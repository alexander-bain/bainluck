import XCTest

/// Telling "the tap path is broken" from "there was nothing to tap".
///
/// A tap-driven journey test has two ways to not-pass and they mean opposite
/// things. If the feed is empty, a navigation test that reports FAIL is blaming
/// navigation for a data outage; if it reports PASS it is reporting a journey it
/// never walked. Either way the next reader is misled, and the second way is
/// worse because it is silent.
///
/// So the two are separated by construction:
///
///   * the thing under test — the gesture, the push, the pop — is an
///     `XCTAssert`, and a miss is a hard red;
///   * the thing the test needs in order to start — a card on screen, a search
///     result to open — is an `XCTSkip` naming what was missing.
///
/// A skip is not a pass. `xcodebuild` counts it separately and
/// `tools/native-uitest.sh` prints the count, so a run that skipped its way to
/// green cannot be read as a run that walked the journey.
///
/// Check 5 is the deliberate exception and it is the reason this file does not
/// simply skip everywhere: "Discover opens with real cards" IS the check, so an
/// empty feed there is a FAILURE, not a precondition.
enum JourneyPrecondition {

    /// Wait for the app to reach its tab bar, or fail — this one is never a skip.
    ///
    /// Reaching `MainTabView` at all is a property of the app and not of the
    /// data behind it, so there is no outage that excuses it.
    @discardableResult
    static func tabBar(of app: XCUIApplication, file: StaticString = #filePath, line: UInt = #line) -> XCUIElement {
        let tabBar = app.tabBars.firstMatch
        XCTAssertTrue(
            tabBar.waitForExistence(timeout: UITestLaunch.launchTimeout),
            "No tab bar \(UITestLaunch.launchTimeout)s after launch — the app never reached MainTabView.",
            file: file, line: line
        )
        return tabBar
    }

    /// Switch to a tab and wait for it to be selected — or fail naming the tab.
    ///
    /// Two rig facts are built in, both measured on 2026-09-14:
    ///
    ///   * `XCUIElement.waitForSelected` (an `XCTNSPredicateExpectation`) missed
    ///     a selection that a plain re-resolve-and-read loop saw immediately, so
    ///     this polls by re-resolving the button each time. Every read is a
    ///     fresh query rather than a re-evaluation of a snapshot.
    ///   * a tap on a tab button occasionally logs `Computed hit point {-1, -1}`
    ///     and lands nowhere, while the app is still mounting its first tab. ONE
    ///     retry covers it. The retry is bounded and counted on purpose: taps
    ///     landing is the premise `CanThisRigTapAtAllTests` exists to assert, and
    ///     a helper that retried forever would quietly hide the day it stops
    ///     being true.
    @discardableResult
    static func openTab(
        _ name: String,
        in app: XCUIApplication,
        file: StaticString = #filePath,
        line: UInt = #line
    ) -> XCUIElement {
        let tabBar = Self.tabBar(of: app, file: file, line: line)
        XCTAssertTrue(
            tabBar.buttons[name].waitForExistence(timeout: 10),
            "No '\(name)' tab. Tabs are Discover/Sports/Browse/Search/My Stuff (MainTabView).",
            file: file, line: line
        )

        for attempt in 1...2 {
            tabBar.buttons[name].tap()
            let deadline = Date().addingTimeInterval(UITestLaunch.contentTimeout / 2)
            while Date() < deadline {
                if tabBar.buttons[name].isSelected { return tabBar }
                Thread.sleep(forTimeInterval: 0.5)
            }
            if attempt == 1 {
                XCTContext.runActivity(named: "retrying the '\(name)' tab tap") { _ in }
            }
        }

        XCTFail(
            "The '\(name)' tab did not become selected after two taps, over \(UITestLaunch.contentTimeout)s.",
            file: file, line: line
        )
        return tabBar
    }

    /// Wait for a query's match count to stop moving, then answer it.
    ///
    /// A feed that is still laying out will accept a gesture and drop it. The
    /// first draft of the swipe test swiped 1.2 seconds after the first card
    /// appeared and the card ignored it; the same swipe seven seconds later
    /// dismissed it every time. That is a rig defect and it reads exactly like
    /// #1773 — a card that silently ignores a swipe — which is the defect the
    /// test exists to catch, so the two must not be confusable.
    @discardableResult
    static func settle(_ query: XCUIElementQuery, timeout: TimeInterval = 20) -> Int {
        var last = -1
        var stableReads = 0
        let deadline = Date().addingTimeInterval(timeout)
        while Date() < deadline {
            let now = query.count
            stableReads = (now == last) ? stableReads + 1 : 0
            last = now
            if stableReads >= 2 { return now }
            Thread.sleep(forTimeInterval: 0.75)
        }
        return last
    }

    /// The first Discover event card, or a SKIP saying the feed had none.
    ///
    /// `discover-card-event` is set on the card's tap target
    /// (`NativeEventDiscoverCard.tapTargetIdentifier`). Matching on the
    /// identifier rather than on any text inside the card is what keeps a
    /// copy-formatting ship from reddening a navigation test.
    static func firstEventCard(in app: XCUIApplication) throws -> XCUIElement {
        let card = app.descendants(matching: .any)
            .matching(identifier: "discover-card-event")
            .firstMatch
        guard card.waitForExistence(timeout: UITestLaunch.contentTimeout) else {
            throw XCTSkip(
                "NOT WALKED: no Discover event card within \(UITestLaunch.contentTimeout)s, so there was nothing to tap. "
                + "This says nothing about navigation. If it is not a transient outage it is check 5 failing — read that test's result, not this skip."
            )
        }
        return card
    }
}
