import Foundation

nonisolated struct PredictionRequest: Encodable, Sendable {
    let marketId: Int
    let guess: String
    let threshold: Int
    let actualProbability: Double
    let correct: Bool
    let category: String?
}

nonisolated struct PredictionStats: Decodable, Sendable {
    let total: Int
    let correct: Int
    let accuracy: Double
    let currentStreak: Int
    let bestStreak: Int
}
