import XCTest
@testable import Bain_Luck

/// #10090 — a held live chart keeps the movement it already drew when a later,
/// sparse history refresh lands.
///
/// The real sequence (15325669, 20:18:32Z on the web, #10795): the page drew
/// `.565 → .525 → .51 → .565` from pushed frames past the served edge. The next
/// history response stored ONE later `.565` and nothing in between, so both
/// merge paths' strictly-newer cutoff moved past the dip and the line went flat
/// while `liveBlend` still held it. These run the chart's own pure transform on
/// the two payloads in order, the way `OddsChartViewModel` rebuilds its points.
final class AHeldChartKeepsTheDipItDrew10090Tests: XCTestCase {

    private func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func at(_ iso: String) -> Date {
        guard let date = iso.asDate else {
            XCTFail("fixture timestamp \(iso) does not parse — the test, not the product")
            return .distantPast
        }
        return date
    }

    private func series(_ source: String, _ points: [ChartDataPoint]) -> [(Date, Double)] {
        points.filter { $0.source == source }.map { ($0.date, $0.probability) }
    }

    private static let dip: [(String, Double)] = [
        ("2026-10-09T12:11:00Z", 0.565), ("2026-10-09T12:12:00Z", 0.525),
        ("2026-10-09T12:13:00Z", 0.51), ("2026-10-09T12:14:00Z", 0.565),
    ]

    /// The blend frames. `p` is the blend; on the single-source page the venue
    /// reading is a different number, so a test can tell which one was drawn.
    private func frames(venue: String? = nil) -> [LiveBlendPoint] {
        Self.dip.map { stamp, value in
            LiveBlendPoint(date: at(stamp), homeProbability: venue == nil ? value : 0.70,
                           source: venue, sourceProbability: venue == nil ? nil : value)
        }
    }

    private func blended(status: String = "live", extra: String = "") throws -> EventHistoryResponse {
        try decode("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A", "status": "\(status)",
          "history": [],
          "win_prob_history": {"kalshi": [{"timestamp": "2026-10-09T12:10:00Z", "home_probability": 0.56}]},
          "aggregate_line": [
            {"timestamp": "2026-10-09T12:00:00Z", "home_probability": 0.50},
            {"timestamp": "2026-10-09T12:10:00Z", "home_probability": 0.565}\(extra)
          ]
        }
        """)
    }

    private func polymarketOnly(_ rows: String) throws -> EventHistoryResponse {
        try decode("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A", "status": "live",
          "history": [],
          "win_prob_history": {"polymarket": [\(rows)]}
        }
        """)
    }

    private static let sparseLater = #", {"timestamp": "2026-10-09T12:15:00Z", "home_probability": 0.565}"#

    private func assertKeepsTheDip(_ drawn: [(Date, Double)], served: Int,
                                   file: StaticString = #filePath, line ln: UInt = #line) {
        XCTAssertEqual(drawn.count, served + 4, "every served point plus the four held readings", file: file, line: ln)
        XCTAssertEqual(drawn.map(\.0), drawn.map(\.0).sorted(), "time order", file: file, line: ln)
        XCTAssertEqual(Set(drawn.map(\.0)).count, drawn.count, "one point per instant", file: file, line: ln)
        let byTime = Dictionary(drawn.map { ($0.0, $0.1) }, uniquingKeysWith: { first, _ in first })
        XCTAssertEqual(byTime[at("2026-10-09T12:12:00Z")] ?? .nan, 0.525, accuracy: 1e-9, file: file, line: ln)
        XCTAssertEqual(byTime[at("2026-10-09T12:13:00Z")] ?? .nan, 0.51, accuracy: 1e-9, file: file, line: ln)
    }

    // MARK: - The ship

    func testABlendedChartKeepsTheDipWhenASparseRefreshMovesTheEdgePastIt() throws {
        let before = series("aggregate", OddsChartView.chartPoints(from: try blended(), liveFrames: frames()))
        assertKeepsTheDip(before, served: 2)  // premise: drawn as the live tail

        let after = series("aggregate", OddsChartView.chartPoints(
            from: try blended(extra: Self.sparseLater), liveFrames: frames()))
        assertKeepsTheDip(after, served: 3)
        XCTAssertEqual(after.last?.0, at("2026-10-09T12:15:00Z"), "the served row still ends the line")
    }

    func testASingleSourceChartKeepsTheVenueDipWhenASparseRefreshMovesTheEdgePastIt() throws {
        let rows = #"""
        {"timestamp": "2026-10-09T12:00:00Z", "home_probability": 0.50},
        {"timestamp": "2026-10-09T12:10:00Z", "home_probability": 0.565}
        """#
        let before = OddsChartView.chartPoints(from: try polymarketOnly(rows), liveFrames: frames(venue: "polymarket"))
        assertKeepsTheDip(series("polymarket", before), served: 2)

        let after = OddsChartView.chartPoints(from: try polymarketOnly(rows + Self.sparseLater),
                                              liveFrames: frames(venue: "polymarket"))
        assertKeepsTheDip(series("polymarket", after), served: 3)
        XCTAssertFalse(series("polymarket", after).contains { $0.1 == 0.70 }, "the venue's value, never the blend p")
        XCTAssertTrue(series("aggregate", after).isEmpty, "no minted blend")
    }

    // MARK: - Controls

    /// A served point at the frame's exact instant wins, and an interval whose
    /// held readings all re-confirm its opening value draws nothing.
    func testAServedPointAtTheSameInstantWinsAndAQuietRunAddsNothing() throws {
        let stored = #", {"timestamp": "2026-10-09T12:12:00Z", "home_probability": 0.53}"# + Self.sparseLater
        let line = series("aggregate", OddsChartView.chartPoints(from: try blended(extra: stored), liveFrames: frames()))

        XCTAssertEqual(line.map(\.0), [
            "2026-10-09T12:00:00Z", "2026-10-09T12:10:00Z", "2026-10-09T12:12:00Z",
            "2026-10-09T12:13:00Z", "2026-10-09T12:14:00Z", "2026-10-09T12:15:00Z",
        ].map(at), "12:11 only re-confirms .565 and 12:12 is the served row's instant")
        XCTAssertEqual(line[2].1, 0.53, accuracy: 1e-9, "the served value, not the frame's .525")
    }

    /// An `observed` point's `covered_through` is the backend's proof the value
    /// held; a held reading inside it is not drawn.
    func testAReadingInsideObservedCoverageIsNotDrawn() throws {
        let rows = #"""
        {"timestamp": "2026-10-09T12:00:00Z", "home_probability": 0.50},
        {"timestamp": "2026-10-09T12:10:00Z", "home_probability": 0.565,
         "evidence": {"kind": "observed", "covered_through": "2026-10-09T12:12:30Z"}}
        """#
        let line = series("polymarket", OddsChartView.chartPoints(
            from: try polymarketOnly(rows + Self.sparseLater), liveFrames: frames(venue: "polymarket")))

        XCTAssertEqual(line.map(\.0), [
            "2026-10-09T12:00:00Z", "2026-10-09T12:10:00Z",
            "2026-10-09T12:13:00Z", "2026-10-09T12:14:00Z", "2026-10-09T12:15:00Z",
        ].map(at))
    }

    /// Settled means settled: a finished payload is exactly as served.
    func testAFinishedPayloadKeepsNoHeldReading() throws {
        let line = series("aggregate", OddsChartView.chartPoints(
            from: try blended(status: "completed", extra: Self.sparseLater), liveFrames: frames()))
        XCTAssertEqual(line.count, 3)
    }
}
