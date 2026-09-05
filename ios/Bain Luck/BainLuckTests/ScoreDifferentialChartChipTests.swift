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

    /// …but still an UPPER bound on what is drawn: 8pt semibold renders at
    /// roughly 4pt per glyph, and the model charges 5.
    func testScoreStripStaysAnUpperBoundOnItsOwnInk() {
        // "Final" at 8pt semibold measures ~20pt of glyphs + 6pt of padding.
        XCTAssertGreaterThanOrEqual(
            PeriodChipGeometry.chipWidth(for: "Final", metrics: .score), 26)
        XCTAssertLessThanOrEqual(
            PeriodChipGeometry.chipWidth(for: "Final", metrics: .score),
            PeriodChipGeometry.chipWidth(for: "Final", metrics: .match))
    }

    /// The concrete payoff: a pair of periods close enough that the MATCH strip
    /// must drop one still fits on the score strip, and both are kept.
    func testTheSmallerStripKeepsAPairTheLargerOneHasToDrop() {
        // 23pt apart: inside a 10pt-bold "3rd" (26pt), outside an 8pt-semibold
        // one (21pt).
        let requests = [request(0, "3rd", 100), request(1, "4th", 123)]

        XCTAssertEqual(
            PeriodChipGeometry.place(requests, plotWidth: 293, metrics: .match).count, 1,
            "23pt apart is inside a 10pt-bold chip's width — one must go")
        XCTAssertEqual(
            PeriodChipGeometry.place(requests, plotWidth: 293, metrics: .score).count, 2,
            "…and outside an 8pt-semibold chip's, so both are drawn")
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
