import XCTest
@testable import Bain_Luck

/// #3269 — the score chart under the MATCH chart is the SAME chart's second half,
/// and #3237's two corrections were only ever applied to the top one.
///
/// `EventDetailView` hands both charts one `forcedDomain` so their times line up.
/// Until this fix the lower chart:
///
///  * drew its period chips with `proxy.position(forX:)` — a PLOT-relative x —
///    inside a `GeometryReader` spanning the WHOLE chart, so every chip sat a
///    y-gutter's width left of the period it marks, exactly the defect #3237
///    measured and fixed above it;
///  * chose its own 15/30/60-minute ticks under a comment claiming it matched
///    `OddsChartView`, which stopped being true when the stride ladder landed
///    (#3238).
///
/// The placement is now the shared `PeriodChipGeometry`, and the axis is the
/// shared `OddsChartView.xAxisPlan`. What this file pins is the one thing sharing
/// them could have got wrong: the two strips are drawn at different type sizes,
/// so one width model would misplace one of them.
final class ScoreDifferentialChartChipTests: XCTestCase {

    private func request(_ key: Int, _ label: String, _ rawX: Double)
        -> PeriodChipGeometry.ChipRequest {
        PeriodChipGeometry.ChipRequest(key: key, label: label, rawX: rawX)
    }

    /// The score chart's chips are 8pt semibold with 3pt padding against the
    /// MATCH chart's 10pt bold with 4pt. Measuring them with the larger model
    /// would drop chips that had room — the mirror of the defect the placement
    /// rule exists to prevent.
    func testScoreStripIsNarrowerThanTheMatchStripForTheSameLabel() {
        for label in ["1st", "10", "Final", "OT"] {
            XCTAssertLessThan(
                PeriodChipGeometry.chipWidth(for: label, metrics: .score),
                PeriodChipGeometry.chipWidth(for: label, metrics: .match),
                "\(label): the smaller strip must measure smaller")
        }
    }

    /// …and it is the ink itself now, not an upper bound on it.
    ///
    /// **#3817.** This used to assert `>= 26pt` for "Final" on the strength of
    /// "8pt semibold renders at roughly 4pt per glyph, and the model charges 5" —
    /// i.e. it pinned the SLACK in the guess. Measured, the chip draws 25.63pt, so
    /// the old floor was a fifth of a chip of ink that does not exist, and
    /// `place` was spending it. `PeriodChipWidthTests` re-renders every label in
    /// the vocabulary against both strips' fonts; what is left here is the
    /// relation between the two strips, which is this file's subject.
    func testScoreStripIsRealInkAndStillSmallerThanTheMatchStrip() {
        XCTAssertLessThanOrEqual(
            PeriodChipGeometry.chipWidth(for: "Final", metrics: .score),
            PeriodChipGeometry.chipWidth(for: "Final", metrics: .match))
        XCTAssertGreaterThan(
            PeriodChipGeometry.chipWidth(for: "Final", metrics: .score),
            PeriodChipGeometry.ChipMetrics.score.horizontalPadding * 2,
            "a chip is its padding plus real glyphs")
    }

    /// The concrete payoff: on a strip too crowded for the large type, the small
    /// type still carries every period.
    ///
    /// **#3817 rewrote the fixture, because the old one stopped being crowded.**
    /// It was a single PAIR 23pt apart, asserting the MATCH strip had to drop one
    /// of the two. Two chips in a 293pt plot are never out of room — the old
    /// policy dropped one because it would not move them apart, and `place`
    /// moves them now. So the difference between the two strips has to be shown
    /// where it is real: a full ten-period strip at 20pt spacing, which the 8pt
    /// type clears outright and the 10pt type cannot.
    func testTheSmallerStripCarriesACrowdedStripTheLargerOneCannot() {
        let labels = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "Final"]
        let requests = labels.enumerated().map { index, label in
            request(index, label, 40 + 20 * Double(index))
        }

        let score = PeriodChipGeometry.place(requests, plotWidth: 293, metrics: .score)
        let match = PeriodChipGeometry.place(requests, plotWidth: 293, metrics: .match)

        XCTAssertEqual(
            score.count, labels.count,
            "20pt clears an 8pt-semibold chip, so the small strip loses nothing")
        XCTAssertLessThan(
            match.count, score.count,
            "…while the 10pt-bold strip cannot seat them all near their own boundaries")
    }

    /// The clamp #3237 added applies to this strip too: a period at x = 0 is the
    /// first period of the game, and its chip may not hang over the y-axis label.
    func testFirstChipStaysInsideThePlotOnTheScoreStrip() {
        let placements = PeriodChipGeometry.place(
            [request(0, "1st", 0)], plotWidth: 293, metrics: .score)
        let half = PeriodChipGeometry.chipWidth(for: "1st", metrics: .score) / 2
        XCTAssertEqual(placements.count, 1)
        XCTAssertGreaterThanOrEqual(placements[0].centerX - half, 0)
    }

    /// And at the other edge, where "Final" is the chip that overhung.
    func testLastChipStaysInsideThePlotOnTheScoreStrip() {
        let plotWidth: Double = 293
        let placements = PeriodChipGeometry.place(
            [request(0, "Final", plotWidth)], plotWidth: plotWidth, metrics: .score)
        let half = PeriodChipGeometry.chipWidth(for: "Final", metrics: .score) / 2
        XCTAssertEqual(placements.count, 1)
        XCTAssertLessThanOrEqual(placements[0].centerX + half, plotWidth)
    }

    /// The existing MATCH-chart placements must be untouched by the metrics
    /// parameter — it defaults to what they already used.
    func testDefaultMetricsAreTheMatchStripsSoNothingAboveMoved() {
        XCTAssertEqual(
            PeriodChipGeometry.chipWidth(for: "Final"),
            PeriodChipGeometry.chipWidth(for: "Final", metrics: .match))
        XCTAssertEqual(
            PeriodChipGeometry.clampedCenterX(rawX: 0, label: "1st", plotWidth: 337),
            PeriodChipGeometry.clampedCenterX(
                rawX: 0, label: "1st", plotWidth: 337, metrics: .match))
    }
}
