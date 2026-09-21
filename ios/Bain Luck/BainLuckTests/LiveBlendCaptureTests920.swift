import XCTest
@testable import Bain_Luck

/// #920, the producing half — a pushed frame must reach the CHART, not only the
/// hero.
///
/// `EventDetailViewModel.apply` wrote `event.currentOdds` and stopped there, and
/// `OddsChartView` never reads `currentOdds`. So the better the push path worked,
/// the further the two numbers on one screen drifted apart: a hero ticking every
/// few seconds above a line whose right edge had not moved since the page opened.
///
/// These drive the REAL `LiveStreamController` through its fake handle, so the
/// frame travels the path production uses — SSE text, decode, controller, `apply`
/// — rather than being handed to `apply` directly. No socket, no server, no wall
/// clock.
@MainActor
final class LiveBlendCaptureTests920: XCTestCase {

    // MARK: - Fakes

    /// `@unchecked Sendable` is honest: `LiveStreamHandle` is `@MainActor` and
    /// every member here is only ever touched on that actor.
    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    /// Serves one live event and declines the five secondary fetches, which
    /// `load()` is documented to tolerate. Nothing here is under test; it exists
    /// so the view model can reach the state where a stream is open.
    private struct LiveOnlyClient: EventDetailProviding {
        struct Declined: Error {}
        let event: EventDetail
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private let anchor = Date(timeIntervalSince1970: 1_757_000_000)

    private func liveEvent() throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {
          "id": 4242, "home_team": "Red Sox", "away_team": "Yankees",
          "status": "live",
          "current_odds": {"home_probability": 0.40, "away_probability": 0.60}
        }
        """.utf8))
    }

    /// Runs `body` against a live page with a fake socket, already loaded and
    /// delivering.
    ///
    /// The poll's sleep is long enough never to return inside a case, so nothing
    /// below races a refetch and every change observed is the stream's. That is
    /// also why the teardown is not optional: an uncancelled poll task keeps the
    /// view model alive after the case ends, so it is cancelled on EVERY exit,
    /// including a failing one.
    private func withLivePage(
        _ body: @MainActor (EventDetailViewModel, FakeHandle) throws -> Void
    ) async throws {
        let handle = FakeHandle()
        let vm = EventDetailViewModel(
            eventId: 4242,
            client: LiveOnlyClient(event: try liveEvent()),
            makeStreamHandle: { _ in handle },
            now: { [anchor] in anchor.timeIntervalSince1970 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        defer { vm.stopRefresh() }

        await vm.load()
        handle.fire("open")
        XCTAssertTrue(vm.streamDelivering, "every case here is about a DELIVERING stream")
        try body(vm, handle)
    }

    private func frame(p: String, updatedAt: String?) -> String {
        let stamp = updatedAt.map { "\"updated_at\": \"\($0)\"" } ?? "\"updated_at\": null"
        return "{\"event_id\": 4242, \"p\": \(p), \"source\": \"kalshi\", \"source_value\": 0.5, \(stamp)}"
    }

    // MARK: - The ship

    func testAPushedFrameIsKeptForTheChartAtItsStampedTime() async throws {
        try await withLivePage { vm, handle in
            XCTAssertTrue(vm.liveBlend.isEmpty, "nothing pushed yet")

            handle.fire("probability", frame(p: "0.52", updatedAt: "2026-09-21T12:12:00Z"))
            handle.fire("probability", frame(p: "0.58", updatedAt: "2026-09-21T12:14:00Z"))

            XCTAssertEqual(vm.liveBlend.count, 2)
            XCTAssertEqual(vm.liveBlend.map(\.date), [
                "2026-09-21T12:12:00Z".asDate, "2026-09-21T12:14:00Z".asDate
            ].compactMap { $0 })
            XCTAssertEqual(vm.liveBlend.last?.homeProbability ?? 0, 0.58, accuracy: 0.0001)
        }
    }

    /// One question, one number. The chart's newest point and the hero must be
    /// the same reading — that agreement is the entire ship.
    func testTheChartsNewestPointIsTheNumberTheHeroIsShowing() async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: "0.58", updatedAt: "2026-09-21T12:14:00Z"))

            XCTAssertEqual(
                vm.liveBlend.last?.homeProbability ?? .nan,
                vm.event?.currentOdds?.homeProbability ?? .infinity,
                accuracy: 0.0001
            )
        }
    }

    /// The stream replays its most recent frame across a reconnect.
    func testAReplayedFrameDoesNotBecomeASecondPoint() async throws {
        try await withLivePage { vm, handle in
            let repeated = frame(p: "0.52", updatedAt: "2026-09-21T12:12:00Z")

            handle.fire("probability", repeated)
            handle.fire("probability", repeated)

            XCTAssertEqual(vm.liveBlend.count, 1)
        }
    }

    /// A frame with no stamp has no honest x-coordinate. It still moves the hero,
    /// which needs none; placing it at "now" would draw an invented time beside
    /// backend points that all carry real ones.
    func testAnUnstampedFrameMovesTheHeroButDrawsNoPoint() async throws {
        try await withLivePage { vm, handle in

            handle.fire("probability", frame(p: "0.71", updatedAt: nil))

            XCTAssertTrue(vm.liveBlend.isEmpty, "no stamp, no point")
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability ?? 0, 0.71, accuracy: 0.0001,
                           "the hero still takes it — this is not a dropped frame")
        }
    }

    /// A frame carrying no probability is a status/heartbeat-shaped frame.
    func testAFrameWithNoProbabilityDrawsNoPoint() async throws {
        try await withLivePage { vm, handle in

            handle.fire("probability", frame(p: "null", updatedAt: "2026-09-21T12:12:00Z"))

            XCTAssertTrue(vm.liveBlend.isEmpty)
        }
    }

    /// End to end on the pure seam the chart actually calls: frames captured off
    /// the wire, merged onto a payload whose blend stops earlier, extend it.
    func testFramesCapturedFromTheStreamExtendTheChartsBlend() async throws {
        try await withLivePage { vm, handle in
            handle.fire("probability", frame(p: "0.52", updatedAt: "2026-09-21T12:12:00Z"))
            handle.fire("probability", frame(p: "0.58", updatedAt: "2026-09-21T12:14:00Z"))

            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let history = try decoder.decode(EventHistoryResponse.self, from: Data("""
            {
              "event_id": 4242, "home_team": "Red Sox", "away_team": "Yankees", "status": "live",
              "history": [{"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.44}],
              "win_prob_history": {"espn": [{"timestamp": "2026-09-21T12:06:00Z", "home_probability": 0.47}]},
              "aggregate_line": [
                {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.41},
                {"timestamp": "2026-09-21T12:10:00Z", "home_probability": 0.46}
              ]
            }
            """.utf8))

            let blend = OddsChartView.chartPoints(from: history, liveFrames: vm.liveBlend)
                .filter { $0.source == "aggregate" }
                .sorted { $0.date < $1.date }

            XCTAssertEqual(blend.count, 4, "2 published + 2 pushed")
            XCTAssertEqual(blend.last?.date, "2026-09-21T12:14:00Z".asDate)
            XCTAssertEqual(blend.last?.probability ?? 0, 0.58, accuracy: 0.0001)
        }
    }
}
