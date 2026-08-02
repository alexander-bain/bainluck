import Foundation

/// Aggregated calibration metrics for one probability bucket.
nonisolated struct CalibrationBucket: Decodable, Sendable {
    let bucketIdx: Int
    let source: String
    let category: String
    let priceMoved: Bool?
    let n: Int
    let winners: Int
    let sumProb: Double
    let sumSqErr: Double
    let ciLower: Double?
    let ciUpper: Double?
    let avgProb: Double?
}

/// A market category held out of the published curve because it hasn't cleared
/// the minimum-sample bar yet. Powers the "niche & long-shot" honest note.
///
/// Queue 299 (#1012) made the disposition machine-readable: a cohort whose
/// defective rows were excluded read-side can legitimately fall UNDER the bar,
/// and the honest answer then is "parked", not a quietly missing chart. The
/// three added fields are optional — a leaner or older payload carries only
/// category + outcomes, and native must not hard-require the rest.
nonisolated struct SmallSampleCategory: Decodable, Sendable, Identifiable {
    let category: String
    let outcomes: Int
    let disposition: String?
    let publishBar: Int?
    let ece: Double?
    var id: String { category }

    /// Queue 299's declared value. Compared as data, never inferred from the count.
    static let parkedBelowPublishBar = "parked_below_publish_bar"

    var isParked: Bool { disposition == Self.parkedBelowPublishBar }
}

/// Queue 297: how fresh the served snapshot is.
///
/// Absent — or present with a status other than `stale` — means the payload is
/// current. When it IS stale the surface MUST say so and date it: a dated
/// last-good is honest, an undated one presented as live is not. Native had no
/// decode for this at all, so every degraded payload rendered as though it were
/// current (L2-231 Item 0's web/native divergence).
nonisolated struct CalibrationCacheState: Decodable, Sendable {
    let status: String
    let reason: String?
    let generatedAt: String?
    let ageS: Double?

    var isStale: Bool { status == "stale" }
}

/// One entry in the data-corrections trust log (payload v2 `corrections[]`).
nonisolated struct CalibrationCorrection: Decodable, Sendable, Identifiable {
    let date: String
    let title: String
    let rows: Int?
    let description: String
    var id: String { date + "|" + title }
}

/// The date span the calibration payload covers.
nonisolated struct CalibrationDateRange: Decodable, Sendable {
    let start: String?
    let end: String?
}

/// Top-level calibration response with bucket data and summary error metrics.
///
/// Payload v2 (#999 §F) carries the sample gate, the held-out categories, and the
/// corrections log so web + native render the same story from the same numbers.
/// All added fields are optional: the in-request route fallback ships a leaner
/// payload than the precompute cache, so native must not hard-require them.
nonisolated struct CalibrationData: Decodable, Sendable {
    let buckets: [CalibrationBucket]
    let totalMarkets: Int
    let totalOutcomes: Int
    let totalWinners: Int?
    let mceCiLower: Double?
    let mceCiUpper: Double?
    let mceClosingLine: Double?
    let mceOpeningPrice: Double?
    let generatedAt: String?
    // Payload v2 additions (all optional — see route fallback note above).
    let minCategoryOutcomes: Int?
    let smallSampleCategories: [SmallSampleCategory]?
    let corrections: [CalibrationCorrection]?
    let dateRange: CalibrationDateRange?
    // L2-231 Item 2 / Queue 297 §3: the freshness envelope and the payload's own
    // population contract. Both optional so a lean route-fallback payload still
    // decodes — but a payload that omits `populationVersion` is treated as
    // UNVERIFIED rather than assumed compatible (see `CalibrationViewModel`).
    let cache: CalibrationCacheState?
    let populationVersion: String?
}
