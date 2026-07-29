import XCTest
@testable import Bain_Luck

/// L2-213 / C78 — Native pagination and actor-cache ACCOUNT ISOLATION.
///
/// Closes C78's two remaining native account-boundary defects, verified against
/// the `native-account-isolation/v1` fixtures
/// (`backend/scripts/evals/native_account_isolation_fixtures.json`):
///   • Item 1 — pagination is bound to the load generation captured before its
///     first await and re-checked after every await, so a response that returns
///     after a logout / login / A→B switch / pull-refresh / superseding load is
///     dropped before it appends cards, advances the offset, flips hasMore/error,
///     or emits analytics (the `reject_stale_append_and_offset` counterexample).
///   • Item 2 — every cached authenticated GET is partitioned by the EXACT
///     resolved request principal, so no anonymous/authenticated or A→B identity
///     transition can surface a prior principal's cached body (the
///     `reject_path_query_only_cache` counterexample), while same-principal TTL
///     hits still work.
///
/// Coverage drives the pure decision cores over the full accepted + rejected
/// fixture set with opaque user A / user B / anonymous identities, AND drives
/// `DiscoverViewModel` pagination through a deterministic gate that releases a
/// prior identity's in-flight page only AFTER a rebind has published — the exact
/// race the generation guard exists to defend. No identity-bearing telemetry is
/// asserted or emitted.
@MainActor
final class NativeAccountIsolationTests: XCTestCase {

    // MARK: - Opaque identity helpers (two authenticated accounts + anonymous)

    /// Map a fixture identity token onto a concrete opaque namespace string.
    private func ns(_ token: String) -> String {
        switch token {
        case "anon": return "anon:session-xyz"
        case "user_a": return "user:a"
        case "user_b": return "user:b"
        default: return token
        }
    }

