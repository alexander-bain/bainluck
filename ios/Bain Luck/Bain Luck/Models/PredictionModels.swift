import Foundation

/// Payload recording a user's higher/lower prediction for a market.
nonisolated struct PredictionRequest: Encodable, Sendable {
    let marketId: Int
    let guess: String
    let threshold: Int
    let actualProbability: Double
    let correct: Bool
    let category: String?
}

/// Summary accuracy and streak stats for user predictions.
nonisolated struct PredictionStats: Decodable, Sendable {
    let total: Int
    let correct: Int
    let accuracy: Double
    let currentStreak: Int
    let bestStreak: Int
}

/// Accuracy stats for predictions in one category.
nonisolated struct CategoryStats: Decodable, Sendable {
    let total: Int
    let correct: Int
    let accuracy: Double
}

/// Achievement badge earned from prediction activity.
nonisolated struct PredictionBadge: Decodable, Sendable {
    let id: String
    let name: String
    let emoji: String
}

/// Expanded prediction stats including category breakdowns and badges.
nonisolated struct DetailedPredictionStats: Decodable, Sendable {
    let total: Int
    let correct: Int
    let accuracy: Double
    let currentStreak: Int
    let bestStreak: Int
    let byCategory: [String: CategoryStats]
    let badges: [PredictionBadge]
}

/// Resolved prediction with guessed and actual probabilities.
nonisolated struct Resolution: Decodable, Sendable {
    let marketName: String
    let category: String?
    let guess: String
    let threshold: Int
    let actual: Int
    let correct: Bool
    let createdAt: String?
}

/// List response for resolved user predictions.
nonisolated struct ResolutionsResponse: Decodable, Sendable {
    let resolutions: [Resolution]
}

// MARK: - Friend Challenges

/// State of a friend challenge for a shared market prediction.
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

/// Payload for accepting a friend challenge.
nonisolated struct AcceptChallengeRequest: Encodable, Sendable {
    let guess: String
}

/// Backend result after accepting a friend challenge.
nonisolated struct AcceptChallengeResponse: Decodable, Sendable {
    let status: String
    let challengeCode: String
    let friendGuess: String
    let actualProbability: Double?
    let creatorCorrect: Bool?
    let friendCorrect: Bool?
}
