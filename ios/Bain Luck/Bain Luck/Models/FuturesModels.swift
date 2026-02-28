import Foundation

// MARK: - Futures Market Detail

struct FuturesMarketDetail: Decodable, Identifiable {
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
    let outcomes: [FuturesOutcome]
}

// MARK: - Futures Outcome

struct FuturesOutcome: Decodable, Identifiable {
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

struct RelatedFuturesResponse: Decodable {
    let eventId: Int
    let homeTeam: String
    let awayTeam: String
    let homeTeamFutures: [RelatedFuture]?
    let awayTeamFutures: [RelatedFuture]?
    let sharedFutures: [RelatedFuture]?
    let summary: String?
}

struct RelatedFuture: Decodable, Identifiable {
    let marketId: Int
    let marketName: String
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
    let matchedPlayer: MatchedPlayer?

    var id: Int { outcomeId }
}

struct MatchedPlayer: Decodable {
    let name: String?
    let headshot: String?
    let espnId: String?
}
