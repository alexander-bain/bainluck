import XCTest
@testable import Bain_Luck

/// L2-201 / #1472 — `DiscoverViewModel.load()` initial-load behavior: a bounded
/// first page with a single fetch path (no normalized no-op fallback, bundles
/// admitted), deadline-aware classified retries (transient-only, one shared
/// budget, never decode/4xx/cancel), stale/superseded-response safety, and
/// first-card attribution telemetry.
///
/// These drive the view model through deterministic fakes (the
/// `DiscoverFeedProviding` seam, an injected last-good reader, and a capturing
/// telemetry sink), so request count/limit/offset, retry classification, budget
/// exhaustion, late-response races, and milestone emission are all provable —
/// none of which a pure predicate test can reach.
@MainActor
final class DiscoverViewModelLoadTests: XCTestCase {

    // MARK: - Fakes

    private enum Reply { case ok(FeedResponse); case fail(Error) }

    /// Records every request's (limit, offset, eventPct) so first-page bounds,
    /// fallback removal, and retry counts are assertable. Nonisolated + lock so it
    /// genuinely suspends when awaited from the MainActor view model.
    private nonisolated final class RecordingFakeClient: DiscoverFeedProviding, @unchecked Sendable {
        struct Call: Sendable { let limit: Int; let offset: Int; let eventPct: Double? }
        private let lock = NSLock()
        private var script: [Reply]
        private var log: [Call] = []

        init(_ script: [Reply]) { self.script = script }

        var calls: [Call] { lock.withLock { log } }
        var callCount: Int { lock.withLock { log.count } }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            await Task.yield()
            return try lock.withLock {
                log.append(Call(limit: limit, offset: offset, eventPct: eventPct))
                guard !script.isEmpty else { throw URLError(.badServerResponse) }
                switch script.removeFirst() {
                case .ok(let r): return r
                case .fail(let e): throw e
                }
            }
        }
    }

    /// First call blocks until `openGate()`; every later call returns the second
    /// response immediately. Lets a slow (older) load's response arrive AFTER a
    /// newer load has already published, to prove the late response is discarded.
    private nonisolated final class GatedFakeClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var callCount = 0
        private var gate: CheckedContinuation<Void, Never>?
        private var opened = false
        private let first: FeedResponse
        private let second: FeedResponse

        init(first: FeedResponse, second: FeedResponse) {
            self.first = first
            self.second = second
        }

        func openGate() {
            lock.withLock {
                opened = true
                gate?.resume()
                gate = nil
            }
        }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
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
    }

    private nonisolated final class FakeLastGood: DiscoverLastGoodReading, @unchecked Sendable {
        private let payload: CachedDiscoverFeed?
        init(_ payload: CachedDiscoverFeed?) { self.payload = payload }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
    }

    private nonisolated final class TelemetrySink: @unchecked Sendable {
        private let lock = NSLock()
        private var events: [DiscoverFeedTelemetry] = []
        func record(_ e: DiscoverFeedTelemetry) { lock.withLock { events.append(e) } }
        var outcomes: [DiscoverFeedTelemetry.Outcome] { lock.withLock { events.map(\.outcome) } }
        var all: [DiscoverFeedTelemetry] { lock.withLock { events } }
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }

    /// A comparison bundle carrying one renderable futures child.
    private func bundleWithChildJSON(id: String, childId: Int) -> String {
        """
        {"type":"bundle","score":95,"bundle":{"id":"\(id)","title":"Compare","kind":"comparison","items":[\(futuresJSON(childId))]}}
        """
    }

    /// A comparison bundle with no children — contributes no renderable card.
    private func emptyBundleJSON(id: String) -> String {
        """
        {"type":"bundle","score":95,"bundle":{"id":"\(id)","title":"Compare","kind":"comparison","items":[]}}
        """
    }

    private func response(itemJSONs: [String], offset: Int, hasMore: Bool, limit: Int) throws -> FeedResponse {
        let json = """
        {"items":[\(itemJSONs.joined(separator: ","))],"total":9999,"limit":\(limit),"offset":\(offset),"has_more":\(hasMore)}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func futuresResponse(ids: [Int], offset: Int, hasMore: Bool, limit: Int) throws -> FeedResponse {
        try response(itemJSONs: ids.map(futuresJSON), offset: offset, hasMore: hasMore, limit: limit)
    }

    private func cached(_ ids: [Int]) throws -> CachedDiscoverFeed {
        CachedDiscoverFeed(
            response: try futuresResponse(ids: ids, offset: 0, hasMore: true, limit: 200),
            storedAt: ISO8601DateFormatter().date(from: "2026-07-28T12:00:00Z")!,
            ttlSeconds: 5,
            identity: "anon:s1"
        )
    }

    // MARK: - Item 1: bounded first page + single fetch path

    func testFirstPageRequestsBoundedLimitNotFullWindow() async throws {
        let fake = RecordingFakeClient([.ok(try futuresResponse(ids: Array(1...12), offset: 0, hasMore: true, limit: 50))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        await vm.load()

        XCTAssertEqual(fake.callCount, 1, "exactly one initial fetch")
        let first = try XCTUnwrap(fake.calls.first)
        XCTAssertEqual(first.limit, DiscoverViewModel.firstPageLimit, "first page uses the bounded limit, not the former 200")
        XCTAssertEqual(first.offset, 0)
        XCTAssertEqual(first.eventPct, 0.15, "Discover mix preserved")
        XCTAssertEqual(vm.items.count, 12)
    }

    func testLowRenderableCountDoesNotTriggerFallbackRefetch() async throws {
        // Fewer than the old 10-item threshold. The prior code fired a SECOND
        // normalized-identical fetch (event_pct nil == 0.15 server-side, a no-op);
        // there must now be exactly ONE request.
        let fake = RecordingFakeClient([.ok(try futuresResponse(ids: [1, 2, 3], offset: 0, hasMore: true, limit: 50))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        await vm.load()

        XCTAssertEqual(fake.callCount, 1, "no low-count fallback refetch")
        XCTAssertEqual(vm.items.count, 3)
        XCTAssertNil(vm.error)
        XCTAssertFalse(vm.loading)
    }

    func testBundleWithRenderableChildIsPublished() async throws {
        let fake = RecordingFakeClient([.ok(try response(
            itemJSONs: [futuresJSON(1), bundleWithChildJSON(id: "b1", childId: 777), futuresJSON(2)],
            offset: 0, hasMore: true, limit: 50))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.items.count, 3, "bundle admitted alongside the two futures")
        XCTAssertNotNil(vm.items.first { $0.bundle?.id == "b1" }, "feed-driven bundle reaches the render path (C42 P1)")
    }

    func testEmptyBundleIsNotPublished() async throws {
        let fake = RecordingFakeClient([.ok(try response(
            itemJSONs: [futuresJSON(1), emptyBundleJSON(id: "b0"), futuresJSON(2)],
            offset: 0, hasMore: true, limit: 50))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.items.count, 2, "an all-ineligible bundle contributes no card")
        XCTAssertNil(vm.items.first { $0.bundle != nil })
    }

    func testBoundedFirstPageThenBackgroundPaginationPreservesOrderAndDedup() async throws {
        // Frozen ordered-ID equivalence: the bounded first page is the first 50 IDs
        // in server order; the next page concatenates 51...80 with no gaps or
        // duplicates. (All economics → interleave is order-preserving.)
        let fake = RecordingFakeClient([
            .ok(try futuresResponse(ids: Array(1...50), offset: 0, hasMore: true, limit: 50)),
            .ok(try futuresResponse(ids: Array(51...80), offset: 50, hasMore: false, limit: 50)),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        await vm.load()
        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(1...50), "first page = first 50 IDs in order")
        XCTAssertEqual(fake.calls.first?.limit, DiscoverViewModel.firstPageLimit)

        await vm.loadMoreIfNeeded()
        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(1...80), "background merge preserves order, no dupes")
        XCTAssertFalse(vm.hasMore, "server exhaustion honored")
        XCTAssertEqual(fake.calls.last?.offset, 50, "next page begins at the server boundary")
        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }).count, 80, "stable identity — no duplicated IDs")
    }

    // MARK: - Item 2: deadline-aware, classified retries

    func testDecodingFailureIsNotRetried() async throws {
        let fake = RecordingFakeClient([.fail(APIError.decodingError(underlying: URLError(.cannotParseResponse)))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil, retryBudget: 5)

        await vm.load()

        XCTAssertEqual(fake.callCount, 1, "a decode failure cannot self-heal — never retried, even with budget left")
        XCTAssertEqual(vm.error, "Couldn't load feed")
    }

    func testClientErrorIsNotRetried() async throws {
        let fake = RecordingFakeClient([.fail(APIError.httpError(statusCode: 404, body: nil))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil, retryBudget: 5)

        await vm.load()

        XCTAssertEqual(fake.callCount, 1, "a deterministic 4xx is not retried")
        XCTAssertEqual(vm.error, "Couldn't load feed")
    }

    func testTransientTransportFailureRetriedWithinBudgetThenSucceeds() async throws {
        let fake = RecordingFakeClient([
            .fail(URLError(.timedOut)),
            .ok(try futuresResponse(ids: Array(1...12), offset: 0, hasMore: true, limit: 50)),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil, retryBudget: 5, retryBackoff: 0)

        await vm.load()

        XCTAssertEqual(fake.callCount, 2, "one transient retry within budget")
        XCTAssertEqual(vm.items.count, 12)
        XCTAssertNil(vm.error)
    }

    func testServerErrorRetriedThenSucceeds() async throws {
        let fake = RecordingFakeClient([
            .fail(APIError.httpError(statusCode: 503, body: nil)),
            .ok(try futuresResponse(ids: Array(1...12), offset: 0, hasMore: true, limit: 50)),
        ])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil, retryBudget: 5, retryBackoff: 0)

        await vm.load()

        XCTAssertEqual(fake.callCount, 2, "5xx is transient — retried once within budget")
        XCTAssertEqual(vm.items.count, 12)
        XCTAssertNil(vm.error)
    }

    func testExhaustedBudgetStopsRetryingNoMultiplication() async throws {
        // Always-timing-out transient failure with zero budget must yield a SINGLE
        // attempt — proving the former up-to-six-request multiplication is gone.
        let fake = RecordingFakeClient(Array(repeating: Reply.fail(URLError(.timedOut)), count: 10))
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil, retryBudget: 0, retryBackoff: 0)

        await vm.load()

        XCTAssertEqual(fake.callCount, 1, "one total budget, exhausted → single attempt (was up to 6)")
        XCTAssertEqual(vm.error, "Couldn't load feed")
    }

    func testCancellationDuringLoadIsNotRetried() async throws {
        let fake = RecordingFakeClient([.fail(CancellationError())])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil, retryBudget: 5)

        await vm.load()

        XCTAssertEqual(fake.callCount, 1, "cancellation is terminal, not retried")
        XCTAssertNil(vm.error, "cancellation is not a user-facing error")
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertFalse(vm.loading)
    }

    func testRetryableClassificationMatrix() {
        // transient / 5xx / 429 self-heal; decode, non-429 4xx, invalid URL, and
        // cancellation do not.
        XCTAssertFalse(DiscoverViewModel.isRetryable(CancellationError()))
        XCTAssertFalse(DiscoverViewModel.isRetryable(URLError(.cancelled)))
        XCTAssertTrue(DiscoverViewModel.isRetryable(URLError(.timedOut)))
        XCTAssertTrue(DiscoverViewModel.isRetryable(URLError(.notConnectedToInternet)))
        XCTAssertTrue(DiscoverViewModel.isRetryable(APIError.networkError(underlying: URLError(.timedOut))))
        XCTAssertFalse(DiscoverViewModel.isRetryable(APIError.networkError(underlying: URLError(.cancelled))),
                       "a cancelled transport error is not retried")
        XCTAssertTrue(DiscoverViewModel.isRetryable(APIError.httpError(statusCode: 500, body: nil)))
        XCTAssertTrue(DiscoverViewModel.isRetryable(APIError.httpError(statusCode: 503, body: nil)))
        XCTAssertTrue(DiscoverViewModel.isRetryable(APIError.httpError(statusCode: 429, body: nil)))
        XCTAssertFalse(DiscoverViewModel.isRetryable(APIError.httpError(statusCode: 404, body: nil)))
        XCTAssertFalse(DiscoverViewModel.isRetryable(APIError.httpError(statusCode: 400, body: nil)))
        XCTAssertFalse(DiscoverViewModel.isRetryable(APIError.decodingError(underlying: URLError(.cannotParseResponse))))
        XCTAssertFalse(DiscoverViewModel.isRetryable(APIError.invalidURL))
    }

    // MARK: - Late-response / account-change race safety

    func testSupersededLoadDiscardsLateResponse() async throws {
        // Load A (older) blocks on the gate; Load B (newer) returns and publishes
        // first. When A's late response finally arrives it must NOT overwrite B's
        // feed — a stale in-flight response cannot clobber a newer session.
        let aContent = try futuresResponse(ids: Array(1...12), offset: 0, hasMore: true, limit: 50)
        let bContent = try futuresResponse(ids: Array(100...112), offset: 0, hasMore: true, limit: 50)
        let fake = GatedFakeClient(first: aContent, second: bContent)
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)

        async let a: Void = vm.load()   // call 1 — blocks on the gate
        await Task.yield()              // let A reach its network await
        await vm.load()                 // call 2 — returns B, publishes, generation advances

        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(100...112), "newer load B published")

        fake.openGate()                 // A's late response returns now
        await a

        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(100...112),
                       "superseded load A's late response discarded — no cross-session overwrite")
    }

    // MARK: - Item 3: first-card attribution telemetry

    func testColdSuccessEmitsNetworkMergeAndFirstCardMilestones() async throws {
        let sink = TelemetrySink()
        let fake = RecordingFakeClient([.ok(try futuresResponse(ids: Array(1...12), offset: 0, hasMore: true, limit: 50))])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: { sink.record($0) })

        await vm.load()

        let e = try XCTUnwrap(sink.all.last)
        XCTAssertEqual(e.outcome, .revalidateSuccess)
        XCTAssertNotNil(e.networkMs, "network round-trip attributed")
        XCTAssertNotNil(e.mergeMs, "merge/interleave attributed")
        XCTAssertNotNil(e.firstCardMs, "cold load: the network produced first paint")
    }

    func testFirstCardAttributedToCacheNotNetworkWhenSeeded() async throws {
        let sink = TelemetrySink()
        let cache = FakeLastGood(try cached([1, 2, 3]))
        let fresh = try futuresResponse(ids: Array(100...112), offset: 0, hasMore: true, limit: 50)
        let vm = DiscoverViewModel(client: RecordingFakeClient([.ok(fresh)]), lastGood: cache,
                                   telemetry: { sink.record($0) })

        await vm.load()

        XCTAssertEqual(sink.outcomes, [.cacheHitServed, .revalidateSuccess])
        let hit = try XCTUnwrap(sink.all.first)
        XCTAssertNotNil(hit.firstCardMs, "the cache seed produced first paint")
        XCTAssertNotNil(hit.mergeMs)
        let reval = try XCTUnwrap(sink.all.last)
        XCTAssertNil(reval.firstCardMs, "the later network revalidate was NOT first paint — no double-count")
        XCTAssertNotNil(reval.networkMs)
    }
}
