import Foundation

// MARK: - Championship Grid Response

struct ChampionshipGridResponse: Codable, Sendable {
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

struct GridColumn: Codable, Sendable {
    let key: String
    let label: String
    let order: Int
    let sequential: Bool?
}

struct GridTeam: Codable, Sendable, Identifiable {
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

struct GridCell: Codable, Sendable {
    let mergedProbability: Double?
    let sources: [GridCellSource]?
    let trend24H: Double?
}

struct GridCellSource: Codable, Sendable {
    let source: String
    let probability: Double
}

struct GridMover: Codable, Sendable, Identifiable {
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
