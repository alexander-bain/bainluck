import XCTest
@testable import Bain_Luck

/// L2-238 Item 0/1 — native's half of the Discover availability contract, case
/// for case against C129
/// (backend/tests/evals/fixtures/cold_feed_generation_contract.json).
///
/// `/api/feed` has three ways of returning zero cards and they mean different
/// things: a typed-UNAVAILABLE waiter terminal, a degraded build that produced
/// nothing, and a genuinely exhausted feed. Native decoded none of that. A
/// 200-OK unavailable body therefore walked the SUCCESS path: it blanked the
/// last-good cards the cache seed had just painted, cleared the staleness flags,
/// set `hasMore = false`, and reported `.revalidateSuccess` — an "all caught up"
/// assembled out of a response that explicitly said it knew nothing.
@MainActor
final class DiscoverFeedAvailabilityTests: XCTestCase {

    // MARK: - Fakes (mirrors DiscoverFeedSWRTests so both suites drive one model)

    private nonisolated final class FakeClient: DiscoverFeedProviding, @unchecked Sendable {
        /// Responses handed out in order; the last one repeats.
        private let responses: [FeedResponse]
        private let lock = NSLock()
        private var calls = 0
        init(_ responses: [FeedResponse]) { self.responses = responses }
        var callCount: Int { lock.withLock { calls } }
        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            lock.withLock {
                let r = responses[min(calls, responses.count - 1)]
                calls += 1
                return r
            }
        }
    }

    /// Answers by REQUEST SHAPE rather than call order, so an interleaving test
    /// cannot be decided by which of two concurrent calls the scheduler happens
    /// to start first. Offset-zero requests are loads; anything else is
    /// pagination, and pagination suspends so a load can be raced against it.
    private nonisolated final class ShapedClient: DiscoverFeedProviding, @unchecked Sendable {
        private let loads: [FeedResponse]
        private let pagination: FeedResponse
        private let paginationDelay: Duration
        private let lock = NSLock()
        private var loadCalls = 0
        init(loads: [FeedResponse], pagination: FeedResponse,
             paginationDelay: Duration = .milliseconds(200)) {
            self.loads = loads
            self.pagination = pagination
            self.paginationDelay = paginationDelay
        }
        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            guard offset > 0 else {
                return lock.withLock {
                    let r = loads[min(loadCalls, loads.count - 1)]
                    loadCalls += 1
                    return r
                }
            }
            try? await Task.sleep(for: paginationDelay)
            return pagination
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

    private func response(_ json: String) throws -> FeedResponse {
        try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func feed(_ ids: [Int], hasMore: Bool = true, extra: String = "") throws -> FeedResponse {
        try response("""
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":9999,"limit":200,"offset":0,"has_more":\(hasMore)\(extra)}
        """)
    }

    /// Byte-for-byte the body `backend/app/routes/feed.py` returns on the
    /// waiter-unavailable path (`build_feed_cache_metadata("unavailable", …)`).
    private func unavailableResponse(offset: Int = 0) throws -> FeedResponse {
        try response("""
        {"items":[],"total":0,"limit":200,"offset":\(offset),"has_more":false,
         "cache":{"status":"unavailable","ttl_seconds":60,"stale_ttl_seconds":900,
                  "reason":"leader_unavailable"}}
        """)
    }

    private func cached(_ ids: [Int]) throws -> CachedDiscoverFeed {
        CachedDiscoverFeed(
            response: try feed(ids),
            storedAt: ISO8601DateFormatter().date(from: "2026-08-03T12:00:00Z")!,
            ttlSeconds: 5,
            identity: "anon:s1"
        )
    }

    // MARK: - Decode (C129: fresh / hit / stale / last-good / unavailable)

    func testDecodesEveryCacheStatusAndOnlyUnavailableIsUnavailable() throws {
        for status in ["miss", "hit", "stale", "coalesced", "last_good", "error"] {
            let r = try feed([1], extra: #","cache":{"status":"\#(status)"}"#)
            XCTAssertFalse(r.isUnavailable, "\(status) must not read unavailable")
            XCTAssertEqual(r.cache?.status, status)
        }
        let unavailable = try unavailableResponse()
        XCTAssertTrue(unavailable.isUnavailable)
        XCTAssertEqual(unavailable.cache?.reason, "leader_unavailable")
        XCTAssertEqual(unavailable.cache?.ttlSeconds, 60)
        XCTAssertEqual(unavailable.cache?.staleTtlSeconds, 900)
    }

    /// The trap: a SERVED last-good payload carries `reason: "redis_unavailable"`.
    /// Keying on the reason (or on a substring) would blank a working feed.
    func testLastGoodWithRedisUnavailableReasonIsAvailable() throws {
        let r = try feed([1, 2], extra: #","cache":{"status":"last_good","reason":"redis_unavailable"}"#)
        XCTAssertFalse(r.isUnavailable)
        XCTAssertEqual(r.items.count, 2)
    }

    func testOldPayloadWithoutMetadataStaysCompatible() throws {
        let r = try feed([1, 2, 3])
        XCTAssertNil(r.cache)
        XCTAssertFalse(r.isUnavailable)
        XCTAssertFalse(r.isDegradedBuild)
        XCTAssertEqual(r.items.count, 3)
        XCTAssertTrue(r.hasMore)
    }

    func testMalformedMetadataNeverFabricatesUnavailability() throws {
        let malformed = [
            #"{"items":[],"has_more":false,"cache":null}"#,
            #"{"items":[],"has_more":false,"cache":"unavailable"}"#,
            #"{"items":[],"has_more":false,"cache":["unavailable"]}"#,
            #"{"items":[],"has_more":false,"cache":{"status":7}}"#,
            #"{"items":[],"has_more":false,"cache":{}}"#,
            #"{"items":[],"has_more":false,"build_quality":42}"#,
        ]
        for json in malformed {
            let r = try response(json)
            XCTAssertFalse(r.isUnavailable, "malformed metadata must read available: \(json)")
        }
    }

    func testBuildQualityOnlyDegradesWhenPresentAndNotComplete() throws {
        XCTAssertFalse(try feed([1]).isDegradedBuild)
        XCTAssertFalse(try feed([1], extra: #","build_quality":"complete""#).isDegradedBuild)
        let d = try feed([1], extra: #","build_quality":"degraded","degraded_reason":"futures_timeout""#)
        XCTAssertTrue(d.isDegradedBuild)
        XCTAssertEqual(d.degradedReason, "futures_timeout")
    }

    func testMayReplaceRenderedKeepsGenuineExhaustionDistinct() throws {
        // Genuine exhaustion: a COMPLETE build that really has nothing.
        let empty = try feed([], hasMore: false, extra: #","cache":{"status":"hit"}"#)
        XCTAssertTrue(empty.mayReplaceRendered(hasRenderedItems: true))
        XCTAssertTrue(empty.mayReplaceRendered(hasRenderedItems: false))
        // Unavailable: never, in either direction.
        let unavailable = try unavailableResponse()
        XCTAssertFalse(unavailable.mayReplaceRendered(hasRenderedItems: true))
        XCTAssertFalse(unavailable.mayReplaceRendered(hasRenderedItems: false))
        // Degraded-and-empty: only barred when there is something to protect.
        let degradedEmpty = try feed([], hasMore: false, extra: #","build_quality":"degraded""#)
        XCTAssertFalse(degradedEmpty.mayReplaceRendered(hasRenderedItems: true))
        XCTAssertTrue(degradedEmpty.mayReplaceRendered(hasRenderedItems: false))
        // Degraded WITH cards is real content.
        let degradedFull = try feed([1, 2], extra: #","build_quality":"degraded""#)
        XCTAssertTrue(degradedFull.mayReplaceRendered(hasRenderedItems: true))
    }

    // MARK: - Initial load (C129: unavailable-looks-empty)

    /// The headline regression. Before L2-238 this test's `vm.items` came back
    /// EMPTY with `hasMore == false`, `error == nil` and `.revalidateSuccess`.
    func testUnavailableRevalidationNeverBlanksLastGood() async throws {
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(
            client: FakeClient([try unavailableResponse()]),
            lastGood: FakeLastGood(try cached([1, 2, 3])),
            telemetry: { sink.record($0) })

        await vm.load()

        XCTAssertEqual(vm.items.map { $0.futures?.id }, [1, 2, 3],
                       "an unavailable response must never replace rendered cards with nothing")
        XCTAssertTrue(vm.isShowingCachedContent)
        XCTAssertTrue(vm.refreshFailedShowingCache, "the honest 'couldn't refresh' state, not silence")
        XCTAssertEqual(vm.error, "Showing recent markets — couldn't refresh")
        XCTAssertFalse(vm.loading, "loading terminates")
        XCTAssertEqual(sink.outcomes, [.cacheHitServed, .revalidateFailedKeptCache],
                       "never reported as a successful revalidation")
    }

    func testUnavailableDoesNotClosePaginationOnTheInitialLoad() async throws {
        let vm = DiscoverViewModel(
            client: FakeClient([try unavailableResponse()]),
            lastGood: FakeLastGood(try cached([1, 2, 3])),
            telemetry: nil)

        await vm.load()

        XCTAssertTrue(vm.hasMore,
                      "`has_more: false` on an unavailable body is an artifact of the empty response")
    }

    /// Cold launch, nothing cached: the same retryable screen a transport failure
    /// produces — never the end-of-feed card.
    func testUnavailableWithNoCacheIsTheRetryableErrorState() async throws {
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(
            client: FakeClient([try unavailableResponse()]),
            lastGood: FakeLastGood(nil),
            telemetry: { sink.record($0) })

        await vm.load()

        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertEqual(vm.error, "Couldn't load feed", "the view's existing retry screen")
        XCTAssertFalse(vm.loading)
        XCTAssertFalse(vm.refreshFailedShowingCache, "there is no cache to be honest about")
        XCTAssertEqual(sink.outcomes, [.cacheMiss, .revalidateFailedNoCache])
    }

    /// The one empty response that IS the truth still gets through unchanged.
    func testGenuineExhaustionStillAppliesAndEndsTheFeed() async throws {
        let vm = DiscoverViewModel(
            client: FakeClient([try feed([], hasMore: false, extra: #","cache":{"status":"hit"}"#)]),
            lastGood: FakeLastGood(nil),
            telemetry: nil)

        await vm.load()

        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertFalse(vm.hasMore, "a complete, empty build honestly ends the feed")
        XCTAssertNil(vm.error)
        XCTAssertFalse(vm.loading)
    }

    func testAnOldPayloadStillLoadsNormally() async throws {
        let vm = DiscoverViewModel(
            client: FakeClient([try feed(Array(1...12))]),
            lastGood: FakeLastGood(nil),
            telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.items.count, 12)
        XCTAssertTrue(vm.hasMore)
        XCTAssertNil(vm.error)
    }

    /// A degraded build that decoded to nothing must not blank the feed either.
    func testDegradedEmptyBuildDoesNotBlankRenderedCards() async throws {
        let vm = DiscoverViewModel(
            client: FakeClient([try feed([], hasMore: false,
                                         extra: #","build_quality":"degraded","degraded_reason":"futures_timeout""#)]),
            lastGood: FakeLastGood(try cached([1, 2])),
            telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.items.map { $0.futures?.id }, [1, 2])
        XCTAssertTrue(vm.hasMore)
        XCTAssertTrue(vm.refreshFailedShowingCache)
    }

    // MARK: - Pagination (C129: pagination unavailable)

    func testUnavailablePageNeverEndsTheFeed() async throws {
        // Page 1 real (13 cards, hasMore), page 2 unavailable.
        let vm = DiscoverViewModel(
            client: FakeClient([try feed(Array(100...112)), try unavailableResponse(offset: 200)]),
            lastGood: FakeLastGood(nil),
            telemetry: nil)

        await vm.load()
        XCTAssertEqual(vm.items.count, 13)
        XCTAssertTrue(vm.hasMore)

        await vm.loadMoreIfNeeded()

        XCTAssertTrue(vm.hasMore, "an unavailable page is transient — it cannot exhaust the feed")
        XCTAssertEqual(vm.items.count, 13, "every loaded card is kept")
        XCTAssertEqual(vm.error, "Couldn't load more markets", "the existing retryable pagination state")
        XCTAssertFalse(vm.loadingMore, "loading terminates")
    }

    /// Retry after an unavailable page resumes at the SAME boundary and succeeds.
    func testRetryAfterUnavailablePageResumesPagination() async throws {
        let client = FakeClient([
            try feed(Array(100...112)),          // initial load
            try unavailableResponse(offset: 200), // first loadMore → unavailable
            try feed(Array(200...204), hasMore: false), // retry → real page
        ])
        let vm = DiscoverViewModel(client: client, lastGood: FakeLastGood(nil), telemetry: nil)

        await vm.load()
        await vm.loadMoreIfNeeded()
        XCTAssertTrue(vm.hasMore, "pagination stayed open across the unavailable page")

        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 18, "the retry appended the real page")
        XCTAssertFalse(vm.hasMore, "and the real last page ended the feed honestly")
        XCTAssertNil(vm.error)
    }

    /// The counterexample: a REAL last page must still end the feed.
    func testRealLastPageStillEndsTheFeed() async throws {
        let vm = DiscoverViewModel(
            client: FakeClient([try feed(Array(100...112)),
                                try feed([], hasMore: false, extra: #","cache":{"status":"hit"}"#)]),
            lastGood: FakeLastGood(nil),
            telemetry: nil)

        await vm.load()
        await vm.loadMoreIfNeeded()

        XCTAssertFalse(vm.hasMore)
        XCTAssertNil(vm.error)
    }

    // MARK: - Identity supersession (C129)

    /// A late unavailable response from a superseded generation must not write
    /// the retry state over the identity that now owns the feed. The new
    /// unavailable branch sits AFTER the existing `shouldApplyPaginationResult`
    /// guard (C78 Item 1) — this proves the ordering rather than assuming it.
    func testSupersededUnavailablePageWritesNothing() async throws {
        let client = ShapedClient(
            loads: [try feed(Array(100...112)),      // first load
                    try feed(Array(300...312))],     // the rebind's own load
            pagination: try unavailableResponse(offset: 200))
        let vm = DiscoverViewModel(client: client, lastGood: FakeLastGood(nil), telemetry: nil)
        await vm.load()

        let paging = Task { await vm.loadMoreIfNeeded() }
        // Let pagination reach its (suspended) fetch before racing a rebind
        // against it, so the interleaving is the test's, not the scheduler's.
        try? await Task.sleep(for: .milliseconds(40))
        // Clears the feed and bumps the load generation, so the unavailable page
        // returns into a dead generation.
        await vm.rebindForIdentityChange()
        await paging.value

        XCTAssertNil(vm.error, "a dead generation's unavailable page writes no error")
        XCTAssertEqual(vm.items.map { $0.futures?.id }, Array(300...312),
                       "the new identity's feed is untouched by the superseded page")
    }

    // MARK: - Last-good persistence

    /// Caching an unavailable body would let a transient outage outlive itself:
    /// the next cold launch would paint its first "card" from an empty payload.
    func testUnavailableBodyIsNeverStoredAsLastGood() throws {
        XCTAssertFalse(APIClient.shouldStoreFeedAsLastGood(try unavailableResponse()))
        XCTAssertFalse(APIClient.shouldStoreFeedAsLastGood(
            try feed([], hasMore: false, extra: #","build_quality":"degraded""#)))
        // Real content — including a genuinely empty complete build — still stores.
        XCTAssertTrue(APIClient.shouldStoreFeedAsLastGood(try feed([1, 2, 3])))
        XCTAssertTrue(APIClient.shouldStoreFeedAsLastGood(
            try feed([], hasMore: false, extra: #","cache":{"status":"hit"}"#)))
        XCTAssertTrue(APIClient.shouldStoreFeedAsLastGood(
            try feed([1, 2], extra: #","build_quality":"degraded""#)))
    }
}
