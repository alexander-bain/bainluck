import XCTest
@testable import Bain_Luck

/// #10834 (under #10090) — leaving an event page whose live stream is
/// delivering stops its poll, and coming back starts exactly one.
///
/// At `0fc33d9184` `stopRefresh()` cancelled the poll, then called
/// `stopStream()`. Stopping the controller fired `onDeliveringChange(false)`,
/// and that callback re-planned while `stream` was still set: the plan was the
/// 30 s poll and nothing was running, so a new loop was installed on a page
/// nobody was looking at. It ran a full load every 30 s until the view model
/// was freed.
///
/// BOTH DIRECTIONS: a left page installs no loop and reads nothing more, AND a
/// deliberate return (`load()`, what the view runs on appear) arms exactly one
/// poll loop and one new stream, with no loop left over from before.
@MainActor
final class ALeftPageStaysStopped10834Tests: XCTestCase {

    // MARK: - Fakes

    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        var isClosed = false
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    /// Answers the detail every time and declines every optional section, so
    /// the only reads a test counts are the page's own detail reads.
    private nonisolated final class CountingClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private let detail: EventDetail
        private var details = 0
        init(_ detail: EventDetail) { self.detail = detail }
        var detailCount: Int { lock.withLock { details } }
        func fetchEvent(id: Int) async throws -> EventDetail {
            lock.withLock { details += 1 }
            return detail
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// The poll's sleep: parks each loop (cancellably) until the test releases
    /// exactly one wake. `parked` counts loops sleeping right now.
    private nonisolated final class Sleeper: @unchecked Sendable {
        private let lock = NSLock()
        private var wakes = 0
        private var sleeping = 0
        var parked: Int { lock.withLock { sleeping } }
        func release() { lock.withLock { wakes += 1 } }
        func sleep(_ seconds: TimeInterval) async {
            lock.withLock { sleeping += 1 }
            defer { lock.withLock { sleeping -= 1 } }
            while !Task.isCancelled {
                let go: Bool = lock.withLock {
                    guard wakes > 0, !Task.isCancelled else { return false }
                    wakes -= 1
                    return true
                }
                if go { return }
                try? await Task.sleep(nanoseconds: 200_000)
            }
        }
    }

    // MARK: - Fixtures

    private func live() throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Denver Broncos","away_team":"Los Angeles Rams","status":"live",
         "home_score":16,"away_score":0,
         "espn":{"game_clock":"11:13","period":"3"},
         "current_odds":{"home_probability":0.86,"away_probability":0.14,
           "home_rendered_percent":86,"away_rendered_percent":14},
         "win_probability_sources":{"kalshi":{"value":0.86,"updated_at":"2026-09-28T02:19:00Z"}}}
        """.utf8))
    }

    private func waitUntil(
        _ description: String, timeout: TimeInterval = 3, _ condition: @MainActor () -> Bool
    ) async {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return }
            await Task.yield()
            try? await Task.sleep(nanoseconds: 200_000)
        }
        XCTFail("timed out waiting for: \(description)")
    }

    private func deliver(_ handle: FakeHandle) {
        handle.fire("open")
        handle.fire("probability", #"""
        {"event_id":4242,"p":0.88,"source":"kalshi","source_value":0.88,"updated_at":"2026-09-28T02:20:50Z","status":"live"}
        """#)
    }

    /// A live page whose stream is delivering, its push-cadence loop parked.
    private func deliveringPage() async throws
        -> (EventDetailViewModel, CountingClient, Sleeper, () -> [FakeHandle]) {
        var handles: [FakeHandle] = []
        let client = CountingClient(try live())
        let sleeper = Sleeper()
        let vm = EventDetailViewModel(
            eventId: 4242,
            client: client,
            makeStreamHandle: { _ in
                let handle = FakeHandle()
                handles.append(handle)
                return handle
            },
            now: { 1_790_562_050 },
            sleep: { seconds in await sleeper.sleep(seconds) }
        )
        await vm.load()
        XCTAssertEqual(handles.count, 1, "the live page opened no stream")
        deliver(handles[0])
        await waitUntil("the delivering page to park on the push cadence") {
            vm.streamDelivering
                && vm.currentRefreshPlan == .poll(every: EventRefreshPlan.livePushPollInterval)
                && sleeper.parked == 1
        }
        return (vm, client, sleeper, { handles })
    }

    // MARK: - Leaving

    /// THE SHIP. The reader leaves while the stream is delivering: no loop is
    /// installed, the stream is closed, and released wakes read nothing.
    func testLeavingADeliveringPageInstallsNoPoll() async throws {
        let (vm, client, sleeper, handles) = try await deliveringPage()
        let base = client.detailCount

        vm.stopRefresh()

        XCTAssertFalse(vm.isAutoRefreshing, "the stream's stop callback re-armed the poll on a left page")
        XCTAssertNil(vm.currentRefreshPlan, "a left page names a cadence")
        XCTAssertFalse(vm.streamDelivering)
        XCTAssertTrue(handles()[0].isClosed, "the left page kept its socket")
        XCTAssertEqual(handles().count, 1, "stopping opened another stream")
        await waitUntil("the stopped loop to leave its sleep") { sleeper.parked == 0 }

        for _ in 1...3 { sleeper.release() }
        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(client.detailCount, base, "a left page kept reading")
        XCTAssertEqual(sleeper.parked, 0, "a left page started another loop")
        XCTAssertFalse(vm.isAutoRefreshing)
    }

    // MARK: - Coming back

    /// A deliberate return still works, and runs ONE loop and ONE stream: the
    /// unpushed cadence first, then the push cadence once the new stream
    /// delivers, and one released wake is one read.
    func testReturningToALeftPageArmsOneLoopAndOneStream() async throws {
        let (vm, client, sleeper, handles) = try await deliveringPage()
        defer { vm.stopRefresh() }
        vm.stopRefresh()
        await waitUntil("the stopped loop to leave its sleep") { sleeper.parked == 0 }

        await vm.load()
        XCTAssertEqual(handles().count, 2, "the return opened no new stream")
        XCTAssertTrue(handles()[0].isClosed)
        XCTAssertFalse(handles()[1].isClosed)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePollInterval))
        await waitUntil("the returned page to park one loop") { sleeper.parked == 1 }

        deliver(handles()[1])
        await waitUntil("the returned page to move to the push cadence") {
            vm.currentRefreshPlan == .poll(every: EventRefreshPlan.livePushPollInterval)
        }
        await waitUntil("exactly one loop to stay parked after the re-plan") { sleeper.parked == 1 }
        XCTAssertEqual(handles().count, 2, "delivery opened another stream")

        let base = client.detailCount
        sleeper.release()
        await waitUntil("one wake to read the detail") { client.detailCount == base + 1 }
        await waitUntil("the loop to park again") { sleeper.parked == 1 }
        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(client.detailCount, base + 1, "a second loop read on the same wake")
        XCTAssertEqual(sleeper.parked, 1, "a duplicate loop is parked")
    }
}
