import Foundation

// MARK: - Championship Grid Response

/// Championship grid response for a league, including teams, columns, and movers.
nonisolated struct ChampionshipGridResponse: Decodable, Sendable {
    let league: String
    let name: String
    let season: String?
    let columns: [GridColumn]
    let teams: [GridTeam]
    let groupedTeams: [String: [GridTeam]]?
    let movers: [GridMover]
    let teamCount: Int
    let lastUpdated: String?
    let sourcesAvailable: [String]
    let championshipMarketId: Int?
}

/// Column definition for one stage in a championship grid.
nonisolated struct GridColumn: Decodable, Sendable {
    let key: String
    let label: String
    let order: Int
    let sequential: Bool?
    let marketId: Int?
}

/// Team row and probabilities across championship grid columns.
nonisolated struct GridTeam: Decodable, Sendable, Identifiable {
    var id: String { name }

    let name: String
    let shortName: String?
    let teamId: Int?
    let logoUrl: String?
    let primaryColor: String?
    let secondaryColor: String?
    let record: String?
    let conference: String?
    let division: String?
    let region: String?
    let seed: Int?
    let cells: [String: GridCell]
}

/// Probability cell for a team at one championship stage.
nonisolated struct GridCell: Decodable, Sendable {
    let mergedProbability: Double?
    let sources: [GridCellSource]?
    let trend24H: Double?
}

/// Source-specific probability inside a championship grid cell.
nonisolated struct GridCellSource: Decodable, Sendable {
    let source: String
    let probability: Double
    let marketName: String?
}

/// Team with notable 24-hour movement in a championship grid column.
nonisolated struct GridMover: Decodable, Sendable, Identifiable {
    var id: String { "\(name)-\(column)" }

    let name: String
    let shortName: String?
    let teamId: Int?
    let column: String
    let change24H: Double
    let direction: String
    let logoUrl: String?
    let primaryColor: String?
}
