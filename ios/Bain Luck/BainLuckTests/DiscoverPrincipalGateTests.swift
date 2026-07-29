import XCTest
@testable import Bain_Luck

/// L2-210 / C72 + L2-212 / C76 — Native Discover EXACT principal and render
/// acknowledgement.
///
/// Adversarial lifecycle coverage for the privacy and telemetry defects C75 left on
/// the native Discover surface, closed against the `native-principal-render/v1`
/// fixtures (`backend/scripts/evals/native_principal_render_fixtures.json`):
///   • Item 1 — publication AND persistence bind to the EXACT opaque dispatch
///     identity, not a signed-in Boolean parity. One authenticated account's response
///     may never paint or store under another's namespace (the `boolean_only_a_to_b_*`
///     / `cross_identity_*` counterexamples), and the divergent no-token optimistic
///     cache-seed is serialized behind the cleanup without delaying a valid returning
///     user's paint.
///   • Item 2 — the on-screen first-render telemetry is bound to an IMMUTABLE
///     generation token `{generation, started_at, provenance, item_count}`. The
///     elapsed time is measured from the token's own frozen `started_at`; the
///     acknowledgement is keyed on `generation` (not a business row id or a mutable
///     view timestamp) and carries no identity.
///
/// These exercise the pure decision cores AND drive `DiscoverViewModel` through a
/// principal-modeling fake with deterministic response-before-rebind ordering.
@MainActor
final class DiscoverPrincipalGateTests: XCTestCase {

    // MARK: - Opaque identity helpers (two authenticated accounts + anonymous)

    /// Map a fixture identity token onto a concrete opaque namespace string.
    private func ns(_ token: String) -> String {
        switch token {
        case "anon": return "anon:session-xyz"
        case "user_a": return "user:a"
        case "user_b": return "user:b"
        default: return token
        }
    }
    /// The backing user id for a fixture identity token (nil for anonymous), used to
    /// drive the persistence gate's `signedInNamespace` term exactly as production does.
    private func uid(_ token: String) -> String? {
        token == "anon" ? nil : token
    }

    // MARK: - Fakes

