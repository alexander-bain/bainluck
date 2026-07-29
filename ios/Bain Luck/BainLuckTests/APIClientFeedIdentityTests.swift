import XCTest
@testable import Bain_Luck

/// L2-206 / #1472 Item 1 — the last-known signed-in user id is persisted so the
/// feed-cache namespace is resolvable at cold launch BEFORE async session restore
/// (`fetchProfile()`) completes. Without this, a returning signed-in user's first
/// cold cache read lands in the anonymous namespace and misses their own last-good
/// feed. Only the public user id is stored (never a token), and it maps straight
/// to the identity-partitioned cache namespace.
final class APIClientFeedIdentityTests: XCTestCase {

    private let key = "bainluck_last_known_user_id"

    override func tearDown() {
        UserDefaults.standard.removeObject(forKey: key)
        super.tearDown()
    }

    func testPersistedIdRoundTrips() {
        UserDefaults.standard.set("42", forKey: key)
        XCTAssertEqual(APIClient.persistedLastKnownUserId(), "42",
                       "cold launch can resolve the signed-in namespace before restore")
    }

    func testAbsentPersistedIdIsAnonymous() {
        UserDefaults.standard.removeObject(forKey: key)
        XCTAssertNil(APIClient.persistedLastKnownUserId())
    }

    func testEmptyPersistedIdIsTreatedAsAnonymous() {
        UserDefaults.standard.set("", forKey: key)
        XCTAssertNil(APIClient.persistedLastKnownUserId(),
                     "an empty id must not produce a `user:` namespace")
    }

    func testPersistedIdMapsToUserCacheNamespace() {
        // The persisted id, once seeded, yields the SAME identity string the disk
        // cache is partitioned by — so the seeded read hits the signed-in file.
        UserDefaults.standard.set("42", forKey: key)
        let id = try! XCTUnwrap(APIClient.persistedLastKnownUserId())
        XCTAssertEqual(DiscoverFeedCache.identity(userId: id, sessionId: "s1"), "user:42")
        // And absent → anonymous namespace, never a foreign user's file.
        XCTAssertEqual(DiscoverFeedCache.identity(userId: nil, sessionId: "s1"), "anon:s1")
    }
}
