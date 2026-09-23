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
/// The database HAS an exclusivity flag, it is fully populated (13,051 false /
/// 25,620 true on open markets) and the timeline payload does not serve it — so the
/// obvious fix looks like "serve the flag". Measured over 211 open markets with ≥3
/// outcomes, **the flag is the weaker signal**:
///
/// | `mutually_exclusive` | markets | median sum | p95 | worst |
/// |---|---|---|---|---|
/// | `true`  | 123 | 0.980 | 1.025 | 1.82 |
/// | `false` | 88  | 2.645 | 7.270 | 12.81 |
///
/// The separation is enormous, and every one of the three `true` markets above this
/// ceiling is a CUMULATIVE THRESHOLD LADDER whose rungs contain each other — "Next
/// Gemini Pro model released on…?" (24 rungs, 1.82), "Israel × Lebanon diplomatic
/// meeting by October 31?" (1.63), "Lowest Mississippi level at St. Louis by
/// November 30?" (1.50). Their rungs are not alternatives however the flag is set,
/// and their sums are not probabilities. So the arithmetic is not a stand-in for the
/// flag pending a producer change: on this population **it is right where the flag
/// is wrong**, and a later ship that gates on the served flag would reintroduce the
/// lie on exactly those three shapes.
///
/// ## What this deliberately does NOT catch
///
/// 33 of the 88 non-exclusive markets sum UNDER the ceiling, and they keep their
/// `Sum` control. Two independent props at 40 and 45 add to 85 — still not a
/// probability, and indistinguishable from a legitimately exclusive field that was
/// truncated to its top rows. Arithmetic cannot separate those two, so the honest
/// boundary is drawn where the sum stops being able to be one at all. This closes
/// the class where the line is provably a fabrication, not every case where a sum is
/// semantically odd.
enum EvolutionCombinedLinePolicy {

    /// The largest served-field total that can still be one question's alternatives.
    ///
    /// Above 1.0 because a real two-way market carries overround — #2582 photographed
    /// every two-way market on one UFC card summing to 101–102% — and p95 for a
    /// flagged-exclusive field is 1.025, so a ceiling at parity would strip the
    /// control off legitimate markets for vig alone. 1.3 sits an order of magnitude
    /// below the non-exclusive median of 2.645 and comfortably above the exclusive
    /// p95, which is why it is not a tuned number: nothing measured lands near it.
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
