import Foundation

// MARK: - Search Response

nonisolated struct SearchResponse: Decodable, Sendable {
    let query: String
    let results: [SearchEvent]
    let futures: [SearchFuturesMarket]
    let pagination: SearchPagination?
    let sports: [SportFacet]?
    let filters: SearchFilters?
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

// MARK: - Typeahead Response

nonisolated struct TypeaheadResponse: Decodable, Sendable {
    let suggestions: [TypeaheadSuggestion]
    let query: String
}

nonisolated struct TypeaheadSuggestion: Decodable, Identifiable, Sendable {
    let type: String
    let text: String
    let abbreviation: String?
    let logo: String?
    let marketId: Int?
    let marketTier: Int?

    var id: String { "\(type)-\(text)-\(marketId ?? 0)" }
}
