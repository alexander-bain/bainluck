import Foundation

/// Public display state for one canonical game. ActivityKit delivery is a separate owner.
nonisolated struct GameActivitySnapshot: Codable, Hashable, Sendable {
    nonisolated enum Lifecycle: String, Codable, Hashable, Sendable {
        case scheduled, live, suspended, final, closed, unknown
    }

    let eventID: Int
    let homeTeam: String
    let awayTeam: String
    let homeScore: Int?
    let awayScore: Int?
    let lifecycle: Lifecycle
    let homeRenderedPercent: Int?
    let scoreObservedAt: Date?
    let probabilityObservedAt: Date?
    /// #10864 — display fields for the Live Activity's matchup layout. All are
    /// optional: a pushed state from a server that predates them carries none,
    /// and the views fall back to the team names above. `awayRenderedPercent`
    /// exists only for two-way sports (a priced draw leaves it empty), and the
    /// period is a label only — a running clock would freeze between updates.
    let awayRenderedPercent: Int?
    let homeAbbreviation: String?
    let awayAbbreviation: String?
    let homeColorHex: String?
    let awayColorHex: String?
    let periodLabel: String?

    private enum CodingKeys: String, CodingKey {
        case eventID, homeTeam, awayTeam, homeScore, awayScore, lifecycle
        case homeRenderedPercent, scoreObservedAt, probabilityObservedAt
        case awayRenderedPercent, homeAbbreviation, awayAbbreviation
        case homeColorHex, awayColorHex, periodLabel
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        eventID = try c.decode(Int.self, forKey: .eventID)
        homeTeam = try c.decode(String.self, forKey: .homeTeam)
        awayTeam = try c.decode(String.self, forKey: .awayTeam)
        homeScore = try c.decodeIfPresent(Int.self, forKey: .homeScore)
        awayScore = try c.decodeIfPresent(Int.self, forKey: .awayScore)
        lifecycle = try c.decode(Lifecycle.self, forKey: .lifecycle)
        homeRenderedPercent = try c.decodeIfPresent(Int.self, forKey: .homeRenderedPercent)
        scoreObservedAt = try c.decodeIfPresent(Date.self, forKey: .scoreObservedAt)
        probabilityObservedAt = try c.decodeIfPresent(Date.self, forKey: .probabilityObservedAt)
        let hasForecast = lifecycle == .live || lifecycle == .scheduled
        // Display-only fields are cleaned, never fatal: a bad badge or colour
        // must not cost the reader the score and chance that decoded fine.
        let away = (try? c.decodeIfPresent(Int.self, forKey: .awayRenderedPercent)) ?? nil
        let hasHome = homeRenderedPercent != nil
        awayRenderedPercent = away.flatMap { hasForecast && hasHome && (0...100).contains($0) ? $0 : nil }
        homeAbbreviation = Self.cleanBadge((try? c.decodeIfPresent(String.self, forKey: .homeAbbreviation)) ?? nil)
        awayAbbreviation = Self.cleanBadge((try? c.decodeIfPresent(String.self, forKey: .awayAbbreviation)) ?? nil)
        homeColorHex = Self.cleanHex((try? c.decodeIfPresent(String.self, forKey: .homeColorHex)) ?? nil)
        awayColorHex = Self.cleanHex((try? c.decodeIfPresent(String.self, forKey: .awayColorHex)) ?? nil)
        periodLabel = Self.cleanPeriod((try? c.decodeIfPresent(String.self, forKey: .periodLabel)) ?? nil,
                                       lifecycle: lifecycle)
        guard eventID > 0,
              !homeTeam.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !awayTeam.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              homeScore.map({ $0 >= 0 }) ?? true, awayScore.map({ $0 >= 0 }) ?? true,
              homeRenderedPercent.map({ (0...100).contains($0) && hasForecast }) ?? true,
              probabilityObservedAt == nil || homeRenderedPercent != nil,
              scoreObservedAt == Self.validDate(scoreObservedAt),
              probabilityObservedAt == Self.validDate(probabilityObservedAt) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                   debugDescription: "Invalid game activity snapshot"))
        }
    }

    /// Supply clocks from the producers of these exact values, never fetch/receipt time.
    /// A typed lifecycle keeps the widget independent of phone status parsing.
    init?(eventID: Int, homeTeam: String, awayTeam: String, lifecycle: Lifecycle,
          homeScore: Int? = nil, awayScore: Int? = nil,
          homeProbability: Double? = nil, awayProbability: Double? = nil,
          drawProbability: Double? = nil, sport: String? = nil,
          scoreObservedAt: Date? = nil, probabilityObservedAt: Date? = nil,
          homeAbbreviation: String? = nil, awayAbbreviation: String? = nil,
          homeColorHex: String? = nil, awayColorHex: String? = nil,
          periodLabel: String? = nil) {
        let home = homeTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        let away = awayTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        guard eventID > 0, !home.isEmpty, !away.isEmpty else { return nil }
        self.eventID = eventID
        self.homeTeam = home
        self.awayTeam = away
        self.homeScore = homeScore.flatMap { $0 >= 0 ? $0 : nil }
        self.awayScore = awayScore.flatMap { $0 >= 0 ? $0 : nil }
        self.lifecycle = lifecycle
        self.scoreObservedAt = Self.validDate(scoreObservedAt)
        let validHome = Self.validProbability(homeProbability)
        let validAway = Self.validProbability(awayProbability)
        let hasSport = sport?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        if lifecycle == .live || lifecycle == .scheduled {
            if !hasSport || DrawPricedWinner.sportPricesADraw(sport) || Self.validProbability(drawProbability) != nil {
                homeRenderedPercent = renderedPercent(validHome)
                awayRenderedPercent = nil
            } else {
                let duel = renderedDuelPercents(away: validAway, home: validHome)
                homeRenderedPercent = duel[1]
                awayRenderedPercent = duel[1] == nil ? nil : duel[0]
            }
            self.probabilityObservedAt = homeRenderedPercent == nil ? nil : Self.validDate(probabilityObservedAt)
        } else {
            homeRenderedPercent = nil
            awayRenderedPercent = nil
            self.probabilityObservedAt = nil
        }
        self.homeAbbreviation = Self.cleanBadge(homeAbbreviation)
        self.awayAbbreviation = Self.cleanBadge(awayAbbreviation)
        self.homeColorHex = Self.cleanHex(homeColorHex)
        self.awayColorHex = Self.cleanHex(awayColorHex)
        self.periodLabel = Self.cleanPeriod(periodLabel, lifecycle: lifecycle)
    }

    var isTerminal: Bool { lifecycle == .final || lifecycle == .closed }
    var isFinal: Bool { lifecycle == .final }
    var statusLabel: String {
        switch lifecycle {
        case .scheduled: return "Upcoming"
        case .live: return "Live"
        case .suspended: return "Paused"
        case .final: return "Final"
        case .closed: return "Closed · result unverified"
        case .unknown: return "Game state unavailable"
        }
    }
    var matchup: String { "\(awayTeam) at \(homeTeam)" }
    var probabilityText: String? {
        homeRenderedPercent.map { (Double($0) / 100).formatted(.percent.precision(.fractionLength(0))) }
    }
    var probabilityLabel: String? { probabilityText.map { "\(homeTeam) win · \($0)" } }
    var scoreText: String? {
        guard let awayScore, let homeScore else { return nil }
        return "\(awayTeam) \(awayScore), \(homeTeam) \(homeScore)"
    }
    var resultText: String? {
        guard isTerminal else { return nil }
        guard isFinal else { return "Closed · result unverified" }
        guard let scoreText else { return "Final score unavailable" }
        // Scores alone do not establish the winner of shootout or aggregate fixtures.
        return "Final · \(scoreText)"
    }
    func scoreAge(at now: Date) -> TimeInterval? { Self.age(scoreObservedAt, at: now) }
    func probabilityAge(at now: Date) -> TimeInterval? { Self.age(probabilityObservedAt, at: now) }

    /// A served team badge ("KC"), never a guess: one to six visible characters.
    private static func cleanBadge(_ value: String?) -> String? {
        guard let text = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              (1...6).contains(text.count) else { return nil }
        return text
    }
    /// A served team colour as `#RRGGBB`, or nothing.
    private static func cleanHex(_ value: String?) -> String? {
        guard let text = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              text.range(of: #"^#?[0-9A-Fa-f]{6}$"#, options: .regularExpression) != nil else { return nil }
        return (text.hasPrefix("#") ? text : "#" + text).uppercased()
    }
    /// The period chip ("Q4", "2nd Half") while a game is under way; nothing otherwise.
    private static func cleanPeriod(_ value: String?, lifecycle: Lifecycle) -> String? {
        guard lifecycle == .live || lifecycle == .suspended,
              let text = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              (1...24).contains(text.count) else { return nil }
        return text
    }
    private static func validProbability(_ value: Double?) -> Double? {
        value.flatMap { $0.isFinite && (0...1).contains($0) ? $0 : nil }
    }
    private static func validDate(_ date: Date?) -> Date? {
        date.flatMap { $0.timeIntervalSinceReferenceDate.isFinite ? $0 : nil }
    }
    private static func age(_ observed: Date?, at now: Date) -> TimeInterval? {
        guard let observed, now.timeIntervalSinceReferenceDate.isFinite, observed <= now else { return nil }
        return now.timeIntervalSince(observed)
    }
}
