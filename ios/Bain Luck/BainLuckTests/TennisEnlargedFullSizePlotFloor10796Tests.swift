import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10796 — **a finished tennis match opened full size at an accessibility
/// text size keeps a plot as tall as the inline chart's, and every other
/// full-size chart is laid out as before.**
///
/// Design's mounted review of 3d52 (2026-10-21): at AX1 on a 375×667 phone the
/// full-size plot was 319×30 at (40, 589) on all three matches, against an
/// inline plot of 287×292, because the enlarged tennis panel took the height
/// first. The 26d8 control was the same 30pt; default Large was 319×338.
///
/// These tests pin the gate and the floor only. Whether the drawn plot is the
/// floor's height, that the cover scrolls, and that a held reading survives
/// lift, re-hold and Done are frames from the app, which this file does not
/// replace.
@MainActor
final class TennisEnlargedFullSizePlotFloor10796Tests: XCTestCase {

    private let phone = OddsChartView.phoneChartHeight

    private func plotFloor(tennis: Bool = true, finished: Bool = true,
                           _ size: DynamicTypeSize, inline: CGFloat? = nil) -> CGFloat? {
        OddsChartView.fullscreenEnlargedPlotFloor(tennisReading: tennis, finished: finished,
                                                  textSize: size, inlinePlotHeight: inline ?? phone)
    }

    func testEveryAccessibilitySizeGivesAFinishedMatchTheInlinePlotHeight() {
        let enlarged = DynamicTypeSize.allCases.filter(\.isAccessibilitySize)
        XCTAssertEqual(enlarged.count, 5, "AX1–AX5")
        for size in enlarged {
            XCTAssertEqual(plotFloor(size), phone, "\(size)")
        }
    }

    func testTheFloorFollowsTheInlineHeightItIsGiven() {
        // iPad's inline heights (`chartHeight`, landscape and portrait).
        XCTAssertEqual(plotFloor(.accessibility3, inline: 320), 320)
        XCTAssertEqual(plotFloor(.accessibility3, inline: 380), 380)
    }

    /// Default Large drew a 319×338 plot and keeps its accepted layout: no
    /// floor, no scroll, panel above the plot — at every non-accessibility size.
    func testNoNonAccessibilitySizeChangesTheFullSizeLayout() {
        let standard = DynamicTypeSize.allCases.filter { !$0.isAccessibilitySize }
        XCTAssertTrue(standard.contains(.large))
        XCTAssertTrue(standard.contains(.xxxLarge))
        for size in standard {
            XCTAssertNil(plotFloor(size), "\(size)")
        }
    }

    func testOtherSportsKeepTheirFullSizeLayoutAtEveryTextSize() {
        for size in DynamicTypeSize.allCases {
            XCTAssertNil(plotFloor(tennis: false, size), "\(size)")
        }
    }

    /// The brief's scope is the finished reader Design reviewed. A live match
    /// is outside it until its own frames exist; widening is one argument.
    func testALiveMatchIsOutsideThisCorrection() {
        for size in DynamicTypeSize.allCases {
            XCTAssertNil(plotFloor(finished: false, size), "\(size)")
        }
    }
}
