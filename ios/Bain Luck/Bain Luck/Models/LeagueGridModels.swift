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
}

nonisolated struct GridColumn: Decodable, Sendable {
    let key: String
    let label: String
    let order: Int
    let sequential: Bool?
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
    let seed: Int?
    let cells: [String: GridCell]
}

nonisolated struct GridCell: Decodable, Sendable {
    let mergedProbability: Double?
    let sources: [GridCellSource]?
    let trend24h: Double?
}

nonisolated struct GridCellSource: Decodable, Sendable {
    let source: String
    let probability: Double
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
}
