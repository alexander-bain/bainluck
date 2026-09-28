import XCTest
@testable import Bain_Luck

/// #9268 — the game clock keeps up with a pushed price.
///
/// Build-28 simulator, Rams at Broncos: the hero moved by push (86% → 88%,
/// Received 7:20:13 → 7:21:22 PM) while the badge held Q3 11:13 and the served
/// `espn.game_clock` had already gone 11:10 → 9:56. The stream carries a price
/// and no game state, and while it delivered the page re-read the detail only
/// every 120 s.
///
/// BOTH DIRECTIONS (gotcha #43): the pushed slow lane now reads the detail every
/// 30 s, AND it still reads the other five endpoints only every 120 s — a fix
/// that moved the whole page back to 30 s would pass the first half while
/// throwing #2687's saving away. And every other plan runs exactly the loop it
/// ran before.
@MainActor
final class AGameClockKeepsUpWithPushedPrices9268Tests: XCTestCase {

    // MARK: - The pure decision

    func testOnlyThePushedSlowLaneIsCutIntoGameStateReads() {
        XCTAssertEqual(EventRefreshPlan.slots(for: .poll(every: EventRefreshPlan.livePushPollInterval)), 4)
        for plan: EventRefreshPlan in [
            .idle,
            .poll(every: EventRefreshPlan.livePollInterval),
            .poll(every: EventRefreshPlan.imminentPollInterval),
            .poll(every: EventRefreshPlan.distantPollInterval)
        ] {
            XCTAssertEqual(EventRefreshPlan.slots(for: plan), 1, "\(plan) was cut into detail-only reads")
        }
    }

    /// The pushed page's clock is never older than an unpushed page's.
    func testTheGameStateReadIsAsFrequentAsTheUnpushedPoll() {
        XCTAssertLessThanOrEqual(EventRefreshPlan.liveStatePollInterval, EventRefreshPlan.livePollInterval)
        XCTAssertLessThan(EventRefreshPlan.liveStatePollInterval, EventRefreshPlan.livePushPollInterval)
    }

    // MARK: - Fakes

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

