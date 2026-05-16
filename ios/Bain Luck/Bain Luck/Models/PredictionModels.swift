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

nonisolated struct Resolution: Decodable, Sendable {
    let marketName: String
    let category: String?
    let guess: String
    let threshold: Int
    let actual: Int
    let correct: Bool
    let createdAt: String?
}

nonisolated struct ResolutionsResponse: Decodable, Sendable {
    let resolutions: [Resolution]
}

// MARK: - Friend Challenges

nonisolated struct ChallengeResponse: Decodable, Sendable {
    let challengeCode: String
    let marketName: String
    let marketId: Int
    let creatorGuess: String
    let threshold: Int
    let friendGuess: String?
    let currentProbability: Double?
    let creatorCorrect: Bool?
    let friendCorrect: Bool?
    let resolvedAt: String?
    let createdAt: String?
}

nonisolated struct AcceptChallengeRequest: Encodable, Sendable {
    let guess: String
}

nonisolated struct AcceptChallengeResponse: Decodable, Sendable {
    let status: String
    let challengeCode: String
    let friendGuess: String
    let actualProbability: Double?
    let creatorCorrect: Bool?
    let friendCorrect: Bool?
}
