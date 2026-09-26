import XCTest
import SwiftUI
@testable import Bain_Luck
#if os(iOS)
import UIKit
#endif

/// #925's installed-phone clause, the half the fast suite can reach.
///
/// Alex's build-20 recording (2026-09-24, Dallas–Washington 14781697): a
/// press-and-drag on the game chart drew a crosshair for a moment, then the page
/// moved under his thumb; the readout the scrub rewrites sat below the chart,
/// under the tab bar; and once scrolled into view it broke both names mid-word
/// ("Cow-/boys", "Comman-/ders").
///
/// The finger itself is driven by
/// `BainLuckUITests/ASidewaysDragOnAGameChartHoldsThePage925Tests` (page travel
/// under a drifting sideways drag, and the vertical-swipe control). This file
/// pins the decisions that make that pass: which touches are a scrub, that a
/// scrub holds the scroll still and gives it back, where the readout lives, and
/// that no name in it can hyphenate.
final class AGameChartScrubHoldsThePage925Tests: XCTestCase {

    // MARK: - Which touches are a scrub

    /// THE DEFECT'S GESTURE. A held press owns the touch; the thumb's vertical
    /// drift afterwards must not hand it back to the page.
    func testAHeldPressScrubsEvenWhenTheThumbThenDriftsVertically() {
        var scrub = ChartScrubState()
        scrub.hold()
        XCTAssertTrue(scrub.scrubs)
        scrub.change(width: 4, height: 40)
        XCTAssertTrue(scrub.scrubs, "a held scrub was handed back to the scroll by vertical drift")
    }

    func testASidewaysDragScrubsWithoutAHold() {
        var scrub = ChartScrubState()
        scrub.change(width: 30, height: 9)
        XCTAssertTrue(scrub.scrubs)
    }

    /// The control: a vertical swipe on the chart is the page's.
    func testAVerticalSwipeIsNeverAScrub() {
        var scrub = ChartScrubState()
        scrub.change(width: 3, height: 30)
        XCTAssertFalse(scrub.scrubs)
    }

    /// Unlike the futures chart's `tracks`, an undecided touch does NOT scrub
    /// the game chart — its readout is a whole row that would flicker at the
    /// start of every scroll begun on the chart.
    func testAnUndecidedTouchDoesNotScrubTheGameChart() {
        var scrub = ChartScrubState()
        scrub.change(width: 2, height: 3)
        XCTAssertFalse(scrub.scrubs)
        XCTAssertTrue(scrub.tracks, "the futures chart's press-and-hold inspect must be unchanged")
    }

    /// A hold that outlived its gesture would make the NEXT vertical swipe a scrub.
    func testTheHoldIsClearedWithTheGesture() {
        var scrub = ChartScrubState()
        scrub.hold()
        scrub.end()
        XCTAssertFalse(scrub.held)
        scrub.change(width: 2, height: 30)
        XCTAssertFalse(scrub.scrubs)
    }

    // MARK: - A finger past either end reads the end, not nothing

    func testAFingerPastEitherEndOfThePlotClampsToIt() {
        let plot = CGRect(x: 40, y: 0, width: 300, height: 200)
        XCTAssertEqual(OddsChartView.clampedPlotX(10, plotFrame: plot), 0)
        XCTAssertEqual(OddsChartView.clampedPlotX(400, plotFrame: plot), 300)
        XCTAssertEqual(OddsChartView.clampedPlotX(190, plotFrame: plot), 150)
    }

    // MARK: - The page holds still while a scrub owns the touch, and gets it back

    #if os(iOS)
    private func rig(scrubs: @escaping () -> Bool) -> (UIScrollView, UIView, ChartScrubSurface.Coordinator) {
        let scroll = UIScrollView()
        let host = UIView()
        let surface = UIView()
        scroll.addSubview(host)
        host.addSubview(surface)
        let coordinator = ChartScrubSurface.Coordinator(
            onChange: { _, _ in }, onHold: nil, holdsTheScrollStill: scrubs, onEnd: {})
        return (scroll, surface, coordinator)
    }

