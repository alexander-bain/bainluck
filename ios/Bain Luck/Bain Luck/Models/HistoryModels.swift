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
    /// The server's period boundaries with their provenance (#3348). Optional
    /// for the same reason `moments` is: additive, and an older cached payload
    /// has no key at all. Decoded per element by a tolerant initialiser — see
    /// `PeriodMarkerPayload` — so one malformed marker cannot blank the chart.
    let periodMarkers: [PeriodMarkerPayload]?
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
    /// `true` on the ONE point the backend synthesises at "now" on a live game,
    /// carrying the series' last real value forward
    /// (`_extend_win_prob_history_to_live_edge`, #920). A delivery time, not an
    /// observation: never a dot, never cadence, never a reading. Absent on
    /// every real row.
    let liveEdge: Bool?
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

// MARK: - Period Marker (served)

/// One entry of the served `period_markers` array (#3348).
///
/// `source` names the tier that answered — `statpal`, `espn_box`, `win_prob`
/// and `espn_state` are INSTRUMENTS; `estimated` is arithmetic on the scheduled
/// start and nobody observed it. `precision` (`boundary_observed` /
/// `first_seen` / `first_score`) and `notBefore` ride only on the observed
/// football transition tier: the period began after `notBefore` and at or
/// before `timestamp`. A marker without them is a first observation, not an
/// exact start.
///
/// EVERY FIELD IS OPTIONAL AND EVERY FIELD IS DECODED WITH `try?`, for the
/// reason `GameMomentPoint` gives: this type sits inside `EventHistoryResponse`,
/// and a single throwing element takes the whole history payload down with it
/// (gotcha #42). A marker the client cannot read is dropped in exactly one
/// place, `OddsChartView.servedPeriodMarkers(from:)`, which is pure and tested.
nonisolated struct PeriodMarkerPayload: Decodable, Sendable {
    let timestamp: String?
    let period: String?
    let source: String?
    let precision: String?
    let notBefore: String?

    /// The server's word for "placed by arithmetic, seen by nobody".
    static let estimatedSource = "estimated"

    /// True when the server says nobody observed this boundary.
    var isEstimated: Bool { source == Self.estimatedSource }

    /// True when a NAMED instrument observed this boundary. A marker with no
    /// `source` is UNKNOWN — neither observed nor estimated — and the phone,
    /// which draws only what was observed (#6718), does not admit it. Missing
    /// evidence is not evidence of observation (codex 2026-09-23 correction).
    var isObserved: Bool {
        guard let source, !source.isEmpty else { return false }
        return source != Self.estimatedSource
    }

    private enum CodingKeys: String, CodingKey {
        case timestamp, period, source, precision, notBefore
    }

    init(timestamp: String?, period: String?, source: String?,
         precision: String? = nil, notBefore: String? = nil) {
        self.timestamp = timestamp
        self.period = period
        self.source = source
        self.precision = precision
        self.notBefore = notBefore
    }

    /// NEVER THROWS. `try?` on each field covers a mistyped field, but the
    /// container itself is the other failure: a `null` or a bare scalar in the
    /// array reaches this initialiser with no keyed container to open, and
    /// `decoder.container(keyedBy:)` throws — which took the WHOLE
    /// `EventHistoryResponse` down (codex 2026-09-23, `CODEX-marker-decode.log`:
    /// scalar and null entries each failed the envelope while the reviewed
    /// candidate claimed per-element tolerance). Such an entry decodes to an
    /// all-nil marker, which `servedPeriodMarkers(from:)` drops for having no
    /// timestamp. The element is still consumed, so the unkeyed cursor moves on.
    init(from decoder: Decoder) throws {
        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else {
            timestamp = nil
            period = nil
            source = nil
            precision = nil
            notBefore = nil
            return
        }
        timestamp = try? c.decodeIfPresent(String.self, forKey: .timestamp)
        period = try? c.decodeIfPresent(String.self, forKey: .period)
        source = try? c.decodeIfPresent(String.self, forKey: .source)
        precision = try? c.decodeIfPresent(String.self, forKey: .precision)
        notBefore = try? c.decodeIfPresent(String.self, forKey: .notBefore)
    }
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
