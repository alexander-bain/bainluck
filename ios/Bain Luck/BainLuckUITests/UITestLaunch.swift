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

    /// Launch arguments in `simctl`'s `-key value` form, which is also
    /// `UserDefaults`' — the same channel `LaunchRig` and `NotificationManager`
    /// already read.
    static let arguments: [String] = [
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
        "-discover_onboarded", "YES",
        // LaunchRig.suppressInteractionUploadKey — a swipe and a card open each
        // POST to `/api/feed/interactions`. A reader's taps are the downrank
        // signal that endpoint is for; a robot's taps are noise in it, and
        // standing notice 39 says our own robots are TAGGED, never minted. So
        // this target taps freely and writes nothing.
        "-launch_no_interaction_upload", "YES",
    ]

    /// Launch the app under test with this target's standing arguments.
    ///
    /// Every test goes through here so no test can quietly omit the
    /// interaction-upload suppression and start writing to production — the one
    /// mistake in this target that would not show up as a red test.
    static func launchApp() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments += arguments
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
