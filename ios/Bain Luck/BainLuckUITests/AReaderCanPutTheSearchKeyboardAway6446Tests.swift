import XCTest

/// CHECK 8: **a reader who has typed a search can get the keyboard — and the tab
/// bar — back.**
///
/// #6446, Alex on a physical iPhone, 2026-09-15: *"When I went to leave the
/// Search experience to click on the My Stuff tab, I couldn't get the keyboard
/// to go away to make the My Stuff tab clickable."* The field had a
/// `@FocusState` and nothing that ever cleared it, and the tab bar sits UNDER
/// the keyboard on a phone — so focusing the field took the bottom of the app
/// away and the only exits were the back gesture or force-quitting.
///
/// `SearchView` now ships two dismissals — `.scrollDismissesKeyboard(.immediately)`
/// and a keyboard-toolbar "Done" — and neither had a test. That gap is the
/// reason this file exists rather than the dismissals themselves: the repair for
/// a defect the product owner hit in person, on the tab a reader reaches
/// My Stuff through, was resting on nothing that could see it break.
///
/// ═══ WHY BOTH, AND WHY NEITHER ALONE WOULD DO ═══
///
/// They answer two different gestures and the view's own note says each one
/// alone leaves a reader stuck: scrolling is what Alex was doing when he hit it,
/// and the Done button is the one that is VISIBLE, which is what "obvious"
/// means here. A green on one proves nothing about the other, so they are two
/// tests.
///
/// ═══ WHAT EACH TEST ASSERTS, AND WHY IT IS NOT THE EASY ASSERTION ═══
///
/// The easy assertion is "the keyboard went away". It is not enough twice over:
///
///   1. **`waitForNonExistence` on a keyboard that was never up passes
///      vacuously.** So both tests assert the keyboard EXISTS first, hard, and
///      fail there if it does not. The dismissal claim is only ever made about
///      a keyboard this test watched appear.
///   2. **A dismissal that clears the query is not a fix.** The view's note is
///      explicit — *"dismissing the keyboard must keep the typed text and the
///      drawn results, or the reader has to retype to get back where he was"* —
///      so both tests re-read the field afterwards. A dismissal that resets
///      `viewModel.query` would pass the keyboard assertion and be a worse bug
///      than the one it replaced.
///
/// And then each test does the thing Alex could not: **taps My Stuff and lands
/// there.** `isHittable` is deliberately NOT the assertion — an element can read
/// hittable while the point you would tap is owned by something drawn over it,
/// which is exactly the geometry here. Only arriving proves arrival.
final class AReaderCanPutTheSearchKeyboardAway6446Tests: XCTestCase {

    /// A query that returns rows in every season, so a red here is about the
    /// keyboard and not about the calendar. Same choice, same reason, as
    /// ``AReaderCanSearchAndOpenAResultTests``.
    private let stableQuery = "Red Sox"

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    // MARK: - The two journeys

