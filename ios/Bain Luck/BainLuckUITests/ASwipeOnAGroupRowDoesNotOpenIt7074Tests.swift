import XCTest

/// #7074 — **a swipe on a group card's row took the reader to the detail page.**
///
/// Alex, physical phone, TestFlight 1.0 (15), on the UFC futures group:
///
///   "when I try to swipe left to positively influence the ranking on that UFC
///   grouping card, it starts to let me swipe left and then it just takes me
///   straight into a UFC futures page"
///
/// (The direction in that sentence is his memory of the mapping, not a defect:
/// left is less-like-this, right is more. #7074's brief says so explicitly. What
/// is a defect is the second half of it.)
///
/// ## Why this is only a defect on GROUP cards
///
/// Every Discover card is wrapped in `SwipeToDismiss`, which attaches its drag
/// with `.simultaneousGesture` — deliberately, so the enclosing `ScrollView` can
/// still pan. Simultaneous means the card's own tap targets stay live for the
/// whole drag. On an event or futures card that costs nothing: those navigate
/// from an `onTapGesture`, and a tap gesture cancels itself as soon as the finger
/// travels. A `NavigationLink` does not — it is a button, and a button fires on
/// touch-up anywhere inside its bounds, however far the finger wandered first.
/// `NativeCompactFuturesRow` is a `NavigationLink`, and it is the whole body of a
/// group card.
///
/// So the specimen has to be the card that can express the defect, and "a
/// Discover card" cannot find it: `SwipeToDismiss.tapTargetIdentifier` is shared
/// by all ten call sites by design. `NativeCompactFuturesRow.rowIdentifier`
/// exists for this journey.
///
/// ## What is asserted
///
/// That the reader is still on Discover. Not that the card was dismissed —
/// whether a given drag commits depends on how far XCUITest's `swipeLeft()`
/// travels on this device, and a test that required a dismissal would be
/// asserting the simulator's gesture metrics. Navigation is binary and it is
/// the thing Alex reported.
final class ASwipeOnAGroupRowDoesNotOpenIt7074Tests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// How many swipes to spend looking for a group card.
    ///
    /// Group/bundle cards were 8 of 50 on the feed measured 2026-09-17, so one
    /// is normally on the first two screens. Bounded so a feed that happens to
    /// serve none skips with a reason instead of hanging the suite.
    private static let swipeBudget = 25

    func testAHorizontalDragOnAGroupRowDoesNotNavigate() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let scrollView = app.scrollViews.firstMatch
        XCTAssertTrue(scrollView.exists, "Discover has no scroll view to walk.")

        let rows = app.descendants(matching: .any)
            .matching(identifier: "discover-group-row")

        var swipes = 0
        while swipes < Self.swipeBudget, !(rows.firstMatch.exists && rows.firstMatch.isHittable) {
            scrollView.swipeUp()
            swipes += 1
        }

        try XCTSkipUnless(
            rows.firstMatch.exists && rows.firstMatch.isHittable,
            "NOT WALKED: \(swipes) swipes found no group card with a touchable row, so the gesture "
            + "under test had nothing to start on. Group cards are a supply fact of the night's feed."
        )

        let row = rows.firstMatch

        // THE PRECONDITION THAT MAKES THE ASSERTION MEAN ANYTHING: we are on
        // Discover now. Without it, a test that never left a detail page it was
        // already on would read as a pass.
        XCTAssertTrue(
            app.navigationBars["Discover"].exists,
            "The journey did not start on Discover, so 'still on Discover' below would prove nothing."
        )

        // The gesture, on the ROW rather than on the card, because where the
        // finger LANDS is the whole mechanism: the same drag starting two
        // millimetres lower — on the card's padding rather than on the link —
        // has never navigated.
        row.swipeLeft()

        // Navigation is not instant: the push animates. Sample for long enough
        // that "we did not navigate" is a finding rather than a race, and stop
        // early the moment we HAVE navigated so a failure is fast.
        var landedOnDetail = false
        let deadline = Date().addingTimeInterval(5)
        while Date() < deadline {
            if app.navigationBars["Market Details"].exists { landedOnDetail = true; break }
            Thread.sleep(forTimeInterval: 0.25)
        }

        XCTAssertFalse(
            landedOnDetail,
            """
            A horizontal drag that began on a group card's row opened the futures \
            detail page. The drag is attached with `.simultaneousGesture`, so the \
            row's `NavigationLink` stayed live underneath it and fired on touch-up \
            — the reader asked to rank the card and was taken off the feed instead. \
            This is Alex's build 15 report on the UFC group, reproduced.
            """
        )

        XCTAssertTrue(
            app.navigationBars["Discover"].waitForExistence(timeout: 5),
            "The swipe left Discover for somewhere that is not the futures detail page either."
        )
    }
}
