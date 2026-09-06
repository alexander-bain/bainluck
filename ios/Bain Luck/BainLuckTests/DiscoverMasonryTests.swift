import XCTest
@testable import Bain_Luck

/// #3651 — iPad Discover left 68–91 pt of background between right-column cards
/// against a 16 pt design spacing, because `LazyVGrid` pads every cell in a row
/// to the tallest cell in that row.
///
/// The pixels cannot be asserted from here, so what is pinned is the arithmetic
/// the render is built on: the column count each supported width resolves to,
/// and the deal that puts a card in a column. The gaps cannot come back while
/// both hold, because a `LazyVStack` has no row to pad to.
final class DiscoverMasonryTests: XCTestCase {

    // MARK: - Column count: the breakpoint must not move

    /// The whole reason this bug reached fifteen sessions of phone screenshots
    /// is that iPhone resolves to one column. That must stay true, or the fix
    /// ships the bug to the device that never had it.
    func testIPhoneWidthsResolveToOneColumn() {
        // iPhone 17 is 402 pt wide; the card area is that less `.padding()`'s
        // 16 pt a side. The narrowest supported phone (SE, 375 pt) is included
        // because `ChampionshipRowLayout` proved the narrow end is where
        // geometry breaks.
        for (device, screenWidth) in [("iPhone SE", 375.0), ("iPhone 17", 402.0), ("iPhone 17 Pro Max", 440.0)] {
            let cardArea = CGFloat(screenWidth) - 32
            XCTAssertEqual(
                DiscoverMasonry.columnCount(availableWidth: cardArea), 1,
                "\(device) (\(cardArea) pt of card area) must stay a single column"
            )
        }
    }

    /// iPad Pro 11-inch is 834 × 1210 pt, and `artifacts-native-044/` was shot
    /// on it in two columns. The fix must resolve to the same two, so that the
    /// only thing that changes is how the cards are stacked.
    func testIPadPro11ResolvesToTwoColumns() {
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: 834 - 32), 2)
    }

    /// The exact `.adaptive(minimum: 300)` boundary, from both sides. Two
    /// columns need `2 * 300 + 16 = 616` pt; one pixel under is one column.
    func testColumnCountIsExactAtTheAdaptiveBoundary() {
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: 615), 1)
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: 616), 2)
        // Three columns need 3 * 300 + 2 * 16 = 932.
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: 931), 2)
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: 932), 3)
    }

    /// Before the first geometry pass the width is 0. That must read as the
    /// phone path, not as zero columns — a `max(1, …)` that is missing renders
    /// an empty feed on launch, which is a worse bug than the one being fixed.
    func testUnknownWidthFallsBackToOneColumn() {
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: 0), 1)
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: -1), 1)
        XCTAssertEqual(DiscoverMasonry.columnCount(availableWidth: 10), 1)
    }

    // MARK: - The deal

    /// One column is the identity. This is the assertion that says the phone
    /// renders the feed in exactly the order the ranker served it.
    func testOneColumnIsTheIdentityDeal() {
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 6, columnCount: 1), [[0, 1, 2, 3, 4, 5]])
    }

    /// Rank order, which is the property that would be lost by dealing
    /// shortest-column-first. Card 0 is top-left, card 1 is top-right, card 2 is
    /// second-left: reading the columns in parallel reads the feed in order.
    func testTwoColumnsDealInRankOrder() {
        XCTAssertEqual(
            DiscoverMasonry.columns(cardCount: 7, columnCount: 2),
            [[0, 2, 4, 6], [1, 3, 5]]
        )
    }

    func testThreeColumnsDealInRankOrder() {
        XCTAssertEqual(
            DiscoverMasonry.columns(cardCount: 7, columnCount: 3),
            [[0, 3, 6], [1, 4], [2, 5]]
        )
    }

    /// Every card is dealt exactly once, at every count and every column count
    /// the app can reach. A deal that drops a card hides a market; a deal that
    /// repeats one shows it twice.
    func testEveryCardIsDealtExactlyOnce() {
        for columnCount in 1...4 {
            for cardCount in 0...40 {
                let buckets = DiscoverMasonry.columns(cardCount: cardCount, columnCount: columnCount)
                let dealt = buckets.flatMap { $0 }.sorted()
                XCTAssertEqual(
                    dealt, Array(0..<cardCount),
                    "cardCount=\(cardCount) columnCount=\(columnCount) lost or duplicated a card"
                )
            }
        }
    }

    /// The buckets always number `columnCount`, even when there are fewer cards
    /// than columns. The view builds one `LazyVStack` per bucket, so a short
    /// bucket list would silently narrow the feed to fewer columns than the
    /// window resolved to.
    func testBucketCountAlwaysMatchesColumnCount() {
        for columnCount in 1...4 {
            for cardCount in 0...5 {
                XCTAssertEqual(
                    DiscoverMasonry.columns(cardCount: cardCount, columnCount: columnCount).count,
                    columnCount,
                    "cardCount=\(cardCount) columnCount=\(columnCount)"
                )
            }
        }
    }

    /// Balanced by COUNT — the property this deal actually promises. Columns
    /// never differ by more than one card, at any page size. (Balance by HEIGHT
    /// is explicitly not promised; see `DiscoverMasonry`'s note on the ragged
    /// bottom edge.)
    func testColumnsAreBalancedToWithinOneCard() {
        for columnCount in 2...4 {
            for cardCount in 0...40 {
                let sizes = DiscoverMasonry.columns(cardCount: cardCount, columnCount: columnCount).map(\.count)
                XCTAssertLessThanOrEqual(
                    (sizes.max() ?? 0) - (sizes.min() ?? 0), 1,
                    "cardCount=\(cardCount) columnCount=\(columnCount) dealt \(sizes)"
                )
            }
        }
    }

    /// Within a column the indices ascend, so scrolling one column down still
    /// walks the feed forwards. This is also what keeps the `onAppear`
    /// pagination trigger (`idx == pageGrouped.count - 3`) near the bottom of
    /// the page rather than somewhere in the middle of a column.
    func testIndicesAscendWithinEachColumn() {
        for columnCount in 1...4 {
            for bucket in DiscoverMasonry.columns(cardCount: 37, columnCount: columnCount) {
                XCTAssertEqual(bucket, bucket.sorted(), "columnCount=\(columnCount) bucket out of order")
            }
        }
    }

    /// A zero-card page must not crash or return a single empty bucket when the
    /// window is two columns wide — the feed renders an empty state through the
    /// same container.
    func testEmptyPageStillReturnsOneBucketPerColumn() {
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 0, columnCount: 2), [[], []])
    }

    /// A degenerate column count from a caller must not produce zero buckets.
    func testNonPositiveColumnCountIsClampedToOne() {
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 3, columnCount: 0), [[0, 1, 2]])
        XCTAssertEqual(DiscoverMasonry.columns(cardCount: 3, columnCount: -2), [[0, 1, 2]])
    }
}
