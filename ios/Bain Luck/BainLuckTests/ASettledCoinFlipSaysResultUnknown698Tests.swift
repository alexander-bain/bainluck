import XCTest
@testable import Bain_Luck

/// #698 — a settled Polymarket row whose result the stored data does not
/// support says "Result unknown", not Lost; web and native agree.
///
/// The fixture is a verbatim copy of `frontend/__tests__/fixtures/settledDisplay698.json`
/// at calibration's frozen source `0cd6a6c695` (sha256 2bf9cd19…, Root's pin):
/// `served` = the banked `/api/futures/<id>` bodies WITHOUT the new key (what an
/// older server sends), `contract` = what `settlement_display.py` serves per row.
/// Each specimen runs twice: as served (fallback) and with the contract attached.
final class ASettledCoinFlipSaysResultUnknown698Tests: XCTestCase {

    // MARK: - Fixture

    private static let fixture: [String: Any] = {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures/settledDisplay698.0cd6a6c695.json")
        let data = try! Data(contentsOf: url)
        return try! JSONSerialization.jsonObject(with: data) as! [String: Any]
    }()

    private enum Mode { case served, contract }

    private func specimen(_ id: String) -> [String: Any] {
        let specimens = Self.fixture["specimens"] as! [String: Any]
        return specimens[id] as! [String: Any]
    }

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// The specimen's body, optionally with each row's contract attached and
    /// any row edited by `edit` (keyed by outcome id).
    private func market(
        _ id: String,
        _ mode: Mode,
        edit: [Int: [String: Any]] = [:]
    ) throws -> FuturesMarketDetail {
        let spec = specimen(id)
        var body = spec["served"] as! [String: Any]
        let contract = spec["contract"] as? [String: Any] ?? [:]
        var outcomes = body["outcomes"] as! [[String: Any]]
        for index in outcomes.indices {
            let outcomeId = outcomes[index]["id"] as! Int
            if mode == .contract, let row = contract[String(outcomeId)] {
                outcomes[index]["settlement_display"] = row
            }
            for (key, value) in edit[outcomeId] ?? [:] {
                outcomes[index][key] = value
            }
        }
        body["outcomes"] = outcomes
        let data = try JSONSerialization.data(withJSONObject: body)
        return try decoder().decode(FuturesMarketDetail.self, from: data)
    }

    private func rowValues(_ market: FuturesMarketDetail) -> [Int: FuturesDetailRowValue] {
        Dictionary(uniqueKeysWithValues: market.outcomes.map {
            ($0.id, FuturesDetailRowValue.of($0, marketStatus: market.status, marketSource: market.source))
        })
    }

    private func outcome(_ json: String) throws -> FuturesOutcome {
        try decoder().decode(FuturesOutcome.self, from: Data(json.utf8))
    }

    // MARK: - Decode

