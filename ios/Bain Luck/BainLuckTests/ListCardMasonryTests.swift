import XCTest
import CoreGraphics
@testable import Bain_Luck

/// #3709 — the three `List`-backed iPad card surfaces had the identical defect
/// #3651 fixed in Discover: `GridItem(.adaptive(minimum: 340), spacing: 12)`
/// fed to a `LazyVGrid`, which lays out in ROWS and pads every cell to the
/// tallest cell in that row.
///
/// The helper was copied verbatim into four files — `FeedView` (the Sports
/// tab), `SportCategoryView`, `MyStuffView` and `SearchView`. The first three
/// deal `[FeedItem]`, which mixes the tall `EventCardView` with the short
/// futures strip, so they are the ones that show it. `SearchView`'s two grids
/// are each homogeneous and are deliberately left alone; that decision is
/// recorded in `frontend/__tests__/ios/listCardMasonry.test.ts` rather than
/// left as an omission.
///
/// The surplus lands as dead space BELOW the shorter card in its column, not
/// as a stretched card: `LazyVGrid` top-aligns the cell content inside the
/// padded row and `.background` wraps the content rather than the row frame.
/// Measured on `bainluck://category/tennis`, iPad Pro 11-inch, in the
/// "Just Happened" section — **right-column gap 50 px before, 30 px after,
/// against a left column that did not move (28 px both times)**. That is
/// ~11 pt of dead space per row, in one column only, and it changes with
/// whatever the feed happens to pair up.
///
/// **What is photographed and what is not, stated rather than hidden.**
/// `bainluck://category/tennis` reaches `SportCategoryView` with no sign-in, so
/// that surface is photographed AND measured before and after in
/// `artifacts-native-045/`, with the left column as the control.
/// **My Stuff cannot be**: it renders `teamFeedView` only for
/// `authManager.isAuthenticated && user?.onboardingCompleted == true`,
/// `isAuthenticated` is `user != nil` off a Keychain-restored session token,
/// `LaunchRig` drives a ROUTE but has no affordance that seeds a signed-in
/// reader, and Apple/Google sign-in is not completable headlessly. On a fresh
/// simulator `bainluck://my-stuff` is the sign-in wall —
/// `artifacts-native-044/ipad-mystuff.png` is a photograph of that wall, not of
/// the grid. native/044 declined to call it clean on that evidence and was
/// right to.
///
/// What makes that acceptable rather than a hole: **the fix does not depend on
/// knowing the column count.** A `VStack` packs its children at exactly its
/// spacing, so no cell can be padded to a neighbour's height at ANY column
/// count — at one column the deal is the identity, and at two or more there is
/// no row to pad to. The photograph shows how many columns a reader sees; it is
/// not what proves the padding is gone, because the padding cannot come back
/// while the arithmetic below holds. All three surfaces share one code path
/// (`DiscoverMasonry.listColumnCount` + `.columns`), so the shot of one is
/// evidence about that path.
final class ListCardMasonryTests: XCTestCase {

    /// The metrics the views actually render with. Read from `DiscoverMasonry`
    /// rather than restated, so a change to the card width cannot leave this
    /// file asserting a breakpoint the app no longer has.
    private let minimum = DiscoverMasonry.listCardMinimumWidth
    private let spacing = DiscoverMasonry.listCardSpacing

    // MARK: - The metrics carried over from the LazyVGrid

    /// The whole claim that this fix changes layout and not sizing rests on the
    /// two numbers being the ones `GridItem(.adaptive(minimum: 340), spacing: 12)`
    /// already used. If either moves, cards change width and the breakpoint
    /// moves with them — which is a different change than the one #3709 asked
    /// for.
    func testCardMetricsAreTheOnesTheGridAlreadyUsed() {
        XCTAssertEqual(minimum, 340)
        XCTAssertEqual(spacing, 12)
    }

    // MARK: - Column count

    /// Two columns need `2 * 340 + 12 = 692` pt; one pixel under is one column.
    /// Three need `3 * 340 + 2 * 12 = 1044`.
    func testColumnCountIsExactAtTheAdaptiveBoundary() {
        for (width, expected) in [(691.0, 1), (692.0, 2), (1043.0, 2), (1044.0, 3)] {
            XCTAssertEqual(
                DiscoverMasonry.columnCount(
                    availableWidth: CGFloat(width),
                    minimumCardWidth: minimum,
                    spacing: spacing
                ),
                expected,
                "\(width) pt of card area must resolve to \(expected) column(s)"
            )
        }
    }

    /// iPad Pro 11-inch is 834 pt wide and the section's own
    /// `listRowInsets` take 16 pt a side, so the card area is at most 802 pt —
    /// inside the two-column band. The List style's own margins take some
    /// further unphotographed amount, so 802 is an upper bound rather than a
    /// measurement; it would have to eat 111 pt before the band changed, which
    /// `.insetGrouped` does not. Asserted as a band, not a point, for exactly
    /// that reason.
    func testIPadPro11SitsInsideTheTwoColumnBand() {
        for width in stride(from: 692.0, through: 1043.0, by: 39.0) {
            XCTAssertEqual(
                DiscoverMasonry.columnCount(
                    availableWidth: CGFloat(width),
                    minimumCardWidth: minimum,
                    spacing: spacing
                ),
                2,
                "\(width) pt is in the two-column band"
            )
        }
    }

    /// Before the first geometry pass `gridWidth` is 0. That must read as one
    /// column, not zero — a missing `max(1, …)` renders an empty section on
    /// open, which is worse than the bug being fixed.
    func testUnknownWidthFallsBackToOneColumn() {
        for width in [0.0, -1.0, 10.0, 691.0] {
            XCTAssertEqual(
                DiscoverMasonry.columnCount(
                    availableWidth: CGFloat(width),
                    minimumCardWidth: minimum,
                    spacing: spacing
                ),
                1
            )
        }
    }

    // MARK: - The deal

    /// Reading the columns in parallel must read the section in the order the
    /// view model served it: Pinned, Live Now and Upcoming are ordered lists,
    /// and a deal that reordered them would be a worse bug than a tall card.
    func testTwoColumnDealPreservesSectionOrder() {
        let columns = DiscoverMasonry.columns(cardCount: 5, columnCount: 2)
        XCTAssertEqual(columns, [[0, 2, 4], [1, 3]])
    }

    /// A one-item section — the common My Stuff case, and the one where an
    /// empty second column must not appear as a half-width hole.
    func testSingleItemSectionFillsOnlyTheFirstColumn() {
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 1, columnCount: 2), [[0], []])
    }

    /// An empty section still returns one bucket per column rather than
    /// nothing, so the `ForEach` over columns is total.
    func testEmptySectionStillReturnsOneBucketPerColumn() {
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 0, columnCount: 2), [[], []])
    }
}
