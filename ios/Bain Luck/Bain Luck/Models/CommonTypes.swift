import Foundation

// MARK: - Team Data

struct TeamData: Decodable {
    let primaryColor: String?
    let secondaryColor: String?
    let logoSmall: String?
    let logoLarge: String?
    let record: String?
    let standings: StandingsData?
}

struct StandingsData: Decodable {
    let pct: String?
    let wins: Int?
    let losses: Int?
    let points: Int?
    let streak: String?
    let division: String?
    let confRank: Int?
    let goalsFor: Int?
    let conference: String?
    let homeRecord: String?
    let roadRecord: String?
    let goalsAgainst: Int?
}

// MARK: - Odds

struct CurrentOdds: Decodable {
    let capturedAt: String?
    let homeProbability: Double?
    let awayProbability: Double?
    let spread: Double?
    let overUnder: Double?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
    let bookmakerCount: Int?
    let probabilityRange: ProbabilityRange?
}

struct ProbabilityRange: Decodable {
    let min: Double?
    let max: Double?
}

struct OpeningOdds: Decodable {
    let homeProbability: Double?
    let awayProbability: Double?
    let favorite: String?
}

// MARK: - Excitement Index

struct EIData: Decodable {
    let score: Int?
    let rawScore: Int?
    let status: String?
    let label: String?
    let emoji: String?
    let metadata: EIMetadata?
}

struct EIMetadata: Decodable {
    let rawEi: Double?
    let leadChanges: Int?
    let comebackFactor: Double?
    let snapshotCount: Int?
}

// MARK: - Highlight

struct Highlight: Decodable {
    let label: String?
}

// MARK: - Event Metadata

struct EventMetadata: Decodable {
    let gender: String?
    let level: String?
    let league: String?
    let importance: String?
}

// MARK: - ESPN

struct ESPNData: Decodable {
    let espnId: String?
    let gameClock: String?
    let period: String?
    let broadcast: String?
    let winProbability: Double?
    let probabilitySources: [String: Double]?
}

// MARK: - Win Probability Sources

struct WinProbSource: Decodable {
    let value: Double?
    let displayName: String?
    let type: String?
    let color: String?
}

// MARK: - Bookmaker Odds

struct BookmakerOdds: Decodable {
    let bookmaker: String?
    let homeMoneyline: Int?
    let awayMoneyline: Int?
    let homeProbability: Double?
    let awayProbability: Double?
    let capturedAt: String?
    let spread: Double?
    let overUnder: Double?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
}

// MARK: - String Date Extension

extension String {
    /// Parse an ISO 8601 date string into a Date.
    var asDate: Date? {
        Self.iso8601Formatter.date(from: self)
    }

    private static let iso8601Formatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
}
