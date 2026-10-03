import XCTest
@testable import Bain_Luck

/// #10244 — the iPhone verified title chart draws the market's own `/history`
/// (the de-vigged consensus), never the timeline's median of raw sportsbook
/// prices. On /futures/86832 the timeline ended the Bills at 13.3% under
/// "Sportsbooks history" while the sportsbooks' own number was 11.2%.
///
/// `historyBills` is a REAL-ROUTE response: production
/// `/api/futures/86832/history?hours=168&top_n=50` read 2026-10-03 04:2xZ,
/// trimmed to four outcomes and the last three instants (coverage keys
/// recomputed for the trim). The timeline is #9387's retained fixture.
@MainActor
final class VerifiedTitleHistory10244Tests: XCTestCase {
    private typealias F = VerifiedTitle9387Fixtures
    private typealias T = VerifiedTitleConsumer9387Tests

    static func history(_ json: String) throws -> FuturesHistoryResponse {
        try T.decoder().decode(FuturesHistoryResponse.self, from: Data(json.utf8))
    }

    private func drawn(_ historyJSON: String = historyBills) throws -> ProbabilityTimelineResponse {
        VerifiedTitleHistory.drawing(try Self.history(historyJSON), over: try T.timeline(F.timelineVerified))
    }

    private func line(_ response: ProbabilityTimelineResponse, _ name: String) -> [Double] {
        response.timeline.compactMap { $0.outcomes[name] }
    }

    // MARK: - Decoding

    func testTheHistoryRouteDecodes() throws {
        let history = try Self.history(Self.historyBills)
        XCTAssertEqual(history.marketId, 86832)
        XCTAssertEqual(history.outcomes.count, 4)
        let bills = try XCTUnwrap(history.outcomes.first { $0.outcomeId == 1_309_486 })
        XCTAssertEqual(bills.name, "Buffalo Bills")
        XCTAssertEqual(bills.history.count, 3)
        XCTAssertEqual(history.coverageHours, 8.0)
        XCTAssertEqual(history.observationTimes, 3)
    }

    // MARK: - The lines are the consensus

    func testTheBillsLineEndsAtTheSportsbooksDeviggedNumberNotTheRawMedian() throws {
        let timeline = try T.timeline(F.timelineVerified)
        let response = try drawn()
        XCTAssertEqual(line(response, "Buffalo Bills").last, 0.11249782733433002)
        XCTAssertNotEqual(line(response, "Buffalo Bills").last, line(timeline, "Buffalo Bills").last,
                          "the raw-median line must not survive")
        XCTAssertEqual(response.timeline.map(\.timestamp), [
            "2026-10-02T16:30:03.937957+00:00",
            "2026-10-02T20:30:26.797101+00:00",
            "2026-10-03T00:30:03.413310+00:00",
        ], "every drawn instant is one /history served — none of the timeline's buckets")
    }

    func testARowHistoryHasNoLineForDrawsNoneRatherThanTheRawMedian() throws {
        let response = try drawn()
        XCTAssertEqual(line(response, "New York Jets"), [])
        XCTAssertEqual(line(response, "Kansas City Chiefs"), [])
    }

    func testCoverageDescribesThePointsDrawn() throws {
        let response = try drawn()
        XCTAssertEqual(response.coverageHours, 8.0)
        XCTAssertEqual(response.observationTimes, 3)
    }

    // MARK: - Everything else stays the timeline's

    func testTheCurrentColumnRowsAndBasisStayTheTimelines() throws {
        let timeline = try T.timeline(F.timelineVerified)
        let response = try drawn()
        XCTAssertEqual(response.outcomes.map(\.name), timeline.outcomes.map(\.name))
        XCTAssertEqual(response.outcomes.map(\.currentProbability), timeline.outcomes.map(\.currentProbability))
        XCTAssertEqual(response.effectiveRepresentation, .verifiedTitle)
        XCTAssertEqual(VerifiedTitlePresentation.historyLabel(response.historyBasis), "Sportsbooks history")
    }

    // MARK: - Joining lines to rows

    func testALineJoinsItsRowByOutcomeIdNotByName() throws {
        let renamed = try T.edited(Self.historyBills) { object in
            T.editOutcome(&object, "Buffalo Bills") { $0["name"] = "Bills" }
        }
        let response = try drawn(renamed)
        XCTAssertEqual(line(response, "Buffalo Bills").count, 3)
        XCTAssertEqual(line(response, "Bills"), [])
    }

    func testALineWithNoRowKeepsItsOwnName() throws {
        // Baltimore is in /history's top 50 but not the fixture timeline's rows.
        XCTAssertEqual(line(try drawn(), "Baltimore Ravens").last, 0.07907186451112222)
    }

    func testInstantsAreChronologicalWhateverOrderTheyArrive() throws {
        let reversed = try T.edited(Self.historyBills) { object in
            var outcomes = object["outcomes"] as? [[String: Any]] ?? []
            for index in outcomes.indices {
                outcomes[index]["history"] = Array(((outcomes[index]["history"] as? [Any]) ?? []).reversed())
            }
            object["outcomes"] = Array(outcomes.reversed())
        }
        let stamps = try drawn(reversed).timeline.compactMap(\.timestamp.asDate)
        XCTAssertEqual(stamps.count, 3)
        XCTAssertEqual(stamps, stamps.sorted())
    }

