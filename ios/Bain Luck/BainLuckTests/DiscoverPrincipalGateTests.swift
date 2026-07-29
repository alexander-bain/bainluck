import XCTest
@testable import Bain_Luck

/// L2-210 / C72 — Native Discover principal + render-generation integrity.
///
/// Adversarial lifecycle coverage for the two correctness gaps L2-208/L2-209 left
/// open on the returning-user cold path:
///   • Item 1 — no anonymous network response may PUBLISH over a signed-in user's
///     optimistic cache while auth restoration is unresolved. The response is
///     discarded and the bounded retry budget re-fetches under the resolved
///     principal (authenticated → publishes, or restore-to-anonymous → publishes).
///   • Item 2 — the on-screen first-render telemetry is bound to an IMMUTABLE
///     generation token (its own provenance + bounded item count), so a later
///     generation, a same-card-ID replacement, navigation, or a model mutation
///     between data-ready and the render callback can never make the emitted event
///     describe another generation.
///
/// These exercise the pure decision cores AND drive `DiscoverViewModel` through a
/// principal-modeling fake so the discard-and-retry actually runs.
@MainActor
final class DiscoverPrincipalGateTests: XCTestCase {

    // MARK: - Fakes

    /// A feed client that models the request/namespace principal, replaying a
    /// script of `(response, wasAuthenticated, expectedSignedIn)`. The last reply is
    /// held for any extra retries so a test never runs off the end of the script.
    private nonisolated final class PrincipalFakeClient: DiscoverFeedProviding, @unchecked Sendable {
        struct Reply { let response: FeedResponse; let wasAuthenticated: Bool; let expectedSignedIn: Bool }
        private let lock = NSLock()
        private var script: [Reply]
        private var count = 0
        init(_ script: [Reply]) { precondition(!script.isEmpty); self.script = script }
        var callCount: Int { lock.withLock { count } }

        nonisolated func fetchDiscoverFeed(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            try await fetchDiscoverFeedResolvingPrincipal(
                limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL).response
        }

        nonisolated func fetchDiscoverFeedResolvingPrincipal(
            limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
        ) async throws -> DiscoverFeedFetchResult {
            await Task.yield()
            return lock.withLock {
                count += 1
                let reply = script.count > 1 ? script.removeFirst() : script[0]
                return DiscoverFeedFetchResult(
                    response: reply.response,
                    wasAuthenticated: reply.wasAuthenticated,
                    expectedSignedIn: reply.expectedSignedIn)
            }
        }
    }

    private nonisolated final class FakeLastGood: DiscoverLastGoodReading, @unchecked Sendable {
        private let payload: CachedDiscoverFeed?
        init(_ payload: CachedDiscoverFeed?) { self.payload = payload }
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { payload }
    }

