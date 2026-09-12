import XCTest
@testable import Bain_Luck

/// #5655 — the 13-inch iPad drew every Browse tile NARROWER than the 6-inch
/// iPhone did, and truncated fifteen labels the phone printed in full.
///
/// The cause is that `GridItem(.adaptive(minimum:))` spends extra width on more
/// columns rather than wider ones, so one spec for every canvas means the
/// biggest screen gets the narrowest tiles.
///
/// **What these tests are worth.** `BrowseGridMetrics.tileWidth` is a model of
/// SwiftUI's layout, not a reading of it, so `theModelMatchesTheMeasuredRasters`
/// below is the load-bearing test: it pins the model to four tiles measured off
/// real simulator screenshots. The rest only mean anything because that one
/// passes. The rendered proof is the iPad raster in the PR.
final class BrowseGridWidth5655Tests: XCTestCase {

    // MARK: Canvases

    /// Content width = screen width − the page's 22 pt horizontal padding, both
    /// sides. Confirmed against the rasters: the NBA tile's leading edge sits at
    /// 22.7 pt on the iPad shot.
    private enum Canvas {
        static let iPhone17: CGFloat = 402 - 44          // 358
        static let iPadPro13Portrait: CGFloat = 1032 - 44 // 988
        /// Landscape is bounded by the page's own `.frame(maxWidth: 1100)`.
        static let iPadPro13Landscape: CGFloat = 1100 - 44 // 1056
        static let iPadPro11Portrait: CGFloat = 834 - 44   // 790
        static let iPadMiniPortrait: CGFloat = 744 - 44    // 700

        /// Every canvas that gets the regular-width treatment.
        static let allRegular: [(String, CGFloat)] = [
            ("iPad Pro 13 portrait", iPadPro13Portrait),
            ("iPad Pro 13 landscape", iPadPro13Landscape),
            ("iPad Pro 11 portrait", iPadPro11Portrait),
            ("iPad mini portrait", iPadMiniPortrait),
        ]
    }

    // MARK: The model is calibrated

    /// The four tiles measured off simulator rasters on 2026-09-12, before any
    /// change: `artifacts-native-020/n132-before-{iphone,ipad}-browse.png`.
    ///
    /// If this fails, every other test in this file is measuring a fiction.
    func testTheModelMatchesTheMeasuredRasters() {
        let cases: [(String, BrowseGridMetrics.Grid, CGFloat, Bool, CGFloat, CGFloat)] = [
            // surface,   grid,      canvas,                    regular, predicted, measured
            ("featured/iPhone", .featured, Canvas.iPhone17,          false, 320, 319),
            ("league/iPhone",   .league,   Canvas.iPhone17,          false, 173, 172),
            ("featured/iPad",   .featured, Canvas.iPadPro13Portrait, false, 238, 236),
            ("league/iPad",     .league,   Canvas.iPadPro13Portrait, false, 155, 153),
        ]
        for (name, grid, canvas, regular, predicted, measured) in cases {
            // The iPad rows pass `regular: false` deliberately — that IS the old
            // behaviour, one spec for every canvas, which is what was measured.
            let modelled = BrowseGridMetrics.tileWidth(grid, availableWidth: canvas, regularWidth: regular)
            XCTAssertEqual(modelled, predicted, accuracy: 0.5, "\(name): model drifted from its documented value")
            XCTAssertEqual(modelled, measured, accuracy: 2.5, "\(name): model no longer matches the raster it was calibrated on")
        }
    }

    // MARK: The defect

    /// The whole of #5655 in one assertion: a big canvas never draws a tile
    /// narrower than a phone does.
    ///
    /// Fails on the shipped code — the iPad's league tile was 155 pt against the
    /// iPhone's 173 pt.
    func testNoRegularCanvasDrawsATileNarrowerThanThePhone() {
        for grid in [BrowseGridMetrics.Grid.featured, .league] {
            let phone = BrowseGridMetrics.tileWidth(grid, availableWidth: Canvas.iPhone17, regularWidth: false)
            for (name, canvas) in Canvas.allRegular {
                let wide = BrowseGridMetrics.tileWidth(grid, availableWidth: canvas, regularWidth: true)
                XCTAssertGreaterThanOrEqual(
                    wide, phone,
                    "\(grid) on \(name): \(wide) pt is narrower than the phone's \(phone) pt — #5655 is back"
                )
            }
        }
    }

