import Foundation

// MARK: - Shared Market Row (Politics + Entertainment)

nonisolated struct CategoryMarketRow: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId ?? 0)-\(q)" }
    let q: String
    let prob: Double
    let src: String
    let marketId: Int?
    let topOutcomes: [CategoryOutcome]
    let outcomeCount: Int
}

nonisolated struct CategoryOutcome: Decodable, Sendable {
    let name: String
    let prob: Double
}

// MARK: - Politics

nonisolated struct PoliticsResponse: Decodable, Sendable {
    let totalMarkets: Int
    let themes: PoliticsThemes
    let bySource: PoliticsBySource
}

nonisolated struct PoliticsThemes: Decodable, Sendable {
    let presidential: PoliticsPresidential?
    let congressional: PoliticsSimple?
    let gubernatorial: PoliticsSimple?
    let policy: PoliticsSimple?
    let scotus: PoliticsSimple?
    let international: PoliticsSimple?
    let other: PoliticsSimple?
}

nonisolated struct PoliticsPresidential: Decodable, Sendable {
    let count: Int
    let headline: PoliticsHeadline?
    let sideMarkets: [CategoryMarketRow]?
}

nonisolated struct PoliticsHeadline: Decodable, Sendable {
    let q: String
    let marketId: Int?
    let src: String
    let candidates: [CategoryOutcome]
    let outcomeCount: Int
}

nonisolated struct PoliticsSimple: Decodable, Sendable {
    let count: Int
    let markets: [CategoryMarketRow]?
}

nonisolated struct PoliticsBySource: Decodable, Sendable {
    let kalshi: Int
    let polymarket: Int
}

// MARK: - Entertainment

nonisolated struct EntertainmentResponse: Decodable, Sendable {
    let totalMarkets: Int
    let sections: [String: EntertainmentSection]
    let bySource: PoliticsBySource
}

nonisolated struct EntertainmentSection: Decodable, Sendable {
    let label: String
    let count: Int
    let markets: [CategoryMarketRow]
}

// MARK: - League Markets

nonisolated struct LeagueMarketsResponse: Decodable, Sendable {
    let sportKey: String
    let sections: [String: [LeagueMarketItem]]
    let totalMarkets: Int
}

nonisolated struct LeagueMarketItem: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let source: String
    let marketTier: Int?
    let category: String?
    let resolutionDate: String?
    let outcomeCount: Int?
    let topOutcomes: [CategoryOutcome]?
    let section: String?
}
