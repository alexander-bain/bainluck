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

// MARK: - Line Movement

/// Cached odds movement explanation for an event detail page.
nonisolated struct LineMovementResponse: Decodable, Sendable {
    let eventId: Int
    let movements: [LineMovement]
    let explanation: String?
    let disagreementExplanation: String?
    let disagreementData: LineMovementDisagreement?
    let context: LineMovementContext?
    let cached: Bool?
    let createdAt: String?

    var hasDisplayContent: Bool {
        hasText(explanation) || hasText(disagreementExplanation)
    }

    private func hasText(_ value: String?) -> Bool {
        guard let value else { return false }
        return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
}

/// One sustained odds move detected from sportsbook snapshots.
nonisolated struct LineMovement: Decodable, Sendable {
    let timestampStart: String
    let timestampEnd: String
    let homeProbBefore: Double
    let homeProbAfter: Double
    let change: Double
    let magnitude: Double
    let direction: String
    let context: String?
    let isMajor: Bool
}

/// Prediction-market disagreement against sportsbook consensus.
nonisolated struct LineMovementDisagreement: Decodable, Sendable {
    let sportsbookHomeProb: Double
    let predictionMarketHomeProb: Double
    let source: String
    let divergence: Double
}

/// Metadata about evidence used to generate the movement explanation.
nonisolated struct LineMovementContext: Decodable, Sendable {
    let injuriesCount: Int?
    let newsCount: Int?
    let hasGameState: Bool?
    let hasTeamStats: Bool?
    let scoringPlaysCount: Int?
}
