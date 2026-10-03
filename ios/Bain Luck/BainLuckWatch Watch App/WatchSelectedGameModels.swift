import Foundation

/// Public event-detail fields only. Missing readings stay missing; an away or draw
/// probability is never manufactured from a home reading.
nonisolated struct WatchSelectedGame: Decodable, Sendable, Identifiable {
    let id: Int
    let homeTeam: String
    let awayTeam: String
    let homeScore: Int?
    let awayScore: Int?
    let status: String?
    let commenceTime: Date?
    let scoreObservedAt: Date?
    let probabilityObservedAt: Date?
    let period: String?
    let gameClock: String?
    let sportKey: String?
    let homeProbability: Double?
    let awayProbability: Double?
    let drawProbability: Double?

    var isFinal: Bool { ["completed", "final"].contains(status?.lowercased() ?? "") }
    var isLive: Bool { status?.lowercased() == "live" }
    var liveClockText: String? {
        // The shared formatter normalizes once. Pre-normalizing an inning
        // ("Bottom 3rd" -> "3rd") makes a second pass misread it as Q3.
        PeriodLabel.liveStatusText(period: period, gameClock: gameClock)
    }
    func observationAge(at now: Date) -> TimeInterval? {
        guard let observed = scoreObservedAt, observed <= now else { return nil }
        return now.timeIntervalSince(observed)
    }

    func probabilityAge(at now: Date) -> TimeInterval? {
        guard let observed = probabilityObservedAt, observed <= now else { return nil }
        return now.timeIntervalSince(observed)
    }

    private enum CodingKeys: String, CodingKey {
        case id, status
        case homeTeam = "home_team", awayTeam = "away_team"
        case homeScore = "home_score", awayScore = "away_score"
        case commenceTime = "commence_time", scoreObservedAt = "score_observed_at"
        case currentOdds = "current_odds", espn, sportKey = "sport_key"
        case heroProbability = "hero_probability", heroAway = "hero_probability_away"
        case probabilityObservedAt = "hero_probability_observed_at"
    }
    private struct Odds: Decodable {
        let homeProbability: Double?
        let awayProbability: Double?
        let drawProbability: Double?
        enum CodingKeys: String, CodingKey {
            case homeProbability = "home_probability", awayProbability = "away_probability"
            case drawProbability = "draw_probability"
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            func probability(_ key: CodingKeys) -> Double? {
                guard let value = try? c.decode(Double.self, forKey: key),
                      value.isFinite, (0...1).contains(value) else { return nil }
                return value
            }
            homeProbability = probability(.homeProbability)
            awayProbability = probability(.awayProbability)
            drawProbability = probability(.drawProbability)
        }
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        guard id > 0 else { throw DecodingError.dataCorruptedError(forKey: .id, in: c, debugDescription: "Invalid event id") }
        // Identity and named sides are essential: {} is an invalid response, not
        // an empty selection or an unnamed game the reader must interpret.
        homeTeam = try c.decode(String.self, forKey: .homeTeam)
        awayTeam = try c.decode(String.self, forKey: .awayTeam)
        guard !homeTeam.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !awayTeam.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw DecodingError.dataCorruptedError(forKey: .homeTeam, in: c, debugDescription: "Missing team name")
        }
        homeScore = try? c.decode(Int.self, forKey: .homeScore)
        awayScore = try? c.decode(Int.self, forKey: .awayScore)
        status = try? c.decode(String.self, forKey: .status)
        commenceTime = Self.date(try? c.decode(String.self, forKey: .commenceTime))
        scoreObservedAt = Self.date(try? c.decode(String.self, forKey: .scoreObservedAt))
        let odds = try? c.decode(Odds.self, forKey: .currentOdds)
        let rawHero = try? c.decode(Double.self, forKey: .heroProbability)
        let hero = rawHero.flatMap { $0.isFinite && (0...1).contains($0) ? $0 : nil }
        let heroAway = try? c.decode(Double.self, forKey: .heroAway)
        homeProbability = hero.flatMap { (0...1).contains($0) ? $0 : nil } ?? odds?.homeProbability
        awayProbability = hero != nil ? heroAway.flatMap { (0...1).contains($0) ? $0 : nil } : odds?.awayProbability
        // The producer clock dates the hero, never the sportsbook capture or score.
        probabilityObservedAt = hero != nil ? Self.date(try? c.decode(String.self, forKey: .probabilityObservedAt)) : nil
        sportKey = try? c.decode(String.self, forKey: .sportKey)
        let espn = try? c.decode(GameState.self, forKey: .espn)
        period = espn?.period
        gameClock = espn?.gameClock
        drawProbability = odds?.drawProbability
    }
    private struct GameState: Decodable {
        let period: String?
        let gameClock: String?
        enum CodingKeys: String, CodingKey { case period, gameClock = "game_clock" }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            period = try? c.decode(String.self, forKey: .period)
            gameClock = try? c.decode(String.self, forKey: .gameClock)
        }
    }
    private static func date(_ value: String?) -> Date? {
        guard let value else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: value) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: value)
    }
}
