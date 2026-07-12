import Foundation

/// Pure, unit-testable calibration math ported 1:1 from the web reference
/// (`frontend/lib/calibrationMath.ts` + the `/calibration` page aggregation).
///
/// This exists to fix #894 (native vs web calibration mismatch): the native tab
/// used to re-derive headline numbers with its OWN formulas, so it disagreed with
/// the web page. The API's precomputed `by_category`/`by_source` rows cover the
/// *all-markets* cohort, but the web page's DEFAULT view is the *well-traded*
/// cohort (`price_moved != false`) computed client-side — so simply reading the
/// precomputed rows would REINTRODUCE the mismatch. Instead native mirrors the
/// web's exact client-side aggregation here (same rounding, same ECE/MCE/Brier),
/// guaranteeing the two surfaces print the same digits.
///
/// ECE is the n-weighted headline metric (reflects the outcomes users actually
/// see); MCE is the equal-weighted worst-bucket-sensitivity number. All error
/// values are in percentage points (pp).
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

    /// Equal-weighted mean |error| (pp). Worst-bucket sensitive. Web `mce`.
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
}
