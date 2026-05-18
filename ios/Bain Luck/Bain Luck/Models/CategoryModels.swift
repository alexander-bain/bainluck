import Foundation

// MARK: - Shared Market Row (Politics + Entertainment)

/// Shared category market row used by politics and entertainment dashboards.
nonisolated struct CategoryMarketRow: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId ?? 0)-\(q)" }
    let q: String
    let prob: Double
    let src: String
    let marketId: Int?
    let topOutcomes: [CategoryOutcome]
    let outcomeCount: Int
}

/// Outcome probability embedded in a category market row.
nonisolated struct CategoryOutcome: Decodable, Sendable {
    let name: String
    let prob: Double
}

// MARK: - Source counts (shared)

/// Count of available markets by prediction market source.
nonisolated struct SourceCounts: Decodable, Sendable {
    let kalshi: Int
    let polymarket: Int
}

// MARK: - Politics

/// Politics dashboard response with themed sections and source comparison.
nonisolated struct PoliticsResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let themes: PoliticsThemes
    let crossSource: [CrossSourceMatch]?
    let bySource: SourceCounts
}

/// Theme buckets returned by the politics dashboard.
nonisolated struct PoliticsThemes: Decodable, Sendable {
    let presidential: PoliticsPresidential?
    let congressional: PoliticsCongressional?
    let gubernatorial: PoliticsSimple?
    let policy: PoliticsSimple?
    let scotus: PoliticsSimple?
    let international: PoliticsSimple?
    let other: PoliticsSimple?
}

/// Presidential market section with candidates and related markets.
nonisolated struct PoliticsPresidential: Decodable, Sendable {
    let count: Int
    let headlineQ: String?
    let candidates: [PoliticsCandidate]
    let hasDualSource: Bool?
    let kalshiMarketId: Int?
    let polyMarketId: Int?
    let sideMarkets: [CategoryMarketRow]?
}

/// Candidate probability row for presidential markets.
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

/// Historical probability point for a politics candidate.
nonisolated struct ProbPoint: Decodable, Sendable {
    let t: String
    let p: Double
}

/// Congressional market section with chamber control context.
nonisolated struct PoliticsCongressional: Decodable, Sendable {
    let count: Int
    let markets: [CategoryMarketRow]?
    let chamberControl: ChamberControlData?
    let senateMap: [String: Double]?
}

/// Senate and House control probabilities.
nonisolated struct ChamberControlData: Decodable, Sendable {
    let senate: ChamberControl?
    let house: ChamberControl?
}

/// Party control probabilities for one chamber.
nonisolated struct ChamberControl: Decodable, Sendable {
    let gop: Double
    let dem: Double
    let marketId: Int?
}

/// Matched Kalshi and Polymarket rows for the same political question.
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

/// Simple politics theme containing a market count and rows.
nonisolated struct PoliticsSimple: Decodable, Sendable {
    let count: Int
    let markets: [CategoryMarketRow]?
}

// MARK: - Entertainment

/// Entertainment dashboard response with themed market sections.
nonisolated struct EntertainmentResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let trending: [EntMarketRow]?
    let themes: EntThemes
    let culturalMoments: [EntMarketRow]?
    let bySource: SourceCounts
}

/// Theme buckets returned by the entertainment dashboard.
nonisolated struct EntThemes: Decodable, Sendable {
    let music: EntThemeMusic?
    let moviesTv: EntThemeMoviesTV?
    let techCulture: EntThemeTechCulture?
}

/// Entertainment market row with outcomes, media, and hook metadata.
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

/// Outcome probability and movement for an entertainment market.
nonisolated struct EntOutcome: Decodable, Sendable {
    let name: String
    let prob: Double
    let delta24h: Double?
}

/// Group of related entertainment threshold markets for one title or entity.
nonisolated struct EntThresholdGroup: Decodable, Identifiable, Sendable {
    var id: String { title }
    let title: String
    let imageUrl: String?
    let thresholds: [EntThreshold]
}

/// One threshold probability inside an entertainment threshold group.
nonisolated struct EntThreshold: Decodable, Sendable {
    let label: String
    let prob: Double
    let marketId: Int
}

/// Music-focused entertainment market groups.
nonisolated struct EntThemeMusic: Decodable, Sendable {
    let count: Int
    let spotifyRace: [EntMarketRow]?
    let billboardWatch: [EntMarketRow]?
    let billboardGroups: [EntThresholdGroup]?
    let albumDrops: [EntMarketRow]?
    let artistStreaming: [EntMarketRow]?
    let sideMarkets: [EntMarketRow]?
}

/// Movie and TV-focused entertainment market groups.
nonisolated struct EntThemeMoviesTV: Decodable, Sendable {
    let count: Int
    let rtGroups: [EntThresholdGroup]?
    let rtMarkets: [EntMarketRow]?
    let boxOfficeGroups: [EntThresholdGroup]?
    let boxOffice: [EntMarketRow]?
    let realityTv: [EntMarketRow]?
    let sideMarkets: [EntMarketRow]?
}

/// Tech and culture entertainment market group.
nonisolated struct EntThemeTechCulture: Decodable, Sendable {
    let count: Int
    let markets: [EntMarketRow]?
}

// MARK: - League Markets

/// League-level futures markets grouped into display sections.
nonisolated struct LeagueMarketsResponse: Decodable, Sendable {
    let sportKey: String
    let sections: [String: [LeagueMarketItem]]
    let totalMarkets: Int
}

/// Single league market row in a league market section.
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
