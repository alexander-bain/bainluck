import Foundation
// Watch builds never link the iOS `Bain_Luck` module (they compile `TeamShortName.swift`
// directly via target membership); this conditional import exists solely when `BainLuckTests`
// compiles `WatchSelectedGameModels.swift` alongside `@testable import Bain_Luck`, matching
// `WatchPinsModels12640.swift`.
#if DEBUG && canImport(Bain_Luck)
@testable import Bain_Luck
#endif

/// Public event-detail fields only. Missing readings stay missing; an away or draw
/// probability is never manufactured from a home reading.
nonisolated struct WatchSelectedGame: Codable, Sendable, Identifiable {
    let id: Int
    let homeTeam: String
    let awayTeam: String
    let homeCompactIdentity: WatchCompactTeamIdentity?
    let awayCompactIdentity: WatchCompactTeamIdentity?
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
    let prematchHomeProbability: Double?
    let prematchAwayProbability: Double?
    let prematchDrawProbability: Double?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
    let homePrimaryColor: String?
    let awayPrimaryColor: String?
    let homeSecondaryColor: String?
    let awaySecondaryColor: String?
    /// The crest the event page serves for each side (direction 217's Matchup slot).
    let homeLogoURL: String?
    let awayLogoURL: String?

    var isFinal: Bool { ["completed", "final"].contains(status?.lowercased() ?? "") }
    var isClosed: Bool { status?.lowercased() == "closed" }
    var showsForecast: Bool { !isFinal && !isClosed }
    var stateLabel: String { Self.stateLabel(for: status) }

    /// Match the phone's shared rounding for this selected pair. Served integers
    /// from current_odds may describe a different source than the hero.
    var homeRenderedPercent: Int? {
        guard showsForecast else { return nil }
        // Older saved readings omitted production's `sport` field. Until a
        // refresh identifies the sport, do not assume it is a two-way market.
        guard let sportKey, !sportKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return renderedPercent(homeProbability)
        }
        if DrawPricedWinner.sportPricesADraw(sportKey) || drawProbability != nil {
            return renderedPercent(homeProbability)
        }
        // The shared helper keeps a missing away price missing and uses scalar
        // rounding when these two prices are not a complementary pair.
        return renderedDuelPercents(away: awayProbability, home: homeProbability)[1]
    }

    /// Each side's chance before the game, rounded the way `homeRenderedPercent`
    /// rounds the live pair (direction 209: a final shows the winner's pregame
    /// chance). A missing price stays missing.
    var pregameRenderedPercents: (home: Int?, away: Int?) {
        let drawSport = (sportKey.map { DrawPricedWinner.sportPricesADraw($0) } ?? true) || prematchDrawProbability != nil
        if drawSport {
            return (renderedPercent(prematchHomeProbability), renderedPercent(prematchAwayProbability))
        }
        let pair = renderedDuelPercents(away: prematchAwayProbability, home: prematchHomeProbability)
        return (pair[1], pair[0])
    }

    static func httpsLogo(_ raw: String?) -> String? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines),
              let url = URL(string: raw), url.scheme == "https", url.host != nil else { return nil }
        return raw
    }

    /// Format the already-decided integer once for both the screen and VoiceOver.
    var homeProbabilityText: String? {
        homeRenderedPercent.map {
            (Double($0) / 100).formatted(.percent.precision(.fractionLength(0)))
        }
    }

    static func stateLabel(for status: String?) -> String {
        switch status?.lowercased() {
        case "completed", "final": return "Final"
        case "closed": return "Closed · result unverified"
        case "live", "in_progress": return "Live"
        default: return status?.capitalized ?? "Game state unavailable"
        }
    }

    var isLive: Bool { ["live", "in_progress"].contains(status?.lowercased() ?? "") }
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
        case homeTeamData = "home_team_data", awayTeamData = "away_team_data"
        case homeScore = "home_score", awayScore = "away_score"
        case commenceTime = "commence_time", scoreObservedAt = "score_observed_at"
        case currentOdds = "current_odds", prematchOdds = "prematch_odds"
        case espn, sportKey = "sport_key", sport
        case heroProbability = "hero_probability", heroAway = "hero_probability_away"
        case probabilityObservedAt = "hero_probability_observed_at"
    }
    private struct TeamColorFields: Codable {
        let teamID: Int?
        let abbreviation: String?
        let primaryColor: String?
        let secondaryColor: String?
        var logoSmall: String? = nil
        var logoLarge: String? = nil
        enum CodingKeys: String, CodingKey {
            case teamID = "team_id", abbreviation
            case primaryColor = "primary_color", secondaryColor = "secondary_color"
            case logoSmall = "logo_small", logoLarge = "logo_large"
        }
    }
    private struct Odds: Decodable {
        let homeProbability: Double?
        let awayProbability: Double?
        let drawProbability: Double?
        let projectedHomeScore: Double?
        let projectedAwayScore: Double?
        enum CodingKeys: String, CodingKey {
            case homeProbability = "home_probability", awayProbability = "away_probability"
            case drawProbability = "draw_probability"
            case projectedHomeScore = "projected_home_score", projectedAwayScore = "projected_away_score"
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            func probability(_ key: CodingKeys) -> Double? {
                guard let value = try? c.decode(Double.self, forKey: key),
                      value.isFinite, (0...1).contains(value) else { return nil }
                return value
            }
            func positiveScore(_ key: CodingKeys) -> Double? {
                guard let value = try? c.decode(Double.self, forKey: key),
                      value.isFinite, value > 0 else { return nil }
                return value
            }
            homeProbability = probability(.homeProbability)
            awayProbability = probability(.awayProbability)
            drawProbability = probability(.drawProbability)
            projectedHomeScore = positiveScore(.projectedHomeScore)
            projectedAwayScore = positiveScore(.projectedAwayScore)
        }
    }
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        guard id > 0 else { throw DecodingError.dataCorruptedError(forKey: .id, in: c, debugDescription: "Invalid event id") }
        // Identity and named sides are essential: {} is an invalid response, not
        // an empty selection or an unnamed game the reader must interpret.
        let rawHomeTeam = try c.decode(String.self, forKey: .homeTeam)
        let rawAwayTeam = try c.decode(String.self, forKey: .awayTeam)
        guard !rawHomeTeam.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !rawAwayTeam.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw DecodingError.dataCorruptedError(forKey: .homeTeam, in: c, debugDescription: "Missing team name")
        }
        // Public event detail uses `sport`; older snapshots use `sport_key`.
        let decodedSportKey = (try? c.decode(String.self, forKey: .sport))
            ?? (try? c.decode(String.self, forKey: .sportKey))
        sportKey = decodedSportKey
        // Ruling 194-A — college teams print the school ("Duke", "Alabama",
        // "Gonzaga", "Ole Miss"), never the mascot.
        if TeamShortName.isCollegeSport(sportKey: decodedSportKey) {
            let schools = TeamShortName.shortPair(
                away: rawAwayTeam,
                home: rawHomeTeam,
                sportKey: decodedSportKey
            )
            awayTeam = schools.away
            homeTeam = schools.home
        } else {
            homeTeam = rawHomeTeam
            awayTeam = rawAwayTeam
        }
        // The server attaches canonical identities to their event side; never derive a shorthand.
        homeCompactIdentity = try? c.decode(WatchCompactTeamIdentity.self, forKey: .homeTeamData)
        awayCompactIdentity = try? c.decode(WatchCompactTeamIdentity.self, forKey: .awayTeamData)
        let homeColors = try? c.decode(TeamColorFields.self, forKey: .homeTeamData)
        let awayColors = try? c.decode(TeamColorFields.self, forKey: .awayTeamData)
        homePrimaryColor = homeColors?.primaryColor
        awayPrimaryColor = awayColors?.primaryColor
        homeSecondaryColor = homeColors?.secondaryColor
        awaySecondaryColor = awayColors?.secondaryColor
        homeLogoURL = Self.httpsLogo(homeColors?.logoSmall) ?? Self.httpsLogo(homeColors?.logoLarge)
        awayLogoURL = Self.httpsLogo(awayColors?.logoSmall) ?? Self.httpsLogo(awayColors?.logoLarge)
        homeScore = try? c.decode(Int.self, forKey: .homeScore)
        awayScore = try? c.decode(Int.self, forKey: .awayScore)
        status = try? c.decode(String.self, forKey: .status)
        commenceTime = Self.date(try? c.decode(String.self, forKey: .commenceTime))
        scoreObservedAt = Self.date(try? c.decode(String.self, forKey: .scoreObservedAt))
        let odds = try? c.decode(Odds.self, forKey: .currentOdds)
        let prematch = try? c.decode(Odds.self, forKey: .prematchOdds)
        let rawHero = try? c.decode(Double.self, forKey: .heroProbability)
        let hero = rawHero.flatMap { $0.isFinite && (0...1).contains($0) ? $0 : nil }
        let heroAway = try? c.decode(Double.self, forKey: .heroAway)
        homeProbability = hero.flatMap { (0...1).contains($0) ? $0 : nil } ?? odds?.homeProbability
        awayProbability = hero != nil ? heroAway.flatMap { (0...1).contains($0) ? $0 : nil } : odds?.awayProbability
        // The producer clock dates the hero, never the sportsbook capture or score.
        probabilityObservedAt = hero != nil ? Self.date(try? c.decode(String.self, forKey: .probabilityObservedAt)) : nil
        let espn = try? c.decode(GameState.self, forKey: .espn)
        period = espn?.period
        gameClock = espn?.gameClock
        drawProbability = odds?.drawProbability
        prematchHomeProbability = prematch?.homeProbability
        prematchAwayProbability = prematch?.awayProbability
        prematchDrawProbability = prematch?.drawProbability
        projectedHomeScore = odds?.projectedHomeScore
        projectedAwayScore = odds?.projectedAwayScore
    }
    // Encode the validated public reading in the same shape as its decoder.
    // Observation clocks remain producer clocks across a process restart.
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(homeTeam, forKey: .homeTeam)
        try c.encode(awayTeam, forKey: .awayTeam)
        if homeCompactIdentity != nil || homePrimaryColor != nil || homeSecondaryColor != nil || homeLogoURL != nil {
            try c.encode(
                TeamColorFields(
                    teamID: homeCompactIdentity?.teamID,
                    abbreviation: homeCompactIdentity?.abbreviation,
                    primaryColor: homePrimaryColor,
                    secondaryColor: homeSecondaryColor,
                    logoSmall: homeLogoURL
                ),
                forKey: .homeTeamData
            )
        }
        if awayCompactIdentity != nil || awayPrimaryColor != nil || awaySecondaryColor != nil || awayLogoURL != nil {
            try c.encode(
                TeamColorFields(
                    teamID: awayCompactIdentity?.teamID,
                    abbreviation: awayCompactIdentity?.abbreviation,
                    primaryColor: awayPrimaryColor,
                    secondaryColor: awaySecondaryColor,
                    logoSmall: awayLogoURL
                ),
                forKey: .awayTeamData
            )
        }
        try c.encodeIfPresent(homeScore, forKey: .homeScore)
        try c.encodeIfPresent(awayScore, forKey: .awayScore)
        try c.encodeIfPresent(status, forKey: .status)
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        try c.encodeIfPresent(commenceTime.map(formatter.string), forKey: .commenceTime)
        try c.encodeIfPresent(scoreObservedAt.map(formatter.string), forKey: .scoreObservedAt)
        try c.encodeIfPresent(probabilityObservedAt.map(formatter.string), forKey: .probabilityObservedAt)
        try c.encodeIfPresent(homeProbability, forKey: .heroProbability)
        try c.encodeIfPresent(awayProbability, forKey: .heroAway)
        try c.encodeIfPresent(sportKey, forKey: .sportKey)
        var odds = c.nestedContainer(keyedBy: Odds.CodingKeys.self, forKey: .currentOdds)
        try odds.encodeIfPresent(homeProbability, forKey: .homeProbability)
        try odds.encodeIfPresent(awayProbability, forKey: .awayProbability)
        try odds.encodeIfPresent(drawProbability, forKey: .drawProbability)
        try odds.encodeIfPresent(projectedHomeScore, forKey: .projectedHomeScore)
        try odds.encodeIfPresent(projectedAwayScore, forKey: .projectedAwayScore)
        if prematchHomeProbability != nil || prematchAwayProbability != nil || prematchDrawProbability != nil {
            var pre = c.nestedContainer(keyedBy: Odds.CodingKeys.self, forKey: .prematchOdds)
            try pre.encodeIfPresent(prematchHomeProbability, forKey: .homeProbability)
            try pre.encodeIfPresent(prematchAwayProbability, forKey: .awayProbability)
            try pre.encodeIfPresent(prematchDrawProbability, forKey: .drawProbability)
        }
        var state = c.nestedContainer(keyedBy: GameState.CodingKeys.self, forKey: .espn)
        try state.encodeIfPresent(period, forKey: .period)
        try state.encodeIfPresent(gameClock, forKey: .gameClock)
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

