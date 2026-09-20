import Foundation

/// The rows of the Accuracy surface's **"How We Compare"** card.
///
/// #7536 — THE SWIFT TWIN OF THIS CARD NEVER GOT THE REPAIRS WEB MADE TO IT.
///
/// The card drew four bars on a shared 0–10pp axis out of four literal
/// arguments to a `benchmarkRow(label, value, detail, highlight)` helper whose
/// only expressible shape was a POINT. Web repaired the same card three times
/// (CAL-P1261 / #6278, then #7524) and the Swift side moved with none of them,
/// because nothing on either surface connects the two lists and no iOS test
/// pinned a single one of the literals. What a reader had in the app:
///
///   - **A range plotted as an invented midpoint, contradicting itself in
///     place.** `Academic consensus` drew a solid bar at `3.5` beside its own
///     caption `"Arrow et al. 2008 (2–5pp)"`. 3.5 is the midpoint of 2–5 and
///     appears nowhere else on the screen. Web's note on the same defect:
///     *"a midpoint that appears nowhere on the page, and one whose green said
///     'excellent' for a range whose top half the footnote itself excluded. A
///     range is drawn as a band between its ends."*
///   - **Every row colour-graded on OUR thresholds.** `eceColor` was applied to
///     all four figures with no condition; `eceColor` is `< 4 ? .green`, and all
///     four values were under 4, so all four printed green. The colour carried
///     no information, and it published a verdict on Metaculus's and two 2008
///     papers' calibration that we cannot support.
///   - **Our own row untagged.** The label was the bare `"Bain Luck"` while its
///     value and detail both moved with the cohort toggle a few cards above.
///     The benchmarks beside it are not cohort-scoped at all, so the one row
///     that changes under the reader's hands was the one row that did not say so.
///   - **A vote-share error drawn as a calibration benchmark.** #7524: Berg et
///     al.'s 1.5pp for the Iowa Electronic Markets is an absolute error on
///     predicted vote SHARE, not a per-bucket calibration error. Two different
///     quantities that share a unit, drawn as one bar beside ours. The
///     reference keeps its place in Further Reading, where it is described
///     correctly.
///
/// Lifted out of the view because the view is where all of that was
/// unfalsifiable: a literal passed to a private `@ViewBuilder` func cannot be
/// read by a test, which is exactly how three web ships drifted silently. The
/// rows and their bar geometry are values now, and `CalibrationBenchmarkTests`
/// pins them.
enum CalibrationBenchmarks {

    /// The shared axis every bar is drawn against, in percentage points. A
    /// constant rather than a literal in the view so a test can assert the
    /// fractions below against the same number the bar is drawn with.
    static let axisMaxPP: Double = 10

    /// One row of the card.
    ///
    /// 🪤 `value` and (`rangeLow`, `rangeHigh`) are **alternatives, never both**
    /// — web's `BenchmarkRow` carries the identical rule in its own docstring:
    /// *"a benchmark published as a RANGE has no point value, and inventing one
    /// to draw a bar with is what CAL-P1261 removed."* The initialisers below
    /// are the enforcement: there is no way to construct a row holding both, so
    /// the next person to add a benchmark has to say which kind it is.
    struct Row: Equatable, Identifiable {
        /// The benchmark's name, as a reader reads it.
        let label: String

        /// The active cohort, on our own row only, in the view model's words.
        ///
        /// Our figure is `cohortMCE` over `cohortN` and both move with the
        /// toggle; the published benchmarks are not cohort-scoped at all. Web
        /// hangs a `<CohortTag>` off the label for the same reason. The string
        /// is passed in rather than spelled here so it cannot drift from the
        /// banner that sets it (L2-237).
        let cohortTag: String?

        /// The published point figure, in pp. `nil` on a row published as a range.
        let value: Double?
        /// The ends of a published range, in pp. Both `nil` on a point row.
        let rangeLow: Double?
        let rangeHigh: Double?

        /// The small line under the bar: our outcome count, or the source.
        let detail: String

        /// Our own measured row. Drives the emphasis, the bar colour, and —
        /// through `isGraded` — whether the figure may be coloured at all.
        let isOurs: Bool

        var id: String { label }

        var isRange: Bool { rangeLow != nil && rangeHigh != nil }

        /// Whether this figure may be COLOURED on our thresholds.
        ///
        /// Only our own measured point. A published benchmark is somebody
        /// else's number measured somebody else's way, and `eceColor`'s verdict
        /// on it is one we cannot support; a range has no point to grade.
        var isGraded: Bool { isOurs && !isRange }

        /// A point row: `Bain Luck`, `Metaculus`.
        static func point(
            _ label: String, _ value: Double, detail: String,
            cohortTag: String? = nil, isOurs: Bool = false
        ) -> Row {
            Row(label: label, cohortTag: cohortTag, value: value,
                rangeLow: nil, rangeHigh: nil, detail: detail, isOurs: isOurs)
        }

