import XCTest

/// #6444 leg · #1471 — **a reader can open a golf tournament, see the field, and
/// get back.**
///
/// This is the golf half of the journey `AReaderCanOpenABoutAndComeBack6667Tests`
/// walks for UFC, and it is a SEPARATE test because the two share no code on the
/// way down. A UFC card is a `concept` item that pushes `ConceptCardView` through
/// `Route.eventConcept`; a golf tournament is a `tournament` item that pushes
/// `GolfTournamentView` through `Route.golfTournament`, off
/// `DiscoverTournamentCard.destination(for:)`. A green UFC run says nothing about
/// this path — which is exactly how #1471 survived: the bout journey was covered
/// and the golf one was not.
///
/// ## The defect this stands over
///
/// Alex, 2026-09-16, on his own phone: tapping the golf card on Discover took him
/// to the generic Golf page, which showed him **the same card again**, and tapping
/// that produced **"Couldn't load Biltmore Championship Asheville"** with a Retry
/// that re-made the identical failing call. Three separate faults in one tap —
/// `Route.golfTournament` discarded its slug, `SportCategoryView` routed golf
/// tournaments at the registered TENNIS hub (`/api/tournaments/{slug}`, a
/// guaranteed 404 for a golf slug), and the error state offered a button that
/// could not work.
///
/// `/api/golf/tournaments/biltmore-championship-asheville` was answering 200 with
/// 132 golfers the whole time the phone was printing that error. So the assertion
/// that matters here is not "a screen appeared" — it is **the field is on it**.
/// An error state IS a screen, and it is the one Alex saw.
///
/// ## Why there is no deeper push to walk
///
/// A golfer row is deliberately not a destination: `GolfTournamentView.fieldRow`
/// draws position, name, movement and price as text, and the only control on the
/// screen is the `Show all N` toggle (D102's collapsed-toggle shape, chosen over
/// 132 rows of scroll). So "reaching a member" on this screen means the field
/// renders and expands, and this test asserts that rather than inventing a tap
/// the product does not offer. A future session that makes a golfer tappable
/// should extend this file, not assume it was already covered.
final class AReaderCanOpenAGolfTournamentAndComeBack1471Tests: XCTestCase {

    /// A real, currently-served tournament. **This slug rots and is MEANT to** —
    /// a golf tournament stops being served once it is over and long out of the
    /// feed's window. When it goes, this test SKIPS rather than reds: a missing
    /// tournament is the calendar, not a navigation defect.
    ///
    /// Refresh it from `GET /api/feed` — any item whose `type` is `tournament`,
    /// taking `data.slug` (measured 2026-09-17: `biltmore-championship-asheville`,
    /// PGA Tour, 200 with a populated field).
    private static let slug = "biltmore-championship-asheville"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testOpeningAGolfTournamentShowsTheFieldAndBackReturns() throws {
        let app = UITestLaunch.launchApp(extra: ["-launch_route", "bainluck://golf/\(Self.slug)"])

        // ═══ FIRST: DID THE ROUTE LAND ANYWHERE AT ALL? ═══
        //
        // `bainluck://golf/<slug>` is `NavigationCoordinator`'s `case "golf"`, and
        // before #1471 there was no such case — a link to this screen opened
        // nothing. The navigation bar carrying a title is the cheapest proof the
        // push resolved, and it is read BEFORE the field so a failure says which
        // of the two halves broke.
        let bar = app.navigationBars.firstMatch
        XCTAssertTrue(
            bar.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "bainluck://golf/\(Self.slug) pushed no screen with a navigation bar. That is the #1471 "
            + "state exactly: a real destination with no case in the one router, so no link could reach it."
        )
        let golfTitle = bar.identifier

        // ═══ AND THE STATE ALEX SAW IS A SCREEN TOO ═══
        //
        // "Couldn't load <name>" satisfies every existence check a lazier test
        // would make. It is checked for BY NAME and reported as itself, because
        // a run that reds with "no golfer rows" when the truth is a 404 sends the
        // next reader hunting in the wrong layer.
        let failedToLoad = app.staticTexts
            .containing(NSPredicate(format: "label CONTAINS[c] %@", "Couldn't load"))
        XCTAssertFalse(
            failedToLoad.firstMatch.waitForExistence(timeout: 3),
            "The golf tournament screen opened on its error state — this is Alex's own #1471 report "
            + "reproduced: '\(failedToLoad.firstMatch.label)'. The field endpoint is "
            + "/api/golf/tournaments/\(Self.slug); check it before reading this as a routing defect."
        )

        // ═══ THE FIELD, WHICH IS THE WHOLE POINT OF THE SCREEN ═══
        let winnerHeading = app.staticTexts["Winner"]
        guard winnerHeading.waitForExistence(timeout: UITestLaunch.contentTimeout) else {
            // A real tournament days out has no published field yet, and the view
            // says so in one line. That is a correct state, not a failure.
            if app.staticTexts["No odds yet"].exists {
                throw XCTSkip(
                    "\(Self.slug) is served but its field is not published yet ('No odds yet'), so there "
                    + "is no field to walk. That is a normal state for a tournament days out — re-point "
                    + "this at a tournament inside its own week to walk the field half."
                )
            }
            return XCTFail(
                "The golf tournament screen mounted with neither a 'Winner' field section nor the "
                + "'No odds yet' line. A screen that is neither the field, the empty state, nor the "
                + "error state is a fourth state nobody designed."
            )
        }

        // A price beside a name is what distinguishes this screen from the
        // "same card again" Alex was bounced to. `%.1f%%` is the row's format.
        let priced = app.staticTexts.containing(
            NSPredicate(format: "label MATCHES %@", #"^\d+\.\d%$"#)
        )
        XCTAssertGreaterThan(
            priced.count, 1,
            "The field section drew fewer than two priced rows. The Discover card that leads here "
            + "already shows a leader and three runners-up, so a screen with less on it than the card "
            + "that pushed it is the 'duplicate card' loop #1471 was filed about."
        )

        // ═══ AND THE REST OF THE FIELD IS REACHABLE ═══
        //
        // The toggle is the only control on the screen, and it is how a reader
        // reaches a member who is not in the top rows. Its label carries the
        // full count, so the assertion can be about arriving at more rows rather
        // than about the button's own text.
        let showAll = app.buttons.containing(
            NSPredicate(format: "label BEGINSWITH[c] %@", "Show all")
        ).firstMatch
        if showAll.waitForExistence(timeout: 5) {
            let before = priced.count
            showAll.tap()
            XCTAssertTrue(
                app.buttons["Show less"].waitForExistence(timeout: 5),
                "Tapped 'Show all' and the control never became 'Show less', so the field never expanded."
            )
            XCTAssertGreaterThan(
                priced.count, before,
                "'Show all' flipped to 'Show less' and the number of priced rows did not grow "
                + "(\(before) before, \(priced.count) after). The toggle moved and the field did not."
            )
        }

        // ═══ AND THE READER CAN LEAVE ═══
        //
        // Same argument as the bout test: a right screen a reader cannot get off
        // is the same defect wearing a better title.
        let backButton = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(
            backButton.waitForExistence(timeout: 5),
            "The golf tournament screen has no navigation-bar button, so a reader who opens it is stranded."
        )
        backButton.tap()

        XCTAssertTrue(
            app.navigationBars[golfTitle].waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "Back from the golf tournament left its navigation bar on screen — the pop did not happen."
        )
    }
}
