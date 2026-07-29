import XCTest
@testable import Bain_Luck

/// L2-211 / #1480 — native **Sports** tab lifecycle + render telemetry contract
/// (C73), translated from C74's `native-sports-lifecycle/v1` fixture corpus
/// (`backend/scripts/evals/native_sports_lifecycle_fixtures.json`). Each test name
/// preserves the fenced fixture scenario ID.
///
/// Two properties are proven here that a pure predicate test cannot reach:
///  1. **One owned load rail** — the view `.task`, pull-refresh, Retry, and the live
///     auto-refresh timer all route through `startLoad()`, which cancels AND joins
///     the prior owned load before installing its replacement, so at most one load
///     executes and a superseded/disappeared load's work is TERMINATED (its main
///     fetch + siblings cancelled), not merely discarded by the generation guard.
///     Optional sibling work is deadline-bounded so a cancellation-IGNORING client
///     can never keep the rail alive.
///  2. **Immutable render token** — first-render telemetry consumes a frozen
///     `SportsRenderGeneration` (generation, started_at, provenance, item_count)
///     stamped at data-ready, keyed by generation id, so a same-id refresh emits its
///     new generation without an `onAppear` refire and a later merge never changes
///     the reported count.
@MainActor
final class FeedViewModelSportsLifecycleTests: XCTestCase {

    // MARK: - Async gates

