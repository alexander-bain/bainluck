import XCTest
@testable import Bain_Luck

/// #10877 — the All markets catalog keeps WHY an outcome has no number. A
/// closed period inside a live game, a stale open period, a missing or
/// non-finite probability and the authoritative final are four different
/// things; each keeps the number and its time withheld, and none borrows
/// another's explanation.
final class CatalogAvailabilityReasons10877Tests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-10-11T18:00:00Z")!
    private let fresh = "2026-10-11T17:58:00Z"
    private let old = "2026-10-11T16:00:00Z"

    private func markets(_ over: [String: Any]) throws -> GameMarketsResponse {
        var dict: [String: Any] = [
            "event_id": 1, "home_team": "Kansas City Chiefs", "away_team": "Buffalo Bills",
            "status": "live", "totals": [], "player_props": [], "team_totals": [], "spreads": [],
            "period_markets": [], "matchups": [], "other": [],
        ]
        dict.merge(over) { $1 }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    /// A served 1st-quarter total, per the #10850 contract when closed.
    private func closedQ1(windowClosed: Any = true, observedAt: String? = nil) -> [String: Any] {
        var row: [String: Any] = [
            "market_name": "1st quarter total", "outcome_name": "Over 10.5", "threshold": 10.5,
            "probability": NSNull(), "source": "kalshi", "market_type": "quarter_total",
            "period": "1st Quarter", "window_closed": windowClosed, "period_score": ["home": 7, "away": 3],
        ]
        if let observedAt { row["observed_at"] = observedAt }
        return row
    }

    private func openQ2(observedAt: String) -> [String: Any] {
        ["market_name": "2nd quarter total", "outcome_name": "Over 9.5", "threshold": 9.5,
         "over_probability": 0.44, "source": "kalshi", "market_type": "quarter_total",
         "period": "2nd Quarter", "observed_at": observedAt]
    }

    private func group(_ groups: [QuestionCatalog9483.Group], _ question: String) throws -> QuestionCatalog9483.Group {
        try XCTUnwrap(groups.first { $0.question == question }, question)
    }

    private func text(_ outcome: QuestionCatalog9483.Outcome, _ status: String) -> String? {
        AllMarketsCatalogView9483.priceText(outcome, status: status)
    }

    // MARK: Closed period inside a live game

    func testAClosedPeriodInsideALiveGameSaysPeriodFinishedAndWithholdsItsNumberAndTime() throws {
        let data = try markets([
            "closed_period_markets": [closedQ1(observedAt: fresh)],
            "period_markets": [openQ2(observedAt: fresh)],
        ])
        let groups = QuestionCatalog9483.build(data, status: "live", now: now)
        let q1 = try group(groups, "1st quarter total")
        let outcome = try XCTUnwrap(q1.outcomes.first)
        XCTAssertNil(outcome.probability, "a closed window never prints a number, even with a fresh stamp")
        XCTAssertEqual(outcome.absence, .periodFinished)
        XCTAssertEqual(text(outcome, "live"), "Period finished")
        XCTAssertNil(AllMarketsCatalogView9483.seenStamp(q1), "its time is not offered as a current price time")
        // The row and its Details stay reachable.
        XCTAssertEqual(q1.family, .periods)
        XCTAssertEqual(q1.period, "1st Quarter")
        XCTAssertEqual(AllMarketsCatalogView9483.lines(q1), ["10.5"])
        XCTAssertEqual(groups.reduce(0) { $0 + $1.outcomes.count }, QuestionCatalog9483.sourceOutcomeCount(data))

        // Control: the open period beside it, same clock, still prints.
        let q2 = try group(groups, "2nd quarter total")
        XCTAssertEqual(q2.outcomes.first?.probability, 0.44)
        XCTAssertNil(q2.outcomes.first?.absence)
        XCTAssertEqual(text(try XCTUnwrap(q2.outcomes.first), "live"), "44%")
    }

    func testAClosedListRowCarryingAPriceOrAnyStampStillPrintsNone() throws {
        for stamp in [fresh, old] {
            var row = closedQ1(observedAt: stamp)
            row["over_probability"] = 0.6
            row["probability"] = 0.6
            let outcome = try XCTUnwrap(QuestionCatalog9483.build(
                try markets(["closed_period_markets": [row]]), status: "live", now: now).first?.outcomes.first)
            XCTAssertNil(outcome.probability, stamp)
            XCTAssertEqual(outcome.absence, .periodFinished, "closure, not age, is the known reason: \(stamp)")
            XCTAssertEqual(text(outcome, "live"), "Period finished", stamp)
        }
    }

    func testOnlyAnExplicitWindowClosedMakesAFinishedPeriod() throws {
        // Withheld either way (the closed list never prices), but without the
        // server's own `window_closed: true` the reason is not claimed.
        // (A non-Bool value is a decode refusal of the whole list, #10850.)
        for flag in [false, NSNull()] as [Any] {
            let outcome = try XCTUnwrap(QuestionCatalog9483.build(
                try markets(["closed_period_markets": [closedQ1(windowClosed: flag)]]),
                status: "live", now: now).first?.outcomes.first, "\(flag)")
            XCTAssertNil(outcome.probability, "\(flag)")
            XCTAssertEqual(outcome.absence, .unavailable, "\(flag)")
            XCTAssertEqual(text(outcome, "live"), "Probability unavailable", "\(flag)")
        }
    }

    // MARK: Stale open period

    func testAStaleOpenPeriodSaysNoRecentUpdateAndNeverPeriodFinished() throws {
        let groups = QuestionCatalog9483.build(
            try markets(["period_markets": [openQ2(observedAt: old)]]), status: "live", now: now)
        let q2 = try group(groups, "2nd quarter total")
        let outcome = try XCTUnwrap(q2.outcomes.first)
        XCTAssertNil(outcome.probability, "the old 44% is not shown as current")
        XCTAssertEqual(outcome.absence, .stale)
        XCTAssertEqual(text(outcome, "live"), "No recent probability update")
        XCTAssertNil(AllMarketsCatalogView9483.seenStamp(q2), "a withheld price offers no seen time")

        // Control: pregame, the same stamp is the pregame number.
        let pregame = QuestionCatalog9483.build(
            try markets(["period_markets": [openQ2(observedAt: old)]]), status: "scheduled", now: now)
        XCTAssertEqual(pregame.first?.outcomes.first?.probability, 0.44)
    }

    // MARK: Missing or non-finite probability

    func testAMissingProbabilityDuringPlayIsNeutralNotStaleOrFinished() throws {
        let groups = QuestionCatalog9483.build(try markets(["other": [
            ["market_name": "Will there be a safety?", "outcome_name": "Yes", "probability": NSNull(),
             "source": "kalshi", "observed_at": fresh],
        ]]), status: "live", now: now)
        let outcome = try XCTUnwrap(groups.first?.outcomes.first)
        XCTAssertNil(outcome.probability)
        XCTAssertEqual(outcome.absence, .unavailable)
        XCTAssertEqual(text(outcome, "live"), "Probability unavailable")
    }

    func testANonFiniteProbabilityIsNeutralAndPrintsNoNumber() {
        for bad in [Double.nan, .infinity, -.infinity] {
            let direct = QuestionCatalog9483.Row(
                marketName: "Will there be a safety?", outcomeName: "Yes", probability: bad,
                pricesOutcome: true, source: "kalshi", observedAt: fresh)
            let over = QuestionCatalog9483.Row(
                marketName: "Total points", outcomeName: "Over 47.5", threshold: 47.5,
                pricesOutcome: false, overProbability: bad, source: "kalshi", observedAt: fresh)
            for row in [direct, over] {
                let reading = QuestionCatalog9483.reading(row, status: "live", now: now)
                XCTAssertNil(reading.probability, "\(bad)")
                XCTAssertEqual(reading.absence, .unavailable, "\(bad)")
            }
        }
    }

    // MARK: Authoritative final

    func testAfterTheFinalEveryAbsencePrintsNothingAndNoneClaimsAPeriodOrStaleness() throws {
        let data = try markets([
            "closed_period_markets": [closedQ1()],
            "period_markets": [openQ2(observedAt: old)],
            "other": [["market_name": "Q", "outcome_name": "Yes", "probability": 1, "source": "kalshi"]],
        ])
        let groups = QuestionCatalog9483.build(data, status: "final", now: now)
        let outcomes = groups.flatMap(\.outcomes)
        XCTAssertEqual(outcomes.count, 3, "every row stays listed")
        for outcome in outcomes {
            XCTAssertNil(outcome.probability, outcome.label)
            XCTAssertEqual(outcome.absence, .settled, outcome.label)
            XCTAssertNil(text(outcome, "final"), "the graded cards own results: \(outcome.label)")
        }
        // A reason carried from before the final still yields to it.
        let carried = QuestionCatalog9483.Outcome(label: "Over 10.5", threshold: 10.5, probability: nil,
                                                  observedAt: nil, absence: .periodFinished)
        XCTAssertNil(text(carried, "final"))
    }

    // MARK: The meanings stay distinct

    func testTheFourMeaningsReadDifferentlyAndNoneNamesAResult() {
        func outcome(_ absence: QuestionCatalog9483.Absence) -> QuestionCatalog9483.Outcome {
            .init(label: "Over 10.5", threshold: 10.5, probability: nil, observedAt: nil, absence: absence)
        }
        let words = [QuestionCatalog9483.Absence.periodFinished, .stale, .unavailable].map { text(outcome($0), "live") }
        XCTAssertEqual(Set(words.compactMap { $0 }).count, 3, "\(words)")
        XCTAssertNil(text(outcome(.settled), "live"))
        for word in words.compactMap({ $0 }) {
            for claim in ["won", "lost", "settled", "result", "final", "%"] {
                XCTAssertFalse(word.lowercased().contains(claim), "\(word) claims \(claim)")
            }
        }
        // A printed number always wins over any carried reason.
        let priced = QuestionCatalog9483.Outcome(label: "Over 9.5", threshold: 9.5, probability: 0.44,
                                                 observedAt: fresh, absence: .stale)
        XCTAssertNil(priced.absence)
        XCTAssertEqual(text(priced, "live"), "44%")
    }
}