    func testANullPointOrAnUnreadableStampDrawsNothing() throws {
        let holed = try T.edited(Self.historyBills) { object in
            T.editOutcome(&object, "Buffalo Bills") { outcome in
                var points = outcome["history"] as? [[String: Any]] ?? []
                points[0]["probability"] = NSNull()
                points[1]["timestamp"] = "not a time"
                outcome["history"] = points
            }
        }
        XCTAssertEqual(line(try drawn(holed), "Buffalo Bills"), [0.11249782733433002])
    }

    // MARK: - Which charts

    /// The page asks for verified on EVERY futures market, so only an answer can
    /// move a chart: an ineligible board (golf, a Kalshi ladder) answers source in
    /// both requests and keeps the chart it had.
    func testOnlyAVerifiedAnswerDrawsHistory() throws {
        XCTAssertTrue(VerifiedTitleHistory.drawsSourceHistory(detail: .verifiedTitle, response: nil))
        XCTAssertTrue(VerifiedTitleHistory.drawsSourceHistory(detail: .source, response: .verifiedTitle))
        XCTAssertTrue(VerifiedTitleHistory.drawsSourceHistory(detail: nil, response: .verifiedTitle))
        XCTAssertFalse(VerifiedTitleHistory.drawsSourceHistory(detail: .source, response: .source))
        XCTAssertFalse(VerifiedTitleHistory.drawsSourceHistory(detail: nil, response: nil))
        // Real answers: #9387's fallback pair is a refused Kalshi board.
        let refusedDetail = try T.detail(F.detailFallback).effectiveRepresentation
        let refusedTimeline = try T.timeline(F.timelineFallback).effectiveRepresentation
        XCTAssertFalse(VerifiedTitleHistory.drawsSourceHistory(detail: refusedDetail, response: refusedTimeline))
        let verifiedDetail = try T.detail(F.detailVerified).effectiveRepresentation
        XCTAssertTrue(VerifiedTitleHistory.drawsSourceHistory(detail: verifiedDetail, response: nil))
    }

    /// The chart is a SwiftUI view this suite cannot load, so its use of the
    /// helper is read off the source (comments stripped).
    func testTheChartAsksHistoryAndDrawsItsLines() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("EvolutionChartView.swift")
        let code = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line in line.range(of: "//").map { String(line[..<$0.lowerBound]) } ?? String(line) }
            .joined(separator: "\n")
        XCTAssertTrue(code.contains("detail: expectation?.representation, response: nil"))
        XCTAssertTrue(code.contains("detail: expectation?.representation, response: result.effectiveRepresentation"))
        XCTAssertTrue(code.contains("APIClient.shared.fetchFuturesHistory(marketId: marketId, hours: hours)"))
        XCTAssertFalse(code.contains("drawsSourceHistory(detail: representation"),
                       "the REQUEST is verified on every futures page — it must not decide")
        XCTAssertTrue(code.contains("data = lines.map { VerifiedTitleHistory.drawing($0, over: result) } ?? result"))
    }

    // MARK: - Fixture

    static let historyBills = #"""
{"market_id":86832,"market_name":"NFL Super Bowl Winner","hours":168,"actual_hours":168,"outcomes":[{"outcome_id":1309486,"name":"Buffalo Bills","history":[{"timestamp":"2026-10-02T16:30:03.937957+00:00","probability":0.11249782733433002,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-02T20:30:26.797101+00:00","probability":0.11249782733433002,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-03T00:30:03.413310+00:00","probability":0.11249782733433002,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null},{"outcome_id":1309487,"name":"Baltimore Ravens","history":[{"timestamp":"2026-10-02T16:30:03.937957+00:00","probability":0.07907186451112222,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-02T20:30:26.797101+00:00","probability":0.07907186451112222,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-03T00:30:03.413310+00:00","probability":0.07907186451112222,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null},{"outcome_id":1309494,"name":"San Francisco 49ers","history":[{"timestamp":"2026-10-02T16:30:03.937957+00:00","probability":0.08210411827065948,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-02T20:30:26.797101+00:00","probability":0.08210411827065948,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-03T00:30:03.413310+00:00","probability":0.08210411827065948,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null},{"outcome_id":1309485,"name":"Los Angeles Rams","history":[{"timestamp":"2026-10-02T16:30:03.937957+00:00","probability":0.10981697095527783,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-02T20:30:26.797101+00:00","probability":0.10981697095527783,"american_odds":null,"bookmaker":"consensus"},{"timestamp":"2026-10-03T00:30:03.413310+00:00","probability":0.10981697095527783,"american_odds":null,"bookmaker":"consensus"}],"eliminated":false,"eliminated_at":null}],"round_boundaries":[],"leaderboard":null,"total_data_points":12,"coverage_start":"2026-10-02T16:30:03.937957+00:00","coverage_end":"2026-10-03T00:30:03.413310+00:00","coverage_hours":8.0,"observation_times":3}
"""#
}