    func testScrollingTheResultsPutsTheKeyboardAwayAndGivesTheTabBarBack() throws {
        let app = UITestLaunch.launchApp()
        let field = try typeTheQuery(in: app)

        // ═══ WHICH OF SEARCH'S FOUR PANES THIS SCROLLS, AND WHY IT IS THAT ONE ═══
        //
        // `SearchView` draws four different things under the field — results,
        // typeahead suggestions, a "Press return to search"
        // `ContentUnavailableView` between two `Spacer`s, and the empty state —
        // and only two of them scroll. Two earlier drafts of this test scrolled
        // the SUGGESTIONS, and both were wrong in the direction that matters:
        // they reported a PRODUCT defect.
        //
        //   * Typeahead is debounced, so a drag fired the instant the keyboard
        //     appears lands on the non-scrolling `ContentUnavailableView`.
        //     Nothing scrolls, the keyboard correctly stays up, and the test
        //     prints "`.scrollDismissesKeyboard` is broken" about an app that
        //     is fine.
        //   * When typeahead DOES answer it is 7 rows or so — and it answered
        //     on two runs out of three, measured. A pane that is present two
        //     times in three cannot carry a verdict either way.
        //
        // The SUBMITTED results are the stable pane: "Red Sox" returns a long
        // inset-card list every time, it is what a reader actually scrolls to
        // read, and it is the list Alex was looking at. Getting there means
        // pressing return, which itself puts the keyboard down — so the test
        // taps the field again to bring it back. That is not a contrivance: it
        // is the reader who submits, starts reading, taps the field to refine,
        // changes his mind and scrolls on. It is also precisely the state
        // #6446 describes, with a populated screen underneath.
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 10), "No keyboard after tapping the field.")
        app.keyboards.buttons["search"].tap()
        XCTAssertTrue(
            app.keyboards.firstMatch.waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "The keyboard stayed up after return, so the results list never got the screen."
        )

        let settled = JourneyPrecondition.settle(app.cells)
        guard settled > 0, let list = scrollableList(in: app) else {
            throw XCTSkip(
                "NOT WALKED: '\(stableQuery)' returned no scrollable result list (\(settled) cells). "
                + "That is a RECALL finding and belongs to whoever owns search — this test is about the "
                + "keyboard and must not report it as one."
            )
        }

        // Bring the keyboard back onto the populated screen. This is the state
        // under test.
        field.tap()
        let keyboard = try keyboardUp(in: app)

        // ═══ AND A FAILURE MUST SAY WHICH OF THE TWO THINGS WENT WRONG ═══
        //
        // A swipe XCUITest accepts and the list ignores is indistinguishable,
        // from the keyboard alone, from a scroll that happened and dismissed
        // nothing — and the two have opposite verdicts. So the row's position
        // is read either side of the gesture.
        //
        // ORDER MATTERS, and getting it wrong cost this test a cycle. Asserting
        // movement FIRST fails on the honest case: `.immediately` dismisses on
        // the drag, and a suggestion list shorter than the viewport BOUNCES —
        // it moves under the finger and settles back, so the row is at the same
        // point afterwards while the keyboard has correctly gone. Movement is
        // therefore not a precondition for the verdict; it is only the tiebreak
        // when the keyboard STAYED. A dismissal is its own proof the gesture
        // landed, because nothing else on this screen could have caused it.
        // `list.swipeUp()` is the obvious call and it is the wrong one HERE. It
        // drags from the element's own centre, and this list's frame extends
        // UNDER the keyboard — so its centre is a point the keyboard owns, and
        // the gesture goes to the keys. Measured on the suggestions pane: 7
        // rows, first row pinned at 226.0pt across two runs, keyboard up
        // throughout. The element was "hittable" the whole time; hittability is
        // about the element, not about what is drawn over the point you chose.
        //
        // So the drag is aimed at the band that is BOTH inside the list and
        // above the keyboard, computed from the two frames rather than guessed.
        // ═══ AND THE KEYBOARD IS NOT THE TOP OF THE KEYBOARD ═══
        //
        // `app.keyboards.firstMatch.frame.minY` is the top of the KEYS. The
        // dismissal affordance this view ships — the `Dismiss keyboard` toolbar
        // item — is an INPUT ACCESSORY drawn ABOVE that line, and it eats touches
        // like any other view. Measured here, iPhone 17 Pro / iOS 26.5: keys
        // start at 583, the toolbar occupies roughly 539–583, and the drag this
        // test computed started at `583 - 40 = 543` — four points inside the
        // toolbar. Every "the list did not move" reading this file has recorded
        // was the toolbar swallowing the press, not a list that will not scroll.
        //
        // That is this file's own lesson one level up: hittability is about the
        // element, not about what is drawn over the point you chose. So the
        // obstruction is the HIGHER of the keys and the accessory, read from the
        // accessory's own frame rather than guessed at with a bigger margin.
        let dismissButton = app.buttons["Dismiss keyboard"]
        let accessoryTop = dismissButton.exists ? dismissButton.frame.minY : .greatestFiniteMagnitude
        let keyboardTop = min(keyboard.frame.minY, accessoryTop)
        let listFrame = list.frame
        let startY = min(listFrame.maxY - 20, keyboardTop - 40)
        let endY = max(listFrame.minY + 20, startY - 200)
        guard startY - endY >= 80 else {
            throw XCTSkip(
                "NOT WALKED: the visible band of the results list is only \(Int(startY - endY))pt tall "
                + "(list \(listFrame), keyboard top \(keyboardTop)) — too short to express a scroll. "
                + "That is a geometry limit of this simulator, not a verdict on the view."
            )
        }

        // ═══ AND FIRST: IS THERE ANYTHING TO SCROLL? ═══
        //
        // `.scrollDismissesKeyboard` is a response to a SCROLL, so a list whose
        // content already fits its frame cannot exercise it — there is no
        // scroll to dismiss on, the keyboard correctly stays up, and the guard
        // below would report a gesture failure about an app that is behaving.
        // That is a rig limit reported as a product defect, the same class of
        // mistake the two earlier drafts made on the suggestions pane, so it is
        // measured rather than assumed.
        //
        // Measured here, iPhone 17 Pro / iOS 26.5, "Red Sox": 10 rows in a list
        // spanning y 256→874, and the drag never moved row 0 one point — at the
        // left edge (x=4, inside UIKit's screen-edge band) AND down the middle
        // (x=201, nothing drawn over it), with the 4-argument velocity flick
        // both times. Two different X values, one result, which is what a list
        // that simply does not scroll looks like.
        let lastCell = app.cells.element(boundBy: settled - 1)
        guard lastCell.exists, lastCell.frame.maxY > listFrame.maxY else {
            throw XCTSkip(
                "NOT WALKED: '\(stableQuery)' drew \(settled) rows ending at "
                + "\(Int(lastCell.frame.maxY))pt inside a list that runs to \(Int(listFrame.maxY))pt, so the "
                + "content FITS and there is no scroll for `.scrollDismissesKeyboard` to answer. That is a "
                + "property of this query's result count on this device, not a verdict on the view — and the "
                + "Done half, which is the affordance Alex confirmed on his own phone, is covered by the other "
                + "test in this file. Re-point this at a query that overflows the viewport to walk the scroll half."
            )
        }

        // ═══ AND THE TIEBREAK MEASURES A ROW, NOT A SLOT ═══
        //
        // `app.cells.element(boundBy: 0)` is not a row, it is "whichever cell is
        // currently topmost" — and XCUITest orders that query by position. Scroll
        // the list and a DIFFERENT row takes the slot, flush against the list's
        // top edge, so `boundBy: 0`'s `minY` reads 256.33 before and 256.33
        // after a scroll that worked perfectly. Measured exactly that, three runs,
        // two drag positions: the slot is pinned by construction, so the tiebreak
        // was unfalsifiable and reported "the gesture never landed" about every
        // run regardless of what the list did.
        //
        // So the row is followed by IDENTITY. Scrolling off the top counts as
        // movement — that is the strongest possible evidence the list moved.
        //
        // AND THE IDENTITY HAS TO BE ONE. `app.cells.element(boundBy: 0).label`
        // is EMPTY on this list — a search result row is an inset card whose text
        // lives in its children, so the cell itself carries no label. The
        // predicate `label == ""` then matches every cell in the list and
        // `firstMatch` hands back the topmost SLOT again, which is the exact
        // unfalsifiable reading this block was written to replace: measured
        // 2026-09-17, anchor `''`, 256.33pt before and after. A tiebreak that
        // cannot fail is worse than no tiebreak, because it speaks.
        //
        // The row's first static text is the identity that actually exists.
        let anchorLabel = list.staticTexts.element(boundBy: 0).label
        guard !anchorLabel.isEmpty else {
            throw XCTSkip(
                "NOT WALKED: the topmost row in the results list carries no readable text, so this run "
                + "has no anchor to follow and any movement reading would be about a SLOT, not a row. "
                + "That is a rig limit — fix the anchor before letting this test speak about #6446."
            )
        }
        let anchor = list.staticTexts.matching(NSPredicate(format: "label == %@", anchorLabel)).firstMatch
        let before = anchor.frame.minY
        // WITH A VELOCITY. `press(forDuration:thenDragTo:)` — the two-argument
        // form — is a press-and-hold followed by a move, and a `UIScrollView`
        // does not read that as a scroll: measured here at a correct drag
        // (201,543)→(201,343), fully inside a list spanning y 256→874 with the
        // keyboard top at 583, over 10 rows, and the first row did not move one
        // point. Nothing about the placement was wrong; the GESTURE KIND was.
        // The four-argument form flicks, which is what a reader's thumb does
        // and what `.scrollDismissesKeyboard` is listening for.
        // AND DOWN THE MIDDLE. The X matters as much as the Y, and the obvious
        // "just inside the list" choice is the one place on the screen a drag
        // cannot start: `listFrame.minX + 4` is 4pt from the left edge, inside
        // the band UIKit reserves for the interactive-pop screen-edge gesture,
        // which claims the press before the scroll view is offered it. Measured
        // here: a correct 4-argument flick (4,543)→(4,343), fully inside a list
        // spanning y 256→874 with the keyboard top at 583, over 10 rows — and
        // the first row did not move one point, so the rig guard below fired and
        // correctly refused to call it a product verdict. Nothing about the
        // gesture KIND was wrong that time; the X was. The centre is also where
        // a reader's thumb actually is.
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let dragX = listFrame.midX
        origin.withOffset(CGVector(dx: dragX, dy: startY))
            .press(
                forDuration: 0.01,
                thenDragTo: origin.withOffset(CGVector(dx: dragX, dy: endY)),
                withVelocity: .default,
                thenHoldForDuration: 0
            )

        if !keyboard.waitForNonExistence(timeout: UITestLaunch.contentTimeout) {
            // The anchor row leaving the tree IS movement, and the clearest kind.
            let scrolledOff = !anchor.exists
            let after = scrolledOff ? before : anchor.frame.minY
            let moved = scrolledOff || abs(after - before) > 0.5

            XCTAssertTrue(
                moved,
                "RIG, NOT PRODUCT: the keyboard stayed up AND the anchor row '\(anchorLabel)' never moved "
                + "(held \(before)pt over \(settled) rows), so this run never performed the gesture whose "
                + "effect it was about to judge. Fix the gesture target before reading anything into the "
                + "keyboard. GEOMETRY: app=\(app.frame) list=\(listFrame) keyboardTop=\(keyboardTop) "
                + "drag=(\(Int(dragX)), \(Int(startY)))→(\(Int(dragX)), \(Int(endY)))"
            )
            XCTFail(
                "The results list scrolled (anchor row '\(anchorLabel)' "
                + (scrolledOff ? "scrolled off the top" : "moved \(before)pt → \(after)pt")
                + ") and the keyboard stayed up. This is #6446 exactly: "
                + "`.scrollDismissesKeyboard(.immediately)` is not reaching the list a reader actually scrolls."
            )
        }

        assertQuerySurvived(in: app, after: "the scroll")
        try assertTheReaderCanLeaveForMyStuff(in: app, after: "scrolling")
    }

    /// The scrollable container holding the suggestion rows.
    ///
    /// A SwiftUI `List` surfaces as a table on some runtimes and a collection
    /// view on others, and hard-coding either makes this test a report about
    /// the SDK. Asked in order, and `nil` when none of them holds a row — which
    /// the caller turns into a skip, not a failure.
    private func scrollableList(in app: XCUIApplication) -> XCUIElement? {
        for candidate in [app.tables.firstMatch, app.collectionViews.firstMatch, app.scrollViews.firstMatch]
        where candidate.exists && candidate.cells.count > 0 {
            return candidate
        }
        return nil
    }

    func testTheDoneButtonPutsTheKeyboardAwayAndGivesTheTabBarBack() throws {
        let app = UITestLaunch.launchApp()
        let field = try typeTheQuery(in: app)
        let keyboard = try keyboardUp(in: app)

        // Found by the accessibility label the toolbar item declares, not by the
        // word "Done": the visible title is a label a translator moves and the
        // accessibility label is the contract a reader using VoiceOver gets.
        let done = app.buttons["Dismiss keyboard"]
        XCTAssertTrue(
            done.waitForExistence(timeout: 10),
            "No 'Dismiss keyboard' button above the keys. The VISIBLE half of #6446's repair is gone — "
            + "a reader who does not think to scroll has no affordance at all."
        )
        done.tap()

        XCTAssertTrue(
            keyboard.waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "Tapped the keyboard toolbar's Done and the keyboard stayed up."
        )

        assertQuerySurvived(in: app, after: "Done")
        try assertTheReaderCanLeaveForMyStuff(in: app, after: "pressing Done")

        // The field also has to stop being first responder, not merely lose the
        // keys: a field that keeps focus re-presents the keyboard on the next
        // layout pass and the reader is back where he started.
        XCTAssertFalse(
            app.keyboards.firstMatch.exists,
            "The keyboard came back after Done, so the field never gave up focus."
        )
        _ = field
    }

    // MARK: - Shared steps

    /// Open Search, type the query, and hand back the field.
    private func typeTheQuery(in app: XCUIApplication) throws -> XCUIElement {
        _ = JourneyPrecondition.openTab("Search", in: app)

        let field = app.textFields.firstMatch
        XCTAssertTrue(
            field.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "The Search tab has no text field (SearchView's is placeholdered 'Search teams, games, futures...')."
        )
        // ═══ AND TYPING RACES THE FOCUS IT NEEDS ═══
        //
        // `tap()` returns when the tap is DELIVERED, not when the field has
        // become first responder, and `typeText` on an unfocused field does not
        // type — it throws "Neither element nor any descendant has keyboard
        // focus" and the test dies in its setup step wearing a failure that
        // reads like a product defect. Measured 2026-09-17: the field was at
        // (51.7, 186.0) still showing its placeholder when the text was sent.
        //
        // The keyboard appearing IS the focus, so that is what is waited on. The
        // retap is not superstition: on the run this was written for, the first
        // tap landed while the results list was still settling under it.
        if !app.keyboards.firstMatch.waitForExistence(timeout: 5) {
            field.tap()
            XCTAssertTrue(
                app.keyboards.firstMatch.waitForExistence(timeout: 10),
                "Tapped the search field twice and no keyboard ever came up, so the field never took "
                + "focus and nothing below would be typing into it."
            )
        }
        field.typeText(stableQuery)

        XCTAssertEqual(
            field.value as? String, stableQuery,
            "The field does not hold what was typed, so every assertion below would be about the wrong query."
        )
        return field
    }

    /// The keyboard must be UP before a dismissal can be claimed. See note 1 in
    /// the class comment — this is the assertion that stops both tests passing
    /// vacuously.
    private func keyboardUp(in app: XCUIApplication) throws -> XCUIElement {
        let keyboard = app.keyboards.firstMatch
        XCTAssertTrue(
            keyboard.waitForExistence(timeout: 10),
            "No keyboard after tapping the search field and typing. Nothing below is a dismissal test."
        )
        return keyboard
    }

    /// The reader's typed text survives the dismissal. See note 2.
    private func assertQuerySurvived(in app: XCUIApplication, after step: String) {
        XCTAssertEqual(
            app.textFields.firstMatch.value as? String, stableQuery,
            "The query was cleared by \(step). Dismissing the keyboard must keep the typed text — "
            + "a reader who has to retype is no better off than one who was stuck."
        )
    }

    /// Alex's own sentence, as an assertion: leave Search for My Stuff and
    /// actually arrive.
    private func assertTheReaderCanLeaveForMyStuff(in app: XCUIApplication, after step: String) throws {
        let tabBar = JourneyPrecondition.tabBar(of: app)
        let myStuff = tabBar.buttons["My Stuff"]
        XCTAssertTrue(
            myStuff.waitForExistence(timeout: 10),
            "No 'My Stuff' tab after \(step)."
        )
        myStuff.tap()

        // Arrival, not hittability. `isHittable` can be true for an element the
        // keyboard is drawn over, which is the precise geometry of #6446.
        XCTAssertTrue(
            app.navigationBars["My Stuff"].waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Tapped My Stuff after \(step) and never got there. #6446's reader is still trapped in Search."
        )
    }
}
