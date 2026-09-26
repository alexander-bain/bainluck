import XCTest
@testable import Bain_Luck

/// #8651 — **a scrub on a game chart rebuilds neither the chart's points nor
/// the event page.**
///
/// Measured on the recorded specimen (14781697, 7,602 history rows) with the
/// app logging its actual UIKit gesture callbacks on a simulator: the callbacks
/// were clean (began / changed / ended — no cancelled, no failed), and the page
/// still froze for 4–5 s per horizontal scrub. Each scrub step set the
/// selection; that ran the chart's body, whose `onChange` wrote the readout
/// point into EVENT PAGE state, which rebuilt the page and ran the chart's body
/// again; and every run built the chart's points twice (`noReadings` and the
/// plot) at ~600 ms apiece. Points memoized: ~2.2 s. Readout point kept in the
/// chart as well: ~0.7 s per step and zero page rebuilds.
///
/// The interactive half is `AnOrdinaryScrollDoesNotRebuildTheGamePage8651Tests`
/// (UI target) — `testAHorizontalScrubDoesNotRebuildThePage` counts page
/// rebuilds under a real finger. This is the fast half.
final class AScrubDoesNotRebuildTheChartOrThePage8651Tests: XCTestCase {

    private func history(_ probability: Double) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.35},
            {"timestamp": "2026-07-27T12:30:00Z", "home_probability": \(probability)}
          ]
        }
        """.utf8))
    }

    private let frame = LiveBlendPoint(date: Date(timeIntervalSince1970: 1_785_155_000), homeProbability: 0.6)

    // MARK: - The memo

    /// A second ask with nothing changed returns the SAME points — same ids,
    /// which a rebuild cannot produce (`ChartDataPoint.id` is a fresh `UUID`).
    func testASecondAskWithNothingChangedReturnsTheSamePoints() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try history(0.82))
        let first = vm.chartPoints(liveFrames: [frame])
        let second = vm.chartPoints(liveFrames: [frame])
        XCTAssertFalse(first.isEmpty, "the fixture drew no points — the id comparison below would be vacuous")
        XCTAssertEqual(first.map(\.id), second.map(\.id),
                       "the points were rebuilt with nothing changed — a scrub pays for this on every step")
    }

    /// The control, direction one: a new payload is new points, never the old
    /// ones served from the memo.
    func testANewPayloadIsNewPoints() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try history(0.82))
        let before = vm.chartPoints(liveFrames: [])
        vm.history = try history(0.11)
        let after = vm.chartPoints(liveFrames: [])
        XCTAssertNotEqual(before.map(\.id), after.map(\.id), "a new payload was answered from the memo")
        XCTAssertEqual(after.map(\.probability).max(), 0.35)
        XCTAssertTrue(after.contains { $0.probability == 0.11 }, "the new payload's reading is not on the chart")
    }

    /// The control, direction two: a newly pushed live frame is new points.
    func testANewLiveFrameIsNewPoints() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try history(0.82))
        let before = vm.chartPoints(liveFrames: [])
        let after = vm.chartPoints(liveFrames: [frame])
        XCTAssertNotEqual(before.map(\.id), after.map(\.id), "a pushed live frame was answered from the memo")
        XCTAssertEqual(after.map(\.id), vm.chartPoints(liveFrames: [frame]).map(\.id))
    }

    /// No payload, no points — and no stale ones from before it went away.
    func testNoPayloadIsNoPoints() throws {
        let vm = OddsChartViewModel(eventId: 1, preloaded: try history(0.82))
        XCTAssertFalse(vm.chartPoints(liveFrames: []).isEmpty)
        vm.history = nil
        XCTAssertTrue(vm.chartPoints(liveFrames: []).isEmpty)
    }

    // MARK: - The wiring (comment-stripped scans: the bodies are not rendered in tests)

    private func code(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// Every body-time point build goes through the memo.
    func testTheChartBuildsItsPointsOnlyThroughTheMemo() throws {
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("vm.chartPoints(liveFrames:liveFrames)"),
                      "the chart no longer asks its view model for points")
        let direct = chart.components(separatedBy: "OddsChartView.chartPoints(from:history,liveFrames:liveFrames)").count - 1
            + chart.components(separatedBy: "Self.chartPoints(from:").count - 1
        XCTAssertEqual(direct, 1, "the transform is called \(direct) times; only the memo may call it")
    }

    /// The scrubbed moment is the chart's state; the page never holds it.
    func testTheScrubbedMomentIsTheChartsStateNotThePages() throws {
        let page = try code("Bain Luck/Views/EventDetailView.swift")
        XCTAssertFalse(page.contains("selectedPlayPoint"),
                       "the page holds the scrubbed moment again — every scrub step will rebuild the page")
        XCTAssertFalse(page.contains("selectedPoint:"), "the page hands the readout a scrubbed moment again")

        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("@StateprivatevarselectedPlayPoint:GamePlayPoint?"),
                      "the chart no longer owns the scrubbed moment")
        XCTAssertFalse(chart.contains("@BindingvarselectedPlayPoint"), "the scrubbed moment is bound to a parent again")
        XCTAssertEqual(chart.components(separatedBy: "ifletreadout{readout.showing(selectedPlayPoint)}").count - 1, 2,
                       "both places the chart draws the readout (inline + fullscreen) must hand it the scrub")
    }

    /// `showing(_:)` replaces the scrubbed moment and nothing else.
    func testShowingSetsOnlyTheScrubbedMoment() {
        let resting = GamePlayPoint(timestamp: "2026-07-27T12:30:00Z", homeProb: 0.82, awayProb: 0.18)
        let scrubbed = GamePlayPoint(timestamp: "2026-07-27T12:00:00Z", homeProb: 0.35, awayProb: 0.65)
        let card = GamePlayCardView(homeTeam: "H", awayTeam: "A", lastPoint: resting)
        XCTAssertNil(card.selectedPoint)
        let shown = card.showing(scrubbed)
        XCTAssertEqual(shown.selectedPoint?.timestamp, scrubbed.timestamp)
        XCTAssertEqual(shown.lastPoint?.timestamp, resting.timestamp)
        XCTAssertEqual(shown.homeTeam, "H")
        XCTAssertNil(card.showing(nil).selectedPoint)
    }
}
