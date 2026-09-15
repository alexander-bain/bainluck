import XCTest

/// The rig's own self-test: can an unattended session in this sandbox TAP?
///
/// Every native walkthrough since #3157 has reached screens by `-launch_route`
/// alone, and every one of them has had to write the same sentence: swipe,
/// pull-to-refresh, back and card→detail are **UNKNOWN, not PASS**. The reason
/// given was always the same — this sandbox has no macOS Accessibility
/// permission, so `osascript`/System Events taps fail with error `-54`, and
/// there is no `cliclick` and no `idb`.
///
/// That reason is true and it is about the WRONG CHANNEL. Those three tools all
/// drive the simulator from OUTSIDE, as if it were a Mac window, which is
/// exactly what needs the Accessibility grant. XCUITest drives it from inside:
/// the test runner is itself an app on the simulator and talks to the
/// simulator's own accessibility server. No TCC grant is asked for and none is
/// bypassed.
///
/// So this file exists before any journey test does, and it asserts the one
/// thing the journey tests all silently assume. If the premise is false, this
/// fails alone and says so in one line, rather than being diagnosed out of a
/// journey test that looks like a product defect.
final class CanThisRigTapAtAllTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// Launch, find the tab bar, tap a tab, and prove the app CHANGED.
    ///
    /// The assertion is deliberately on a state change and not on "the tap did
    /// not throw". `XCUIElement.tap()` on an element that exists but is not
    /// hittable is a no-op that raises nothing, so a test that taps and then
    /// asserts the tab bar still exists passes on a rig that cannot tap at all
    /// — a green light wired to no sensor. Selecting a DIFFERENT tab and
    /// requiring its content is the cheapest assertion that can only be true if
    /// a real touch was delivered.
    func testTheRigCanDeliverATouchAndTheAppRespondsToIt() {
        let app = XCUIApplication()
        app.launchArguments += UITestLaunch.arguments
        app.launch()

        let tabBar = app.tabBars.firstMatch
        XCTAssertTrue(
            tabBar.waitForExistence(timeout: UITestLaunch.launchTimeout),
            "No tab bar after launch — the app did not reach MainTabView, so nothing below this can be read as a tap result."
        )

        let searchTab = tabBar.buttons["Search"]
        XCTAssertTrue(searchTab.exists, "No 'Search' tab button. Tabs are Discover/Sports/Browse/Search/My Stuff (MainTabView.swift).")

        // Discover is the default tab, so "Search is selected" is a state the
        // app cannot be in unless the touch landed.
        XCTAssertFalse(searchTab.isSelected, "Search was ALREADY selected before the tap — the default tab is Discover, so this test cannot tell a tap from the initial state.")

        searchTab.tap()

        XCTAssertTrue(
            // Generous, because a tab switch waits for the destination tab to go
            // idle and a tab that loads from the network takes seconds to do it.
            // A tight timeout here would report "the rig cannot tap" — the most
            // alarming sentence in this target — about a rig that tapped fine.
            searchTab.waitForSelected(timeout: UITestLaunch.contentTimeout),
            "Tapped the Search tab and it did not become selected. THE RIG CANNOT TAP — every journey test in this target is void until this passes."
        )
    }
}
