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
nonisolated struct SmallSampleCategory: Decodable, Sendable, Identifiable {
    let category: String
    let outcomes: Int
    var id: String { category }
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
}
