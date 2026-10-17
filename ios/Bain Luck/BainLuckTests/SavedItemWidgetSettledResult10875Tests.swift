import CryptoKit
import XCTest
@testable import Bain_Luck

/// #10875 × #698 — a saved market widget says "Result unknown" for a settled
/// row whose result the stored data does not support, never Lost.
///
/// `/futures/62134744` (*Marchi vs. Lokoli: Match O/U 21.5*, Polymarket,
/// resolved) serves both legs as `probability 0.5, is_winner false,
/// resolution_source "clob_authoritative"`. Read through `OutcomeVerdict` alone,
/// the widget printed **Lost** for whichever leg the reader chose.
///
/// The fixture is a verbatim copy of `frontend/__tests__/fixtures/settledDisplay698.json`
/// at calibration's frozen source `0cd6a6c695` (sha256 2bf9cd19…), the same
/// bytes Native's #698 consumer carries: `served` = the banked
/// `/api/futures/<id>` bodies WITHOUT the new key (an older server),
/// `contract` = what `settlement_display.py` serves per row. Each specimen runs
/// twice: as served (the fallback) and with the contract attached.
@MainActor
final class SavedItemWidgetSettledResult10875Tests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_792_000_000) // 2026-10-17T20:26:40Z

    // MARK: - Fixture

    private static let fixtureData: Data = {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures/settledDisplay698.0cd6a6c695.json")
        return try! Data(contentsOf: url)
    }()

    private static let fixture: [String: Any] = {
        try! JSONSerialization.jsonObject(with: fixtureData) as! [String: Any]
    }()

    private enum Mode: CaseIterable { case served, contract }

    private func contract(_ id: String) -> [String: [String: String]] {
        let specimens = Self.fixture["specimens"] as! [String: Any]
        let spec = specimens[id] as! [String: Any]
        return spec["contract"] as? [String: [String: String]] ?? [:]
    }

    /// The specimen's body, optionally with each row's contract attached and
    /// any row edited by `edit` (keyed by outcome id).
    private func market(_ id: String, _ mode: Mode,
                        edit: [Int: [String: Any]] = [:]) throws -> SavedWidgetMarketDetail10875 {
        let specimens = Self.fixture["specimens"] as! [String: Any]
        let spec = specimens[id] as! [String: Any]
        var body = spec["served"] as! [String: Any]
        let rows = contract(id)
        var outcomes = body["outcomes"] as! [[String: Any]]
        for index in outcomes.indices {
            let outcomeID = outcomes[index]["id"] as! Int
            if mode == .contract, let row = rows[String(outcomeID)] {
                outcomes[index]["settlement_display"] = row
            }
            for (key, value) in edit[outcomeID] ?? [:] {
                outcomes[index][key] = value
            }
        }
        body["outcomes"] = outcomes
        let data = try JSONSerialization.data(withJSONObject: body)
        return try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetMarketDetail10875.self, from: data)
    }

    func testTheFixtureIsTheFrozenSpecimen() {
        let digest = SHA256.hash(data: Self.fixtureData).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(digest, "2bf9cd195b2fda605cfd8de33c6e64e4cbb9326ec291dc607c04e73b5b9a324c",
                       "the fixture is no longer calibration's frozen 0cd6a6c695 copy")
    }

    // MARK: - The defect

    func testASettledCoinFlipIsUnknownNeverLost() throws {
        for mode in Mode.allCases {
            let m = try market("62134744", mode)
            XCTAssertEqual(m.source, "polymarket")
            XCTAssertEqual(m.outcomes.count, 2, "a leg was dropped by the decode (\(mode))")
            for outcome in m.outcomes {
                let r = SavedWidgetReadingRules10875.market(m, outcomeID: outcome.id, now: t0)
                XCTAssertNotEqual(r.headline?.verdict, "Lost", "\(outcome.name) printed Lost over a 50/50 last price (\(mode))")
                XCTAssertEqual(r.headline?.verdict, "Result unknown", "\(outcome.name) did not say its result is unknown (\(mode))")
                XCTAssertEqual(r.rows.first?.verdict, "Result unknown", "the medium widget did not say unknown (\(mode))")
                XCTAssertEqual(r.phase, .noResult, "an unknown result was given phase \(r.phase) (\(mode))")
                XCTAssertNil(r.headline?.figure, "the last price was printed as a value (\(mode))")
                XCTAssertEqual(r.lastRecordedFigure, "50%", "the last price was not kept as last recorded (\(mode))")
                XCTAssertNil(r.priceCaption, "an unknown result was given a price caption (\(mode))")
                XCTAssertNil(r.becomesLastRecordedAt, "an unknown result was scheduled to change (\(mode))")
                XCTAssertEqual(r.status, "Settled")
                XCTAssertEqual(r.observedAt, SavedWidgetDetailDecoding10875.date("2026-09-24T09:57:47.408009+00:00"),
                               "the last price lost its own clock (\(mode))")
                XCTAssertFalse(r.spoken.localizedCaseInsensitiveContains("lost"), "VoiceOver said lost (\(mode))")
                XCTAssertTrue(r.spoken.contains("unknown"), "VoiceOver did not say unknown (\(mode))")
                XCTAssertTrue(r.spoken.contains("last recorded chance was 50%"), "VoiceOver did not name the last price (\(mode))")
            }
            // No outcome chosen: the hero leg is followed, and it is unknown too.
            let hero = SavedWidgetReadingRules10875.market(m, outcomeID: nil, now: t0)
            XCTAssertEqual(hero.headline?.verdict, "Result unknown", "the hero leg printed \(String(describing: hero.headline?.verdict)) (\(mode))")
        }
    }

    func testTheRuleIsTheServedContract() throws {
        for mode in Mode.allCases {
            for id in ["62134744", "13798072", "12194657"] {
                let m = try market(id, mode)
                for outcome in m.outcomes {
                    let expected: SavedWidgetReadingRules10875.SettledResult? = {
                        switch contract(id)[String(outcome.id)]?["verdict"] {
                        case "won": return .won
                        case "lost": return .lost
                        case .some: return .unknown
                        case nil: return nil
                        }
                    }()
                    XCTAssertEqual(SavedWidgetReadingRules10875.settledResult(outcome, marketSource: m.source, marketStatus: m.status),
                                   expected, "\(id)/\(outcome.id) disagrees with the server's contract (\(mode))")
                }
            }
        }
    }

    // MARK: - Controls: definite results keep their words

    func testATerminalAgreementStillReadsWonAndLost() throws {
        for mode in Mode.allCases {
            let m = try market("13798072", mode)
            let no = SavedWidgetReadingRules10875.market(m, outcomeID: 125653874, now: t0)
            XCTAssertEqual(no.headline?.verdict, "Won", "a 1/true/api_settlement row stopped reading Won (\(mode))")
            XCTAssertEqual(no.phase, .result)
            XCTAssertNil(no.lastRecordedFigure)
            let yes = SavedWidgetReadingRules10875.market(m, outcomeID: 125653873, now: t0)
            XCTAssertEqual(yes.headline?.verdict, "Lost", "a 0/false/api_settlement row stopped reading Lost (\(mode))")
            XCTAssertEqual(yes.phase, .result)
        }
    }

    func testAFieldThatAllLostIsNotUnknown() throws {
        for mode in Mode.allCases {
            let m = try market("12194657", mode)
            for outcome in m.outcomes {
                XCTAssertEqual(SavedWidgetReadingRules10875.market(m, outcomeID: outcome.id, now: t0).headline?.verdict, "Lost",
                               "an independent field settling with no winner was read as unknown: \(outcome.name) (\(mode))")
            }
        }
    }

    func testAnOpenBoardKeepsItsPrices() throws {
        let m = try market("113360", .served, edit: [1629208: ["last_updated": ISO8601DateFormatter().string(from: t0)]])
        let r = SavedWidgetReadingRules10875.market(m, outcomeID: 1629208, now: t0)
        XCTAssertNil(r.headline?.verdict, "an open market's row was given a verdict")
        XCTAssertEqual(r.headline?.figure, "61%", "an open market's price was withheld")
        XCTAssertEqual(r.phase, .current)
        XCTAssertNil(SavedWidgetReadingRules10875.settledResult(m.outcomes[0], marketSource: m.source, marketStatus: m.status),
                     "the #698 rule ran on an open market")
    }

    func testAnotherVenueKeepsTheSettlementRule() throws {
        // No contract and not a targeted venue: OutcomeVerdict, unchanged.
        let m = try market("62134744", .served, edit: [:])
        let kalshi = SavedWidgetMarketDetail10875(id: m.id, name: m.name, status: m.status, source: "kalshi",
                                                  leadOutcomeId: m.leadOutcomeId, outcomes: m.outcomes)
        XCTAssertNil(SavedWidgetReadingRules10875.settledResult(kalshi.outcomes[0], marketSource: "kalshi", marketStatus: "resolved"))
        XCTAssertEqual(SavedWidgetReadingRules10875.market(kalshi, outcomeID: kalshi.outcomes[0].id, now: t0).headline?.verdict,
                       OutcomeVerdict.verdict(isWinner: false, resolutionSource: "clob_authoritative", marketResolved: true)?.label,
                       "an untargeted venue no longer reads the settlement rule")
    }

    // MARK: - The fallback can only say less

    func testTheFallbackRefusesAnUnrecognisedOrRetractedSource() throws {
        for source in ["unrecognized_future_source", "ungradeable_result", ""] {
            let m = try market("13798072", .served, edit: [125653874: ["resolution_source": source],
                                                           125653873: ["resolution_source": source]])
            for outcome in m.outcomes {
                XCTAssertEqual(SavedWidgetReadingRules10875.market(m, outcomeID: outcome.id, now: t0).headline?.verdict,
                               "Result unknown", "\(outcome.name) with source \"\(source)\" said more than the server")
            }
        }
        let nullSource = try market("13798072", .served, edit: [125653874: ["resolution_source": NSNull()]])
        XCTAssertEqual(SavedWidgetReadingRules10875.market(nullSource, outcomeID: 125653874, now: t0).headline?.verdict,
                       "Result unknown", "a null source was read as a result")
    }

    func testANearTerminalPriceIsNotAResult() throws {
        for (price, winner) in [(0.999, true), (0.001, false)] {
            let m = try market("13798072", .served, edit: [125653874: ["probability": price, "is_winner": winner]])
            let r = SavedWidgetReadingRules10875.market(m, outcomeID: 125653874, now: t0)
            XCTAssertEqual(r.headline?.verdict, "Result unknown", "\(price)/\(winner) was rounded into a result")
        }
    }

    func testAnUnknownWithNoPriceIsNumberless() throws {
        let m = try market("62134744", .contract, edit: [234738381: ["probability": NSNull()]])
        let r = SavedWidgetReadingRules10875.market(m, outcomeID: 234738381, now: t0)
        XCTAssertEqual(r.headline?.verdict, "Result unknown")
        XCTAssertNil(r.lastRecordedFigure, "a number was invented for a row with no price")
        XCTAssertNil(r.observedAt, "a clock was printed with no price to belong to")
        XCTAssertFalse(r.spoken.contains("%"), "VoiceOver read a number the row does not hold")
    }

    // MARK: - Decode

    func testAContractWordThisBuildDoesNotKnowIsUnknown() throws {
        let m = try market("13798072", .served, edit: [125653874: ["settlement_display": ["verdict": "void", "basis": "x"]],
                                                       125653873: ["settlement_display": ["verdict": 3]]])
        XCTAssertEqual(m.outcomes.first { $0.id == 125653874 }?.settlementDisplay?.verdict, "void")
        XCTAssertNotNil(m.outcomes.first { $0.id == 125653873 }?.settlementDisplay, "an object contract was dropped")
        for outcome in m.outcomes {
            XCTAssertEqual(SavedWidgetReadingRules10875.market(m, outcomeID: outcome.id, now: t0).headline?.verdict,
                           "Result unknown", "an unknown contract word for \(outcome.name) was read as a result")
        }
    }

    func testAMalformedContractNeitherDropsTheChosenLegNorInventsAResult() throws {
        let m = try market("62134744", .served, edit: [234738381: ["settlement_display": "unknown"],
                                                       234738382: ["settlement_display": NSNull()]])
        for id in [234738381, 234738382] {
            let leg = m.outcomes.first { $0.id == id }
            XCTAssertNotNil(leg, "a malformed contract failed leg \(id), so the widget would read \"No longer listed\"")
            XCTAssertNil(leg?.settlementDisplay, "a non-object contract was read as present on \(id)")
            let r = SavedWidgetReadingRules10875.market(m, outcomeID: id, now: t0)
            XCTAssertEqual(r.headline?.verdict, "Result unknown", "\(id) printed \(String(describing: r.headline?.verdict))")
        }
    }
}
