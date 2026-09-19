import XCTest

/// CHECK 5, the half that has never been verified: **a reader can swipe and
/// refresh Discover.**
///
/// The screenshot rig has photographed Discover since #3157 and every
/// walkthrough that used it had to write the same sentence — swipe and
/// pull-to-refresh are UNKNOWN, not PASS. A still photograph of a feed cannot
/// distinguish a scroll view from a picture of one, and `-launch_scroll` moves
/// a `UIScrollView` programmatically, which proves the content is tall and
/// proves nothing about whether a finger moves it.
///
/// Three distinct gestures live here because they fail independently and have
/// failed independently: a vertical drag on the page, a horizontal drag on ONE
/// card (#1773's axis latch — a card that ignored every swipe after its first,
/// silently, with no visual feedback), and the overscroll that arms
/// `.refreshable`.
final class AReaderCanSwipeAndRefreshDiscoverTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    // MARK: - The feed is really there

    /// Check 5's own assertion, and the only one in this target that treats an
    /// empty feed as a FAILURE rather than a skipped precondition.
    ///
    /// "Discover opens with real cards" is the check. Everything else in this
    /// file needs cards in order to run; this needs them in order to pass.
    func testDiscoverOpensOnRealCards() {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)

        XCTAssertTrue(
            app.navigationBars["Discover"].waitForExistence(timeout: UITestLaunch.launchTimeout),
            "Cold launch did not land on Discover. Discover is the default tab (MainTabView)."
        )

        // ANY CARD, NOT AN EVENT CARD, and the difference is the whole of this
        // check's honesty. Until 2026-09-17 this waited on `discover-card-event`
        // — the identifier only `NativeEventDiscoverCard` carries — and called
        // its absence "Discover drew no cards". Measured against the live
        // `GET /api/feed?limit=50` at 10:25Z that morning: 2 events, 39 futures,
        // 8 bundles, 1 tournament. The app had drawn 50 real cards and the
        // photograph of that run shows two of them; the check still read FAIL,
        // and took four sibling journeys down as skips behind it. A feed with no
        // GAME in it is the night's fixture list. A feed with no CARD in it is
        // the defect this check is named for.
        // Deliberately NOT `JourneyPrecondition.firstCard`: that helper SKIPS an
        // empty feed, and an empty feed is the one thing this check must go RED
        // for. Same query, opposite verdict.
        let card = JourneyPrecondition.cards(in: app).firstMatch
        XCTAssertTrue(
            card.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "CHECK 5 FAILS: Discover mounted but drew no card of any kind within \(UITestLaunch.contentTimeout)s. "
            + "A screenshot of this state looks like a slow load and is not distinguishable from an empty feed."
        )

        // EXISTS IS NOT REACHES THE READER, and the gap is not hypothetical.
        // Measured 2026-09-15 with the first-run sheet re-armed
        // (`--rearm-first-run-gates`): Discover mounted, drew its cards, and every
        // one of them sat under a modal the reader had not answered yet. The
        // assertion above was true; the sibling test failed on the same build at
        // `card.tap()` with "Failed to not hittable … identifier:
        // 'discover-card-event'". So check 5 — the check this whole file is named
        // for — reported PASS on a feed nobody could touch.
        //
        // Hittability is the cheapest property that separates "cards are in the
        // accessibility tree" from "a reader can engage with them", and it is the
        // one a first-run gate, a stray overlay or a full-screen spinner all
        // break. The first card is the topmost one, so it is on screen whenever
        // the feed drew at all — this does not flake on content below the fold.
        XCTAssertTrue(
            card.isHittable,
            "CHECK 5 FAILS: Discover drew a card and the reader cannot touch it — "
            + "the card exists at \(card.frame) but reports `isHittable == false`, which is what a modal, "
            + "an overlay or a blocking spinner on top of the feed looks like from here."
        )
    }

    // MARK: - Swipe: the page

    func testAVerticalSwipeMovesTheFeed() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let scrollView = app.scrollViews.firstMatch
        XCTAssertTrue(scrollView.exists, "Discover has no scroll view to swipe.")

        // The assertion is that the CONTENT moved, not that the gesture was
        // accepted. `swipeUp()` on a frozen page raises nothing at all, so a
        // test that only swipes and then asserts the scroll view still exists
        // passes on a feed that cannot scroll — the green-light-no-sensor shape.
        // A card's own frame is the cheapest witness: it is in content
        // coordinates, so it can only change if the content scrolled.
        let cards = JourneyPrecondition.cards(in: app)
        JourneyPrecondition.settle(cards)
        let card = cards.firstMatch
        let before = card.frame.origin.y

        scrollView.swipeUp()

        let moved = expectation(description: "the first card's position changed")
        var after = before
        for _ in 0..<20 {
            after = card.frame.origin.y
            if abs(after - before) > 1 { moved.fulfill(); break }
            usleep(250_000)
        }
        wait(for: [moved], timeout: 1)
        XCTAssertNotEqual(
            before, after,
            accuracy: 1,
            "A swipe up left the first card at y=\(before). The feed did not scroll under the finger."
        )
    }

    // MARK: - Swipe: one card

    /// #1773's gesture, driven by a finger for the first time.
    ///
    /// A left swipe on a card is a downrank and dismisses it. The dismissed card
    /// **cannot** be backfilled in the same sitting — `applyDismissFloor`'s
    /// `neverBackfill` excludes anything inside `backfillGraceWindow` — so "this
    /// card is gone" is a sound assertion here, and would not be on an aged
    /// dismiss.
    ///
    /// IDENTITY, NOT COUNT, and the difference is not stylistic. The first draft
    /// asserted the number of matching cards went down, and it failed
    /// intermittently on a working app: the masonry is lazy, so only one to
    /// three event cards are RENDERED at a time, and a dismissal that pulls the
    /// next card into view leaves the count exactly where it was. Measured — the
    /// same swipe read DISMISSED and IGNORED on consecutive attempts with every
    /// dwell from 3s to 10s, which looks precisely like the #1773 defect this
    /// test exists to catch. A count is not an identity.
    ///
    /// No row is written to `/api/feed/interactions`: the target launches with
    /// `-launch_no_interaction_upload`.
    func testAHorizontalSwipeDismissesTheCardUnderTheFinger() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let cards = JourneyPrecondition.cards(in: app)
        JourneyPrecondition.settle(cards)

        let target = cards.firstMatch
        let signature = Self.signature(of: target)
        try XCTSkipIf(
            signature.isEmpty,
            "NOT WALKED: the first event card exposed no text to identify it by, so a dismissal could not be told from a re-render."
        )

        target.swipeLeft()

        var stillThere = true
        let deadline = Date().addingTimeInterval(10)
        while Date() < deadline {
            stillThere = cards.allElementsBoundByIndex.contains { Self.signature(of: $0) == signature }
            if !stillThere { break }
            Thread.sleep(forTimeInterval: 0.5)
        }

        XCTAssertFalse(
            stillThere,
            "A left swipe left the same card on the page 10s later. The card did not accept the gesture — which is exactly the #1773 shape: "
            + "no visual feedback, nothing raised, the swipe simply ignored. (Card: \(signature.prefix(80)))"
        )

        XCTAssertTrue(
            cards.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Dismissing one card left the feed with no event card at all. The floor (`applyDismissFloor`) is meant to backfill to \(28)."
        )
    }

    /// What a rendered card can be recognised by, without pinning its copy.
    ///
    /// The labels of its own text, joined. Not the identifier (every card shares
    /// it, by design) and not the frame (which moves when the page relays out).
    /// This is used ONLY to tell one card from another within a single test, so
    /// a copy change cannot red it: both reads happen seconds apart on the same
    /// build.
    private static func signature(of card: XCUIElement) -> String {
        card.staticTexts.allElementsBoundByIndex.prefix(6).map { $0.label }.joined(separator: "|")
    }

    // MARK: - Refresh

    /// Pull-to-refresh, witnessed by the refresh closure having RUN.
    ///
    /// Three witnesses were tried before this one and all three are blind.
    /// Measured on 2026-09-14, written down because the next person to write
    /// this test will reach for the first two:
    ///
    ///   1. **The spinner.** `.refreshable`'s control is not in the
    ///      accessibility tree at all — zero activity and zero progress
    ///      indicators over a four-second sample taken WHILE the finger was
    ///      down, and not only on Discover: also on Sports and Browse, which
    ///      are `List`s, where `.refreshable` is the canonical case. The first
    ///      draft of this test asserted on a spinner and would have filed a
    ///      pull-to-refresh defect against a page that works.
    ///   2. **The content offset holding down while refreshing.** Springs
    ///      straight back on all three surfaces, `List`s included.
    ///   3. **`vm.itemsVersion` moving.** Looked right and FAILED ITS POSITIVE
    ///      CONTROL: the feed arrives complete (48 served), so scrolling to the
    ///      end reloads nothing and the version never moves for a reason that
    ///      has nothing to do with refreshing. A witness whose positive control
    ///      fails cannot be read as evidence in either direction.
    ///
    /// So: `PULLS n` in the rig-only badge, incremented as the first statement
    /// of `refreshFeed()`. It can only move if the closure ran. A reader never
    /// sees the badge — it is drawn only under `-launch_debug_counts`.
    ///
    /// The assertion is NOT that the cards changed. A refresh returning the same
    /// cards is a correct refresh, and asserting otherwise would red this test
    /// whenever the API is doing its job.
    func testPullingDownRunsTheRefresh() throws {
        // LaunchRig.debugCountsKey — draws the counter this test reads.
        let app = UITestLaunch.launchApp(extra: ["-launch_debug_counts", "YES"])

        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let badge = app.descendants(matching: .any).matching(identifier: "discover-debug-counts").firstMatch
        XCTAssertTrue(
            badge.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "-launch_debug_counts drew no badge, so this test has no witness. A flag with no visible effect is the #3157 shape: silently inert."
        )
        JourneyPrecondition.settle(JourneyPrecondition.cards(in: app))

        // THE CONTROL, and it is not ceremony: a counter that ticks on its own
        // would make this test pass forever while proving nothing. Cold load,
        // cache seed and tab restore all run through code near this one, so the
        // quiet window establishes that NONE of them bumps PULLS.
        let before = try badgeField("PULLS", of: badge)
        Thread.sleep(forTimeInterval: 6)
        let afterQuietWindow = try badgeField("PULLS", of: badge)
        XCTAssertEqual(
            afterQuietWindow, before,
            "PULLS moved from \(before) to \(afterQuietWindow) with NO pull. The counter is not counting pulls, so this test cannot say anything about the gesture."
        )

        try pullToRefresh(in: app)

        var after = before
        let deadline = Date().addingTimeInterval(UITestLaunch.contentTimeout)
        while Date() < deadline {
            after = (try? badgeField("PULLS", of: badge)) ?? after
            if after > before { break }
            Thread.sleep(forTimeInterval: 0.5)
        }
        XCTAssertGreaterThan(
            after, before,
            "A pull past the top of Discover did not run the refresh: PULLS stayed at \(before) for \(UITestLaunch.contentTimeout)s, "
            + "on a counter that a quiet window of the same length proved does not tick on its own."
        )

        XCTAssertTrue(
            JourneyPrecondition.cards(in: app).firstMatch
                .waitForExistence(timeout: UITestLaunch.contentTimeout),
            "The feed had no event card after the refresh. A refresh emptied the page."
        )
    }

    /// A reader's pull, as a gesture and not as a flick.
    ///
    /// Hoisted at its SECOND caller rather than copied (native/243): a bare
    /// `swipeDown()` is too short and too fast to hold an overscroll open, and the
    /// dy 0.30 start is load-bearing — dy 0.15 lands on the 62-168pt navigation bar
    /// and swallowed the first draft's pull entirely. Two copies of a recipe with
    /// two magic numbers in it is one copy that gets tuned and one that silently
    /// stops arming the thing it is named for.
    private func pullToRefresh(
        in app: XCUIApplication,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let scrollView = app.scrollViews.firstMatch
        guard scrollView.exists else {
            XCTFail("Discover has no scroll view to pull.", file: file, line: line)
            throw XCTSkip("no scroll view")
        }
        let top = scrollView.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.30))
        let bottom = scrollView.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.95))
        top.press(forDuration: 0.2, thenDragTo: bottom, withVelocity: .slow, thenHoldForDuration: 1.0)
    }

    /// #7074: **a completed pull says so where the reader who pulled is standing.**
    ///
    /// The sibling above proves the gesture reaches the closure. It deliberately
    /// does NOT assert the cards changed — a refresh returning the same markets is
    /// a correct refresh — and that is exactly why Alex's report was ruled
    /// inconclusive: on build 15 a pull that succeeded, a pull that succeeded with
    /// identical cards, and a pull that FAILED all rendered byte-identically to not
    /// having pulled. The three readers of the refresh phase were all in the footer,
    /// a screen-and-a-half below, and both of Discover's error surfaces are gated on
    /// an empty feed.
    ///
    /// This is the assertion no unit test in the world can make: the row is built
    /// inside a SwiftUI builder returning an opaque type, so
    /// `APullOnDiscoverCompletesAndSaysSo7074Tests` can prove every word of the rule
    /// and prove nothing about whether a finger ever produces it. Here a finger does.
    ///
    /// ⏱ THE SUCCESS NOTICE HAS A BOUNDED LIFE — `refreshConfirmationWindow`, 4
    /// seconds — and that is the point of it (a confirmation that never expires
    /// becomes a lie by sitting still). The window opens when the load COMPLETES, not
    /// when the finger lifts, so a slow network delays the notice rather than
    /// shortening it. If this ever goes flaky, the thing to check is whether that
    /// constant moved, not whether the wait is long enough.
    func testACompletedPullSaysSoAtTheTopOfTheFeed() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let notice = app.descendants(matching: .any)
            .matching(identifier: "discover-refresh-notice").firstMatch

        // THE CONTROL. A row that is always on screen would make this test pass
        // forever while proving nothing about the gesture — and it would also be a
        // defect of its own, a permanent fixture at the top of the feed announcing
        // an event that has not happened.
        JourneyPrecondition.settle(JourneyPrecondition.cards(in: app))
        XCTAssertFalse(
            notice.exists,
            "Discover is announcing a refresh outcome before anyone refreshed anything."
        )

        try pullToRefresh(in: app)

        // 🪤 `waitForExistence` MEASURED FALSE ON AN ELEMENT A PLAIN `.exists` LOOP
        // SAW 59 MILLISECONDS LATER — SAME BUILD, SAME GESTURE, SAME QUERY.
        //
        // Measured twice, 2026-09-19 (native/243). Run 1 called
        // `notice.waitForExistence(timeout: 30)` at exactly this point and got
        // `false` after the full thirty seconds. Run 2 replaced it with the loop
        // below and recorded `firstSeen = 0.059s`, `trueSamples = 6 of 129` across
        // 25s: the notice was ALREADY on screen when the gesture returned, stayed for
        // its ~4-second confirmation window, and went. The refresh completes while
        // the finger is still holding the overscroll open, so nearly the whole life
        // of the notice is spent before any assertion can run.
        //
        // Whatever the mechanism inside `waitForExistence` — it is predicate-driven
        // and notification-backed rather than a plain poll — the lesson is the flat
        // one: **on a state with a deliberately bounded life, a waiter reporting
        // absence is not evidence of absence.** The sibling test above reached the
        // same place from the other side and polls `PULLS` by hand for it.
        //
        // So everything the assertions need is captured INSIDE the window, in one
        // pass, cheapest query first. By the time the last assertion runs the row may
        // legitimately be gone, and re-querying a decayed notice would red this test
        // on the confirmation working exactly as designed.
        var appeared = false
        var seenLabel = ""
        var seenFrame = CGRect.zero
        var seenCardFrame = CGRect.zero
        var capturedFrame: XCUIScreenshot? = nil
        let cards = JourneyPrecondition.cards(in: app)
        let deadline = Date().addingTimeInterval(UITestLaunch.contentTimeout)
        while Date() < deadline {
            guard notice.exists else { continue }
            appeared = true
            seenLabel = notice.label
            seenFrame = notice.frame
            seenCardFrame = cards.firstMatch.frame
            capturedFrame = app.screenshot()
            break
        }

        // 📷 SHOT WHATEVER HAPPENED, AND THAT ORDERING IS DELIBERATE. A frame taken
        // only on the happy path exists only in the world where the ship already
        // landed — so the BEFORE half of a BEFORE/AFTER pair is unbuildable and the
        // first thing anyone asks for cannot be produced (D48).
        let shot = XCTAttachment(screenshot: capturedFrame ?? app.screenshot())
        shot.name = "7074-pull-notice"
        shot.lifetime = .keepAlways
        add(shot)

        XCTAssertTrue(
            appeared,
            "A pull completed and the top of the feed said nothing about it. This is Alex's build-15 "
            + "report verbatim: 'Pull gesture briefly shows activity with no apparent change.' The "
            + "outcome is known to the page — the end card reads it — and the reader who pulled cannot "
            + "see the end card."
        )

        XCTAssertEqual(
            seenLabel, "Feed refreshed. Checked just now.",
            "The notice drew, and announces something other than the outcome it was given. Its label is "
            + "what a VoiceOver reader gets INSTEAD of the row's contents, not in addition to them."
        )
        // EXISTS IS NOT ON SCREEN. A row with a zero height, or one drawn above the
        // window's top edge, is in the accessibility tree and invisible — the same
        // gap `testDiscoverOpensOnRealCards` closes with `isHittable`. Hittability is
        // not the test here (the success notice carries no control, so a decorative
        // combined element's hittability is not a property worth reddening a gate
        // over); a real rectangle inside the window is.
        let window = app.windows.firstMatch.frame
        XCTAssertFalse(
            seenFrame.isEmpty,
            "The notice is in the accessibility tree with an empty frame — present to a query, invisible "
            + "to a reader."
        )
        XCTAssertTrue(
            window.contains(seenFrame.origin),
            "The notice drew outside the window (notice at \(seenFrame), window \(window))."
        )

        // It is ABOVE the cards, not merely present. A confirmation the reader has
        // to scroll to is a confirmation for a reader who no longer needs one.
        XCTAssertLessThan(
            seenFrame.minY, seenCardFrame.minY,
            "The refresh notice drew BELOW the first card (notice at \(seenFrame), card at "
            + "\(seenCardFrame)), so the reader must scroll past the feed to learn they do not need to."
        )
    }

    /// #7170: **a pull republishes the feed, and reports the outcome of its OWN
    /// request.**
    ///
    /// The sibling above proves the gesture reaches the closure; the one before it
    /// proves the top of the feed says something. Both passed on a build that lied.
    /// `testACompletedPullSaysSoAtTheTopOfTheFeed` asserted the notice reads "Feed
    /// refreshed. Checked just now." — and it did, on a refresh that never
    /// reassigned `items`. A test of what a row SAYS cannot see that the sentence
    /// is false.
    ///
    /// So this one reads the two rig fields the notice cannot fake:
    ///   * `FEED` — `vm.itemsVersion`, one bump per `items` reassign. It moves iff
    ///     a generation published.
    ///   * `OUTCOME` — which of `load()`'s terminals the refresh actually reached.
    ///
    /// 🪤 `FEED` ALONE WAS REJECTED AS A WITNESS ONCE ALREADY, and the rejection
    /// still stands in the form it was made: `testPullingDownRunsTheRefresh`'s
    /// docs record that `itemsVersion` FAILED its positive control as a witness
    /// *for the gesture* — the feed arrives complete, so scrolling to the end
    /// reloads nothing and the version sits still for reasons having nothing to do
    /// with refreshing. That is why the gesture is witnessed by `PULLS` here too,
    /// and `FEED` is only ever read AFTER `PULLS` has moved. A `FEED` that sits
    /// still while `PULLS` sits still says nothing; a `FEED` that sits still after
    /// `PULLS` moved is the defect.
    ///
    /// ⏱ THE EIGHT-SECOND SETTLE IS LOAD-BEARING, not padding. A pull issued
    /// immediately after the first load reproduces a DIFFERENT non-publish: the
    /// backend answers the immediate second request out of its singleflight with a
    /// typed UNAVAILABLE, which `mayReplaceRendered` correctly declines. That is a
    /// working refusal, it sets an error, and it now reports `failed` — a correct
    /// outcome, and not the one this test is about.
    func testAPullRepublishesTheFeedAndSaysWhatItDid() throws {
        // LaunchRig.debugCountsKey — draws the counter this test reads.
        let app = UITestLaunch.launchApp(extra: ["-launch_debug_counts", "YES"])

        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let badge = app.descendants(matching: .any).matching(identifier: "discover-debug-counts").firstMatch
        XCTAssertTrue(
            badge.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "-launch_debug_counts drew no badge, so this test has no witness. A flag with no visible effect is the #3157 shape: silently inert."
        )
        JourneyPrecondition.settle(JourneyPrecondition.cards(in: app))
        Thread.sleep(forTimeInterval: 8)

        // THE CONTROL, before anything is pulled: the field must exist and must
        // read `none`. A badge that already named an outcome would mean something
        // other than a refresh writes it, and every assertion below would be
        // reading a number this gesture did not produce.
        let outcomeBefore = try badgeWord("OUTCOME", of: badge)
        XCTAssertEqual(
            outcomeBefore, "none",
            "The badge reported OUTCOME '\(outcomeBefore)' before any refresh ran. Only a completed "
            + "refresh may write that field, so this test cannot attribute what it reads later to the pull."
        )

        let pullsBefore = try badgeField("PULLS", of: badge)
        let feedBefore = try badgeField("FEED", of: badge)

        try pullToRefresh(in: app)

        // Wait on the GESTURE first. Everything after this point is a statement
        // about a refresh that provably ran.
        var pullsAfter = pullsBefore
        let deadline = Date().addingTimeInterval(UITestLaunch.contentTimeout)
        while Date() < deadline {
            pullsAfter = (try? badgeField("PULLS", of: badge)) ?? pullsAfter
            if pullsAfter > pullsBefore { break }
            Thread.sleep(forTimeInterval: 0.5)
        }
        XCTAssertGreaterThan(
            pullsAfter, pullsBefore,
            "The pull never reached the refresh closure (PULLS stayed at \(pullsBefore)), so this run "
            + "says nothing about publication. This is the gesture failing, not the feed."
        )

        // Now let the load finish. The outcome field is written when `load()`
        // RETURNS, so poll it off `none` rather than reading once.
        var outcomeAfter = "none"
        var feedAfter = feedBefore
        let settleBy = Date().addingTimeInterval(UITestLaunch.contentTimeout)
        while Date() < settleBy {
            outcomeAfter = (try? badgeWord("OUTCOME", of: badge)) ?? outcomeAfter
            feedAfter = (try? badgeField("FEED", of: badge)) ?? feedAfter
            if outcomeAfter != "none" { break }
            Thread.sleep(forTimeInterval: 0.5)
        }

        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "7170-pull-outcome-\(outcomeAfter)"
        shot.lifetime = .keepAlways
        add(shot)

        XCTAssertEqual(
            outcomeAfter, "published",
            "A pull that reached the closure ended at the '\(outcomeAfter)' terminal of load(). "
            + "The reader was told their refresh completed; it did not publish. "
            + "(FEED \(feedBefore) → \(feedAfter), PULLS \(pullsBefore) → \(pullsAfter).)"
        )

        // The independent half: `OUTCOME` is the app's account of itself, `FEED` is
        // the consequence. A `published` that did not move `FEED` would mean the
        // contract is reporting a publication that did not happen — the same class
        // of defect one layer down — so the two are asserted separately on purpose.
        XCTAssertGreaterThan(
            feedAfter, feedBefore,
            "`items` was never reassigned (FEED \(feedBefore) → \(feedAfter)) though the gesture "
            + "landed and load() reported '\(outcomeAfter)', so the refresh did not republish the feed."
        )
    }

    /// #7074's LAST ARM: **a controlled changed response arrives, renders, and
    /// leaves the reader where they were standing.**
    ///
    /// This is the journey #7074 asked for and native/243 could not build: *"Prove
    /// gesture→request→completion and useful stable position on a controlled
    /// changed-response test"* and, one line later, *"Test actual gestures and read
    /// frames, not state-machine tests alone."* Against the live API those pull in
    /// opposite directions — a finger cannot control what production serves, and
    /// the server may legitimately serve the same cards twice, so asserting "the
    /// cards changed" would red on a working app.
    ///
    /// `-launch_changed_refresh` resolves it by making the DIFFERENCE the
    /// controlled variable: the real gesture, the real network, the real screen,
    /// and a response that differs from the published one by construction. See
    /// `LaunchRig.changedRefreshKey`; the affordance is `#if DEBUG` at its only
    /// call site and cannot exist in a Release build.
    ///
    /// 🪤 IT COULD NOT RUN AT ALL UNTIL #7170. The pull's load was being cancelled
    /// by `.refreshable`'s task teardown, so no refresh ever published and there was
    /// nothing for the rig to stage — measured as `OUTCOME cancelled · FEED 1 → 1`.
    /// A version of this test written then would have failed and read as "the rig
    /// does not work".
    ///
    /// 🪤 AND IT WAS WRITTEN ONCE AND WITHDRAWN (`928a40736`). The rig withheld from
    /// the first load of a WARM container — the last-good cache seed is a paint —
    /// so both sides of the experiment were staged and it measured no difference at
    /// all. It was green in isolation and red in its class, on one build, because
    /// `native-uitest.sh` uninstalls once per INVOCATION. The witness is now a
    /// completed network publication (`DiscoverViewModel.hasPublishedNetworkFeed`),
    /// which no cache can satisfy, and the container tests in
    /// `AControlledChangedRefresh7074Tests` hold that from the other side.
    ///
    /// 🪤 THE TOP CARD'S IDENTITY IS NOT THE WITNESS, though it reads like the
    /// obvious one. `interleave`, grouping and the view's own filters sit between
    /// the response and the screen, so a card at response index 20 survives a
    /// 12-card withholding and can still be drawn first — measured, byte-identical
    /// on both sides, with the feed working correctly. Codex ruled the same:
    /// *"a single top-card identity need not change after grouping."* The count of
    /// cards actually served to the screen is the witness that survives grouping.
    func testAControlledChangedRefreshRendersAndKeepsTheReadersPlace() throws {
        let app = UITestLaunch.launchApp(extra: [
            "-launch_debug_counts", "YES",
            // LaunchRig.changedRefreshKey — the controlled difference. 30 rather
            // than a handful so the shrink it causes cannot be confused with the
            // few-card jitter between two live pages (see the margin below).
            "-launch_changed_refresh", "30",
        ])

        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let badge = app.descendants(matching: .any).matching(identifier: "discover-debug-counts").firstMatch
        XCTAssertTrue(
            badge.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "-launch_debug_counts drew no badge, so this test has no witness."
        )
        JourneyPrecondition.settle(JourneyPrecondition.cards(in: app))
        // The sibling that pulls reliably spends this window first, and it is
        // load-bearing rather than politeness: pulling the instant the first load
        // settles is answered from the backend's singleflight with a typed
        // UNAVAILABLE, which `mayReplaceRendered` correctly declines — so the
        // refresh does not publish and the experiment never runs.
        Thread.sleep(forTimeInterval: 8)

        let outcomeBefore = try badgeWord("OUTCOME", of: badge)
        XCTAssertEqual(
            outcomeBefore, "none",
            "The badge named an outcome before any refresh ran, so nothing read after the pull can "
            + "be attributed to it."
        )

        let servedBefore = try badgeField("SERVED", of: badge)
        let feedBefore = try badgeField("FEED", of: badge)
        let pullsBefore = try badgeField("PULLS", of: badge)

        // THE ANTI-VACUITY GUARD ON THE WITNESS ITSELF. The assertion below reads a
        // 15-card shrink; a page that never held 15 spare cards cannot show one, and
        // the honest answer is that this run did not perform the experiment — not a
        // failure, and emphatically not a pass.
        try XCTSkipIf(
            servedBefore < 25,
            "NOT WALKED: production served only \(servedBefore) cards, so a 30-card withholding "
            + "cannot produce a shrink distinguishable from page jitter. The experiment was not run."
        )
        // And the payload the change is measured AGAINST must be the UNSTAGED one.
        // If the first publication were itself withheld, `servedBefore` would already
        // be ~20 and this guard is what notices — it is the withdrawn journey's exact
        // failure, kept as a tripwire rather than a memory.
        XCTAssertGreaterThan(
            servedBefore, 30,
            "The FIRST network publication was already shortened (SERVED \(servedBefore)), so the "
            + "before and the after are both staged and there is no difference to observe. This is "
            + "the warm-container confound that withdrew this journey once."
        )

        // 🔴 THE ARMING PRECONDITION, and it must be read BEFORE the pull. `RIG` is
        // the drop that will be applied to the NEXT publication, written only at a
        // publication terminal, so a non-zero value proves the launch argument
        // arrived AND that payload A exists.
        //
        // Zero has two innocent causes and neither is a defect: the argument did not
        // reach the app, or the first network load failed and the page on screen is
        // the container's cache seed — in which case the reader's pull would BE the
        // first publication and correctly go unstaged. Measured, both: the run that
        // reported `SERVED 50 → 50` before this field existed was the second one.
        // Without this check that run reads as "the refresh published and the reader
        // saw nothing", which is the product verdict, from an experiment never run.
        let rigArmed = try badgeField("RIG", of: badge)
        try XCTSkipIf(
            rigArmed != 30,
            "NOT WALKED: the rig is not armed (RIG \(rigArmed), SERVED \(servedBefore)). Either the "
            + "launch argument did not reach the load, or no network publication has happened yet — "
            + "so there is no payload A and a pull now would be the first publication, correctly "
            + "unstaged. This run performed no experiment; it is not evidence about the app."
        )

        try pullToRefresh(in: app)

        var pullsAfter = pullsBefore
        var outcome = "none"
        var feedAfter = feedBefore
        var servedAfter = servedBefore
        let deadline = Date().addingTimeInterval(UITestLaunch.contentTimeout)
        while Date() < deadline {
            pullsAfter = (try? badgeField("PULLS", of: badge)) ?? pullsAfter
            outcome = (try? badgeWord("OUTCOME", of: badge)) ?? outcome
            feedAfter = (try? badgeField("FEED", of: badge)) ?? feedAfter
            servedAfter = (try? badgeField("SERVED", of: badge)) ?? servedAfter
            if pullsAfter > pullsBefore && outcome != "none" { break }
            Thread.sleep(forTimeInterval: 0.5)
        }

        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = "7074-changed-refresh-\(outcome)"
        shot.lifetime = .keepAlways
        add(shot)

        // The run's own numbers, banked rather than reconstructed: a passing
        // journey that records nothing leaves its next reader re-running it to find
        // out what it measured.
        let measured = "RIG \(rigArmed) · SERVED \(servedBefore) -> \(servedAfter)"
            + " · FEED \(feedBefore) -> \(feedAfter) · PULLS \(pullsBefore) -> \(pullsAfter)"
            + " · OUTCOME \(outcome)"
        print("7074 CHANGED-RESPONSE MEASUREMENT: \(measured)")
        let note = XCTAttachment(string: measured)
        note.name = "7074-changed-refresh-measurement"
        note.lifetime = .keepAlways
        add(note)

        // 1 — THE REQUEST. Without this the rest describes a page nobody touched.
        XCTAssertGreaterThan(
            pullsAfter, pullsBefore,
            "The pull never reached the refresh closure, so no experiment was performed."
        )

        // 2 — ADMISSION AND PUBLICATION, from the app's own account and from its
        // consequence, asserted separately so one cannot cover for the other.
        XCTAssertEqual(
            outcome, "published",
            "The controlled refresh ended at the '\(outcome)' terminal, so the staged response was "
            + "never admitted (FEED \(feedBefore) → \(feedAfter))."
        )
        XCTAssertGreaterThan(
            feedAfter, feedBefore,
            "`items` was never reassigned, so nothing the rig staged reached the screen."
        )

        // 2b — the arming must still hold on the load that just published, or the
        // shrink below is being read off a publication the rig had no part in.
        let rigArmedAfter = try badgeField("RIG", of: badge)
        XCTAssertEqual(
            rigArmedAfter, 30,
            "The rig was armed before the pull and reads \(rigArmedAfter) after it, so the response "
            + "just published was not the staged one and the comparison below is meaningless."
        )

        // 3 — THE RENDERED CHANGE, which is the clause a live-API journey cannot
        // assert without the rig. 30 cards were withheld from the response, so the
        // list the reader is now looking at must be materially shorter than the one
        // they were looking at. The margin is 15 — half the withholding — because
        // two live pages need not be the same size and the difference must not be
        // readable as jitter in either direction.
        XCTAssertLessThan(
            servedAfter, servedBefore - 15,
            "The refresh published a response with 30 cards withheld from its front and the feed on "
            + "screen did not shrink (SERVED \(servedBefore) → \(servedAfter)). A change that "
            + "published without reaching the reader is exactly what Alex reported as 'no apparent "
            + "change'."
        )
        XCTAssertGreaterThan(
            servedAfter, 0,
            "The staged refresh emptied the feed, which is the empty-state terminal rather than a "
            + "changed response — the rig manufactured a different defect."
        )

        // 4 — THE USEFUL STABLE POSITION. A reader who pulled from the top belongs
        // at the top: the first card of the NEW feed must be on screen, not
        // somewhere they have to hunt for. #7074's end-card arm is the other half
        // of this and is still open — that reader starts at the bottom.
        let cards = JourneyPrecondition.cards(in: app)
        let window = app.windows.firstMatch.frame
        let topCardFrame = cards.firstMatch.frame
        XCTAssertTrue(
            cards.firstMatch.exists && !topCardFrame.isEmpty,
            "There is no first card after the refresh: the pull emptied the page."
        )
        XCTAssertLessThan(
            topCardFrame.minY, window.midY,
            "After a pull from the top the reader is looking at \(topCardFrame) in a \(window) window — "
            + "the first card of the refreshed feed is below the halfway line, so they landed in the "
            + "middle of a feed they have never seen."
        )
    }

    /// One `NAME word` field out of the rig badge, for the fields that are not
    /// numbers. Same token-keyed parse as ``badgeField``; see its note on why
    /// position is never used.
    private func badgeWord(
        _ name: String,
        of badge: XCUIElement,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws -> String {
        let text = badge.label
        let parts = text.split(separator: "\u{00B7}").map { $0.trimmingCharacters(in: .whitespaces) }
        guard let field = parts.first(where: { $0.hasPrefix(name + " ") }) else {
            XCTFail("Could not read \(name) out of the debug badge: '\(text)'", file: file, line: line)
            throw XCTSkip("unreadable badge")
        }
        return String(field.dropFirst(name.count + 1))
    }

    /// One `NAME n` field out of the rig badge's
    /// `SERVED a - DRAWN b - FEED c - PULLS d`.
    ///
    /// Parsed by its own token, never by position: the badge is a rig affordance
    /// that has gained a field twice already, and a hard-coded index would hand
    /// back a plausible wrong number rather than an error the next time it does.
    private func badgeField(
        _ name: String,
        of badge: XCUIElement,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws -> Int {
        let text = badge.label
        let parts = text.split(separator: "\u{00B7}").map { $0.trimmingCharacters(in: .whitespaces) }
        guard
            let field = parts.first(where: { $0.hasPrefix(name + " ") }),
            let value = Int(field.dropFirst(name.count + 1))
        else {
            XCTFail("Could not read \(name) out of the debug badge: '\(text)'", file: file, line: line)
            throw XCTSkip("unreadable badge")
        }
        return value
    }
}
