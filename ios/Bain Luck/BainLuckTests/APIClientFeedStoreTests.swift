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
