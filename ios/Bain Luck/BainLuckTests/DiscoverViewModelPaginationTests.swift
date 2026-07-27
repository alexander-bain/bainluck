import XCTest
@testable import Bain_Luck

/// L2-192 Item 2 / C26 P2 — `DiscoverViewModel` pagination must always terminate
/// in one of three honest states (new cards, honest exhaustion, or a retryable
/// error) and never sit on an indefinite "Finding fresh markets…" spinner.
///
/// These drive the view model through a deterministic fake feed client (the
/// `DiscoverFeedProviding` seam) so offsets, `hasMore`, duplicate-only pages,
/// decoded-empty pages, failures, cancellation, and concurrent calls are all
/// exercised — none of which a pure predicate test can reach.
final class DiscoverViewModelPaginationTests: XCTestCase {

    // MARK: - Fake client

    private enum Reply {
        case ok(FeedResponse)
        case fail(Error)
    }

    /// Nonisolated (off-MainActor) fake so `fetchDiscoverFeed` genuinely suspends
    /// when awaited from the MainActor view model — required for the concurrency
    /// guard test. State is lock-guarded (`@unchecked Sendable`).
    private nonisolated final class FakeFeedClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var script: [Reply]
        private var offsets: [Int] = []

        init(_ script: [Reply]) { self.script = script }

        var requestedOffsets: [Int] { lock.withLock { offsets } }

        func reset() { lock.withLock { offsets.removeAll() } }

