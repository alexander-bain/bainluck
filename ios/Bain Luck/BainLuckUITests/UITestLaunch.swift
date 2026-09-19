import XCTest

/// The launch arguments every test in this target passes, and the waits they
/// are allowed to use.
///
/// Centralised because the two first-run gates below mask EVERY subsequent
/// assertion when they are missed, and they do it in a way that reads as a
/// product defect rather than a rig defect:
///
///   * the telemetry consent sheet covers Discover on a clean install, so
///     `app.cells.count == 0` is true and means nothing about the feed;
///   * the notification permission alert is **SpringBoard-owned** — it survives
///     app terminate AND uninstall/reinstall (measured, native/169), so it
///     cannot be cleared by anything the test does to the app.
///
/// Both are answered through the app's OWN affordances, which is what
/// `tools/native-walk.sh` already does for the screenshot rig. Nothing here
/// touches TCC and nothing here is a bypass: `-suppress_notification_prompt`
/// means the app never ASKS, which is a decision the app is entitled to make
/// about its own prompt.
enum UITestLaunch {

    /// Present Discover's first-run sheet ON PURPOSE, to prove this target's
    /// assertions can still see a blocked app.
    ///
    /// A journey suite has a sensor problem it cannot detect from the inside: a
    /// test whose every assertion is satisfied by "nothing happened" reports PASS
    /// forever and looks exactly like a test that walked. Re-arming the gate is
    /// the negative control — with the app behind a modal, EVERY test here must
    /// go red, and any test that stays green is asserting nothing.
    ///
    /// Measured 2026-09-15 on `29d42093`, which is why this switch exists: 2 of
    /// 10 stayed green — check 5 (`testDiscoverOpensOnRealCards`, which asserted
    /// its cards EXIST, and they do underneath a modal) and check 6's tab
    /// round-trip. Both have since been given the assertion they were missing.
    /// The control now holds 9 red + 1 named exemption: it cannot block the tab
    /// round-trip, because XCUITest clears the sheet as an interrupting element
    /// before that test's one retry. The script names it and says why; that test's
    /// new assertion is proved by mutation instead. Re-run whenever a test is added:
    ///
    ///     tools/native-uitest.sh --rearm-first-run-gates
    ///
    /// Read as an environment variable rather than a launch argument because it
    /// configures the TEST RUNNER's idea of how to launch the app, not the app.
    static var firstRunGatesAreReArmed: Bool {
        ProcessInfo.processInfo.environment["BL_UITEST_REARM_FIRST_RUN_GATES"] == "1"
    }

    /// Launch arguments in `simctl`'s `-key value` form, which is also
    /// `UserDefaults`' — the same channel `LaunchRig` and `NotificationManager`
    /// already read.
    static var arguments: [String] { [
        // NotificationManager.suppressPromptKey — never ask for notifications.
        "-suppress_notification_prompt", "YES",
        // TelemetryConsent.storageKey — `none` is exactly what tapping
        // "No thanks" records (ConsentLevel.none), so the sheet is already
        // answered and never presents.
        "-bainluck_telemetry_consent", "none",
        // DiscoverView's welcome sheet (`discover_onboarded`). The SECOND
        // first-run gate over Discover, and it was missed when this file was
        // written because the container in front of the rig that day had already
        // been through it. Measured 2026-09-14 on a genuinely clean install: the
        // sheet presents over Discover and the ONLY two hittable buttons in the
        // whole app are its "Continue" and "Skip" — the tab bar reports
        // `hittable == false` at correct geometry `(0, 791, 402, 83)`, so a tab
        // tap logs `Computed hit point {-1, -1}` and lands nowhere. That reads as
        // "THE RIG CANNOT TAP", which is the most alarming and most misleading
        // sentence this target can print: the rig taps fine, the app is behind a
        // modal. `WelcomeView`'s own `onDisappear` writes exactly this key, so
        // setting it is the same answer a reader gives by tapping Skip.
        "-discover_onboarded", firstRunGatesAreReArmed ? "NO" : "YES",
        // LaunchRig.suppressInteractionUploadKey — a swipe and a card open each
        // POST to `/api/feed/interactions`. A reader's taps are the downrank
        // signal that endpoint is for; a robot's taps are noise in it, and
        // standing notice 39 says our own robots are TAGGED, never minted. So
        // this target taps freely and writes nothing.
        "-launch_no_interaction_upload", "YES",
        // NotificationManager.suppressPromptKey. The permission alert lands over
        // Discover a few seconds after launch and belongs to SpringBoard, not to
        // the app, so nothing this target asserts can see it and every gesture
        // after it arrives is aimed at a dialog. Measured 2026-09-18
        // (native/240): one run in three of the footer-refresh journey logged
        // `Default interruption handler attempting to dismiss alert by tapping
        // "Allow"` at t=30.9s and failed; the two runs without the alert passed
        // the same assertion on the same sha. XCUITest's interruption monitor
        // does clear it, but only after it has already eaten a gesture — and it
        // is the difference between a green journey and a red one.
        //
        // `tools/native-walk.sh` has passed this flag since it was written and
        // says why in its header; this target never did, so every journey in it
        // has been exposed to a race it did not need to run.
        "-suppress_notification_prompt", "YES",
    ] }

