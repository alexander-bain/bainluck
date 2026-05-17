import Foundation

// MARK: - Championship Grid Response

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

nonisolated struct GridColumn: Decodable, Sendable {
    let key: String
    let label: String
    let order: Int
    let sequential: Bool?
    let marketId: Int?
}

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

nonisolated struct GridCell: Decodable, Sendable {
    let mergedProbability: Double?
    let sources: [GridCellSource]?
    let trend24h: Double?

    private enum CodingKeys: String, CodingKey {
        case mergedProbability = "merged_probability"
        case sources
        case trend24h = "trend24H"
    }
}

nonisolated struct GridCellSource: Decodable, Sendable {
    let source: String
    let probability: Double
    let marketName: String?
}

nonisolated struct GridMover: Decodable, Sendable, Identifiable {
    var id: String { "\(name)-\(column)" }

    let name: String
    let shortName: String?
    let teamId: Int?
    let column: String
    let change24h: Double
    let direction: String
    let logoUrl: String?
    let primaryColor: String?

    private enum CodingKeys: String, CodingKey {
        case name
        case shortName = "short_name"
        case teamId = "team_id"
        case column
        case change24h = "change24H"
        case direction
        case logoUrl = "logo_url"
        case primaryColor = "primary_color"
    }
}
