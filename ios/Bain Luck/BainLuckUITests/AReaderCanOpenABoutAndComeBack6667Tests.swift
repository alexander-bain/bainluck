import XCTest

/// #6667 / #6444 — **a reader can open a fight card, open one bout, and get back
/// to the card.**
///
/// The unit suite pins what the screen DECIDES: which key, which id space, who is
/// named a winner, what a 404 means. None of it proves the screen is reachable or
/// that a bout row is a tap target — `ConceptCardView`'s rows are
/// `NavigationLink`s inside a `ScrollView`, and a row that draws correctly and
/// does not push is invisible to every test in `BainLuckTests`.
///
/// This is the same argument `AReaderCanOpenACardAndComeBackTests` makes for
/// Discover, one level down: that test is destination-agnostic and so it already
/// covers the tap that OPENS a fight card. What it cannot cover is the screen the
/// fight card pushes, because that screen did not exist when it was written.
///
/// The back half carries the weight here. #6667's whole complaint is that tapping
/// a UFC card stranded the reader on the wrong screen; shipping a right screen
/// they cannot leave would be the same defect wearing a better title.
final class AReaderCanOpenABoutAndComeBack6667Tests: XCTestCase {

    /// A real, currently-served card. **This key rots and is MEANT to** — the
    /// server stops resolving a card once its markets close (measured
    /// 2026-09-17: `event:ufc:26sep12`, served on the 12th, 404s on the 17th).
    ///
    /// When it goes, this test SKIPS rather than reds: a 404 is the server's
    /// correct answer about a finished card, not a navigation defect, and a red
    /// here would send the next reader hunting a bug in the push. Refresh it from
    /// `GET /api/feed` — any concept card's `data.key` whose domain is `ufc`.
    private static let cardKey = "event:ufc:26sep19"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testOpeningABoutFromAFightCardAndComingBack() throws {
        let app = UITestLaunch.launchApp(extra: ["-launch_route", "bainluck://event/ufc/26sep19"])

        // The rows, not the title: the title is the card's name, which is data.
        let bouts = app.descendants(matching: .any).matching(identifier: "concept-bout-row")

        guard bouts.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout) else {
            // Distinguish "the card is gone" (fine, skip) from "the card loaded
            // and drew no rows" (a real failure, and the one worth a red).
            let unavailable = app.staticTexts
                .containing(NSPredicate(format: "label CONTAINS[c] %@", "isn't available"))
            if unavailable.firstMatch.exists {
                throw XCTSkip(
                    "\(Self.cardKey) no longer resolves — the server 404s a card whose markets have "
                    + "closed, which is the documented answer, not a defect. Refresh the key from "
                    + "GET /api/feed and re-run."
                )
            }
            return XCTFail(
                "The fight card mounted and drew no bout rows, and the server did not say the card "
                + "is unavailable. A card screen with nothing on it is the #6667 defect with a new title."
            )
        }

        let boutCount = bouts.count
        XCTAssertGreaterThan(boutCount, 1, "A UFC card is a card of bouts; one row means the list collapsed.")

        // `MAIN EVENT` is the row ordering's only reader-visible claim, and it is
        // the one thing about this list a reader could catch us getting wrong:
        // the server sends the headline fight LAST and the phone must show it
        // first. Asserted here rather than in the unit suite because it is the
        // rendered order that matters.
        XCTAssertTrue(
            app.staticTexts["MAIN EVENT"].exists,
            "No bout is marked MAIN EVENT, so the card's headline fight is not identified on screen."
        )

        let cardBar = app.navigationBars.firstMatch
        let cardTitle = cardBar.identifier
        XCTAssertFalse(cardTitle.isEmpty, "The fight card has no navigation bar, so there is nothing to come back to.")

        bouts.firstMatch.tap()

        XCTAssertTrue(
            app.navigationBars[cardTitle].waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "Tapped a bout row and the fight card's navigation bar never went away — no push happened. "
            + "The rows are NavigationLinks inside a ScrollView, so this is the link not resolving a "
            + "Route, which is exactly what `boutTarget` refusing an unknown source looks like on screen."
        )

        let backButton = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(
            backButton.waitForExistence(timeout: 5),
            "The bout screen has no navigation-bar button, so a reader who opens a bout is stranded on it."
        )

        backButton.tap()

        XCTAssertTrue(
            app.navigationBars[cardTitle].waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Back from a bout did not return to the fight card."
        )
        XCTAssertTrue(
            bouts.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Came back to the fight card and its bouts were gone. Returning to an empty card is the "
            + "same defect as not returning — and it is what a view model that re-enters `.loading` "
            + "on every appear would do."
        )
        XCTAssertEqual(
            bouts.count, boutCount,
            "The card came back with a different number of bouts than it had before the push."
        )
    }

    /// The other destination this screen can reach, and the one a reader hits by
    /// tapping a card the feed cached and the server has since retired (#6733).
    /// It must be a dead end with a way out, never a Retry that cannot work.
    func testARetiredCardSaysSoAndOffersAWayOut() {
        let app = UITestLaunch.launchApp(extra: ["-launch_route", "bainluck://event/ufc/26sep12"])

        let unavailable = app.staticTexts
            .containing(NSPredicate(format: "label CONTAINS[c] %@", "isn't available"))
        XCTAssertTrue(
            unavailable.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "A 404 card drew neither its bouts nor an explanation. Measured 2026-09-17: "
            + "event:ufc:26sep12 returns 404."
        )
        XCTAssertFalse(
            app.buttons["Retry"].exists,
            "A retired card offers Retry. Retrying a 404 cannot change the answer (UX-P031/#1599); "
            + "a button that cannot work is worse than no button."
        )
        XCTAssertTrue(
            app.buttons.containing(NSPredicate(format: "label BEGINSWITH[c] %@", "See all")).firstMatch.exists,
            "A retired card is a dead end with no onward link, so the reader's only move is Back."
        )
    }
}
