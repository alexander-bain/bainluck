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

        let card = app.descendants(matching: .any)
            .matching(identifier: "discover-card-event")
            .firstMatch
        XCTAssertTrue(
            card.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "CHECK 5 FAILS: Discover mounted but drew no event card within \(UITestLaunch.contentTimeout)s. "
            + "A screenshot of this state looks like a slow load and is not distinguishable from an empty feed."
        )
    }

    // MARK: - Swipe: the page

    func testAVerticalSwipeMovesTheFeed() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstEventCard(in: app)

        let scrollView = app.scrollViews.firstMatch
        XCTAssertTrue(scrollView.exists, "Discover has no scroll view to swipe.")

        // The assertion is that the CONTENT moved, not that the gesture was
        // accepted. `swipeUp()` on a frozen page raises nothing at all, so a
        // test that only swipes and then asserts the scroll view still exists
        // passes on a feed that cannot scroll — the green-light-no-sensor shape.
        // A card's own frame is the cheapest witness: it is in content
        // coordinates, so it can only change if the content scrolled.
        let cards = app.descendants(matching: .any).matching(identifier: "discover-card-event")
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
        _ = try JourneyPrecondition.firstEventCard(in: app)

        let cards = app.descendants(matching: .any).matching(identifier: "discover-card-event")
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
        let app = XCUIApplication()
        app.launchArguments += UITestLaunch.arguments
        // LaunchRig.debugCountsKey — draws the counter this test reads.
        app.launchArguments += ["-launch_debug_counts", "YES"]
        app.launch()

        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstEventCard(in: app)

        let badge = app.descendants(matching: .any).matching(identifier: "discover-debug-counts").firstMatch
        XCTAssertTrue(
            badge.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "-launch_debug_counts drew no badge, so this test has no witness. A flag with no visible effect is the #3157 shape: silently inert."
        )
        JourneyPrecondition.settle(app.descendants(matching: .any).matching(identifier: "discover-card-event"))

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

        let scrollView = app.scrollViews.firstMatch
        XCTAssertTrue(scrollView.exists, "Discover has no scroll view to pull.")

        // A bare `swipeDown()` is a flick: too short and too fast to hold an
        // overscroll open. The press-drag-hold form is what a reader's pull
        // actually is, and it starts at dy 0.30 — below the 62-168pt navigation
        // bar, which dy 0.15 lands on and which swallowed the first draft's pull.
        let top = scrollView.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.30))
        let bottom = scrollView.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.95))
        top.press(forDuration: 0.2, thenDragTo: bottom, withVelocity: .slow, thenHoldForDuration: 1.0)

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
            app.descendants(matching: .any).matching(identifier: "discover-card-event").firstMatch
                .waitForExistence(timeout: UITestLaunch.contentTimeout),
            "The feed had no event card after the refresh. A refresh emptied the page."
        )
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
