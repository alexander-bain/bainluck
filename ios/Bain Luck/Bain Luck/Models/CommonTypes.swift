import Foundation

// MARK: - Team Data

nonisolated struct TeamData: Decodable, Sendable {
    let primaryColor: String?
    let secondaryColor: String?
    let logoSmall: String?
    let logoLarge: String?
    let record: String?
    let standings: StandingsData?
    let abbreviation: String?
}

nonisolated struct StandingsData: Decodable, Sendable {
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

nonisolated struct CurrentOdds: Decodable, Sendable {
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

nonisolated struct ProbabilityRange: Decodable, Sendable {
    let min: Double?
    let max: Double?
}

nonisolated struct OpeningOdds: Decodable, Sendable {
    let homeProbability: Double?
    let awayProbability: Double?
    let favorite: String?
}

// MARK: - Excitement Index

nonisolated struct EIData: Decodable, Sendable {
    let score: Int?
    let rawScore: Int?
    let status: String?
    let label: String?
    let emoji: String?
    let metadata: EIMetadata?
}

nonisolated struct EIMetadata: Decodable, Sendable {
    let rawEi: Double?
    let leadChanges: Int?
    let comebackFactor: Double?
    let snapshotCount: Int?
}

// MARK: - Highlight

nonisolated struct Highlight: Decodable, Sendable {
    let label: String?
}

// MARK: - Event Metadata

nonisolated struct EventMetadata: Decodable, Sendable {
    let gender: String?
    let level: String?
    let league: String?
    let importance: String?
}

// MARK: - ESPN

nonisolated struct ESPNData: Decodable, Sendable {
    let espnId: String?
    let gameClock: String?
    let period: String?
    let broadcast: String?
    let winProbability: Double?
    let probabilitySources: [String: String]?
}

// MARK: - Win Probability Sources

nonisolated struct WinProbSource: Decodable, Sendable {
    let value: WinProbValue?
    let displayName: String?
    let type: String?
    let color: String?
}

/// Flexible value that handles both numeric (0.65) and string ("987726") from API.
nonisolated enum WinProbValue: Decodable, Sendable {
    case number(Double)
    case string(String)

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let d = try? container.decode(Double.self) {
            self = .number(d)
            return
        }
        if let s = try? container.decode(String.self) {
            self = .string(s)
            return
        }
        throw DecodingError.typeMismatch(WinProbValue.self,
            DecodingError.Context(codingPath: decoder.codingPath,
                                  debugDescription: "Expected Double or String"))
    }

    var doubleValue: Double? {
        switch self {
        case .number(let d): return d
        case .string(let s): return Double(s)
        }
    }
}

// MARK: - Bookmaker Odds

nonisolated struct BookmakerOdds: Decodable, Sendable {
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
    /// Handles both with and without fractional seconds.
    var asDate: Date? {
        Self.iso8601FracFormatter.date(from: self)
            ?? Self.iso8601Formatter.date(from: self)
    }

    private static let iso8601FracFormatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let iso8601Formatter: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
}
