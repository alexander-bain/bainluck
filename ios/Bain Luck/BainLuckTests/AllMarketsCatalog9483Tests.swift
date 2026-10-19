import XCTest
@testable import Bain_Luck

/// #9483 — the native All markets catalog makes web's `questionCatalog`
/// decisions (`frontend/__tests__/components/QuestionCatalog10809.test.tsx`,
/// case for case where the rule is shared), and every served outcome stays
/// reachable on a real 1,598-row payload.
final class AllMarketsCatalog9483Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-10-11T18:00:00Z")!
    private let fresh = "2026-10-11T17:58:00Z"
    private let old = "2026-10-11T16:00:00Z"

    private func markets(_ over: [String: Any] = [:]) throws -> GameMarketsResponse {
        var dict: [String: Any] = [
            "event_id": 1, "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills",
            "status": "scheduled", "totals": [], "player_props": [], "team_totals": [], "spreads": [],
            "period_markets": [], "matchups": [], "other": [],
        ]
        dict.merge(over) { $1 }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func rungs(_ n: Int, source: String = "kalshi") -> [[String: Any]] {
        (0..<n).map { i in
            ["market_name": "Patrick Mahomes passing yards",
             "outcome_name": "Patrick Mahomes: \(200 + i * 25)+",
             "threshold": 200 + i * 25, "over_probability": 0.9 - Double(i) * 0.1, "source": source]
        }
    }

    private let over: [String: Any] = [
        "market_name": "Total points", "outcome_name": "Over 47.5", "threshold": 47.5,
        "over_probability": 0.52, "source": "kalshi",
    ]
    private var under: [String: Any] { over.merging(["outcome_name": "Under 47.5"]) { $1 } }

    private func lineRow(_ fields: [String: Any]) -> QuestionCatalog9483.Row {
        QuestionCatalog9483.Row(
            marketName: fields["market_name"] as? String ?? "",
            outcomeName: fields["outcome_name"] as? String ?? "",
            threshold: fields["threshold"] as? Double,
            pricesOutcome: false,
            overProbability: fields["over_probability"] as? Double,
            source: fields["source"] as? String,
            observedAt: fields["observed_at"] as? String,
            inverted: fields["_inverted"] as? Bool ?? false)
    }

    // MARK: Grouping keeps venue and market identity

    func testTheSameTitleAtTwoVenuesStaysTwoGroups() throws {
        let groups = QuestionCatalog9483.build(
            try markets(["player_props": rungs(2) + rungs(2, source: "polymarket")]), status: "scheduled", now: now)
        XCTAssertEqual(groups.map(\.venue), ["Kalshi", "Polymarket"])
        XCTAssertTrue(groups.allSatisfy { $0.outcomes.count == 2 })
    }

    func testAMarketNoCardDrawsStillLandsInTheCatalog() throws {
        let groups = QuestionCatalog9483.build(try markets(["other": [
            ["market_name": "Will there be a safety?", "outcome_name": "Yes", "probability": 0.07, "source": "kalshi"],
        ]]), status: "scheduled", now: now)
        XCTAssertEqual(groups.count, 1)
        XCTAssertEqual(groups[0].family, .other)
        XCTAssertEqual(groups[0].question, "Will there be a safety?")
        XCTAssertEqual(groups[0].outcomes[0].probability, 0.07)
    }

    func testSeparateVenueContractsUnderOneTitleStaySeparate() throws {
        let groups = QuestionCatalog9483.build(try markets(["other": [
            ["market_name": "Both teams to score", "outcome_name": "Yes", "probability": 0.525, "source": "kalshi", "_market_id": 64953335],
            ["market_name": "Both teams to score", "outcome_name": "Yes", "probability": 0.365, "source": "kalshi", "_market_id": 64953321],
            ["market_name": "Both teams to score", "outcome_name": "14+ points", "probability": 0.84, "source": "kalshi", "_market_id": 64953349],
            ["market_name": "Both teams to score", "outcome_name": "21+ points", "probability": 0.32, "source": "kalshi", "_market_id": 64953349],
        ]]), status: "scheduled", now: now)
        XCTAssertEqual(groups.map { $0.outcomes.map(\.label) }, [["Yes"], ["Yes"], ["14+ points", "21+ points"]])
        XCTAssertEqual(Set(groups.map(\.id)).count, 3, "stable, distinct ids keep expansion per contract")
    }

    func testFamiliesComeOutInPageOrder() throws {
        let groups = QuestionCatalog9483.build(try markets([
            "other": [["market_name": "Q", "outcome_name": "Yes", "probability": 0.5, "source": "kalshi"]],
            "totals": [over],
        ]), status: "scheduled", now: now)
        XCTAssertEqual(groups.map(\.family), [.gameLines, .other])
    }

    // MARK: Quotes follow the flat-list rule

    func testAnUnderBesideItsOverTwinIsDroppedAndTheOverPrintsTheOverChance() throws {
        let groups = QuestionCatalog9483.build(try markets(["totals": [over, under]]), status: "scheduled", now: now)
        XCTAssertEqual(groups.count, 1)
        XCTAssertEqual(groups[0].outcomes.map(\.label), ["Over 47.5"])
        XCTAssertEqual(groups[0].outcomes[0].probability, 0.52)
    }

    func testAnUnderWithNoTwinStaysReachableAndNeverWearsTheOverPrice() throws {
        let groups = QuestionCatalog9483.build(try markets(["totals": [under]]), status: "scheduled", now: now)
        XCTAssertEqual(groups[0].outcomes.map(\.label), ["Under 47.5"])
        XCTAssertNil(groups[0].outcomes[0].probability)
    }

    func testAnInvertedLegIsAnUnderWhateverItsLabelSays() {
        var rung = lineRow(rungs(1)[0])
        XCTAssertEqual(QuestionCatalog9483.quote(rung, status: "scheduled", now: now), 0.9)
        rung.inverted = true
        XCTAssertNil(QuestionCatalog9483.quote(rung, status: "scheduled", now: now))
    }

    func testAnOutcomeThatNamesNoSidePrintsNoOverPrice() {
        XCTAssertNil(QuestionCatalog9483.quote(
            lineRow(over.merging(["outcome_name": "Mahomes"]) { $1 }), status: "scheduled", now: now))
    }

    func testDuringPlayAnOldPricePrintsNothingAndAFreshOnePrints() {
        XCTAssertNil(QuestionCatalog9483.quote(
            lineRow(over.merging(["observed_at": old]) { $1 }), status: "live", now: now))
        XCTAssertEqual(QuestionCatalog9483.quote(
            lineRow(over.merging(["observed_at": fresh]) { $1 }), status: "live", now: now), 0.52)
        XCTAssertEqual(QuestionCatalog9483.quote(
            lineRow(over.merging(["observed_at": old]) { $1 }), status: "scheduled", now: now), 0.52,
            "pregame, the old stamp is the pregame number")
    }

    func testTheServedClockReachesTheRowsThroughDecoding() throws {
        let groups = QuestionCatalog9483.build(try markets([
            "player_props": [rungs(1)[0].merging(["observed_at": old]) { $1 }],
            "totals": [over.merging(["observed_at": old]) { $1 }],
        ]), status: "live", now: now)
        XCTAssertEqual(groups.flatMap { $0.outcomes.map(\.probability) }, [nil, nil],
                       "a stale live prop and line print nothing once observed_at is decoded")
    }

    func testAfterTheFinalNoNumberPrints() throws {
        let groups = QuestionCatalog9483.build(try markets([
            "totals": [over],
            "other": [["market_name": "Q", "outcome_name": "Yes", "probability": 1, "source": "kalshi"]],
        ]), status: "final", now: now)
        XCTAssertEqual(groups.count, 2)
        XCTAssertEqual(groups.flatMap { $0.outcomes.map(\.probability) }, [nil, nil])
        XCTAssertNil(AllMarketsCatalogView9483.priceText(groups[0].outcomes[0], status: "final"),
                     "after the final an unpriced row prints nothing, not 'No recent probability update'")
    }

    func testAClosedPeriodRowIsListedAndNeverPriced() throws {
        let groups = QuestionCatalog9483.build(try markets(["closed_period_markets": [
            ["market_name": "1st half total", "outcome_name": "Over 24.5", "threshold": 24.5,
             "probability": NSNull(), "over_probability": 0.6, "source": "kalshi",
             "market_type": "half_total", "period": "1st Half"],
        ]]), status: "live", now: now)
        XCTAssertEqual(groups.first?.family, .periods)
        XCTAssertEqual(groups.first?.period, "1st Half")
        XCTAssertNil(groups.first?.outcomes.first?.probability)
    }

    func testAnUnpricedOutcomeBeforeTheFinalSaysWhyOnlyWhenTheReasonIsKnown() {
        // #10877: an absence with no known reason is neutral; only a stale
        // observation says the update is not recent.
        let outcome = QuestionCatalog9483.Outcome(label: "Under 47.5", threshold: 47.5, probability: nil, observedAt: nil)
        XCTAssertEqual(AllMarketsCatalogView9483.priceText(outcome, status: "live"), "Probability unavailable")
        XCTAssertEqual(AllMarketsCatalogView9483.priceText(outcome, status: "scheduled"), "Probability unavailable")
        let stale = QuestionCatalog9483.Outcome(label: "Over 47.5", threshold: 47.5, probability: nil,
                                                observedAt: old, absence: .stale)
        XCTAssertEqual(AllMarketsCatalogView9483.priceText(stale, status: "live"), "No recent probability update")
        let priced = QuestionCatalog9483.Outcome(label: "Over 47.5", threshold: 47.5, probability: 0.52, observedAt: nil)
        XCTAssertEqual(AllMarketsCatalogView9483.priceText(priced, status: "live"), "52%")
    }

    func testNothingServedNothingDrawn() throws {
        XCTAssertTrue(QuestionCatalog9483.build(try markets(), status: "scheduled", now: now).isEmpty)
    }

    func testTheCatalogsOwnWordsNeverCallTheRowsQuestions() {
        let words = [AllMarketsCatalogView9483.title, AllMarketsCatalogView9483.countText(1),
                     AllMarketsCatalogView9483.countText(3), AllMarketsCatalogView9483.noRecentPrice,
                     AllMarketsCatalogView9483.periodFinished, AllMarketsCatalogView9483.unavailablePrice]
            + QuestionCatalog9483.Family.allCases.map(\.rawValue)
        for word in words { XCTAssertFalse(word.lowercased().contains("question"), word) }
    }

    // MARK: Every served outcome stays reachable (real payload)

    func testEveryOutcomeOfARealPayloadIsReachable() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/event-14780549-game-markets-9585-bears-eagles.20260928.json")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try decoder.decode(GameMarketsResponse.self, from: Data(contentsOf: url))
        let groups = QuestionCatalog9483.build(data, status: "scheduled", now: now)
        let listed = groups.reduce(0) { $0 + $1.outcomes.count }

        // The only outcomes the catalog leaves out are Under legs whose Over
        // twin it already lists, counted here independently of `build`.
        func twinDropped(_ rows: [QuestionCatalog9483.Row]) -> Int {
            func key(_ r: QuestionCatalog9483.Row) -> String {
                "\(r.source ?? "")|\(r.marketName)|\(r.period ?? "")|\(r.threshold.map { "\($0)" } ?? "")"
            }
            let overs = Set(rows.filter { QuestionCatalog9483.lineSide($0) == .over }.map(key))
            return rows.filter { QuestionCatalog9483.lineSide($0) == .under && overs.contains(key($0)) }.count
        }
        let dropped = twinDropped((data.totals ?? []).map(QuestionCatalog9483.row))
            + twinDropped((data.spreads ?? []).map(QuestionCatalog9483.row))
            + twinDropped((data.teamTotals ?? []).map(QuestionCatalog9483.row))
            + twinDropped((data.periodMarkets ?? []).map(QuestionCatalog9483.row))
            + twinDropped((data.closedPeriodMarkets ?? []).map { QuestionCatalog9483.row($0.row) })
            + twinDropped((data.playerProps ?? []).map(QuestionCatalog9483.row))

        let source = QuestionCatalog9483.sourceOutcomeCount(data)
        XCTAssertEqual(source, 1598, "control: the specimen's served rows")
        XCTAssertEqual(listed + dropped, source, "an outcome was silently lost")
        XCTAssertGreaterThan(listed, 1000)
        // Every `other` market — the family the special card gates at three
        // rows — is in the catalog by its served title.
        let titles = Set(groups.map(\.question))
        for row in data.other ?? [] {
            XCTAssertTrue(titles.contains(row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)), row.marketName)
        }
        XCTAssertEqual(Set(groups.map(\.id)).count, groups.count, "group ids are unique")
    }
}
