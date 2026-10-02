import XCTest

/// #10146 (Alex, build 34) — **on an NFL week hub, "More on this game" opens the
/// game page and Back returns to the same game on the hub.**
///
/// The unit suite pins the decision (which games get a row, that it routes to the
/// card's own game page, that the row records the game anchor). None of it proves
/// the row is a tap target that pushes, or that Back lands on the hub with the row
/// still there rather than a reloaded or emptied hub.
final class AHubMoreOnGameOpensTheGameAndComesBack10146Tests: XCTestCase {

    /// A real, currently-published edition. **This slug rots and is MEANT to** —
    /// once the week is withdrawn the hub says it isn't available and this SKIPS.
    /// Refresh it from `GET /api/containers/<slug>` for the current NFL week.
    private static let slug = "nfl-2026-week-4"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testMoreOnThisGameOpensTheGameAndBackReturnsToIt() throws {
        let app = UITestLaunch.launchApp(extra: [
            "-launch_route", "bainluck://containers/\(Self.slug)?name=NFL%20Week%204",
        ])
        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "hub.moreOnGame."))

        guard rows.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout) else {
            let unavailable = app.staticTexts
                .matching(NSPredicate(format: "label CONTAINS[c] %@", "isn't available"))
            if unavailable.firstMatch.exists {
                throw XCTSkip("\(Self.slug) is no longer published; refresh the slug and re-run.")
            }
            return XCTFail("The week hub drew no 'More on this game' row for any game.")
        }

        XCTAssertFalse(
            app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Related questions")).firstMatch.exists,
            "The hub still offers the inline 'Related questions (N)' toggle."
        )
        let row = rows.element(boundBy: rows.count > 1 ? 1 : 0)
        let rowId = row.identifier
        XCTAssertEqual(row.label.contains("More on this game"), true, "row label: \(row.label)")
        XCTAssertNil(row.label.range(of: #"\d"#, options: .regularExpression), "The row carries a count: \(row.label)")

        let hubBar = app.navigationBars["NFL Week 4"]
        XCTAssertTrue(hubBar.exists, "The hub has no navigation bar to come back to.")
        row.tap()

        XCTAssertTrue(
            hubBar.waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "Tapped 'More on this game' and the hub never went away — no push happened."
        )
        let backButton = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(backButton.waitForExistence(timeout: 5), "The game page has no Back button.")
        backButton.tap()

        XCTAssertTrue(hubBar.waitForExistence(timeout: UITestLaunch.contentTimeout), "Back did not return to the hub.")
        let sameRow = app.buttons[rowId]
        XCTAssertTrue(sameRow.waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "Came back to the hub and the game's row was gone (\(rowId)).")
        XCTAssertTrue(sameRow.isHittable, "Came back to the hub but not to the game the reader left from (\(rowId)).")
    }
}
