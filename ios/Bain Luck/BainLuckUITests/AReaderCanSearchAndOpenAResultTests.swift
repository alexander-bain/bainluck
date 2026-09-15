import XCTest

/// CHECK 7: **a reader can type a search and open what it finds.**
///
/// Search recall has been read before — by deep-linking `bainluck://search?q=…`
/// and photographing the page. That measures the API's answer. It does not touch
/// the keyboard, the field, the return key, or the row a reader taps, and those
/// are the parts of search that a reader experiences as "search".
///
/// The query is deliberately a stable one. `Red Sox` is a team that exists in
/// every season and is not a fixture that ages out overnight, so a red here is
/// about search and not about the calendar. The test still refuses to assert
/// WHICH rows come back: recall is its own measurement, and pinning a specific
/// result would turn a ranking change into a navigation failure.
///
/// ONE ROUTE, NAMED: this walks the SUBMITTED-RESULTS route — type, press
/// return, tap a result. The other route a reader has, tapping a live typeahead
/// suggestion while the keyboard is up, is NOT walked here and is not covered by
/// a green on this file, because it is currently unreliable: measured 2026-09-14
/// over nine attempts in three sessions, a team suggestion opened 4 times and
/// did nothing the other 5, while the Game suggestion directly beneath it in the
/// same list at the same moment opened every time. That is filed separately. A
/// test cannot both walk a path and be green while the path is a coin flip, and
/// pretending otherwise is how a suite stops meaning anything.
final class AReaderCanSearchAndOpenAResultTests: XCTestCase {

    /// A query whose subject does not expire. See the class note.
    private let stableQuery = "Red Sox"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testTypingAQueryProducesResultsAndOneOpensAndComesBack() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.openTab("Search", in: app)

        let field = app.textFields.firstMatch
        XCTAssertTrue(
            field.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "The Search tab has no text field (SearchView's is placeholdered 'Search teams, games, futures...')."
        )

        field.tap()
        field.typeText(stableQuery)

        // The field must hold what was typed. Not pedantry: a field that drops
        // characters under a debounce, or that a view model overwrites mid-type,
        // searches for something the reader did not ask for, and every assertion
        // after it would be about the wrong query.
        XCTAssertEqual(
            field.value as? String, stableQuery,
            "The field does not hold what was typed — the search below is not the reader's query."
        )

        // Press return. This is the reader's own submit, and it is also what
        // puts the keyboard away: the results list and the live suggestion list
        // are DIFFERENT lists (the suggestions are full-bleed 54pt rows, the
        // results are inset cards), so which one is on screen decides what a tap
        // below is testing.
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10), "No keyboard after tapping the search field.")
        app.keyboards.buttons["search"].tap()

        XCTAssertTrue(
            app.keyboards.firstMatch.waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "The keyboard stayed up after return, so the results list never got the screen."
        )

        // `matching`, NOT `containing`: `containing` selects buttons that hold a
        // DESCENDANT satisfying the predicate, which matched whole-screen
        // furniture rather than a row, and `.firstMatch` then tapped something
        // that navigates nowhere — reading exactly like "the row did not open".
        // Measured; the first draft of this test failed on it.
        let resultRow = app.buttons
            .matching(NSPredicate(format: "label CONTAINS[c] %@", "Red Sox"))
            .firstMatch
        guard resultRow.waitForExistence(timeout: UITestLaunch.contentTimeout) else {
            throw XCTSkip(
                "NOT WALKED: '\(stableQuery)' returned no row naming it within \(UITestLaunch.contentTimeout)s. "
                + "That is a RECALL finding and belongs to whoever owns search — this test is about the tap path and must not report it as one."
            )
        }

        let searchBar = app.navigationBars["Search"]
        XCTAssertTrue(searchBar.exists, "Not on the Search screen before opening a result.")
        let opened = resultRow.label

        resultRow.tap()

        XCTAssertTrue(
            searchBar.waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "Tapped the search result '\(opened)' and the Search navigation bar never went away — the row opened nothing."
        )

        let backButton = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(backButton.waitForExistence(timeout: 10), "The opened result has no navigation-bar button, so there is no way back from it.")
        backButton.tap()

        XCTAssertTrue(
            searchBar.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Back did not return to Search. A reader who opens a result loses their query."
        )
        XCTAssertEqual(
            app.textFields.firstMatch.value as? String, stableQuery,
            "Came back to Search and the query was gone. The reader has to retype to see the rest of their own results."
        )
    }
}