    /// A feed client that models the request/namespace principal with deterministic
    /// response-before-rebind ordering. Each reply carries the OPAQUE dispatch
    /// identity it left under and the CURRENT identity at the moment publication is
    /// attempted for it (defaulting to the dispatch identity when no rebind happened).
    /// The last reply is held for extra retries so a test never runs off the script.
    private nonisolated final class PrincipalFakeClient: DiscoverFeedProviding, @unchecked Sendable {
        struct Reply {
            let response: FeedResponse
            let identityAtFetch: String
            let wasAuthenticated: Bool
            let expectedSignedIn: Bool
            let currentIdentityAtPublish: String
            init(response: FeedResponse, identityAtFetch: String, wasAuthenticated: Bool,
                 expectedSignedIn: Bool, currentIdentityAtPublish: String? = nil) {
                self.response = response
                self.identityAtFetch = identityAtFetch
                self.wasAuthenticated = wasAuthenticated
                self.expectedSignedIn = expectedSignedIn
                self.currentIdentityAtPublish = currentIdentityAtPublish ?? identityAtFetch
            }
        }
        private let lock = NSLock()
        private var script: [Reply]
        private var count = 0
        private var lastServed: Reply?
        private let seed: DiscoverOptimisticSeedContext
        init(_ script: [Reply],
             seedContext: DiscoverOptimisticSeedContext = .init(signedInNamespace: false, credentialEligibleForRestore: true)) {
            precondition(!script.isEmpty); self.script = script; self.seed = seedContext
        }
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
                lastServed = reply
                return DiscoverFeedFetchResult(
                    response: reply.response,
                    identityAtFetch: reply.identityAtFetch,
                    wasAuthenticated: reply.wasAuthenticated,
                    expectedSignedIn: reply.expectedSignedIn)
            }
        }

        nonisolated func currentFeedPrincipal() async -> String {
            lock.withLock { lastServed?.currentIdentityAtPublish ?? "" }
        }

        nonisolated func optimisticSeedContext() async -> DiscoverOptimisticSeedContext {
            lock.withLock { seed }
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

    // MARK: - Item 1: exact-identity publish + persist over the full fixture set

    /// Every `native-principal-render/v1` scenario ID, mapped to the production
    /// publish (`DiscoverViewModel.shouldPublishFeed`) and persist
    /// (`APIClient.shouldPersistFeed`) gates. Publish and disk are asserted
    /// INDEPENDENTLY. The accepted scenarios must admit/deny exactly as declared; the
    /// rejected counterexamples — whose fixture `publish`/`store` values are what a
    /// Boolean-only gate WOULD have done — must resolve to the safe value for the
    /// exact declared reason.
    func testExactIdentityPublishAndPersistMatrix() {
        // (id, dispatch, current, wasAuthenticated, expectPublish, expectStore)
        let accepted: [(String, String, String, Bool, Bool, Bool)] = [
            ("returning_same_user",                  "user_a", "user_a", true,  true,  true),
            ("anonymous_to_user_login_old_response", "anon",   "user_a", false, false, false),
            ("user_to_anonymous_logout_old_response","user_a", "anon",   true,  false, false),
            ("user_a_to_b_both_authenticated",       "user_a", "user_b", true,  false, false),
            ("response_before_rebind_same_identity", "user_a", "user_a", true,  true,  true),
            ("rejected_restore_to_anon",             "user_a", "anon",   false, false, false),
            ("transient_restore_keeps_user",         "user_a", "user_a", true,  true,  true),
            ("cache_seed_then_network_same_load",    "user_a", "user_a", true,  true,  true),
            ("retained_same_id_refresh",             "user_a", "user_a", true,  true,  true),
            ("different_id_replacement",             "anon",   "anon",   false, true,  true),
            ("empty_response",                       "anon",   "anon",   false, true,  true),
            ("navigation_reappearance",              "user_b", "user_b", true,  true,  true),
            ("rapid_generations_latest_ack",         "user_b", "user_b", true,  true,  true),
        ]
        for (id, dispatch, current, wasAuth, expectPublish, expectStore) in accepted {
            let expectedSignedIn = dispatch != "anon"
            XCTAssertEqual(
                DiscoverViewModel.shouldPublishFeed(
                    identityAtFetch: ns(dispatch), expectedSignedIn: expectedSignedIn,
                    wasAuthenticated: wasAuth, currentIdentity: ns(current)),
                expectPublish, "publish gate wrong for scenario \(id)")
            XCTAssertEqual(
                APIClient.shouldPersistFeed(
                    identityAtFetch: ns(dispatch), userIdAtFetch: uid(dispatch),
                    wasAuthenticated: wasAuth, currentIdentity: ns(current)),
                expectStore, "persist gate wrong for scenario \(id)")
        }

        // Rejected counterexamples: the production gates return the SAFE value, never
        // the buggy value the fixture row carries.
        // boolean_only_a_to_b_publish: A→B both authenticated must NOT publish.
        XCTAssertFalse(DiscoverViewModel.shouldPublishFeed(
            identityAtFetch: ns("user_a"), expectedSignedIn: true,
            wasAuthenticated: true, currentIdentity: ns("user_b")),
            "cross_identity_publish: A's response must never paint under B")
        // cross_identity_store: A→B both authenticated must NOT store.
        XCTAssertFalse(APIClient.shouldPersistFeed(
            identityAtFetch: ns("user_a"), userIdAtFetch: uid("user_a"),
            wasAuthenticated: true, currentIdentity: ns("user_b")),
            "cross_identity_store: A's response must never persist under B")
    }

    /// Reproduce the pre-fix defect directly: a signed-in Boolean-parity gate
    /// (`expectedSignedIn == wasAuthenticated`) publishes A→B (both authenticated),
    /// while the exact-identity gate does not.
    func testBooleanOnlyGateWouldHavePublishedCrossIdentity() {
        // Old rule: A and B are both signed-in namespaces with authenticated
        // responses, so signed-in parity holds and the feed would publish.
        let booleanOnlyWouldPublish = (true == true) // expectedSignedIn == wasAuthenticated
        XCTAssertTrue(booleanOnlyWouldPublish, "the Boolean-only rule admitted A→B")
        // New rule: exact identity mismatch fails closed.
        XCTAssertFalse(DiscoverViewModel.shouldPublishFeed(
            identityAtFetch: ns("user_a"), expectedSignedIn: true,
            wasAuthenticated: true, currentIdentity: ns("user_b")))
    }

    // MARK: - Item 1: no-token divergent optimistic-seed serialization

    func testShouldSeedOptimisticCacheMatrix() {
        // Anonymous namespace always seeds its own last-good.
        XCTAssertTrue(DiscoverViewModel.shouldSeedOptimisticCache(
            signedInNamespace: false, credentialEligibleForRestore: false))
        XCTAssertTrue(DiscoverViewModel.shouldSeedOptimisticCache(
            signedInNamespace: false, credentialEligibleForRestore: true))
        // Valid returning user: signed-in namespace WITH a restorable credential
        // paints immediately.
        XCTAssertTrue(DiscoverViewModel.shouldSeedOptimisticCache(
            signedInNamespace: true, credentialEligibleForRestore: true))
        // Divergent no-token state: signed-in namespace, no restorable credential →
        // the cleanup is serialized before any signed-in cache is painted.
        XCTAssertFalse(DiscoverViewModel.shouldSeedOptimisticCache(
            signedInNamespace: true, credentialEligibleForRestore: false))
    }

    func testDivergentNoTokenSeedIsNotPainted() async throws {
        // Signed-in namespace whose credential is gone: the personalized last-good
        // must NOT paint. With the network failing there is nothing to fall back to,
        // so the feed stays empty rather than surfacing a stranded signed-in cache.
        let client = PrincipalFakeClient(
            [.init(response: try response(ids: [1]), identityAtFetch: ns("user_a"),
                   wasAuthenticated: false, expectedSignedIn: true)],
            seedContext: .init(signedInNamespace: true, credentialEligibleForRestore: false))
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([7, 8, 9], identity: "user:a")),
            telemetry: nil, retryBudget: 0.05, retryBackoff: 0.01)

        await vm.load()

        XCTAssertTrue(vm.items.isEmpty,
                      "the divergent no-token signed-in cache was never painted")
        XCTAssertNil(vm.firstDataFromCache, "no cache generation stamped")
        XCTAssertNil(vm.firstRenderGeneration)
    }

    func testValidReturningUserSeedsImmediately() async throws {
        // Signed-in namespace WITH a restorable credential: the personalized cache
        // paints on the first pass with no added delay.
        let client = PrincipalFakeClient(
            [.init(response: try response(ids: Array(100...113)), identityAtFetch: ns("user_a"),
                   wasAuthenticated: true, expectedSignedIn: true)],
            seedContext: .init(signedInNamespace: true, credentialEligibleForRestore: true))
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([7, 8, 9], identity: "user:a")),
            telemetry: nil, retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        // First paint came from the personalized cache (provenance frozen), even
        // though the network later replaced the content.
        let gen = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertTrue(gen.fromCache, "the valid returning user's cache produced first paint")
        XCTAssertEqual(gen.itemCount, 3)
    }

    // MARK: - Item 1: response-before-rebind at load() level

    func testResponseBeforeRebindToOtherAuthenticatedAccountFailsClosed() async throws {
        // A's request completes, but by publication the current identity has rebound
        // to another authenticated account B (account switch). A's data must never
        // paint into B's session; with only A-dispatched replies the load settles to
        // an honest empty/error state rather than cross-painting.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(1...5)), identityAtFetch: ns("user_a"),
                  wasAuthenticated: true, expectedSignedIn: true,
                  currentIdentityAtPublish: ns("user_b")),
        ])
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(nil),
            telemetry: nil, retryBudget: 0.05, retryBackoff: 0.01)

        await vm.load()

        XCTAssertTrue(vm.items.compactMap { $0.futures?.id }.allSatisfy { !(1...5).contains($0) },
                      "account A's response never painted under account B")
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertGreaterThanOrEqual(client.callCount, 1)
    }

    func testAnonymousResponseDiscardedThenAuthenticatedPublishes() async throws {
        // Returning user, personalized cache seeds first paint. The first network
        // response comes back ANONYMOUS (the revalidation left before auth restore
        // installed the provider) → discarded, NOT painted over the cache. The retry
        // — provider now installed — authenticates and publishes.
        let client = PrincipalFakeClient(
            [
                .init(response: try response(ids: Array(1...5)), identityAtFetch: ns("user_a"),
                      wasAuthenticated: false, expectedSignedIn: true),
                .init(response: try response(ids: Array(100...113)), identityAtFetch: ns("user_a"),
                      wasAuthenticated: true, expectedSignedIn: true),
            ],
            seedContext: .init(signedInNamespace: true, credentialEligibleForRestore: true))
        let sink = TelemetrySink()
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([7, 8, 9], identity: "user:a")),
            telemetry: { sink.record($0) }, retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(client.callCount, 2, "the anonymous response was discarded and one retry ran")
        XCTAssertEqual(Set(vm.items.compactMap { $0.futures?.id }), Set(100...113),
                       "only the authenticated response published")
        XCTAssertEqual(sink.outcomes, [.cacheHitServed, .principalDiscarded, .revalidateSuccess])
        XCTAssertEqual(vm.firstDataFromCache, true)
    }

    func testAnonymousResponsePublishesWhenNamespaceResolvedAnonymous() async throws {
        // No-token / signed-out launch: the expected namespace is anonymous, so an
        // anonymous response is exactly right and publishes on the first attempt.
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(200...213)), identityAtFetch: ns("anon"),
                  wasAuthenticated: false, expectedSignedIn: false),
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
            .init(response: try response(ids: Array(1...5)), identityAtFetch: ns("user_a"),
                  wasAuthenticated: false, expectedSignedIn: true),
            .init(response: try response(ids: Array(300...305)), identityAtFetch: ns("anon"),
                  wasAuthenticated: false, expectedSignedIn: false),
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
        let client = PrincipalFakeClient(
            [.init(response: try response(ids: Array(1...5)), identityAtFetch: ns("user_a"),
                   wasAuthenticated: false, expectedSignedIn: true)],
            seedContext: .init(signedInNamespace: true, credentialEligibleForRestore: true))
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([7, 8, 9], identity: "user:a")),
            telemetry: nil, retryBudget: 0.05, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(vm.items.compactMap { $0.futures?.id }, [7, 8, 9],
                       "the optimistic personalized cache is kept, never overwritten by anonymous content")
        XCTAssertTrue(vm.refreshFailedShowingCache, "honest kept-cache banner")
        XCTAssertTrue(vm.isShowingCachedContent)
        XCTAssertGreaterThanOrEqual(client.callCount, 1, "at least the one guaranteed attempt ran")
    }

    // MARK: - Item 2: immutable render-generation token (canonical four fields)

    func testRenderGenerationFrozenFromCacheDespiteNetworkReplace() async throws {
        // Cache seeds 3 cards (data-ready gen), then the network replaces with 14.
        // The frozen render generation must still describe the CACHE generation
        // (provenance cache, count 3) — never the later 14-card network state.
        let client = PrincipalFakeClient(
            [.init(response: try response(ids: Array(100...113)), identityAtFetch: ns("user_a"),
                   wasAuthenticated: true, expectedSignedIn: true)],
            seedContext: .init(signedInNamespace: true, credentialEligibleForRestore: true))
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(try cached([1, 2, 3], identity: "user:a")),
            telemetry: nil, retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        XCTAssertEqual(vm.items.count, 14, "network replaced the seed")
        let gen = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertEqual(gen.provenance, "cache", "provenance frozen to the cache seed that first rendered")
        XCTAssertTrue(gen.fromCache)
        XCTAssertEqual(gen.itemCount, 3, "bounded item count frozen at data-ready, not the later 14")
    }

    func testRenderGenerationIsNetworkOnColdMiss() async throws {
        let client = PrincipalFakeClient([
            .init(response: try response(ids: Array(100...113)), identityAtFetch: ns("anon"),
                  wasAuthenticated: false, expectedSignedIn: false),
        ])
        let vm = DiscoverViewModel(
            client: client, lastGood: FakeLastGood(nil), telemetry: nil,
            retryBudget: 5, retryBackoff: 0.01)

        await vm.load()

        let gen = try XCTUnwrap(vm.firstRenderGeneration)
        XCTAssertEqual(gen.provenance, "network")
        XCTAssertFalse(gen.fromCache)
        XCTAssertEqual(gen.itemCount, 14)
        XCTAssertEqual(gen.generation, 1, "first load claims generation 1")
    }

    func testRenderGenerationCarriesCanonicalFourFieldsAndNoIdentity() async throws {
        // The token exposes exactly {generation, started_at, provenance, item_count}
        // — provenance is a source label, never an identity. This is the structural
        // guarantee behind the `identity_bearing_telemetry` fix: there is no member
        // that could carry `user_a`/`user_b`/`anon`.
        let start = Date()
        let gen = DiscoverRenderGeneration(
            generation: 6, startedAt: start, provenance: "network", itemCount: 4)
        XCTAssertEqual(gen.generation, 6)
        XCTAssertEqual(gen.startedAt, start)
        XCTAssertEqual(gen.itemCount, 4)
        XCTAssertTrue(["cache", "network"].contains(gen.provenance),
                      "provenance is a source label, never an opaque identity")
    }

    // MARK: - Item 2: pure generation-decision core (started_at, same-ID, empty)

    func testGenerationDecisionMeasuresFromFrozenStartedAt() {
        // The elapsed ms is anchored to the token's OWN started_at, not a mutable
        // view-level load-start (the C76 `mutable_render_start` counterexample). Two
        // tokens with different started_at yield different ms for the same `now`.
        let now = Date()
        let old = DiscoverRenderGeneration(
            generation: 2, startedAt: now.addingTimeInterval(-2), provenance: "network", itemCount: 4)
        let recent = DiscoverRenderGeneration(
            generation: 3, startedAt: now.addingTimeInterval(-0.5), provenance: "network", itemCount: 4)
        let dOld = DiscoverFirstRender.generationDecision(
            generation: old, lastEmittedGenerationId: nil, now: now)
        let dRecent = DiscoverFirstRender.generationDecision(
            generation: recent, lastEmittedGenerationId: 2, now: now)
        XCTAssertEqual(dOld?.ms ?? 0, 2000, accuracy: 50)
        XCTAssertEqual(dRecent?.ms ?? 0, 500, accuracy: 50)
    }

    func testGenerationDecisionEmitsOncePerGenerationWithoutOnAppearRefire() {
        let now = Date()
        let gen = DiscoverRenderGeneration(
            generation: 7, startedAt: now.addingTimeInterval(-1), provenance: "cache", itemCount: 3)

        // First emit for generation 7 (keyed on generation, not a business row id).
        let first = DiscoverFirstRender.generationDecision(
            generation: gen, lastEmittedGenerationId: nil, now: now)
        XCTAssertEqual(first?.generation, gen)
        XCTAssertNotNil(first?.ms)

        // Same generation already emitted (a same-card-ID row re-appears, or a
        // navigation back would re-fire onAppear) → no duplicate. The onChange-driven
        // acknowledgement does not depend on onAppear re-firing (the C76
        // `same_id_onappear_dependency` / `onappear_refire_assumption` fix).
        XCTAssertNil(DiscoverFirstRender.generationDecision(
            generation: gen, lastEmittedGenerationId: 7, now: now),
            "a same-ID replacement / re-appear must not re-emit the same generation")
    }

    func testGenerationDecisionEmptyAndUnanchoredEmitNothing() {
        let now = Date()
        // Empty generation → no first-card event (data-ready stays distinct).
        XCTAssertNil(DiscoverFirstRender.generationDecision(
            generation: DiscoverRenderGeneration(
                generation: 1, startedAt: now, provenance: "network", itemCount: 0),
            lastEmittedGenerationId: nil, now: now))
        // No generation yet → nothing to attribute.
        XCTAssertNil(DiscoverFirstRender.generationDecision(
            generation: nil, lastEmittedGenerationId: nil, now: now))
    }

    func testGenerationDecisionAdvancesToNewGeneration() {
        let now = Date()
        // A NEW generation (id 10) after 7 was emitted → emits for 10 (rapid
        // generations acknowledge the LATEST).
        let d = DiscoverFirstRender.generationDecision(
            generation: DiscoverRenderGeneration(
                generation: 10, startedAt: now.addingTimeInterval(-1), provenance: "network", itemCount: 7),
            lastEmittedGenerationId: 7, now: now)
        XCTAssertEqual(d?.generation.generation, 10)
        XCTAssertEqual(d?.generation.itemCount, 7)
    }
}
