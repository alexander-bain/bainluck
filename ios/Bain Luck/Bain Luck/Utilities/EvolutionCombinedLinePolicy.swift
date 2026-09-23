import Foundation

/// Whether a market's served field is a set of ALTERNATIVES TO ONE QUESTION, and
/// so whether adding its outcomes up produces a probability at all.
///
/// 🔴 THE DEFECT THIS EXISTS FOR. `EvolutionChartView.chartEntries` builds the
/// `Sum` line as `min(100, latestProbs.values.reduce(0, +))`. On market 56775596
/// ("Las Vegas: Team Specials", 12 independent Kalshi props) the default top-three
/// selection — Brock Bowers 3+ TDs at 94, Mendoza 300+ passing yards at 64,
/// Washington 500+ rushing yards at 52 — sums to between **107 and 234** across the
/// served week. The clamp took all **584 of 584** points to exactly 100, so a reader
/// who taps `Sum` gets a dead-flat dashed line pinned to the top of the chart.
///
/// That is the worst of the available failures. The sum of independent binaries is
/// meaningless (gotcha #23), and the clamp does not report the meaninglessness — it
/// **launders it into a confident certainty**. An unclamped 234% line at least reads
/// as broken; a flat 100% reads as "these three together are a lock", which is a
/// statement the market never made. The clamp also destroys the movement: 20 distinct
/// unclamped values collapse to 1.
///
/// ## Why the field's own arithmetic, and not `futures_markets.mutually_exclusive`
///
/// The database HAS an exclusivity flag and the timeline payload does not serve it,
/// so the obvious fix looks like "serve the flag". Censused 2026-09-22 over **every**
/// open market with ≥3 priced outcomes — 11,095 of them, complete keyset walk, raw
/// rows banked at `artifacts/native-303/8158-ceiling-census.json` — **the flag is
/// informative but nowhere near sufficient**:
///
/// | `mutually_exclusive` | markets | median sum | p95 | worst | above 1.3 |
/// |---|---|---|---|---|---|
/// | `true`  | 4,764 | 1.014 | 2.500 | 21.64 | 646 (13.6%) |
/// | `false` | 6,331 | 3.610 | 12.310 | 179.87 | 5,576 (88.1%) |
///
/// Flagged-exclusive fields do cluster where they should (median 1.014). But **646
/// of them still cannot be summed**, and they are not a rounding error or one exotic
/// shape. Two distinct populations sit up there:
///
///   * **Cumulative threshold ladders** whose rungs contain one another — a
///     "by October 31 / by November 30 / …" date board is flagged exclusive and its
///     rungs are not alternatives however the flag reads.
///   * **Large fields whose per-outcome YES prices never normalise** — "Maxwell
///     Award Winner" (63 outcomes, 20.39), "College Football Playoff: #12 Seed"
///     (50, 21.64), "ACC Conference Championship Matchup" (136, 20.71). These ARE
///     one question; their prices are simply not a distribution, so adding any
///     subset of them is adding numbers that were never shares of anything.
///
/// So the arithmetic is not a stand-in for the flag pending a producer change: on
/// this population it is right where the flag is wrong, and a later ship that gates
/// on the served flag would reintroduce the lie on all 646.
///
/// ## What this deliberately does NOT catch, and what it costs
///
/// 755 of the non-exclusive markets sum UNDER the ceiling and keep their `Sum`
/// control. Two independent props at 40 and 45 add to 85 — still not a probability,
/// and indistinguishable from a legitimately exclusive field truncated to its top
/// rows. Arithmetic cannot separate those two, so the honest boundary is drawn where
/// the sum stops being able to be one at all.
///
/// 🪤 **The cost is not zero and is worth stating plainly.** 6,222 markets (56.1%)
/// lose the control. For **5,877 of them (94.5%) the line was already a flat clamped
/// 100** — there the refusal is purely the repair. The other **345 were drawing a
/// moving line under 100**, and those readers lose something that looked like it
/// worked: they are overwhelmingly 100+-outcome boards ("ACC Conference Championship
/// Matchup", top-3 = 0.72 of a field totalling 20.71) where the sub-total reads as a
/// probability but sits on prices inflated roughly twentyfold. A plausible wrong
/// number is the worse failure of the two, which is why they are refused too — but
/// it is a judgement, not a free win.
enum EvolutionCombinedLinePolicy {

