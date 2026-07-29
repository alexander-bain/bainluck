import XCTest
@testable import Bain_Luck

/// L2-197 / #1465 — `DiscoverViewModel` stale-while-revalidate behavior. Drives
/// the view model through injected fakes (a last-good reader, a scripted feed
/// client, and a capturing telemetry sink) so the perceived-latency win is
/// provable without claiming the backend cold miss (#1459) is fixed: last-good
/// seeds a first card before the network, a background success replaces it
/// without blanking, and a failed refresh preserves last-good honestly.
@MainActor
final class DiscoverFeedSWRTests: XCTestCase {

    // MARK: - Fakes

    private nonisolated final class FakeClient: DiscoverFeedProviding, @unchecked Sendable {
        enum Mode { case success(FeedResponse); case fail(Error) }
        private let mode: Mode
        init(_ mode: Mode) { self.mode = mode }
        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            switch mode {
            case .success(let r): return r
            case .fail(let e): throw e
            }
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

    private func eventJSON(_ id: Int) -> String {
        """
        {"type":"event","score":90,"data":{"id":\(id),"sport":"basketball","home_team":"Home","away_team":"Away","status":"scheduled","commence_time":"2030-01-01T00:00:00Z"}}
        """
    }

    private func conceptJSON(_ key: String) -> String {
        """
        {"type":"concept","score":90,"data":{"key":"\(key)","name":"Tour","domain":"golf","status":"live"}}
        """
    }

    private func bundleOnlyJSON() -> String {
        """
        {"type":"bundle","score":95,"bundle":{"id":"b1","title":"Compare","kind":"comparison","items":[]}}
        """
    }

    private func feedResponse(_ itemJSONs: [String], hasMore: Bool = true) throws -> FeedResponse {
        let json = """
        {"items":[\(itemJSONs.joined(separator: ","))],"total":9999,"limit":200,"offset":0,"has_more":\(hasMore)}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func cached(_ itemJSONs: [String], storedAt: Date? = nil) throws -> CachedDiscoverFeed {
        CachedDiscoverFeed(
            response: try feedResponse(itemJSONs),
            storedAt: storedAt ?? ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!,
            ttlSeconds: 5,
            identity: "anon:s1"
        )
    }

    // MARK: - Cache seeds before network

    func testCacheHitServedThenRevalidatedByFreshContent() async throws {
        let cache = FakeLastGood(try cached([futuresJSON(1), futuresJSON(2), futuresJSON(3)]))
        let fresh = try feedResponse((100...112).map(futuresJSON))   // >=10 → no fallback
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(client: FakeClient(.success(fresh)), lastGood: cache,
                                   telemetry: { sink.record($0) })

        await vm.load()

        // Last-good served FIRST, then a background success replaced it.
        XCTAssertEqual(sink.outcomes, [.cacheHitServed, .revalidateSuccess])
        XCTAssertEqual(vm.items.count, 13, "fresh server set replaced the 3 cached cards")
        XCTAssertFalse(vm.isShowingCachedContent, "no longer showing cache after fresh replace")
        XCTAssertFalse(vm.refreshFailedShowingCache)
        XCTAssertFalse(vm.loading)
        XCTAssertNil(vm.error)
        XCTAssertNil(vm.lastGoodStoredAt)

        let hit = try XCTUnwrap(sink.all.first)
        XCTAssertEqual(hit.itemCount, 3)
        XCTAssertNotNil(hit.cacheDecodeMs, "cache-render cost recorded")
        XCTAssertNotNil(hit.cacheAgeSeconds)
    }

    // MARK: - Instant first card without network (cancellation mid-revalidate)

    func testCachedItemsRenderEvenWhenRevalidateDoesNotComplete() async throws {
        let cache = FakeLastGood(try cached([futuresJSON(1), futuresJSON(2), futuresJSON(3)]))
        // Cancellation returns early after seeding — proves a first card renders
        // from cache with no completed network round-trip.
        let vm = DiscoverViewModel(client: FakeClient(.fail(CancellationError())),
                                   lastGood: cache, telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.items.map { $0.futures?.id }, [1, 2, 3], "cached cards shown, order preserved")
        XCTAssertTrue(vm.isShowingCachedContent)
        XCTAssertFalse(vm.loading)
    }

    // MARK: - Background success never blanks

    func testRevalidateSuccessReplacesWithoutBlanking() async throws {
        let cache = FakeLastGood(try cached([futuresJSON(1)]))
        let fresh = try feedResponse((100...112).map(futuresJSON))
        let vm = DiscoverViewModel(client: FakeClient(.success(fresh)), lastGood: cache, telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.items.count, 13)
        XCTAssertFalse(vm.items.isEmpty, "feed is never blanked between cache and fresh")
        XCTAssertFalse(vm.isShowingCachedContent)
        XCTAssertNil(vm.error)
    }

    // MARK: - Refresh failure preserves last-good

    func testRefreshFailureKeepsLastGoodAndSurfacesHonestState() async throws {
        let cache = FakeLastGood(try cached([futuresJSON(1), futuresJSON(2)]))
        let sink = TelemetrySink()
        // retryBudget 0 → exactly one transient attempt (no waiting), so the test
        // stays fast and deterministic while still proving the honest kept-cache
        // state (L2-201 / #1472).
        let vm = DiscoverViewModel(client: FakeClient(.fail(URLError(.notConnectedToInternet))),
                                   lastGood: cache, telemetry: { sink.record($0) },
                                   retryBudget: 0)

        await vm.load()

        XCTAssertEqual(vm.items.map { $0.futures?.id }, [1, 2], "last-good preserved, not blanked")
        XCTAssertTrue(vm.isShowingCachedContent)
        XCTAssertTrue(vm.refreshFailedShowingCache, "honest 'showing recent' banner state")
        XCTAssertEqual(vm.error, "Showing recent markets — couldn't refresh")
        XCTAssertFalse(vm.loading)
        XCTAssertEqual(sink.outcomes, [.cacheHitServed, .revalidateFailedKeptCache])
    }

    // MARK: - No cache: honest loading/error, no false cache state

    func testNoCacheRevalidateFailureFallsToHonestError() async throws {
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(client: FakeClient(.fail(URLError(.timedOut))),
                                   lastGood: FakeLastGood(nil), telemetry: { sink.record($0) },
                                   retryBudget: 0)

        await vm.load()

        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertEqual(vm.error, "Couldn't load feed")
        XCTAssertFalse(vm.isShowingCachedContent)
        XCTAssertFalse(vm.refreshFailedShowingCache)
        XCTAssertEqual(sink.outcomes, [.cacheMiss, .revalidateFailedNoCache])
    }

    func testNoCacheSuccessLoadsNormally() async throws {
        let fresh = try feedResponse((100...112).map(futuresJSON))
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(client: FakeClient(.success(fresh)),
                                   lastGood: FakeLastGood(nil), telemetry: { sink.record($0) })

        await vm.load()

        XCTAssertEqual(vm.items.count, 13)
        XCTAssertEqual(sink.outcomes, [.cacheMiss, .revalidateSuccess])
        let revalidate = try XCTUnwrap(sink.all.last)
        XCTAssertNotNil(revalidate.networkMs, "network round-trip cost recorded")
    }

    // MARK: - Mixed payload seeds every renderable card type

    func testMixedPayloadSeedsEventFuturesConcept() async throws {
        let cache = FakeLastGood(try cached([eventJSON(100), futuresJSON(1), conceptJSON("tour-2026")]))
        // Cancellation → seed only, fast (no retry sleeps).
        let vm = DiscoverViewModel(client: FakeClient(.fail(CancellationError())),
                                   lastGood: cache, telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.items.count, 3, "event + futures + concept all seeded")
        XCTAssertNotNil(vm.items.first { $0.event?.id == 100 })
        XCTAssertNotNil(vm.items.first { $0.futures?.id == 1 })
        XCTAssertNotNil(vm.items.first { $0.concept?.key == "tour-2026" })
    }

    // MARK: - Cached-but-nothing-renderable is a miss, not a hit

    func testCachedPayloadWithNoRenderableItemsIsMiss() async throws {
        let cache = FakeLastGood(try cached([bundleOnlyJSON()]))
        let fresh = try feedResponse((100...112).map(futuresJSON))
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(client: FakeClient(.success(fresh)), lastGood: cache,
                                   telemetry: { sink.record($0) })

        await vm.load()

        // A cached payload with no event/futures/tournament/concept can't seed a
        // first card → treated as a miss, then the network fills the feed.
        XCTAssertEqual(sink.outcomes, [.cacheMiss, .revalidateSuccess])
        XCTAssertFalse(vm.isShowingCachedContent)
        XCTAssertEqual(vm.items.count, 13)
    }

    // MARK: - First-render provenance frozen at data-ready (L2-208 Item 2 / C67 P2)

    func testFirstDataProvenanceIsCacheEvenAfterFastNetworkReplace() async throws {
        // The cache seed produces first paint, then a fast network hit replaces
        // items and flips `isShowingCachedContent` to false. The FROZEN first-paint
        // provenance must stay `cache` so the view's on-screen first-render event is
        // not mislabeled network — the exact race C67 P2 flagged (the pre-fix view
        // read the live `isShowingCachedContent`, already false by `onAppear`).
        let cache = FakeLastGood(try cached([futuresJSON(1), futuresJSON(2), futuresJSON(3)]))
        let fresh = try feedResponse((100...112).map(futuresJSON))
        let vm = DiscoverViewModel(client: FakeClient(.success(fresh)), lastGood: cache, telemetry: nil)

        await vm.load()

        XCTAssertFalse(vm.isShowingCachedContent, "network replaced the seed (live flag flipped)")
        XCTAssertEqual(vm.firstDataFromCache, true,
            "first paint came from cache; provenance frozen despite the later network replace")
    }

    func testFirstDataProvenanceIsNetworkOnColdMiss() async throws {
        // No cache → the network produces first paint → provenance is network.
        let fresh = try feedResponse((100...112).map(futuresJSON))
        let vm = DiscoverViewModel(client: FakeClient(.success(fresh)), lastGood: FakeLastGood(nil), telemetry: nil)

        await vm.load()

        XCTAssertEqual(vm.firstDataFromCache, false,
            "a cold miss's first paint is network, reported truthfully")
    }

    func testFirstDataProvenanceResetsPerLoad() async throws {
        // Provenance is per-load, not sticky. A first load seeds from cache
        // (provenance cache); a second load runs with items already present, skips
        // the cache seed, and revalidates via network → provenance re-stamps network.
        let cache = FakeLastGood(try cached([futuresJSON(1)]))
        let fresh = try feedResponse((100...112).map(futuresJSON))
        let vm = DiscoverViewModel(client: FakeClient(.success(fresh)), lastGood: cache, telemetry: nil)

        await vm.load()
        XCTAssertEqual(vm.firstDataFromCache, true, "first load seeded from cache")

        await vm.load()
        XCTAssertEqual(vm.firstDataFromCache, false,
            "second load's first data came from the network revalidation")
    }
}
