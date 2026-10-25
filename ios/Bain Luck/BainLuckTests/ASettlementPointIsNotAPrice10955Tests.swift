import XCTest
@testable import Bain_Luck

/// #10955 G2 — a settled line's last price is not joined to its result.
///
/// `/api/futures/{id}/history` appends one `bookmaker: "settlement"` point to a
/// settled line (`routes/futures.py`, the freeze arms): 1.0 on the winner, 0.0 on
/// an evidenced loss, at the market's `resolution_date` — when it was DUE to
/// close, a schedule, not an observed finish (Alex 9/14). An hour after the last
/// price, inside the line's own gap threshold (six medians = 6 h here), the chart
/// drew it into the solid run: a stroke from 11.3% to 0% at a time nobody saw a
/// trade, which #11184 says a solid line may never do.
///
/// Uses only what the chart already consumed before #10955, so this file runs
/// red on that code for the reason it names.
@MainActor
final class ASettlementPointIsNotAPrice10955Tests: XCTestCase {
    private typealias F = VerifiedTitle9387Fixtures
    private typealias T = VerifiedTitleConsumer9387Tests

    static let bills = (id: 1_309_486, name: "Buffalo Bills")
    static let rams = (id: 1_309_485, name: "Los Angeles Rams")
    static let lastPrice = ISO8601DateFormatter().date(from: "2026-10-02T18:00:00Z")!

    static func stamp(_ date: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss'+00:00'"
        return f.string(from: date)
    }

    /// Eight hourly prices ending at `lastPrice`, as `/history` serves a price.
    static func hourly(_ start: Double, step: Double) -> [[String: Any]] {
        (0..<8).map { i in
            ["timestamp": stamp(lastPrice.addingTimeInterval(Double(i - 7) * 3600)),
             "probability": start + Double(i) * step,
             "american_odds": NSNull(), "bookmaker": "consensus"]
        }
    }

    static func settlement(_ probability: Double, at date: Date, basis: String?) -> [String: Any] {
        var point: [String: Any] = ["timestamp": stamp(date), "probability": probability,
                                    "american_odds": NSNull(), "bookmaker": "settlement"]
        if let basis { point["settlement_basis"] = basis }
        return point
    }

    /// A `/history` body; the coverage keys are the server's (settlement included).
    static func history(_ lines: [(id: Int, name: String, points: [[String: Any]])],
                        coverageHours: Double, observationTimes: Int) throws -> FuturesHistoryResponse {
        let body: [String: Any] = [
            "market_id": 86832, "market_name": "NFL Super Bowl Winner",
            "outcomes": lines.map { ["outcome_id": $0.id, "name": $0.name, "history": $0.points,
                                     "eliminated": false, "eliminated_at": NSNull()] },
            "coverage_hours": coverageHours, "observation_times": observationTimes,
        ]
        return try T.decoder().decode(
            FuturesHistoryResponse.self, from: JSONSerialization.data(withJSONObject: body))
    }

    static func timeline() throws -> ProbabilityTimelineResponse {
        try T.timeline(F.timelineVerified)
    }

    /// The leg as the chart's timeline holds it: (instant, value) in order.
    static func leg(_ name: String, _ response: ProbabilityTimelineResponse) -> [(Date, Double)] {
        response.timeline.compactMap { entry in
            entry.outcomes[name].flatMap { value in entry.timestamp.asDate.map { ($0, value) } }
        }
    }

    // MARK: - G2

    func testAScheduledCloseAnHourAfterTheLastPriceDrawsNoSolidSegment() throws {
        let close = Self.lastPrice.addingTimeInterval(3600)
        let history = try Self.history([
            (Self.bills.id, Self.bills.name,
             Self.hourly(0.10, step: 0.002) + [Self.settlement(0.0, at: close, basis: "resolution_date")]),
            (Self.rams.id, Self.rams.name, Self.hourly(0.09, step: 0.001)),
        ], coverageHours: 8.0, observationTimes: 9)

        let drawn = VerifiedTitleHistory.drawing(history, over: try Self.timeline())
        let bills = Self.leg(Self.bills.name, drawn)
        let instants = bills.map(\.0)

        // The step to the settlement is inside this leg's threshold — the case
        // where it would have joined the solid run rather than a dotted bridge.
        XCTAssertEqual(EvolutionSeriesGaps.threshold(Array(instants.prefix(8))), 6 * 3600)

        XCTAssertFalse(drawn.timeline.contains { $0.timestamp == Self.stamp(close) },
                       "the scheduled close must not become an instant on the chart")
        XCTAssertEqual(bills.count, 8, "only the eight prices are a line")
        XCTAssertEqual(instants.last, Self.lastPrice, "the line ends at its own last price")
        XCTAssertFalse(bills.contains { $0.1 == 0 }, "no 0% is drawn as if it traded")
        XCTAssertEqual(Set(EvolutionSeriesGaps.runs(instants)), [0])
    }

    // MARK: - G5 control

    /// A line with no settlement point is drawn exactly as served, and the
    /// server's coverage keys pass through untouched.
    func testAHealthyHistoryIsDrawnExactlyAsServed() throws {
        let history = try Self.history([
            (Self.bills.id, Self.bills.name, Self.hourly(0.10, step: 0.002)),
            (Self.rams.id, Self.rams.name, Self.hourly(0.09, step: 0.001)),
        ], coverageHours: 7.0, observationTimes: 8)

        let drawn = VerifiedTitleHistory.drawing(history, over: try Self.timeline())
        let expected = (0..<8).map { Self.lastPrice.addingTimeInterval(Double($0 - 7) * 3600) }
        XCTAssertEqual(Self.leg(Self.bills.name, drawn).map(\.0), expected)
        XCTAssertEqual(Self.leg(Self.bills.name, drawn).map(\.1),
                       (0..<8).map { 0.10 + Double($0) * 0.002 })
        XCTAssertEqual(Self.leg(Self.rams.name, drawn).map(\.1),
                       (0..<8).map { 0.09 + Double($0) * 0.001 })
        XCTAssertEqual(drawn.timeline.map(\.timestamp), expected.map(Self.stamp))
        XCTAssertEqual(drawn.coverageHours, 7.0)
        XCTAssertEqual(drawn.observationTimes, 8)
    }
}
