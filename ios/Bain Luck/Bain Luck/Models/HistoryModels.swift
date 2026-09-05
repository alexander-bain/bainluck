import Foundation

// MARK: - Event History Response

/// Historical probability, score, and source data for an event.
nonisolated struct EventHistoryResponse: Decodable, Sendable {
    let eventId: Int
    let homeTeam: String
    let awayTeam: String
    let completedAt: String?
    let status: String?
    let history: [HistoryPoint]
    let bookmakerHistory: [String: [BookmakerHistoryPoint]]?
    let scoreHistory: [ScoreHistoryPoint]?
    let espnHistory: [ESPNHistoryPoint]?
    let winProbHistory: [String: [WinProbHistoryPoint]]?
    let winProbSources: [String: WinProbSourceInfo]?
    let scoringPlays: [ScoringPlay]?
    /// The Moments Engine's confident subset (#1168 consumer 3, #3196). Optional
    /// because it is additive: an older cached payload has no key at all.
    let moments: [GameMomentPoint]?
    let aggregateLine: [AggregateLinePoint]?
    let points: Int?
    let bookmakerCount: Int?
    let snapshotCount: Int?
    let espnSnapshotCount: Int?
}

// MARK: - History Points

/// Aggregated odds history point for an event.
nonisolated struct HistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let awayProbability: Double?
    let bookmakerCount: Int?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
}

/// Bookmaker-specific odds history point for an event.
nonisolated struct BookmakerHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let awayProbability: Double?
    let homeMoneyline: Int?
    let awayMoneyline: Int?
    let projectedHomeScore: Double?
    let projectedAwayScore: Double?
}

/// Score snapshot captured during an event.
nonisolated struct ScoreHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeScore: Int
    let awayScore: Int
}

/// ESPN win-probability and game-state snapshot.
nonisolated struct ESPNHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let gameClock: String?
    let period: String?
    let homeScore: Int?
    let awayScore: Int?
}

/// Source-specific win-probability snapshot with optional game state.
nonisolated struct WinProbHistoryPoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double?
    let gameState: WinProbGameState?
}

/// Game-state fields paired with a win-probability snapshot.
nonisolated struct WinProbGameState: Decodable, Sendable {
    let period: String?
    let clock: String?
    let inning: Int?
    let homeScore: Int?
    let awayScore: Int?
}

// MARK: - Win Prob Source Info

/// Display and attribution metadata for a win-probability source.
nonisolated struct WinProbSourceInfo: Decodable, Sendable {
    let displayName: String?
    let type: String?
    let color: String?
    let dashPattern: String?
    let methodology: String?
    let attribution: String?
}

// MARK: - Scoring Play

/// Scoring event shown on the event history timeline.
nonisolated struct ScoringPlay: Decodable, Sendable {
    let timestamp: String?
    let team: String?
    let description: String?
    let type: String?
    let shortText: String?
    let homeScore: Int?
    let awayScore: Int?
    let period: String?
    let gameClock: String?
}

// MARK: - Game Moment

/// One confident "this is what moved the line" annotation from the Moments Engine
/// (#1168): a scoring event joined to a win-probability swing, offline, and gated
/// server-side.
///
/// EVERY FIELD IS OPTIONAL AND THAT IS THE POINT. This type sits inside
/// `EventHistoryResponse`, so a single moment row that throws takes the whole
/// history payload down and blanks the chart — the reader loses the curve to gain
/// nothing (gotcha #42: one bad item must never wipe the pass). Optional fields make
/// the element unable to throw, which is also why there is no tolerant per-element
/// decoder here: it would be unreachable code. The rows that cannot be drawn are
/// dropped in exactly one place, `OddsChartView.chartMoments(from:points:)`, which is
/// pure and tested.
///
/// The `confidence >= 0.5` gate and the `moments:surface_enabled` kill switch both
/// live in `routes/events.py`. The client deliberately does NOT re-gate: an empty
/// array is the kill switch working, and a second client-side threshold would make
/// the server's switch a half-measure that needs an App Store release to complete.
nonisolated struct GameMomentPoint: Decodable, Sendable {
    let ts: String?
    let label: String?
    let confidence: Double?
    let momentType: String?
    let actorTeam: String?
    /// Signed swing in probability points, 0.0–1.0 (0.935 = "+93.5 pts" in the label).
    let probDelta: Double?
    let period: String?
}

// MARK: - Aggregate Line

/// Aggregated home and away probability point for charting.
nonisolated struct AggregateLinePoint: Decodable, Sendable {
    let timestamp: String
    let homeProbability: Double
    let awayProbability: Double?
}
