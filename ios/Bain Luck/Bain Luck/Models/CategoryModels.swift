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

// MARK: - Source counts (shared)

nonisolated struct SourceCounts: Decodable, Sendable {
    let kalshi: Int
    let polymarket: Int
}

// MARK: - Politics

nonisolated struct PoliticsResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let themes: PoliticsThemes
    let crossSource: [CrossSourceMatch]?
    let bySource: SourceCounts
}

nonisolated struct PoliticsThemes: Decodable, Sendable {
    let presidential: PoliticsPresidential?
    let congressional: PoliticsCongressional?
    let gubernatorial: PoliticsSimple?
    let policy: PoliticsSimple?
    let scotus: PoliticsSimple?
    let international: PoliticsSimple?
    let other: PoliticsSimple?
}

nonisolated struct PoliticsPresidential: Decodable, Sendable {
    let count: Int
    let headlineQ: String?
    let candidates: [PoliticsCandidate]
    let hasDualSource: Bool?
    let kalshiMarketId: Int?
    let polyMarketId: Int?
    let sideMarkets: [CategoryMarketRow]?
}

nonisolated struct PoliticsCandidate: Decodable, Identifiable, Sendable {
    var id: String { name }
    let name: String
    let party: String
    let kalshi: Double?
    let poly: Double?
    let merged: Double
    let change7d: Double?
    let history: [ProbPoint]?
}

nonisolated struct ProbPoint: Decodable, Sendable {
    let t: String
    let p: Double
}

nonisolated struct PoliticsCongressional: Decodable, Sendable {
    let count: Int
    let markets: [CategoryMarketRow]?
    let chamberControl: ChamberControlData?
    let senateMap: [String: Double]?
}

nonisolated struct ChamberControlData: Decodable, Sendable {
    let senate: ChamberControl?
    let house: ChamberControl?
}

nonisolated struct ChamberControl: Decodable, Sendable {
    let gop: Double
    let dem: Double
    let marketId: Int?
}

nonisolated struct CrossSourceMatch: Decodable, Identifiable, Sendable {
    var id: String { "\(kalshiMarketId)-\(polyMarketId)" }
    let q: String
    let kalshi: Double
    let poly: Double
    let delta: Double
    let category: String?
    let kalshiMarketId: Int
    let polyMarketId: Int
}

nonisolated struct PoliticsSimple: Decodable, Sendable {
    let count: Int
    let markets: [CategoryMarketRow]?
}

// MARK: - Entertainment

nonisolated struct EntertainmentResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let trending: [EntMarketRow]?
    let themes: EntThemes
    let culturalMoments: [EntMarketRow]?
    let bySource: SourceCounts
}

nonisolated struct EntThemes: Decodable, Sendable {
    let music: EntThemeMusic?
    let moviesTv: EntThemeMoviesTV?
    let techCulture: EntThemeTechCulture?
}

nonisolated struct EntMarketRow: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId)-\(q)" }
    let q: String
    let prob: Double
    let src: String
    let marketId: Int
    let externalId: String?
    let kind: String?
    let topOutcomes: [EntOutcome]
    let outcomeCount: Int
    let volume24h: Int?
    let resolutionDate: String?
    let imageUrl: String?
    let hook: String?
}

nonisolated struct EntOutcome: Decodable, Sendable {
    let name: String
    let prob: Double
    let delta24h: Double?
}

nonisolated struct EntThresholdGroup: Decodable, Identifiable, Sendable {
    var id: String { title }
    let title: String
    let imageUrl: String?
    let thresholds: [EntThreshold]
}

nonisolated struct EntThreshold: Decodable, Sendable {
    let label: String
    let prob: Double
    let marketId: Int
}

nonisolated struct EntThemeMusic: Decodable, Sendable {
    let count: Int
    let spotifyRace: [EntMarketRow]?
    let billboardWatch: [EntMarketRow]?
    let billboardGroups: [EntThresholdGroup]?
    let albumDrops: [EntMarketRow]?
    let artistStreaming: [EntMarketRow]?
    let sideMarkets: [EntMarketRow]?
}

nonisolated struct EntThemeMoviesTV: Decodable, Sendable {
    let count: Int
    let rtGroups: [EntThresholdGroup]?
    let rtMarkets: [EntMarketRow]?
    let boxOfficeGroups: [EntThresholdGroup]?
    let boxOffice: [EntMarketRow]?
    let realityTv: [EntMarketRow]?
    let sideMarkets: [EntMarketRow]?
}

nonisolated struct EntThemeTechCulture: Decodable, Sendable {
    let count: Int
    let markets: [EntMarketRow]?
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
