import XCTest

/// CHECK 6: **a reader can tap a card, land on the event, and get back.**
///
/// Every previous walkthrough reached event detail by `-launch_route`, which
/// hands the URL straight to `NavigationCoordinator.handleURL`. That exercises
/// the destination view and it skips the entire route a reader takes: the card's
/// `onTapGesture`, the `Route` it appends, the push, and the pop. A deep link
/// proves the screen renders. It cannot prove the screen is REACHABLE, and
/// "reachable" is the half of check 6 that was UNKNOWN.
///
/// The back half is not decoration. A screen a reader can enter and not leave is
/// a trapped reader, and it is invisible to any test that only ever navigates
/// forward.
final class AReaderCanOpenACardAndComeBackTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testTappingACardOpensTheEventAndBackReturnsToDiscover() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        let card = try JourneyPrecondition.firstEventCard(in: app)

        let discover = app.navigationBars["Discover"]
        XCTAssertTrue(discover.exists, "Not on Discover before the tap; the pop assertion below would prove nothing.")

        card.tap()

        // A push is the assertion, and "some other navigation bar" is how to
        // state it without pinning the destination's TITLE. The event page's
        // title is the matchup, which is data, and a test keyed on it would red
        // whenever the feed's first card changed — i.e. constantly, for no
        // reason connected to navigation.
        XCTAssertTrue(
            discover.waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "Tapped a Discover card and the Discover navigation bar never went away — no push happened. "
            + "The card opens on `.onTapGesture` (DiscoverEventCard), so this is the gesture not landing, not a routing bug."
        )

        let backButton = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(
            backButton.waitForExistence(timeout: 5),
            "The pushed screen has no navigation-bar button at all, so there is no way back from it by tapping."
        )

        backButton.tap()

        XCTAssertTrue(
            discover.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Back did not return to Discover. A reader who opens a card is stranded on it."
        )
        XCTAssertTrue(
            app.descendants(matching: .any).matching(identifier: "discover-card-event").firstMatch
                .waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Came back to Discover and it had no cards. Returning to an empty feed is the same defect as not returning."
        )
    }

    /// Recoverable navigation across TABS, which is a different mechanism.
    ///
    /// The push above is one `NavigationStack`'s path. Switching tabs and coming
    /// back is `MainTabView`'s selection plus each tab's own retained state, and
    /// it has its own failure — a tab that rebuilds from nothing on every visit,
    /// or one that comes back to a screen the reader never left it on.
    func testLeavingDiscoverForAnotherTabAndComingBackLandsOnDiscover() {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)

        XCTAssertTrue(
            app.navigationBars["Discover"].waitForExistence(timeout: UITestLaunch.launchTimeout),
            "Cold launch did not land on Discover."
        )

        JourneyPrecondition.openTab("Browse", in: app)

        // THE ASSERTION THIS TEST WAS MISSING, and the only one here that a
        // stationary app can fail. The other three — a tab bar exists, the
        // Discover navigation bar exists, it exists again at the end — are all
        // equally true of an app that never moved, so without this line "came
        // back to Discover" is also satisfied by never having left it.
        //
        // Nothing here was checking the tab CHANGED. That was delegated entirely
        // to `openTab`, and `openTab` answers a different question: it waits for
        // the tab BUTTON to report `isSelected`, which is a property of the tab
        // bar rather than of the screen. The destination is what the tab was
        // for, so the destination is what gets asserted.
        //
        // Proved load-bearing by mutation (2026-09-15) rather than by the
        // `--rearm-first-run-gates` control, which cannot block this particular
        // test: its first tap does land nowhere (`Computed hit point {-1, -1}`),
        // but XCUITest clears the sheet as an interrupting element before
        // `openTab`'s one retry, so the app is genuinely unblocked by then. The
        // mutant that kills it is pointing `openTab` at the already-selected
        // Discover tab — no navigation, and this line goes red.
        XCTAssertTrue(
            app.navigationBars["Discover"].waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "Tapped the Browse tab and the Discover navigation bar is still on screen — the app never left Discover, so the return below would prove nothing."
        )

        JourneyPrecondition.openTab("Discover", in: app)

        XCTAssertTrue(
            app.navigationBars["Discover"].waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Came back to the Discover tab and it is not showing Discover."
        )
    }
}
