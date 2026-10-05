#if DEBUG
import XCTest
@testable import Bain_Luck

/// #10399 — the DEBUG restored-deck runtime behind
/// `ARestoredDiscoverDeckIsReplacedAfterTabAway10399Tests`.
///
/// Each test pins a way the journey could report a pass about a race it never
/// ran: a seed that shares cards with the fresh deck, a seed served to the wrong
/// namespace, a latch that swallows cancellation (the old appearance path would
/// then publish too), a latch that waits forever, a second fetch passing as the
/// first, and a default #9648 launch that quietly gained a last-good.
@MainActor
final class AFixedRestoredDeckHoldsTheFirstResponse10399Tests: XCTestCase {

    private var suiteName = ""
    private var defaults: UserDefaults!
    private var home: URL!

    override func setUp() {
        super.setUp()
        suiteName = "restored-deck-10399-\(UUID().uuidString)"
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
        FixedDiscoverRestoredDeck.active = nil
        super.tearDown()
    }

    // MARK: - Fixtures

    private func futuresJSON(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?","llm_sport_category":"economics","source":"kalshi","status":"open","top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1}],"outcome_count":1}}
        """
    }

    private func feedJSON(_ ids: [Int]) -> String {
        """
        {"items":[\(ids.map(futuresJSON).joined(separator: ","))],"total":\(ids.count),"limit":\(ids.count),"offset":0,"has_more":false}
        """
    }

    private func seedBytes(_ ids: [Int], age: String = "93600", principal: String = "\"anonymous\"") -> Data {
        Data(#"{"age_seconds":\#(age),"principal":\#(principal),"response":\#(feedJSON(ids))}"#.utf8)
    }

    private func runtime(
        seed: Data?, fresh: [Int] = [1, 2], arm: FixedDiscoverRestoredDeck.Arm = .current,
        identity: String = "anon:s1", bound: TimeInterval = 30
    ) -> FixedDiscoverRestoredDeck {
        let freshIds = fresh.map { "futures-\($0)" }
        return FixedDiscoverRestoredDeck(
            path: "restored-seed.json",
            seed: FixedDiscoverRestoredDeck.validateSeed(seed, path: "restored-seed.json", freshIds: freshIds),
            arm: .success(arm), bound: bound, identityNow: { identity })
    }

    private func client(_ restored: FixedDiscoverRestoredDeck, fresh: [Int] = [1, 2], identity: String = "anon:s1") -> FixedDiscoverFeed {
        let p = FixedDiscoverFeed.Principal(identity: identity, expectedSignedIn: false, authenticated: false)
        return FixedDiscoverFeed(
            path: "fresh-feed.json", bytes: Data(feedJSON(fresh).utf8), restored: restored,
            principal: { p }, identityNow: { identity },
            seedContext: { DiscoverOptimisticSeedContext(signedInNamespace: false, credentialEligibleForRestore: true) })
    }

    private func names(_ r: FixedDiscoverRestoredDeck) -> [String] { r.orderedEvents.map(\.name) }

    // MARK: - Launch contract

    func testNoSeedFlagLeavesTheFixedDeckLaunchWithoutALastGood() throws {
        let rel = "Library/Application Support/BL10399/fresh-feed.json"
        let url = home.appendingPathComponent(rel)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data(feedJSON([1, 2]).utf8).write(to: url)
        defaults.set(rel, forKey: LaunchRig.fixedFeedKey)
        let fixed = try XCTUnwrap(FixedDiscoverFeed.launchClient(defaults: defaults, home: home))
        XCTAssertNil(fixed.restored, "the #9648 default must stay lastGood:nil and unlatched")
        XCTAssertNil(FixedDiscoverRestoredDeck.active)
    }

    func testTheSeedFlagArmsTheRuntimeAndAnUnknownControlWordIsRefusedByName() throws {
        let dir = home.appendingPathComponent("Library/Application Support/BL10399")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try Data(feedJSON([1, 2]).utf8).write(to: dir.appendingPathComponent("fresh.json"))
        try seedBytes([7, 8]).write(to: dir.appendingPathComponent("seed.json"))
        defaults.set("Library/Application Support/BL10399/fresh.json", forKey: LaunchRig.fixedFeedKey)
        defaults.set("Library/Application Support/BL10399/seed.json", forKey: LaunchRig.fixedFeedRestoredSeedKey)

        let armed = try XCTUnwrap(FixedDiscoverFeed.launchClient(defaults: defaults, home: home)?.restored)
        XCTAssertTrue(armed === FixedDiscoverRestoredDeck.active)
        guard case .success(.current) = armed.arm else { return XCTFail("default arm is the current path") }
        guard case .success(let seed) = armed.seed else { return XCTFail("seed must validate: \(armed.seed)") }
        XCTAssertEqual(seed.ids, ["futures-7", "futures-8"])

        defaults.set("old_direct_load", forKey: LaunchRig.fixedFeedAppearanceControlKey)
        guard case .success(.oldDirectLoad)? = FixedDiscoverFeed.launchClient(defaults: defaults, home: home)?.restored?.arm
        else { return XCTFail("old_direct_load selects the negative arm") }

        defaults.set("oldDirectLoad", forKey: LaunchRig.fixedFeedAppearanceControlKey)
        let refused = try XCTUnwrap(FixedDiscoverFeed.launchClient(defaults: defaults, home: home)?.restored)
        guard case .failure = refused.arm else { return XCTFail("an unknown control word must be refused") }
        XCTAssertThrowsError(try refused.refuseIfMalformed())

        XCTAssertNil(LaunchRig.fixedFeedRestoredSeedURL(defaults: UserDefaults(suiteName: "empty-\(UUID())")!, home: home))
        defaults.set("../seed.json", forKey: LaunchRig.fixedFeedRestoredSeedKey)
        XCTAssertNil(LaunchRig.fixedFeedRestoredSeedURL(defaults: defaults, home: home), "the seed path stays inside the container")
    }

    // MARK: - Seed validation fails closed

    func testAMissingOrMalformedSeedIsRefusedAndEveryFetchFailsByName() async {
        let cases: [(String, Data?)] = [
            ("missing", nil),
            ("not an object", Data("[1]".utf8)),
            ("zero age", seedBytes([7], age: "0")),
            ("no age", Data(#"{"principal":"anonymous","response":\#(feedJSON([7]))}"#.utf8)),
            ("unknown principal", seedBytes([7], principal: "\"guest\"")),
            ("empty response", seedBytes([])),
            ("shares a card with the fresh deck", seedBytes([2, 7])),
        ]
        for (name, bytes) in cases {
            let r = runtime(seed: bytes)
            guard case .failure = r.seed else { XCTFail("\(name): must be refused, got \(r.seed)"); continue }
            let c = client(r)
            do {
                _ = try await c.fetchDiscoverFeedResolvingPrincipal(limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil)
                XCTFail("\(name): a refused seed must not let the fresh deck serve")
            } catch is FixedDiscoverFeed.HarnessFailure {
            } catch { XCTFail("\(name): unexpected \(error)") }
            let served = await r.serveSeed()
            XCTAssertNil(served, "\(name): a refused seed is never served")
            XCTAssertEqual(r.initialFetchCount, 0, "\(name): a refused run never counts a fetch")
        }
    }

    func testTheSeedIsAgedAndServedOnlyToItsOwnNamespace() async throws {
        let anon = runtime(seed: seedBytes([7, 8]))
        let served = try XCTUnwrap(await anon.serveSeed())
        XCTAssertEqual(served.identity, "anon:s1")
        XCTAssertEqual(served.age(now: Date()), 93600, accuracy: 5)
        XCTAssertEqual(served.response.items.count, 2)

        let wrong = runtime(seed: seedBytes([7, 8]), identity: "user:42")
        let refused = await wrong.serveSeed()
        XCTAssertNil(refused, "an anonymous seed is not a signed-in reader's deck")
        XCTAssertEqual(names(wrong), ["seed_refused"])
    }

    // MARK: - The latch

    func testOnlyTheFirstFetchIsHeldAndReleaseLetsItReturn() async throws {
        let r = runtime(seed: seedBytes([7]))
        let c = client(r)
        let first = Task { try await c.fetchDiscoverFeedResolvingPrincipal(limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil) }
        try await waitUntil { self.names(r).contains("fetch_waiting_on_latch") }
        let second = try await c.fetchDiscoverFeedResolvingPrincipal(limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil)
        XCTAssertEqual(second.response.items.count, 2, "a later fetch is not held")
        XCTAssertEqual(r.initialFetchCount, 2, "every offset-0 fetch is counted, so a second cannot pass as the first")
        r.release()
        let held = try await first.value
        XCTAssertEqual(held.response.items.compactMap { $0.futures?.id }, [1, 2])
        XCTAssertEqual(held.identityAtFetch, "anon:s1")
        XCTAssertEqual(r.snapshot()["latch"].flatMap { ($0 as? [String: Any])?["state"] as? String }, "released")
        XCTAssertEqual(names(r).filter { $0.hasPrefix("fetch_") }, ["fetch_started", "fetch_waiting_on_latch", "fetch_started", "fetch_returned"])
    }

    /// The property the whole journey rests on: the latch does NOT swallow
    /// cancellation. If it did, the pre-#10399 appearance path would publish too.
    func testCancellingTheWaitingTaskThrowsAtOnceAndALaterReleaseChangesNothing() async throws {
        let r = runtime(seed: seedBytes([7]))
        let c = client(r)
        let started = Date()
        let first = Task { try await c.fetchDiscoverFeedResolvingPrincipal(limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil) }
        try await waitUntil { self.names(r).contains("fetch_waiting_on_latch") }
        first.cancel()
        do {
            _ = try await first.value
            XCTFail("a cancelled hold must not return a response")
        } catch is CancellationError {
        } catch { XCTFail("expected CancellationError, got \(error)") }
        XCTAssertLessThan(Date().timeIntervalSince(started), 5, "cancellation must not wait out the bound")
        r.release()
        XCTAssertEqual(r.snapshot()["latch"].flatMap { ($0 as? [String: Any])?["state"] as? String }, "cancelled")
        XCTAssertTrue(names(r).contains("fetch_cancelled"))
        XCTAssertFalse(names(r).contains("fetch_returned"))
    }

    func testAnUnreleasedHoldFailsByNameAfterItsBound() async throws {
        let r = runtime(seed: seedBytes([7]), bound: 0.3)
        let c = client(r)
        do {
            _ = try await c.fetchDiscoverFeedResolvingPrincipal(limit: 50, offset: 0, eventPct: 0.15, cacheTTL: nil)
            XCTFail("an unreleased hold must not succeed")
        } catch let failure as FixedDiscoverFeed.HarnessFailure {
            XCTAssertEqual(failure, .latchTimedOut(seconds: 0.3))
        }
        XCTAssertEqual(r.snapshot()["latch"].flatMap { ($0 as? [String: Any])?["state"] as? String }, "timed_out")
    }

    // MARK: - Through the production view model

    func testTheProductionViewModelPaintsTheSeedThenPublishesTheReleasedResponse() async throws {
        let r = runtime(seed: seedBytes([7, 8]))
        let model = DiscoverViewModel(client: client(r), lastGood: r.lastGood, telemetry: nil)
        let load = Task { @MainActor in await model.load() }
        try await waitUntil { self.names(r).contains("fetch_waiting_on_latch") }
        XCTAssertEqual(model.items.compactMap { $0.futures?.id }, [7, 8])
        XCTAssertTrue(model.isShowingCachedContent)
        r.release()
        let outcome = await load.value
        XCTAssertEqual(outcome, .published)
        XCTAssertEqual(model.items.compactMap { $0.futures?.id }, [1, 2])
        XCTAssertFalse(model.isShowingCachedContent)
        XCTAssertEqual(r.initialFetchCount, 1)
    }

    private func waitUntil(_ condition: @escaping () -> Bool, timeout: TimeInterval = 5) async throws {
        let deadline = Date().addingTimeInterval(timeout)
        while !condition() {
            guard Date() < deadline else { return XCTFail("condition not reached within \(timeout) s") }
            try await Task.sleep(nanoseconds: 20_000_000)
        }
    }
}
#endif
