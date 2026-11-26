import XCTest

/// #11177 — the event page's Share control is a 44 pt target, measured on the
/// running app: its frame is at least 44×44, and a tap 20 pt above or below its
/// centre (inside 44, outside the 24×36 pt the toolbar gave it on f62502f156)
/// opens the system share sheet.
///
/// Opt-in with `BL_EVENT_SHARE_ROUTE` (`bainluck://events/<id>`); without it the
/// test skips, matching `ATapNearTheMoreEdgeOpensItsMenu10880Tests`.
final class ATapNearTheShareEdgeOpensItsSheet11177Tests: XCTestCase {

    private var route: String? {
        ProcessInfo.processInfo.environment["BL_EVENT_SHARE_ROUTE"]
    }

    func testTheShareControlIsAtLeast44By44() throws {
        let app = try launch()
        let share = shareButton(app)
        XCTAssertTrue(share.waitForExistence(timeout: 65), "the game page showed no Share button")
        XCTAssertGreaterThanOrEqual(share.frame.height, 44, "Share frame \(share.frame)")
        XCTAssertGreaterThanOrEqual(share.frame.width, 44, "Share frame \(share.frame)")
    }

    func testATapNearTheTopEdgeOpensTheShareSheet() throws {
        try assertTapOpensShareSheet(dy: -20)
    }

    func testATapNearTheBottomEdgeOpensTheShareSheet() throws {
        try assertTapOpensShareSheet(dy: 20)
    }

    private func assertTapOpensShareSheet(dy: CGFloat) throws {
        continueAfterFailure = false
        let app = try launch()
        let share = shareButton(app)
        XCTAssertTrue(share.waitForExistence(timeout: 65), "the game page showed no Share button")
        let centre = share.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        centre.withOffset(CGVector(dx: 0, dy: dy)).tap()
        let activitySheet = app.otherElements["ActivityListView"]
        XCTAssertTrue(
            activitySheet.waitForExistence(timeout: 5),
            "a tap \(dy) pt from Share's centre opened no share sheet (frame \(share.frame))"
        )
    }

    private func launch() throws -> XCUIApplication {
        guard let route else { throw XCTSkip("BL_EVENT_SHARE_ROUTE names no game") }
        return UITestLaunch.launchApp(extra: ["-launch_route", route])
    }

    private func shareButton(_ app: XCUIApplication) -> XCUIElement {
        app.navigationBars.buttons.matching(NSPredicate(format: "label == %@", "Share")).firstMatch
    }
}
