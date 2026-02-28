import Foundation

// MARK: - Event History Response

struct EventHistoryResponse: Decodable {
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

struct HistoryPoint: Decodable {
    let timestamp: String
    let homeProbability: Double
    let awayProbability: Double
    let bookmakerCount: Int?
}

struct BookmakerHistoryPoint: Decodable {
    let timestamp: String
    let homeProbability: Double?
    let awayProbability: Double?
    let homeMoneyline: Int?
    let awayMoneyline: Int?
}

struct ScoreHistoryPoint: Decodable {
    let timestamp: String
    let homeScore: Int
    let awayScore: Int
}

struct ESPNHistoryPoint: Decodable {
    let timestamp: String
    let homeProbability: Double?
    let gameClock: String?
    let period: String?
}

struct WinProbHistoryPoint: Decodable {
    let timestamp: String
    let homeProbability: Double
}

// MARK: - Win Prob Source Info

struct WinProbSourceInfo: Decodable {
    let displayName: String?
    let type: String?
    let color: String?
    let dashPattern: String?
    let methodology: String?
    let attribution: String?
}

// MARK: - Scoring Play

struct ScoringPlay: Decodable {
    let timestamp: String?
    let team: String?
    let description: String?
    let homeScore: Int?
    let awayScore: Int?
    let period: String?
    let gameClock: String?
}

// MARK: - Aggregate Line

struct AggregateLinePoint: Decodable {
    let timestamp: String
    let homeProbability: Double
    let awayProbability: Double
}