    /// The activity every launch logs, naming which mode the run is in.
    ///
    /// `--rearm-first-run-gates` is worthless if it can fail to arrive and leave
    /// the run looking normal: a control that did not control reports "these
    /// tests are green against a blocked app" about an app that was never
    /// blocked, which is a false accusation aimed at the suite. Measured
    /// 2026-09-15 — the first draft passed the switch as an xcodebuild build
    /// setting, which reaches the BUILD environment and not the runner's, and
    /// the control came back 10/10 green looking exactly like a real finding.
    /// So the runner says out loud what it is doing and the script refuses to
    /// report a control that cannot show this line.
    static var modeActivityName: String {
        "first-run gates: " + (firstRunGatesAreReArmed ? "RE-ARMED (negative control)" : "answered")
    }

    /// Launch the app under test with this target's standing arguments.
    ///
    /// Every test goes through here so no test can quietly omit the
    /// interaction-upload suppression and start writing to production — the one
    /// mistake in this target that would not show up as a red test. `extra` is
    /// for the flags one test needs (the debug badge) and exists so that needing
    /// one is not a reason to hand-roll a launch and drop the suppression.
    @discardableResult
    static func launchApp(extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments += arguments + extra
        XCTContext.runActivity(named: modeActivityName) { _ in }
        app.launch()
        return app
    }

    /// How long a cold launch may take before the test calls it a failure.
    ///
    /// Generous on purpose. This is NOT a latency measurement and must never be
    /// read as one — a timeout that a launch passes says only that the launch
    /// finished inside it. Launch-time measurement is its own instrument
    /// (`ScreenTiming`), proved separately; until then launch latency stays
    /// UNKNOWN rather than being inferred from a green test.
    static let launchTimeout: TimeInterval = 30

    /// How long a screen's own network load may take after it is on screen.
    ///
    /// Separate from ``launchTimeout`` because it is a different wait: mounting
    /// the app and filling a screen from the API are different failures and
    /// collapsing them into one number makes a slow feed read as a broken tap.
    static let contentTimeout: TimeInterval = 30
}

extension XCUIElement {

    /// Wait for this element to report itself SELECTED.
    ///
    /// `waitForExistence` cannot express this and `isSelected` read immediately
    /// after a `tap()` races the animation, so a bare assert flakes in the
    /// direction that matters least — a red on a working app. Polling on the
    /// predicate is what XCTest is for.
    func waitForSelected(timeout: TimeInterval) -> Bool {
        let selected = NSPredicate(format: "isSelected == true")
        let expectation = XCTNSPredicateExpectation(predicate: selected, object: self)
        return XCTWaiter().wait(for: [expectation], timeout: timeout) == .completed
    }

    /// Wait for this element to STOP existing.
    ///
    /// The other half of `waitForExistence`, and the one a back-navigation test
    /// needs: "the detail screen is gone" is the assertion, and asserting
    /// `!exists` immediately after a tap races the pop animation.
    func waitForNonExistence(timeout: TimeInterval) -> Bool {
        let gone = NSPredicate(format: "exists == false")
        let expectation = XCTNSPredicateExpectation(predicate: gone, object: self)
        return XCTWaiter().wait(for: [expectation], timeout: timeout) == .completed
    }
}
