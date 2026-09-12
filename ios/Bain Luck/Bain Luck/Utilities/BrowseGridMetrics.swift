import CoreGraphics

// MARK: - How wide a Browse tile is allowed to get

/// The column minimums behind the Browse page's two grids.
///
/// #5655. Like `DiscoverMasonry` (#3651), `ChampionshipRowLayout` (#3574/#3580)
/// and `MarketMapRail` (#3503), this is arithmetic lifted out of a
/// `@ViewBuilder` so it can be asserted directly — a `GridItem` expression can
/// only be checked by reading pixels.
///
/// **What went wrong.** Both grids asked for one adaptive spec at every size:
///
/// ```swift
/// [GridItem(.adaptive(minimum: minimum, maximum: 320), spacing: 12)]
/// ```
///
/// `.adaptive` spends extra width on MORE columns, never on wider ones. So a
/// 13-inch iPad's 988 pt of content got six league columns of 155 pt, while a
/// 6-inch iPhone's 358 pt got two of 173 pt — **the big screen drew the tile
/// 18 pt narrower than the small one**, and truncated fifteen labels the phone
/// printed in full (`Bundesli…`, `NCAA Wome…`, `PGA Tour &…`). The featured
/// cards did the same thing: 320 pt on the phone, 238 pt on the iPad, which is
/// why "Futures Markets" wrapped onto two lines only on the larger device.
///
/// The "half the screen is empty" half of #5655 is the same cause seen from the
/// other side. Six columns were available and no league group has six leagues,
/// so every row ran out of tiles before it ran out of room. Four wider columns
/// fill the row that six narrow ones could not.
///
/// **The rule.** A tile is never drawn narrower on a big canvas than on a phone.
/// The minimum therefore grows with the horizontal size class, which is the
/// signal `EntertainmentView` already switches its own grid on.
///
/// **What this does not fix, stated rather than hidden.** The rule keys on the
/// size class, not on the measured canvas, so the one regular-width phone case —
/// a Max-model iPhone in landscape — gets the wide minimums (checked: still
/// 219 pt league tiles, wider than portrait, so it is an improvement there too),
/// while a *compact* landscape phone keeps the narrow ones and can still resolve
/// five 152 pt league columns. Reaching that case needs the real canvas width
/// from a `GeometryReader`, which is a bigger change than #5655 asked for and is
/// not what Alex's iPad walk found. It is recorded here rather than left to be
/// rediscovered.
enum BrowseGridMetrics {

    /// Which of the Browse page's two grids is being sized.
    enum Grid {
        /// The tournament hubs and tools at the top — icon, title, subtitle,
        /// chevron. The widest content on the page.
        case featured
        /// The per-league tiles under each group heading.
        case league
    }

    /// The gap between tiles, across and down. Unchanged from what both grids
    /// already asked for.
    static let spacing: CGFloat = 12

    /// The widest a tile may be drawn, at any size class. Unchanged: this is the
    /// cap that keeps a single-column phone card from spanning an iPad.
    static let maximumTileWidth: CGFloat = 320

    /// The narrowest a tile may be drawn before `.adaptive` drops a column.
    ///
    /// The compact numbers are the ones that shipped — 230 and 150 — so no phone
    /// tile moves by a pixel. The regular numbers are chosen as the largest that
    /// still leave the iPad's own rows full rather than sparse: at 988 pt they
    /// give four league columns of 238 pt (a group of four leagues fills its
    /// row exactly) and three featured columns at the 320 pt cap (the same width
    /// the phone gives them).
    static func minimumTileWidth(_ grid: Grid, regularWidth: Bool) -> CGFloat {
        switch grid {
        case .featured: return regularWidth ? 280 : 230
        case .league:   return regularWidth ? 200 : 150
        }
    }

    /// How wide `grid` resolves each tile to on a canvas of `availableWidth`.
    ///
    /// Delegates the `floor((w + s) / (m + s))` to `DiscoverMasonry`, which owns
    /// it — that file's own note is that a second copy of this arithmetic is
    /// exactly the bug it was written to stop (#3554).
    static func tileWidth(
        _ grid: Grid,
        availableWidth: CGFloat,
        regularWidth: Bool
    ) -> CGFloat {
        DiscoverMasonry.columnWidth(
            availableWidth: availableWidth,
            minimumCardWidth: minimumTileWidth(grid, regularWidth: regularWidth),
            maximumCardWidth: maximumTileWidth,
            spacing: spacing
        )
    }
}
