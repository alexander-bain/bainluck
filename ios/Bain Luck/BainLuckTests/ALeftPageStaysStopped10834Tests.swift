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

    /// Like `CountingClient`, but every detail read after the first `free`
    /// parks until the test lets it land — with the detail, or with an error.
    /// Held reads land in the order they parked.
    private nonisolated final class HeldClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        enum Landing { case detail, failure }
        private let lock = NSLock()
        private let detail: EventDetail
        private var free: Int
        private var parkedSoFar = 0
        private var held = 0
        private var landings: [Landing] = []
        init(_ detail: EventDetail, free: Int) { self.detail = detail; self.free = free }
        var heldCount: Int { lock.withLock { held } }
        func land(_ landing: Landing) { lock.withLock { landings.append(landing) } }
        func fetchEvent(id: Int) async throws -> EventDetail {
            let ticket: Int? = lock.withLock {
                guard free == 0 else { free -= 1; return nil }
                held += 1
                parkedSoFar += 1
                return parkedSoFar - 1
            }
            guard let ticket else { return detail }
            while true {
                let landing: Landing? = lock.withLock {
                    guard landings.count > ticket else { return nil }
                    held -= 1
                    return landings[ticket]
                }
                switch landing {
                case .detail: return detail
                case .failure: throw Declined()
                case nil: try? await Task.sleep(nanoseconds: 200_000)
                }
            }
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// Answers a folded detail every time and holds the next history read until
    /// the test releases it. Counts the chart's catch-up reads
    /// (`fetchFreshEventHistory`, `rereadPricePair`'s) apart from a load's own.
    private nonisolated final class HistoryHeldClient: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        private let lock = NSLock()
        private let detail: EventDetail
        private let history: EventHistoryResponse
        private var holdNext = false
        private var released = false
        private var held = 0
        private var catchUps = 0
        init(detail: EventDetail, history: EventHistoryResponse) {
            self.detail = detail
            self.history = history
        }
        var heldCount: Int { lock.withLock { held } }
        var catchUpCount: Int { lock.withLock { catchUps } }
        func holdNextHistory() { lock.withLock { holdNext = true; released = false } }
        func releaseHistory() { lock.withLock { released = true } }
        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            let hold: Bool = lock.withLock {
                guard holdNext else { return false }
                holdNext = false
                held += 1
                return true
            }
            if hold {
                while !lock.withLock({ released }) { try? await Task.sleep(nanoseconds: 200_000) }
                lock.withLock { held -= 1 }
            }
            return history
        }
        func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            lock.withLock { catchUps += 1 }
            return history
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
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

    /// #10833's repair shape: the headline holds fold revision 14 at 40%,
    /// and the history pins its right edge at 60% on revision 12 — a chart
    /// that has to catch up.
    private func foldedAhead() throws -> (EventDetail, EventHistoryResponse) {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let detail = try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Denver Broncos","away_team":"Los Angeles Rams","status":"live",
         "home_score":16,"away_score":0,
         "espn":{"game_clock":"11:13","period":"3"},
         "current_odds":{"home_probability":0.4,"away_probability":0.6,
           "home_rendered_percent":40,"away_rendered_percent":60},
         "hero_probability":0.4,"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-09-28T02:19:00Z",
         "blend_fold_revision":{"4242":14},
         "win_probability_sources":{"polymarket":{"value":0.4,"updated_at":"2026-09-28T02:19:00Z"}}}
        """.utf8))
        let history = try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Denver Broncos","away_team":"Los Angeles Rams","status":"live","history":[],
         "aggregate_line":[{"timestamp":"2026-09-28T02:00:00Z","home_probability":0.55},
                           {"timestamp":"2026-09-28T02:19:00Z","home_probability":0.6}],
         "blend_edge_pinned":true,"blend_edge_fold_revision":{"4242":12}}
        """.utf8))
        return (detail, history)
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

    // MARK: - A read that lands after the reader left

    /// Nothing the test held may outlive it: a parked read here spins forever.
    private func assertNoHeldRead(_ client: HeldClient, _ note: String) async {
        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(client.heldCount, 0, "a held read outlived the test (\(note))")
    }

    /// A page with a held client, its stream handles and its sleeper.
    private func heldPage(free: Int)
        -> (EventDetailViewModel, HeldClient, Sleeper, () -> [FakeHandle]) {
        var handles: [FakeHandle] = []
        let client = HeldClient(try! live(), free: free)
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
        return (vm, client, sleeper, { handles })
    }

    /// The page is opened and left before its detail answers. When the detail
    /// lands — with the game, or with an error (a cancelled read takes the
    /// same catch) — the page keeps what it read and arms nothing: no loop,
    /// no plan, no stream.
    func testALoadLandingAfterTheReaderLeftArmsNothing() async throws {
        for landing in [HeldClient.Landing.detail, .failure] {
            let (vm, client, sleeper, handles) = heldPage(free: 0)
            let open = Task { @MainActor in await vm.load() }
            await waitUntil("the opening detail to be in flight (\(landing))") { client.heldCount == 1 }

            vm.stopRefresh()
            client.land(landing)
            await open.value

            if landing == .detail {
                XCTAssertEqual(vm.event?.id, 4242, "the late detail was dropped, not just fenced")
            }
            XCTAssertFalse(vm.isAutoRefreshing, "a load that landed after the reader left re-armed the poll (\(landing))")
            XCTAssertNil(vm.currentRefreshPlan, "a left page names a cadence (\(landing))")
            XCTAssertEqual(handles().count, 0, "a left page opened a stream (\(landing))")
            try? await Task.sleep(nanoseconds: 30_000_000)
            XCTAssertEqual(sleeper.parked, 0, "a left page parked a loop (\(landing))")
            await assertNoHeldRead(client, "load \(landing)")
        }
    }

    /// The ordinary game-state slot of a delivering page is mid-read when the
    /// reader leaves. When it lands it re-plans nothing.
    func testAGameStateReadLandingAfterTheReaderLeftArmsNothing() async throws {
        for landing in [HeldClient.Landing.detail, .failure] {
            let (vm, client, sleeper, handles) = heldPage(free: 1)
            await vm.load()
            deliver(handles()[0])
            await waitUntil("the delivering page to park on the push cadence (\(landing))") {
                vm.currentRefreshPlan == .poll(every: EventRefreshPlan.livePushPollInterval)
                    && sleeper.parked == 1
            }
            XCTAssertGreaterThan(
                EventRefreshPlan.slots(for: .poll(every: EventRefreshPlan.livePushPollInterval)), 1,
                "the first push-cadence slot is no longer the game-state read"
            )

            XCTAssertEqual(client.heldCount, 0, "a read other than the slot's is parked (\(landing))")
            sleeper.release()
            await waitUntil("the game-state read to be in flight (\(landing))") { client.heldCount == 1 }
            vm.stopRefresh()
            client.land(landing)
            await waitUntil("the late read to land (\(landing))") { client.heldCount == 0 }
            try? await Task.sleep(nanoseconds: 30_000_000)

            XCTAssertFalse(vm.isAutoRefreshing, "a game-state read that landed after the reader left re-armed the poll (\(landing))")
            XCTAssertNil(vm.currentRefreshPlan, "a left page names a cadence (\(landing))")
            XCTAssertEqual(handles().count, 1, "a left page opened another stream (\(landing))")
            XCTAssertEqual(sleeper.parked, 0, "a left page parked a loop (\(landing))")
            await assertNoHeldRead(client, "game state \(landing)")
        }
    }

    /// The reader leaves and comes back while the first visit's detail is still
    /// out. The return plans one loop and one stream; the old read landing after
    /// it adds neither.
    func testAReturnWhileTheOldReadIsOutStillArmsOneLoop() async throws {
        let (vm, client, sleeper, handles) = heldPage(free: 0)
        defer { vm.stopRefresh() }
        let first = Task { @MainActor in await vm.load() }
        await waitUntil("the first visit's detail to be in flight") { client.heldCount == 1 }
        vm.stopRefresh()

        let back = Task { @MainActor in await vm.load() }
        await waitUntil("the return's detail to be in flight") { client.heldCount == 2 }
        client.land(.detail)   // the FIRST visit's read lands first
        await first.value
        XCTAssertNil(vm.currentRefreshPlan, "the old visit's read planned the page before the return did")
        XCTAssertEqual(handles().count, 0)

        client.land(.detail)
        await back.value
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePollInterval))
        XCTAssertEqual(handles().count, 1, "the return opened no stream, or two")
        await waitUntil("the returned page to park one loop") { sleeper.parked == 1 }
        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(sleeper.parked, 1, "a duplicate loop is parked")
        await assertNoHeldRead(client, "return")
    }

    /// A page with `HistoryHeldClient` on #10833's repair shape.
    private func historyHeldPage() throws
        -> (EventDetailViewModel, HistoryHeldClient, Sleeper, () -> [FakeHandle]) {
        var handles: [FakeHandle] = []
        let (detail, history) = try foldedAhead()
        let client = HistoryHeldClient(detail: detail, history: history)
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
        return (vm, client, sleeper, { handles })
    }

    /// The page opens, takes its detail and is left while its history is
    /// still out. The history lands on a chart that needs catching up: the
    /// page keeps the history but asks for no repair — the repair's pair would
    /// re-plan a page nobody is looking at. Coming back to the same fold, the
    /// return's own check still asks for the repair, exactly once.
    func testAHistoryLandingAfterTheReaderLeftStartsNoRepair() async throws {
        let (vm, client, sleeper, handles) = try historyHeldPage()
        defer { vm.stopRefresh() }
        client.holdNextHistory()
        let open = Task { @MainActor in await vm.load() }
        await waitUntil("the opening detail to plan and its history to be in flight") {
            vm.currentRefreshPlan != nil && client.heldCount == 1
        }
        XCTAssertEqual(handles().count, 1)

        vm.stopRefresh()
        client.releaseHistory()
        await open.value
        for _ in 0..<50 { await Task.yield() }
        try? await Task.sleep(nanoseconds: 30_000_000)

        XCTAssertNotNil(vm.history, "the late history was dropped, not just fenced")
        XCTAssertEqual(client.catchUpCount, 0, "a history that landed after the reader left asked for a chart repair")
        XCTAssertFalse(vm.isAutoRefreshing, "a late history's repair re-armed the poll on a left page")
        XCTAssertNil(vm.currentRefreshPlan, "a left page names a cadence")
        XCTAssertEqual(handles().count, 1, "a late history's repair opened a stream on a left page")
        XCTAssertEqual(sleeper.parked, 0, "a left page parked a loop")

        await vm.load()
        await waitUntil("the return to ask the chart to catch up") { client.catchUpCount == 1 }
        for _ in 0..<50 { await Task.yield() }
        XCTAssertEqual(client.catchUpCount, 1, "the return's repair was not asked exactly once")
        XCTAssertEqual(handles().count, 2, "the return opened no stream, or two")
        await waitUntil("the returned page to park one loop") { sleeper.parked == 1 }
        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(sleeper.parked, 1, "a duplicate loop is parked")
        XCTAssertEqual(client.heldCount, 0, "a held read outlived the test")
    }

    /// The reader leaves and comes back while the first visit's history is
    /// still out; the return joins that read. When it lands, the left visit's
    /// copy asks for nothing and the return's asks for the repair once — on
    /// one stream and one loop.
    func testAReturnJoiningTheLeftVisitsHistoryStillRepairsTheChart() async throws {
        let (vm, client, sleeper, handles) = try historyHeldPage()
        defer { vm.stopRefresh() }
        client.holdNextHistory()
        let first = Task { @MainActor in await vm.load() }
        await waitUntil("the first visit's history to be in flight") {
            vm.currentRefreshPlan != nil && client.heldCount == 1
        }
        vm.stopRefresh()

        let back = Task { @MainActor in await vm.load() }
        await waitUntil("the return to take its detail and plan") { vm.currentRefreshPlan != nil }
        XCTAssertEqual(client.heldCount, 1, "the return stacked a second history read")
        XCTAssertEqual(client.catchUpCount, 0)

        client.releaseHistory()
        await first.value
        await back.value
        await waitUntil("the return to ask the chart to catch up") { client.catchUpCount == 1 }
        for _ in 0..<50 { await Task.yield() }
        try? await Task.sleep(nanoseconds: 30_000_000)
        XCTAssertEqual(client.catchUpCount, 1, "the repair was not asked exactly once")
        XCTAssertEqual(handles().count, 2, "the return opened no stream, or two")
        XCTAssertEqual(sleeper.parked, 1, "the returned page parked no loop, or two")
        XCTAssertEqual(client.heldCount, 0, "a held read outlived the test")
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
