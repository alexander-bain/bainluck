import Foundation
#if canImport(UIKit)
import UIKit
#endif

/// Where the period chips on a time chart's strip are drawn, and which of them
/// there is room to draw at all.
///
/// #3817 — LIFTED OUT OF `OddsChartView` because it is not one chart's business.
/// D58 makes the event page's win-probability chart the MATCH primitive and folds
/// the score chart under it; both strips already called into this type, so it was
/// a shared layer living inside one of its two callers. Nothing about the geometry
/// changed in the move — only `chipWidth`, below, and that for its own reasons.
enum PeriodChipGeometry {
    /// Widest realistic chip: 2 characters at size 10 bold (~20pt) + 4pt padding
    /// each side. Two-digit innings ("10") are reachable since #1831's 1…N ladder.
    static let chipWidthPoints: Double = 28
    /// Plot area on a common phone layout: 393pt screen − 32pt card padding −
    /// 24pt rotated team-label gutter = 337pt. Asserted against those three
    /// numbers in `EventScreenLayoutTests`, so it cannot drift into a fiction that
    /// the spacing fraction below is then derived from.
    static let plotWidthPoints: Double = 337
    /// The fraction actually applied — DERIVED, not a hand-picked literal.
    ///
    /// It was briefly written as `0.09`, "the derived 8.3% rounded up for safety",
    /// and the round-up was not safe: it is an absolute threshold in disguise, and
    /// on a LONG chart it grows past the real gap between periods. A 12-inning game
    /// over four hours has innings 1,200s apart against a 9% threshold of 1,296s,
    /// so the padding would have deleted a real inning chip — trading an overlap
    /// defect for a missing-data defect. `EventScreenLayoutTests` caught it.
    ///
    /// Keeping it exactly `chipWidth / plotWidth` is what makes it a pure
    /// no-overlap rule: it drops a chip if and only if there is genuinely no room
    /// for one, which is the most information the strip can carry without
    /// collisions. Beyond about 12 periods there IS no room, and dropping is then
    /// the correct behaviour rather than a compromise.
    static var minSpacingFraction: Double { chipWidthPoints / plotWidthPoints }

    /// Per-label chip width, for the questions `chipWidthPoints` cannot answer:
    /// does THIS chip fit inside the plot, and does it hit its neighbour.
    static let horizontalPaddingPoints: Double = 4
    /// Per-character width, kept ONLY as the fallback for a platform that cannot
    /// measure text — see `textWidth`. On iOS nothing reads it.
    static let characterWidthPoints: Double = 6

    /// One chip strip's own type, because the event page draws two.
    ///
    /// The MATCH chart's chips are 10pt bold with 4pt padding; the score chart
    /// below it draws the same periods at 8pt semibold with 3pt padding, under a
    /// 160pt-tall plot where a full-size chip would shout. Placing the smaller
    /// chips with the larger chip's width would drop chips that had room — the
    /// opposite defect from the one this file exists to prevent — so the width
    /// model takes the strip's metrics instead of assuming one of them.
    struct ChipMetrics: Equatable {
        enum Weight: Equatable { case bold, semibold }

        let horizontalPadding: Double
        let fontSize: Double
        let weight: Weight
        /// Used only where `textWidth` cannot measure. Never on iOS.
        let fallbackCharacterWidth: Double

        /// 10pt bold, 4pt padding — the MATCH chart's strip.
        static let match = ChipMetrics(
            horizontalPadding: horizontalPaddingPoints, fontSize: 10, weight: .bold,
            fallbackCharacterWidth: characterWidthPoints)
        /// 8pt semibold, 3pt padding — the score chart's strip.
        static let score = ChipMetrics(
            horizontalPadding: 3, fontSize: 8, weight: .semibold,
            fallbackCharacterWidth: 5)
    }