    private nonisolated final class TelemetrySink: @unchecked Sendable {
        private let lock = NSLock()
        private var events: [DiscoverFeedTelemetry] = []
        func record(_ e: DiscoverFeedTelemetry) { lock.withLock { events.append(e) } }
        var outcomes: [DiscoverFeedTelemetry.Outcome] { lock.withLock { events.map(\.outcome) } }
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
    private func cached(_ ids: [Int], identity: String) throws -> CachedDiscoverFeed {
        CachedDiscoverFeed(
            response: try response(ids: ids),
            storedAt: ISO8601DateFormatter().date(from: "2026-07-29T12:00:00Z")!,
            ttlSeconds: 5, identity: identity)
    }

    // MARK: - Pure publish gate (mirrors shouldPersistFeed)

    func testPublishGateMatrix() {
        // Signed-in namespace admits only an authenticated response.
        XCTAssertTrue(DiscoverViewModel.shouldPublishFeed(expectedSignedIn: true, wasAuthenticated: true))
        // The returning-user race: anonymous response while signed-in expected → discard.
        XCTAssertFalse(DiscoverViewModel.shouldPublishFeed(expectedSignedIn: true, wasAuthenticated: false),
                       "an anonymous response must never publish over a signed-in user's cache")
        // Anonymous namespace admits only an unauthenticated response.
        XCTAssertTrue(DiscoverViewModel.shouldPublishFeed(expectedSignedIn: false, wasAuthenticated: false))
        // Logout/anon-expected must not surface a signed-in response.
        XCTAssertFalse(DiscoverViewModel.shouldPublishFeed(expectedSignedIn: false, wasAuthenticated: true))
    }

    // MARK: - Persisted user + slow restore + fast anonymous response

    func testAnonymousResponseDiscardedThenAuthenticatedPublishes() async throws {
        // Returning user, personalized cache seeds first paint. The first network
        // response comes back ANONYMOUS (the revalidation left before auth restore
        // installed the provider) → discarded, NOT painted over the cache. The retry
        // — provider now installed — authenticates and publishes.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(1...5)), wasAuthenticated: false, expectedSignedIn: true),
            .init(response: try response(ids: Array(100...113)), wasAuthenticated: true, expectedSignedIn: true),
        ])
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([7, 8, 9], identity: "user:42")),
            telemetry: { sink.record($0) }, retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(client.callCount, 2, "the anonymous response was discarded and one retry ran")
        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(100...113),
                       "only the authenticated response published")
        XCTAssertEqual(sink.outcomes, [.cacheHitServed, .principalDiscarded, .revalidateSuccess])
        // First paint came from the personalized cache; provenance stays frozen.
        XCTAssertEqual(vm.firstDataFromCache, true)
    }

    func testAnonymousResponsePublishesWhenNamespaceResolvedAnonymous() async throws {
        // No-token / signed-out launch: the expected namespace is anonymous, so an
        // anonymous response is exactly right and publishes on the first attempt.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(200...213)), wasAuthenticated: false, expectedSignedIn: false),
        ])
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(nil),
            telemetry: { sink.record($0) }, retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(client.callCount, 1, "no discard — anon response under anon namespace publishes immediately")
        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(200...213))
        XCTAssertEqual(sink.outcomes, [.cacheMiss, .revalidateSuccess])
    }

    func testNoTokenRestoreRacingCacheReadResolvesToAnonymous() async throws {
        // The divergent no-token launch: the first (racing) response is still under
        // the optimistic signed-in expectation and comes back anonymous → discarded.
        // Once the no-token cleanup resolves the namespace to anonymous, the retry's
        // anonymous response publishes. No signed-in content is stranded on screen.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(1...5)), wasAuthenticated: false, expectedSignedIn: true),
            .init(response: try response(ids: Array(300...305)), wasAuthenticated: false, expectedSignedIn: false),
        ])
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(nil),
            telemetry: nil, retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(client.callCount, 2)
        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(300...305),
                       "resolved-anonymous response published; the racing signed-in-expected anon response was discarded")
    }

    func testPersistentAnonymousDiscardSettlesToKeptCacheWithinBudget() async throws {
        // Pathological: every response comes back anonymous while signed-in is still
        // expected (restore never resolves within the budget). The discard-retry is
        // BOUNDED — it never spins forever; it settles to the honest kept-cache state
        // over the optimistic personalized cache, never blanking it.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(1...5)), wasAuthenticated: false, expectedSignedIn: true),
        ])
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([7, 8, 9], identity: "user:42")),
            telemetry: nil, retryBudget: 0.05, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, [7, 8, 9],
                       "the optimistic personalized cache is kept, never overwritten by anonymous content")
        XCTAssertTrue(vm.refreshFailedShowingCache, "honest kept-cache banner")
        XCTAssertTrue(vm.isShowingCachedContent)
        XCTAssertGreaterThanOrEqual(client.callCount, 1, "at least the one guaranteed attempt ran")
    }

    // MARK: - Immutable render-generation token (Item 2)

    func testRenderGenerationFrozenFromCacheDespiteNetworkReplace() async throws {
        // Cache seeds 3 cards (data-ready gen), then the network replaces with 14.
        // The frozen render generation must still describe the CACHE generation
        // (provenance cache, count 3) — the count/provenance that the on-screen
        // first-render event will report — not the later 14-card network state.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(100...113)), wasAuthenticated: true, expectedSignedIn: true),
        ])
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([1, 2, 3], identity: "user:42")),
            telemetry: nil, retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(vm.items.count, 14, "network replaced the seed")
        let gen = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertTrue(gen.fromCache, "provenance frozen to the cache seed that first rendered")
        XCTAssertEqual(gen.itemCount, 3, "bounded item count frozen at data-ready, not the later 14")
    }

    func testRenderGenerationIsNetworkOnColdMiss() async throws {
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(100...113)), wasAuthenticated: false, expectedSignedIn: false),
        ])
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        let gen = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertFalse(gen.fromCache)
        XCTAssertEqual(gen.itemCount, 14)
        XCTAssertEqual(gen.id, 1, "first load claims generation 1")
    }

    func testRenderGenerationReStampsAndAdvancesPerLoad() async throws {
        // A discarded (anonymous) generation must NOT stamp a render generation —
        // only a genuinely published generation does. The published generation's id
        // is the current load id.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(1...5)), wasAuthenticated: false, expectedSignedIn: true),
            .init(response: try response(ids: Array(100...113)), wasAuthenticated: true, expectedSignedIn: true),
        ])
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        let gen = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertFalse(gen.fromCache, "the published (authenticated) network generation stamped the token")
        XCTAssertEqual(gen.itemCount, 14)
    }

    // MARK: - Pure generation-decision core (same-ID / navigation / empty)

    func testGenerationDecisionEmitsOncePerGeneration() {
        let now = Date()
        let start = now.addingTimeInterval(-1)
        let gen = DiscoverRenderGeneration(id: 7, fromCache: true, itemCount: 3)

        // First emit for generation 7.
        let first = DiscoverFirstRender.generationDecision(
            generation: gen, lastEmittedGenerationId: nil, loadStartedAt: start, now: now)
        XCTAssertEqual(first?.generation, gen)
        XCTAssertNotNil(first?.ms)

        // Same generation already emitted (e.g. a same-card-ID row re-appears, or a
        // navigation back re-fires onAppear) → no duplicate.
        XCTAssertNil(DiscoverFirstRender.generationDecision(
            generation: gen, lastEmittedGenerationId: 7, loadStartedAt: start, now: now),
            "a same-ID replacement / re-appear must not re-emit the same generation")
    }

    func testGenerationDecisionEmptyAndUnanchoredEmitNothing() {
        let now = Date(); let start = now.addingTimeInterval(-1)
        // Empty generation → no first-card event (data-ready stays distinct).
        XCTAssertNil(DiscoverFirstRender.generationDecision(
            generation: DiscoverRenderGeneration(id: 1, fromCache: false, itemCount: 0),
            lastEmittedGenerationId: nil, loadStartedAt: start, now: now))
        // No generation yet → nothing to attribute.
        XCTAssertNil(DiscoverFirstRender.generationDecision(
            generation: nil, lastEmittedGenerationId: nil, loadStartedAt: start, now: now))
        // No load-start → never conflate render with model assignment.
        XCTAssertNil(DiscoverFirstRender.generationDecision(
            generation: DiscoverRenderGeneration(id: 1, fromCache: false, itemCount: 3),
            lastEmittedGenerationId: nil, loadStartedAt: nil, now: now))
    }

    func testGenerationDecisionAdvancesToNewGeneration() {
        let now = Date(); let start = now.addingTimeInterval(-2)
        // A NEW generation (id 8) after 7 was emitted → emits for 8.
        let d = DiscoverFirstRender.generationDecision(
            generation: DiscoverRenderGeneration(id: 8, fromCache: false, itemCount: 14),
            lastEmittedGenerationId: 7, loadStartedAt: start, now: now)
        XCTAssertEqual(d?.generation.id, 8)
        XCTAssertEqual(d?.generation.itemCount, 14)
    }
}