    func testAScrubFreezesTheEnclosingScrollAndReleasesIt() {
        var scrubbing = true
        let (scroll, surface, coordinator) = rig { scrubbing }
        XCTAssertTrue(ChartScrubSurface.Coordinator.enclosingScrollView(of: surface) === scroll)

        coordinator.syncTheScroll(from: surface)
        XCTAssertFalse(scroll.isScrollEnabled, "the page kept scrolling under a scrub")

        scrubbing = false
        coordinator.syncTheScroll(from: surface)
        XCTAssertTrue(scroll.isScrollEnabled, "the page was left frozen after the scrub let go")
    }

    func testTheGestureEndAlwaysGivesTheScrollBack() {
        let (scroll, surface, coordinator) = rig { true }
        coordinator.syncTheScroll(from: surface)
        coordinator.releaseTheScroll()
        XCTAssertTrue(scroll.isScrollEnabled)
    }

    /// Restored to what it WAS, never assumed `true`.
    func testReleaseRestoresAScrollThatWasAlreadyDisabled() {
        let (scroll, surface, coordinator) = rig { true }
        scroll.isScrollEnabled = false
        coordinator.syncTheScroll(from: surface)
        coordinator.releaseTheScroll()
        XCTAssertFalse(scroll.isScrollEnabled)
    }

    /// The futures chart never asks, so #6705's simultaneous scroll is untouched.
    func testASurfaceThatNeverScrubsNeverFreezes() {
        let (scroll, surface, coordinator) = rig { false }
        coordinator.syncTheScroll(from: surface)
        XCTAssertTrue(scroll.isScrollEnabled)
    }
    #endif

    // MARK: - Wiring (source scans; the behaviour above is worthless unasked)

    func testTheGameChartScrubsOnTheSurfaceWithAHoldAndFreezesOnScrubs() throws {
        let chart = try code(at: "Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("holdToScrub: ChartScrubSurface.gameChartHold"),
                      "the game chart's surface must install the hold recognizer")
        XCTAssertTrue(chart.contains("holdsTheScrollStill: { scrub.scrubs }"),
                      "the freeze must follow the game chart's scrub decision")
        XCTAssertTrue(chart.contains("scrub.hold()"), "a matured hold must be recorded as one")
        XCTAssertTrue(chart.contains("guard scrub.scrubs else"),
                      "the selection must be gated on the scrub decision, not written beside it")
        XCTAssertTrue(chart.contains("scrub.end()"))

        // `chartXSelection` lost the touch to the scroll: it may survive only
        // on the Mac, inside its own `#if os(macOS)` block.
        let parts = chart.components(separatedBy: ".chartXSelection(")
        XCTAssertEqual(parts.count, 2, "exactly one chartXSelection, the Mac's")
        let before = parts[0]
        let lastMac = before.range(of: "#if os(macOS)", options: .backwards)
        let lastEnd = before.range(of: "#endif", options: .backwards)
        XCTAssertNotNil(lastMac, "chartXSelection is outside a macOS block — the iPhone uses it again")
        if let lastMac, let lastEnd {
            XCTAssertTrue(lastMac.lowerBound > lastEnd.lowerBound,
                          "chartXSelection is outside a macOS block — the iPhone uses it again")
        }
    }

