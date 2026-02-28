import Foundation

// MARK: - Search Response

struct SearchResponse: Decodable {
    let query: String
    let results: [SearchEvent]
    let futures: [SearchFuturesMarket]
    let pagination: SearchPagination?
    let sports: [SportFacet]?
    let filters: SearchFilters?
}

struct SearchEvent: Decodable, Identifiable {
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

struct SearchFuturesMarket: Decodable, Identifiable {
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

struct SearchFuturesOutcome: Decodable, Identifiable {
    let id: Int
    let name: String
    let probability: Double?
    let americanOdds: Int?
    let rank: Int?
    let movement: Double?
}

struct SearchPagination: Decodable {
    let page: Int
    let perPage: Int
    let totalResults: Int
    let totalPages: Int
    let hasNext: Bool
    let hasPrev: Bool
}

struct SportFacet: Decodable {
    let key: String
    let name: String
    let count: Int
}

struct SearchFilters: Decodable {
    let sport: String?
    let daysBack: Int?
    let includeUpcoming: Bool?
}

// MARK: - Typeahead Response

struct TypeaheadResponse: Decodable {
    let suggestions: [TypeaheadSuggestion]
    let query: String
}

struct TypeaheadSuggestion: Decodable, Identifiable {
    let type: String
    let text: String
    let abbreviation: String?
    let logo: String?
    let marketId: Int?
    let marketTier: Int?

    var id: String { "\(type)-\(text)-\(marketId ?? 0)" }
}
