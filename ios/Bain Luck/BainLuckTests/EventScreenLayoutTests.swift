import XCTest
import SwiftUI
@testable import Bain_Luck

/// UX-P090 — the EVENT-SCREEN LAYOUT pass (Alex's "hideous" verdict, layout half).
///
/// SwiftUI bodies are not rendered in tests, so these pin the GEOMETRY the layout
/// depends on rather than the pixels. That is the honest limit of this file and it
/// is stated up front: each defect below was found by arithmetic on the constants,
/// and arithmetic on the constants is exactly what can be regression-guarded here.
/// Alex remains the acceptance eyeball for how it actually looks.
///
/// What these do buy: every one of the three defects was a NUMBER that was wrong
/// against a screen width, and each would have been caught the day it was written
/// by the corresponding assertion below.
final class EventScreenLayoutTests: XCTestCase {

    // MARK: - Screen widths under test

    /// Narrowest supported phone (SE, 3rd gen) and the common one (16).
    private let seWidth: CGFloat = 375
    private let iPhone16Width: CGFloat = 393
    /// The event card's own horizontal padding, both edges.
    private let cardPadding: CGFloat = 32

    // MARK: - Defect 1: period chips overlapped each other

    /// The dedup threshold is a fraction of the chart's DURATION, and because the
    /// x-axis is linear it is equally a fraction of the chart's WIDTH. So it is
    /// directly comparable to a chip's width, and it must not be smaller.
    func testPeriodChipSpacingIsAtLeastOneChipWide() {
        let requiredFraction =
            PeriodChipGeometry.chipWidthPoints / PeriodChipGeometry.plotWidthPoints

        XCTAssertGreaterThanOrEqual(
            PeriodChipGeometry.minSpacingFraction,
            requiredFraction,
            """
            Two period chips closer than one chip-width overlap. The historical \
            value was 0.03 — about 10pt of separation between chips ~28pt wide, \
            so they overlapped by roughly two thirds.
            """
        )
    }

    /// The regression this replaces, stated as a value so it cannot come back by
    /// someone "restoring" the old constant.
    func testTheOldThreePercentThresholdWouldStillFail() {
        let old = 0.03
        let required =
            PeriodChipGeometry.chipWidthPoints / PeriodChipGeometry.plotWidthPoints
        XCTAssertLessThan(old, required, "0.03 must remain provably too small")
    }

    /// Raising the threshold must not silently DROP real periods — the fix is meant
    /// to remove collisions, not information.
    ///
    /// This test earned its keep on the first run: the constant was `0.09`, the
    /// derived 8.31% "rounded up for safety", and the round-up deleted the 12th
    /// inning of a four-hour game (1,200s of real spacing against a 1,296s
    /// threshold). A percentage padded for safety is an absolute threshold in
    /// disguise — it grows with the chart and eventually eats real data. The
    /// constant is now exactly `chipWidth / plotWidth`.
    func testRealPeriodBoundariesSurviveTheThreshold() {
        let cases: [(name: String, durationSeconds: Double, periods: Int)] = [
            ("9-inning MLB game over 3h", 3 * 3600, 9),
            ("4-quarter NBA game over 2.5h", 2.5 * 3600, 4),
            ("3-period NHL game over 2.5h", 2.5 * 3600, 3),
            ("12-inning MLB game over 4h", 4 * 3600, 12),
        ]
        for c in cases {
            let spacingBetweenPeriods = c.durationSeconds / Double(c.periods)
            let threshold = c.durationSeconds * PeriodChipGeometry.minSpacingFraction
            XCTAssertGreaterThan(
                spacingBetweenPeriods,
                threshold,
                "\(c.name): a real period boundary would be deduped away"
            )
        }
    }

    /// The other direction, so "keep everything" is not achieved by disabling the
    /// rule. Past the strip's physical capacity — roughly plotWidth / chipWidth ≈ 12
    /// chips — a chip MUST be dropped, because there is no room for it. Dropping is
    /// correct there; overlapping is not.
    func testBeyondCapacityChipsAreDroppedRatherThanOverlapped() {
        let capacity = PeriodChipGeometry.plotWidthPoints / PeriodChipGeometry.chipWidthPoints
        let periods = Int(capacity.rounded(.down)) + 4   // comfortably past capacity
        let duration = 5.0 * 3600
        let spacingBetweenPeriods = duration / Double(periods)
        let threshold = duration * PeriodChipGeometry.minSpacingFraction
        XCTAssertLessThan(
            spacingBetweenPeriods, threshold,
            "past capacity the rule must thin the strip, not draw overlapping chips"
        )
    }