    /// The largest served-field total that can still be one question's alternatives.
    ///
    /// **Principled, not fitted.** One question's alternatives sum to 1 by
    /// construction; the only legitimate excess is overround, and #2582 photographed
    /// every two-way market on one UFC card summing to 101–102%. 1.3 allows thirty
    /// points of vig and pricing noise on top of a well-formed field — comfortably
    /// clear of the flagged-exclusive median of 1.014, and far below the
    /// non-exclusive median of 3.610.
    ///
    /// 🪤 **It is NOT a natural boundary, and the measurement says so.** Sweeping the
    /// ceiling across the full 11,095-market census produces no cliff — the curve is
    /// smooth, so any claim that "nothing lands near it" would be false:
    ///
    /// | ceiling | markets refused | already flat | working lines lost |
    /// |---|---|---|---|
    /// | 1.0 | 8,638 | 6,914 | 1,724 |
    /// | 1.2 | 6,500 | 6,013 | 487 |
    /// | **1.3** | **6,222** | **5,877** | **345** |
    /// | 1.5 | 5,903 | 5,670 | 233 |
    /// | 3.0 | 3,988 | 3,941 | 47 |
    ///
    /// Raising it buys a better ratio and leaves more flat lines unfixed; lowering it
    /// fixes more and costs more working ones. 1.3 is therefore a judgement defended
    /// by what a probability IS, and the table is here so the next person changing it
    /// argues with the trade rather than rediscovering it. The reported specimen
    /// (56775596, field sum 3.91) is caught by every row above.
    static let singleQuestionSumCeiling: Double = 1.3

    /// Whether `servedOutcomes` are alternatives to one question.
    ///
    /// Measured over the WHOLE SERVED FIELD, including `Field` — not over the rows
    /// the reader's `Top N` chip left on screen. `Field` is the residual bucket that
    /// makes an exclusive field total 100 in the first place, so dropping it biases
    /// the sum down; and a card-level truth must not change because a reader
    /// narrowed the table, which is the same distinction `EvolutionLeaderboard
    /// Geometry.renderedPercents(forServedField:)` draws for #8109.
    ///
    /// Truncation is safe in one direction only, and that is the direction the route
    /// truncates in: `top=50` can only REMOVE probability mass, so it can lower a
    /// field under the ceiling but never lift one over it. A false "one question" is
    /// today's behaviour; a false "not one question" would silently remove a working
    /// control, and this cannot produce one.
    ///
    /// An unpriced field answers `true` — today's behaviour — because a chart with no
    /// served probabilities has said nothing this can contradict. Two priced outcomes
    /// are required before it will judge: one outcome cannot exceed the ceiling on
    /// its own, so a single row could only ever return `true`, and reading that as a
    /// verdict would dress a non-answer up as a measurement (gotcha #53).
    static func fieldIsOneQuestion(servedOutcomes: [TimelineOutcomeMeta]) -> Bool {
        let priced = servedOutcomes.compactMap(\.currentProbability)
        guard priced.count >= 2 else { return true }
        return priced.reduce(0, +) <= singleQuestionSumCeiling
    }

    /// The combined point for one instant, or `nil` where no line should be drawn.
    ///
    /// The clamp lives HERE rather than at the call site because the clamp is the
    /// defect: `min(100, …)` is what converted a meaningless 234 into a confident
    /// 100, and a number that can mislead a reader belongs somewhere a test can
    /// reach it. `chartEntries` is left as the one call.
    ///
    /// It is kept for the case it was written for. On alternatives to one question a
    /// selection genuinely cannot exceed certainty, so the clamp only ever absorbs
    /// rounding and overround there — a percent or two of vig, not a factor of two.
    /// What makes it safe now is that it can no longer be reached by a field whose
    /// sum was never a probability to begin with.
    static func combinedProbability(
        showRequested: Bool,
        fieldIsOneQuestion: Bool,
        selectedCount: Int,
        latestProbs: [String: Double]
    ) -> Double? {
        guard showRequested, fieldIsOneQuestion, selectedCount > 1, !latestProbs.isEmpty
        else { return nil }
        return min(100, latestProbs.values.reduce(0, +))
    }
}
