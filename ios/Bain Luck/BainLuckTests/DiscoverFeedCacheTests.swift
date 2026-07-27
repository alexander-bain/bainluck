import XCTest
@testable import Bain_Luck

/// L2-197 / #1465 — the disk-backed last-good Discover feed cache. These pin the
/// contract the stale-while-revalidate path depends on: raw bytes round-trip
/// byte-for-byte (server order + probabilities preserved), payloads are
/// partitioned per identity and never cross an account/logout boundary, corrupt
/// or foreign entries fail closed, and TTL metadata is lifted honestly.
final class DiscoverFeedCacheTests: XCTestCase {

    private var dir: URL!
    private var cache: DiscoverFeedCache!

    override func setUpWithError() throws {
        dir = FileManager.default.temporaryDirectory
            .appendingPathComponent("DiscoverFeedCacheTests-\(UUID().uuidString)", isDirectory: true)
        cache = DiscoverFeedCache(directory: dir)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: dir)
    }

    // A raw `/api/feed` body with a known card order, probabilities, and optional
    // `cache.ttl_seconds` — the exact shape the server sends and the cache stores.
    private func rawBody(
        ids: [Int],
        probabilities: [Int: Double] = [:],
        hasMore: Bool = true,
        ttlSeconds: Double? = nil
    ) -> Data {
        let items = ids.map { id -> String in
            let p = probabilities[id] ?? 0.5
            return """
            {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":\(p),"rank":1,"movement":0.02}],"outcome_count":1}}
            """
        }.joined(separator: ",")
        let ttl = ttlSeconds.map { ",\"cache\":{\"ttl_seconds\":\($0)}" } ?? ""
        let json = """
        {"items":[\(items)],"total":9999,"limit":200,"offset":0,"has_more":\(hasMore)\(ttl)}
        """
        return Data(json.utf8)
    }

    private let storedAt = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!

    // MARK: - Round-trip byte fidelity

    func testStoreThenLoadPreservesOrderAndProbabilities() throws {
        let raw = rawBody(ids: [3, 1, 2], probabilities: [3: 0.61, 1: 0.44, 2: 0.9], hasMore: true)
        cache.store(rawBody: raw, identity: "anon:s1", storedAt: storedAt)

        let cached = try XCTUnwrap(cache.load(identity: "anon:s1"))
        XCTAssertEqual(cached.response.items.map { $0.futures?.id }, [3, 1, 2],
                       "server card order preserved byte-for-byte")
        XCTAssertEqual(cached.response.items.map { $0.futures?.topOutcomes?.first?.probability },
                       [0.61, 0.44, 0.9], "probabilities preserved exactly")
        XCTAssertEqual(cached.response.hasMore, true)
        XCTAssertEqual(cached.storedAt, storedAt)
        XCTAssertEqual(cached.identity, "anon:s1")
    }

    func testLoadExtractsTTLSeconds() throws {
        cache.store(rawBody: rawBody(ids: [1], ttlSeconds: 42), identity: "anon:s1", storedAt: storedAt)
        let cached = try XCTUnwrap(cache.load(identity: "anon:s1"))
        XCTAssertEqual(cached.ttlSeconds, 42)
    }

    func testLoadToleratesMissingTTL() throws {
        cache.store(rawBody: rawBody(ids: [1], ttlSeconds: nil), identity: "anon:s1", storedAt: storedAt)
        let cached = try XCTUnwrap(cache.load(identity: "anon:s1"))
        XCTAssertNil(cached.ttlSeconds, "no cache.ttl_seconds → nil, not a decode failure")
        XCTAssertEqual(cached.response.items.count, 1)
    }

    func testAgeComputedFromStoredAt() throws {
        cache.store(rawBody: rawBody(ids: [1]), identity: "anon:s1", storedAt: storedAt)
        let cached = try XCTUnwrap(cache.load(identity: "anon:s1"))
        let now = storedAt.addingTimeInterval(120)
        XCTAssertEqual(cached.age(now: now), 120, accuracy: 0.001)
    }

    // MARK: - Identity partitioning (no cross-account leakage)

    func testLoadWithDifferentIdentityReturnsNil() {
        cache.store(rawBody: rawBody(ids: [1]), identity: "user:5", storedAt: storedAt)
        XCTAssertNil(cache.load(identity: "user:6"), "user 6 must not see user 5's feed")
        XCTAssertNil(cache.load(identity: "anon:s1"), "signed-out must not see a signed-in feed")
        XCTAssertNotNil(cache.load(identity: "user:5"), "owner still reads its own")
    }

    func testDistinctIdentitiesCoexist() throws {
        cache.store(rawBody: rawBody(ids: [1]), identity: "user:5", storedAt: storedAt)
        cache.store(rawBody: rawBody(ids: [2]), identity: "anon:s1", storedAt: storedAt)
        XCTAssertEqual(try XCTUnwrap(cache.load(identity: "user:5")).response.items.first?.futures?.id, 1)
        XCTAssertEqual(try XCTUnwrap(cache.load(identity: "anon:s1")).response.items.first?.futures?.id, 2)
    }

    // MARK: - Eviction (logout / account switch)

    func testEvictKeepingOnlyRemovesOtherNamespaces() {
        cache.store(rawBody: rawBody(ids: [1]), identity: "user:5", storedAt: storedAt)
        cache.store(rawBody: rawBody(ids: [2]), identity: "anon:s1", storedAt: storedAt)

        cache.evict(keepingOnly: "user:5")   // e.g. a fresh login evicting anon

        XCTAssertNotNil(cache.load(identity: "user:5"), "kept identity survives")
        XCTAssertNil(cache.load(identity: "anon:s1"), "other identity evicted on switch")
    }

    func testEvictKeepingNilRemovesAll() {
        cache.store(rawBody: rawBody(ids: [1]), identity: "user:5", storedAt: storedAt)
        cache.store(rawBody: rawBody(ids: [2]), identity: "anon:s1", storedAt: storedAt)

        cache.evict(keepingOnly: nil)

        XCTAssertNil(cache.load(identity: "user:5"))
        XCTAssertNil(cache.load(identity: "anon:s1"))
    }

    // MARK: - Fail closed

    func testMissingEntryReturnsNil() {
        XCTAssertNil(cache.load(identity: "anon:never-stored"))
    }

    func testCorruptEntryFailsClosedAndIsDeleted() throws {
        cache.store(rawBody: rawBody(ids: [1]), identity: "anon:s1", storedAt: storedAt)
        // Corrupt the on-disk file without needing the private filename derivation.
        let files = try FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)
        let file = try XCTUnwrap(files.first { $0.pathExtension == "json" })
        try Data("{not valid json".utf8).write(to: file)

        XCTAssertNil(cache.load(identity: "anon:s1"), "corrupt entry never served")
        XCTAssertFalse(FileManager.default.fileExists(atPath: file.path), "corrupt entry deleted")
    }

    func testEmptyItemsPayloadStillDecodes() throws {
        cache.store(rawBody: rawBody(ids: []), identity: "anon:s1", storedAt: storedAt)
        let cached = try XCTUnwrap(cache.load(identity: "anon:s1"))
        XCTAssertTrue(cached.response.items.isEmpty, "empty-but-valid payload is not a corrupt entry")
    }

    // MARK: - Identity helper

    func testIdentityHelper() {
        XCTAssertEqual(DiscoverFeedCache.identity(userId: "5", sessionId: "s1"), "user:5")
        XCTAssertEqual(DiscoverFeedCache.identity(userId: nil, sessionId: "s1"), "anon:s1")
        XCTAssertEqual(DiscoverFeedCache.identity(userId: "", sessionId: "s1"), "anon:s1",
                       "empty user id is treated as anonymous")
    }
}