        /// A row published as a range, drawn as a band between its ends.
        static func range(
            _ label: String, low: Double, high: Double, detail: String
        ) -> Row {
            Row(label: label, cohortTag: nil, value: nil,
                rangeLow: low, rangeHigh: high, detail: detail, isOurs: false)
        }

        /// The figure as it is printed, which for a range is the range — never a
        /// number derived from it.
        ///
        /// An en dash, matching the `(2–5pp)` the caption on this row has always
        /// carried, and one token so the two ends cannot wrap apart: web
        /// measured `"2-" / "5pp"` across two lines on production and a figure
        /// broken mid-token reads as a different number.
        var figureText: String {
            if let low = rangeLow, let high = rangeHigh {
                return "\(Self.trim(low))\u{2013}\(Self.trim(high))pp"
            }
            return String(format: "%.1fpp", value ?? 0)
        }

        /// The statistic the figure IS, printed beside it — our row only.
        ///
        /// #7225, the fourth web repair this card never took. Our figure is
        /// `cohortMCE`, the ten buckets averaged with EQUAL weight; the hero and
        /// the Combined row of the source table a few hundred points above are
        /// `cohortECE`, n-weighted. On the 2026-09-20 render they read 1.0pp and
        /// 0.9pp over the same cohort, the same denominator and the same unit,
        /// and a reader met them with nothing to tell them apart — the source
        /// table's `Bucket` header (#7174) is the only separator, and it is on a
        /// different card. So the word travels with the number.
        ///
        /// Our row only: the published benchmarks are somebody else's figures
        /// and we cannot say how they were averaged, which is the same rule that
        /// keeps `isGraded` off them.
        var figureQualifier: String? { isGraded ? "per-bucket" : nil }

        /// Where the bar starts, as a fraction of the track. Non-zero only for a
        /// range: a band between 2 and 5 on a 0–10 axis begins a fifth of the
        /// way along, which is the whole difference between drawing a range and
        /// drawing a midpoint.
        var barLeadingFraction: Double {
            Self.clamp((rangeLow ?? 0) / axisMaxPP)
        }

        /// How much of the track the bar covers. Clamped so a figure past the
        /// axis maximum fills it rather than overflowing the card, and so a band
        /// never runs past the end of the track it started inside.
        var barWidthFraction: Double {
            if let low = rangeLow, let high = rangeHigh {
                return min(1 - barLeadingFraction, Self.clamp((high - low) / axisMaxPP))
            }
            return Self.clamp((value ?? 0) / axisMaxPP)
        }

        private static func clamp(_ f: Double) -> Double {
            guard f.isFinite else { return 0 }
            return min(1, max(0, f))
        }

        /// `2` and `5`, not `2.0` and `5.0`. These are the ends the source
        /// published, printed as published.
        private static func trim(_ v: Double) -> String {
            v == v.rounded() ? String(Int(v)) : String(format: "%.1f", v)
        }
    }

    /// The card's rows, in the order it draws them.
    ///
    /// - Parameters:
    ///   - ourMCE: `viewModel.cohortMCE` — the equal-weighted per-bucket error.
    ///   - ourOutcomes: the formatted cohort size.
    ///   - cohort: `viewModel.cohortShortLabel`, the active cohort's own name.
    static func rows(ourMCE: Double, ourOutcomes: String, cohort: String) -> [Row] {
        [
            .point("Bain Luck", ourMCE, detail: "\(ourOutcomes) outcomes",
                   cohortTag: cohort, isOurs: true),

            // 🪤 #7531 — 2.5 is the MIDPOINT of the ~2-3pp range Metaculus
            // publishes, and this page sources it as a range itself in Further
            // Reading. It is the one defect on this card that is not iOS
            // lagging web: web plots the same midpoint and #7531 is open on
            // both surfaces. Left in step deliberately — the range path above
            // is what its fix needs, and both halves flip together so the two
            // surfaces never disagree about a published figure.
            .point("Metaculus", 2.5, detail: "Self-reported"),

            // #7524's row was here: "Iowa Electronic Markets", 1.5, "Berg et
            // al. 2008". Berg's 1.5pp is an absolute error on predicted vote
            // share and ours is a per-bucket calibration error; drawn on one
            // axis they read as "we beat IEM by 0.5pp", which is not a
            // comparison either number supports. Naming the statistic in the
            // row instead was considered and rejected on web: the bar would
            // still be drawn at 15% of a calibration-error axis, and under
            // notice 34 / D102 a number that cannot be shown honestly is left
            // out rather than explained in a caption.

            .range("Academic consensus", low: 2, high: 5, detail: "Arrow et al. 2008"),
        ]
    }
}
