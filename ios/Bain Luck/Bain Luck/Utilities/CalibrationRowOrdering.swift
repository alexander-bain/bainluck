import Foundation

/// Calibration row ordering, and the n=0 state that used to be a 0.
///
/// WHY THIS EXISTS (#3650). The iPad Calibration screen rendered a **DataGolf**
/// row reading `0 · 0.0 · 0.0 · 0.000`, in green, **first in a table whose own
/// subhead says "sorted by ECE … Lower is better"**
/// (`artifacts-native-042/ipad-calibration.png`). The screen therefore presented
/// its worst-calibrated source as its best, with a number nobody measured.
///
/// Measured against `/api/calibration` on 2026-09-06: `datagolf` publishes **36
/// outcomes, every one of them `price_moved: false`**, so the default cohort
/// (`price_moved != false`) holds **zero** of them. Include the never-moved
/// outcomes with the toggle already on that screen and its real ECE is
/// **36.49pp** — 13× the worst measured source (polymarket, 2.81pp) and 104×
/// the best (odds_api_spreads, 0.35pp). It was ranked first.
///
/// Every zero in that row is an empty reduction's identity element, not a
/// measurement:
///
///   - `CalibrationMath.ece([])`   → `0` (`totalN > 0` guard, line 103)
///   - `CalibrationMath.mce([])`   → `0` (`!cal.isEmpty` guard, line 96)
///   - `CalibrationMath.brier(…)`  → `0` (`n > 0 ? sq / n : 0`)
///
/// Each guard is individually correct — a metric over nothing has no value, and
/// `0` is the conventional neutral return. They only become a lie at the point
/// of RENDER, where `String(format: "%.1f", 0)` is indistinguishable from a
/// source that was measured and found perfect.
///
/// ── PORTED, NOT INVENTED ────────────────────────────────────────────────────
///
/// The web solved this first and its module header names this exact defect:
/// `frontend/lib/calibrationSourceRows.ts` (UX-P128). This is that judgement in
/// Swift, with the one improvement the language affords: a withheld metric is
/// `nil`, not `0`, so **the compiler — not a reviewer — enforces that an
/// unmeasured number can never reach a formatter.** The web could only promise
/// that in a comment.
///
/// ── THE ORDERING IS THE ROLLUP THAT WAS FLATTERED ───────────────────────────
///
/// "Sorted by ECE, lower is better" makes a row's POSITION a published claim,
/// and a fabricated `0.0` collected first place. Rows with no cohort data are
/// therefore ordered after every measured row rather than by a metric they do
/// not have. **They are not ranked, because they were not measured.**
///
/// The row is not DROPPED, because two absences are not the same absence: a
/// source the payload never published is absent because we have no data, but
/// `datagolf` published 36 outcomes that this cohort happens to exclude, and a
/// toggle on the same screen brings them back. Dropping it silently would hide
/// a source the reader can see with one tap. **Nothing is better than a number
/// we made up; a stated absence is better than either.**
enum CalRowState: Equatable {
    /// Outcomes stand behind this row's metrics.
    case measured
    /// The active cohort holds no outcomes for this row. Its metrics are `nil`.
    case noCohortData
}

/// A calibration row that can be ordered by its headline metric.
///
/// `ece` is optional at the protocol level so that a conforming row physically
/// cannot offer an unmeasured metric for ranking — the ordering below never has
/// to ask whether a `Double` it was handed is real.
protocol CalibrationMetricRow {
    /// Outcomes behind this row IN THE ACTIVE COHORT.
    var n: Int { get }
    /// `nil` when `n == 0`. The headline metric the table sorts on.
    var ece: Double? { get }
    /// Display label — breaks ties, and orders the unmeasured tail.
    var name: String { get }
}

enum CalibrationRowOrdering {

    /// A row is a measurement only when outcomes stand behind it.
    ///
    /// The COUNT, never the metric. `ece` returns a finite `0` on empty input,
    /// so the metric can never report its own absence — only `n` can. This is
    /// the same reason the web keys on `n` rather than `Number.isFinite(ece)`.
    static func state(outcomes n: Int) -> CalRowState {
        n > 0 ? .measured : .noCohortData
    }

    /// A metric, or `nil` if nothing was measured to produce it.
    ///
    /// Call this at every site that builds a row, so the empty reduction's `0`
    /// is discarded once, where `n` is still in scope, rather than travelling
    /// to a formatter that has no way left to tell it from a real zero.
    static func metric(_ value: Double, outcomes n: Int) -> Double? {
        guard state(outcomes: n) == .measured, value.isFinite else { return nil }
        return value
    }

    /// Measured rows by ECE ascending, then every unmeasured row, by label.
    ///
    /// A stable tail matters because a `noCohortData` row has no metric to break
    /// ties with, and an unstable tail would make row order depend on the
    /// payload's source ordering — a difference a reader would read as a change
    /// in the data. Plain `<` on `String`, not `localizedCompare`: the order of
    /// this table must not depend on the device's locale.
    static func orderedByECE<Row: CalibrationMetricRow>(_ rows: [Row]) -> [Row] {
        rows.sorted { lhs, rhs in
            switch (lhs.ece, rhs.ece) {
            case let (l?, r?):
                // Both measured: the ranking the subhead promises.
                return l == r ? lhs.name < rhs.name : l < r
            case (.some, .none):
                // Unmeasured rows leave the ranking entirely rather than
                // winning it. `lhs` is measured, so it sorts first.
                return true
            case (.none, .some):
                return false
            case (.none, .none):
                return lhs.name < rhs.name
            }
        }
    }

    /// The rows withheld from the ranking.
    ///
    /// Derived from the SAME rows the table renders, never from a second
    /// condition that has to be kept in step with them.
    ///
    /// #4118 — this used to feed `withheldNote`, which built the grey paragraph
    /// under the Source Comparison table ("DataGolf has no outcomes in this
    /// cohort, so it is not ranked above. Tap …"). Standing notice 34 bans that
    /// shape from a reader's screen, so the paragraph and its builder are gone.
    /// The predicate stays because it is the ranking's own definition of a row
    /// it cannot place, and `CalibrationRowOrderingTests` holds it to that.
    static func withheld<Row: CalibrationMetricRow>(_ rows: [Row]) -> [Row] {
        rows.filter { state(outcomes: $0.n) == .noCohortData }
    }
}