    /// Serves `script` in order, then repeats its last entry. Counts the detail
    /// and the history separately: a history fetch is how a test tells a full
    /// `load()` from a game-state read.
    private nonisolated final class ScriptedClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var script: [EventDetail]
        private var last: EventDetail?
        private var details = 0
        private var histories = 0
        init(_ script: [EventDetail]) { self.script = script }
        var detailCount: Int { lock.withLock { details } }
        var historyCount: Int { lock.withLock { histories } }
        func fetchEvent(id: Int) async throws -> EventDetail {
            let next: EventDetail? = lock.withLock {
                details += 1
                if !script.isEmpty { last = script.removeFirst() }
                return last
            }
            guard let next else { throw Declined() }
            return next
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            lock.withLock { histories += 1 }
            throw Declined()
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// The poll's sleep. Records every interval it is asked for, and parks every
    /// loop (cancellably, so a re-plan retires it) until the test releases one
    /// wake — then exactly one sleeper returns and runs exactly one slot.
    private nonisolated final class Sleeper: @unchecked Sendable {
        private let lock = NSLock()
        private var wakes = 0
        private var asked: [TimeInterval] = []
        var recorded: [TimeInterval] { lock.withLock { asked } }
        func release() { lock.withLock { wakes += 1 } }
        func sleep(_ seconds: TimeInterval) async {
            lock.withLock { asked.append(seconds) }
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

    /// Rams at Broncos, Q3. The Kalshi reading is stamped 17:00:00 in every
    /// served payload, so a pushed frame stamped after it is the newer price.
    private func live(clock: String, status: String = "live", home: Int = 16) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Denver Broncos","away_team":"Los Angeles Rams","status":"\(status)",
         "home_score":\(home),"away_score":0,
         "espn":{"game_clock":"\(clock)","period":"3"},
         "current_odds":{"home_probability":0.86,"away_probability":0.14,
           "home_rendered_percent":86,"away_rendered_percent":14},
         "win_probability_sources":{"kalshi":{"value":0.86,"updated_at":"2026-09-28T02:19:00Z"}}}
        """.utf8))
    }

    /// Two points: a real price move that does NOT arm #9056's catch-up, so the
    /// page stays on the slow lane this ship is about.
    private func pushSmallMove(_ handle: FakeHandle) {
        handle.fire("probability", #"""
        {"event_id":4242,"p":0.88,"source":"kalshi","source_value":0.88,"updated_at":"2026-09-28T02:20:50Z","status":"live"}
        """#)
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

    private func page(
        _ script: [EventDetail], push: Bool = true
    ) async -> (EventDetailViewModel, FakeHandle, ScriptedClient, Sleeper) {
        let handle = FakeHandle()
        let client = ScriptedClient(script)
        let sleeper = Sleeper()
        let vm = EventDetailViewModel(
            eventId: 4242,
            client: client,
            makeStreamHandle: { _ in handle },
            now: { 1_790_562_050 },
            sleep: { seconds in await sleeper.sleep(seconds) }
        )
        await vm.load()
        if push {
            handle.fire("open")
            pushSmallMove(handle)
        }
        return (vm, handle, client, sleeper)
    }

    // MARK: - The wired page

    /// THE SHIP. Thirty seconds into the slow lane the clock moves — and only
    /// the detail was asked for, and the pushed price beside it is not undone.
    func testThePushedPageMovesTheClockOnTheNextGameStateRead() async throws {
        let (vm, _, client, sleeper) = await page([
            try live(clock: "11:13"),
            try live(clock: "9:56")
        ])
        defer { vm.stopRefresh() }
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePushPollInterval))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.88, "the push never reached the hero")
        await waitUntil("the slow lane to park on its first slot") { sleeper.recorded.last == 30 }
        let loadedAt = vm.lastLoadedAt

        sleeper.release()
        await waitUntil("the clock to move under the pushed price") { vm.event?.espn?.gameClock == "9:56" }

        XCTAssertEqual(client.detailCount, 2)
        XCTAssertEqual(client.historyCount, 1, "a game-state read ran the whole six-request load")
        XCTAssertEqual(vm.lastLoadedAt, loadedAt, "a game-state read claimed to be a load")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.88, "the older cached detail undid the push")
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePushPollInterval))
    }

    /// The saving is kept: three game-state reads, then the full load, every
    /// slot 30 s apart — so the chart and markets still refresh on 120 s.
    func testTheFourthSlotIsTheFullLoad() async throws {
        let (vm, _, client, sleeper) = await page([try live(clock: "11:13")])
        defer { vm.stopRefresh() }
        await waitUntil("the slow lane to park") { sleeper.recorded.last == 30 }

        for read in 1...3 {
            sleeper.release()
            await waitUntil("game-state read \(read)") { client.detailCount == 1 + read }
            XCTAssertEqual(client.historyCount, 1, "slot \(read) ran a full load")
        }
        sleeper.release()
        await waitUntil("the full load on the fourth slot") { client.historyCount == 2 }
        XCTAssertEqual(client.detailCount, 5)
        await waitUntil("the loop to park again") { sleeper.recorded.count >= 5 }
        XCTAssertEqual(Set(sleeper.recorded.suffix(5)), [30], "the slow lane slept in slots other than 30 s")
    }

    /// The sibling: an unpushed live page runs exactly the loop it ran before —
    /// one slot of 30 s, and every wake is a full load.
    func testAnUnpushedLivePageStillFullyLoadsEveryPoll() async throws {
        let (vm, _, client, sleeper) = await page([try live(clock: "11:13")], push: false)
        defer { vm.stopRefresh() }
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePollInterval))
        await waitUntil("the poll to park") { sleeper.recorded.last == 30 }

        sleeper.release()
        await waitUntil("the full load") { client.historyCount == 2 }
        XCTAssertEqual(client.detailCount, 2)
    }

    /// A game-state read that brings the final re-plans the page as a load
    /// would: settled means settled, so nothing asks again.
    func testAGameStateReadThatBringsTheFinalSettlesThePage() async throws {
        let (vm, _, _, sleeper) = await page([
            try live(clock: "0:12"),
            try live(clock: "0:00", status: "completed", home: 23)
        ])
        defer { vm.stopRefresh() }
        await waitUntil("the slow lane to park") { sleeper.recorded.last == 30 }

        sleeper.release()
        await waitUntil("the final to arrive by the game-state read") { vm.event?.status == "completed" }
        XCTAssertEqual(vm.event?.homeScore, 23)
        await waitUntil("the page to go idle") { !vm.isAutoRefreshing }
        XCTAssertNil(vm.currentRefreshPlan)
        XCTAssertFalse(vm.streamDelivering, "a settled page kept its stream open")
    }
}
