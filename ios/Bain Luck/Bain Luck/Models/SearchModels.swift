import Foundation

// MARK: - Search Response

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

nonisolated struct SearchFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let americanOdds: Int?
    let rank: Int?
    let movement: Double?
}

nonisolated struct SearchPagination: Decodable, Sendable {
    let page: Int
    let perPage: Int
    let totalResults: Int
    let totalPages: Int
    let hasNext: Bool
    let hasPrev: Bool
}

nonisolated struct SportFacet: Decodable, Sendable {
    let key: String
    let name: String
    let count: Int
}

nonisolated struct SearchFilters: Decodable, Sendable {
    let sport: String?
    let daysBack: Int?
    let includeUpcoming: Bool?
}

// MARK: - Faceted Events Response

nonisolated struct FacetedEventsResponse: Decodable, Sendable {
    let total: Int
    let page: Int
    let perPage: Int
    let filters: [String]
    let events: [FeedEventData]
    let facets: [String: [FacetTag]]
}

// MARK: - Faceted Futures Response

nonisolated struct FacetedFuturesResponse: Decodable, Sendable {
    let total: Int
    let page: Int
    let perPage: Int
    let filters: [String]
    let markets: [FacetedFuturesMarket]
    let facets: [String: [FacetTag]]
}

nonisolated struct FacetedFuturesMarket: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let llmSportCategory: String?
    let source: String?
    let resolutionDate: String?
    let marketTags: [String]?
    let topOutcomes: [FacetedFuturesOutcome]?
    let outcomeCount: Int?
}

nonisolated struct FacetedFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let movement: Double?
}

nonisolated struct FacetTag: Decodable, Sendable {
    let tag: String
    let count: Int
}

// MARK: - Typeahead Response

nonisolated struct TypeaheadResponse: Decodable, Sendable {
    let suggestions: [TypeaheadSuggestion]
    let query: String
    let didYouMean: String?
}

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

nonisolated struct TeamPageResponse: Decodable, Sendable {
    let team: TeamPageTeam
    let upcomingEvents: [SearchEvent]
    let recentEvents: [SearchEvent]
    let futures: [TeamFutureItem]
    let championshipPath: [ChampionshipPathEntry]
}

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
