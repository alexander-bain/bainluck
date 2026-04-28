import Foundation

// MARK: - Event Detail

nonisolated struct EventDetail: Decodable, Identifiable, Sendable {
    let id: Int
    let externalId: String?
    let sport: String?
    let homeTeam: String
    let awayTeam: String
    let commenceTime: String?
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    let homeTeamData: TeamData?
    let awayTeamData: TeamData?
    let metadata: EventMetadata?
    let standingsContext: StandingsContext?
    let currentOdds: CurrentOdds?
    let openingOdds: OpeningOdds?
    let bookmakerOdds: [BookmakerOdds]?
    let highlight: Highlight?
    let espn: ESPNData?
    let winProbabilitySources: [String: WinProbSource]?
    let ei: EIData?
    let pulse: EIData?
    let eventTags: [String]?
}

// MARK: - Standings Context

nonisolated struct StandingsContext: Decodable, Sendable {
    let home: String?
    let away: String?
    let stakes: String?
}

// MARK: - EI Rankings

nonisolated struct EIRankingsResponse: Decodable, Sendable {
    let highest: [EIRankedEvent]
    let lowest: [EIRankedEvent]
    let filters: EIRankingsFilters?
}

nonisolated struct EIRankedEvent: Decodable, Identifiable, Sendable {
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
    let ei: EIData?
    let pulse: EIData?
    let rank: Int
}

nonisolated struct EIRankingsFilters: Decodable, Sendable {
    let sport: String?
    let limit: Int?
}
