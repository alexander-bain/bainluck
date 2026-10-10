import XCTest
@testable import Bain_Luck

/// #10833 (under #10090) — a slow optional section never holds the poll loop.
///
/// At `361cb29772` the loop's full-load slot ran `await load(fresh: false)`,
/// and `load()` returned only after history, related futures, progression,
/// game markets and line movement had all been awaited. Telemetry measured
/// related-futures and line-movement reads at 37–81 s; for that long the same
/// loop could not reach its next game-state slot, so a held page's score and
/// clock stood still while prices kept arriving by push.
///
/// BOTH DIRECTIONS: the next game-state slot runs while one optional read is
/// still pending, AND the slot after that does not stack a second read of the
/// pending section — it joins it; the read still lands and still stamps the
/// load; a stopped page asks for nothing more.
@MainActor
final class ASlowOptionalSectionDoesNotHoldTheGameState10833Tests: XCTestCase {

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

    /// Serves `script` in order, then repeats its last entry. The first
    /// related-futures read (the page opening) answers at once; every later one
    /// is held until `releaseRelatedFutures()`, standing in for the 37–81 s read.
    private nonisolated final class SlowSectionClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private var script: [EventDetail]
        private var last: EventDetail?
        private var details = 0
        private var histories = 0
        private var relatedReads = 0
        private var relatedReleased = false
        private let related: (Int) throws -> RelatedFuturesResponse
        init(_ script: [EventDetail], related: @escaping (Int) throws -> RelatedFuturesResponse) {
            self.script = script
            self.related = related
        }
        var detailCount: Int { lock.withLock { details } }
        var historyCount: Int { lock.withLock { histories } }
        var relatedFuturesCount: Int { lock.withLock { relatedReads } }
        func releaseRelatedFutures() { lock.withLock { relatedReleased = true } }
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
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
            let read: Int = lock.withLock { relatedReads += 1; return relatedReads }
            if read > 1 {
                while !lock.withLock({ relatedReleased }) {
                    try? await Task.sleep(nanoseconds: 200_000)
                }
            }
            return try related(read)
        }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// The poll's sleep: records every interval asked for and parks each loop
    /// (cancellably) until the test releases exactly one wake. `parked` counts
    /// loops sleeping right now — a re-plan's retired loop leaves on cancel.
    private nonisolated final class Sleeper: @unchecked Sendable {
        private let lock = NSLock()
        private var wakes = 0
        private var sleeping = 0
        private var asked: [TimeInterval] = []
        var recorded: [TimeInterval] { lock.withLock { asked } }
        var parked: Int { lock.withLock { sleeping } }
        func release() { lock.withLock { wakes += 1 } }
        func sleep(_ seconds: TimeInterval) async {
            lock.withLock { asked.append(seconds); sleeping += 1 }
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

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func live(clock: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Denver Broncos","away_team":"Los Angeles Rams","status":"live",
         "home_score":16,"away_score":0,
         "espn":{"game_clock":"\(clock)","period":"3"},
         "current_odds":{"home_probability":0.86,"away_probability":0.14,
           "home_rendered_percent":86,"away_rendered_percent":14},
         "win_probability_sources":{"kalshi":{"value":0.86,"updated_at":"2026-09-28T02:19:00Z"}}}
        """.utf8))
    }

    /// Read `n`'s box score carries `n`, so the test can tell which read landed.
    private func related(_ read: Int) throws -> RelatedFuturesResponse {
        try decoder().decode(RelatedFuturesResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Denver Broncos","away_team":"Los Angeles Rams",
         "box_score":{"read":{"n":\(read)}}}
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

    /// A pushed live page (the held page of the report) on the slow lane: three
    /// game-state slots, then the full load, every 30 s.
    private func heldPage(
        _ script: [EventDetail], push: Bool = true
    ) async -> (EventDetailViewModel, SlowSectionClient, Sleeper) {
        let handle = FakeHandle()
        let client = SlowSectionClient(script, related: { [unowned self] in try self.related($0) })
        let sleeper = Sleeper()
        let vm = EventDetailViewModel(
            eventId: 4242,
            client: client,
            makeStreamHandle: { _ in handle },
            now: { 1_790_562_050 },
            sleep: { seconds in await sleeper.sleep(seconds) }
        )
        await vm.load()
        guard push else { return (vm, client, sleeper) }
        handle.fire("open")
        handle.fire("probability", #"""
        {"event_id":4242,"p":0.88,"source":"kalshi","source_value":0.88,"updated_at":"2026-09-28T02:20:50Z","status":"live"}
        """#)
        return (vm, client, sleeper)
    }

    /// Runs the three game-state slots and the full load, then waits for the
    /// loop to park again although that load's related-futures read is held.
    /// Returns the detail count before the first slot.
    @discardableResult
    private func reachHeldFullLoad(
        _ vm: EventDetailViewModel, _ client: SlowSectionClient, _ sleeper: Sleeper
    ) async -> Int {
        await waitUntil("the slow lane to park") {
            vm.currentRefreshPlan == .poll(every: EventRefreshPlan.livePushPollInterval) && sleeper.parked == 1
        }
        let base = client.detailCount
        for slot in 1...4 {
            sleeper.release()
            await waitUntil("slot \(slot) to read the detail") { client.detailCount == base + slot }
            await waitUntil(slot < 4 ? "slot \(slot) to park again"
                            : "the loop to park again behind the full load's pending optional read") {
                sleeper.parked == 1
            }
        }
        XCTAssertEqual(client.relatedFuturesCount, 2, "the full load never asked for related futures")
        XCTAssertEqual(client.historyCount, 2, "slot 4 was not the full load")
        XCTAssertEqual(sleeper.recorded.last, 30, "the loop changed its cadence")
        return base
    }

    // MARK: - The wired page

    /// THE SHIP. The full load's related-futures read is still pending, and the
    /// next game-state slot runs anyway and moves the clock.
    func testTheNextGameStateSlotRunsWhileAnOptionalReadIsPending() async throws {
        let (vm, client, sleeper) = await heldPage([
            try live(clock: "11:13"), try live(clock: "11:13"), try live(clock: "11:13"),
            try live(clock: "11:13"), try live(clock: "11:13"), try live(clock: "9:56")
        ])
        defer { vm.stopRefresh() }
        let base = await reachHeldFullLoad(vm, client, sleeper)
        let loadedAt = vm.lastLoadedAt
        XCTAssertNotNil(loadedAt)

        sleeper.release()
        await waitUntil("the clock to move while related futures is pending") { vm.event?.espn?.gameClock == "9:56" }

        XCTAssertEqual(client.detailCount, base + 5)
        XCTAssertEqual(client.relatedFuturesCount, 2)
        XCTAssertEqual(vm.relatedFutures?.boxScore?["read"]?["n"], 1, "the pending read was invented")
        XCTAssertEqual(vm.lastLoadedAt, loadedAt, "a load claimed to finish before its sections did")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.88, "the game-state read undid the push")

        client.releaseRelatedFutures()
        await waitUntil("the pending read to land") { vm.relatedFutures?.boxScore?["read"]?["n"] == 2 }
        await waitUntil("the load to stamp once its sections settled") { vm.lastLoadedAt != loadedAt }
    }

    /// No stacking: the next full load finds related futures still in flight and
    /// joins it — one read, not two — while its other sections run again.
    func testTheNextFullLoadJoinsThePendingReadInsteadOfStackingOne() async throws {
        let (vm, client, sleeper) = await heldPage([try live(clock: "11:13")])
        defer { vm.stopRefresh() }
        let base = await reachHeldFullLoad(vm, client, sleeper)

        for slot in 5...8 {
            sleeper.release()
            await waitUntil("slot \(slot) to read the detail") { client.detailCount == base + slot }
            await waitUntil("slot \(slot) to park again") { sleeper.parked == 1 }
        }
        XCTAssertEqual(client.historyCount, 3, "slot 8 was not the full load")
        XCTAssertEqual(client.relatedFuturesCount, 2, "a second related-futures read stacked on the pending one")

        client.releaseRelatedFutures()
        await waitUntil("the joined read to land") { vm.relatedFutures?.boxScore?["read"]?["n"] == 2 }
        // Once settled, the section is free: the next full load reads it again.
        for slot in 9...12 {
            sleeper.release()
            await waitUntil("slot \(slot) to read the detail") { client.detailCount == base + slot }
            await waitUntil("slot \(slot) to park again") { sleeper.parked == 1 }
        }
        await waitUntil("a new related-futures read after the joined one settled") {
            client.relatedFuturesCount == 3
        }
    }

    /// A page the reader left asks for nothing more, and the read already in
    /// flight still lands, as it did when the loop awaited it. Unpushed — every
    /// slot is the full load: leaving a page whose stream is DELIVERING re-arms
    /// the poll from the stream's own stop callback, at master as here (#10834),
    /// which this ship does not touch.
    func testAStoppedPageRunsNoFurtherSlotWhileItsReadLands() async throws {
        let (vm, client, sleeper) = await heldPage([try live(clock: "11:13")], push: false)
        await waitUntil("the unpushed page to park") {
            vm.currentRefreshPlan == .poll(every: EventRefreshPlan.livePollInterval) && sleeper.parked == 1
        }
        let base = client.detailCount
        sleeper.release()
        await waitUntil("the full load to read the detail") { client.detailCount == base + 1 }
        await waitUntil("the loop to park again behind the pending related-futures read") { sleeper.parked == 1 }
        XCTAssertEqual(client.relatedFuturesCount, 2)

        vm.stopRefresh()
        XCTAssertFalse(vm.isAutoRefreshing)
        await waitUntil("the stopped loop to leave its sleep") { sleeper.parked == 0 }
        sleeper.release()
        client.releaseRelatedFutures()
        await waitUntil("the in-flight read to land") { vm.relatedFutures?.boxScore?["read"]?["n"] == 2 }
        try? await Task.sleep(nanoseconds: 20_000_000)
        XCTAssertEqual(client.detailCount, base + 1, "a stopped page ran another slot")
        XCTAssertEqual(client.relatedFuturesCount, 2)
        XCTAssertEqual(sleeper.parked, 0, "a stopped page started another loop")
    }
}
