import Foundation

// MARK: - Event Detail

struct EventDetail: Decodable, Identifiable {
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
}

// MARK: - Standings Context

struct StandingsContext: Decodable {
    let home: String?
    let away: String?
}

// MARK: - EI Rankings

struct EIRankingsResponse: Decodable {
    let highest: [EIRankedEvent]
    let lowest: [EIRankedEvent]
    let filters: EIRankingsFilters?
}

struct EIRankedEvent: Decodable, Identifiable {
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

struct EIRankingsFilters: Decodable {
    let sport: String?
    let limit: Int?
}
