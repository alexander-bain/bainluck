import XCTest
@testable import Bain_Luck

/// #3180 — the cold-start failure screen heals itself.
///
/// Measured on master 2026-09-05, first cold launch after a simulator erase:
/// `GET /api/feed?limit=50` answered **200 in 7.08s**, one second past the 6s
/// empty-screen budget, so Discover drew "Couldn't load feed" over a response that
/// was already in flight — and then sat there until a human tapped Retry. The very
/// next launch on the same build loaded normally, because the server's response
/// cache had warmed. Server-side the failed launch is invisible: it returned 200.
///
/// The fix does NOT lengthen the budget — Q425's short empty-screen budget is a
/// standing decision and it is still right, because it bounds how long a reader
/// stares at a spinner. It removes the other half of the defect: that the honest
/// error was TERMINAL. These pin the contract of the recovery ladder that replaces
/// it — it runs only on an empty screen, it is bounded, it stops the moment cards
/// land, and any caller-initiated load supersedes it.
@MainActor
final class DiscoverColdStartRecoveryTests: XCTestCase {

    // MARK: - Fakes

    /// Hangs on the first `hangingCalls` calls (the deadline race cancels each at
    /// the budget, exactly as a 7.1s response does against a 6s ceiling), then
    /// returns `response` — the warmed-cache launch that follows.
    private nonisolated final class HangThenSucceedFake: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var n = 0
        var calls: Int { lock.withLock { n } }
        private let hangingCalls: Int
        private let response: FeedResponse

