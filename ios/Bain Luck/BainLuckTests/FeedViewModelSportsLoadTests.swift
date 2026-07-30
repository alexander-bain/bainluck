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

    /// Returns scripted main replies in order (clamping to the last), with fixed
    /// events/grouped siblings. Lets one view model be loaded repeatedly with a
    /// success→failure→success main sequence (refresh-failure lifecycle).
    private nonisolated final class ScriptedMainClient: SportsFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var index = 0
        private let mains: [Result<FeedResponse, Error>]
        private let events: FeedResponse
        private let grouped: GroupedFeedResponse
        init(mains: [Result<FeedResponse, Error>], events: FeedResponse, grouped: GroupedFeedResponse) {
            self.mains = mains; self.events = events; self.grouped = grouped
        }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse {
            let reply = lock.withLock { () -> Result<FeedResponse, Error> in
                let r = mains[min(index, mains.count - 1)]
                index += 1
                return r
            }
            return try reply.get()
        }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { events }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
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

    // MARK: - L2-215 Item 2: quiet cancellation parity (mirrors DiscoverViewModel L2-214)

    /// A cancellation WRAPPED as `APIError.networkError(NSURLErrorCancelled)` — what a
    /// torn-down `.task`/`.refreshable` or a superseded `startLoad()` actually throws
    /// on the Sports feed request.
    private func wrappedCancellation() -> APIError {
        APIError.networkError(underlying: NSError(domain: NSURLErrorDomain, code: NSURLErrorCancelled))
    }

    /// Cold load, every cancellation form: no error/retry screen, no `refreshFailed`,
    /// and NO `.main` failure stage is emitted (the load returns before `emit`).
    func testCancellationDuringColdMainIsQuietExitNoFailureTelemetry() async throws {
        let forms: [(String, Error)] = [
            ("raw CancellationError", CancellationError()),
            ("URLError.cancelled", URLError(.cancelled)),
            ("wrapped APIError.networkError(cancelled)", wrappedCancellation()),
        ]
        for (label, err) in forms {
            let sink = TelemetrySink()
            let fake = FakeSportsClient(
                main: .failure(err),
                backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
                grouped: .success(try groupedResponse(2))
            )
            let vm = FeedViewModel(client: fake, telemetry: { sink.record($0) }, autoRefreshEnabled: false)

            await vm.load()

            XCTAssertNil(vm.error, "\(label): cancellation is not surfaced as an error")
            XCTAssertFalse(vm.refreshFailed, "\(label): cancellation is not a refresh failure")
            XCTAssertTrue(vm.items.isEmpty, "\(label): sibling content is not published on a cancelled main")
            XCTAssertFalse(vm.loading, "\(label): loading resolved")
            XCTAssertNil(sink.stage(.main), "\(label): no false success:false main stage emitted")
        }
    }

    /// A genuine transport failure WRAPPED as `APIError.networkError` (non-cancel)
    /// must STILL surface — the predicate only swallows cancellation, not real errors.
    func testWrappedNonCancellationTransportFailureStillSurfaces() async throws {
        let sink = TelemetrySink()
        let realFailure = APIError.networkError(
            underlying: NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut))
        let fake = FakeSportsClient(
            main: .failure(realFailure),
            backfill: .success(try emptyFeed()),
            grouped: .success(try emptyGrouped())
        )
        let vm = FeedViewModel(client: fake, telemetry: { sink.record($0) }, autoRefreshEnabled: false)

        await vm.load()

        XCTAssertNotNil(vm.error, "a real wrapped transport failure is still surfaced")
        XCTAssertEqual(sink.stage(.main)?.success, false, "real failure still emits a success:false stage")
    }

    /// On a REFRESH (content already on screen), a wrapped cancellation preserves the
    /// existing cards and raises neither an error banner nor `refreshFailed` — the
    /// cached-content case, distinct from a genuine refresh failure.
    func testWrappedCancellationOnRefreshPreservesContentNoBanner() async throws {
        let fake = ScriptedMainClient(
            mains: [
                .success(try feed([eventJSON(1, status: "scheduled")])),  // initial load
                .failure(wrappedCancellation()),                          // refresh cancelled
            ],
            events: try emptyFeed(),
            grouped: try emptyGrouped()
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()
        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "initial content present")

        await vm.load()  // refresh — main throws wrapped cancellation

        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "cancelled refresh preserves cached content")
        XCTAssertNil(vm.error, "cancelled refresh raises no error banner")
        XCTAssertFalse(vm.refreshFailed, "cancelled refresh is not a refresh failure")
    }

    /// Contrast: a GENUINE refresh failure (non-cancel) DOES set `refreshFailed` while
    /// keeping content — proving the parity change did not swallow real failures.
    func testGenuineRefreshFailureStillFlagsRefreshFailed() async throws {
        let fake = ScriptedMainClient(
            mains: [
                .success(try feed([eventJSON(1, status: "scheduled")])),
                .failure(URLError(.badServerResponse)),
            ],
            events: try emptyFeed(),
            grouped: try emptyGrouped()
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()
        await vm.load()

        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "content preserved on refresh failure")
        XCTAssertTrue(vm.refreshFailed, "a real refresh failure is honestly flagged")
        XCTAssertNil(vm.error, "refresh failure keeps content, no cold error screen")
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

    func testTelemetryEmitsThreeDataReadyStages() async throws {
        // L2-209 Item 2 / C68: each stage reports a DATA-ready milestone (model
        // assignment). The misleading model-assignment "first-real-card" field is
        // gone — the true on-screen first render is a separate view-driven
        // `sports_feed_first_render` event that never fires for an empty main.
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
        for stage in sink.all {
            XCTAssertGreaterThanOrEqual(stage.dataReadyMs, 0, "each stage carries a data-ready milestone")
        }
        XCTAssertTrue(try XCTUnwrap(sink.stage(.main)).success)
    }

    // MARK: - Item 1: structured sibling ownership (C68-P2)

    func testViewDidStopDiscardsInFlightSiblingMerges() async throws {
        // Main publishes; both siblings are gated (in flight). The view then stops
        // (disappear). Pre-fix, siblings were unstructured `Task`s and `stopRefresh()`
        // did NOT bump the generation, so a late backfill/grouped still merged after
        // the view was gone. Now `viewDidStop()` invalidates the generation, so the
        // late siblings are dropped by the merge guard.
        let backfillGate = AsyncGate()
        let groupedGate = AsyncGate()
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "scheduled")])),
            backfill: .success(try feed([eventJSON(2, status: "scheduled")])),
            grouped: .success(try groupedResponse(3)),
            backfillGate: backfillGate,
            groupedGate: groupedGate
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        let task = Task { await vm.load() }
        await waitUntil { !vm.loading && vm.items.count == 1 }
        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "main published, siblings still gated")

        vm.viewDidStop()               // view disappears → generation invalidated

        backfillGate.open()
        groupedGate.open()
        await task.value

        XCTAssertEqual(vm.items.map(\.id), ["event-1"],
                       "a stopped view's late backfill did not merge")
        XCTAssertTrue(vm.groupedItems.isEmpty,
                      "a stopped view's late grouped did not publish")
    }

    // MARK: - Item 2: refresh armed immediately after main (C68-P2)

    func testAutoRefreshArmsImmediatelyAfterMainEvenWithSlowSiblings() async throws {
        // A live game must have its refresh timer armed the moment the main feed
        // publishes — pre-fix, `configureAutoRefresh()` ran only AFTER awaiting both
        // siblings, so a slow/hung sibling left a live game with no refresh timer.
        let backfillGate = AsyncGate()
        let groupedGate = AsyncGate()
        let fake = FakeSportsClient(
            main: .success(try feed([eventJSON(1, status: "live")])),
            backfill: .success(try emptyFeed()),
            grouped: .success(try emptyGrouped()),
            backfillGate: backfillGate,
            groupedGate: groupedGate
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: true)

        let task = Task { await vm.load() }
        await waitUntil { !vm.loading && vm.items.count == 1 }
        XCTAssertTrue(vm.refreshArmed,
                      "auto-refresh armed right after main, not deferred behind slow siblings")

        vm.viewDidStop()               // stop the real timer before it can fire
        XCTAssertFalse(vm.refreshArmed)
        backfillGate.open()
        groupedGate.open()
        await task.value
    }

    // MARK: - Item 2: honest non-initial refresh failure (C68-P2)

    func testNonInitialRefreshFailureKeepsContentAndFlagsRefreshFailed() async throws {
        // Main succeeds, then fails on a refresh (items already present). Pre-fix the
        // catch path only set an error when `isInitial`, so a refresh failure was
        // silent — stale content presented as fresh. Now `refreshFailed` surfaces a
        // non-blocking retryable state while the content is preserved.
        let fake = ScriptedMainClient(
            mains: [.success(try feed([eventJSON(1, status: "scheduled")])),
                    .failure(URLError(.timedOut))],
            events: try emptyFeed(),
            grouped: try emptyGrouped()
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)

        await vm.load()
        XCTAssertEqual(vm.items.map(\.id), ["event-1"])
        XCTAssertFalse(vm.refreshFailed)

        await vm.load()   // refresh — main fails

        XCTAssertEqual(vm.items.map(\.id), ["event-1"], "content retained on refresh failure")
        XCTAssertTrue(vm.refreshFailed, "refresh failure surfaced honestly")
        XCTAssertNil(vm.error, "no full-screen error while content is present")
        XCTAssertFalse(vm.loading)
    }

    func testSuccessfulRefreshClearsRefreshFailed() async throws {
        let fake = ScriptedMainClient(
            mains: [.success(try feed([eventJSON(1, status: "scheduled")])),
                    .failure(URLError(.timedOut)),
                    .success(try feed([eventJSON(1, status: "scheduled"), eventJSON(5, status: "scheduled")]))],
            events: try emptyFeed(),
            grouped: try emptyGrouped()
        )
        let vm = FeedViewModel(client: fake, telemetry: nil, autoRefreshEnabled: false)
        await vm.load()
        await vm.load()
        XCTAssertTrue(vm.refreshFailed)
        await vm.load()   // recovers
        XCTAssertFalse(vm.refreshFailed, "a later successful refresh clears the failed state")
        XCTAssertEqual(vm.items.map(\.id), ["event-1", "event-5"])
    }

    // MARK: - Item 2: empty successful main (C68-P2)

    func testEmptyMainSuccessEmitsDataReadyWithoutConflatedFirstCard() async throws {
        // An empty-but-successful main must still report a data-ready stage, but the
        // (removed) model-assignment first-card metric can no longer fire for zero
        // cards; the real first render is view-driven and never fires with no cards
        // to appear.
        let sink = TelemetrySink()
        let fake = FakeSportsClient(
            main: .success(try emptyFeed()),
            backfill: .success(try emptyFeed()),
            grouped: .success(try emptyGrouped())
        )
        let vm = FeedViewModel(client: fake, telemetry: { sink.record($0) }, autoRefreshEnabled: false)

        await vm.load()

        let main = try XCTUnwrap(sink.stage(.main))
        XCTAssertTrue(main.success, "empty main is a successful response")
        XCTAssertEqual(main.itemCount, 0)
        XCTAssertGreaterThanOrEqual(main.dataReadyMs, 0)
        XCTAssertTrue(vm.items.isEmpty)
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
