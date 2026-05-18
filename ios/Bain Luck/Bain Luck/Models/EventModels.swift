import Foundation

// MARK: - Event Detail

/// Full event-detail payload for the iOS game detail screen.
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

/// Short standings and stakes summary shown alongside an event matchup.
nonisolated struct StandingsContext: Decodable, Sendable {
    let home: String?
    let away: String?
    let stakes: String?
}

// MARK: - EI Rankings

/// Response containing the highest- and lowest-interest events for EI rankings.
nonisolated struct EIRankingsResponse: Decodable, Sendable {
    let highest: [EIRankedEvent]
    let lowest: [EIRankedEvent]
    let filters: EIRankingsFilters?
}

/// Compact event row used in EI ranking lists.
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

/// Filters echoed by the EI rankings endpoint.
nonisolated struct EIRankingsFilters: Decodable, Sendable {
    let sport: String?
    let limit: Int?
}