    /// Split a fixture endpoint (`/path?a=1&b=2`) into the path + query dictionary
    /// the production cache-key derivation consumes.
    private func split(_ endpoint: String) -> (path: String, query: [String: String]) {
        let parts = endpoint.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false)
        let path = String(parts[0])
        var query: [String: String] = [:]
        if parts.count > 1 {
            for pair in parts[1].split(separator: "&") {
                let kv = pair.split(separator: "=", maxSplits: 1)
                if kv.count == 2 { query[String(kv[0])] = String(kv[1]) }
            }
        }
        return (path, query)
    }

    // MARK: - Item 1: generation-bound pagination (pure decision core)

    /// Every `native-account-isolation/v1` pagination scenario, mapped onto the
    /// production gate `DiscoverViewModel.shouldApplyPaginationResult`. A response
    /// applies (mutates items/offset/hasMore/error/analytics) ONLY when its captured
    /// generation is still current; every identity transition or supersession bumps
    /// the generation and the response is dropped.
    func testPaginationGenerationGateMatrix() {
        // (id, capturedGeneration, currentGeneration, appliesExpected)
        let accepted: [(String, Int, Int, Bool)] = [
            ("page_same_generation",              7,  7,  true),
            ("page_logout_in_flight",             7,  8,  false),
            ("page_anon_login_in_flight",         2,  3,  false),
            ("page_a_to_b_in_flight",             9,  10, false),
            ("page_refresh_supersedes",           11, 12, false),
            ("page_rapid_pagination_single_owner",12, 12, true),
        ]
        for (id, captured, current, applies) in accepted {
            XCTAssertEqual(
                DiscoverViewModel.shouldApplyPaginationResult(
                    capturedGeneration: captured, currentGeneration: current),
                applies, "pagination gate wrong for scenario \(id)")
        }

        // reject_stale_append_and_offset: captured 4, current 5 — a stale, superseded
        // page. The fixture carries items/offset/has_more/error/analytics all mutated
        // (`expected_violations`), i.e. exactly what a MISSING post-await guard would
        // do. The production gate returns false, so none of those mutations happen.
        XCTAssertFalse(
            DiscoverViewModel.shouldApplyPaginationResult(
                capturedGeneration: 4, currentGeneration: 5),
            "reject_stale_append_and_offset: a superseded generation must never mutate feed state")
    }

    // MARK: - Item 1: generation-bound pagination (live view-model race)

    private nonisolated final class FakeLastGood: DiscoverLastGoodReading, @unchecked Sendable {
        private let payload: CachedDiscoverFeed?
        init(_ payload: CachedDiscoverFeed?) { self.payload = payload }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
    }

    /// Gates the in-flight PAGINATION fetch (offset 12) on a continuation so the test
    /// can deterministically publish a rebind before the stale page returns. All other
    /// offsets return immediately: offset 0 serves the initial page (identity A) then
    /// the rebound page (identity B); offset 11 serves B's next page.
    private nonisolated final class GatedPaginationClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var offsets: [Int] = []
        private var zeroCalls = 0
        private var gate: CheckedContinuation<Void, Never>?
        private var opened = false
        let staleFetchArrived: XCTestExpectation
        private let a: FeedResponse
        private let b: FeedResponse
        private let stale: FeedResponse
        private let bPage2: FeedResponse

        init(a: FeedResponse, b: FeedResponse, stale: FeedResponse, bPage2: FeedResponse,
             staleFetchArrived: XCTestExpectation) {
            self.a = a; self.b = b; self.stale = stale; self.bPage2 = bPage2
            self.staleFetchArrived = staleFetchArrived
        }

        var requestedOffsets: [Int] { lock.withLock { offsets } }
        func openGate() { lock.withLock { opened = true; gate?.resume(); gate = nil } }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            lock.withLock { offsets.append(offset) }
            if offset == 12 {
                // The superseded pagination page parks until the test releases it —
                // by which time the rebind has bumped the load generation.
                await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                    let signal: Bool = lock.withLock {
                        if opened { cont.resume(); return false }
                        gate = cont; return true
                    }
                    if signal { staleFetchArrived.fulfill() }
                }
                return stale
            }
            if offset == 0 {
                let n = lock.withLock { () -> Int in zeroCalls += 1; return zeroCalls }
                return n == 1 ? a : b
            }
            return bPage2
        }
    }

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d
    }
    private func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }
    private func response(ids: [Int], offset: Int = 0, hasMore: Bool = true, limit: Int? = nil) throws -> FeedResponse {
        let lim = limit ?? ids.count
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":9999,"limit":\(lim),"offset":\(offset),"has_more":\(hasMore)}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// The Item 1 acceptance in full: a gated pagination response RELEASED AFTER
    /// `rebindForIdentityChange()` appends zero cards, leaves the rebound
    /// offset/hasMore/error untouched, and emits no dead-generation event — while a
    /// fresh same-generation pagination still advances normally.
    func testStalePaginationResponseAfterRebindIsDropped() async throws {
        let a = try response(ids: Array(1...12))                              // identity A, boundary → offset 12
        let stale = try response(ids: [999], offset: 12, hasMore: true, limit: 200)  // superseded page
        let b = try response(ids: Array(100...110))                          // identity B, boundary → offset 11
        let bPage2 = try response(ids: [200], offset: 11, hasMore: false, limit: 11)
        let arrived = expectation(description: "stale pagination fetch parked on the gate")
        let fake = GatedPaginationClient(a: a, b: b, stale: stale, bPage2: bPage2,
                                         staleFetchArrived: arrived)
        // Large budget so the initial load's deadline never fires during the gate wait.
        let vm = DiscoverViewModel(client: fake, lastGood: FakeLastGood(nil),
                                   telemetry: nil, retryBudget: 30, retryBackoff: 0.01)

        await vm.load()                                                       // generation 1 (identity A)
        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(1...12))

        async let more: Void = vm.loadMoreIfNeeded()                          // captures generation 1, parks at offset 12
        await fulfillment(of: [arrived], timeout: 5)
        await vm.rebindForIdentityChange()                                    // generation 2 (identity B) publishes
        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(100...110),
                       "identity B published while the prior page was in flight")

        fake.openGate()                                                       // stale page (id 999) returns now
        await more

        // Dropped by the generation guard: zero cards appended, no cross-identity id.
        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(100...110),
                       "the superseded page appended zero cards under the new identity")
        XCTAssertFalse(vm.items.contains { $0.futures?.id == 999 },
                       "the prior identity's page content never leaked into identity B")
        XCTAssertNil(vm.error, "a dead-generation response never paints an error over the new identity")
        XCTAssertTrue(vm.hasMore, "rebound hasMore untouched by the stale page")

        // The offset cursor was NOT advanced by the stale page: a fresh same-generation
        // loadMore targets B's own boundary (11), not the stale page's 12 + 200 = 212.
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requestedOffsets, [0, 12, 0, 11],
                       "same-generation pagination advances by B's boundary; the stale page never moved the cursor")
        XCTAssertEqual(vm.items.count, 12, "same-generation pagination appended the next page normally")
        XCTAssertTrue(vm.items.contains { $0.futures?.id == 200 })
    }

    // MARK: - Item 2: principal-bound actor response cache (pure key core)

    /// Every `native-account-isolation/v1` cache scenario, mapped onto the production
    /// key `APIClient.responseCacheKey`. A cross-identity cache hit is possible ONLY
    /// when the dispatch and current principals are identical — the partitioned key
    /// differs for every anonymous/authenticated or A→B transition, so a prior
    /// principal's body can never be served.
    func testCacheKeyPartitionMatrix() {
        // (id, endpoint, dispatch, current, hitExpected)
        let scenarios: [(String, String, String, String, Bool)] = [
            ("cache_same_user_my_stuff",   "/api/me/team-futures",     "user_a", "user_a", true),
            ("cache_logout_my_stuff",      "/api/me/team-futures",     "user_a", "anon",   false),
            ("cache_a_to_b_my_stuff",      "/api/me/team-futures",     "user_a", "user_b", false),
            ("cache_a_to_b_sports",        "/api/feed?sport=basketball","user_a", "user_b", false),
            ("cache_anon_to_user_generic", "/api/events/faceted",      "anon",   "user_a", false),
            ("cache_pagination_uncached",  "/api/feed?offset=200",     "user_a", "user_b", false),
        ]
        for (id, endpoint, dispatch, current, hit) in scenarios {
            let (path, query) = split(endpoint)
            let dispatchKey = APIClient.responseCacheKey(principal: ns(dispatch), path: path, query: query)
            let currentKey = APIClient.responseCacheKey(principal: ns(current), path: path, query: query)
            XCTAssertEqual(dispatchKey == currentKey, hit,
                           "cache-hit possibility wrong for scenario \(id)")
        }
    }

    /// reject_path_query_only_cache: A→B on `/api/me/team-futures?limit=100`. The
    /// fixture's `cache_hit: true` is the BUG — a path+query-only key is identical for
    /// both accounts, so A's cached body would serve B. The production principal-bound
    /// key differs, so no cross-identity hit is possible by construction.
    func testPathQueryOnlyCacheCounterexampleIsClosed() {
        let (path, query) = split("/api/me/team-futures?limit=100")

        // The pre-fix path+query-only key ignored the principal entirely, so the SAME
        // key was derived whoever the caller was — A's stored body served B (the bug).
        func legacyKey(path: String, query: [String: String]) -> String {
            let sortedQuery = query.sorted(by: { $0.key < $1.key })
                .map { "\($0.key)=\($0.value)" }.joined(separator: "&")
            return path + "?" + sortedQuery
        }
        XCTAssertEqual(legacyKey(path: path, query: query), "/api/me/team-futures?limit=100",
                       "the pre-fix key carried no principal, so it was identical for A and B — the cross-identity hit the fixture flags")

        // The production key binds the principal, so A and B never share an entry.
        let keyA = APIClient.responseCacheKey(principal: ns("user_a"), path: path, query: query)
        let keyB = APIClient.responseCacheKey(principal: ns("user_b"), path: path, query: query)
        XCTAssertNotEqual(keyA, keyB,
                          "principal-partitioned keys make the A→B cache hit impossible by construction")
    }

    /// Same-principal TTL hits remain functional: an identical (principal, path,
    /// query) reproduces the same key, so a warm same-account read still hits.
    func testSamePrincipalCacheKeyIsStable() {
        let (path, query) = split("/api/me/team-futures")
        XCTAssertEqual(
            APIClient.responseCacheKey(principal: ns("user_a"), path: path, query: query),
            APIClient.responseCacheKey(principal: ns("user_a"), path: path, query: query),
            "the same principal + path + query must reproduce one key so TTL hits still serve")
    }

    /// The partition delimiter is a control character that can never appear in a
    /// principal (`user:<id>` / `anon:<session>`) or a URL path, so the principal
    /// segment can never be confused with, or forged from, path/query bytes.
    func testCacheKeyDelimiterCannotBeForgedFromPath() {
        // A path crafted to look like "user:a" + separator + real path must NOT collide
        // with the genuine user:a key for that path.
        let genuine = APIClient.responseCacheKey(principal: "user:a", path: "/api/x", query: [:])
        let forged = APIClient.responseCacheKey(principal: "anon:s", path: "user:a/api/x", query: [:])
        XCTAssertNotEqual(genuine, forged,
                          "no path can impersonate another principal's cache namespace")
    }
}
