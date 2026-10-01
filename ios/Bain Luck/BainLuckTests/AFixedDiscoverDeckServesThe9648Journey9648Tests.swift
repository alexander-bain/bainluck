#if DEBUG
import XCTest
@testable import Bain_Luck

/// #9648 — the DEBUG fixed-deck seam that lets the installed journey run on a
/// pinned 36-card deck instead of waiting for seasonal live supply.
///
/// These pin the seam's refusals, because each one is a way the journey could
/// report a pass about cards it never controlled: a flag that falls back to the
/// network, a malformed file served as a short feed, a page that lies about
/// `has_more`, a principal-free client that publishes under any account, a seed
/// that rewrites the stores on the cold relaunch it is meant to observe.
@MainActor
final class AFixedDiscoverDeckServesThe9648Journey9648Tests: XCTestCase {

    private var suiteName = ""
    private var defaults: UserDefaults!
    private var home: URL!

    override func setUp() {
        super.setUp()
        suiteName = "fixed-deck-9648-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
        home = FileManager.default.temporaryDirectory.appendingPathComponent(suiteName, isDirectory: true)
        try? FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
        FixedDiscoverFeedSeed.resetLatchForTesting()
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        try? FileManager.default.removeItem(at: home)
        FixedDiscoverFeedSeed.resetLatchForTesting()
        FixedDiscoverFeedReceipt.launch = nil
        super.tearDown()
    }

    // MARK: - Fixtures

