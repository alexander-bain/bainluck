import Foundation

// MARK: - Line Movement Response

nonisolated struct LineMovementResponse: Decodable, Sendable {
    let eventId: Int
    let movements: [Movement]
    let explanation: String?
    let disagreementExplanation: String?
    let disagreementData: DisagreementData?
    let context: LineMovementContext?
    let cached: Bool?
    let createdAt: String?
}

nonisolated struct Movement: Decodable, Identifiable, Sendable {
    let change: Double
    let context: String?
    let isMajor: Bool?
    let direction: String?
    let magnitude: Double?
    let timestampEnd: String?
    let homeProbAfter: Double?
    let timestampStart: String?
    let homeProbBefore: Double?

    var id: String { "\(timestampStart ?? "")-\(change)" }
}

nonisolated struct DisagreementData: Decodable, Sendable {
    let sportsbooks: Double?
    let predictionMarkets: Double?
    let gap: Double?
    let sources: [String: Double]?
}

nonisolated struct LineMovementContext: Decodable, Sendable {
    let newsCount: Int?
    let hasGameState: Bool?
    let hasTeamStats: Bool?
    let injuriesCount: Int?
}
