import XCTest
@testable import Bain_Luck

/// L2-206 / #1472 Item 2 — the initial load's total budget is a REAL cancellable
/// deadline, not merely a retry-admission gate. Before L2-206 the six-second
/// budget only decided whether to admit a RETRY; the first `fetchDiscoverFeed`
/// itself was bounded solely by URLSession's 30/60s timeouts, so a suspended
/// request could hang far past the nominal budget with no late-publication guard.
/// These drive a client that suspends until cancelled to prove the deadline
/// actually cancels a stuck request at the budget — and that a cache seed survives.
@MainActor
final class DiscoverViewModelDeadlineTests: XCTestCase {

    // MARK: - Fakes

    /// Suspends every call until the enclosing task is cancelled (the deadline
    /// race cancels it). Records that a request was started so "exactly one
    /// attempt, then cancelled" is provable.
    private nonisolated final class HangingFakeClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var startCount = 0
        var starts: Int { lock.withLock { startCount } }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            lock.withLock { startCount += 1 }
            // Sleep far past any test budget; cancellation (from the deadline race)
            // makes Task.sleep throw, standing in for URLSession honoring cancel.
            try await Task.sleep(for: .seconds(3600))
            throw URLError(.badServerResponse) // unreachable
        }
    }

    private nonisolated final class FakeLastGood: DiscoverLastGoodReading, @unchecked Sendable {
        private let payload: CachedDiscoverFeed?
        init(_ payload: CachedDiscoverFeed?) { self.payload = payload }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
    }

    /// Fails the FIRST call retryably after consuming most of the budget, then
    /// would return a distinct marker on a SECOND call. Proves the exhausted-budget
    /// retry path never STARTS that second (unbounded) request (L2-208 Item 2 /
    /// C67 P1): the pre-fix `fetchWithinDeadline` had a `remaining <= 0` branch that
    /// returned a bare `client.fetchDiscoverFeed(...)` — bounded only by
    /// URLSession's 30/60s timeouts — recreating the very hang the total budget
    /// exists to prevent. On the fixed code the second call is never made
    /// (`calls == 1`); on the pre-fix code the exhausted branch issued it
    /// (`calls == 2`, marker data published).
    private nonisolated final class NearDeadlineFake: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var n = 0
        var calls: Int { lock.withLock { n } }
        private let firstDelay: TimeInterval
        private let second: FeedResponse
        init(firstDelay: TimeInterval, second: FeedResponse) {
            self.firstDelay = firstDelay; self.second = second
        }
        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            let c = lock.withLock { () -> Int in n += 1; return n }
            if c == 1 {
                // Consume most of the budget (well inside it, so the deadline race
                // does NOT cancel this attempt), then fail RETRYABLY (503).
                try await Task.sleep(for: .seconds(firstDelay))
                throw APIError.httpError(statusCode: 503, body: nil)
            }
            // A second request must never be started once the budget is exhausted.
            return second
        }
    }

    private func markerResponse() throws -> FeedResponse {
        let json = """
        {"items":[\(futuresJSON(999))],"total":1,"limit":50,"offset":0,"has_more":false}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d
    }

    private func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }

    private func cached(_ ids: [Int]) throws -> CachedDiscoverFeed {
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":9999,"limit":200,"offset":0,"has_more":true}
        """
        return CachedDiscoverFeed(
            response: try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8)),
            storedAt: ISO8601DateFormatter().date(from: "2026-07-28T12:00:00Z")!,
            ttlSeconds: 5, identity: "anon:s1")
    }

    // MARK: - Tests

    func testSuspendedRequestIsCancelledAtTotalBudgetWithNoCache() async throws {
        let fake = HangingFakeClient()
        // Small real budget so the test is fast; retryBackoff 0 so no retry sleeps.
        let vm = DiscoverViewModel(client: fake, lastGood: FakeLastGood(nil),
                                   telemetry: nil, retryBudget: 0.3, retryBackoff: 0)

        let started = Date()
        await vm.load()
        let elapsed = Date().timeIntervalSince(started)

        // The load returned in ~budget, NOT after the 3600s hang → the deadline
        // really cancelled the suspended request (the test would otherwise wedge).
        XCTAssertLessThan(elapsed, 3.0, "suspended request cancelled at the budget, not after 3600s")
        XCTAssertEqual(fake.starts, 1, "exactly one attempt was started (no retry after the deadline)")
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertEqual(vm.error, "Couldn't load feed", "no cache → honest error after the deadline")
        XCTAssertFalse(vm.loading)
    }

    func testSuspendedRevalidateCancelledButLastGoodPreserved() async throws {
        let fake = HangingFakeClient()
        let vm = DiscoverViewModel(client: fake, lastGood: FakeLastGood(try cached([1, 2, 3])),
                                   telemetry: nil, retryBudget: 0.3, retryBackoff: 0)

        let started = Date()
        await vm.load()
        let elapsed = Date().timeIntervalSince(started)

        XCTAssertLessThan(elapsed, 3.0, "revalidate cancelled at the budget")
        XCTAssertEqual(fake.starts, 1)
        // A first card from the cache seed survives — the timed-out revalidate must
        // never blank last-good, and surfaces the honest "couldn't refresh" state.
        XCTAssertEqual(vm.items.map { $0.futures?.id }, [1, 2, 3], "cache seed preserved through the deadline")
        XCTAssertTrue(vm.isShowingCachedContent)
        XCTAssertTrue(vm.refreshFailedShowingCache)
        XCTAssertEqual(vm.error, "Showing recent markets — couldn't refresh")
    }

    func testExhaustedRetryBudgetNeverStartsSecondUnboundedRequest() async throws {
        // budget 0.3s; first call fails retryably at 0.1s (remainder ~0.2s); backoff
        // 1.0s clamps to the remaining ~0.2s and consumes it → the next loop finds
        // the budget exhausted. The fixed code THROWS a non-retryable deadline error
        // there; the pre-fix code started an unbounded second request.
        let fake = NearDeadlineFake(firstDelay: 0.1, second: try markerResponse())
        let vm = DiscoverViewModel(client: fake, lastGood: FakeLastGood(nil),
                                   telemetry: nil, retryBudget: 0.3, retryBackoff: 1.0)

        let started = Date()
        await vm.load()
        let elapsed = Date().timeIntervalSince(started)

        XCTAssertEqual(fake.calls, 1,
            "the exhausted-budget retry must not start a second (unbounded) request")
        XCTAssertLessThan(elapsed, 3.0, "settled within the total budget — no unbounded hang")
        XCTAssertTrue(vm.items.isEmpty,
            "no cache and the retry threw → honest error, never the marker from call 2")
        XCTAssertEqual(vm.error, "Couldn't load feed")
        XCTAssertFalse(vm.loading)
    }
}
