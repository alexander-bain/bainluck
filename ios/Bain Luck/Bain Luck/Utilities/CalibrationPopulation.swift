import Foundation

/// What the Calibration screen's category table says about the POPULATIONS its
/// two numbers are counted on. The Swift twin of `frontend/lib/calibrationPopulation.ts`.
///
/// ── WHY THIS EXISTS (#7515) ─────────────────────────────────────────────────
///
/// **The publish bar and the Outcomes column beside it are counted on different
/// populations, and the caption between them named neither.**
///
///   * **Eligibility** is decided by the backend on the **all-cohort** count.
///     That basis is settled deliberately by #7195/#7302 and this file does not
///     reopen it.
///   * **The Outcomes column** is cohort-scoped — the #7190 fix — so in the
///     default (traded) cohort it counts a strict subset of what the bar counted.
///
/// Measured against `/api/calibration` on 2026-09-20 14:05Z: `geopolitics` is
/// **1,749 all-cohort and 732 traded** against a 1,000 bar. Web renders that row
/// and prints the contradiction in full; the defect report and the BEFORE shot
/// are on the web half (#7518).
///
/// **The native table renders that row as of #7533.** It did not when this file
/// was written: `categories` took the 15 largest by all-cohort outcomes and
/// `topCategoryRows` took a further 10 by ECE, and `geopolitics` is 19th of the
/// 21 that clear the bar. Those two slices were the separately-filed defect this
/// paragraph pointed at, and deleting them is what made the consequence visible
/// here — so the clause below now fires on the default cohort rather than
/// waiting for a payload that trips it.
///
/// That transition needed no edit to the gating rule, which is the point of
/// keying it on the rendered counts: the caption started explaining the row in
/// the same commit that put the row on screen. Had it been switched on a cohort
/// flag, #7533 would have shipped a published 732 under a 1,000 bar with nothing
/// to reconcile it.
///
/// ── TWO CLAUSES, EARNING THEIR PLACE DIFFERENTLY ────────────────────────────
///
/// Standing notice 34 / D102 bans prose a reader cannot act on, not grey type as
/// such, so the two clauses are gated differently on purpose:
///
///   * **The units clause is unconditional.** The bar's population is a fact
///     about the bar in either cohort. It is the sentence web's niche card has
///     carried since #7195, word for word — one bar, one vocabulary. A reader
///     who meets the bar twice on one page must not meet it two different ways.
///   * **The consequence clause is conditional on the RENDERED ROWS**, never on
///     the cohort flag. It describes something on screen, so it appears exactly
///     when there is a row to be confused by and disappears when the data stops
///     contradicting. Keying on the data rather than on `includeThin` also means
///     the all-markets view would get the clause if it ever published a sub-bar
///     row, which a cohort branch would miss.
nonisolated enum CalibrationPopulation {

    /// The compact count this surface prints everywhere: `1000` -> `"1.0K"`.
    ///
    /// It lives here, rather than staying private to the view, because the
    /// caption below has to name the bar in **the same characters the reader
    /// sees in the Outcomes column**. A second formatter would let the caption
    /// say "1,000" over a column reading "0.7K", which is the #7515 defect
    /// wearing different digits. `CalibrationView.fmtN` delegates to this.
    static func compactCount(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fK", Double(n) / 1000) : "\(n)"
    }

    /// The Category Breakdown caption, including the population its bar counts.
    ///
    /// - Parameters:
    ///   - bar: `min_category_outcomes` as the payload published it. Read from
    ///     the payload rather than written as a literal because it is
    ///     Redis-tunable (#997) — a hard-coded copy goes stale silently.
    ///   - renderedRowOutcomes: the Outcomes column **as rendered** — the same
    ///     cohort-scoped `n` the table prints — so the comparison is against
    ///     what the reader actually reads, never a recomputed population.
    static func categoryTableNote(bar: Int, renderedRowOutcomes: [Int]) -> String {
        let label = compactCount(bar)
        // `<`, not `<=`: a row sitting exactly ON the bar is published, so it is
        // not below it and there is nothing for the reader to reconcile. (The
        // web twin also weighs `n < bar` against `!(n >= bar)`; on a `Double`
        // those part on `NaN`. These counts are `Int`, so the two spellings are
        // the same here and the boundary is the only live choice.)
        let anyBelowBar = renderedRowOutcomes.contains { $0 < bar }
        return "Raw leagues are rolled up into product-level categories, sorted by ECE. "
            + "Categories below \(label) resolved outcomes are held out — see below. "
            + "That bar counts every resolved outcome, traded or not"
            + (anyBelowBar
               ? ", so a row here can show fewer than \(label) in the Outcomes column."
               : ".")
    }
}
