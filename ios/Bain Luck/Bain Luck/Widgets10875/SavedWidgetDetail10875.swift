import Foundation

// #10875 — the fields of the two public detail endpoints the saved-item widget
// reads, and nothing else. `GET /api/events/{id}` and `GET /api/futures/{id}`
// are what the event and market pages load (`APIClient.fetchEvent` /
// `fetchFuturesDetail`); neither needs a credential, so the widget never holds
// one. Keys arrive snake_case and are decoded with `.convertFromSnakeCase`.
//
// Every field is optional except identity: an absent key is "not established",
// never zero, false or now.

nonisolated struct SavedWidgetEventDetail10875: Decodable, Equatable, Sendable {
    let id: Int
    let sport: String?
    let homeTeam: String
    let awayTeam: String
    let status: String?
    let commenceTime: String?
    let startIsTbd: Bool?
    let homeScore: Int?
    let awayScore: Int?
    let currentOdds: SavedWidgetEventOdds10875?
    let heroProbability: Double?
    let heroProbabilityAway: Double?
    let heroProbabilitySource: String?
    /// The quote's own clock — the instant the price behind the pair was
    /// observed, not when anyone fetched it.
    let heroProbabilityObservedAt: String?
    let heroSettledResult: String?
    let venueSettled: Bool?
    let venueSettledResult: String?
    let venueClosedNoWinner: Bool?
    let homeTeamData: SavedWidgetTeamData10875?
    let awayTeamData: SavedWidgetTeamData10875?
}

nonisolated struct SavedWidgetEventOdds10875: Decodable, Equatable, Sendable {
    let homeProbability: Double?
    let awayProbability: Double?
    let homeRenderedPercent: Int?
    let awayRenderedPercent: Int?
}

nonisolated struct SavedWidgetTeamData10875: Decodable, Equatable, Sendable {
    let abbreviation: String?
}

nonisolated struct SavedWidgetMarketDetail10875: Decodable, Equatable, Sendable {
    let id: Int
    let name: String
    let status: String?
    /// The venue (`polymarket`, `kalshi`, …). Read only to decide whether a
    /// resolved market without `settlement_display` is a server that predates
    /// it (#698).
    let source: String?
    let leadOutcomeId: Int?
    let outcomes: [SavedWidgetMarketOutcome10875]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        source = (try? c.decodeIfPresent(String.self, forKey: .source)) ?? nil
        leadOutcomeId = try c.decodeIfPresent(Int.self, forKey: .leadOutcomeId)
        // One malformed leg must not blank the reader's chosen one.
        var legs = try c.nestedUnkeyedContainer(forKey: .outcomes)
        var decoded: [SavedWidgetMarketOutcome10875] = []
        while !legs.isAtEnd {
            if let leg = try? legs.decode(SavedWidgetMarketOutcome10875.self) {
                decoded.append(leg)
            } else {
                _ = try? legs.decode(WidgetSkipOne10875.self)
            }
        }
        outcomes = decoded
    }

    init(id: Int, name: String, status: String?, source: String? = nil, leadOutcomeId: Int?,
         outcomes: [SavedWidgetMarketOutcome10875]) {
        self.id = id
        self.name = name
        self.status = status
        self.source = source
        self.leadOutcomeId = leadOutcomeId
        self.outcomes = outcomes
    }

    private enum CodingKeys: String, CodingKey {
        case id, name, status, source, leadOutcomeId, outcomes
    }
}

nonisolated struct SavedWidgetMarketOutcome10875: Decodable, Equatable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let isWinner: Bool?
    let resolutionSource: String?
    let lastUpdated: String?
    /// A verified answer's oldest included observation, when served.
    let observedAt: String?
    /// #698, resolved Polymarket markets only: what this row may say about its
    /// own result. Absent everywhere else and on older servers. Read only
    /// through `SavedWidgetReadingRules10875.settledResult`.
    let settlementDisplay: SavedWidgetSettlementDisplay10875?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        probability = try c.decodeIfPresent(Double.self, forKey: .probability)
        isWinner = try c.decodeIfPresent(Bool.self, forKey: .isWinner)
        resolutionSource = try c.decodeIfPresent(String.self, forKey: .resolutionSource)
        lastUpdated = try c.decodeIfPresent(String.self, forKey: .lastUpdated)
        observedAt = try c.decodeIfPresent(String.self, forKey: .observedAt)
        // A contract of the wrong shape reads as absent, never fails the leg:
        // a failed leg is skipped, and the reader's choice would then read
        // "No longer listed".
        settlementDisplay = (try? c.decodeIfPresent(SavedWidgetSettlementDisplay10875.self, forKey: .settlementDisplay)) ?? nil
    }

    private enum CodingKeys: String, CodingKey {
        case id, name, probability, isWinner, resolutionSource, lastUpdated, observedAt, settlementDisplay
    }
}

/// `settlement_display` on one `/api/futures/{id}` outcome: `{"verdict",
/// "basis"}`. Each field is read leniently; a missing or non-string verdict is
/// unknown, so an unexpected value can never invent a result.
nonisolated struct SavedWidgetSettlementDisplay10875: Decodable, Equatable, Sendable {
    let verdict: String?
    let basis: String?

    init(verdict: String?, basis: String?) {
        self.verdict = verdict
        self.basis = basis
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        verdict = (try? c.decodeIfPresent(String.self, forKey: .verdict)) ?? nil
        basis = (try? c.decodeIfPresent(String.self, forKey: .basis)) ?? nil
    }

    private enum CodingKeys: String, CodingKey {
        case verdict, basis
    }
}

/// Advances past a leg that does not decode.
nonisolated struct WidgetSkipOne10875: Decodable {}

nonisolated enum SavedWidgetDetailDecoding10875 {
    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    /// ISO 8601 with or without fractional seconds; production serves both.
    static func date(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: raw) { return date }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: raw)
    }
}