/// Presentation of producer observation age, shared by visible and spoken labels.
/// Fetch time is deliberately not an input.
nonisolated struct WatchObservationAge {
    private let seconds: TimeInterval?

    init(observedAt: Date?, now: Date) {
        let age = observedAt.map { now.timeIntervalSince($0) }
        seconds = age.flatMap { $0.isFinite && $0 >= 0 ? $0 : nil }
    }

    private var unit: (value: Double, short: String, singular: String)? {
        guard let seconds else { return nil }
        if seconds < 60 { return (seconds.rounded(.down), "s", "second") }
        if seconds < 3600 { return ((seconds / 60).rounded(.down), "m", "minute") }
        if seconds < 86400 { return ((seconds / 3600).rounded(.down), "h", "hour") }
        return ((seconds / 86400).rounded(.down), "d", "day")
    }

    var compactText: String? {
        guard let unit else { return nil }
        return "\(unit.value.formatted(.number.grouping(.never).precision(.fractionLength(0))))\(unit.short) ago"
    }

    var spokenText: String? {
        guard let unit else { return nil }
        let count = unit.value.formatted(.number.grouping(.never).precision(.fractionLength(0)))
        return "\(count) \(unit.singular)\(unit.value == 1 ? "" : "s") ago"
    }

    var isStale: Bool { seconds.map { $0 > 120 } ?? false }
}
