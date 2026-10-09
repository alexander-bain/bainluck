import XCTest
@testable import Bain_Luck

/// L2-208 Item 1 / C67 P1+P2 — the last-good feed STORE is bound to the request's
/// real principal (not the optimistic cold-launch read namespace), and a launch
/// with no credential clears a stale persisted signed-in identity.
///
/// These exercise the pure store-decision matrix, the persisted-id write/clear,
/// and ACTUAL cache files (identity-partitioned eviction) — not only the static
/// string helpers `APIClientFeedIdentityTests` covered, which C67 flagged as
/// never touching the real cache/identity lifecycle.
final class APIClientFeedStoreTests: XCTestCase {

    private let key = "bainluck_last_known_user_id"

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: key)
        super.tearDown()
    }

    // MARK: - Store principal binding (C67 P1)

    func testAnonymousResponseNeverStoredUnderUserNamespace() {
        // The returning-user race: the read namespace is `user:42` (optimistic
        // cold-launch seed), but the revalidation left the client BEFORE auth
        // restore installed the token provider, so it authenticated as nobody. Its
        // anonymous response must not be written back under `user:42` — the exact
        // poison C67 P1 identified. On the pre-fix code the store guard checked only
        // `identityAtFetch == currentFeedIdentity()` (both `user:42`) and would have
        // persisted the anonymous body under `user:42`.
        XCTAssertFalse(APIClient.shouldPersistFeed(
            identityAtFetch: "user:42", userIdAtFetch: "42",
            wasAuthenticated: false, currentIdentity: "user:42"),
            "a tokenless (anonymous) response must never poison user:42 last-good")
    }

    func testAuthenticatedResponseStoredUnderUserNamespace() {
        XCTAssertTrue(APIClient.shouldPersistFeed(
            identityAtFetch: "user:42", userIdAtFetch: "42",
            wasAuthenticated: true, currentIdentity: "user:42"),
            "a genuinely signed-in response persists under the user namespace")
    }

    func testAnonymousResponseStoredUnderAnonymousNamespace() {
        XCTAssertTrue(APIClient.shouldPersistFeed(
            identityAtFetch: "anon:s1", userIdAtFetch: nil,
            wasAuthenticated: false, currentIdentity: "anon:s1"),
            "a genuinely anonymous response persists under the anon namespace")
    }

    func testAuthenticatedResponseNeverStoredUnderAnonymousNamespace() {
        // Defensive inverse: a signed-in response landing in a shared anonymous
        // namespace would leak one account's personalized feed to signed-out mode.
        XCTAssertFalse(APIClient.shouldPersistFeed(
            identityAtFetch: "anon:s1", userIdAtFetch: nil,
            wasAuthenticated: true, currentIdentity: "anon:s1"))
    }

    func testMidFlightIdentityChangeSuppressesStore() {
        // Account switch A→B (or logout) between request dispatch and store: the
        // effective identity moved, so A's captured response must not land at all.
        XCTAssertFalse(APIClient.shouldPersistFeed(
            identityAtFetch: "user:42", userIdAtFetch: "42",
            wasAuthenticated: true, currentIdentity: "user:99"),
            "a response captured under a now-stale identity must not be stored")
        XCTAssertFalse(APIClient.shouldPersistFeed(
            identityAtFetch: "user:42", userIdAtFetch: "42",
            wasAuthenticated: true, currentIdentity: "anon:s1"),
            "logout mid-flight suppresses the signed-in store")
    }

    func testEmptyUserIdIsTreatedAsAnonymousNamespace() {
        // An empty id is the anonymous namespace, so only an unauthenticated
        // response may store — never a signed-in one.
        XCTAssertTrue(APIClient.shouldPersistFeed(
            identityAtFetch: "anon:s1", userIdAtFetch: "",
            wasAuthenticated: false, currentIdentity: "anon:s1"))
        XCTAssertFalse(APIClient.shouldPersistFeed(
            identityAtFetch: "anon:s1", userIdAtFetch: "",
            wasAuthenticated: true, currentIdentity: "anon:s1"))
    }

    // MARK: - Persisted-id write/clear (C67 P2)

    func testPersistedIdWriteThenClear() {
        APIClient.setPersistedLastKnownUserId("42")
        XCTAssertEqual(APIClient.persistedLastKnownUserId(), "42")
        // No credential → clear, so the next launch never reads `user:42`.
        APIClient.setPersistedLastKnownUserId(nil)
        XCTAssertNil(APIClient.persistedLastKnownUserId(),
                     "a no-credential launch clears the stale signed-in identity")
    }

    func testEmptyPersistedIdWriteClears() {
        APIClient.setPersistedLastKnownUserId("42")
        APIClient.setPersistedLastKnownUserId("")
        XCTAssertNil(APIClient.persistedLastKnownUserId(),
                     "an empty id must not leave a `user:` namespace active")
    }

    // MARK: - Actual cache files: identity-partitioned eviction (C67 P2 mechanism)

    func testEvictionDropsStaleUserNamespaceKeepingAnonymous() throws {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("FeedStoreTest-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: dir) }
        let cache = DiscoverFeedCache(directory: dir)

        let body = Data(#"{"items":[],"total":0,"limit":50,"offset":0,"has_more":false}"#.utf8)
        cache.store(rawBody: body, identity: "user:42", storedAt: Date())
        cache.store(rawBody: body, identity: "anon:s1", storedAt: Date())
        XCTAssertNotNil(cache.load(identity: "user:42"), "user namespace stored")
        XCTAssertNotNil(cache.load(identity: "anon:s1"), "anon namespace stored")

        // A no-credential launch resolves to anonymous → evict everything but anon,
        // exactly as `setFeedCacheIdentity(nil)` does on the C67 P2 clear path.
        cache.evict(keepingOnly: "anon:s1")

        XCTAssertNil(cache.load(identity: "user:42"),
                     "the stale signed-in namespace is evicted on a no-credential launch")
        XCTAssertNotNil(cache.load(identity: "anon:s1"),
                        "the anonymous namespace survives")
    }
}

// MARK: - #5105: the accepted edition reaches BOTH Discover request builders

/// Real `APIClient` + real `URLSession`; only the origin is stubbed. The
/// principal-resolving offset-0 revalidation is a separate query builder from
/// `fetchFeed`, so a token added to one and not the other silently re-asks for an
/// unpinned order on every background revalidation of an accepted deck.
final class APIClientFeedEditionTransport5105Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var captured: [URL] = []

        static func reset() { lock.withLock { captured = [] } }
        static var feedURLs: [URL] {
            lock.withLock { captured.filter { $0.path == "/api/feed" } }
        }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            if let url = request.url { Self.lock.withLock { Self.captured.append(url) } }
            // UNAVAILABLE: decodes, and is never stored as last-good, so the test
            // writes nothing to the on-disk feed cache.
            let body = #"{"items":[],"total":0,"limit":50,"offset":0,"has_more":false,"cache":{"status":"unavailable"}}"#
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func client() -> APIClient {
        Origin.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        return APIClient(session: URLSession(configuration: configuration))
    }

    private func edition(of url: URL) -> String? {
        URLComponents(url: url, resolvingAgainstBaseURL: false)?
            .queryItems?.first { $0.name == "edition" }?.value
    }

    func testTokenRidesPaginationAndPrincipalResolvingRevalidation() async throws {
        let api = client()
        _ = try await api.fetchDiscoverFeedResolvingPrincipal(
            limit: 50, offset: 0, eventPct: 0.15, edition: "ed-7", cacheTTL: nil)
        _ = try await api.fetchDiscoverFeed(
            limit: 200, offset: 50, eventPct: 0.15, edition: "ed-7", cacheTTL: nil)

        let urls = Origin.feedURLs
        XCTAssertEqual(urls.count, 2)
        XCTAssertEqual(urls.map { edition(of: $0) }, ["ed-7", "ed-7"],
            "the token must reach the offset-0 principal-resolving builder AND pagination")
    }

    func testUnpinnedRequestsCarryNoToken() async throws {
        let api = client()
        _ = try await api.fetchDiscoverFeedResolvingPrincipal(
            limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil)
        _ = try await api.fetchDiscoverFeedResolvingPrincipal(
            limit: 50, offset: 0, eventPct: 0.15, edition: nil, cacheTTL: nil)
        _ = try await api.fetchDiscoverFeed(
            limit: 200, offset: 50, eventPct: 0.15, edition: "  ", cacheTTL: nil)

        let urls = Origin.feedURLs
        XCTAssertEqual(urls.count, 3)
        XCTAssertTrue(urls.allSatisfy { edition(of: $0) == nil },
            "a new opening / manual replacement sends no token; a blank one is none: \(urls)")
    }
}
