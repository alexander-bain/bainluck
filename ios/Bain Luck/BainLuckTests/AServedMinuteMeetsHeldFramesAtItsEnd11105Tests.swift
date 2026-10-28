import XCTest
@testable import Bain_Luck

/// #10090 / #11105 — a held live chart stops drawing out-and-back spikes that
/// never happened.
///
/// The backend stamps each `aggregate_line` bucket at the minute's START and
/// fills it with each source's latest reading before the minute's END
/// (`compute_aggregated_probability`). The phone plots on a real time axis and
/// joins those buckets with exact-time pushed frames, so a change inside a
/// minute drew as: served M:00 (the value from M:40) → frame M:10 (the older
/// value) → frame M:40 (back again). Latency measured the mechanism on 10/28
/// (`artifacts/latency-10090-held-tail-20261028/`); web draws one category per
/// minute and is immune.
///
/// The fixture is that shape: the price falls .50 → .40 at 17:44:40, inside the
/// 17:44 minute, and the page holds both frames. The pre-fix control is the
/// SAME payload without the server's read-time pin, which keeps today's
/// minute-start placement (an unpinned payload proves no read time, so it is
/// deliberately left alone).
final class AServedMinuteMeetsHeldFramesAtItsEnd11105Tests: XCTestCase {

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

