import XCTest

/// #1472, driven by a finger: **a reader who presses Refresh at the bottom of
/// Discover can see that they pressed it.**
///
/// The unit tests in `FooterRefreshSaysWhatItIsDoing1472Tests` pin the rule that
/// decides what the control says. They cannot say whether a reader ever reaches
/// the control, nor what the page does around it once the refresh lands — and
/// "what the page does around it" is the whole of Alex's report. A still
/// photograph of the end card cannot distinguish a control that responds from
/// one that does not; only pressing it can.
///
/// ## Reaching the bottom is the expensive part, and it is the point
///
/// `NativeFeedEndCard`'s bottom-of-feed call site renders only when pagination
/// is exhausted (`!vm.hasMore`). Measured against production on 2026-09-16 the
/// Discover feed is 151 items deep, which the app pages in at 50 at a time and
/// draws 20 at a time. So this test swipes — a lot — and that long walk to the
/// bottom IS the surface under test: it is the place the reader was when they
/// pressed the button and nothing happened.
///
/// A feed that does not end inside the swipe budget SKIPS with a reason. It does
/// not fail: an unreachable end card is a supply fact, not a navigation defect,
/// and failing here would blame this control for the feed being long.
final class AReaderCanSeeTheFooterRefreshWorking1472Tests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// How many swipes to spend looking for the end of the feed.
    ///
    /// 151 items at ~2 cards a screen is ~75 screens; this is that with room.
    /// Bounded rather than unbounded so a feed that has grown does not hang the
    /// suite — it skips, and says how far it got.
    private static let swipeBudget = 110

    func testPressingRefreshAtTheBottomOfTheFeedVisiblyDoesSomething() throws {
        // `-launch_debug_counts` draws the rig badge whose `PULLS` field is
        // incremented as the FIRST statement of `refreshFeed()`. It is the only
        // witness that separates "the button did not fire" from "the button
        // fired and the page did not show it" — and those two need opposite
        // fixes. A reader never sees the badge.
        let app = UITestLaunch.launchApp(extra: ["-launch_debug_counts", "YES"])
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstEventCard(in: app)

        let scrollView = app.scrollViews.firstMatch
        XCTAssertTrue(scrollView.exists, "Discover has no scroll view to walk.")

        // "You're all caught up" is the end card's headline and nothing else on
        // Discover says it. Matched as a static text rather than by identifier
        // because the card has never needed one.
        let endCard = app.staticTexts["You're all caught up"]

        // THE CONTROL IS FOUND BY ITS SPOKEN LABEL, and every phase has its own.
        // A `Button` with an explicit `.accessibilityLabel` replaces its children
        // in the accessibility tree, so the `Text` inside it is not an element —
        // the first draft looked for `staticTexts["Refreshing…"]` and could not
        // find it after a real tap on a working build. That was not a rig
        // problem: the label was phase-blind, which is #1472 for a reader who
        // cannot see the control, and the fix moved the label into the same rule
        // that decides everything else. Read the button, not its insides.
        let refresh = app.buttons["Refresh feed"]
        let refreshing = app.buttons["Refreshing the feed"]

        // THE WALK STOPS ON HITTABILITY, NOT ON EXISTENCE, and the difference is
        // measured, not stylistic. The first draft stopped at `endCard.exists`
        // and then failed at `refresh.isHittable` after 39.6s: the lazy stack
        // puts the end card into the accessibility tree while it is still below
        // the fold, so `exists` went true a screen or more before anything was
        // on screen. The sibling file's check 5 carries the same lesson about
        // the same surface — exists is not reaches the reader.
        var swipes = 0
        while swipes < Self.swipeBudget, !refresh.isHittable {
            scrollView.swipeUp()
            swipes += 1
        }

        try XCTSkipUnless(
            endCard.exists,
            "NOT WALKED: \(swipes) swipes did not reach the end of the Discover feed, so the "
            + "bottom-of-feed Refresh control was never on screen. The feed is longer than the budget, "
            + "or pagination is still fetching. This is a supply fact, not a defect in the control."
        )
        XCTAssertTrue(
            refresh.isHittable,
            "The end card is on screen after \(swipes) swipes and its Refresh control is not touchable. "
            + "#1773 put the control here precisely because the gesture it replaced is unreachable at this "
            + "end of the page; a control the reader cannot press is the same defect one layer in."
        )

        add(Self.shot(app, "1-idle"))

        // THE RESTING STATE, and the control against the fix being inert: before
        // the press there must be nothing saying a refresh is happening. If this
        // is already on screen, everything below proves nothing.
        XCTAssertFalse(
            refreshing.exists,
            "The control is already in its in-flight state before anything was pressed, so a later reading "
            + "of it would say nothing about the press."
        )

        // THE CONTROL FOR `PULLS`: it must not tick on its own. Cold load, cache
        // seed and the long scroll all ran before this line, so a counter that
        // is still where it was proves the reads below are about the press.
        let pullsBefore = try Self.pulls(of: app)
        Thread.sleep(forTimeInterval: 3)
        XCTAssertEqual(
            try Self.pulls(of: app), pullsBefore,
            "PULLS moved with no press, so it is not counting presses and this test cannot use it."
        )

        refresh.tap()

        // WHAT THE PAGE LOOKS LIKE THE INSTANT AFTER THE PRESS, taken
        // unconditionally so a failure below is diagnosable from the artifact
        // rather than from a re-run.
        add(Self.shot(app, "2a-just-after-tap"))

        // ── 1. The press reaches the refresh ────────────────────────────────
        //
        // `PULLS` separates "the button did not fire" from "the button fired and
        // the page did not show it", and those two need opposite fixes. It moves
        // on the first statement of `refreshFeed()`, so it cannot move for any
        // other reason.
        let badge = app.descendants(matching: .any).matching(identifier: "discover-debug-counts").firstMatch
        let ran = expectation(description: "the refresh closure ran")
        let ranBy = Date().addingTimeInterval(UITestLaunch.contentTimeout)
        while Date() < ranBy {
            if badge.exists, badge.label.contains("PULLS \(pullsBefore + 1)") { ran.fulfill(); break }
            Thread.sleep(forTimeInterval: 0.2)
        }
        wait(for: [ran], timeout: 1)

        // ── 2. The reader is taken somewhere, and it has content ────────────
        //
        // THIS IS THE ASSERTION, and it is deliberately not about the in-flight
        // label. Measured across four runs: the whole refresh completes faster
        // than XCUITest can sample (production /api/feed is ~0.4s from here), so
        // a screenshot taken in the same instruction as the tap already shows
        // the finished, scrolled result. An assertion on a state that brief
        // passes or fails on network weather, and a green from it would say
        // nothing. `.refreshing` is pinned where it can be pinned —
        // `FooterRefreshSaysWhatItIsDoing1472Tests`, and it earns its keep on
        // the slow and failing refreshes where it is the only thing on screen.
        //
        // What a reader can rely on is this: they pressed a control at the END
        // of the feed and they are no longer at the end of the feed. Before the
        // tap the end card was the on-screen content; after it, it must not be,
        // and there must be real cards where they landed. That is the difference
        // between "nothing happened" and a refresh.
        let movedOn = expectation(description: "the page moved off the end card")
        let moveBy = Date().addingTimeInterval(UITestLaunch.contentTimeout)
        while Date() < moveBy {
            if !endCard.isHittable { movedOn.fulfill(); break }
            Thread.sleep(forTimeInterval: 0.25)
        }
        wait(for: [movedOn], timeout: 1)

        add(Self.shot(app, "3-after"))

        XCTAssertTrue(
            app.descendants(matching: .any).matching(identifier: "discover-card-event").firstMatch
                .waitForExistence(timeout: UITestLaunch.contentTimeout),
            "The refresh left the reader on a feed with no event cards in it. Moving them is only an "
            + "improvement if there is something where they land."
        )

        // The in-flight control, if the network was slow enough for it to have a
        // frame. Recorded, never asserted — see above.
        if refreshing.exists, refreshing.isHittable { add(Self.shot(app, "2-refreshing")) }
    }

    /// The badge's `PULLS` field, read by its own token.
    ///
    /// Never by position: the badge is a rig affordance that has gained a field
    /// twice already, and an index would hand back a plausible wrong number
    /// rather than an error the next time it does.
    private static func pulls(
        of app: XCUIApplication,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws -> Int {
        let badge = app.descendants(matching: .any).matching(identifier: "discover-debug-counts").firstMatch
        guard badge.waitForExistence(timeout: 10) else {
            XCTFail("-launch_debug_counts drew no badge, so there is no witness for the press.", file: file, line: line)
            throw XCTSkip("no badge")
        }
        let field = badge.label
            .split(separator: "\u{00B7}")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .first { $0.hasPrefix("PULLS ") }
        guard let field, let value = Int(field.dropFirst("PULLS ".count)) else {
            XCTFail("Could not read PULLS out of the badge: '\(badge.label)'", file: file, line: line)
            throw XCTSkip("unreadable badge")
        }
        return value
    }

    private static func shot(_ app: XCUIApplication, _ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "footer-refresh-\(name)"
        attachment.lifetime = .keepAlways
        return attachment
    }
}
