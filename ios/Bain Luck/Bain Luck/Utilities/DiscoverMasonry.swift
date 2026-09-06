import CoreGraphics

// MARK: - How the Discover feed divides itself into columns

/// How the Discover feed assigns its cards to columns when the window is wide
/// enough for more than one.
///
/// #3651. Like `ChampionshipRowLayout` (#3574/#3580) and `MarketMapRail` (#3503),
/// this is arithmetic lifted out of a `@ViewBuilder` so it can be asserted
/// directly: a raster can tell you a gap is 68 pt, but it cannot tell you why,
/// and a `GridItem` expression can only be checked by reading pixels.
///
/// **What went wrong.** Discover rendered its cards through
///
/// ```swift
/// let columns = [GridItem(.adaptive(minimum: 300), spacing: 16)]
/// LazyVGrid(columns: columns, spacing: 16) { … }
/// ```
///
/// `LazyVGrid` lays out in **rows**, and every cell in a row is padded to the
/// height of the tallest cell in that row. It is a grid, not a masonry layout.
/// On iPhone `.adaptive(minimum: 300)` resolves to a single column, rows contain
/// one cell each, and there is nothing to pad — which is why this survived
/// fifteen sessions of phone screenshots. On iPad it resolves to two, and every
/// short card is stretched to whatever tall card happens to sit beside it.
///
/// Measured on iPad Pro 11-inch (834 × 1210 pt) against production:
///
/// - `artifacts-native-042/ipad-discover.png` (2026-09-06, the first photograph
///   of Discover at this size): **91 pt** and **82 pt** of background between
///   right-column cards.
/// - `artifacts-native-044/BEFORE-ipad-discover.png` (2026-09-06, a different
///   feed several hours later): **68 pt** in the right column against a
///   left-column maximum of 24 pt.
///
/// The design spacing is **16 pt**. These are 4×–6× that, they appear in one
/// column and not the other, and they are not a constant anyone can tune: they
/// are the height *differences* between whichever cards the feed paired up, so
/// they change on every refresh.
///
/// **The rule.** Stop asking `LazyVGrid` for a masonry layout. Deal the cards
/// into `columnCount` buckets and render each bucket as its own `LazyVStack`
/// inside an `HStack(alignment: .top)`. A `LazyVStack` packs its children at
/// exactly its spacing, so no card is ever padded to a neighbour's height and
/// the interior gaps cannot exist — whatever the feed serves.
///
/// **Why the deal is round-robin and not shortest-column-first.** #3651 proposed
/// bucketing by running height. That needs every card's height *before* it is
/// rendered, and the only way to have those is to estimate them from the card
/// archetype — a table of numbers nobody measured, which is the thing this lane
/// exists to stop shipping. It would also cost the laziness: `LazyVStack` only
/// builds what is on screen, and Discover pages up to hundreds of cards
/// (`visibleCount += 20`), so a layout that must size every card up front is a
/// real regression on the device that has this bug.
///
/// Round-robin needs no heights at all, and it is what preserves rank: card 0 is
/// top-left, card 1 is top-right, card 2 is second-left. Shortest-first would
/// reorder the feed's own ranking to suit the pixels, which is a worse bug than
/// the one being fixed.
///
/// **What this does not fix, stated rather than hidden.** Balancing by count
/// rather than height leaves the columns ending at different depths — a ragged
/// bottom edge at the growing end of the page. That is bounded by the height
/// difference the feed happens to deal out and it is at the edge of the content,
/// not a hole in the middle of it. Closing it properly needs heights measured
/// from the render and fed back, which converges in one pass (column width does
/// not depend on the assignment, so neither does any card's height) but costs a
/// visible reflow on first paint. That is a separate question from how the cards
/// are dealt, and it is filed rather than guessed at here.
enum DiscoverMasonry {

    // MARK: Measured constants

    /// The narrowest a Discover card may be drawn. Carried over unchanged from
    /// the `GridItem(.adaptive(minimum: 300))` this replaces, so the breakpoint
    /// where the feed becomes two columns does not move.
    static let minimumCardWidth: CGFloat = 300

    /// The gap between cards, both down a column and across the gutter. The
    /// design spacing, and the number the measured 68 pt should have been.
    static let spacing: CGFloat = 16

    // MARK: Column count

    /// How many columns `availableWidth` holds, reproducing what
    /// `GridItem(.adaptive(minimum: 300), spacing: 16)` resolved to so that no
    /// device changes its column count as a side effect of this fix.
    ///
    /// `.adaptive` fits as many columns of at least `minimum` as it can:
    /// `n` columns need `n * minimum + (n - 1) * spacing`. Solving for the
    /// largest such `n` gives `floor((width + spacing) / (minimum + spacing))`,
    /// floored at 1 so a width that is not yet known (0 on the first layout
    /// pass, before the geometry resolves) renders the single-column phone path
    /// rather than nothing.
    static func columnCount(availableWidth: CGFloat) -> Int {
        guard availableWidth > 0 else { return 1 }
        let n = Int((availableWidth + spacing) / (minimumCardWidth + spacing))
        return max(1, n)
    }

    // MARK: The deal

    /// Deals `cardCount` card indices into `columnCount` columns, left to right,
    /// so that reading the columns in parallel reads the feed in rank order.
    ///
    /// Returns exactly `columnCount` buckets (some may be empty when there are
    /// fewer cards than columns), each holding its indices in ascending order.
    /// `columnCount == 1` returns the identity: one bucket, every index, in the
    /// order the feed served them.
    static func columns(cardCount: Int, columnCount: Int) -> [[Int]] {
        let n = max(1, columnCount)
        guard cardCount > 0 else { return Array(repeating: [], count: n) }
        var buckets = Array(repeating: [Int](), count: n)
        for index in 0..<cardCount {
            buckets[index % n].append(index)
        }
        return buckets
    }
}