    /// Three served minutes and the live pin at the read time (17:45:40).
    /// 17:43 holds .50 (its last reading came before the fall); 17:44 holds .40
    /// (the 17:44:40 reading); 17:45 holds .35, read at 17:45:40 like the pin.
    private func payload(pinned: Bool = true, status: String = "live") throws -> EventHistoryResponse {
        try decode("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A", "status": "\(status)",
          "history": [],
          "win_prob_history": {"polymarket": [{"timestamp": "2026-10-28T17:44:40Z", "home_probability": 0.40}]},
          "aggregate_line": [
            {"timestamp": "2026-10-28T17:43:00Z", "home_probability": 0.50},
            {"timestamp": "2026-10-28T17:44:00Z", "home_probability": 0.40},
            {"timestamp": "2026-10-28T17:45:00Z", "home_probability": 0.35},
            {"timestamp": "2026-10-28T17:45:40Z", "home_probability": 0.35}
          ],
          "blend_edge_pinned": \(pinned)
        }
        """)
    }

    private func frames(tail: Bool = false) -> [LiveBlendPoint] {
        var stamps: [(String, Double)] = [
            ("2026-10-28T17:44:10Z", 0.50), ("2026-10-28T17:44:40Z", 0.40), ("2026-10-28T17:45:20Z", 0.35),
        ]
        if tail { stamps.append(("2026-10-28T17:45:50Z", 0.33)) }
        return stamps.map { LiveBlendPoint(date: at($0.0), homeProbability: $0.1) }
    }

    private func blend(_ history: EventHistoryResponse, _ frames: [LiveBlendPoint]) -> [(date: Date, value: Double)] {
        OddsChartView.chartPoints(from: history, liveFrames: frames)
            .filter { $0.source == "aggregate" }
            .map { (date: $0.date, value: $0.probability) }
    }

    /// Direction changes along the drawn line, ignoring flat steps.
    private func reversals(_ line: [(date: Date, value: Double)]) -> Int {
        var count = 0, last = 0.0
        for (a, b) in zip(line, line.dropFirst()) {
            let step = b.value - a.value
            guard abs(step) > 1e-9 else { continue }
            if last != 0, (step > 0) != (last > 0) { count += 1 }
            last = step
        }
        return count
    }

    // MARK: - The ship

    func testAChangeInsideAMinuteDrawsOnceAtItsRealTime() throws {
        let line = blend(try payload(), frames())

        XCTAssertEqual(reversals(line), 0, "the price only fell; the line only falls")
        XCTAssertEqual(line.map(\.date), line.map(\.date).sorted(), "time order")
        XCTAssertEqual(line.map(\.date), [
            "2026-10-28T17:44:00Z",  // the 17:43 minute, at its end
            "2026-10-28T17:44:10Z", "2026-10-28T17:44:40Z",  // held frames, own times
            "2026-10-28T17:45:00Z",  // the 17:44 minute, at its end
            "2026-10-28T17:45:20Z",  // held frame
            "2026-10-28T17:45:40Z",  // the 17:45 minute: its end is past the read, so the read
            "2026-10-28T17:45:40Z",  // the server's pin, still last
        ].map(at))
        XCTAssertEqual(line.map(\.value), [0.50, 0.50, 0.40, 0.40, 0.35, 0.35, 0.35])
    }

    /// Pre-fix control: the same buckets left at the minute's start draw the
    /// out-and-back the reader saw. Without this the ship test could pass on a
    /// fixture that never spiked.
    func testControlTheSameMinutesAtTheirStartDrawTheSpike() throws {
        let line = blend(try payload(pinned: false), frames())

        XCTAssertGreaterThanOrEqual(reversals(line), 2, "down, back up, down again")
        let around = line.filter { $0.date >= at("2026-10-28T17:44:00Z") && $0.date <= at("2026-10-28T17:44:40Z") }
        XCTAssertEqual(around.map(\.value), [0.40, 0.50, 0.40], "17:44:00 shows the 17:44:40 price before 17:44:10")
        XCTAssertEqual(line.first?.date, at("2026-10-28T17:43:00Z"), "an unpinned payload keeps minute starts")
    }

    // MARK: - What must not change

    func testAFreshChartWithNoFramesIsUnchanged() throws {
        let history = try payload()
        let line = blend(history, [])
        XCTAssertEqual(line.map(\.date), try XCTUnwrap(history.aggregateLine).map { at($0.timestamp) })
        XCTAssertEqual(line.map(\.value), try XCTUnwrap(history.aggregateLine).map(\.homeProbability))
    }

    func testTheLineStillEndsOnTheHeadline() throws {
        let history = try payload()
        // No tail: the pin ends the line at the read time, as before.
        let held = blend(history, frames())
        XCTAssertEqual(held.last?.date, at("2026-10-28T17:45:40Z"))
        XCTAssertEqual(held.last?.value, 0.35)
        XCTAssertFalse(held.contains { $0.date > at("2026-10-28T17:45:40Z") }, "no served minute moves past the read")

        // A frame past the read is the tail and ends the line.
        let tailed = blend(history, frames(tail: true))
        XCTAssertEqual(tailed.last?.date, at("2026-10-28T17:45:50Z"))
        XCTAssertEqual(tailed.last?.value, 0.33)

        // The page's catch-up check reads the served edge, which did not move.
        XCTAssertEqual(
            OddsChartView.chartPoints(from: history, liveFrames: frames())
                .filter { $0.source == "aggregate" }.map(\.date).max(),
            at("2026-10-28T17:45:40Z"))
    }

    func testEveryServedValueSurvivesInOrderWithNoneAddedOrRemoved() throws {
        let history = try payload()
        let served = try XCTUnwrap(history.aggregateLine).map(\.homeProbability)
        let shifted = OddsChartView.servedBlendAtEvidenceTime(
            OddsChartView.chartPoints(from: history), history: history, previewAt: nil)
            .filter { $0.source == "aggregate" }
        XCTAssertEqual(shifted.map(\.probability), served, "same values, same order")
        XCTAssertEqual(shifted.map(\.date), shifted.map(\.date).sorted())

        // Only the blend moves: the venue series stays at its own times.
        let venue = OddsChartView.chartPoints(from: history, liveFrames: frames())
            .filter { $0.source == "polymarket" }.map(\.date)
        XCTAssertEqual(venue, [at("2026-10-28T17:44:40Z")])
    }

    func testAFinishedPayloadIsNeverMoved() throws {
        let history = try payload(status: "completed")
        XCTAssertEqual(blend(history, frames()).map(\.date),
                       try XCTUnwrap(history.aggregateLine).map { at($0.timestamp) })
    }

    /// When a preview replaced the pin, the preview must stay strictly newer
    /// than every committed point: the minute that contains it stays put, the
    /// earlier ones still move to their ends.
    func testAPreviewThatReplacedThePinStillEndsTheLine() throws {
        let history = try payload()
        let preview = at("2026-10-28T17:45:30Z")
        let moved = OddsChartView.servedBlendAtEvidenceTime(
            OddsChartView.chartPoints(from: history).filter { $0.date < at("2026-10-28T17:45:40Z") },
            history: history, previewAt: preview)
            .filter { $0.source == "aggregate" }.map(\.date)
        XCTAssertEqual(moved, ["2026-10-28T17:44:00Z", "2026-10-28T17:45:00Z", "2026-10-28T17:45:00Z"].map(at))
        XCTAssertTrue(moved.allSatisfy { $0 < preview })
    }
}
