import XCTest

/// #10399 / #10094 — **a reader whose Discover opens on an old restored deck,
/// leaves the tab while the fresh feed is still loading, and comes back, sees the
/// fresh feed replace the old deck.**
///
/// The unit tests (`DiscoverInitialLoadLifetime10094Tests`) prove the rule on a
/// helper. This walks the MOUNTED view: the real `DiscoverView` `.task`, the real
/// `TabView` lifecycle, the production `DiscoverViewModel`. Two DEBUG inputs make
/// the ordering deterministic (`FixedDiscoverRestoredDeck`): an aged anonymous
/// seed served through the existing last-good injection, and a first response
/// held on a cancellation-cooperative latch that this test releases by tapping
/// `discover-restored-deck-release`.
///
/// ## The ordered claim, and what each arm proves
///
/// 1. the OLD seed is on screen while the first fetch is held (no response yet);
/// 2. a Search round trip makes SwiftUI cancel the appearance task — read from the
///    app's own record of that task's cancellation, not inferred from the tap;
/// 3. only then the response is released, and:
///    * current path → the FRESH deck replaces the seed from the ONE initial fetch;
///    * `old_direct_load` (the pre-#10399 shape, NEGATIVE control) → the held fetch
///      was cancelled with its task and the seed stays, from the same one fetch.
///
/// If SwiftUI never cancels the task on a tab round trip, the race was not
/// exercised and the test SKIPS saying UNEVENTFUL — it never claims the race.
///
/// Armed only when the harness placed both fixtures in the app container and named
/// them: `TEST_RUNNER_BL_10399_FRESH`, `TEST_RUNNER_BL_10399_SEED`, with their
/// expected hashes `TEST_RUNNER_BL_10399_FRESH_SHA` / `TEST_RUNNER_BL_10399_SEED_SHA`.
final class ARestoredDiscoverDeckIsReplacedAfterTabAway10399Tests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    // MARK: - The two arms

    func testFreshFeedReplacesTheRestoredDeckAfterTheAppearanceTaskIsCancelled() throws {
        let (app, returned) = try walkToReleased(arm: nil)

        let after = try waitForState(app, "the fresh deck replaces the restored seed", timeout: 10) {
            $0.renderedFresh > 0 && $0.renderedSeed == 0 && $0.has("network_painted")
        }
        snap("10399-04-current-fresh-replaced-seed")
        attach(after, as: "10399-current-final")

        XCTAssertEqual(after.initialFetches, 1, "the fresh deck must come from the ONE initial fetch, not a second one")
        XCTAssertEqual(after.latchState, "released")
        let returnedEvent = try XCTUnwrap(after.first("fetch_returned"), "the held fetch never returned")
        XCTAssertGreaterThan(returnedEvent.seq, try XCTUnwrap(after.first("latch_release_requested")).seq)
        XCTAssertGreaterThan(returnedEvent.seq, returned.cancelSeq, "the response returned AFTER the owner was cancelled")
        XCTAssertNil(after.first("fetch_cancelled"), "the held fetch must survive its appearance task's cancellation")
        let owner = try XCTUnwrap(after.first("appearance_owner_returned"))
        XCTAssertTrue(owner.detail.contains("outcome=published"), "appearance load outcome: \(owner.detail)")
        XCTAssertGreaterThan(try XCTUnwrap(after.first("network_painted")).seq, returnedEvent.seq)
        XCTAssertEqual(after.count("appearance_owner_started"), 1, "a second appearance load would be a second fetch path")
        log("CURRENT final " + after.events.map { "\($0.seq):\($0.name)" }.joined(separator: " "))
    }

    /// NEGATIVE control: the same walk with the pre-#10399 appearance shape must
    /// keep the OLD deck. If this arm showed the fresh deck, the treatment above
    /// would be proving nothing about the cancellation path.
    func testOldDirectAppearanceLoadKeepsTheRestoredDeckNegativeControl() throws {
        let (app, returned) = try walkToReleased(arm: "old_direct_load")

        let settled = try waitForState(app, "the old path settles on the cancelled fetch", timeout: 10) {
            $0.has("appearance_owner_returned") && $0.has("latch_release_requested")
        }
        // Give a late publication every chance to land before reading the screen.
        Thread.sleep(forTimeInterval: 4)
        let after = try read(app)
        snap("10399-04-control-seed-kept")
        attach(after, as: "10399-control-final")

        let cancelled = try XCTUnwrap(settled.first("fetch_cancelled"), "the old path's fetch was not cancelled with its task")
        XCTAssertLessThan(cancelled.seq, returned.secondAppearSeq, "the fetch was cancelled BEFORE the reader returned")
        XCTAssertTrue(
            try XCTUnwrap(after.first("appearance_owner_returned")).detail.contains("outcome=cancelled"),
            "old appearance outcome: \(after.first("appearance_owner_returned")?.detail ?? "")")
        XCTAssertNil(after.first("fetch_returned"))
        XCTAssertEqual(after.latchState, "cancelled")
        XCTAssertEqual(after.initialFetches, 1)
        XCTAssertGreaterThan(after.renderedSeed, 0, "the old path keeps the restored deck on screen")
        XCTAssertEqual(after.renderedFresh, 0, "the old path must not show the fresh deck")
        XCTAssertNil(after.first("network_painted"))
        log("CONTROL final " + after.events.map { "\($0.seq):\($0.name)" }.joined(separator: " "))
    }

    // MARK: - The shared walk: seed mounted → Search → back → release

    private struct Returned { let cancelSeq: Int; let secondAppearSeq: Int }

    private func walkToReleased(arm: String?) throws -> (XCUIApplication, Returned) {
        let env = ProcessInfo.processInfo.environment
        guard let fresh = env["BL_10399_FRESH"], !fresh.isEmpty,
              let seed = env["BL_10399_SEED"], !seed.isEmpty,
              let freshSHA = env["BL_10399_FRESH_SHA"], !freshSHA.isEmpty,
              let seedSHA = env["BL_10399_SEED_SHA"], !seedSHA.isEmpty
        else {
            throw XCTSkip("NOT ARMED: the #10399 runtime runs only when the harness placed and named both fixtures.")
        }
        var args = ["-launch_fixed_feed", fresh, "-launch_fixed_feed_restored_seed", seed]
        if let arm { args += ["-launch_fixed_feed_appearance_control", arm] }
        let app = UITestLaunch.launchApp(extra: args)
        JourneyPrecondition.tabBar(of: app)

        // ═══ 1. the OLD deck is mounted while the first response is held ═══
        let mounted = try waitForState(app, "the restored seed mounted with the first fetch held", timeout: 30) {
            $0.has("seed_painted") && $0.has("fetch_waiting_on_latch") && $0.renderedSeed > 0
        }
        // The view model's own seeded deadline (20 s from dispatch) ends an
        // unreleased hold. A walk that starts after it is not this experiment.
        if mounted.has("fetch_cancelled") || mounted.has("fetch_failed") || mounted.has("appearance_owner_returned") {
            XCTFail("HARNESS: the held fetch ended before the walk began (production seeded deadline?): "
                    + mounted.events.map { "\($0.name)@\(String(format: "%.2f", $0.uptime))" }.joined(separator: " "))
            throw XCTSkip("stopped: the walk started too late")
        }
        snap("10399-01-seed-mounted-response-held")
        attach(mounted, as: "10399-\(arm ?? "current")-01-mounted")
        XCTAssertEqual(mounted.freshSHA, freshSHA, "HARNESS: not the fresh fixture the harness placed")
        XCTAssertEqual(mounted.seedSHA, seedSHA, "HARNESS: not the seed fixture the harness placed")
        XCTAssertNil(mounted.failure, "HARNESS: \(mounted.failure ?? "")")
        XCTAssertEqual(mounted.arm, arm ?? "current_appearance_load")
        XCTAssertEqual(mounted.renderedFresh, 0, "the fresh deck is on screen before its response was released")
        XCTAssertNil(mounted.first("fetch_returned"))
        XCTAssertEqual(mounted.initialFetches, 1)
        XCTAssertLessThan(try XCTUnwrap(mounted.first("seed_served")).seq, try XCTUnwrap(mounted.first("seed_painted")).seq)

        // ═══ 2. an ordinary tab round trip ═══
        JourneyPrecondition.openTab("Search", in: app)
        snap("10399-02-search-tab")
        JourneyPrecondition.openTab("Discover", in: app)
        let back = try waitForState(app, "Discover appeared again", timeout: 10) { $0.count("discover_appeared") >= 2 }
        attach(back, as: "10399-\(arm ?? "current")-03-returned")
        snap("10399-03-returned-before-release")

        guard let cancelled = back.first("appearance_owner_cancelled") else {
            throw XCTSkip(
                "UNEVENTFUL: a Search round trip did not cancel Discover's appearance task, so the "
                + "restored-deck race was not exercised. Log: \(back.events.map(\.name))")
        }
        let appears = back.events.filter { $0.name == "discover_appeared" }
        XCTAssertGreaterThan(cancelled.seq, appears[0].seq)
        XCTAssertLessThan(cancelled.seq, appears[1].seq, "the appearance task was cancelled before the reader returned")
        XCTAssertNotNil(back.first("discover_disappeared"))
        XCTAssertNil(back.first("fetch_returned"), "the response returned before release")
        XCTAssertGreaterThan(back.renderedSeed, 0, "the restored deck is still the screen when the reader returns")
        XCTAssertEqual(back.renderedFresh, 0)

        // ═══ 3. release the held response, inside the production seeded budget ═══
        let started = try XCTUnwrap(back.first("fetch_started"))
        let elapsed = ProcessUptimeDelta.since(started.uptime, readAt: back)
        XCTAssertLessThan(elapsed, 16, "HARNESS: release would arrive after the view model's 20 s seeded deadline")
        let release = app.descendants(matching: .any)["discover-restored-deck-release"]
        XCTAssertTrue(release.waitForExistence(timeout: 5), "HARNESS: no release control on the fixture launch")
        release.tap()
        return (app, Returned(cancelSeq: cancelled.seq, secondAppearSeq: appears[1].seq))
    }

    // MARK: - Reading the app's own receipt

    private struct Event { let seq: Int; let name: String; let detail: String; let uptime: Double }

    private struct State {
        let raw: String
        let events: [Event]
        let initialFetches: Int
        let latchState: String
        let arm: String?
        let failure: String?
        let freshSHA: String?
        let seedSHA: String?
        let renderedSeed: Int
        let renderedFresh: Int
        let latestUptime: Double

        func has(_ name: String) -> Bool { events.contains { $0.name == name } }
        func count(_ name: String) -> Int { events.filter { $0.name == name }.count }
        func first(_ name: String) -> Event? { events.first { $0.name == name } }
    }

    private enum ProcessUptimeDelta {
        /// Seconds between an event and the newest event in the same read: both are
        /// the app's own uptime, so no clock of the runner's enters the comparison.
        static func since(_ uptime: Double, readAt state: State) -> Double { state.latestUptime - uptime }
    }

    private func read(_ app: XCUIApplication) throws -> State {
        let receipt = app.descendants(matching: .any)["discover-fixed-feed-receipt"]
        let release = app.descendants(matching: .any)["discover-restored-deck-release"]
        guard receipt.exists, release.exists,
              let receiptText = receipt.value as? String, let logText = release.value as? String,
              let body = try? JSONSerialization.jsonObject(with: Data(receiptText.utf8)) as? [String: Any],
              let deck = try? JSONSerialization.jsonObject(with: Data(logText.utf8)) as? [String: Any]
        else { throw ReadError.notYet }
        let seed = deck["seed"] as? [String: Any] ?? [:]
        let fixture = body["fixture"] as? [String: Any] ?? [:]
        let seedIds = Set(seed["ids"] as? [String] ?? [])
        let rendered = (body["rendered"] as? [[String: Any]] ?? []).compactMap { $0["id"] as? String }
        let events = (deck["events"] as? [[String: Any]] ?? []).map {
            Event(seq: $0["seq"] as? Int ?? 0, name: $0["name"] as? String ?? "",
                  detail: $0["detail"] as? String ?? "", uptime: $0["uptime"] as? Double ?? 0)
        }
        let failure = (fixture["failure"] as? String) ?? (seed["failure"] as? String) ?? (deck["arm_failure"] as? String)
        return State(
            raw: logText + "\n" + receiptText,
            events: events,
            initialFetches: deck["initial_fetches"] as? Int ?? -1,
            latchState: (deck["latch"] as? [String: Any])?["state"] as? String ?? "",
            arm: deck["arm"] as? String,
            failure: failure,
            freshSHA: fixture["sha256"] as? String,
            seedSHA: seed["sha256"] as? String,
            renderedSeed: rendered.filter { seedIds.contains($0) }.count,
            // A card that is not the seed's is the fresh deck's: the app refuses
            // fixtures that share an id, so there is no third source on screen.
            renderedFresh: rendered.filter { !seedIds.contains($0) }.count,
            latestUptime: events.map(\.uptime).max() ?? 0)
    }

    private enum ReadError: Error { case notYet }

    private func waitForState(
        _ app: XCUIApplication, _ what: String, timeout: TimeInterval,
        file: StaticString = #filePath, line: UInt = #line,
        until done: (State) -> Bool
    ) throws -> State {
        let deadline = Date().addingTimeInterval(timeout)
        var last: State?
        while Date() < deadline {
            if let state = try? read(app) {
                last = state
                if let failure = state.failure {
                    XCTFail("HARNESS: \(failure)", file: file, line: line)
                    throw XCTSkip("stopped on a harness failure")
                }
                if done(state) { return state }
            }
            Thread.sleep(forTimeInterval: 0.4)
        }
        if let last { attach(last, as: "10399-timeout-\(what)") }
        XCTFail("Not reached within \(Int(timeout)) s: \(what). Log: \(last?.events.map(\.name) ?? [])",
                file: file, line: line)
        throw XCTSkip("stopped: \(what)")
    }

    // MARK: - Evidence

    private func attach(_ state: State, as name: String) {
        let a = XCTAttachment(string: state.raw)
        a.name = name + ".json"
        a.lifetime = .keepAlways
        add(a)
        let t0 = state.events.first?.uptime ?? 0
        log("RECEIPT \(name) " + state.events.map {
            "\($0.seq):\($0.name)[\($0.detail)]+\(String(format: "%.2f", $0.uptime - t0))s"
        }.joined(separator: " "))
    }

    private func snap(_ name: String) {
        let a = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        a.name = name
        a.lifetime = .keepAlways
        add(a)
    }

    private func log(_ line: String) { print("10399-LOG \(line)") }
}
