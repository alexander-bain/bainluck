import XCTest
@testable import Bain_Luck

/// #1773 — "none of these cards can be swiped left or right" on iOS Discover.
///
/// The report named one symptom; the surface carried three separable defects.
/// SwiftUI bodies are not unit-rendered here (and this sandbox cannot compile
/// Swift at all — see #1848), so each defect was extracted into pure logic and
/// is pinned below against a literal reference copy of the shipped behaviour.
///
///   A. `DiscoverSwipeState` — the gesture state machine. Two bugs:
///      the axis latch was gated on `offset == 0`, and a committed swipe never
///      reset `offset`/`removing`.
///   B. `DiscoverView.dismissKeys(forGroupOf:)` — a swipe on a GROUP card has to
///      suppress every member, or the group re-forms from the survivors.
///   C. `NativeFeedEndCard.bodyCopy(hasRefreshAction:)` — the bottom-of-feed
///      card must not instruct a gesture that surface cannot accept.
final class DiscoverSwipeTests: XCTestCase {

    // MARK: - A1. Axis latching

    func testHorizontalDragLatchesHorizontalAndTracksOffset() {
        var s = DiscoverSwipeState()
        s.change(width: 30, height: 4)
        XCTAssertTrue(s.isHorizontal)
        XCTAssertEqual(s.offset, 30)
    }

    func testVerticalDragNeverMovesTheCard() {
        var s = DiscoverSwipeState()
        s.change(width: 4, height: 30)
        XCTAssertFalse(s.isHorizontal)
        XCTAssertEqual(s.offset, 0, "a vertical drag is a scroll; the card must not track it")

        // Still zero even as the vertical drag continues and gains some width.
        s.change(width: 40, height: 120)
        XCTAssertEqual(s.offset, 0, "axis is latched once per gesture — a scroll never becomes a swipe mid-drag")
    }

    func testAxisIsLatchedOncePerGestureAndClearedOnEnd() {
        var s = DiscoverSwipeState()
        s.change(width: 30, height: 2)
        XCTAssertTrue(s.axisLatched)
        _ = s.end(width: 30)
        XCTAssertFalse(s.axisLatched, "the latch must not survive its own gesture")
        XCTAssertFalse(s.isHorizontal)
    }

    // MARK: - A2. Commit threshold

    func testCommitsRightBeyondThreshold() {
        var s = DiscoverSwipeState()
        s.change(width: 150, height: 5)
        XCTAssertTrue(s.commits(width: 150))
        XCTAssertEqual(s.end(width: 150), .right)
        XCTAssertTrue(s.removing)
    }

    func testCommitsLeftBeyondThreshold() {
        var s = DiscoverSwipeState()
        s.change(width: -150, height: 5)
        XCTAssertEqual(s.end(width: -150), .left)
        XCTAssertEqual(s.offset, -DiscoverSwipeState.exitOffset)
    }

    func testShortDragSpringsBackWithoutCommitting() {
        var s = DiscoverSwipeState()
        s.change(width: 100, height: 5)
        XCTAssertFalse(s.commits(width: 100))
        XCTAssertEqual(s.end(width: 100), .none)
        XCTAssertEqual(s.offset, 0)
        XCTAssertFalse(s.removing)
    }

    func testVerticalDragCannotCommitEvenAtLargeWidth() {
        var s = DiscoverSwipeState()
        s.change(width: 5, height: 60)   // latches vertical
        XCTAssertEqual(s.end(width: 400), .none, "a latched scroll must never fire like/unlike")
    }

    // MARK: - A3. The regression that made swipe "dead" — post-commit reset

    /// Literal copy of the SHIPPED (pre-#1773) state machine. This is the ground
    /// truth the tests below prove is broken, in the same style
    /// `DiscoverPresentationTests` uses for the old interleave.
    private struct LegacySwipeState {
        var offset: CGFloat = 0
        var removing = false
        var isHorizontalDrag = false

        mutating func change(width: CGFloat, height: CGFloat) {
            if !isHorizontalDrag && offset == 0 {          // ← the defect
                isHorizontalDrag = abs(width) > abs(height)
            }
            if isHorizontalDrag { offset = width }
        }

        mutating func end(width: CGFloat) -> DiscoverSwipeOutcome {
            var outcome = DiscoverSwipeOutcome.none
            if isHorizontalDrag && abs(width) > 120 {
                outcome = width > 0 ? .right : .left
                offset = width > 0 ? 400 : -400
                removing = true                            // ← never cleared
            } else {
                offset = 0
            }
            isHorizontalDrag = false
            return outcome
        }
    }

