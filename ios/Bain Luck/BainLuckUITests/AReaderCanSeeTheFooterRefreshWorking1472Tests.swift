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
        _ = try JourneyPrecondition.firstCard(in: app)

        let scrollView = app.scrollViews.firstMatch
        XCTAssertTrue(scrollView.exists, "Discover has no scroll view to walk.")

        // ── THE TOP-OF-FEED WITNESS, captured before the walk ────────────────
        //
        // WHY NOT THE NAVIGATION BAR, which is the obvious instrument and the one
        // this arm was measured with for a whole session (#7074, native/239).
        // Discover's bar is `.large`, so it reads 108pt at the top and 54pt once
        // scrolled, and it reads 54pt after the footer refresh — which was taken
        // as "the reader does not move" and sent three hypotheses to their graves.
        // It is not that. `scrollTo(feedTopAnchor, anchor: .top)` aligns the
        // anchor with the top of the VISIBLE area, which is below a collapsed
        // bar, so the bar cannot re-expand no matter how perfectly the scroll
        // lands. The witness could never have moved: every reading it gave was
        // the same reading, for a reason that has nothing to do with the fix.
        //
        // The swipe hint is the first element of the feed and nothing else on
        // Discover says it, so seeing it IS being at the top — and unlike a bar
        // height it cannot be produced by landing near the top of a short feed,
        // which is precisely the failure this arm hypothesised.
        // READ AS A POSITION, NOT AS HITTABILITY. `isHittable` was the first
        // draft and it is marginal here by construction: at the top of the feed
        // the hint sits directly under a translucent navigation bar, so whether
        // it reports hittable turns on a pixel or two of overlap. Measured
        // 2026-09-18: the same assertion on the same sha passed one run and
        // timed out the next. The hint's frame is continuous — at the top it is
        // tens of points below the top edge, at the end of a 150-card feed it is
        // tens of thousands of points above it — so there is no boundary for a
        // run to land on.
        let swipeHint = app.staticTexts["Shape your feed"]
        let hintWasAtTheTop = swipeHint.waitForExistence(timeout: UITestLaunch.contentTimeout)
            && swipeHint.frame.maxY > scrollView.frame.minY

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

        // THE ANTI-VACUITY HALF OF THE TOP-OF-FEED WITNESS. The reader has walked
        // to the end of the feed, so the hint must be gone from the screen. If it
        // were still hittable here, the read after the press would prove nothing
        // — it would be true of a page that never moved at all.
        let hintAtTheEnd = swipeHint.frame.maxY
        if hintWasAtTheTop {
            XCTAssertLessThanOrEqual(
                hintAtTheEnd, scrollView.frame.minY,
                "The top-of-feed swipe hint is still on screen at the END of the feed after \(swipes) swipes "
                + "(its bottom edge reads \(hintAtTheEnd), the scroll view starts at \(scrollView.frame.minY)), "
                + "so it does not mark the top and the check after the press would be vacuous."
            )
        }

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
            JourneyPrecondition.cards(in: app).firstMatch
                .waitForExistence(timeout: UITestLaunch.contentTimeout),
            "The refresh left the reader on a feed with no event cards in it. Moving them is only an "
            + "improvement if there is something where they land."
        )

        // ── 3. And where they land is the TOP of the feed ───────────────────
        //
        // Alex's report is not "the refresh did nothing", it is "it put me
        // somewhere I had never been": *"about halfway up the page"*. Check 2
        // above is satisfied by ANY position that is not the end card, so the
        // whole of that report lives in the gap between check 2 and this one.
        //
        // Measured on `aa901f83f` before this assertion existed (native/240): the
        // run's own `3-after` attachment shows the swipe hint and the first card,
        // with the badge reading `PULLS 1` — the reader is at the top, and the
        // navigation bar reads 54pt while they are there. So this is a guard over
        // behaviour that is already right, written because the only witness the
        // arm had could not see it and would have reported a regression here as
        // "unchanged, still 54pt".
        if hintWasAtTheTop {
            var hintAfter = swipeHint.frame.maxY
            let topBy = Date().addingTimeInterval(UITestLaunch.contentTimeout)
            while Date() < topBy, hintAfter <= scrollView.frame.minY {
                Thread.sleep(forTimeInterval: 0.25)
                hintAfter = swipeHint.frame.maxY
            }
            // Both numbers in the message, always: a bare "it is not at the top"
            // sends the next session back to the simulator to find out how far
            // off it was, and "one screen high" and "forty screens high" are
            // different defects.
            XCTAssertGreaterThan(
                hintAfter, scrollView.frame.minY,
                "The refresh did not return the reader to the top of the feed. The first element of the feed "
                + "(the swipe hint) has its bottom edge at \(hintAfter), above the top of the scroll view at "
                + "\(scrollView.frame.minY); it read \(hintAtTheEnd) at the end card before the press. "
                + "The navigation bar is NOT a witness for this — it reads 54pt at the top of a refreshed "
                + "feed and at the end card alike (#7074, native/239)."
            )
        } else {
            // A supply fact, not a defect: the hint is shown once per install
            // (`discover_swipe_hinted`), so on a simulator where a card has ever
            // been swiped there is no top-of-feed marker to read. Erase the
            // device to restore it. Said out loud rather than skipped silently —
            // a guard that quietly stops asserting is worse than no guard.
            XCTFail(
                "NO TOP-OF-FEED WITNESS: the swipe hint was not on screen at the start, so this run "
                + "cannot tell the top of the feed from anywhere else in it. The hint is shown once per "
                + "install (UserDefaults `discover_swipe_hinted`); erase the simulator and re-run."
            )
        }

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
