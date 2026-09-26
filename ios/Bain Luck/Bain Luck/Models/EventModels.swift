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
    // #2687 — a `closed` frame means the match ended under the stream; the
    // status has to be able to follow it without a full refetch.
    var status: String?
    let homeScore: Int?
    let awayScore: Int?
    let homeTeamData: TeamData?
    let awayTeamData: TeamData?
    let metadata: EventMetadata?
    let standingsContext: StandingsContext?
    // #2687 — `var` so a pushed SSE frame can write the fresher blend into the
    // model every native surface already reads. See `CurrentOdds`.
    var currentOdds: CurrentOdds?
    let openingOdds: OpeningOdds?
    let bookmakerOdds: [BookmakerOdds]?
    let highlight: Highlight?
    let espn: ESPNData?
    var winProbabilitySources: [String: WinProbSource]?
    let ei: EIData?
    let pulse: EIData?
    let eventTags: [String]?
    /// #4915 — the server's own verdict on a settled game: `"home" | "away" |
    /// "draw"`, decoded from `hero_settled_result` by `.convertFromSnakeCase`.
    ///
    /// The route OMITS the key on a game it cannot grade (`resolve_settled_hero`
    /// returns nothing), so absent is an ordinary state and this is optional
    /// rather than defaulted. Read it through `EventOutcome.resolve` — never
    /// branch on the raw string, or the third outcome goes missing again.
    let heroSettledResult: String?
    /// #6381 — whether the VENUE has already graded this event, decoded from
    /// `venue_settled`. Three states and they are three different answers:
    /// absent (this build's server never asked), `false` (we asked and the
    /// venue said nothing), `true` (it graded this event).
    ///
    /// It is NOT a status and it never becomes one. `status`, the scores and
    /// `started_without_result` are byte-identical beside it — the producer
    /// (`app/utils/venue_settlement.py`) reads `futures_outcomes` rows where
    /// `is_winner IS TRUE AND resolution_source = 'api_settlement'` and writes
    /// nothing. Read it through ``EventState/showsVenueSettledVerdict(_:venueSettled:commenceTime:now:)``.
    let venueSettled: Bool?
    /// #6381 — the graded FULL-CONTEST score, as an outcome NAME and verbatim:
    /// `"Draw 0-0"`, `"Brighton & Hove Albion wins 5-0"`, `"Aryna Sabalenka
    /// wins 2-0"`. `nil` whenever the venue graded only props, which is 370 of
    /// the 426 rows in the issue's own sample.
    ///
    /// 🔴 DO NOT PARSE IT. Its shape differs by sport (soccer names a scoreline,
    /// tennis names sets) and the producer's own contract note says the same
    /// thing to the web half: render it as given. A `nil` here is not a missing
    /// value to fill in — it is the state where saying "settled" without
    /// inventing a score is the whole answer (#6381 acceptance 4).
    let venueSettledResult: String?
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
