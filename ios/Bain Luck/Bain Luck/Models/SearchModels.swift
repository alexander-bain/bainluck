import Foundation

// MARK: - Search Response

/// Search results response containing teams, events, futures, and facets.
nonisolated struct SearchResponse: Decodable, Sendable {
    let query: String
    let teams: [SearchTeam]?
    let results: [SearchEvent]
    let futures: [SearchFuturesMarket]
    let pagination: SearchPagination?
    let sports: [SportFacet]?
    let filters: SearchFilters?
    let didYouMean: String?
}

/// Event result returned by search endpoints.
nonisolated struct SearchEvent: Decodable, Identifiable, Sendable {
    let id: Int
    let externalId: String?
    let sport: String?
    let homeTeam: String
    let awayTeam: String
    let commenceTime: String?
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    let metadata: EventMetadata?
    let espn: ESPNData?
    let winProbabilitySources: [String: WinProbSource]?
    let ei: EIData?
    let pulse: EIData?
    let currentOdds: CurrentOdds?
    let bookmakerOdds: [BookmakerOdds]?
    let highlight: Highlight?
    let openingOdds: OpeningOdds?
}

/// Futures market result returned by search endpoints.
nonisolated struct SearchFuturesMarket: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let sport: String?
    let sportName: String?
    let category: String?
    let llmSportCategory: String?
    let status: String?
    let source: String?
    let resolutionDate: String?
    let topOutcomes: [SearchFuturesOutcome]?
    let outcomeCount: Int?
    let updatedAt: String?
}

/// Top outcome for a futures market search result.
nonisolated struct SearchFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let americanOdds: Int?
    let rank: Int?
    let movement: Double?
}

/// Pagination metadata for search results.
nonisolated struct SearchPagination: Decodable, Sendable {
    let page: Int
    let perPage: Int
    let totalResults: Int
    let totalPages: Int
    let hasNext: Bool
    let hasPrev: Bool
}

/// Sport facet count returned with search filters.
nonisolated struct SportFacet: Decodable, Sendable {
    let key: String
    let name: String
    let count: Int
}

/// Filters applied to a search request.
nonisolated struct SearchFilters: Decodable, Sendable {
    let sport: String?
    let daysBack: Int?
    let includeUpcoming: Bool?
}

// MARK: - Faceted Events Response

/// Paginated event results with facet counts for browse views.
nonisolated struct FacetedEventsResponse: Decodable, Sendable {
    let total: Int
    let page: Int
    let perPage: Int
    let filters: [String]
    let events: [FeedEventData]
    let facets: [String: [FacetTag]]
}

// MARK: - Faceted Futures Response

/// Paginated futures market results with facet counts for browse views.
nonisolated struct FacetedFuturesResponse: Decodable, Sendable {
    let total: Int
    let page: Int
    let perPage: Int
    let filters: [String]
    let markets: [FacetedFuturesMarket]
    let facets: [String: [FacetTag]]
}

/// Futures market row returned by faceted browsing.
nonisolated struct FacetedFuturesMarket: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let llmSportCategory: String?
    let source: String?
    let resolutionDate: String?
    let marketTags: [String]?
    let topOutcomes: [FacetedFuturesOutcome]?
    let outcomeCount: Int?
    let imageUrl: String?
    let hookDescription: String?
}

/// Outcome row embedded in a faceted futures market.
nonisolated struct FacetedFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let movement: Double?
}

/// Named facet value and count used by browse filters.
nonisolated struct FacetTag: Decodable, Sendable {
    let tag: String
    let count: Int
}

// MARK: - Futures Movers Response

/// Response from the /api/futures/movers endpoint.
nonisolated struct FuturesMoversResponse: Decodable, Sendable {
    let movers: [FuturesMover]
    let timeframeHours: Int
}

/// Single outcome with significant probability movement.
nonisolated struct FuturesMover: Decodable, Identifiable, Sendable {
    let outcomeId: Int
    let name: String
    let marketId: Int
    let marketName: String?
    let currentProbability: Double?
    let probabilityChange24h: Double?
    let currentAmericanOdds: Int?
    let rank: Int?
    let rankChange24h: Int?

    var id: Int { outcomeId }
}

// MARK: - Typeahead Response

/// Typeahead suggestion response for the active query.
nonisolated struct TypeaheadResponse: Decodable, Sendable {
    let suggestions: [TypeaheadSuggestion]
    let query: String
    let didYouMean: String?
}

/// Trending search queries for search discovery.
nonisolated struct TrendingSearchesResponse: Decodable, Sendable {
    let trending: [TrendingQuery]
}

/// Single trending query and its usage count.
nonisolated struct TrendingQuery: Decodable, Identifiable, Sendable {
    let query: String
    let count: Int
    var id: String { query }
}

/// Search typeahead suggestion for a team, event, or market.
nonisolated struct TypeaheadSuggestion: Decodable, Identifiable, Sendable {
    let type: String
    let text: String
    let abbreviation: String?
    let logo: String?
    let teamId: Int?
    let teamSlug: String?
    let sportKey: String?
    let eventId: Int?
    let status: String?
    let commenceTime: String?
    let marketId: Int?
    let marketTier: Int?
    let marketTypeLabel: String?

    var id: String { "\(type)-\(text)-\(marketId ?? teamId ?? eventId ?? 0)" }
}

/// Team result returned by search.
nonisolated struct SearchTeam: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let slug: String?
    let abbreviation: String?
    let logo: String?
    let record: String?
    let sportKey: String?
}

// MARK: - Team Page

/// Full team page response with games, futures, and championship path.
nonisolated struct TeamPageResponse: Decodable, Sendable {
    let team: TeamPageTeam
    let upcomingEvents: [SearchEvent]
    let recentEvents: [SearchEvent]
    let futures: [TeamFutureItem]
    let championshipPath: [ChampionshipPathEntry]
}

/// Team identity and display metadata for a team page.
nonisolated struct TeamPageTeam: Decodable, Sendable {
    let id: Int
    let slug: String
    let name: String
    let abbreviation: String?
    let sportKey: String?
    let sportName: String?
    let primaryColor: String?
    let secondaryColor: String?
    let logoSmall: String?
    let logoLarge: String?
    let record: String?
    let standings: [String: AnyCodable]?
}

// TeamFutureItem defined in FuturesModels.swift (shared with team page + futures browsing)

/// One stage in a team's championship path summary.
nonisolated struct ChampionshipPathEntry: Decodable, Identifiable, Sendable {
    let tier: Int
    let label: String
    let marketName: String
    let marketId: Int
    let probability: Double?
    let rank: Int?
    let movement: Double?

    var id: Int { tier }
}

// AnyCodable moved to CommonTypes.swift
