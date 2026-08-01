import Foundation

// MARK: - Numeric-Suffix Decode Contract

/// Why `…24h` / `…7d` properties need explicit `CodingKeys` everywhere.
///
/// The client decodes with `.convertFromSnakeCase`, which capitalises each
/// underscore-separated component after the first. `"24h".capitalized` is
/// `"24H"` — a digit is not a cased character, so ICU title-cases the `h` as if
/// it were the word's first letter. So the backend's `probability_change_24h`
/// arrives as the key `probabilityChange24H`, which matches no property spelled
/// `probabilityChange24h`, and the value is silently dropped on every response.
///
/// `.convertToSnakeCase` is **not** the inverse: the key `probabilityChange24H`
/// encodes back out as `probability_change24_h`. That is fine where the payload
/// is stored opaquely (see `DiscoverLabelingOutcome`) but means an encoded key
/// must never be assumed to equal the backend's key.
///
/// Two rules for any new field whose name ends in digits-plus-letters:
/// 1. give it an explicit `CodingKeys` case whose raw value is the *converted*
///    key (`case foo24h = "foo24H"`), or name the property `foo24H` outright as
///    `LeagueGridModels` does; and
/// 2. mark it `@TolerantNumeric` so a malformed value degrades to `nil` instead
///    of failing the whole item.
///
/// A numeric payload field that decodes to `nil` rather than throwing when the
/// value is absent, null, or the wrong JSON type. One bad number must not erase
/// its own item or that item's healthy siblings.
@propertyWrapper
nonisolated struct TolerantNumeric<Value: Codable & Sendable>: Codable, Sendable {
    let wrappedValue: Value?

    init(wrappedValue: Value?) {
        self.wrappedValue = wrappedValue
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        wrappedValue = try? container.decode(Value.self)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        if let wrappedValue {
            try container.encode(wrappedValue)
        } else {
            try container.encodeNil()
        }
    }
}

extension KeyedDecodingContainer {
    /// A missing key must mean "no value", not a thrown error. The synthesized
    /// `init(from:)` calls `decode(_:forKey:)` (not `decodeIfPresent`) because
    /// the property's declared type is the non-optional wrapper, so without this
    /// overload an absent `…24h` key would fail the whole item.
    func decode<Value>(
        _ type: TolerantNumeric<Value>.Type,
        forKey key: Key
    ) throws -> TolerantNumeric<Value> {
        (try? decodeIfPresent(type, forKey: key)) ?? TolerantNumeric(wrappedValue: nil)
    }
}

// MARK: - Team Data

/// Shared team branding, record, and standings data used across event views.
nonisolated struct TeamData: Decodable, Sendable {
    let primaryColor: String?
    let secondaryColor: String?
    let logoSmall: String?
    let logoLarge: String?
    let record: String?
    let standings: StandingsData?
    let abbreviation: String?
}

/// League standings snapshot for a team, including record and rank context.
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

/// Current consensus odds and derived probabilities for an event.
nonisolated struct CurrentOdds: Decodable, Sendable {
    let capturedAt: String?
    let homeProbability: Double?
    let awayProbability: Double?
    let spread: Double?
    let homeSpread: Double?
    let overUnder: Double?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
    let bookmakerCount: Int?
    let probabilityRange: ProbabilityRange?
}

/// Bookmaker spread around the lowest and highest observed probabilities.
nonisolated struct ProbabilityRange: Decodable, Sendable {
    let min: Double?
    let max: Double?
}

/// Opening market probabilities and favorite metadata for an event.
nonisolated struct OpeningOdds: Decodable, Sendable {
    let homeProbability: Double?
    let awayProbability: Double?
    let favorite: String?
}

// MARK: - Excitement Index

/// Excitement Index score and presentation metadata for an event.
nonisolated struct EIData: Decodable, Sendable {
    let score: Int?
    let rawScore: Int?
    let status: String?
    let label: String?
    let emoji: String?
    let metadata: EIMetadata?
}

/// Raw factors used to explain or debug an Excitement Index score.
nonisolated struct EIMetadata: Decodable, Sendable {
    let rawEi: Double?
    let leadChanges: Int?
    let comebackFactor: Double?
    let snapshotCount: Int?
}

// MARK: - Highlight

/// Short event highlight label surfaced in compact cards and summaries.
nonisolated struct Highlight: Decodable, Sendable {
    let label: String?
}

// MARK: - Event Metadata

/// Supplemental event classification fields such as league, level, and importance.
nonisolated struct EventMetadata: Decodable, Sendable {
    let gender: String?
    let level: String?
    let league: String?
    let importance: String?
}

// MARK: - ESPN

/// ESPN-specific live game context and win probability payload.
nonisolated struct ESPNData: Decodable, Sendable {
    let espnId: String?
    let gameClock: String?
    let period: String?
    let broadcast: String?
    let winProbability: Double?
    let probabilitySources: [String: WinProbValue]?
    let seriesHomeWins: Int?
    let seriesAwayWins: Int?
}

// MARK: - Win Probability Sources

/// One source's win probability value and display metadata.
nonisolated struct WinProbSource: Decodable, Sendable {
    let value: WinProbValue?
    let displayName: String?
    let type: String?
    let color: String?

    init(from decoder: Decoder) throws {
        // The API sends either a bare number (0.65) or a structured object.
        if let container = try? decoder.singleValueContainer(),
           let d = try? container.decode(Double.self) {
            self.value = .number(d)
            self.displayName = nil
            self.type = nil
            self.color = nil
            return
        }
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.value = try container.decodeIfPresent(WinProbValue.self, forKey: .value)
        self.displayName = try container.decodeIfPresent(String.self, forKey: .displayName)
        self.type = try container.decodeIfPresent(String.self, forKey: .type)
        self.color = try container.decodeIfPresent(String.self, forKey: .color)
    }

    private enum CodingKeys: String, CodingKey {
        case value, displayName, type, color
    }
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

/// Per-bookmaker odds snapshot with moneyline, probability, spread, and total data.
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

// MARK: - AnyCodable (used by FeedModels + SearchModels)

enum AnyCodable: Decodable, Sendable {
    case int(Int)
    case double(Double)
    case string(String)
    case bool(Bool)
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let v = try? container.decode(Int.self) { self = .int(v) }
        else if let v = try? container.decode(Double.self) { self = .double(v) }
        else if let v = try? container.decode(String.self) { self = .string(v) }
        else if let v = try? container.decode(Bool.self) { self = .bool(v) }
        else { self = .null }
    }

    var stringValue: String {
        switch self {
        case .int(let v): return "\(v)"
        case .double(let v): return "\(v)"
        case .string(let v): return v
        case .bool(let v): return v ? "true" : "false"
        case .null: return ""
        }
    }
}
