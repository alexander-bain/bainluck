import XCTest
@testable import Bain_Luck

/// #7074 — A GROUP OF THREE HID TWO OF ITS THREE ROWS BEHIND A BUTTON.
///
/// Alex, on build 15's UFC futures group (physical phone, 2026-09-18):
///
///   "This card is fantastic but has a similar issue where it started out only
///   showing one and asked me to click to see more, where it then only revealed
///   two more. If the total number that would be shown is only three, then we
///   should just show them all."
///
/// The same sentence about the Awards card two slots earlier. `group-overlap.png`
/// is the expanded state: three rows that fit comfortably, one tap and one
/// animation away from a card that was showing one.
///
/// ## Why the rule is a function and not two conditions in the body
///
/// The body asked `expanded` in one place to decide WHICH ROWS TO BUILD and
/// `!expanded` in another to decide WHETHER TO OFFER THE BUTTON. Two conditions
/// that must always agree are a defect waiting for someone to edit one of them —
/// a group drawn whole with a "Show 2 more" button under it is a worse card than
/// the one being fixed. One expression now answers both, and it is asserted
/// here directly rather than through a screenshot of a `@ViewBuilder`.
final class SmallGroupsAreDrawnWhole7074Tests: XCTestCase {

    private typealias Card = DiscoverGroupRows

    /// The reader's case: a three-item group arrives open.
    func testAGroupOfThreeOrFewerIsDrawnWholeWithoutATap() {
        for count in 1...3 {
            XCTAssertTrue(
                Card.showsEveryRow(itemCount: count, expanded: false),
                """
                a group of \(count) still hides rows behind "Show \(count - 1) more". \
                The button costs a tap, an animation and a layout change to reveal \
                rows that already fit.
                """
            )
        }
    }

    /// The control. Without this the rule could be "always show everything",
    /// which is not what was asked for and would make a 12-market group
    /// unusable — codex's brief: "Larger groups retain expansion."
    func testAGroupLargerThanTheLimitStillCollapses() {
        for count in 4...12 {
            XCTAssertFalse(
                Card.showsEveryRow(itemCount: count, expanded: false),
                "a group of \(count) is drawn whole; groups past the limit must still collapse"
            )
        }
    }

    /// Expanding still works, at every size — the change raises the floor, it
    /// does not remove the control.
    func testExpandingShowsEveryRowAtAnySize() {
        for count in 1...12 {
            XCTAssertTrue(
                Card.showsEveryRow(itemCount: count, expanded: true),
                "an expanded group of \(count) is not showing every row"
            )
        }
    }

    /// The boundary is where a rule is wrong by one, and 3-vs-4 is the whole of
    /// Alex's ask. Pinned as the two answers rather than as the constant, so
    /// moving `showsEveryRowUpTo` to 4 without meaning to fails here.
    func testTheLimitIsThreeAndFourIsTheFirstCollapsedGroup() {
        XCTAssertEqual(Card.showsEveryRowUpTo, 3)
        XCTAssertTrue(Card.showsEveryRow(itemCount: 3, expanded: false))
        XCTAssertFalse(Card.showsEveryRow(itemCount: 4, expanded: false))
    }

    /// An empty group cannot ask for a button it has no rows for.
    func testAnEmptyGroupIsTrivallyWhole() {
        XCTAssertTrue(Card.showsEveryRow(itemCount: 0, expanded: false))
    }
}