        nonisolated func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            // Yield first so a concurrent second call observes loadingMore=true
            // before this one records its request.
            await Task.yield()
            return try lock.withLock {
                offsets.append(offset)
                guard !script.isEmpty else {
                    // Safety default: honest exhaustion so an over-scan can't crash.
                    return try DiscoverViewModelPaginationTests.emptyResponse(offset: offset, hasMore: false)
                }
                switch script.removeFirst() {
                case .ok(let r): return r
                case .fail(let e): throw e
                }
            }
        }
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private static func futuresJSON(id: Int, probability: Double = 0.55) -> String {
        """
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Market \(id)?",
            "llm_sport_category": "economics",
            "source": "kalshi",
            "status": "open",
            "top_outcomes": [{"id": \(id * 10), "name": "A", "probability": \(probability), "rank": 1, "movement": 0.02}],
            "outcome_count": 1
          }
        }
        """
    }

    private static func response(ids: [Int], offset: Int, hasMore: Bool) throws -> FeedResponse {
        let items = ids.map { futuresJSON(id: $0) }.joined(separator: ",")
        let json = """
        {"items":[\(items)],"total":9999,"limit":200,"offset":\(offset),"has_more":\(hasMore)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private static func emptyResponse(offset: Int, hasMore: Bool) throws -> FeedResponse {
        let json = """
        {"items":[],"total":9999,"limit":200,"offset":\(offset),"has_more":\(hasMore)}
        """
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// Initial load page with enough renderable items (>10) that `load()` takes
    /// the primary path and does not trigger its low-count fallback fetch.
    private static func initialPage(hasMore: Bool = true) throws -> FeedResponse {
        try response(ids: Array(1...12), offset: 0, hasMore: hasMore)
    }

    /// Build a VM already past initial load, with the fake's call log cleared so
    /// pagination-offset assertions start from a clean slate.
    @MainActor
    private func loadedVM(_ replies: [Reply]) async throws -> (DiscoverViewModel, FakeFeedClient) {
        let fake = FakeFeedClient([.ok(try Self.initialPage())] + replies)
        let vm = DiscoverViewModel(client: fake)
        await vm.load()
        XCTAssertFalse(vm.loading, "initial load should clear loading")
        XCTAssertEqual(vm.items.count, 12, "initial page should populate 12 items")
        fake.reset()
        return (vm, fake)
    }

    // MARK: - Tests

    @MainActor
    func testNewEligiblePageAppendsCards() async throws {
        let (vm, fake) = try await loadedVM([
            .ok(try Self.response(ids: [500], offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertEqual(vm.items.count, 13)
        XCTAssertTrue(vm.hasMore)
        XCTAssertNil(vm.error)
        let offsets = fake.requestedOffsets
        XCTAssertEqual(offsets, [12], "should fetch exactly the next page, not offset 0")
    }

    @MainActor
    func testDistinctAllStalePagesThenExhaustion() async throws {
        // Each page has NEW ids (so items.count grows and the view would retrigger)
        // and the final page reports no more — pagination must reach hasMore=false.
        let (vm, _) = try await loadedVM([
            .ok(try Self.response(ids: [100, 101, 102], offset: 12, hasMore: true)),
            .ok(try Self.response(ids: [200, 201, 202], offset: 15, hasMore: false)),
        ])
        await vm.loadMoreIfNeeded()   // page A appended, hasMore still true
        XCTAssertTrue(vm.hasMore)
        XCTAssertEqual(vm.items.count, 15)

        await vm.loadMoreIfNeeded()   // page B appended, server says done
        XCTAssertFalse(vm.hasMore, "must terminate as caught-up")
        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.items.count, 18)
    }

    @MainActor
    func testDuplicateOnlyPagesSurfaceRetry() async throws {
        // Every page returns only already-loaded ids (1...12) but the server keeps
        // claiming hasMore=true and the offset advances each page. The paginator
        // must scan a bounded window then surface a retryable error — never spin.
        var replies: [Reply] = []
        for k in 1...6 {
            replies.append(.ok(try Self.response(ids: Array(1...12), offset: 12 * k, hasMore: true)))
        }
        let (vm, fake) = try await loadedVM(replies)
        await vm.loadMoreIfNeeded()

        XCTAssertNotNil(vm.error, "bounded duplicate scan must expose a retryable error")
        XCTAssertTrue(vm.hasMore, "server still claims more; not a false exhaustion")
        XCTAssertEqual(vm.items.count, 12, "no duplicate content appended")
        let offsets = fake.requestedOffsets
        XCTAssertFalse(offsets.contains(0), "must never refetch offset 0")
        XCTAssertEqual(offsets, offsets.sorted(), "offset must advance monotonically")
        XCTAssertEqual(Set(offsets).count, offsets.count, "no repeated offset")
    }

    @MainActor
    func testDecodedEmptyPageWithHasMoreTerminates() async throws {
        // Server claims hasMore=true but returns an empty page (offset can't
        // advance) — treat as honest exhaustion, not a permanent spinner.
        let (vm, fake) = try await loadedVM([
            .ok(try Self.emptyResponse(offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertFalse(vm.hasMore, "decoded-empty page must terminate as caught-up")
        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.items.count, 12)
        let offsets = fake.requestedOffsets
        XCTAssertEqual(offsets, [12])
    }

    @MainActor
    func testRequestFailureThenRetrySucceeds() async throws {
        let (vm, _) = try await loadedVM([
            .fail(URLError(.timedOut)),
            .ok(try Self.response(ids: [500], offset: 12, hasMore: true)),
        ])
        await vm.loadMoreIfNeeded()
        XCTAssertNotNil(vm.error, "network failure must surface a retryable error")
        XCTAssertEqual(vm.items.count, 12, "no partial content on failure")
        XCTAssertTrue(vm.hasMore)

        await vm.loadMoreIfNeeded()   // retry
        XCTAssertNil(vm.error, "successful retry clears the error")
        XCTAssertEqual(vm.items.count, 13)
    }

    @MainActor
    func testCancellationLeavesStateClean() async throws {
        let (vm, _) = try await loadedVM([
            .fail(CancellationError()),
        ])
        await vm.loadMoreIfNeeded()

        XCTAssertNil(vm.error, "cancellation is not a user-facing error")
        XCTAssertTrue(vm.hasMore, "cancellation leaves pagination retryable")
        XCTAssertEqual(vm.items.count, 12)
        XCTAssertFalse(vm.loadingMore)
    }

    @MainActor
    func testConcurrentCallsIssueSingleRequest() async throws {
        let (vm, fake) = try await loadedVM([
            .ok(try Self.response(ids: [500], offset: 12, hasMore: true)),
        ])
        async let a: Void = vm.loadMoreIfNeeded()
        async let b: Void = vm.loadMoreIfNeeded()
        _ = await (a, b)

        let offsets = fake.requestedOffsets
        XCTAssertEqual(offsets.count, 1, "concurrent loadMore must not double-fetch")
        XCTAssertEqual(vm.items.count, 13)
    }
}
