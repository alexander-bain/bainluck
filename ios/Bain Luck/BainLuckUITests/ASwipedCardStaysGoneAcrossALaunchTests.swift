import XCTest

/// #6444 leg — **a card a reader swiped away is still gone the next time the app
/// opens.**
///
/// ## Why this is a test and not a signed-in walkthrough
///
/// This leg was carried for several sessions as "retained swipe history — needs a
/// signed-in simulator", and that premise is wrong. The Discover dismiss store is
/// **local and account-independent**: `DiscoverView` keeps `discover_dismissed_v2`
/// in `UserDefaults` (a `[String: TimeInterval]` of item id → dismissal time, a
/// 14-day TTL and a 500-entry cap), reads it into `@State` at launch and writes it
/// on every swipe. No session token is consulted on either side, so retention is
/// fully walkable by an anonymous reader — which is also the reader most likely to
/// be doing the swiping.
///
/// The corollary matters as much: **My Stuff never shows swipe history at all**,
/// signed in or out. It draws pins, the team feed and prediction stats. So a
/// My Stuff screenshot — signed in or signed out — was never evidence about this
/// behaviour in either direction, and the two questions should not be traded for
/// one another. What genuinely needs an account is My Stuff's own content, and
/// that is a different leg with a different blocker.
///
/// ## What makes this test able to fail
///
/// A feed is live, so "the card is not there any more" is the cheap assertion and
/// it passes for free the moment the pool rotates. The control is that the cards
/// swiped ALONGSIDE it must still be there: if none of them survive the relaunch,
/// the feed moved under the test and it SKIPS instead of claiming a retention it
/// did not observe.
final class ASwipedCardStaysGoneAcrossALaunchTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testACardSwipedAwayDoesNotComeBackOnTheNextLaunch() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)

        let cards = JourneyPrecondition.cards(in: app)
        JourneyPrecondition.settle(cards)

        // The neighbours are the control. Captured BEFORE the swipe, because
        // after it the page has relaid out and "what was on screen" is a
        // different set.
        let onScreen = cards.allElementsBoundByIndex.prefix(6).map(Self.signature(of:))
        let victim = onScreen.first ?? ""
        try XCTSkipIf(
            victim.isEmpty,
            "NOT WALKED: the first card exposed no text to identify it by, so a card that came back "
            + "could not be told from a card that never left."
        )
        let neighbours = onScreen.dropFirst().filter { !$0.isEmpty }
        try XCTSkipIf(
            neighbours.isEmpty,
            "NOT WALKED: only one identifiable card was on screen, so this run has no control for "
            + "feed rotation and a green would be indistinguishable from the pool simply moving."
        )

        cards.firstMatch.swipeLeft()

        var dismissed = false
        let deadline = Date().addingTimeInterval(10)
        while Date() < deadline {
            dismissed = !cards.allElementsBoundByIndex.contains { Self.signature(of: $0) == victim }
            if dismissed { break }
            Thread.sleep(forTimeInterval: 0.5)
        }
        try XCTSkipIf(
            !dismissed,
            "NOT WALKED: the left swipe did not remove the card within 10s, so there is no dismissal "
            + "whose PERSISTENCE could be tested. That is `AReaderCanSwipeAndRefreshDiscoverTests`' "
            + "subject (#1773) and it must not be re-reported here as a retention defect."
        )

        // ═══ THE RELAUNCH, WHICH IS THE WHOLE TEST ═══
        //
        // `terminate()` then a fresh `launchApp()` is a genuine cold start
        // against the SAME container, which is what a reader reopening the app
        // does. The store is read in `DiscoverView`'s `@State` initialiser, so a
        // dismissal that was never written — or was written and not read — shows
        // up here and nowhere else in this target.
        app.terminate()
        let relaunched = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: relaunched)
        _ = try JourneyPrecondition.firstCard(in: relaunched)

        let cardsAfter = JourneyPrecondition.cards(in: relaunched)
        JourneyPrecondition.settle(cardsAfter)
        let after = cardsAfter.allElementsBoundByIndex.map(Self.signature(of:))

        // The control: is this the same feed we swiped on?
        let survivors = neighbours.filter { after.contains($0) }
        try XCTSkipIf(
            survivors.isEmpty,
            "NOT WALKED: none of the \(neighbours.count) cards that sat beside the swiped one came back "
            + "after the relaunch, so the feed pool rotated and the swiped card's absence proves nothing. "
            + "Re-run; this is the control doing its job, not a defect."
        )

        XCTAssertFalse(
            after.contains(victim),
            "A card swiped away came back on the next launch, with \(survivors.count) of its neighbours "
            + "still in place — so the feed did NOT rotate and this is the dismiss store failing to "
            + "persist. `discover_dismissed_v2` is written in `saveDismissed` and read in "
            + "`loadDismissed`; a reader who swipes a card away is being shown it again. "
            + "(Card: \(victim.prefix(80)))"
        )
    }

    /// What a rendered card can be recognised by, without pinning its copy.
    ///
    /// The labels of its own text, joined — the same recognition
    /// `AReaderCanSwipeAndRefreshDiscoverTests` uses, and re-stated here rather
    /// than shared because the two tests may diverge: that one compares within a
    /// single launch, this one compares ACROSS one, so a card whose copy is
    /// time-dependent ("In 28m") could change under this test and not that one.
    /// If this starts flaking, that is the first thing to suspect.
    private static func signature(of card: XCUIElement) -> String {
        card.staticTexts.allElementsBoundByIndex.prefix(6).map { $0.label }.joined(separator: "|")
    }
}
