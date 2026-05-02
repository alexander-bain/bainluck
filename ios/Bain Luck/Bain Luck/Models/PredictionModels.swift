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

nonisolated struct CategoryStats: Decodable, Sendable {
    let total: Int
    let correct: Int
    let accuracy: Double
}

nonisolated struct PredictionBadge: Decodable, Sendable {
    let id: String
    let name: String
    let emoji: String
}

nonisolated struct DetailedPredictionStats: Decodable, Sendable {
    let total: Int
    let correct: Int
    let accuracy: Double
    let currentStreak: Int
    let bestStreak: Int
    let byCategory: [String: CategoryStats]
    let badges: [PredictionBadge]
}
