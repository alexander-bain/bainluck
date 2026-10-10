import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10850 — AT HALFTIME THE 1ST HALF CARDS SHOW HOW THE HALF FINISHED.
///
/// The iPhone twin of web `closedHalfGradesAtHalftime10850.test.tsx`. At
/// halftime the server stops quoting a finished half (#1588), and the half's
/// cards vanished at the moment the half had a result. Live's server half
/// (PR #10856, 6eaa74a28c) serves those rows under `closed_period_markets`:
/// `probability` null, `window_closed` true, `period_score {home, away}`.
///
/// ═══ THE BYTES ═══
/// The 1H rows of `15322373` (Indiana @ Nebraska, banked 16:41Z for #10830),
/// moved to the new key with their prices removed, as the server does. The
/// halftime score is the production look's 17:56Z read, Nebraska 10–3. This
/// is the contract applied to real rows, not served bytes. The cross-card
/// score split and the null total line are Root's two synthetic
/// counterexamples (ROOT-INDEPENDENT-90B1.md).
final class ClosedHalfGradesAtHalftime10850Tests: XCTestCase {

    private static let home = "Nebraska Cornhuskers"
    private static let away = "Indiana Hoosiers"
    private static let halftime = ["home": 10, "away": 3]

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("frontend/__tests__/fixtures/ux10830_game_markets_15322373.20261010T1641Z.json")
    }

    private static func isFirstHalf(_ row: [String: Any]) -> Bool {
        let type = row["market_type"] as? String
        return (type == "half_spread" || type == "half_total") && row["period"] as? String == "1H"
    }

    /// The served body at halftime, with `closed` as its new key (nil: no key).
    /// `edit` changes one closed row, the way each counterexample needs.
    private static func body(
        closed: Bool = true,
        score: (_ row: [String: Any]) -> [String: Int] = { _ in halftime },
        edit: (_ row: inout [String: Any]) -> Void = { _ in },
        editBody: (_ body: inout [String: Any]) -> Void = { _ in }
    ) throws -> GameMarketsResponse {
        var json = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any]
        )
        let period = try XCTUnwrap(json["period_markets"] as? [[String: Any]])
        json["period_markets"] = period.filter { !isFirstHalf($0) }
        json["home_score"] = 10
        json["away_score"] = 3
        json["status"] = "live"
        if closed {
            json["closed_period_markets"] = period.filter(isFirstHalf).map { row -> [String: Any] in
                var r = row
                r["probability"] = NSNull()
                r.removeValue(forKey: "over_probability")
                r["window_closed"] = true
                r["period_score"] = score(row)
                edit(&r)
                return r
            }
        }
        editBody(&json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self,
                                  from: JSONSerialization.data(withJSONObject: json))
    }

    private static func map(_ markets: GameMarketsResponse, status: String = "live") -> MarketMapView {
        MarketMapView(
            gameMarkets: markets, eventStatus: status,
            homeTeam: home, awayTeam: away, homeAbbr: "NEB", awayAbbr: "IU",
            homeColor: .red, awayColor: .blue, sportKey: "americanfootball_ncaaf",
            absenceStatedAbove: false
        )
    }

    private static func cards(_ markets: GameMarketsResponse, status: String = "live") -> [String] {
        map(markets, status: status).mapEntries.map(\.id)
    }

    private static func closedBinding(_ entry: MarketMapView.MapEntry) -> ClosedHalfMarkets.Binding? {
        switch entry.kind {
        case let .halfMargin(_, _, _, closed), let .halfTotal(_, _, _, closed): return closed
        case .fullMargin, .fullTotal: return nil
        }
    }

    private static func periodOf(_ o: GameMarketOutcome) -> String? { o.period }

    // MARK: - The key decodes, and a body the app cannot read costs only these cards

    func testTheNewKeyDecodesWithItsTwoFields() throws {
        let rows = try XCTUnwrap(try Self.body().closedPeriodMarkets)
        XCTAssertEqual(rows.count, 20)
        XCTAssertTrue(rows.allSatisfy { $0.windowClosed == true && $0.row.probability == nil })
        XCTAssertTrue(rows.allSatisfy { $0.periodScore == .init(home: 10, away: 3) })
    }

    func testAnUnreadableKeyIsNilAndThePageStillDecodes() throws {
        let markets = try Self.body(edit: { $0["period_score"] = "10-3" })
        XCTAssertNil(markets.closedPeriodMarkets)
        XCTAssertFalse((markets.periodMarkets ?? []).isEmpty)
    }

    // MARK: - ClosedHalfMarkets, read strictly

    func testItHandsBackTheHalfsRowsAndTheScoreTheyGradeBy() throws {
        let markets = try Self.body()
        let spread = try XCTUnwrap(ClosedHalfMarkets.binding(
            closed: markets.closedPeriodMarkets, quoting: markets.periodMarkets,
            kind: .spread, half: "1H", periodOf: Self.periodOf))
        XCTAssertEqual(spread.rows.count, 12)
        XCTAssertEqual(spread.score, HalfScoreSplit(home: 10, away: 3))
        let total = try XCTUnwrap(ClosedHalfMarkets.binding(
            closed: markets.closedPeriodMarkets, quoting: markets.periodMarkets,
            kind: .total, half: "1H", periodOf: Self.periodOf))
        XCTAssertEqual(total.rows.count, 8)
    }

    func testAHalfThatStillQuotesKeepsItsQuotingCard() throws {
        let markets = try Self.body()
        let quoting = markets.closedPeriodMarkets!.map(\.row)
        XCTAssertNil(ClosedHalfMarkets.binding(
            closed: markets.closedPeriodMarkets, quoting: quoting,
            kind: .spread, half: "1H", periodOf: Self.periodOf))
    }

    func testRefusesAPricedRowAMissingScoreAndAnOpenWindow() throws {
        for edit: (inout [String: Any]) -> Void in [
            { $0["probability"] = 0.5 },
            { $0["period_score"] = NSNull() },
            { $0["window_closed"] = NSNull() },
        ] {
            var first = true
            let markets = try Self.body(edit: { row in
                if first, row["market_type"] as? String == "half_spread" { edit(&row); first = false }
            })
            XCTAssertNil(ClosedHalfMarkets.binding(
                closed: markets.closedPeriodMarkets, quoting: markets.periodMarkets,
                kind: .spread, half: "1H", periodOf: Self.periodOf))
        }
    }

    /// Root's counterexample 1: spread rows at 10–3, total rows at 7–3. Each
    /// type agrees with itself; the half does not.
    func testMarginAndTotalRowsThatDisagreeOnTheHalfsScoreRefuseBothCards() throws {
        let markets = try Self.body(score: {
            $0["market_type"] as? String == "half_spread" ? Self.halftime : ["home": 7, "away": 3]
        })
        for kind in [ClosedHalfMarkets.Kind.spread, .total] {
            XCTAssertNil(ClosedHalfMarkets.binding(
                closed: markets.closedPeriodMarkets, quoting: markets.periodMarkets,
                kind: kind, half: "1H", periodOf: Self.periodOf), "\(kind)")
        }
    }

    /// Root's counterexample 2: one total row loses its line. A NaN or an
    /// infinity cannot arrive as JSON, so those are built as values.
    func testAClosedTotalRowWithoutAFiniteLineRefusesItsCard() throws {
        let markets = try Self.body(edit: { row in
            if row["market_type"] as? String == "half_total", row["threshold"] as? Double == 27.5,
               row["outcome_name"] as? String == "Over" { row["threshold"] = NSNull() }
        })
        XCTAssertNil(ClosedHalfMarkets.binding(
            closed: markets.closedPeriodMarkets, quoting: markets.periodMarkets,
            kind: .total, half: "1H", periodOf: Self.periodOf))
        XCTAssertNotNil(ClosedHalfMarkets.binding(
            closed: markets.closedPeriodMarkets, quoting: markets.periodMarkets,
            kind: .spread, half: "1H", periodOf: Self.periodOf), "the margin card is not the total's")

        let good = try XCTUnwrap(try Self.body().closedPeriodMarkets)
        for line in [Double.nan, .infinity] {
            let rows = good.map { r -> ClosedPeriodOutcome in
                guard r.row.marketType == "half_total", r.row.threshold == 27.5 else { return r }
                return ClosedPeriodOutcome(row: Self.withThreshold(r.row, line),
                                           windowClosed: r.windowClosed, periodScore: r.periodScore)
            }
            XCTAssertNil(ClosedHalfMarkets.binding(
                closed: rows, quoting: [], kind: .total, half: "1H", periodOf: Self.periodOf), "\(line)")
        }
    }

    func testAnExplicitZeroLineIsARealLine() throws {
        let markets = try Self.body(edit: { row in
            if row["market_type"] as? String == "half_total", row["threshold"] as? Double == 27.5 { row["threshold"] = 0 }
        })
        XCTAssertNotNil(ClosedHalfMarkets.binding(
            closed: markets.closedPeriodMarkets, quoting: markets.periodMarkets,
            kind: .total, half: "1H", periodOf: Self.periodOf))
    }

    func testASpreadsCutLivesInItsTitleSoANullThresholdStillDraws() throws {
        let rows = try XCTUnwrap(try Self.body().closedPeriodMarkets).filter { $0.row.marketType == "half_spread" }
        XCTAssertTrue(rows.allSatisfy { $0.row.threshold == nil })
        let lines = SpreadRungs.unpricedLines(
            from: rows.map { SpreadRungs.Leg(marketName: $0.row.marketName, outcomeName: $0.row.outcomeName) },
            home: Self.home, away: Self.away,
            sportUnit: SportVocab.forSport("americanfootball_ncaaf").unit, readsHalfTitles: true
        ).lines
        XCTAssertEqual(lines.map(\.margin).sorted(), [-9.5, -7.5, -6.5, -5.5, -4.5, -2.5])
        XCTAssertTrue(lines.allSatisfy { !$0.isHome }, "every line is Indiana's cover")
    }

    // MARK: - #6676, folded in: no price, no rung

    func testAnUnpricedNamedLegIsNoRung() {
        let unit = SportVocab.forSport("americanfootball_nfl").unit
        let legs = [
            SpreadRungs.Leg(marketName: "Spread", outcomeName: "Seattle wins by over 3.5 points", probability: nil),
            SpreadRungs.Leg(marketName: "Spread", outcomeName: "Seattle wins by over 6.5 points", probability: 0.31),
        ]
        let map = SpreadRungs.map(from: legs, home: "Seattle Seahawks", away: "New England Patriots", sportUnit: unit)
        XCTAssertEqual(map.rungs.map(\.margin), [6.5], "the unpriced -3.5 is not drawn as a coin flip")
        XCTAssertEqual(map.rungs.map(\.probability), [0.31])
    }

    func testNoTotalsMapBuildsAFallbackPrice() throws {
        let file = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        let source = try String(contentsOf: file, encoding: .utf8)
        let body = try XCTUnwrap(source.range(of: "private func extractTotalThresholds("))
        let end = try XCTUnwrap(source.range(of: "private func totalLines(", range: body.upperBound..<source.endIndex))
        XCTAssertFalse(String(source[body.upperBound..<end.lowerBound]).contains("?? 0.5"))
        let rungs = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Utilities/SpreadRungs.swift")
        XCTAssertFalse(try String(contentsOf: rungs, encoding: .utf8).contains("probability ?? 0.5"))
    }

    // MARK: - The live page at halftime

    func testControlWithoutTheKeyTheFirstHalfCardsAreGone() throws {
        let ids = Self.cards(try Self.body(closed: false))
        XCTAssertFalse(ids.contains("margin-1st half margin"))
        XCTAssertFalse(ids.contains("total-1st half total map"))
        XCTAssertTrue(ids.contains("margin-2nd half margin"))
    }

    func testWithTheKeyBothFirstHalfCardsAreBackOnTheServedScore() throws {
        let entries = Self.map(try Self.body()).mapEntries
        for id in ["margin-1st half margin", "total-1st half total map"] {
            let entry = try XCTUnwrap(entries.first { $0.id == id }, id)
            XCTAssertEqual(Self.closedBinding(entry)?.score, HalfScoreSplit(home: 10, away: 3), id)
        }
        let second = try XCTUnwrap(entries.first { $0.id == "margin-2nd half margin" })
        XCTAssertNil(Self.closedBinding(second), "the 2nd half still quotes")
    }

    func testClosedHalfMarginSurvivesEmptyAndMissingFullGameSpreads() throws {
        for includesSpreadsKey in [true, false] {
            let markets = try Self.body(editBody: { json in
                if includesSpreadsKey { json["spreads"] = [] as [[String: Any]] }
                else { json.removeValue(forKey: "spreads") }
            })
            let entries = Self.map(markets).mapEntries
            let margin = try XCTUnwrap(entries.first { $0.id == "margin-1st half margin" })
            XCTAssertEqual(Self.closedBinding(margin)?.score, HalfScoreSplit(home: 10, away: 3))
            XCTAssertFalse(entries.contains { $0.id == "full-margin" })
            XCTAssertTrue(entries.contains { $0.id == "total-1st half total map" })
        }
    }

    /// Rendering only the card would miss the outer EmptyView gate: exercise
    /// the whole maps browser with the closed margin as its only content.
    @MainActor
    func testClosedHalfMarginOnlyKeepsTheWholeMapsViewVisible() throws {
        for includesSpreadsKey in [true, false] {
            let markets = try Self.body(editBody: { json in
                if includesSpreadsKey { json["spreads"] = [] as [[String: Any]] }
                else { json.removeValue(forKey: "spreads") }
                json["totals"] = [] as [[String: Any]]
                json["period_markets"] = [] as [[String: Any]]
                json["closed_period_markets"] = (json["closed_period_markets"] as? [[String: Any]])?
                    .filter { $0["market_type"] as? String == "half_spread" }
            })
            let map = Self.map(markets)
            XCTAssertEqual(map.mapEntries.map(\.id), ["margin-1st half margin"])
            let view = map.frame(width: 390).background(Color.white)
            let renderer = rendererForMeasurement(view, at: .large)
            let image = try XCTUnwrap(renderer.uiImage)
            XCTAssertGreaterThan(image.size.height, 100)
        }
    }

    func testConflictingFinalsDrawNeitherFirstHalfCard() throws {
        let ids = Self.cards(try Self.body(score: {
            $0["market_type"] as? String == "half_spread" ? Self.halftime : ["home": 7, "away": 3]
        }))
        XCTAssertFalse(ids.contains("margin-1st half margin"))
        XCTAssertFalse(ids.contains("total-1st half total map"))
    }

    func testAMissingTotalLineWithholdsOnlyThePointsCard() throws {
        let ids = Self.cards(try Self.body(edit: { row in
            if row["market_type"] as? String == "half_total", row["threshold"] as? Double == 27.5,
               row["outcome_name"] as? String == "Over" { row["threshold"] = NSNull() }
        }))
        XCTAssertFalse(ids.contains("total-1st half total map"))
        XCTAssertTrue(ids.contains("margin-1st half margin"))
    }

    func testAGameThatIsNotLiveNeverReadsTheKey() throws {
        XCTAssertFalse(Self.cards(try Self.body(), status: "scheduled").contains("margin-1st half margin"))
    }

    /// The camera, for the reader check: writes each 1st half card at
    /// default and AX3 text to `$TMPDIR/ux10850-<card>-<size>.png` for the
    /// author to open and read. The phone shows one card per tab.
    @MainActor
    func testRendersTheHalftimeCardsForTheReaderCheck() throws {
        let map = Self.map(try Self.body())
        for (id, name) in [("margin-1st half margin", "margin"), ("total-1st half total map", "total")] {
            let entry = try XCTUnwrap(map.mapEntries.first { $0.id == id })
            for (size, tag) in [(DynamicTypeSize.large, "default"), (.accessibility3, "ax3")] {
                let view = map.mapEntryCard(entry).frame(width: 390).background(Color.white)
                let renderer = rendererForMeasurement(view, at: size)
                renderer.scale = 3
                let image = try XCTUnwrap(renderer.uiImage, id)
                try XCTUnwrap(image.pngData()).write(to: FileManager.default.temporaryDirectory
                    .appendingPathComponent("ux10850-\(name)-\(tag).png"))
                XCTAssertGreaterThan(image.size.height, 100, id)
            }
        }
    }

    private static func withThreshold(_ o: GameMarketOutcome, _ line: Double) -> GameMarketOutcome {
        GameMarketOutcome(
            _marketId: o._marketId, _marketIds: o._marketIds, contributorOutcomeIds: o.contributorOutcomeIds,
            marketName: o.marketName, outcomeName: o.outcomeName, probability: o.probability,
            source: o.source, threshold: line, overProbability: o.overProbability,
            marketType: o.marketType, movement: o.movement, period: o.period,
            isWinner: o.isWinner, resolutionSource: o.resolutionSource
        )
    }
}
