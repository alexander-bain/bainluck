import XCTest

/// #6268 — the typeahead row's MIDDLE was dead, and the shorter the label the more of
/// the row was dead.
///
/// `SearchView.suggestionList` draws each row as
/// `Button { … } label: { HStack { icon; Text(name); Spacer(); Text(kind) } }` with
/// `.buttonStyle(.plain)`. `.plain` hit-tests the rendered CONTENT, and a `Spacer()`
/// renders nothing, so the gap between the name and the trailing kind label took no
/// touches. Measured on iPhone 17 before the fix, one fresh launch per team:
///
/// | row | label ends at | tap at x=201 | |
/// |---|---|---|---|
/// | Boston Red Sox | 158 | nothing | dead |
/// | New York Yankees | ~170 | nothing | dead |
/// | Boston Celtics | ~158 | nothing | dead |
/// | Los Angeles Dodgers | past 201 | opens | worked |
/// | Los Angeles Lakers | past 201 | opens | worked |
/// | Golden State Warriors | past 201 | opens | worked |
///
/// Six for six, deterministic, all with `hittable == true` and `enabled == true` and
/// the identical frame `(0, 226, 402, 54)` — which is why this read as "some team rows
/// are dead" and survived a day of hypotheses about slugs and stale responses. The
/// discriminator was never the team; it was whether the text happened to reach the
/// middle of the row. Confirmed by prediction before the fix: the SAME dead Red Sox
/// row fired at dx=0.15 (over the name) and dx=0.92 (over "Team") and did nothing at
/// dx=0.50.
///
/// **THIS TEST TAPS THE FAILING PATH AND NOTHING ELSE.** Not the submitted-results
/// route (type → return → tap), which uses `NavigationLink` and never had this defect
/// and would pass on the broken build. The typeahead row, at the row's own centre,
/// which is where a thumb goes.
///
/// ═══ THREE NOT-PASSES, AND THEY MEAN DIFFERENT THINGS ═══
///
/// The first draft collapsed all three into one red reading "no typeahead team row was
/// short enough", and the first run after the fix hit it for a reason that had nothing
/// to do with rows: the tab tap logged `Computed hit point {-1, -1}`, the Search screen
/// never mounted, no row of any kind was ever on screen, and the test reported a
/// statement about team-name lengths. So they are separated by construction:
///
///   * the SCREEN not mounting is a rig/app failure — hard red (and the tab tap now
///     goes through `JourneyPrecondition.openTab`, which retries that exact flake);
///   * NO team rows at all is a data outage — skip, naming it;
///   * team rows with no dead centre is today's index — skip, naming it;
///   * the tap not navigating is #6268 — hard red, which is the whole point.
final class ATypeaheadRowIsTappableInItsMiddleTests: XCTestCase {

    /// A row whose text ends before the row's own midpoint. The defect only exists
    /// where the spacer covers the centre, so the test FINDS such a row rather than
    /// hard-coding a team — a club can be renamed, dropped from the index, or grow a
    /// longer name, and a hard-coded "Boston Red Sox" would then pass by walking a row
    /// that never had the defect.
    private struct ShortRow {
        let element: XCUIElement
        let name: String
        let textEndsAt: CGFloat
        let rowMidX: CGFloat
    }

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testTappingAShortTypeaheadRowInItsMiddleOpensIt() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.openTab("Search", in: app)

        let field = app.textFields.firstMatch
        XCTAssertTrue(
            field.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "The Search tab has no text field (SearchView's is placeholdered "
            + "'Search teams, games, futures...'), so nothing below was walked."
        )

        // Several queries, because which teams are in the index is data and this test
        // is about geometry. The first one that yields a row with a spacer over its
        // centre is the specimen.
        var specimen: ShortRow?
        var sawATeamRow = false
        var longestSeen: [String] = []

        for query in ["Red Sox", "Celtics", "Yankees", "Mets", "Jets", "Suns"] {
            type(query, into: field)

            guard app.buttons.matching(teamRow).firstMatch.waitForExistence(timeout: 12) else {
                clear(field)
                continue
            }
            sawATeamRow = true

            // Let the 200 ms debounce settle past any reassignment of the array.
            JourneyPrecondition.settle(app.buttons.matching(teamRow))

            if let found = shortestRowWithADeadCentre(app) {
                specimen = found
                break
            }
            longestSeen.append(contentsOf: app.buttons.matching(teamRow)
                .allElementsBoundByIndex.prefix(3).map(\.label))
            clear(field)
        }

        guard sawATeamRow else {
            throw XCTSkip(
                "NOT WALKED: none of the six queries produced a single '…, Team' "
                + "suggestion row, so there was nothing to tap. That is a statement "
                + "about the typeahead's answers today, not about hit-testing — read "
                + "search recall, not this skip."
            )
        }

        guard let row = specimen else {
            throw XCTSkip(
                "NOT WALKED: team rows were on screen but none had its text end before "
                + "its own midpoint, so the geometry this test exists for is not "
                + "reproducible on today's index. Rows seen: \(longestSeen). A long name "
                + "covers its own centre and would pass on the broken build too."
            )
        }

        XCTAssertLessThan(
            row.textEndsAt, row.rowMidX,
            "precondition: the specimen's text must END before the row's midpoint, "
            + "otherwise tapping the middle taps the text and proves nothing"
        )

