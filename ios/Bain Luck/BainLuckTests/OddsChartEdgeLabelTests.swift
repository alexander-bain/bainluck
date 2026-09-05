import SwiftUI
import XCTest
@testable import Bain_Luck

/// #3237 — the win-probability chart's chrome must stop colliding with its own
/// frame at the two edges.
///
/// Both defects were photographed on master `33778417` (iPhone 17 simulator,
/// 2026-09-05) and both are geometry, not data:
///
///  * the last time label truncated to "S…" on 15303442's axis
///    (`Fri 11 PM · Sat 12 AM · S…`), because every label was centred on its
///    tick and the last tick sits on the plot's trailing edge;
///  * the first period chip was drawn over the "100%" axis label on 15302915,
///    because a chip centred at `x = 0` hangs half its width outside the plot.
///
/// Both helpers are pure, so the rule is pinned here rather than in a screenshot
/// — a screenshot proves today's chart and a test proves every chart.
final class OddsChartEdgeLabelTests: XCTestCase {

    // MARK: - x-axis label anchors

    /// The defect itself: the LAST label must hang inward (trailing edge on the
    /// tick) so nothing of it falls outside the plot to be truncated.
    func testLastLabelAnchorsTrailingSoItCannotTruncate() {
        XCTAssertEqual(OddsChartView.xAxisLabelAnchor(index: 2, count: 3), .topTrailing)
        XCTAssertEqual(OddsChartView.xAxisLabelAnchor(index: 5, count: 6), .topTrailing)
    }

    /// The mirror case at the other end — a first label centred on tick 0 spills
    /// into the y-axis gutter where "0%" lives.
    func testFirstLabelAnchorsLeading() {
        XCTAssertEqual(OddsChartView.xAxisLabelAnchor(index: 0, count: 3), .topLeading)
    }

    /// Everything between the ends keeps centring — the fix is about the two
    /// edges only, and a middle label that suddenly hung left would read as a
    /// misaligned axis.
    func testInteriorLabelsStayCentred() {
        for index in 1..<5 {
            XCTAssertEqual(
                OddsChartView.xAxisLabelAnchor(index: index, count: 6), .top,
                "interior tick \(index) of 6 must stay centred")
        }
    }

    /// A one-tick axis is both ends at once; centring is the least wrong answer.
    /// `count = 0` is unreachable from Swift Charts but must not trap.
    func testDegenerateAxisCentres() {
        XCTAssertEqual(OddsChartView.xAxisLabelAnchor(index: 0, count: 1), .top)
        XCTAssertEqual(OddsChartView.xAxisLabelAnchor(index: 0, count: 0), .top)
    }

    // MARK: - period chip clamp

    /// `chipWidthPoints` claims to be a CONSERVATIVE bound on a two-character
    /// chip, and the spacing rule is derived from that claim. The per-label width
    /// must stay under it on its own case, or the two disagree about the same
    /// chip and one of them is lying.
    func testTwoCharacterChipStaysUnderTheConservativeSpacingBound() {
        XCTAssertLessThanOrEqual(PeriodChipGeometry.chipWidth(for: "10"),
                                 PeriodChipGeometry.chipWidthPoints)
    }

    /// "Final" is the chip the walk-off chart actually drew, and it is wider than
    /// any inning number — the reason a per-label width exists at all.
    func testFinalIsWiderThanAnyInningChip() {
        XCTAssertGreaterThan(PeriodChipGeometry.chipWidth(for: "Final"),
                             PeriodChipGeometry.chipWidth(for: "10"))
    }

    /// The photographed defect: a marker at the plot's leading edge must not
    /// leave the chip hanging over the gutter.
    func testChipAtTheLeadingEdgeIsPushedFullyInside() {
        let x = PeriodChipGeometry.clampedCenterX(rawX: 0, label: "1st", plotWidth: 337)
        XCTAssertEqual(x, PeriodChipGeometry.chipWidth(for: "1st") / 2, accuracy: 0.001)
        XCTAssertGreaterThanOrEqual(x - PeriodChipGeometry.chipWidth(for: "1st") / 2, 0)
    }

    /// Same rule at the other end, with the widest chip a game produces.
    func testChipAtTheTrailingEdgeIsPushedFullyInside() {
        let plotWidth = 337.0
        let x = PeriodChipGeometry.clampedCenterX(
            rawX: plotWidth, label: "Final", plotWidth: plotWidth)
        let half = PeriodChipGeometry.chipWidth(for: "Final") / 2
        XCTAssertEqual(x, plotWidth - half, accuracy: 0.001)
        XCTAssertLessThanOrEqual(x + half, plotWidth)
    }

    /// A chip with room on both sides is not moved at all — the clamp must not
    /// become a general nudge that pulls every chip off its own gridline.
    func testChipWithRoomIsNotMoved() {
        XCTAssertEqual(
            PeriodChipGeometry.clampedCenterX(rawX: 170, label: "4th", plotWidth: 337),
            170, accuracy: 0.001)
    }

