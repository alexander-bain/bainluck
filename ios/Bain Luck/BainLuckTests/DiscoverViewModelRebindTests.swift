import XCTest
@testable import Bain_Luck

/// L2-206 / #1472 Item 1 — `DiscoverViewModel.rebindForIdentityChange()` on an
/// auth transition (login, logout, account switch, or a failed restore dropping
/// back to anonymous). The prior identity's in-memory cards must be cleared and
/// the new identity reloaded before any of the old cards can be presented, and a
/// still-in-flight load from the prior identity must never overwrite the new one.
@MainActor
final class DiscoverViewModelRebindTests: XCTestCase {

    // MARK: - Fakes

    private enum Reply { case ok(FeedResponse); case fail(Error) }

    private nonisolated final class RecordingFakeClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var script: [Reply]
        private var count = 0
        init(_ script: [Reply]) { self.script = script }
        var callCount: Int { lock.withLock { count } }
        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            await Task.yield()
            return try lock.withLock {
                count += 1
                guard !script.isEmpty else { throw URLError(.badServerResponse) }
                switch script.removeFirst() {
                case .ok(let r): return r
                case .fail(let e): throw e
                }
            }
        }
    }

    /// First call blocks on the gate (and signals its arrival deterministically so
    /// the test can order the two loads without a scheduling race); later calls
    /// return immediately. Lets a prior identity's in-flight load's late response
    /// land AFTER the rebind published.
    private nonisolated final class GatedFakeClient: DiscoverFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private var n = 0
        private var gate: CheckedContinuation<Void, Never>?
        private var opened = false
        private let first: FeedResponse
        private let second: FeedResponse
        /// Fulfilled the moment the FIRST call parks on the gate, so the test can
        /// start the second load only once the first is genuinely in-flight.
        let firstCallArrived: XCTestExpectation
        init(first: FeedResponse, second: FeedResponse, firstCallArrived: XCTestExpectation) {
            self.first = first; self.second = second; self.firstCallArrived = firstCallArrived
        }
        func openGate() { lock.withLock { opened = true; gate?.resume(); gate = nil } }
        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            let c = lock.withLock { () -> Int in n += 1; return n }
            if c == 1 {
                await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                    let shouldSignal: Bool = lock.withLock {
                        if opened { cont.resume(); return false }
                        gate = cont; return true
                    }
                    if shouldSignal { firstCallArrived.fulfill() }
                }
                return first
            }
            return second
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
    private func response(ids: [Int]) throws -> FeedResponse {
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":9999,"limit":50,"offset":0,"has_more":true}
        """
        return try Self.decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    // MARK: - Tests

    func testRebindClearsPriorIdentityItemsAndReloadsNewIdentity() async throws {
        // Load A (identity 1), then rebind (identity 2) → B replaces A entirely.
        let fake = RecordingFakeClient([.ok(try response(ids: Array(1...5))),
                                        .ok(try response(ids: Array(100...104)))])
        let vm = DiscoverViewModel(client: fake, lastGood: FakeLastGood(nil), telemetry: nil)

        await vm.load()
        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(1...5), "identity 1's feed loaded")

        await vm.rebindForIdentityChange()

        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(100...104),
                       "identity 2's feed replaced identity 1's — no old cards remain")
        XCTAssertEqual(fake.callCount, 2, "rebind issued exactly one reload")
        XCTAssertFalse(vm.isShowingCachedContent)
        XCTAssertNil(vm.error)
        XCTAssertFalse(vm.loading)
    }

    func testRebindResetsCacheAndErrorStateBeforeReload() async throws {
        // Prior state: showing cache after a failed refresh. Rebind must not carry
        // that identity's cache flags/banner into the new identity.
        let fake = RecordingFakeClient([.fail(URLError(.notConnectedToInternet)),
                                        .ok(try response(ids: Array(200...203)))])
        let seed = CachedDiscoverFeed(response: try response(ids: [9]),
                                      storedAt: ISO8601DateFormatter().date(from: "2026-07-28T12:00:00Z")!,
                                      ttlSeconds: 5, identity: "user:1")
        let vm = DiscoverViewModel(client: fake, lastGood: FakeLastGood(seed),
                                   telemetry: nil, retryBudget: 0)

        await vm.load()
        XCTAssertTrue(vm.refreshFailedShowingCache, "identity 1 ended on a kept-cache banner")

        await vm.rebindForIdentityChange()

        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, Array(200...203))
        XCTAssertFalse(vm.refreshFailedShowingCache, "the prior identity's banner did not leak")
        XCTAssertFalse(vm.isShowingCachedContent)
        XCTAssertNil(vm.error)
    }

    func testInFlightPriorLoadCannotOverwriteRebind() async throws {
        // Prior-identity load A is suspended; rebind (identity 2) loads B and
        // publishes. When A's late response finally lands it must be discarded.
        let aContent = try response(ids: Array(1...5))
        let bContent = try response(ids: Array(100...104))
        let arrived = expectation(description: "prior-identity load reached the gate")
        let fake = GatedFakeClient(first: aContent, second: bContent, firstCallArrived: arrived)
        // Large budget so the total-load deadline never fires during the gate wait
        // (this test exercises supersession, not the deadline).
        let vm = DiscoverViewModel(client: fake, lastGood: FakeLastGood(nil),
                                   telemetry: nil, retryBudget: 30)

        async let a: Void = vm.load()          // identity 1 — parks on the gate
        await fulfillment(of: [arrived], timeout: 5)  // A is deterministically in-flight
        await vm.rebindForIdentityChange()     // identity 2 — loads B (call 2), publishes

        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(100...104), "new identity B published")

        fake.openGate()                        // A's late response returns now
        await a

        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(100...104),
                       "the prior identity's late response was discarded — no cross-identity overwrite")
    }
}
