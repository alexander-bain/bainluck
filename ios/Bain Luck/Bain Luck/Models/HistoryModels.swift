import Foundation

// MARK: - Event History Response

/// Historical probability, score, and source data for an event.
nonisolated struct EventHistoryResponse: Decodable, Sendable {
    let eventId: Int
    let homeTeam: String
    let awayTeam: String
    let completedAt: String?
    let status: String?
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

/// Aggregated odds history point for an event.
nonisolated struct HistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let awayProbability: Double?
    let bookmakerCount: Int?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
}

/// Bookmaker-specific odds history point for an event.
nonisolated struct BookmakerHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let awayProbability: Double?
    let homeMoneyline: Int?
    let awayMoneyline: Int?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
}

/// Score snapshot captured during an event.
nonisolated struct ScoreHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeScore: Int
    let awayScore: Int
}

/// ESPN win-probability and game-state snapshot.
nonisolated struct ESPNHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let gameClock: String?
    let period: String?
    let homeScore: Int?
    let awayScore: Int?
}

/// Source-specific win-probability snapshot with optional game state.
nonisolated struct WinProbHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let gameState: WinProbGameState?
}

/// Game-state fields paired with a win-probability snapshot.
nonisolated struct WinProbGameState: Decodable, Sendable {
    let period: String?
    let clock: String?
    let inning: Int?
    let homeScore: Int?
    let awayScore: Int?
}

// MARK: - Win Prob Source Info

/// Display and attribution metadata for a win-probability source.
nonisolated struct WinProbSourceInfo: Decodable, Sendable {
    let displayName: String?
    let type: String?
    let color: String?
    let dashPattern: String?
    let methodology: String?
    let attribution: String?
}

// MARK: - Scoring Play

/// Scoring event shown on the event history timeline.
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

/// Aggregated home and away probability point for charting.
nonisolated struct AggregateLinePoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double
    let awayProbability: Double?
}