    /// Manually-releasable gate whose `wait()` IGNORES cancellation — models a
    /// cancellation-ignoring client (the adversarial sibling in
    /// `timer_cancellation_ignoring_sibling` / `discard_only_claimed_cancelled`).
    private nonisolated final class AsyncGate: @unchecked Sendable {
        private let lock = NSLock()
        private var opened = false
        private var conts: [CheckedContinuation<Void, Never>] = []
        func open() {
            let waiting: [CheckedContinuation<Void, Never>] = lock.withLock {
                opened = true; let c = conts; conts = []; return c
            }
            waiting.forEach { $0.resume() }
        }
        func wait() async {
            await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                let now: Bool = lock.withLock {
                    if opened { return true }
                    conts.append(cont); return false
                }
                if now { cont.resume() }
            }
        }
    }

    // MARK: - Fakes

    /// Main feed that waits COOPERATIVELY: it polls `Task.isCancelled` while blocked,
    /// so a superseding `startLoad()` (which cancels the owned task) actually
    /// terminates it — recording that it observed cancellation. Distinguishes real
    /// termination from a mere generation discard.
    private nonisolated final class CooperativeMainClient: SportsFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var opened = false
        private var _mainCalls = 0
        private var _mainCancelled = 0
        private var _activeMain = 0
        private var _maxActiveMain = 0
        private let replies: [FeedResponse]
        private let events: FeedResponse
        private let grouped: GroupedFeedResponse

        init(replies: [FeedResponse], events: FeedResponse, grouped: GroupedFeedResponse) {
            self.replies = replies; self.events = events; self.grouped = grouped
        }

        func open() { lock.withLock { opened = true } }
        var mainCalls: Int { lock.withLock { _mainCalls } }
        var mainCancelled: Int { lock.withLock { _mainCancelled } }
        var maxActiveMain: Int { lock.withLock { _maxActiveMain } }

        nonisolated func fetchSportsFeed() async throws -> FeedResponse {
            let n = lock.withLock { () -> Int in
                _mainCalls += 1; _activeMain += 1
                _maxActiveMain = max(_maxActiveMain, _activeMain)
                return _mainCalls
            }
            defer { lock.withLock { _activeMain -= 1 } }
            while !(lock.withLock { opened }) {
                if Task.isCancelled {
                    lock.withLock { _mainCancelled += 1 }
                    throw CancellationError()
                }
                await Task.yield()
            }
            return replies[min(n - 1, replies.count - 1)]
        }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { events }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    /// Main returns immediately; the BACKFILL sibling blocks on a gate that ignores
    /// cancellation and is never opened — the adversarial cancellation-ignoring
    /// sibling. Grouped returns immediately.
    private nonisolated final class IgnoringSiblingClient: SportsFeedProviding, @unchecked Sendable {
        let neverOpens = AsyncGate()
        private let main: FeedResponse
        private let grouped: GroupedFeedResponse
        init(main: FeedResponse, grouped: GroupedFeedResponse) { self.main = main; self.grouped = grouped }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse { main }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            await neverOpens.wait()                 // ignores cancellation, never returns
            return try FeedResponseFixtures.empty()
        }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    /// Fully-scripted immediate client: main replies in order (clamped), fixed
    /// siblings. Immediate — for the render-token / generation scenarios.
    private nonisolated final class ScriptedClient: SportsFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var index = 0
        private let mains: [FeedResponse]
        private let events: FeedResponse
        private let grouped: GroupedFeedResponse
        init(mains: [FeedResponse], events: FeedResponse, grouped: GroupedFeedResponse) {
            self.mains = mains; self.events = events; self.grouped = grouped
        }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse {
            lock.withLock { let r = mains[min(index, mains.count - 1)]; index += 1; return r }
        }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { events }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    /// Main + grouped immediate; backfill gated (slow, cooperative-agnostic) — for
    /// `slow_backfill_grouped_first`.
    private nonisolated final class SlowBackfillClient: SportsFeedProviding, @unchecked Sendable {
        let backfillGate = AsyncGate()
        private let main: FeedResponse
        private let events: FeedResponse
        private let grouped: GroupedFeedResponse
        init(main: FeedResponse, events: FeedResponse, grouped: GroupedFeedResponse) {
            self.main = main; self.events = events; self.grouped = grouped
        }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse { main }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            await backfillGate.wait(); return events
        }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    private nonisolated final class TelemetrySink: @unchecked Sendable {
        private let lock = NSLock()
        private var events: [SportsFeedStage] = []
        func record(_ e: SportsFeedStage) { lock.withLock { events.append(e) } }
        var kinds: [SportsFeedStage.Kind] { lock.withLock { events.map(\.kind) } }
        func stage(_ k: SportsFeedStage.Kind) -> SportsFeedStage? { lock.withLock { events.first { $0.kind == k } } }
    }

    // MARK: - Fixtures

    private func feed(_ ids: [Int], statuses: [String]? = nil, total: Int = 9999) throws -> FeedResponse {
        let s = statuses ?? Array(repeating: "scheduled", count: ids.count)
        let items = zip(ids, s).map { id, status in
            "{\"type\":\"event\",\"score\":90,\"data\":{\"id\":\(id),\"home_team\":\"H\(id)\",\"away_team\":\"A\(id)\",\"status\":\"\(status)\"}}"
        }
        return try FeedResponseFixtures.decode("{\"items\":[\(items.joined(separator: ","))],\"total\":\(total),\"limit\":50,\"offset\":0,\"has_more\":true}")
    }
    private func grouped(_ count: Int) throws -> GroupedFeedResponse {
        let items = (0..<count).map { i in
            "{\"type\":\"playoff_progression\",\"group_key\":\"g\(i)\",\"entity_name\":\"T\(i)\",\"stages\":[{\"id\":\(i),\"label\":\"R1\",\"probability\":0.5,\"status\":\"active\"}]}"
        }
        return try FeedResponseFixtures.decodeGrouped("{\"feed\":[\(items.joined(separator: ","))],\"total\":\(count),\"limit\":20,\"offset\":0}")
    }

    private func waitUntil(_ cond: () -> Bool, cap: Int = 20000) async {
        var n = 0
        while !cond() && n < cap { await Task.yield(); n += 1 }
    }

    /// Mirrors the view's generation-keyed emit guard: emits (returns the reported
    /// count) exactly once per render-generation id, reading the FROZEN token — never
    /// the live `vm.items.count`.
    @discardableResult
    private func emit(_ vm: FeedViewModel, lastEmitted: inout Int?) -> Int? {
        guard let d = SportsFirstRender.generationDecision(
            generation: vm.firstRenderGeneration, lastEmittedGenerationId: lastEmitted, now: Date()
        ) else { return nil }
        lastEmitted = d.generation.generation
        return d.generation.itemCount
    }

    // MARK: - Accepted scenarios

    /// swiftui_task_main_success
    func test_swiftui_task_main_success() async throws {
        let client = ScriptedClient(mains: [try feed([1, 2, 3, 4])], events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        await vm.startLoad()
        XCTAssertEqual(vm.items.count, 4)
        let token = try XCTUnwrap(vm.firstRenderGeneration, "successful non-empty main stamps a render token")
        XCTAssertEqual(token.itemCount, 4)
        XCTAssertEqual(token.provenance, "network")
        var last: Int? = nil
        XCTAssertEqual(emit(vm, lastEmitted: &last), 4, "first render emits once with the frozen count")
    }

    /// timer_load_disappears — cancel_and_join_on_disappear, no publication, no token.
    func test_timer_load_disappears() async throws {
        let client = CooperativeMainClient(replies: [try feed([1])], events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        let task = Task { await vm.startLoad() }
        await waitUntil { client.mainCalls == 1 }         // main in flight, blocked
        vm.viewDidStop()                                   // view disappears
        await task.value
        XCTAssertEqual(client.mainCancelled, 1, "the in-flight timer/main load is terminated, not just discarded")
        XCTAssertTrue(vm.items.isEmpty, "no late publication after disappearance")
        XCTAssertNil(vm.firstRenderGeneration, "no render token for a cancelled load")
        XCTAssertFalse(vm.refreshArmed, "refresh stopped on disappear")
    }

    /// timer_cancellation_ignoring_sibling — deadline_then_join.
    func test_timer_cancellation_ignoring_sibling() async throws {
        let client = IgnoringSiblingClient(main: try feed([1, 2]), grouped: try grouped(1))
        // Short sibling deadline so the runaway backfill cannot keep the rail alive.
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false, siblingDeadline: 0.05)
        // If the load did not terminate at the deadline, this would hang forever.
        await vm.startLoad()
        XCTAssertEqual(vm.items.map(\.id), ["event-1", "event-2"], "main published; load terminated at the sibling deadline")
        XCTAssertEqual(vm.groupedItems.count, 1, "the cooperative grouped sibling still merged")
    }

    /// pull_refresh_same_id — generation_keyed, requires_onappear_refire == false.
    func test_pull_refresh_same_id() async throws {
        let client = ScriptedClient(
            mains: [try feed([1, 2, 3, 4]), try feed([1, 2, 3, 4])],   // SAME ids on refresh
            events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        var last: Int? = nil
        await vm.startLoad()
        let g1 = try XCTUnwrap(vm.firstRenderGeneration).generation
        XCTAssertEqual(emit(vm, lastEmitted: &last), 4, "first render emits for generation 1")
        await vm.startLoad()                                // pull-refresh, identical ids
        let g2 = try XCTUnwrap(vm.firstRenderGeneration).generation
        XCTAssertGreaterThan(g2, g1, "the refresh stamps a NEW render generation even with identical card ids")
        XCTAssertEqual(emit(vm, lastEmitted: &last), 4,
                       "the new generation emits without needing an onAppear refire for the retained rows")
    }

    /// refresh_different_id_replacement.
    func test_refresh_different_id_replacement() async throws {
        let client = ScriptedClient(
            mains: [try feed([1, 2, 3]), try feed([10, 11, 12, 13, 14, 15])],
            events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        var last: Int? = nil
        await vm.startLoad()
        XCTAssertEqual(emit(vm, lastEmitted: &last), 3)
        await vm.startLoad()
        XCTAssertEqual(vm.items.count, 6, "different-id replacement swaps the feed")
        XCTAssertEqual(emit(vm, lastEmitted: &last), 6, "the replacement generation emits with its own frozen count")
    }

    /// empty_main — no token, refresh not_armed, data-ready still emitted.
    func test_empty_main() async throws {
        let sink = TelemetrySink()
        let client = ScriptedClient(mains: [try FeedResponseFixtures.empty()], events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: { sink.record($0) }, autoRefreshEnabled: true)
        await vm.startLoad()
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertNil(vm.firstRenderGeneration, "empty successful main stamps NO render token")
        var last: Int? = nil
        XCTAssertNil(emit(vm, lastEmitted: &last), "no first-card render event for an empty main")
        XCTAssertTrue(try XCTUnwrap(sink.stage(.main)).success, "data-ready main stage still reported")
        XCTAssertFalse(vm.refreshArmed, "no live games → refresh not armed")
    }

    /// superseded_load — cancel_and_join_before_replacement.
    func test_superseded_load() async throws {
        let client = CooperativeMainClient(
            replies: [try feed([1]), try feed([2, 3, 4])],
            events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        let first = Task { await vm.startLoad() }           // blocks on gate
        await waitUntil { client.mainCalls == 1 }
        let second = Task { await vm.startLoad() }           // supersede: cancel + join first
        await waitUntil { client.mainCancelled == 1 }        // first terminated
        client.open()                                        // let the second main resolve
        await first.value; await second.value
        XCTAssertEqual(vm.items.map(\.id), ["event-2", "event-3", "event-4"], "only the superseding load publishes")
        XCTAssertEqual(client.maxActiveMain, 1, "at most one owned load executes at a time")
    }

    /// slow_backfill_grouped_first — grouped publishes before a slow backfill.
    func test_slow_backfill_grouped_first() async throws {
        let client = SlowBackfillClient(main: try feed([1]), events: try feed([2]), grouped: try grouped(3))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        let task = Task { await vm.startLoad() }
        await waitUntil { vm.groupedItems.count == 3 }
        XCTAssertEqual(vm.groupedItems.count, 3, "grouped merged while the backfill is still blocked")
        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "backfill not yet merged")
        XCTAssertEqual(try XCTUnwrap(vm.firstRenderGeneration).itemCount, 1, "render token frozen at the main count")
        client.backfillGate.open()
        await task.value
        XCTAssertEqual(vm.items.map(\.id), ["event-1", "event-2"])
    }

    /// navigation_reappearance_new_generation — viewDidStop then reappearance loads.
    func test_navigation_reappearance_new_generation() async throws {
        let client = ScriptedClient(mains: [try feed([1, 2]), try feed([3, 4, 5])],
                                    events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        await vm.startLoad()
        let g1 = try XCTUnwrap(vm.firstRenderGeneration).generation
        vm.viewDidStop()                                    // navigate away
        vm.viewDidStart()                                   // navigate back
        await vm.startLoad()                                // reappearance load
        let g2 = try XCTUnwrap(vm.firstRenderGeneration).generation
        XCTAssertGreaterThan(g2, g1, "reappearance produces a NEW render generation")
        XCTAssertEqual(vm.items.map(\.id), ["event-3", "event-4", "event-5"], "reappearance load succeeds after a prior stop")
    }

    /// rapid_generations_latest_only.
    func test_rapid_generations_latest_only() async throws {
        let client = CooperativeMainClient(
            replies: [try feed([1]), try feed([2]), try feed([3]), try feed([4, 5])],
            events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        var tasks: [Task<Void, Never>] = []
        for _ in 0..<4 { tasks.append(Task { await vm.startLoad() }); await Task.yield() }
        client.open()
        for t in tasks { await t.value }
        XCTAssertEqual(client.maxActiveMain, 1, "rapid re-entry never runs overlapping owned loads")
        XCTAssertFalse(vm.items.isEmpty, "the latest generation publishes")
    }

    // MARK: - Rejected counterexamples (each fails for its declared reason pre-fix)

    /// discard_only_claimed_cancelled → work_not_terminated / discard_is_not_cancellation.
    /// The fix TERMINATES the superseded main (records cancellation); a discard-only
    /// design would leave `mainCancelled == 0`.
    func test_reject_discard_only_claimed_cancelled() async throws {
        let client = CooperativeMainClient(
            replies: [try feed([1]), try feed([2])],
            events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        let first = Task { await vm.startLoad() }
        await waitUntil { client.mainCalls == 1 }
        let second = Task { await vm.startLoad() }
        await waitUntil { client.mainCancelled == 1 }
        client.open()
        await first.value; await second.value
        XCTAssertEqual(client.mainCancelled, 1,
                       "supersession actually cancels the prior load's work — not a discard-only")
    }

    /// overlapping_owned_refreshes → multiple_active_owned_loads.
    func test_reject_overlapping_owned_refreshes() async throws {
        let client = CooperativeMainClient(
            replies: [try feed([1]), try feed([2]), try feed([3])],
            events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        let a = Task { await vm.startLoad() }; await Task.yield()
        let b = Task { await vm.startLoad() }; await Task.yield()
        let c = Task { await vm.startLoad() }; await Task.yield()
        client.open()
        await a.value; await b.value; await c.value
        XCTAssertEqual(client.maxActiveMain, 1, "never more than one active owned load")
    }

    /// mutable_count_old_token → render_generation_mismatch / mutable_render_count.
    /// The token's count is frozen at the main response; a later backfill grows
    /// `vm.items` but must NOT change what first-render reports.
    func test_reject_mutable_count_old_token() async throws {
        let client = ScriptedClient(
            mains: [try feed([1])],                          // main = 1 card
            events: try feed([2, 3, 4]),                     // backfill appends 3 more
            grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        await vm.startLoad()
        XCTAssertEqual(vm.items.count, 4, "backfill grew the live feed to 4")
        let token = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertEqual(token.itemCount, 1, "render token stays frozen at the main count, not the live 4")
        var last: Int? = nil
        XCTAssertEqual(emit(vm, lastEmitted: &last), 1, "first render reports the frozen count, never the live mutable one")
    }

    /// same_id_requires_onappear_again → onappear_refire_assumption.
    /// A same-id refresh must emit its new generation via the generation-keyed
    /// mechanism (an `onChange` on the token), NOT by assuming `onAppear` refires for
    /// the retained rows.
    func test_reject_same_id_requires_onappear_again() async throws {
        let client = ScriptedClient(
            mains: [try feed([1, 2]), try feed([1, 2])],     // identical ids
            events: try FeedResponseFixtures.empty(), grouped: try grouped(0))
        let vm = FeedViewModel(client: client, telemetry: nil, autoRefreshEnabled: false)
        var last: Int? = nil
        await vm.startLoad()
        XCTAssertEqual(emit(vm, lastEmitted: &last), 2)
        let tokenBefore = try XCTUnwrap(vm.firstRenderGeneration)
        await vm.startLoad()
        let tokenAfter = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertNotEqual(tokenBefore, tokenAfter,
                          "the token changes on a same-id refresh, so an onChange acknowledgement fires")
        XCTAssertEqual(emit(vm, lastEmitted: &last), 2,
                       "the new generation emits without an onAppear refire for the retained rows")
    }
}

/// Small JSON fixture helpers shared by the lifecycle tests.
enum FeedResponseFixtures {
    static func decoder() -> JSONDecoder {
        let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d
    }
    static func decode(_ json: String) throws -> FeedResponse {
        try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }
    static func decodeGrouped(_ json: String) throws -> GroupedFeedResponse {
        try decoder().decode(GroupedFeedResponse.self, from: Data(json.utf8))
    }
    static func empty() throws -> FeedResponse {
        try decode("{\"items\":[],\"total\":0,\"limit\":50,\"offset\":0,\"has_more\":false}")
    }
}