        let navBefore = app.navigationBars.allElementsBoundByIndex.map(\.identifier)
        row.element.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap()

        // The row's own name becomes the navigation title of the team page.
        let arrived = app.navigationBars[row.name].waitForExistence(timeout: 15)
        let navAfter = app.navigationBars.allElementsBoundByIndex.map(\.identifier)

        XCTAssertTrue(
            arrived,
            "tapped \"\(row.name)\" at the row's centre (x=\(row.rowMidX), text ends at "
            + "x=\(row.textEndsAt)) and the app did not navigate. nav \(navBefore) -> "
            + "\(navAfter). This is #6268: the spacer in the middle of the row is "
            + "taking no touches."
        )
    }

    /// The "Showing results for <correction>" row, tapped past the end of its text.
    ///
    /// The same defect in a different dress, and the reason it is walked rather than
    /// left to the source guard: its content is a short caption, so on the unfixed
    /// build the tappable area ended where the correction's last letter did and the
    /// right half of the row did nothing. Tapping it replaces the query with the
    /// correction — a state change the test can read out of the field itself, which
    /// is why this one does not need a navigation.
    func testTappingTheDidYouMeanRowPastItsTextAdoptsTheCorrection() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.openTab("Search", in: app)

        let field = app.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: UITestLaunch.contentTimeout), "no search field")

        // A misspelling the server corrects. If it stops being corrected this skips
        // rather than fails: what the spell-checker knows is data.
        type("yankes", into: field)

        let dym = app.staticTexts["Showing results for"]
        guard dym.waitForExistence(timeout: 15) else {
            throw XCTSkip(
                "NOT WALKED: 'yankes' produced no 'Showing results for' row, so the "
                + "did-you-mean row was not on screen. That is a statement about the "
                + "correction the API offered today, not about hit-testing."
            )
        }

        // The row is the button that CONTAINS that caption.
        let row = app.buttons.containing(NSPredicate(format: "label == %@", "Showing results for")).firstMatch
        guard row.waitForExistence(timeout: 5) else {
            throw XCTSkip("NOT WALKED: the caption is on screen but not inside a button — re-aim this test")
        }

        // Tap to the RIGHT of the correction's last letter, which is the part of the
        // row that took no touches before the fix.
        let correction = app.staticTexts.allElementsBoundByIndex.first {
            $0.exists && $0.frame.intersects(row.frame) && $0.label != "Showing results for"
        }
        let textEndsAt = correction?.frame.maxX ?? dym.frame.maxX
        guard textEndsAt < row.frame.maxX - 20 else {
            throw XCTSkip(
                "NOT WALKED: the correction's text reaches the end of the row "
                + "(text ends x=\(textEndsAt), row ends x=\(row.frame.maxX)), so there is "
                + "no dead area to tap and a tap here would prove nothing."
            )
        }
        let dx = ((textEndsAt + row.frame.maxX) / 2 - row.frame.minX) / row.frame.width

        row.coordinate(withNormalizedOffset: CGVector(dx: dx, dy: 0.5)).tap()

        let adopted = NSPredicate(format: "value != %@", "yankes")
        let changed = XCTWaiter().wait(
            for: [XCTNSPredicateExpectation(predicate: adopted, object: field)],
            timeout: 10
        ) == .completed

        XCTAssertTrue(
            changed,
            "tapped the did-you-mean row at x=\(dx) of its width (its text ends at "
            + "\(textEndsAt), the row ends at \(row.frame.maxX)) and the query is still "
            + "\"\(field.value as? String ?? "")\". This is #6268 on the caption row: "
            + "without a full-width hit shape only the words themselves take touches."
        )
    }

    // MARK: -

    private var teamRow: NSPredicate {
        NSPredicate(format: "label ENDSWITH %@", ", Team")
    }

    private func type(_ query: String, into field: XCUIElement) {
        field.tap()
        field.typeText(query)
    }

    /// Empty the field with the keyboard rather than by finding the clear button.
    ///
    /// The clear button is an `Image(systemName: "xmark.circle.fill")` with no
    /// accessibility label of its own, so a query for it is a guess about what
    /// SwiftUI synthesises — and a `if clear.exists` guard around a guess fails
    /// OPEN: the field keeps the last query, the next `typeText` appends to it,
    /// and the test searches for "Red SoxCeltics". Deleting what is there is a
    /// statement about the field's actual value.
    private func clear(_ field: XCUIElement) {
        field.tap()
        let existing = (field.value as? String) ?? ""
        guard !existing.isEmpty else { return }
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: existing.count))
    }

    /// A visible `… , Team` row whose name text ends before the row's midpoint.
    private func shortestRowWithADeadCentre(_ app: XCUIApplication) -> ShortRow? {
        let rows = app.buttons.matching(teamRow)
            .allElementsBoundByIndex.filter { $0.exists && $0.isHittable }

        for element in rows {
            let name = String(element.label.dropLast(", Team".count))
            // The name is drawn as its own StaticText inside the row; find the one
            // whose frame sits inside this row.
            let text = app.staticTexts.allElementsBoundByIndex.first {
                $0.exists && $0.label == name && element.frame.intersects($0.frame)
            }
            guard let text else { continue }
            let endsAt = text.frame.maxX
            let midX = element.frame.midX
            if endsAt < midX {
                return ShortRow(element: element, name: name, textEndsAt: endsAt, rowMidX: midX)
            }
        }
        return nil
    }
}