    /// The same defect stated the other way round, which is what a reader sees:
    /// the iPad's league row now holds four tiles, and every league group has at
    /// most four leagues, so no row is left half-empty.
    func testTheIPadLeagueRowFitsAWholeGroup() {
        let columns = DiscoverMasonry.columnCount(
            availableWidth: Canvas.iPadPro13Portrait,
            minimumCardWidth: BrowseGridMetrics.minimumTileWidth(.league, regularWidth: true),
            spacing: BrowseGridMetrics.spacing
        )
        XCTAssertEqual(columns, 4, "the largest league group has four leagues; a wider row leaves it sparse")
    }

    // MARK: Nothing on the phone moves

    /// The compact numbers are the ones that shipped. A phone tile that changes
    /// width is a regression, not a fix — #5655 is an iPad bug.
    func testCompactMetricsAreUnchanged() {
        XCTAssertEqual(BrowseGridMetrics.minimumTileWidth(.featured, regularWidth: false), 230)
        XCTAssertEqual(BrowseGridMetrics.minimumTileWidth(.league, regularWidth: false), 150)
        XCTAssertEqual(BrowseGridMetrics.maximumTileWidth, 320)
        XCTAssertEqual(BrowseGridMetrics.spacing, 12)

        XCTAssertEqual(
            BrowseGridMetrics.tileWidth(.featured, availableWidth: Canvas.iPhone17, regularWidth: false),
            320, accuracy: 0.5
        )
        XCTAssertEqual(
            BrowseGridMetrics.tileWidth(.league, availableWidth: Canvas.iPhone17, regularWidth: false),
            173, accuracy: 0.5
        )
    }

    /// A regular canvas must ask for a LARGER minimum than a compact one, in
    /// both grids. This is the clause the fix is made of; without it the rest is
    /// a no-op.
    func testRegularAsksForAWiderMinimumThanCompact() {
        for grid in [BrowseGridMetrics.Grid.featured, .league] {
            XCTAssertGreaterThan(
                BrowseGridMetrics.minimumTileWidth(grid, regularWidth: true),
                BrowseGridMetrics.minimumTileWidth(grid, regularWidth: false),
                "\(grid): a big canvas must not reuse the phone's minimum"
            )
        }
    }

    // MARK: The arithmetic itself

    /// `columnWidth` must respect the cap, or the featured card would span a
    /// whole iPad.
    func testWidthIsCappedAtTheMaximum() {
        let wide = BrowseGridMetrics.tileWidth(.featured, availableWidth: 4000, regularWidth: true)
        XCTAssertLessThanOrEqual(wide, BrowseGridMetrics.maximumTileWidth)
    }

    /// A width that has not resolved yet (0 on the first layout pass) must not
    /// produce a negative or NaN tile.
    func testUnresolvedWidthIsNotNegative() {
        XCTAssertEqual(BrowseGridMetrics.tileWidth(.league, availableWidth: 0, regularWidth: true), 0)
        XCTAssertEqual(DiscoverMasonry.columnWidth(availableWidth: 0), 0)
    }

    /// The model must agree with `columnCount`, which is the product code's own
    /// view of the same grid — n columns and their spacing fill the canvas.
    func testWidthAndCountAgree() {
        for (name, canvas) in Canvas.allRegular {
            for grid in [BrowseGridMetrics.Grid.featured, .league] {
                let minimum = BrowseGridMetrics.minimumTileWidth(grid, regularWidth: true)
                let n = CGFloat(DiscoverMasonry.columnCount(
                    availableWidth: canvas,
                    minimumCardWidth: minimum,
                    spacing: BrowseGridMetrics.spacing
                ))
                let width = BrowseGridMetrics.tileWidth(grid, availableWidth: canvas, regularWidth: true)
                // Either the columns fill the canvas exactly, or they are capped
                // at the maximum and leave slack — never more than the canvas.
                let used = n * width + (n - 1) * BrowseGridMetrics.spacing
                XCTAssertLessThanOrEqual(used, canvas + 0.5, "\(grid) on \(name) overflows its canvas")
                XCTAssertGreaterThanOrEqual(width, minimum - 0.5, "\(grid) on \(name) is under its own minimum")
            }
        }
    }
}