    func testTheContractDecodesAndAnAbsentOneIsNil() throws {
        let present = try outcome(#"{"id":1,"name":"Over","probability":0.5,"is_winner":false,"resolution_source":"clob_authoritative","settlement_display":{"verdict":"unknown","basis":"nonterminal_stored_price"}}"#)
        XCTAssertEqual(present.settlementDisplay, SettlementDisplay698(verdict: "unknown", basis: "nonterminal_stored_price"))
        let absent = try outcome(#"{"id":1,"name":"Over","probability":0.5,"is_winner":false}"#)
        XCTAssertNil(absent.settlementDisplay)
        let null = try outcome(#"{"id":1,"name":"Over","probability":0.5,"is_winner":false,"settlement_display":null}"#)
        XCTAssertNil(null.settlementDisplay)
    }

    func testAnUnexpectedShapeNeitherFailsTheDecodeNorInventsAResult() throws {
        // A verdict word this build does not know, a non-string verdict, a
        // missing basis: the outcome still decodes and the row says unknown.
        for display in [
            #"{"verdict":"void","basis":"a_new_basis"}"#,
            #"{"verdict":7,"basis":["x"]}"#,
            #"{"basis":"stored_terminal_agreement"}"#,
            #"{}"#,
        ] {
            let o = try outcome(#"{"id":1,"name":"Yes","probability":1.0,"is_winner":true,"resolution_source":"api_settlement","settlement_display":"# + display + "}")
            XCTAssertNotNil(o.settlementDisplay, display)
            XCTAssertEqual(SettledResultDisplay698.certainty(o, marketSource: "polymarket", marketStatus: "resolved"),
                           .unknown, display)
            XCTAssertEqual(FuturesDetailRowValue.of(o, marketStatus: "resolved", marketSource: "polymarket"),
                           .resultUnknown(lastRecorded: 1.0), display)
        }
        // Not an object at all: the key reads as absent and the page still loads.
        let junk = try outcome(#"{"id":1,"name":"Yes","probability":0.5,"is_winner":true,"settlement_display":"won"}"#)
        XCTAssertNil(junk.settlementDisplay)
    }

    // MARK: - The four specimens, both modes

    /// 62134744 — both legs 0.5 / false / clob_authoritative. Before #698 each
    /// row printed Lost. Now both say Result unknown, Last recorded 50%, and the
    /// hero names NOBODY over a board-level "Result unknown" — web's mounted page
    /// on this same verbatim fixture (`settledCoinFlipSaysResultUnknown698.test.tsx`:
    /// "crowns nobody … says Result unknown"). #11616 R1: 0d239c9d named "Over" here.
    func testTheCoinFlipSaysResultUnknownOnBothRows() throws {
        for mode in [Mode.served, .contract] {
            let m = try market("62134744", mode)
            let values = rowValues(m)
            XCTAssertEqual(values.count, 2)
            for (_, value) in values {
                XCTAssertEqual(value, .resultUnknown(lastRecorded: 0.5), "\(mode)")
                XCTAssertFalse(value.printsMovement)
            }
            XCTAssertEqual(SettledResultDisplay698.board(m), .all, "\(mode)")
            XCTAssertNil(futuresDetailHeroOutcome(m), "a row whose result is unknown is not the answer: \(mode)")
            XCTAssertEqual(heroValue(m), .resultUnknown(lastRecorded: nil),
                           "the board says Result unknown, with no last price: \(mode)")
            XCTAssertEqual(futuresDetailShareMessage(m), "\(m.name) on Bain Luck",
                           "a settled unknown is never quoted as a live chance")
        }
    }

    /// The control: the legacy rule alone reads these rows as LOST. That is the
    /// defect, so the new decision must be the one that runs.
    func testTheLegacyRuleAloneWouldHavePrintedLost() throws {
        let m = try market("62134744", .served)
        for o in m.outcomes {
            XCTAssertEqual(OutcomeVerdict.verdict(isWinner: o.isWinner, resolutionSource: o.resolutionSource,
                                                  marketResolved: true), .lost)
        }
    }

    /// 13798072 — No 1.0/true, Yes 0.0/false, api_settlement. A real result.
    func testATerminalAgreementStaysAResult() throws {
        for mode in [Mode.served, .contract] {
            let m = try market("13798072", mode)
            let values = rowValues(m)
            XCTAssertEqual(values[125653874], .verdict(.won), "\(mode)")
            XCTAssertEqual(values[125653873], .verdict(.lost), "\(mode)")
            XCTAssertNil(SettledResultDisplay698.board(m))
            let hero = try XCTUnwrap(futuresDetailHeroOutcome(m))
            XCTAssertEqual(hero.id, 125653874)
            XCTAssertTrue(SettledResultDisplay698.heroWearsWinnerBadge(hero, in: m))
            XCTAssertFalse(SettledResultDisplay698.isUnknown(hero, in: m))
        }
    }

    /// 12194657 — ten candidates at 0/false. An independent field can settle
    /// with no affirmative winner: all Lost, not unknown, no pair rule.
    func testAFieldWithNoWinnerIsAllLostNotUnknown() throws {
        for mode in [Mode.served, .contract] {
            let m = try market("12194657", mode)
            let values = rowValues(m)
            XCTAssertEqual(values.count, 10)
            XCTAssertTrue(values.values.allSatisfy { $0 == .verdict(.lost) }, "\(mode)")
            XCTAssertNil(SettledResultDisplay698.board(m))
        }
    }

    /// 113360 — an open board. No key is served and nothing here changes.
    func testAnOpenBoardIsUntouched() throws {
        let m = try market("113360", .served)
        XCTAssertEqual(m.status, "open")
        for o in m.outcomes {
            XCTAssertNil(o.settlementDisplay)
            XCTAssertNil(SettledResultDisplay698.certainty(o, marketSource: m.source, marketStatus: m.status))
            XCTAssertEqual(FuturesDetailRowValue.of(o, marketStatus: m.status, marketSource: m.source),
                           FuturesDetailRowValue.of(o, marketStatus: m.status))
        }
        XCTAssertNil(SettledResultDisplay698.board(m))
    }

    // MARK: - The absent-contract fallback says less than the server, never more

    /// Root's counterexample on b0e37eb2b1: `1 / true / "unrecognized_future_source"`
    /// read WON on web while the server said unknown.
    func testAnUnrecognizedSourceIsUnknownEvenAtATerminalPrice() throws {
        for (p, w) in [(1.0, true), (0.0, false)] {
            let m = try market("13798072", .served, edit: [
                125653874: ["probability": p, "is_winner": w, "resolution_source": "unrecognized_future_source"],
            ])
            let row = try XCTUnwrap(m.outcomes.first { $0.id == 125653874 })
            XCTAssertEqual(SettledResultDisplay698.certainty(row, marketSource: m.source, marketStatus: m.status),
                           .unknown, "\(p)/\(w)")
            XCTAssertFalse(SettledResultDisplay698.heroWearsWinnerBadge(row, in: m))
        }
    }

    func testTheFallbackClauses() {
        typealias S = SettledResultDisplay698
        XCTAssertEqual(S.fallback(probability: 1, isWinner: true, resolutionSource: "api_settlement"), .won)
        XCTAssertEqual(S.fallback(probability: 0, isWinner: false, resolutionSource: "clob_authoritative"), .lost)
        // Midrange, whatever the grade: a 0.999 is not a 1.
        XCTAssertEqual(S.fallback(probability: 0.999, isWinner: true, resolutionSource: "api_settlement"), .unknown)
        XCTAssertEqual(S.fallback(probability: 0.5, isWinner: false, resolutionSource: "api_settlement"), .unknown)
        // Disagreeing price and grade.
        XCTAssertEqual(S.fallback(probability: 1, isWinner: false, resolutionSource: "api_settlement"), .unknown)
        XCTAssertEqual(S.fallback(probability: 0, isWinner: true, resolutionSource: "api_settlement"), .unknown)
        // Retracted, missing, empty or non-tier-3 source.
        XCTAssertEqual(S.fallback(probability: 0, isWinner: false, resolutionSource: "ungradeable_result"), .unknown)
        XCTAssertEqual(S.fallback(probability: 0, isWinner: false, resolutionSource: nil), .unknown)
        XCTAssertEqual(S.fallback(probability: 0, isWinner: false, resolutionSource: ""), .unknown)
        XCTAssertEqual(S.fallback(probability: 0, isWinner: false, resolutionSource: "game_score"), .unknown)
        // Missing grade or price is never read as zero.
        XCTAssertEqual(S.fallback(probability: 0, isWinner: nil, resolutionSource: "api_settlement"), .unknown)
        XCTAssertEqual(S.fallback(probability: nil, isWinner: false, resolutionSource: "api_settlement"), .unknown)
        XCTAssertEqual(S.fallback(probability: .nan, isWinner: false, resolutionSource: "api_settlement"), .unknown)
    }

    /// A midrange `true` must not crown a phantom champion on the hero — nor be
    /// named at all (web `:291` "a midrange TRUE marked unknown crowns nobody").
    func testAMidrangeTrueIsNeverCrowned() throws {
        for mode in [Mode.served, .contract] {
            let m = try market("62134744", mode, edit: [234738381: ["is_winner": true, "probability": 0.55]])
            let row = try XCTUnwrap(m.outcomes.first { $0.id == 234738381 })
            XCTAssertTrue(SettledResultDisplay698.isUnknown(row, in: m), "\(mode)")
            XCTAssertNil(futuresDetailHeroOutcome(m), "\(mode)")
            // The decision the hero actually prints: the board's unknown, never Won.
            XCTAssertEqual(heroValue(m), .resultUnknown(lastRecorded: nil), "\(mode)")
            XCTAssertEqual(futuresDetailShareMessage(m), "\(m.name) on Bain Luck", "\(mode)")
        }
    }

    /// The opposite direction on the same board: with no contract served, a
    /// terminal 1 / true leg IS a supported winner, so the hero names it and the
    /// board is no longer all-unknown. With the served contract still saying
    /// "unknown" for that row, the contract governs and nobody is named.
    func testATerminalWinnerOnTheCoinFlipBoardIsNamedUnlessTheContractSaysUnknown() throws {
        let edit: [Int: [String: Any]] = [234738381: ["is_winner": true, "probability": 1.0]]
        let fallback = try market("62134744", .served, edit: edit)
        XCTAssertEqual(futuresDetailHeroOutcome(fallback)?.id, 234738381)
        XCTAssertEqual(heroValue(fallback), .verdict(.won))
        XCTAssertEqual(SettledResultDisplay698.board(fallback), .some)
        XCTAssertEqual(futuresDetailShareMessage(fallback), "Over: Won — \(fallback.name) on Bain Luck")

        let contract = try market("62134744", .contract, edit: edit)
        XCTAssertNil(futuresDetailHeroOutcome(contract))
        XCTAssertEqual(heroValue(contract), .resultUnknown(lastRecorded: nil))
    }

    /// The hero's own decision for a market, as `heroSection` computes it.
    private func heroValue(_ m: FuturesMarketDetail) -> FuturesDetailRowValue {
        futuresDetailHeroValue(m, hero: futuresDetailHeroOutcome(m))
    }

    /// An unsupported `is_winner = true` (open, no resolution source) is not a
    /// result anywhere the hero reads: it is a price, and the hero never crowns it.
    func testAnUnsupportedWinnerFlagIsNeverCrownedByTheHero() throws {
        let m = try market("113360", .served, edit: [:])
        let first = try XCTUnwrap(m.outcomes.first)
        let edited = try market("113360", .served, edit: [
            first.id: ["is_winner": true, "resolution_source": NSNull(), "probability": 0.55],
        ])
        let row = try XCTUnwrap(edited.outcomes.first { $0.id == first.id })
        XCTAssertEqual(FuturesDetailRowValue.of(row, marketStatus: edited.status, marketSource: edited.source),
                       .price(0.55))
        XCTAssertNotEqual(heroValue(edited), .verdict(.won))
        XCTAssertFalse(futuresDetailShareMessage(edited).contains("Won"))
    }

    /// Lane1's N1: the My Stuff saved-market card reads the same body and named
    /// `first is_winner == true` as the winner. It now uses the hero's rule, so
    /// a midrange `true` is neither named nor sorted first; a real result is.
    func testTheSavedMarketCardNamesNoPhantomWinner() throws {
        for mode in [Mode.served, .contract] {
            let unknown = try market("62134744", mode, edit: [234738381: ["is_winner": true]])
            let card = FeedFuturesData(savedPinDetail: unknown)
            XCTAssertNil(card.winner, "\(mode)")
            XCTAssertNil(card.winnerOpeningProbability, "\(mode)")
            let terminal = FeedFuturesData(savedPinDetail: try market("13798072", mode))
            XCTAssertEqual(terminal.winner, "No", "\(mode)")
            XCTAssertEqual(terminal.topOutcomes?.first?.id, 125653874, "\(mode)")
        }
    }

    /// An explicit unknown on a row with no price prints no number at all.
    func testAnUnknownRowWithNoPricePrintsNoNumber() throws {
        let m = try market("62134744", .contract, edit: [234738381: ["probability": NSNull()]])
        XCTAssertEqual(rowValues(m)[234738381], .resultUnknown(lastRecorded: nil))
    }

    /// Other venues' settled contracts are not targeted and keep their rule
    /// (#10964: a graded priceless Kalshi leg still reads Lost).
    func testOtherVenuesKeepTheirSettledRule() throws {
        let o = try outcome(#"{"id":1,"name":"Detroit over 4.5","probability":null,"is_winner":false,"resolution_source":"game_score"}"#)
        XCTAssertNil(SettledResultDisplay698.certainty(o, marketSource: "kalshi", marketStatus: "resolved"))
        XCTAssertEqual(FuturesDetailRowValue.of(o, marketStatus: "resolved", marketSource: "kalshi"), .verdict(.lost))
        let midrange = try outcome(#"{"id":2,"name":"Yes","probability":0.5,"is_winner":true,"resolution_source":"api_settlement"}"#)
        XCTAssertNil(SettledResultDisplay698.certainty(midrange, marketSource: "kalshi", marketStatus: "resolved"))
    }

    // MARK: - The page reads these decisions (static: no SwiftUI render here)

    private func pageSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/FuturesDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testTheRowPassesTheMarketSourceAndDrawsTheUnknownState() throws {
        let source = try pageSource()
        let start = try XCTUnwrap(source.range(of: "private func outcomeRow("))
        let end = try XCTUnwrap(source.range(of: "// MARK: - Golf Tournament Dates",
                                             range: start.upperBound..<source.endIndex))
        let row = String(source[start.upperBound..<end.lowerBound])
        XCTAssertTrue(row.contains("marketSource: marketSource)"))
        XCTAssertTrue(row.contains("case .resultUnknown(let lastRecorded):"))
        XCTAssertTrue(row.contains("Text(\"Result unknown\")"))
        XCTAssertTrue(row.contains("Last recorded"))
        XCTAssertTrue(source.contains("marketSource: market.source"))
    }

    func testTheHeroUsesTheSameDecision() throws {
        let source = try pageSource()
        let start = try XCTUnwrap(source.range(of: "private func heroSection("))
        let end = try XCTUnwrap(source.range(of: "private func heroBackground(",
                                             range: start.upperBound..<source.endIndex))
        let hero = String(source[start.upperBound..<end.lowerBound])
        // #11616 replaced the separate unknown flag and Winner capsule with the
        // row's own decision; the runtime half is in the specimen tests above.
        // R1 moved that decision into `futuresDetailHeroValue`, which the
        // specimen tests call directly; the hero must print exactly it.
        XCTAssertTrue(hero.contains("let leader = futuresDetailHeroOutcome(market)"))
        XCTAssertTrue(hero.contains("let heroValue = futuresDetailHeroValue(market, hero: leader)"))
        let valueStart = try XCTUnwrap(source.range(of: "nonisolated func futuresDetailHeroValue("))
        let valueEnd = try XCTUnwrap(source.range(of: "nonisolated enum FuturesLineOrPropLeg8280",
                                                  range: valueStart.upperBound..<source.endIndex))
        let value = String(source[valueStart.upperBound..<valueEnd.lowerBound])
        XCTAssertTrue(value.contains(
            "FuturesDetailRowValue.of($0, marketStatus: market.status, marketSource: market.source)"))
        XCTAssertTrue(value.contains("SettledResultDisplay698.board(market) == .all"))
        XCTAssertTrue(value.contains(".resultUnknown(lastRecorded: nil)"), "the board's unknown quotes no last price")
        // Only a verdict or a price names the row; the board's unknown names nobody.
        let nameGate = try XCTUnwrap(hero.range(of: "case .verdict, .price:"))
        let name = try XCTUnwrap(hero.range(of: "Text(leader.name)"))
        XCTAssertLessThan(nameGate.lowerBound, name.lowerBound)
        XCTAssertTrue(hero.contains("case .resultUnknown:"))
        XCTAssertTrue(hero.contains("Text(\"Result unknown\")"))
        XCTAssertTrue(hero.contains("case .verdict(let verdict):"))
        XCTAssertFalse(hero.contains("leader.isWinner == true"), "`is_winner` alone does not crown")
        XCTAssertFalse(hero.contains(".isWinner"), "the hero reads no raw grade at all")
        XCTAssertFalse(hero.contains("heroWearsWinnerBadge"),
                       "its untargeted branch is the raw `is_winner == true` fallback")
    }
}
