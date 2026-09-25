import Foundation

/// Pure, unit-testable calibration math ported 1:1 from the web reference
/// (`frontend/lib/calibrationMath.ts` + the `/calibration` page aggregation).
///
/// This exists to fix #894 (native vs web calibration mismatch): the native tab
/// used to re-derive headline numbers with its OWN formulas, so it disagreed with
/// the web page. The API's precomputed `by_category`/`by_source` rows cover the
/// *all-markets* cohort, but the web page's DEFAULT view is the price-moved
/// cohort (`price_moved != false` — outcomes whose price moved, plus the
/// sportsbook lines where that test does not apply) computed client-side, so
/// simply reading the
/// precomputed rows would REINTRODUCE the mismatch. Instead native mirrors the
/// web's exact client-side aggregation here (same rounding, same ECE/MCE/Brier),
/// guaranteeing the two surfaces print the same digits.
///
/// ECE is the n-weighted headline metric (reflects the outcomes users actually
/// see); `mce` is the equal-weighted mean over the ten buckets — a tiny bucket
/// counts as much as a huge one, which is why it can read BELOW ECE. It is NOT a
/// maximum, whatever the three letters suggest; the reader-facing column was
/// renamed to `Bucket` in #7174 and the key kept for web parity. All error values
/// are in percentage points (pp).
nonisolated enum CalibrationMath {

    /// One probability bucket after aggregation across sources/categories.
    /// Mirrors the web page's `AggBucket` (values rounded to 0.1 for parity).
    nonisolated struct AggBucket: Sendable, Identifiable {
        let bucketIdx: Int
        let n: Int
        let winners: Int
        /// Average predicted probability in the bucket, percent (0–100).
        let avgProb: Double
        /// Actual win rate, percent (0–100).
        let actual: Double
        /// actual − avgProb, percentage points.
        let error: Double
        /// Wilson lower bound, percent (0–100).
        let ciLower: Double
        /// Wilson upper bound, percent (0–100).
        let ciUpper: Double

        /// Bucket midpoint on the 0–100 predicted axis (5, 15, 25, …).
        var midpoint: Double { Double(bucketIdx) * 10 + 5 }
        /// e.g. "30-40%".
        var bucketLabel: String { "\(bucketIdx * 10)-\(bucketIdx * 10 + 10)%" }
        var id: Int { bucketIdx }
    }

    /// Wilson score interval (z = 1.96), returned as fractions in 0…1.
    /// Ported verbatim from the web `wilsonCI`.
    static func wilsonCI(wins: Int, total: Int, z: Double = 1.96) -> (Double, Double) {
        guard total > 0 else { return (0, 0) }
        let t = Double(total)
        let p = Double(wins) / t
        let denom = 1 + (z * z) / t
        let center = (p + (z * z) / (2 * t)) / denom
        let inner = (p * (1 - p) + (z * z) / (4 * t)) / t
        let spread = (z * inner.squareRoot()) / denom
        return (max(0, center - spread), min(1, center + spread))
    }

    /// Aggregate raw per-source/per-category buckets into 10 probability bins.
    /// Optionally filtered (e.g. to a cohort or a single source/category).
    /// Rounding matches the web page exactly (0.1% / 0.1pp) so digits line up.
    static func aggregate(
        _ buckets: [CalibrationBucket],
        filter: ((CalibrationBucket) -> Bool)? = nil
    ) -> [AggBucket] {
        struct Acc { var n = 0; var winners = 0; var sumProb = 0.0 }
        var agg: [Int: Acc] = [:]
        for b in buckets {
            if let filter, !filter(b) { continue }
            var a = agg[b.bucketIdx] ?? Acc()
            a.n += b.n
            a.winners += b.winners
            a.sumProb += b.sumProb
            agg[b.bucketIdx] = a
        }
        return agg.map { idx, a -> AggBucket in
            let avgProb = a.n > 0 ? a.sumProb / Double(a.n) : 0
            let actual = a.n > 0 ? Double(a.winners) / Double(a.n) : 0
            let (lo, hi) = wilsonCI(wins: a.winners, total: a.n)
            return AggBucket(
                bucketIdx: idx,
                n: a.n,
                winners: a.winners,
                avgProb: round1(avgProb),
                actual: round1(actual),
                error: round1(actual - avgProb),
                ciLower: round1(lo),
                ciUpper: round1(hi)
            )
        }
        .sorted { $0.bucketIdx < $1.bucketIdx }
    }

    /// Equal-weighted mean |error| across the buckets (pp). Web `mce`.
    ///
    /// #7174 — it is a MEAN. It is more sensitive to a bad thin bucket than ECE
    /// is, which is the property the old "worst-bucket" wording was reaching for,
    /// but it is bounded by the mean of the errors and not by the worst of them:
    /// `mce(cal) <= max |error|`, with equality only when every bucket ties.
    /// Shown to readers as `Bucket`.
    static func mce(_ cal: [AggBucket]) -> Double {
        guard !cal.isEmpty else { return 0 }
        return cal.reduce(0.0) { $0 + abs($1.error) } / Double(cal.count)
    }

    /// n-weighted mean |error| (pp). The headline calibration metric. Web `ece`.
    static func ece(_ cal: [AggBucket]) -> Double {
        let totalN = cal.reduce(0) { $0 + $1.n }
        guard totalN > 0 else { return 0 }
        return cal.reduce(0.0) { $0 + (Double($1.n) / Double(totalN)) * abs($1.error) }
    }

    /// Mean Brier (average squared error) over the raw buckets. Web `brierScore`.
    static func brier(
        _ buckets: [CalibrationBucket],
        filter: ((CalibrationBucket) -> Bool)? = nil
    ) -> Double {
        var n = 0
        var sq = 0.0
        for b in buckets {
            if let filter, !filter(b) { continue }
            n += b.n
            sq += b.sumSqErr
        }
        return n > 0 ? sq / Double(n) : 0
    }

    /// Total resolved outcomes across buckets matching the filter.
    static func totalN(
        _ buckets: [CalibrationBucket],
        filter: ((CalibrationBucket) -> Bool)? = nil
    ) -> Int {
        buckets.reduce(0) { acc, b in
            if let filter, !filter(b) { return acc }
            return acc + b.n
        }
    }

    /// Round a fraction (0…1) to a 0.1-precision percent, matching the web's
    /// `Math.round(x * 1000) / 10`.
    private static func round1(_ fraction: Double) -> Double {
        (fraction * 1000).rounded() / 10
    }

    // MARK: - Trading-activity comparison (L2-230 web parity)

    /// Decimal places every ECE on the calibration surface is rendered with.
    private static let eceDisplayDP = 1

    /// Which cohort carries the HIGHER error, judged at display precision.
    nonisolated enum ActivityDirection: String, Sendable {
        case movedHigher = "moved_higher"
        case unchangedHigher = "unchanged_higher"
        case tied
        case unknown
    }

    /// The rendered description of the activity split. `sentence == nil` means
    /// render no comparison at all.
    ///
    /// #8504: `direction` is still computed and never rendered — not in the
    /// sentence, not as a value colour. The ratio the sentence used to print is
    /// gone rather than kept unrendered: a "1.3x" left in the struct is one line
    /// away from being printed again.
    nonisolated struct ActivityComparison: Sendable {
        let direction: ActivityDirection
        let movedText: String?
        let unchangedText: String?
        let sentence: String?

        static let unrenderable = ActivityComparison(
            direction: .unknown, movedText: nil, unchangedText: nil, sentence: nil
        )
    }

    /// A cohort is usable only if it has outcomes AND a finite, non-negative ECE.
    private static func cohortValue(ece: Double?, n: Int?) -> Double? {
        guard let n, n > 0 else { return nil }
        guard let e = ece, e.isFinite, e >= 0 else { return nil }
        // Round to what the reader actually sees before anything is compared.
        return (e * 10).rounded() / 10
    }

    private static func fixed1(_ v: Double) -> String { String(format: "%.1f", v) }

    /// Direction-aware, causation-free description of the trading-activity split.
    ///
    /// A 1:1 port of the web's `describeActivityComparison`
    /// (`frontend/lib/calibrationMath.ts`), shipped in L2-230 to end this exact
    /// sentence on the public page:
    ///
    ///     "Markets with active trading are 0.6x more accurately calibrated."
    ///
    /// It rendered beside stat cards reading 1.7pp (moved) and 1.0pp (unchanged)
    /// — a ratio BELOW 1 sold as superiority, inverting the two numbers next to
    /// it. Native kept printing it verbatim after the web fix, which is the
    /// divergence L2-231 Item 0 found. Two rules make the replacement safe:
    ///
    ///   1. Compare at DISPLAY precision. If both cards show "1.0pp", prose that
    ///      ranks one above the other contradicts the pixels beside it. Rounding
    ///      first makes the tie state fall out, and makes 0.05pp the tolerance
    ///      rather than an invented threshold.
    ///   2. Never infer cause. C111 [P2] showed this aggregate is composition
    ///      sensitive: a synthetic mix where moved was better within BOTH strata
    ///      still inverted in aggregate. An ordering is an ordering. When one
    ///      cannot be computed honestly we say nothing — nothing > unhelpful.
    ///
    /// #8504 — ports web's #6176 (Alex, 2026-09-14): AN ORDERING IS ALSO A CLAIM.
    /// Rule 2 forbade saying trading CAUSED the gap, and "in this sample the
    /// price-moved cohort carries the higher calibration error, 1.3x …" obeyed it
    /// to the letter; a reader still hears "one of these is more accurate". The
    /// two sides are different sets of outcomes (the split is a value inequality
    /// between two stored prices, not a trade), so no ranking between them says
    /// anything about what trading does to a forecast. The figures stay; the
    /// ranking goes, and the sentence says why the two numbers cannot answer the
    /// section's question. #1865: the nouns are now web's `COHORT_NOUNS` —
    /// "Traded" sentence-initially, "untraded" mid-sentence.
    static func describeActivity(
        movedECE: Double?, movedN: Int?,
        unchangedECE: Double?, unchangedN: Int?
    ) -> ActivityComparison {
        guard let m = cohortValue(ece: movedECE, n: movedN),
              let u = cohortValue(ece: unchangedECE, n: unchangedN)
        else { return .unrenderable }

        let movedText = fixed1(m)
        let unchangedText = fixed1(u)
        return ActivityComparison(
            // Still computed, never rendered as a verdict.
            direction: m == u ? .tied : (m > u ? .movedHigher : .unchangedHigher),
            movedText: movedText, unchangedText: unchangedText,
            sentence: "Traded sits at \(movedText)pp and untraded at \(unchangedText)pp. "
                + "These are two different sets of outcomes, not the same forecasts "
                + "measured twice, so the gap between them does not tell you whether "
                + "trading moved a price closer to the truth."
        )
    }
}