    /// The ink a label actually occupies, MEASURED in the strip's own font.
    ///
    /// #3817 — THIS USED TO BE `label.count × 6pt`, A DELIBERATE UPPER BOUND, AND
    /// A BOUND IS THE WRONG SHAPE FOR THIS NUMBER.
    ///
    /// The per-character figure was justified as safety: "6pt per character is the
    /// round number above [the measured 4.7–5.3pt], so every chip's computed width
    /// is an upper bound on its drawn width — which is the safe direction for a
    /// rule that decides whether two chips collide." That is only half a rule.
    /// Over-estimating is the safe direction for AVOIDING AN OVERLAP and the
    /// unsafe direction for KEEPING INFORMATION, because `place` answers a
    /// predicted collision by deleting a chip: every point of imagined ink is a
    /// period the reader loses. A width model owes accuracy in both directions,
    /// which is why it is measured now — the treatment #3269 already gave the
    /// x-axis labels next to it ("Label widths are MEASURED — the suite re-renders
    /// every label each style can print").
    ///
    /// **HOW BIG THE ERROR ACTUALLY WAS, because the first diagnosis of #3817 got
    /// this backwards and the measurement caught it.** The screenshot that opened
    /// the issue was blamed on this function; it was mostly `place`'s deletion
    /// policy, corrected there. At 10pt bold a glyph really does draw ~5.9pt, so a
    /// three-character inning chip was over-charged by a third of a point — not
    /// the several points the first reading assumed. The surplus was real but
    /// concentrated: "Final" was charged 38pt against 32.5pt of ink, and the score
    /// strip's 5pt-per-character model over-charged every chip by about a fifth.
    ///
    /// `PeriodChipWidthTests` re-renders every label the period vocabulary can
    /// produce and asserts the model tracks the drawn ink in BOTH directions, so
    /// it can neither grow back into a bound nor shrink into an overlap.
    static func textWidth(_ label: String, metrics: ChipMetrics) -> Double {
        #if canImport(UIKit)
        let font = UIFont.systemFont(
            ofSize: metrics.fontSize,
            weight: metrics.weight == .bold ? .bold : .semibold)
        return Double((label as NSString).size(withAttributes: [.font: font]).width)
        #else
        return Double(label.count) * metrics.fallbackCharacterWidth
        #endif
    }

    static func chipWidth(for label: String, metrics: ChipMetrics = .match) -> Double {
        metrics.horizontalPadding * 2 + textWidth(label, metrics: metrics)
    }

    /// Keep a chip's full width inside the plot (#3237).
    ///
    /// `rawX` is the chip's ideal centre — the x of the period boundary it marks,
    /// measured from the plot's leading edge. A marker at or near `x = 0` centres
    /// a chip whose left half hangs over the y-axis gutter, on top of the "100%"
    /// label; the same happens at the trailing edge against the plot's right
    /// border. Clamping the CENTRE by half the chip's width is the whole fix: the
    /// chip still names its period, it just stops overhanging the frame.
    ///
    /// A plot too narrow to hold the chip at all has no non-overlapping answer,
    /// so it centres — visibly wrong beats arbitrarily wrong.
    static func clampedCenterX(
        rawX: Double, label: String, plotWidth: Double, metrics: ChipMetrics = .match
    ) -> Double {
        let width = chipWidth(for: label, metrics: metrics)
        guard plotWidth > width else { return plotWidth / 2 }
        let half = width / 2
        return min(max(rawX, half), plotWidth - half)
    }

    /// One chip asking to be drawn: `key` is the caller's identity for it, so the
    /// placement can be matched back to a marker without this type knowing what a
    /// marker is.
    struct ChipRequest: Equatable {
        let key: Int
        let label: String
        let rawX: Double
    }

    struct ChipPlacement: Equatable {
        let key: Int
        let centerX: Double
    }

    /// How far a chip may be moved off the boundary it names: half its own width,
    /// so the chip still overlaps its own gridline.
    ///
    /// This is the whole justification for moving a chip at all. The period
    /// boundary is drawn exactly, as a `RuleMark`; the chip is a LABEL for that
    /// line, and a label a few points off its line still reads as belonging to
    /// it. A label that no longer touches the line has stopped labelling it, and
    /// at that point dropping the chip is more honest than drawing it against the
    /// wrong boundary.
    static func nudgeBudget(for label: String, metrics: ChipMetrics = .match) -> Double {
        chipWidth(for: label, metrics: metrics) / 2
    }