        init(hangingCalls: Int, response: FeedResponse) {
            self.hangingCalls = hangingCalls
            self.response = response
        }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            let c = lock.withLock { () -> Int in n += 1; return n }
            if c <= hangingCalls {
                // Far past any test budget; the deadline race cancels it, standing in
                // for a URLSession request the client gives up on.
                try await Task.sleep(for: .seconds(3600))
            }
            return response
        }
    }

    private nonisolated final class FakeLastGood: DiscoverLastGoodReading, @unchecked Sendable {
        private let payload: CachedDiscoverFeed?
        init(_ payload: CachedDiscoverFeed?) { self.payload = payload }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
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

    private func response(_ ids: [Int]) throws -> FeedResponse {
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":\(ids.count),"limit":50,"offset":0,"has_more":false}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func cached(_ ids: [Int]) throws -> CachedDiscoverFeed {
        CachedDiscoverFeed(
            response: try response(ids),
            storedAt: ISO8601DateFormatter().date(from: "2026-09-04T12:00:00Z")!,
            ttlSeconds: 5, identity: "anon:s1")
    }

    /// Poll until `condition` holds or `timeout` elapses. The ladder runs on its own
    /// task, so the assertion has to wait for it rather than assume a fixed sleep.
    private func waitUntil(
        _ timeout: TimeInterval = 3, _ condition: () -> Bool
    ) async -> Bool {
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            if condition() { return true }
            try? await Task.sleep(for: .milliseconds(20))
        }
        return condition()
    }

    // MARK: - Tests

    /// The #3180 case end to end: the first attempt burns the budget, the honest
    /// error is drawn immediately — and then the feed appears on its own, with
    /// nobody tapping anything.
    func testSlowFirstAttemptHealsWithoutATap() async throws {
        let fake = HangThenSucceedFake(hangingCalls: 1, response: try response([1, 2, 3]))
        let vm = DiscoverViewModel(
            client: fake, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 0.2, retryBackoff: 0, autoRecoveryDelays: [0.05])

        await vm.load()

        // Q425 is intact: the reader is told the truth inside the short budget.
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertEqual(vm.error, "Couldn't load feed", "the honest error still comes fast")
        XCTAssertFalse(vm.loading)
        XCTAssertTrue(vm.isRecovering, "…but the app has not given up, and says so")

        let healed = await waitUntil { !vm.items.isEmpty }
        XCTAssertTrue(healed, "the ladder's own attempt published the feed with no tap")
        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, [1, 2, 3])
        XCTAssertNil(vm.error, "the failure card is gone once cards land")
        XCTAssertFalse(vm.isRecovering, "the ladder stops the moment it succeeds")
        XCTAssertEqual(fake.calls, 2, "one initial attempt plus exactly one recovery attempt")
    }

    /// A dark network settles where it settles today. The ladder is bounded: it does
    /// not become a retry storm against a server that is down.
    func testLadderIsBoundedAndSettlesToTheSameHonestError() async throws {
        let fake = HangThenSucceedFake(hangingCalls: 99, response: try response([1]))
        let vm = DiscoverViewModel(
            client: fake, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 0.1, retryBackoff: 0, autoRecoveryDelays: [0.05, 0.05])

        await vm.load()
        let finished = await waitUntil { !vm.isRecovering }

        XCTAssertTrue(finished, "the ladder ended rather than retrying forever")
        XCTAssertEqual(fake.calls, 3, "one initial attempt plus the two configured rungs — no more")
        XCTAssertEqual(vm.error, "Couldn't load feed", "the terminal state is unchanged")
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertFalse(vm.loading)

        // And it stays ended: no rung fires after the ladder is spent.
        try? await Task.sleep(for: .milliseconds(200))
        XCTAssertEqual(fake.calls, 3)
    }

    /// Never reload from under a reader who has content. A kept last-good cache has
    /// its own honest "showing recent — couldn't refresh" banner; the ladder is for
    /// the empty screen only.
    func testCacheOnScreenIsNeverRecoveredOver() async throws {
        let fake = HangThenSucceedFake(hangingCalls: 99, response: try response([9]))
        let vm = DiscoverViewModel(
            client: fake, lastGood: FakeLastGood(try cached([7, 8])), telemetry: nil,
            retryBudget: 0.1, seededRetryBudget: 0.1, retryBackoff: 0,
            autoRecoveryDelays: [0.05, 0.05])

        await vm.load()

        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, [7, 8], "last-good stayed put")
        XCTAssertTrue(vm.refreshFailedShowingCache)
        XCTAssertFalse(vm.isRecovering, "content on screen → no recovery ladder")

        let callsAfterLoad = fake.calls
        try? await Task.sleep(for: .milliseconds(250))
        XCTAssertEqual(fake.calls, callsAfterLoad, "no rung ever fired behind the cached feed")
    }

    /// The newest load owns the feed. A Retry tap / pull-to-refresh / identity rebind
    /// supersedes a ladder mid-countdown instead of racing it.
    func testCallerInitiatedLoadCancelsTheLadder() async throws {
        let fake = HangThenSucceedFake(hangingCalls: 1, response: try response([4, 5]))
        let vm = DiscoverViewModel(
            client: fake, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 0.2, retryBackoff: 0, autoRecoveryDelays: [5])

        await vm.load()
        XCTAssertTrue(vm.isRecovering, "a ladder is counting down behind the error")

        // The reader does not wait for the 5s rung — they tap Retry.
        await vm.load()

        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, [4, 5])
        XCTAssertFalse(vm.isRecovering, "the tap superseded the ladder")
        XCTAssertEqual(fake.calls, 2, "the cancelled rung never issued a third request")

        try? await Task.sleep(for: .milliseconds(150))
        XCTAssertEqual(fake.calls, 2, "and it stayed cancelled")
    }

    /// An empty ladder is the opt-out the existing deadline / SWR suites rely on:
    /// the terminal state is exactly what it was before #3180.
    func testEmptyLadderMeansNoRecovery() async throws {
        let fake = HangThenSucceedFake(hangingCalls: 1, response: try response([1]))
        let vm = DiscoverViewModel(
            client: fake, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 0.1, retryBackoff: 0, autoRecoveryDelays: [])

        await vm.load()

        XCTAssertEqual(vm.error, "Couldn't load feed")
        XCTAssertFalse(vm.isRecovering)
        try? await Task.sleep(for: .milliseconds(200))
        XCTAssertEqual(fake.calls, 1, "no ladder, no second request")
        XCTAssertTrue(vm.items.isEmpty)
    }

    /// The production default is a real ladder, not an empty one. #3157's scaffold
    /// went silently inert for weeks because nothing pinned it; this is the same
    /// class of mistake, so it gets the same kind of guard.
    func testProductionDefaultShipsANonEmptyLadder() async throws {
        let fake = HangThenSucceedFake(hangingCalls: 1, response: try response([1]))
        // Default `autoRecoveryDelays` — the shipping value.
        let vm = DiscoverViewModel(
            client: fake, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 0.1, retryBackoff: 0)

        await vm.load()

        XCTAssertTrue(vm.isRecovering,
                      "the shipping build recovers by default — an empty default would be inert")
    }
}
