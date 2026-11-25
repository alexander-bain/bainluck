import XCTest
@testable import Bain_Luck

/// 1.0.8 Item 3 — When Discover continuation receives a mismatched edition
/// (e.g. `limit=200&offset=20` with `has_more: false` vs `page_base_stale_hit`),
/// recover once instead of silently dropping all continuation cards and claiming
/// "You're all caught up" after item 19.
final class DiscoverEditionSkew108Tests: XCTestCase {

    private nonisolated final class ScriptedFeedClient108: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var responses: [FeedResponse]
        private var recordedRequests: [(limit: Int, offset: Int, edition: String?)] = []

        init(_ responses: [FeedResponse]) {
            self.responses = responses
        }

        var requests: [(limit: Int, offset: Int, edition: String?)] {
            lock.withLock { recordedRequests }
        }

        nonisolated func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            try await fetchDiscoverFeed(
                limit: limit,
                offset: offset,
                eventPct: eventPct,
                edition: nil,
                cacheTTL: cacheTTL
            )
        }

        nonisolated func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            edition: String?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            try lock.withLock {
                recordedRequests.append((limit, offset, edition))
                guard !responses.isEmpty else {
                    throw APIError.httpError(statusCode: 500, body: nil)
                }
                return responses.removeFirst()
            }
        }
    }

    private static func makeFuturesJSON(id: Int) -> String {
        """
        {
          "type": "futures",
          "score": 80,
          "data": {
            "id": \(id),
            "name": "Market \(id)",
            "llm_sport_category": "economics",
            "source": "kalshi",
            "status": "open",
            "market_tier": 2,
            "outcome_count": 1,
            "top_outcomes": [
              { "id": \(id * 10), "name": "Yes", "probability": 0.55, "rank": 1 }
            ]
          }
        }
        """
    }

    private static func decodePage(
        ids: [Int],
        offset: Int,
        limit: Int,
        total: Int,
        hasMore: Bool,
        edition: String?
    ) throws -> FeedResponse {
        let itemsJSON = ids.map(makeFuturesJSON).joined(separator: ",")
        let ed = edition.map { #""edition":"\#($0)","# } ?? ""
        let json = """
        {
          "items": [\(itemsJSON)],
          "total": \(total),
          "limit": \(limit),
          "offset": \(offset),
          "has_more": \(hasMore ? "true" : "false"),
          \(ed)
          "degraded": false
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedResponse.self, from: Data(json.utf8))
    }

    @MainActor
    func testUnseatedOffset20SkewRecoversOnceInsteadOfStoppingAtItem19() async throws {
        // Page 0: edition A, 20 items (`1...20`), more available (`has_more: true`).
        // Page 1 (unpinned offset=20): mismatched edition B with `has_more: false`.
        // Recovery (offset=0 unpinned): edition B (`1...20`, `has_more: true`), then next page (`21...30`).
        let page0 = try Self.decodePage(
            ids: Array(1...20), offset: 0, limit: 20, total: 60, hasMore: true, edition: "ed-a"
        )
        let skewedPage1 = try Self.decodePage(
            ids: Array(21...45), offset: 20, limit: 200, total: 45, hasMore: false, edition: "ed-b"
        )
        let recoveredPage0 = try Self.decodePage(
            ids: Array(1...20) + [21, 22], offset: 0, limit: 20, total: 45, hasMore: true, edition: "ed-b"
        )

        let fake = ScriptedFeedClient108([page0, skewedPage1, recoveredPage0])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = false

        await vm.load()
        XCTAssertEqual(vm.items.compactMap(\.futures?.id), Array(1...20))
        XCTAssertTrue(vm.hasMore)

        await vm.loadMoreIfNeeded()
        XCTAssertTrue(vm.hasMore, "edition skew must recover to continuation instead of prematurely ending at item 19")
        let loadedIDs = vm.items.compactMap(\.futures?.id)
        XCTAssertEqual(Array(loadedIDs.prefix(20)), Array(1...20), "painted items stay in place")
        XCTAssertTrue(loadedIDs.contains(21))
        XCTAssertTrue(loadedIDs.contains(22))
    }

    @MainActor
    func testSkewRecoveryIsBoundedToOneAttemptWhenMismatchPersists() async throws {
        let page0 = try Self.decodePage(
            ids: Array(1...20), offset: 0, limit: 20, total: 60, hasMore: true, edition: "ed-a"
        )
        let skewed1 = try Self.decodePage(
            ids: Array(21...40), offset: 20, limit: 200, total: 60, hasMore: false, edition: "ed-b"
        )
        let recoveryBackToA = try Self.decodePage(
            ids: Array(1...20), offset: 0, limit: 20, total: 60, hasMore: true, edition: "ed-a"
        )
        let skewed2 = try Self.decodePage(
            ids: Array(41...60), offset: 20, limit: 200, total: 60, hasMore: false, edition: "ed-c"
        )

        let fake = ScriptedFeedClient108([page0, skewed1, recoveryBackToA, skewed2])
        let vm = DiscoverViewModel(client: fake, lastGood: nil, telemetry: nil)
        vm.openingEditionEnabled = false

        await vm.load()
        await vm.loadMoreIfNeeded()
        let countAfterFirstSkew = fake.requests.count
        XCTAssertEqual(countAfterFirstSkew, 3, "only one replacement load should fire on first skew")

        // Second persistent skew must terminate rather than recursing forever.
        await vm.loadMoreIfNeeded()
        XCTAssertEqual(fake.requests.count, 4)
        XCTAssertFalse(vm.hasMore)
    }
}