    /// Place the chips that will actually be drawn (#3237, #3817).
    ///
    /// The clamp above cannot be applied on its own: pulling a wide trailing chip
    /// inside the plot moves it INTO its neighbour. Measured on 15302915, the
    /// 10-inning walk-off — clamping alone drew "Final" over "9th" so the strip
    /// read "9Final". So the last word on overlap belongs here, where the final
    /// positions are known.
    ///
    /// **#3817 — IT USED TO ANSWER EVERY COLLISION BY DELETING A CHIP, AND THAT
    /// COST FOUR INNINGS OF A NINE-INNING GAME.** Photographed on master
    /// `a2ed380e` (iPhone 17, 2026-09-07): the completed Cardinals 10 — Rockies 8
    /// (15305472) drew `2nd · 3rd · 5th · 7th · 8th · Final` under a Game Segments
    /// table printing all nine innings. Replaying this function over the event's
    /// own history at the chart's 280pt plot reproduced that strip exactly, and
    /// named the three losses:
    ///
    ///  * `4th` was 0.4pt short of clearing `5th` — deleted for want of moving
    ///    two fifths of a point;
    ///  * `9th` was deleted by a move `Final` made. The trailing clamp is
    ///    mandatory (the chip may not overhang) and pulls `Final` 15pt inward;
    ///    that displacement was then charged to its neighbour's existence;
    ///  * `1st` the same, at the leading edge.
    ///
    /// The total ink was 238pt in a 280pt plot. **The strip was never out of
    /// room; it was out of willingness to move.**
    ///
    /// So chips are placed by relaxation instead. A left-to-right pass pushes each
    /// chip clear of its predecessor, a right-to-left pass pulls the tail back
    /// inside the plot, and a chip is dropped only when it still cannot be drawn:
    /// overlapping, overhanging, or moved further than `nudgeBudget` — further
    /// than its own half-width from the boundary it names. When one must go it is
    /// the EARLIER of the pair in tension, the preference this file has always
    /// stated ("keep later/more informative label"), so the terminal chip survives.
    ///
    /// Requests are placed in the order given; the caller passes them in time
    /// order, which is x order on a linear axis.
    static func place(
        _ requests: [ChipRequest], plotWidth: Double, metrics: ChipMetrics = .match
    ) -> [ChipPlacement] {
        var candidates = requests
        while !candidates.isEmpty {
            let centers = relaxedCenters(candidates, plotWidth: plotWidth, metrics: metrics)
            guard let doomed = firstUnplaceable(
                candidates, centers: centers, plotWidth: plotWidth, metrics: metrics) else {
                return zip(candidates, centers).map {
                    ChipPlacement(key: $0.key, centerX: $1)
                }
            }
            // A plot with no room for even one chip has no non-overlapping answer,
            // so the last one standing is centred rather than dropped — the same
            // "visibly wrong beats arbitrarily wrong" `clampedCenterX` takes.
            if candidates.count == 1 {
                return [ChipPlacement(
                    key: candidates[0].key,
                    centerX: clampedCenterX(
                        rawX: candidates[0].rawX, label: candidates[0].label,
                        plotWidth: plotWidth, metrics: metrics))]
            }
            candidates.remove(at: doomed)
        }
        return []
    }

    /// The two relaxation passes. Left-to-right seats each chip clear of the one
    /// before it; right-to-left pulls the tail back inside the trailing edge,
    /// which is the pass that stops `Final` shoving its neighbour out of the
    /// strip. Neither pass drops anything — that decision belongs to the caller,
    /// once it can see where everything landed.
    private static func relaxedCenters(
        _ requests: [ChipRequest], plotWidth: Double, metrics: ChipMetrics
    ) -> [Double] {
        let halves = requests.map { chipWidth(for: $0.label, metrics: metrics) / 2 }
        var centers = requests.map(\.rawX)
        guard !centers.isEmpty else { return centers }

        centers[0] = max(centers[0], halves[0])
        for i in 1..<centers.count {
            centers[i] = max(centers[i], centers[i - 1] + halves[i - 1] + halves[i])
        }
        let last = centers.count - 1
        centers[last] = min(centers[last], plotWidth - halves[last])
        for i in stride(from: last - 1, through: 0, by: -1) {
            centers[i] = min(centers[i], centers[i + 1] - halves[i + 1] - halves[i])
        }
        return centers
    }

    /// The index to give up on, or `nil` when every chip is drawable.
    ///
    /// A chip is undrawable if it overlaps its predecessor, hangs off either edge,
    /// or has been pushed further than `nudgeBudget` from its own boundary. Which
    /// chip to drop follows the direction of the pressure: a chip shoved RIGHT is
    /// being crowded from the left, so the earlier neighbour goes; a chip pulled
    /// LEFT is being crowded from the right, and is itself the earlier of that
    /// pair. Either way the later, more informative chip survives.
    ///
    /// The budget is measured from the CLAMPED ideal, not from `rawX`. Pulling a
    /// chip inside the plot is mandatory rather than a nudge, and charging it to
    /// the budget would delete the two chips that most need to exist — the first
    /// period and the terminal one, which are the only two the clamp ever moves.
    private static func firstUnplaceable(
        _ requests: [ChipRequest], centers: [Double], plotWidth: Double,
        metrics: ChipMetrics
    ) -> Int? {
        let epsilon = 0.001
        for (i, request) in requests.enumerated() {
            let half = chipWidth(for: request.label, metrics: metrics) / 2
            if centers[i] - half < -epsilon { return i }
            if centers[i] + half > plotWidth + epsilon { return max(i - 1, 0) }
            if i > 0 {
                let previousHalf = chipWidth(
                    for: requests[i - 1].label, metrics: metrics) / 2
                if centers[i] - half < centers[i - 1] + previousHalf - epsilon {
                    return i - 1
                }
            }
            let ideal = clampedCenterX(
                rawX: request.rawX, label: request.label,
                plotWidth: plotWidth, metrics: metrics)
            let nudge = centers[i] - ideal
            if abs(nudge) > nudgeBudget(for: request.label, metrics: metrics) + epsilon {
                return nudge > 0 ? max(i - 1, 0) : i
            }
        }
        return nil
    }
}
