import XCTest
@testable import Bain_Luck

/// #6444 / #1221 part three — a SHORT page must still ask for the next one.
///
/// Alex's 2026-09-15 physical-phone walkthrough: three cards, and "there's no
/// obvious way to get more. Pulling to refresh the screen doesn't improve the
/// situation, nor does leaving and returning or even force quitting the app."
///
/// The cause was not a filter. Both of Discover's prefetch triggers were index
/// comparisons against `pageGrouped.count - lookahead`:
///
///     if idx == pageGrouped.count - 3 { visibleCount += 20 }
///     if idx == pageGrouped.count - 5 { Task { await vm.loadMoreIfNeeded() } }
///
/// On a page of three those right-hand sides are `0` and `-2`. No index is ever
/// `-2`, so the network trigger was DEAD on exactly the pages that needed it,
/// and the only other refill path (`hideForSession`) needs a swipe the reader
/// has no reason to make. Every recovery gesture re-fetched page ONE.
///
/// His own client-reported impression rows corroborate it: across two different
/// feed payloads that session, the maximum rank his phone ever reported was 3,
/// and the footer drew neither the end card nor a spinner — the signature of
/// `hasMore == true` with page two never requested.
///
/// Two contracts, both needed. The index rule makes the trigger reachable on a
/// short page; the standing rule keeps asking after a page lands and is short
/// too, which `onAppear` cannot do because it runs once per card identity.
final class DiscoverShortPageRefill6444Tests: XCTestCase {

    // MARK: - The index rule

    /// The regression, stated as the arithmetic that caused it. A page shorter
    /// than the lookahead used to compute a NEGATIVE trigger index, which no
    /// `idx` can equal.
    func testShortPageTriggerIsReachable() {
        for pageCount in 0...5 {
            let trigger = DiscoverView.prefetchTriggerIndex(
                pageCount: pageCount, lookahead: 5)
            XCTAssertGreaterThanOrEqual(
                trigger, 0,
                "a page of \(pageCount) computed trigger index \(trigger); "
                + "a negative index is unreachable and is the #6444 defect")
            if pageCount > 0 {
                XCTAssertLessThan(
                    trigger, pageCount,
                    "a page of \(pageCount) must put its trigger on a card it "
                    + "actually draws")
            }
        }
    }

    /// Alex's exact page. Three cards, five-card lookahead: the first card is
    /// the one that asks.
    func testThreeCardPageAsksOnItsFirstCard() {
        XCTAssertEqual(
            DiscoverView.prefetchTriggerIndex(pageCount: 3, lookahead: 5), 0)
        XCTAssertEqual(
            DiscoverView.prefetchTriggerIndex(pageCount: 3, lookahead: 3), 0)
    }

    /// The clamp must not change the rule on pages that were already working —
    /// a full page still prefetches `lookahead` cards from its end, not at its
    /// start. A fix that made every page fire on card one would page eagerly
    /// forever and would pass the test above.
    func testLongPageKeepsItsLookahead() {
        XCTAssertEqual(
            DiscoverView.prefetchTriggerIndex(pageCount: 20, lookahead: 5), 15)
        XCTAssertEqual(
            DiscoverView.prefetchTriggerIndex(pageCount: 20, lookahead: 3), 17)
        XCTAssertEqual(
            DiscoverView.prefetchTriggerIndex(pageCount: 6, lookahead: 5), 1)
    }

    /// Exactly one card fires the trigger, at every page length. A rule written
    /// `idx >= max(count - lookahead, 0)` also clears the reachability test and
    /// would fire on every card of a short page.
    func testExactlyOneCardFiresPerPage() {
        for pageCount in 1...24 {
            for lookahead in [3, 5] {
                let trigger = DiscoverView.prefetchTriggerIndex(
                    pageCount: pageCount, lookahead: lookahead)
                let firing = (0..<pageCount).filter { $0 == trigger }
                XCTAssertEqual(
                    firing.count, 1,
                    "page \(pageCount), lookahead \(lookahead): \(firing.count) "
                    + "cards fire the prefetch")
            }
        }
    }

    // MARK: - The standing rule

    /// The page Alex was looking at: under the floor, server says there is
    /// more, nothing in flight. This must ask.
    func testShortPageWithMoreAvailableAsksForMore() {
        XCTAssertTrue(DiscoverView.needsMorePages(
            drawn: 3, hasMore: true, loadingMore: false))
    }

    /// The server's own terminal. "All caught up" is an honest answer and must
    /// not be turned into a request loop.
    func testExhaustedFeedDoesNotAsk() {
        XCTAssertFalse(DiscoverView.needsMorePages(
            drawn: 3, hasMore: false, loadingMore: false))
        XCTAssertFalse(DiscoverView.needsMorePages(
            drawn: 0, hasMore: false, loadingMore: false))
    }

    /// A request already in flight is the other terminal — this rule re-fires
    /// on every arriving page, so without it a slow page would stack requests.
    func testInFlightLoadDoesNotStack() {
        XCTAssertFalse(DiscoverView.needsMorePages(
            drawn: 3, hasMore: true, loadingMore: true))
    }

    /// A page that has met the floor stops asking even though the server has
    /// more — that is what the floor is for, and a rule without this clause
    /// would page the whole feed down on first paint.
    func testFloorMetStopsAsking() {
        XCTAssertFalse(DiscoverView.needsMorePages(
            drawn: DiscoverView.feedFloor, hasMore: true, loadingMore: false))
        XCTAssertFalse(DiscoverView.needsMorePages(
            drawn: DiscoverView.feedFloor + 20, hasMore: true, loadingMore: false))
        XCTAssertTrue(
            DiscoverView.needsMorePages(
                drawn: DiscoverView.feedFloor - 1, hasMore: true, loadingMore: false),
            "the boundary is the floor itself, not one short of it")
    }

    /// The floor this rule defends is the BROWSE floor (`feedFloor`), not the
    /// group-expansion floor. #6444's acceptance is "10–15 genuinely varied
    /// cards", and `groupExpansionFloor` is 8 — a rule that stopped there would
    /// pass every test above and still leave the reader short of the bar.
    func testRuleDefendsTheBrowseFloorNotTheGroupFloor() {
        XCTAssertGreaterThan(DiscoverView.feedFloor, 15)
        XCTAssertTrue(
            DiscoverView.needsMorePages(
                drawn: DiscoverView.groupExpansionFloor,
                hasMore: true, loadingMore: false),
            "a page at the group-expansion floor is still under the browse floor "
            + "and must keep asking")
    }
}