    /// The raster switch must default ON: off, every phone loses the scrub while
    /// every render test (which turns it off anyway) stays green.
    func testTheAppInstallsTheSurfaceUnlessARasterSaysOtherwise() throws {
        XCTAssertTrue(EnvironmentValues().chartScrubSurfaces)
        let chart = try code(at: "Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("if scrubSurfaces {"))
        let app = try FileManager.default.subpathsOfDirectory(atPath: Self.appRoot.path)
            .filter { $0.hasSuffix(".swift") }
            .filter { try String(contentsOf: Self.appRoot.appendingPathComponent($0), encoding: .utf8)
                .contains("chartScrubSurfaces, false") }
        XCTAssertEqual(app, [], "only the test raster helper may turn the chart's touch surface off")
    }

    func testTheSurfaceInstallsTheHoldAndSyncsTheScrollFromBothRecognizers() throws {
        let surface = try code(at: "Bain Luck/Components/ChartScrubSurface.swift")
        XCTAssertTrue(surface.contains("UILongPressGestureRecognizer"))
        XCTAssertTrue(surface.contains("hold.minimumPressDuration = holdToScrub"))
        XCTAssertTrue(surface.contains("hold.delegate = context.coordinator"),
                      "without the delegate the hold cannot share the touch with the pan")
        XCTAssertEqual(surface.components(separatedBy: "syncTheScroll(from: view)").count - 1, 2,
                       "both the pan and the hold must sync the freeze")
        XCTAssertTrue(surface.contains("coordinator.releaseTheScroll()"),
                      "a page popped mid-scrub must not keep a frozen scroll view")
        #if os(iOS)
        XCTAssertGreaterThanOrEqual(ChartScrubSurface.gameChartHold, 0.15)
        XCTAssertLessThanOrEqual(ChartScrubSurface.gameChartHold, 0.5)
        #endif
    }

    /// The readout lives above the plot, and the page no longer draws its own
    /// copy below the chart.
    func testTheReadoutIsDrawnAboveThePlotNotBelowTheChart() throws {
        let chart = try code(at: "Bain Luck/Components/OddsChartView.swift")
        guard let readout = chart.range(of: "if let readout { readout.showing(selectedPlayPoint) }"),
              let plotRow = chart.range(of: "ChartGutter.run(chartHeight: chartHeight, verticalPadding: 8)") else {
            return XCTFail("the chart no longer places its readout")
        }
        XCTAssertTrue(readout.lowerBound < plotRow.lowerBound, "the readout is not above the plot")

        let page = try code(at: "Bain Luck/Views/EventDetailView.swift")
        XCTAssertTrue(page.contains("readout: (isLive || isFinished)"),
                      "the page must hand its readout to the chart")
        XCTAssertEqual(page.components(separatedBy: "GamePlayCardView(").count - 1, 1,
                       "a second GamePlayCardView on the page is the old one below the chart")
    }

    /// No arrangement may wrap inside a name; only the last may shrink.
    func testNoNameInTheReadoutCanBreakMidWord() throws {
        let card = try code(at: "Bain Luck/Components/GamePlayCardView.swift")
        XCTAssertTrue(card.contains(".fixedSize(horizontal: !shrinks, vertical: false)"),
                      "a name run that is not fixed-size can be hyphenated by a squeezed row")
        XCTAssertTrue(card.contains(".minimumScaleFactor(shrinks ? 0.5 : 1)"))
        XCTAssertEqual(card.components(separatedBy: "shrinks: true").count - 1, 2,
                       "the last arrangement shrinks BOTH sides; no other one does")
        XCTAssertEqual(card.components(separatedBy: "ViewThatFits(in: .horizontal)").count - 1, 2,
                       "the state row and the probability row each re-stack instead of wrapping")
        XCTAssertTrue(card.contains(#"Text(verbatim: "X\nX")"#) && card.contains(".hidden()"),
                      """
                      the detail row must reserve two lines: it sits above the plot, and a row \
                      that grows on a scoring play moves the plot under the scrubbing finger \
                      (measured 14pt at 375pt)
                      """)
        XCTAssertFalse(card.contains("Text(homeShort)"),
                       "the old bare name Text — the one that hyphenated — is back")
    }

    // MARK: - Helpers

    private static var appRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
    }

    private func code(at relative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let source = try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
        let stripped = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertTrue(stripped.contains("struct "), "comment strip left nothing in \(relative)")
        return stripped
    }
}
