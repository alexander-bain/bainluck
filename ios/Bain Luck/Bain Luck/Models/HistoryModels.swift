import Foundation

// MARK: - Event History Response

nonisolated struct EventHistoryResponse: Decodable, Sendable {
    let eventId: Int
    let homeTeam: String
    let awayTeam: String
    let history: [HistoryPoint]
    let bookmakerHistory: [String: [BookmakerHistoryPoint]]?
    let scoreHistory: [ScoreHistoryPoint]?
    let espnHistory: [ESPNHistoryPoint]?
    let winProbHistory: [String: [WinProbHistoryPoint]]?
    let winProbSources: [String: WinProbSourceInfo]?
    let scoringPlays: [ScoringPlay]?
    let aggregateLine: [AggregateLinePoint]?
    let points: Int?
    let bookmakerCount: Int?
    let snapshotCount: Int?
    let espnSnapshotCount: Int?
}

// MARK: - History Points

nonisolated struct HistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let awayProbability: Double?
    let bookmakerCount: Int?
}

nonisolated struct BookmakerHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let awayProbability: Double?
    let homeMoneyline: Int?
    let awayMoneyline: Int?
}

nonisolated struct ScoreHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeScore: Int
    let awayScore: Int
}

nonisolated struct ESPNHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let gameClock: String?
    let period: String?
    let homeScore: Int?
    let awayScore: Int?
}

nonisolated struct WinProbHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
}

// MARK: - Win Prob Source Info

nonisolated struct WinProbSourceInfo: Decodable, Sendable {
    let displayName: String?
    let type: String?
    let color: String?
    let dashPattern: String?
    let methodology: String?
    let attribution: String?
}

// MARK: - Scoring Play

nonisolated struct ScoringPlay: Decodable, Sendable {
    let timestamp: String?
    let team: String?
    let description: String?
    let type: String?
    let shortText: String?
    let homeScore: Int?
    let awayScore: Int?
    let period: String?
    let gameClock: String?
}

// MARK: - Aggregate Line

nonisolated struct AggregateLinePoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double
    let awayProbability: Double?
}
