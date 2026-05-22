import Foundation

// MARK: - Team Progression (Championship Path)

/// Championship-path probabilities for both teams in an event.
nonisolated struct TeamProgressionResponse: Decodable, Sendable {
    let eventId: Int
    let league: String?
    let leagueName: String?
    let homeTeam: TeamProgressionData?
    let awayTeam: TeamProgressionData?
}

/// Team metadata and stage probabilities for a championship path.
nonisolated struct TeamProgressionData: Decodable, Sendable {
    let name: String
    let shortName: String?
    let logoUrl: String?
    let record: String?
    let conference: String?
    let stages: [ProgressionStageData]
}

/// Probability and movement for one stage in a team's progression path.
nonisolated struct ProgressionStageData: Decodable, Sendable {
    let key: String
    let label: String
    let probability: Double?
    let trend24h: Double?
}

// MARK: - Game Markets Response

/// Full set of prediction markets attached to a game detail page.
nonisolated struct GameMarketsResponse: Decodable, Sendable {
    let eventId: Int
    let homeTeam: String?
    let awayTeam: String?
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    let playerProps: [GameMarketPlayerProp]?
    let spreads: [GameMarketOutcome]?
    let totals: [GameMarketOutcome]?
    let teamTotals: [GameMarketOutcome]?
    let periodMarkets: [GameMarketOutcome]?
    let other: [GameMarketOther]?
    let pace: GameMarketPace?
}

/// Miscellaneous game market outcome that does not fit a primary section.
nonisolated struct GameMarketOther: Decodable, Identifiable, Sendable {
    var id: String { "\(marketName)-\(outcomeName)" }
    let marketName: String
    let outcomeName: String
    let probability: Double?
    let source: String?
}

/// Live scoring pace context for totals and in-game markets.
nonisolated struct GameMarketPace: Decodable, Sendable {
    let totalScored: Int?
    let projectedTotal: Double?
    let fractionElapsed: Double?
    let timeRemainingDisplay: String?
}

/// Player prop market with threshold, probability, and player metadata.
nonisolated struct GameMarketPlayerProp: Decodable, Identifiable, Sendable {
    var id: String { "\(marketName)-\(outcomeName)" }
    let marketName: String
    let outcomeName: String
    let threshold: Double?
    let overProbability: Double?
    let source: String?
    let movement: Double?
    let playerHeadshot: String?
    let playerTeam: String?
}

/// Generic game market outcome used for spreads, totals, team totals, and periods.
nonisolated struct GameMarketOutcome: Decodable, Identifiable, Sendable {
    var id: String { "\(marketName)-\(outcomeName)" }
    let marketName: String
    let outcomeName: String
    let probability: Double?
    let source: String?
    let threshold: Double?
    let overProbability: Double?
    let marketType: String?
    let movement: Double?
    let period: String?
}

// MARK: - Futures Market Detail

/// Detailed futures market response including metadata and all outcomes.
nonisolated struct FuturesMarketDetail: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let description: String?
    let sport: String?
    let sportName: String?
    let category: String?
    let llmSportCategory: String?
    let status: String?
    let source: String?
    let externalId: String?
    let mutuallyExclusive: Bool?
    let commenceTime: String?
    let resolutionDate: String?
    let updatedAt: String?
    let outcomeCount: Int?
    let bookmakers: [String]?
    let outcomes: [FuturesOutcome]
    let hookDescription: String?
    let imageUrl: String?
}

// MARK: - Futures Outcome

/// Individual outcome within a futures market.
nonisolated struct FuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let americanOdds: Int?
    let rank: Int?
    let rankChange24h: Int?
    let probabilityChange24h: Double?
    let openingProbability: Double?
    let openingAmericanOdds: Int?
    let isWinner: Bool?
    let lastUpdated: String?
}

// MARK: - Related Futures Response

/// Outcome row for a series-level market related to an event.
nonisolated struct SeriesMarketOutcome: Decodable, Identifiable, Sendable {
    let outcomeId: Int
    let name: String
    let probability: Double?
    let probabilityChange24h: Double?

    var id: Int { outcomeId }
}