    /// The exact production sequence: swipe a card, then have it come BACK.
    ///
    /// It comes back for two real reasons, both in `DiscoverView`:
    /// `filteredItems` backfills the least-recently-dismissed whenever dismissal
    /// would drop the feed below `feedFloor`, and pull-to-refresh calls
    /// `dismissedAt.removeAll()`. Either way the same `gi.id` re-renders, and
    /// `ForEach(id:)` + `.id(gi.id)` hand it back the SAME `@State`.
    func testLegacyStateIsPermanentlyDeadAfterOneCommit() {
        var legacy = LegacySwipeState()
        legacy.change(width: 150, height: 5)
        XCTAssertEqual(legacy.end(width: 150), .right)

        // Card returns. State was reused, so offset == 400 and removing == true.
        XCTAssertEqual(legacy.offset, 400)
        XCTAssertTrue(legacy.removing, "card is rendered at opacity 0 — invisible")

        // Alex swipes it again. `offset == 0` is false, so the axis never latches.
        legacy.change(width: 200, height: 5)
        XCTAssertFalse(legacy.isHorizontalDrag)
        XCTAssertEqual(legacy.offset, 400, "the card does not move at all")
        XCTAssertEqual(legacy.end(width: 200), .none, "and no like/unlike is ever produced")
    }

    func testFixedStateIsVisibleAndSwipeableAfterTheCardReturns() {
        var s = DiscoverSwipeState()
        s.change(width: 150, height: 5)
        XCTAssertEqual(s.end(width: 150), .right)
        XCTAssertEqual(s.opacity, 0, accuracy: 0.0001, "flying out, still invisible")

        // The commit callback has run; the row may or may not have survived.
        s.settleAfterCommit()
        XCTAssertEqual(s.offset, 0)
        XCTAssertFalse(s.removing)
        XCTAssertEqual(s.opacity, 1, accuracy: 0.0001, "a returned card is VISIBLE again")

        // And it accepts a second swipe.
        s.change(width: 200, height: 5)
        XCTAssertTrue(s.isHorizontal)
        XCTAssertEqual(s.offset, 200)
        XCTAssertEqual(s.end(width: 200), .right, "the second swipe registers")
    }

    /// Opacity must clamp: `1 - 400/300` is negative.
    func testOpacityNeverGoesNegative() {
        var s = DiscoverSwipeState()
        s.change(width: 380, height: 5)
        XCTAssertGreaterThanOrEqual(s.opacity, 0)
    }

    // MARK: - A4. Affordance

    func testOverlaySidesAndVisibility() {
        var s = DiscoverSwipeState()
        s.change(width: 5, height: 1)
        XCTAssertFalse(s.showsOverlay, "below the reveal distance, no affordance")

        s.change(width: 60, height: 1)
        XCTAssertTrue(s.showsOverlay)
        XCTAssertTrue(s.overlayIsLeading, "right drag = 'More like this', leading")

        var l = DiscoverSwipeState()
        l.change(width: -60, height: 1)
        XCTAssertTrue(l.showsOverlay)
        XCTAssertFalse(l.overlayIsLeading, "left drag = 'Less like this', trailing")
    }

    // MARK: - B. Group swipe must suppress every member

    private func futuresItem(id: Int) throws -> FeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data("""
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Market \(id)?",
            "llm_sport_category": "politics",
            "source": "kalshi",
            "status": "open",
            "top_outcomes": [{"id": \(id * 10), "name": "Yes", "probability": 0.4, "rank": 1, "movement": null}],
            "outcome_count": 1
          }
        }
        """.utf8))
    }

    /// A group card is ONE card to the reader but N feed items to
    /// `filteredItems`, which filters by item id. Dismissing only the primary
    /// child lets the group immediately re-form from the remaining N-1 — the card
    /// visibly returns, and the swipe reads as ignored.
    func testGroupSwipeDismissesEveryMemberNotJustThePrimary() throws {
        let members = try (1...4).map { try futuresItem(id: $0) }
        let keys = DiscoverView.dismissKeys(forGroupOf: members)

        XCTAssertEqual(keys.count, 4, "every member of the group is suppressed")
        XCTAssertEqual(Set(keys), ["futures-1", "futures-2", "futures-3", "futures-4"])
    }

    func testDismissKeyIsStableAndArchetypeQualified() throws {
        let item = try futuresItem(id: 7)
        XCTAssertEqual(DiscoverView.feedItemId(item), "futures-7")
        XCTAssertEqual(DiscoverView.feedItemId(item), DiscoverView.feedItemId(item), "stable across calls")
    }

    func testEmptyGroupYieldsNoKeys() {
        XCTAssertTrue(DiscoverView.dismissKeys(forGroupOf: []).isEmpty)
    }

    // MARK: - C. The end card must not ask for an unreachable gesture

    func testEndCardWithARefreshActionDoesNotInstructPullToRefresh() {
        let copy = NativeFeedEndCard.bodyCopy(hasRefreshAction: true)
        XCTAssertFalse(
            copy.lowercased().contains("pull"),
            "this card renders at the BOTTOM of the feed, where pull-to-refresh cannot be performed"
        )
        XCTAssertTrue(copy.contains("couple of hours"), "the honest cadence line is kept")
    }

    func testEndCardWithoutAnActionStillNamesTheGesture() {
        let copy = NativeFeedEndCard.bodyCopy(hasRefreshAction: false)
        XCTAssertTrue(copy.lowercased().contains("pull to refresh"))
    }
}
