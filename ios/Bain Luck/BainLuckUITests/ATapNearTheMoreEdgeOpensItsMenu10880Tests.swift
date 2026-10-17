import XCTest

/// #10880 — the event page's More control is a 44 pt target, measured on the
/// running app: its frame is at least 44 high, and a tap 20 pt above or below
/// its centre (inside 44, outside the 36 pt the toolbar gave it on f62502f156)
/// still opens "Add to Calendar".
///
/// Real network and opt-in: an eligible game is an upcoming, schedule-started
/// one, and which ids qualify changes every day. Set `BL_CALENDAR_ROUTE` to
/// one (`bainluck://events/<id>`); without it the test skips.
final class ATapNearTheMoreEdgeOpensItsMenu10880Tests: XCTestCase {

    private var route: String? {
        ProcessInfo.processInfo.environment["BL_CALENDAR_ROUTE"]
    }

    func testTheMoreControlIsAtLeast44High() throws {
        let app = try launch()
        let more = moreButton(app)
        XCTAssertTrue(more.waitForExistence(timeout: 65), "the eligible game page showed no More")
        XCTAssertGreaterThanOrEqual(more.frame.height, 44, "More frame \(more.frame)")
        XCTAssertGreaterThanOrEqual(more.frame.width, 44, "More frame \(more.frame)")
    }

    func testATapNearTheTopEdgeOpensTheMenu() throws {
        try assertTapOpensMenu(dy: -20)
    }

    func testATapNearTheBottomEdgeOpensTheMenu() throws {
        try assertTapOpensMenu(dy: 20)
    }

    private func assertTapOpensMenu(dy: CGFloat) throws {
        continueAfterFailure = false
        let app = try launch()
        let more = moreButton(app)
        XCTAssertTrue(more.waitForExistence(timeout: 65), "the eligible game page showed no More")
        // From the control's own centre, so a wider frame cannot pass by moving it.
        let centre = more.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        centre.withOffset(CGVector(dx: 0, dy: dy)).tap()
        let item = app.buttons["Add to Calendar"]
        XCTAssertTrue(item.waitForExistence(timeout: 5),
                      "a tap \(dy) pt from More's centre opened no menu (frame \(more.frame))")
    }

    private func launch() throws -> XCUIApplication {
        guard let route else { throw XCTSkip("BL_CALENDAR_ROUTE names no eligible game") }
        return UITestLaunch.launchApp(extra: ["-launch_route", route])
    }

    /// The game page's own toolbar control. Card buttons elsewhere can carry
    /// labels too; the navigation bar's cannot be confused with them.
    private func moreButton(_ app: XCUIApplication) -> XCUIElement {
        app.navigationBars.buttons.matching(NSPredicate(format: "label == %@", "More")).firstMatch
    }
}