/// Series-level market related to an event detail page.
nonisolated struct SeriesMarket: Decodable, Identifiable, Sendable {
    let marketId: Int
    let marketName: String
    let source: String?
    let status: String?
    let resolutionDate: String?
    let outcomes: [SeriesMarketOutcome]

    var id: Int { marketId }
}

/// Related futures and context shown alongside a game event.
nonisolated struct RelatedFuturesResponse: Decodable, Sendable {
    let eventId: Int
    let homeTeam: String
    let awayTeam: String
    let homeTeamFutures: [RelatedFuture]?
    let awayTeamFutures: [RelatedFuture]?
    let seriesMarkets: [SeriesMarket]?
    let sharedFutures: [RelatedFuture]?
    let summary: String?
    let eventStatus: String?
    let boxScore: [String: [String: Double]]?
    let gamePeriod: String?
    let gameClock: String?
}

/// Team, player, or shared futures outcome related to a specific event.
nonisolated struct RelatedFuture: Decodable, Identifiable, Sendable {
    let marketId: Int
    let marketName: String
    let cleanLabel: String?
    let displayCategory: String?
    let mergeGroup: String?
    let playoffStage: String?
    let playoffStageType: String?
    let stageOrder: Int?
    let marketTier: Int?
    let category: String?
    let source: String?
    let outcomeId: Int
    let outcomeName: String
    let probability: Double?
    let americanOdds: Int?
    let probabilityChange24h: Double?
    let openingProbability: Double?
    let rank: Int?
    let relevanceScore: Double?
    let relevanceReason: String?
    let lastUpdated: String?
    let nextUpdateExpected: String?
    let resolutionDate: String?
    let bookmakerCount: Int?
    let allSources: [String]?
    let matchedPlayer: MatchedPlayer?

    var id: Int { outcomeId }
}

/// Matched player metadata attached to a related future.
nonisolated struct MatchedPlayer: Decodable, Sendable {
    let name: String?
    let headshot: String?
    let espnId: String?
}

// MARK: - Team Futures (My Stuff)

/// Collection of futures tied to the user's followed teams.
nonisolated struct TeamFuturesResponse: Decodable, Sendable {
    let items: [TeamFutureItem]
    let teamIds: [Int]
    let totalCount: Int
}

/// Single futures outcome associated with one of the user's teams.
nonisolated struct TeamFutureItem: Decodable, Identifiable, Sendable {
    let outcomeId: Int
    let outcomeName: String
    let marketId: Int
    let marketName: String
    let marketTier: Int?
    let category: String?
    let source: String?
    let probability: Double?
    let probabilityChange24h: Double?
    let rank: Int?
    let totalOutcomes: Int?
    let resolutionDate: String?
    let matchedTeam: TeamFutureTeam?
    let canonicalMarketKey: String?

    var id: Int { outcomeId }
}

/// Team metadata attached to a team futures item.
nonisolated struct TeamFutureTeam: Decodable, Sendable {
    let id: Int
    let name: String
    let logoSmall: String?
    let primaryColor: String?
}

// MARK: - Probability Timeline

/// Time-series probability response for a futures market.
nonisolated struct ProbabilityTimelineResponse: Decodable, Sendable {
    let marketId: Int
    let marketName: String
    let sportCategory: String?
    let source: String?
    let hours: Int
    let top: Int
    let bucketSeconds: Int
    let timeline: [TimelineEntry]
    let outcomes: [TimelineOutcomeMeta]
}

/// Probability snapshot for all tracked outcomes at one timestamp.
nonisolated struct TimelineEntry: Decodable, Sendable {
    let timestamp: String
    let outcomes: [String: Double]
}

/// Display metadata for an outcome included in a probability timeline.
nonisolated struct TimelineOutcomeMeta: Decodable, Identifiable, Sendable {
    let id: Int?
    let name: String
    let currentProbability: Double?
    let rank: Int?
    let probabilityChange24h: Double?
    let openingProbability: Double?
    // Team enrichment
    let teamId: Int?
    let logoSmall: String?
    let logoLarge: String?
    let primaryColor: String?
    let secondaryColor: String?
    let abbreviation: String?
    let record: String?
    let location: String?
    let espnId: String?

    // CodingKeys not needed — camelCase matches JSON snake_case via keyDecodingStrategy
}