    /// Every chip a game can produce stays inside the plot, swept across the
    /// whole width — the property, not three hand-picked points.
    func testNoChipEverOverhangsThePlot() {
        let plotWidth = 337.0
        for label in ["1st", "2nd", "10", "OT", "Final", "Half"] {
            let half = PeriodChipGeometry.chipWidth(for: label) / 2
            for step in 0...40 {
                let rawX = plotWidth * Double(step) / 40.0
                let x = PeriodChipGeometry.clampedCenterX(
                    rawX: rawX, label: label, plotWidth: plotWidth)
                XCTAssertGreaterThanOrEqual(
                    x - half, -0.001, "\(label) overhangs the leading edge at x=\(rawX)")
                XCTAssertLessThanOrEqual(
                    x + half, plotWidth + 0.001,
                    "\(label) overhangs the trailing edge at x=\(rawX)")
            }
        }
    }

    /// A plot narrower than the chip has no non-overlapping answer; it must
    /// centre rather than return a negative x or trap.
    func testPlotTooNarrowForTheChipCentres() {
        XCTAssertEqual(
            PeriodChipGeometry.clampedCenterX(rawX: 0, label: "Final", plotWidth: 30),
            15, accuracy: 0.001)
    }

    // MARK: - placement (clamp + collision)

    private func request(_ key: Int, _ label: String, _ rawX: Double)
        -> PeriodChipGeometry.ChipRequest {
        PeriodChipGeometry.ChipRequest(key: key, label: label, rawX: rawX)
    }

    /// THE REGRESSION THE CLAMP CREATED, and the reason `place` exists.
    ///
    /// The first cut of #3237 clamped each chip independently. On 15302915 — the
    /// 10-inning walk-off — that pulled "Final" off the trailing edge straight
    /// into "9th", and the strip drew "9Final". Photographed before this test was
    /// written; pinned here so a later simplification cannot bring it back.
    func testClampedTerminalChipDoesNotLandOnItsNeighbour() {
        let plotWidth = 337.0
        let labels = [0: "8th", 1: "9th", 2: "Final"]
        let placements = PeriodChipGeometry.place(
            [request(0, "8th", 250), request(1, "9th", 300), request(2, "Final", 335)],
            plotWidth: plotWidth)

        XCTAssertEqual(placements.map(\.key), [0, 2],
                       "the earlier chip of the colliding pair is the one dropped")
        assertNoOverlaps(placements, labels: labels, plotWidth: plotWidth)
    }

    /// The general property: whatever comes in, nothing drawn overlaps anything
    /// else drawn and nothing hangs outside the plot. Swept over a strip that
    /// bunches towards the trailing edge, which is where the defect lives.
    func testPlacementNeverOverlapsAndNeverOverhangs() {
        let plotWidth = 337.0
        let labels = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "Final"]
        let byKey = Dictionary(uniqueKeysWithValues: labels.enumerated().map { ($0, $1) })
        for squeeze in [1.0, 0.6, 0.3, 0.12] {
            let requests = labels.enumerated().map { index, label in
                request(index, label,
                        plotWidth * (1 - squeeze)
                            + plotWidth * squeeze * Double(index) / Double(labels.count - 1))
            }
            let placements = PeriodChipGeometry.place(requests, plotWidth: plotWidth)
            XCTAssertFalse(placements.isEmpty, "squeeze \(squeeze) dropped every chip")
            assertNoOverlaps(placements, labels: byKey, plotWidth: plotWidth)
        }
    }

    /// A well-spread strip must lose nothing and move nothing — the collision
    /// pass is a last resort, not a second thinning of a chart already fine.
    func testWellSpacedChipsAreAllKeptAndUnmoved() {
        let placements = PeriodChipGeometry.place(
            [request(0, "1st", 40), request(1, "2nd", 140), request(2, "3rd", 240)],
            plotWidth: 337)
        XCTAssertEqual(placements.map(\.key), [0, 1, 2])
        XCTAssertEqual(placements.map(\.centerX), [40, 140, 240])
    }

    /// A marker whose position the chart proxy cannot resolve never becomes a
    /// request, so placement must not assume a dense key range.
    func testSparseKeysSurvive() {
        let placements = PeriodChipGeometry.place(
            [request(3, "4th", 60), request(7, "8th", 260)], plotWidth: 337)
        XCTAssertEqual(placements.map(\.key), [3, 7])
    }

    func testEmptyPlacementIsEmpty() {
        XCTAssertTrue(PeriodChipGeometry.place([], plotWidth: 337).isEmpty)
    }

    private func assertNoOverlaps(
        _ placements: [PeriodChipGeometry.ChipPlacement],
        labels: [Int: String],
        plotWidth: Double,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        var previousTrailing = -Double.infinity
        for placement in placements {
            let label = labels[placement.key] ?? ""
            let half = PeriodChipGeometry.chipWidth(for: label) / 2
            XCTAssertGreaterThanOrEqual(
                placement.centerX - half, previousTrailing - 0.001,
                "\(label) overlaps the chip before it", file: file, line: line)
            XCTAssertGreaterThanOrEqual(
                placement.centerX - half, -0.001,
                "\(label) hangs off the leading edge", file: file, line: line)
            XCTAssertLessThanOrEqual(
                placement.centerX + half, plotWidth + 0.001,
                "\(label) hangs off the trailing edge", file: file, line: line)
            previousTrailing = placement.centerX + half
        }
    }
}
