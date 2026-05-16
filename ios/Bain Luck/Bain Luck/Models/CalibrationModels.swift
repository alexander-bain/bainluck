import Foundation

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
}

nonisolated struct CalibrationData: Decodable, Sendable {
    let buckets: [CalibrationBucket]
    let totalMarkets: Int
    let totalOutcomes: Int
    let totalWinners: Int?
    let mceCiLower: Double?
    let mceCiUpper: Double?
    let generatedAt: String?
}