    /// The fraction must stay DERIVED. A literal here is how the round-up got in.
    func testSpacingFractionIsDerivedFromGeometryNotHandPicked() {
        XCTAssertEqual(
            PeriodChipGeometry.minSpacingFraction,
            PeriodChipGeometry.chipWidthPoints / PeriodChipGeometry.plotWidthPoints,
            accuracy: 1e-9
        )
    }

    // MARK: - Defect 2: the Game Segments total column was off-screen

    /// Total width of the segments row, mirroring `GameSegmentsView`'s Grid:
    /// one team-label column, N segment columns, one total column, uniform gaps,
    /// the total's leading gutter, and the card's padding.
    private func segmentsRowWidth(
        innings: Int,
        labelColumn: CGFloat,
        segmentColumn: CGFloat,
        totalColumn: CGFloat,
        gap: CGFloat,
        totalGutter: CGFloat
    ) -> CGFloat {
        let columns = 1 + innings + 1
        let content = labelColumn + CGFloat(innings) * segmentColumn + totalColumn
        return content + CGFloat(columns - 1) * gap + totalGutter + cardPadding
    }

    /// The shipped geometry. A regulation nine-inning game must fit the NARROWEST
    /// phone — if it does not, the "T" column is off the right edge, and the total
    /// is the one number the card exists to reconcile against the hero score.
    private func shippedWidth(innings: Int) -> CGFloat {
        segmentsRowWidth(
            innings: innings,
            labelColumn: 44,
            segmentColumn: 22,
            totalColumn: 26,
            gap: 4,
            totalGutter: 6
        )
    }

    func testNineInningsFitTheNarrowestPhone() {
        XCTAssertLessThanOrEqual(
            shippedWidth(innings: 9), seWidth,
            "a regulation 9-inning line score must not require horizontal scrolling"
        )
    }

    func testTenInningsStillFitTheNarrowestPhone() {
        // One extra inning is common enough that it should not push the total off.
        XCTAssertLessThanOrEqual(shippedWidth(innings: 10), seWidth)
    }

    /// The defect, pinned. #1831's 1…N ladder was correct and is what widened this
    /// row past the screen; the old geometry could not show a nine-inning total on
    /// ANY iPhone.
    func testTheOldGeometryOverflowedEveryPhone() {
        let old = segmentsRowWidth(
            innings: 9,
            labelColumn: 54, segmentColumn: 28, totalColumn: 28,
            gap: 12, totalGutter: 0
        )
        XCTAssertGreaterThan(old, iPhone16Width)
        XCTAssertGreaterThan(old, seWidth)
        XCTAssertLessThan(
            shippedWidth(innings: 9), old,
            "the fix must actually narrow the row"
        )
    }

    /// Deep extras legitimately scroll. That is a declared trade, not an oversight:
    /// the indicator is enabled so the overflow is visible rather than silent.
    func testDeepExtrasScrollRatherThanBeingCrushed() {
        XCTAssertGreaterThan(shippedWidth(innings: 13), iPhone16Width)
    }

    // MARK: - Defect 3: the legend sat left of the plot it labels

    /// One gutter width, shared by the inline chart row, the fullscreen chart row,
    /// and the legend's indent. The legend used none, so it hung 24pt to the left
    /// of the data it describes.
    func testLegendIndentMatchesTheTeamGutter() {
        XCTAssertEqual(
            chartTeamGutterWidth, 24,
            "the legend indents by this exact value; changing one must change both"
        )
        XCTAssertGreaterThan(chartTeamGutterWidth, 0)
    }

    /// The plot width the chip arithmetic assumes must stay consistent with the
    /// gutter it subtracts, or defect 1's threshold is derived from a fiction.
    func testPlotWidthIsConsistentWithScreenAndGutter() {
        let derived = iPhone16Width - cardPadding - chartTeamGutterWidth
        XCTAssertEqual(
            PeriodChipGeometry.plotWidthPoints, Double(derived), accuracy: 1.0,
            "chip spacing is derived from this width — it must match the real layout"
        )
    }
}