    private func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }

    private func deck(_ ids: [Int], total: Int? = nil) -> Data {
        let json = """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":\(total ?? ids.count),"limit":\(ids.count),"offset":0,"has_more":false,"cache":{"status":"controlled_fixture","ttl_seconds":0}}
        """
        return Data(json.utf8)
    }

    private func principal(_ identity: String, signedIn: Bool = true) -> FixedDiscoverFeed.Principal {
        FixedDiscoverFeed.Principal(identity: identity, expectedSignedIn: signedIn, authenticated: signedIn)
    }

    private func fixed(
        _ bytes: Data?, atFetch: String = "user:1", current: String = "user:1"
    ) -> FixedDiscoverFeed {
        let p = principal(atFetch)
        return FixedDiscoverFeed(
            path: "fixed-feed.json", bytes: bytes,
            principal: { p },
            identityNow: { current },
            seedContext: { DiscoverOptimisticSeedContext(signedInNamespace: true, credentialEligibleForRestore: true) })
    }

    private final class Sink: @unchecked Sendable {
        private let lock = NSLock()
        private var events: [DiscoverFeedTelemetry.Outcome] = []
        func record(_ e: DiscoverFeedTelemetry) { lock.withLock { events.append(e.outcome) } }
        var outcomes: [DiscoverFeedTelemetry.Outcome] { lock.withLock { events } }
    }

    // MARK: - Flag absent / path contract

    func testNoFlagMeansTheOrdinaryProductionClient() {
        XCTAssertNil(FixedDiscoverFeed.launchClient(defaults: defaults, home: home))
        XCTAssertNil(FixedDiscoverFeedReceipt.launch, "an unarmed launch records no fixture receipt")
    }

    func testThePathCanOnlyNameAFileInsideTheAppsOwnContainer() {
        XCTAssertEqual(
            LaunchRig.containerURL("Library/Application Support/BL9648/fixed-feed.json", home: home)?.path,
            home.appendingPathComponent("Library/Application Support/BL9648/fixed-feed.json").path)
        for refused in ["", "   ", "/etc/hosts", "~/x.json", "../x.json", "a/../../x.json"] {
            XCTAssertNil(LaunchRig.containerURL(refused, home: home), "must refuse \(refused.debugDescription)")
        }
    }

    func testTheAnchorIsReadAsTextOrNumberAndRefusesNonsense() {
        defaults.set("1790872800", forKey: LaunchRig.fixedFeedAnchorKey)
        XCTAssertEqual(LaunchRig.fixedFeedAnchor(defaults: defaults), 1_790_872_800)
        defaults.set(NSNumber(value: 1_790_872_801.5), forKey: LaunchRig.fixedFeedAnchorKey)
        XCTAssertEqual(LaunchRig.fixedFeedAnchor(defaults: defaults), 1_790_872_801.5)
        for bad in ["0", "-5", "soon", "inf"] {
            defaults.set(bad, forKey: LaunchRig.fixedFeedAnchorKey)
            XCTAssertNil(LaunchRig.fixedFeedAnchor(defaults: defaults), "must refuse \(bad)")
        }
    }

    // MARK: - Missing / malformed is a named failure, never a fallback

    func testAMissingFixtureFailsEveryFetchByName() async {
        let client = fixed(nil)
        do {
            _ = try await client.fetchDiscoverFeedResolvingPrincipal(limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil)
            XCTFail("a missing fixture must not serve")
        } catch let failure as FixedDiscoverFeed.HarnessFailure {
            XCTAssertEqual(failure, .missing(path: "fixed-feed.json"))
        } catch { XCTFail("unexpected \(error)") }
    }

    func testAMalformedFixtureIsRefusedBeforeAnyPageIsServed() async {
        let cases: [(String, Data)] = [
            ("not an object", Data("[1,2]".utf8)),
            ("no items", Data(#"{"items":[],"total":0}"#.utf8)),
            ("total disagrees with items", deck([1, 2, 3], total: 36)),
            ("an item the decoder's skip loop drops", Data(#"{"items":[42],"total":1,"limit":1,"offset":0,"has_more":false}"#.utf8)),
        ]
        for (name, bytes) in cases {
            let client = fixed(bytes)
            guard case .failure(.malformed) = client.fixture else {
                XCTFail("\(name): must be refused as malformed, got \(client.fixture)"); continue
            }
            do {
                _ = try await client.fetchDiscoverFeed(limit: 200, offset: 0, eventPct: 0.15, cacheTTL: nil)
                XCTFail("\(name): a malformed fixture must not serve a page")
            } catch is FixedDiscoverFeed.HarnessFailure {
            } catch { XCTFail("\(name): unexpected \(error)") }
        }
    }

    // MARK: - Deterministic, truthful paging

    func testPagesAreDeterministicWindowsWithTruthfulTotalsAndOneEdition() throws {
        let client = fixed(deck(Array(1...7)))
        let fixture = try client.fixture.get()
        XCTAssertEqual(fixture.cards, 7)
        XCTAssertEqual(fixture.sha256.count, 64)

        let first = try client.page(limit: 3, offset: 0)
        XCTAssertEqual(first.items.map(\.id), ["futures-1", "futures-2", "futures-3"])
        XCTAssertEqual(first.total, 7)
        XCTAssertTrue(first.hasMore)

        let last = try client.page(limit: 3, offset: 6)
        XCTAssertEqual(last.items.map(\.id), ["futures-7"])
        XCTAssertFalse(last.hasMore, "the final window must not claim more")

        let whole = try client.page(limit: 50, offset: 0)
        XCTAssertEqual(whole.items.count, 7)
        XCTAssertFalse(whole.hasMore)
        XCTAssertEqual(try client.page(limit: 50, offset: 0).items.map(\.id), whole.items.map(\.id), "same bytes, same page")

        XCTAssertNotNil(first.edition)
        XCTAssertEqual(first.edition, last.edition, "one stable edition for the whole file")
        XCTAssertEqual(first.edition, whole.edition)
        XCTAssertEqual(try client.page(limit: 3, offset: 99).items.count, 0)
    }

    // MARK: - Principal: bound, not publish-always

    func testOffsetZeroCarriesTheRealDispatchPrincipalNotTheNeutralDefault() async throws {
        let client = fixed(deck([1, 2]), atFetch: "user:42")
        let result = try await client.fetchDiscoverFeedResolvingPrincipal(limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil)
        XCTAssertEqual(result.identityAtFetch, "user:42")
        XCTAssertTrue(result.wasAuthenticated)
        XCTAssertTrue(result.expectedSignedIn)
        let current = await client.currentFeedPrincipal()
        XCTAssertEqual(current, "user:1")
    }

    func testAPrincipalMismatchIsDiscardedByTheRealPublicationGate() async {
        let sink = Sink()
        let vm = DiscoverViewModel(
            client: fixed(deck(Array(1...5)), atFetch: "user:A", current: "user:B"),
            lastGood: nil, telemetry: { sink.record($0) },
            retryBudget: 0.3, seededRetryBudget: 0.3, retryBackoff: 0.05, autoRecoveryDelays: [])
        let outcome = await vm.load()
        XCTAssertNotEqual(outcome, .published)
        XCTAssertTrue(vm.items.isEmpty, "another principal's deck must not paint")
        XCTAssertTrue(sink.outcomes.contains(.principalDiscarded))
    }

    func testAMatchingPrincipalPublishesTheWholeDeckWithNoPriceClient() async {
        let client = fixed(deck(Array(1...5)))
        XCTAssertNil(client as Any as? DiscoverPriceCardsProviding, "no price client ⇒ no REST price poll, no socket")
        let vm = DiscoverViewModel(client: client, lastGood: nil, telemetry: nil, autoRecoveryDelays: [])
        let outcome = await vm.load()
        XCTAssertEqual(outcome, .published)
        XCTAssertEqual(vm.items.map(\.id), (1...5).map { "futures-\($0)" })
    }

    // MARK: - Seeding: explicit, once, before the stores are read

    private func writeSeed() throws -> String {
        let seed = """
        {"clock":"2026-10-01T16:40:00+00:00","defaults":{
          "discover_interaction_profile_native_v2":{"baseball":{"score":6.0,"at":1790872800.0},"politics":{"score":-4.0,"at":1790872800.0}},
          "discover_dismissed_v2":{"futures-27594131":1790872740.0},
          "discover_interaction_profile_native_v1":null,"discover_dismissed":null}}
        """
        let dir = home.appendingPathComponent("Library/BL9648", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try Data(seed.utf8).write(to: dir.appendingPathComponent("seed.json"))
        return "Library/BL9648/seed.json"
    }

    func testTheSeedMaterializesEveryTimestampAgainstTheOneRunAnchor() throws {
        defaults.set(try writeSeed(), forKey: LaunchRig.fixedFeedSeedKey)
        defaults.set("1800000000", forKey: LaunchRig.fixedFeedAnchorKey)
        defaults.set(["old": 1.0], forKey: FixedDiscoverFeedSeed.legacyProfileKey)
        defaults.set(["event-1"], forKey: FixedDiscoverFeedSeed.legacyDismissKey)

        let outcome = FixedDiscoverFeedSeed.apply(defaults: defaults, home: home)

        XCTAssertEqual(outcome.state, .seeded)
        XCTAssertEqual(outcome.anchor, 1_800_000_000)
        let profile = defaults.dictionary(forKey: FixedDiscoverFeedSeed.profileKey) as? [String: [String: Double]]
        XCTAssertEqual(profile?["baseball"], ["score": 6.0, "at": 1_800_000_000])
        XCTAssertEqual(profile?["politics"], ["score": -4.0, "at": 1_800_000_000])
        let dismissed = defaults.dictionary(forKey: FixedDiscoverFeedSeed.dismissKey) as? [String: Double]
        XCTAssertEqual(dismissed, ["futures-27594131": 1_799_999_940], "keeps its 60 s age relative to the anchor")
        XCTAssertNil(defaults.object(forKey: FixedDiscoverFeedSeed.legacyProfileKey), "a legacy v1 profile would migrate on load")
        XCTAssertNil(defaults.object(forKey: FixedDiscoverFeedSeed.legacyDismissKey))
    }

    func testALaunchWithoutTheSeedFlagWritesNothing() throws {
        _ = try writeSeed()
        defaults.set("1800000000", forKey: LaunchRig.fixedFeedAnchorKey)
        defaults.set(["event-9": 1_799_999_999.0], forKey: FixedDiscoverFeedSeed.dismissKey)

        let outcome = FixedDiscoverFeedSeed.apply(defaults: defaults, home: home)

        XCTAssertEqual(outcome.state, .notRequested)
        XCTAssertEqual(defaults.dictionary(forKey: FixedDiscoverFeedSeed.dismissKey) as? [String: Double],
                       ["event-9": 1_799_999_999], "the cold relaunch must observe the treatment's stores untouched")
    }

    func testASeedWithoutAnAnchorIsAFailureAndWritesNothing() throws {
        defaults.set(try writeSeed(), forKey: LaunchRig.fixedFeedSeedKey)
        let outcome = FixedDiscoverFeedSeed.apply(defaults: defaults, home: home)
        guard case .failed = outcome.state else { return XCTFail("got \(outcome.state)") }
        XCTAssertNil(defaults.object(forKey: FixedDiscoverFeedSeed.profileKey))
    }

    func testTheSeedRunsOncePerProcess() throws {
        defaults.set(try writeSeed(), forKey: LaunchRig.fixedFeedSeedKey)
        defaults.set("1800000000", forKey: LaunchRig.fixedFeedAnchorKey)
        XCTAssertEqual(FixedDiscoverFeedSeed.applyIfRequested(defaults: defaults, home: home).state, .seeded)
        defaults.set(["event-15317023": 1_800_000_100.0], forKey: FixedDiscoverFeedSeed.dismissKey)

        _ = FixedDiscoverFeedSeed.applyIfRequested(defaults: defaults, home: home)

        XCTAssertEqual(defaults.dictionary(forKey: FixedDiscoverFeedSeed.dismissKey) as? [String: Double],
                       ["event-15317023": 1_800_000_100], "a second view-model construction must not reseed")
    }

    func testLaunchClientSeedsBeforeReturningAndRecordsTheReceipt() throws {
        let dir = home.appendingPathComponent("Library/BL9648", isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try deck([1, 2, 3]).write(to: dir.appendingPathComponent("fixed-feed.json"))
        defaults.set("Library/BL9648/fixed-feed.json", forKey: LaunchRig.fixedFeedKey)
        defaults.set(try writeSeed(), forKey: LaunchRig.fixedFeedSeedKey)
        defaults.set("1800000000", forKey: LaunchRig.fixedFeedAnchorKey)

        let client = try XCTUnwrap(FixedDiscoverFeed.launchClient(defaults: defaults, home: home))

        XCTAssertEqual(try client.fixture.get().cards, 3)
        XCTAssertNotNil(defaults.object(forKey: FixedDiscoverFeedSeed.profileKey), "seeded before the client is handed out")
        XCTAssertEqual(FixedDiscoverFeedReceipt.launch?.seed.state, .seeded)
    }

    // MARK: - Receipt

    func testTheReceiptCarriesRawStoresCanonicallyAndNoCredential() throws {
        defaults.set(["b": ["score": 6.0, "at": 2.0], "a": ["score": 1.5, "at": 1.0]], forKey: FixedDiscoverFeedSeed.profileKey)
        let text = FixedDiscoverFeedReceipt.json(
            launch: nil, signedIn: true, served: 36, eligible: 35,
            rendered: [.init(id: "event-15317515", category: "baseball", score: 90, adjustment: 6)],
            defaults: defaults, now: Date(timeIntervalSince1970: 5))
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any])
        let stores = try XCTUnwrap(body["stores"] as? [String: String])
        XCTAssertEqual(stores[FixedDiscoverFeedSeed.profileKey], #"{"a":{"at":1,"score":1.5},"b":{"at":2,"score":6}}"#)
        XCTAssertEqual(stores[FixedDiscoverFeedSeed.dismissKey], "null")
        XCTAssertEqual((body["store_sha256"] as? [String: String])?.count, 4)
        XCTAssertEqual(body["signed_in"] as? Bool, true)
        XCTAssertFalse(text.lowercased().contains("token"), "the receipt never carries a credential")
    }
}
#endif
