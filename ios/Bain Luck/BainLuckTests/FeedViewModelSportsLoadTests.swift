import XCTest
@testable import Bain_Luck

/// L2-207 / #1480 — native **Sports** tab (`FeedViewModel.load()`) progressive
/// first-card critical path. The tab issues three requests (main fast
/// `mode=sports` feed, events-only backfill, grouped futures); first paint must
/// be gated on the MAIN response only, with the siblings merging in
/// independently — never blanking or reordering already-visible cards, never
/// turning sibling content into a false full-success when the main feed fails.
///
/// These drive the view model through the `SportsFeedProviding` seam with
/// deterministic, individually-gateable fakes and a capturing telemetry sink, so
/// request routing/shape, progressive render, delayed siblings, cancellation of
/// superseded loads, refresh, and per-stage milestone emission are all provable —
/// none of which a pure predicate test can reach.
@MainActor
final class FeedViewModelSportsLoadTests: XCTestCase {

    // MARK: - Async gate

    /// A manually-releasable async gate. `wait()` suspends until `open()` (or
    /// returns immediately if already opened).
    private nonisolated final class AsyncGate: @unchecked Sendable {
        private let lock = NSLock()
        private var opened = false
        private var conts: [CheckedContinuation<Void, Never>] = []

        func open() {
            let waiting: [CheckedContinuation<Void, Never>] = lock.withLock {
                opened = true
                let c = conts
                conts = []
                return c
            }
            waiting.forEach { $0.resume() }
        }

        func wait() async {
            await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                let resumeNow: Bool = lock.withLock {
                    if opened { return true }
                    conts.append(cont)
                    return false
                }
                if resumeNow { cont.resume() }
            }
        }
    }

    // MARK: - Fakes

    /// Records each request and returns scripted replies. Any of the three methods
    /// can be independently gated so a delayed/failed sibling is deterministic.
    private nonisolated final class FakeSportsClient: SportsFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var _mainCalls = 0
        private var _backfillLimits: [Int] = []
        private var _groupedLimits: [Int] = []

        private let mainReply: Result<FeedResponse, Error>
        private let backfillReply: Result<FeedResponse, Error>
        private let groupedReply: Result<GroupedFeedResponse, Error>

        let mainGate: AsyncGate?
        let backfillGate: AsyncGate?
        let groupedGate: AsyncGate?

        init(
            main: Result<FeedResponse, Error>,
            backfill: Result<FeedResponse, Error>,
            grouped: Result<GroupedFeedResponse, Error>,
            mainGate: AsyncGate? = nil,
            backfillGate: AsyncGate? = nil,
            groupedGate: AsyncGate? = nil
        ) {
            self.mainReply = main
            self.backfillReply = backfill
            self.groupedReply = grouped
            self.mainGate = mainGate
            self.backfillGate = backfillGate
            self.groupedGate = groupedGate
        }

        var mainCalls: Int { lock.withLock { _mainCalls } }
        var backfillLimits: [Int] { lock.withLock { _backfillLimits } }
        var groupedLimits: [Int] { lock.withLock { _groupedLimits } }

        nonisolated func fetchSportsFeed() async throws -> FeedResponse {
            lock.withLock { _mainCalls += 1 }
            if let mainGate { await mainGate.wait() }
            return try mainReply.get()
        }

        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            lock.withLock { _backfillLimits.append(limit) }
            if let backfillGate { await backfillGate.wait() }
            return try backfillReply.get()
        }

        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
            lock.withLock { _groupedLimits.append(limit) }
            if let groupedGate { await groupedGate.wait() }
            return try groupedReply.get()
        }
    }

    /// Main call #1 blocks on a gate and returns `first`; call #2+ returns
    /// `second` immediately. Backfill/grouped are always empty + immediate. Proves
    /// a superseded (older) load's late main response is discarded.
    private nonisolated final class SupersedeClient: SportsFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var callCount = 0
        private var gate: CheckedContinuation<Void, Never>?
        private var opened = false
        private let first: FeedResponse
        private let second: FeedResponse
        private let emptyEvents: FeedResponse
        private let emptyGrouped: GroupedFeedResponse

        init(first: FeedResponse, second: FeedResponse, emptyEvents: FeedResponse, emptyGrouped: GroupedFeedResponse) {
            self.first = first
            self.second = second
            self.emptyEvents = emptyEvents
            self.emptyGrouped = emptyGrouped
        }

        func openGate() {
            lock.withLock {
                opened = true
                gate?.resume()
                gate = nil
            }
        }

        nonisolated func fetchSportsFeed() async throws -> FeedResponse {
            let n = lock.withLock { () -> Int in callCount += 1; return callCount }
            if n == 1 {
                await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                    lock.withLock {
                        if opened { cont.resume() } else { gate = cont }
                    }
                }
                return first
            }
            return second
        }

        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { emptyEvents }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { emptyGrouped }
    }

    private nonisolated final class TelemetrySink: @unchecked Sendable {
        private let lock = NSLock()
        private var events: [SportsFeedStage] = []
        func record(_ e: SportsFeedStage) { lock.withLock { events.append(e) } }
        var all: [SportsFeedStage] { lock.withLock { events } }
        var kinds: [SportsFeedStage.Kind] { lock.withLock { events.map(\.kind) } }
        func stage(_ k: SportsFeedStage.Kind) -> SportsFeedStage? { lock.withLock { events.first { $0.kind == k } } }
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func eventJSON(_ id: Int, status: String) -> String {
        """
        {"type":"event","score":90,"data":{"id":\(id),"home_team":"Home \(id)","away_team":"Away \(id)","status":"\(status)"}}
        """
    }

    private func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":88,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"basketball","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }

    private func feed(_ itemJSONs: [String], total: Int = 9999) throws -> FeedResponse {
        let json = """
        {"items":[\(itemJSONs.joined(separator: ","))],"total":\(total),"limit":50,"offset":0,"has_more":true}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func groupedResponse(_ count: Int) throws -> GroupedFeedResponse {
        let items = (0..<count).map { i in
            """
            {"type":"playoff_progression","group_key":"g\(i)","entity_name":"Team \(i)","stages":[{"id":\(i),"label":"Round 1","probability":0.5,"status":"active"}]}
            """
        }
        let json = """
        {"feed":[\(items.joined(separator: ","))],"total":\(count),"limit":20,"offset":0}
        """
        return try Self.decoder().decode(GroupedFeedResponse.self, from: Data(json.utf8))
    }

    private func emptyFeed() throws -> FeedResponse { try feed([]) }
    private func emptyGrouped() throws -> GroupedFeedResponse { try groupedResponse(0) }

    /// Poll the main actor until `cond` holds (or a generous cap), yielding so the
    /// in-flight `load()` task can make progress on the single-threaded actor.
    private func waitUntil(_ cond: () -> Bool, cap: Int = 5000) async {
        var n = 0
        while !cond() && n < cap { await Task.yield(); n += 1 }
    }

    // MARK: - Item 1: request shape / routing

    func testMainTabRequestsSportsContractPlusEventBackfillAndGrouped() async throws {
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled"), futuresJSON(10)])),
            backfill: .success(try emptyFeed()),
            grouped: .success(try emptyGrouped())
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertEqual(fake.mainCalls, 1, "main tab routes through the fast sports contract (mode=sports)")
        XCTAssertEqual(fake.backfillLimits, [FeedViewModel.supplementalEventLimit],
                       "events-only backfill requested at the 200-event limit")
        XCTAssertEqual(fake.groupedLimits, [FeedViewModel.groupedFeedLimit],
                       "grouped futures requested at the 20 limit")
        XCTAssertFalse(vm.loading)
        XCTAssertNil(vm.error)
    }

    // MARK: - Item 1: progressive render — main gates first paint

    func testMainSuccessRemovesSkeletonWithoutWaitingForSiblings() async throws {
        let backfillGate = AsyncGate()
        let groupedGate = AsyncGate()
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
            grouped: .success(try groupedResponse(2)),
            backfillGate: backfillGate,
            groupedGate: groupedGate
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        let task = Task { await vm.load() }

        // Main resolves first; skeleton comes down while BOTH siblings are gated.
        await waitUntil { !vm.loading && vm.items.count == 1 }
        XCTAssertFalse(vm.loading, "skeleton removed on main success")
        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "only the main feed is on screen")
        XCTAssertTrue(vm.groupedItems.isEmpty, "grouped has NOT merged yet")

        backfillGate.open()
        groupedGate.open()
        await task.value

        XCTAssertEqual(vm.items.map(\.id), ["event-1", "event-2"], "backfill merged after first paint")
        XCTAssertEqual(vm.groupedItems.count, 2, "grouped merged after first paint")
    }

    /// Grouped must not be held hostage behind a slow 200-event backfill.
    func testGroupedPublishesIndependentlyOfSlowBackfill() async throws {
        let backfillGate = AsyncGate()  // backfill stays slow
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
            grouped: .success(try groupedResponse(3)),  // grouped is fast (ungated)
            backfillGate: backfillGate
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        let task = Task { await vm.load() }

        // Grouped should land while the backfill is still blocked.
        await waitUntil { vm.groupedItems.count == 3 }
        XCTAssertEqual(vm.groupedItems.count, 3, "grouped published without waiting on the backfill")
        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "backfill not yet merged")

        backfillGate.open()
        await task.value
        XCTAssertEqual(vm.items.map(\.id), ["event-1", "event-2"])
    }

    // MARK: - Item 1: backfill dedup, events-only, main order preserved

    func testBackfillIsEventsOnlyDedupedAndPreservesMainOrder() async throws {
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled"), futuresJSON(10)])),
            backfill: .success(try feed([
                eventJSON(1, status: "scheduled"),   // dup of main → excluded
                eventJSON(3, status: "live"),         // live → excluded
                eventJSON(2, status: "scheduled"),    // new non-live event → appended
                futuresJSON(11),                       // futures in backfill → excluded (events-only)
            ])),
            grouped: .success(try emptyGrouped())
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertEqual(vm.items.map(\.id), ["event-1", "futures-10", "event-2"],
                       "main order preserved; only the new non-live event appended; dup/live/futures excluded")
    }

    // MARK: - Item 1: main failure is retryable, no false success

    func testMainFailureIsRetryableAndDoesNotPublishSiblingContent() async throws {
        let fake = FakeSportsClient(
            main: .failure(URLError(.timedOut)),
            backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
            grouped: .success(try groupedResponse(2))
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertNotNil(vm.error, "main failure surfaces a retryable error")
        XCTAssertTrue(vm.items.isEmpty, "sibling content is NOT published as a false full-success")
        XCTAssertTrue(vm.groupedItems.isEmpty)
        XCTAssertFalse(vm.loading)
    }

    // MARK: - Item 1: grouped failure honest + non-fatal

    func testGroupedFailureIsNonFatal() async throws {
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
            grouped: .failure(URLError(.badServerResponse))
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertNil(vm.error, "grouped failure never fails the tab")
        XCTAssertEqual(vm.items.map(\.id), ["event-1", "event-2"], "main + backfill still render")
        XCTAssertTrue(vm.groupedItems.isEmpty)
        XCTAssertFalse(vm.loading)
    }

    /// Backfill failure is also non-fatal — the main feed remains.
    func testBackfillFailureIsNonFatal() async throws {
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .failure(URLError(.badServerResponse)),
            grouped: .success(try groupedResponse(1))
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "main feed intact despite backfill miss")
        XCTAssertEqual(vm.groupedItems.count, 1)
    }

    // MARK: - Superseded / refresh safety

    func testSupersededLoadDiscardsLateMainResponse() async throws {
        let a = try feed([eventJSON(1, status: "scheduled")])
        let b = try feed([eventJSON(9, status: "scheduled")])
        let fake = SupersedeClient(
            first: a, second: b,
            emptyEvents: try emptyFeed(), emptyGrouped: try emptyGrouped()
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        async let loadA: Void = vm.load()   // call 1 — main blocks on the gate
        await Task.yield()
        await vm.load()                      // call 2 — publishes B, advances generation

        XCTAssertEqual(vm.items.map(\.id), ["event-9"], "newer load B published")

        fake.openGate()                      // A's late main returns now
        await loadA

        XCTAssertEqual(vm.items.map(\.id), ["event-9"],
                       "superseded load A's late response discarded — no clobber/blank/reorder")
    }

    func testRefreshReplacesFeedInPlaceWithoutSkeleton() async throws {
        let fake1 = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .success(try emptyFeed()),
            grouped: .success(try emptyGrouped())
        )
        let vm = FeedViewModel(client: fake1, telemetry: nil, autoRefreshEnabled: false)
        await vm.load()
        XCTAssertEqual(vm.items.map(\.id), ["event-1"])
        XCTAssertFalse(vm.loading)

        // A refresh (items already present) must not re-raise the skeleton.
        await vm.load()
        XCTAssertFalse(vm.loading, "refresh keeps content on screen, no skeleton flash")
    }

    // MARK: - Item 2: telemetry

    func testTelemetryEmitsThreeStagesWithFirstCardOnlyOnMain() async throws {
        let sink = TelemetrySink()
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
            grouped: .success(try groupedResponse(1))
        )
        let vm = FeedViewModel(client: fake, telemetry: { sink.record($0) }, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertEqual(Set(sink.kinds), Set([.main, .eventsBackfill, .grouped]),
                       "all three stages report")
        let main = try XCTUnwrap(sink.stage(.main))
        XCTAssertTrue(main.success)
        XCTAssertNotNil(main.firstRealCardMs, "first-real-card attributed to the main stage")
        XCTAssertGreaterThanOrEqual(main.dataReadyMs, 0)
        XCTAssertNil(try XCTUnwrap(sink.stage(.eventsBackfill)).firstRealCardMs,
                     "a sibling can never be mistaken for first paint")
        XCTAssertNil(try XCTUnwrap(sink.stage(.grouped)).firstRealCardMs)
    }

    func testTelemetryMainFailureEmitsOnlyFailedMainStage() async throws {
        let sink = TelemetrySink()
        let fake = FakeSportsClient(
            main: .failure(URLError(.timedOut)),
            backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
            grouped: .success(try groupedResponse(1))
        )
        let vm = FeedViewModel(client: fake, telemetry: { sink.record($0) }, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertEqual(sink.kinds, [.main], "no sibling stages emit when main fails")
        XCTAssertFalse(try XCTUnwrap(sink.stage(.main)).success)
    }

    func testTelemetryReportsSiblingMissHonestly() async throws {
        let sink = TelemetrySink()
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .failure(URLError(.badServerResponse)),
            grouped: .failure(URLError(.badServerResponse))
        )
        let vm = FeedViewModel(client: fake, telemetry: { sink.record($0) }, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertTrue(try XCTUnwrap(sink.stage(.main)).success)
        XCTAssertFalse(try XCTUnwrap(sink.stage(.eventsBackfill)).success, "backfill miss reported")
        XCTAssertFalse(try XCTUnwrap(sink.stage(.grouped)).success, "grouped miss reported")
    }
}
