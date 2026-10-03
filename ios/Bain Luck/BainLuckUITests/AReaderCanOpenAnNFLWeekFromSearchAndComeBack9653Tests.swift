import XCTest

/// #9653 — **a reader who searches a club can open its published NFL week from
/// Search, open a game in it, and come Back → Back to the same query.**
///
/// Browse's entry is walked by `…FromBrowseAndComeBack9989Tests`; the hub → game
/// arm by `AHubMoreOnGameOpensTheGameAndComesBack10146Tests`. Neither types a
/// query. Search's Collections section is server-chosen from the page's own games
/// (`search_collections.py`), so the only honest entry is the one a reader uses:
/// type, return, tap the row.
///
/// SKIPS when production offers no collection for the query on any of the tries
/// below — the week was withdrawn or the season moved on, which is the calendar,
/// not navigation. The query is a club with a game in both published weeks.
final class AReaderCanOpenAnNFLWeekFromSearchAndComeBack9653Tests: XCTestCase {

    private let query = "Bills"

    /// The server attaches `collections` under a 0.25 s read budget and omits the
    /// key when the read overruns (measured 10/3: steelers 1 of 2 serves, eagles
    /// 0 of 2). Resubmitting is what a reader who expected the row would do; the
    /// attempt count is attached so the flake stays visible rather than absorbed.
    private let submits = 4

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testSearchOffersTheWeekAndBackBackKeepsTheQuery() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.openTab("Search", in: app)

        let field = app.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: UITestLaunch.contentTimeout), "The Search tab has no text field.")
        field.tap()
        field.typeText(query)
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10), "No keyboard after tapping the search field.")
        app.keyboards.buttons["search"].tap()

        let entries = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH %@", "search-collection-"))
        var tries = 1
        while !entries.firstMatch.waitForExistence(timeout: 12), tries < submits {
            tries += 1
            field.tap()
            XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10), "No keyboard on resubmit \(tries).")
            app.keyboards.buttons["search"].tap()
        }
        note("search submits until a Collections row appeared: \(entries.firstMatch.exists ? "\(tries)" : "never (\(tries))")")
        guard entries.firstMatch.exists else {
            attach(app, "search-no-collections")
            throw XCTSkip("NOT WALKED: '\(query)' carried no Collections row on \(tries) submits.")
        }
        _ = app.keyboards.firstMatch.waitForNonExistence(timeout: 10)

        let entry = entries.firstMatch
        let id = entry.identifier
        for _ in 0..<4 where !JourneyPrecondition.isReachable(entry, in: app) {
            JourneyPrecondition.liftContent(app, by: JourneyPrecondition.liftNeeded(for: entry, in: app) + 40)
        }
        let before = entry.frame.minY
        let searchBar = app.navigationBars["Search"]
        XCTAssertTrue(searchBar.exists, "Not on the Search screen before opening the collection.")
        attach(app, "1-search-before")

        entry.tap()
        XCTAssertTrue(searchBar.waitForNonExistence(timeout: UITestLaunch.contentTimeout),
                      "Tapped \(id) and Search is still the top screen.")
        let gameRows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "hub.moreOnGame."))
        XCTAssertTrue(gameRows.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "Tapped \(id) and the screen it opened shows no game of the week.")
        let hubBar = app.navigationBars.element(boundBy: 0)
        let hubTitle = hubBar.identifier
        note("hub navigation title: \(hubTitle)")
        attach(app, "2-hub")

        // The member is the game's own card — the tap target directly above its
        // "More on this game" row (ContainerHubView.memberCard). It carries no
        // identifier of its own, so press the card body, not the row.
        let row = gameRows.firstMatch
        for _ in 0..<4 where !JourneyPrecondition.isReachable(row, in: app) {
            JourneyPrecondition.liftContent(app, by: JourneyPrecondition.liftNeeded(for: row, in: app) + 40)
        }
        let rowId = row.identifier
        row.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0)).withOffset(CGVector(dx: 0, dy: -50)).tap()
        XCTAssertTrue(app.navigationBars[hubTitle].waitForNonExistence(timeout: UITestLaunch.contentTimeout),
                      "Pressed the game card above \(rowId) and the hub never went away.")
        attach(app, "3-game")

        let back1 = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back1.waitForExistence(timeout: 10), "The game page has no Back button.")
        back1.tap()
        XCTAssertTrue(app.navigationBars[hubTitle].waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "Back from the game did not return to the hub.")
        let sameRow = app.buttons[rowId]
        XCTAssertTrue(sameRow.waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "Back on the hub and the game the reader left from is gone (\(rowId)).")
        XCTAssertTrue(JourneyPrecondition.isReachable(sameRow, in: app),
                      "Back on the hub but not at the game the reader left from (\(rowId)).")
        attach(app, "4-hub-after")

        let back2 = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back2.waitForExistence(timeout: 10), "The hub has no Back button.")
        back2.tap()
        XCTAssertTrue(searchBar.waitForExistence(timeout: UITestLaunch.contentTimeout), "Back from the hub did not return to Search.")
        XCTAssertEqual(app.textFields.firstMatch.value as? String, query, "Back on Search and the query was gone.")
        let again = app.descendants(matching: .any)[id]
        XCTAssertTrue(again.waitForExistence(timeout: UITestLaunch.contentTimeout), "Back on Search and \(id) is gone.")
        attach(app, "5-search-after")
        XCTAssertEqual(again.frame.minY, before, accuracy: 1,
                       "Back on Search landed somewhere else (\(before) → \(again.frame.minY)).")
    }

    private func attach(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    private func note(_ text: String) {
        let a = XCTAttachment(string: text)
        a.name = "note"
        a.lifetime = .keepAlways
        add(a)
    }
}
