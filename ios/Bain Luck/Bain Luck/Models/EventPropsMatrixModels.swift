import Foundation

// MARK: - During player-props matrix (#10236)

/// `during_player_props` on `GET /api/events/{id}/game-markets` — contract
/// `10236.v1` as amended by v1.1 (Authority) and built by Live in
/// `backend/app/utils/event_props_matrix.py`.
///
/// 🔴 EVERY DECISION HERE IS THE SERVER'S. The subject, the stat, the
/// predicate and its label, the quote state, the blend, the comparison and its
/// delta are all typed upstream (ruling 003). The phone formats them; it never
/// parses a market name, computes a complement, averages sources or subtracts
/// one number from another. A row the server could not type is not in this
/// payload at all, and the old `PlayerPropsCardView` keeps drawing it.
///
/// ABSENT AND NULL MEAN THE SAME THING: the key is `null` unless the served
/// status is `live` AND at least one prop types, and older servers omit it.
/// Both decode to nil, and nil keeps today's card exactly as it is.
nonisolated struct DuringPlayerProps: Decodable, Equatable, Sendable {
    let contract: String?
    let stats: [DuringPropStat]
    var rows: [DuringPropRow]
    let coverage: DuringPropCoverage?
}

/// One statistic the payload has rows for, in the server's table order.
nonisolated struct DuringPropStat: Decodable, Equatable, Identifiable, Sendable {
    var id: String { statKey }
    let statKey: String
    /// "Hits", "Total Bases" — the header a reader sees.
    let label: String
    /// Plural / singular unit for the question sentence ("2+ hits", "1+ hit").
    let unit: String
    let unitSingular: String
    let periodKey: String
    let periodLabel: String?
    /// The predicate the matrix's columns are drawn in (`count_at_least`).
    let predicate: String
}

/// One typed question: one player, one stat, one threshold, one side.
nonisolated struct DuringPropRow: Decodable, Equatable, Identifiable, Sendable {
    var id: String { questionKey }
    /// Deterministic from the typed parts — never a price, clock or index.
    let questionKey: String
    let subject: DuringPropSubject
    let statKey: String
    let periodKey: String
    let predicate: DuringPropPredicate
    /// Set on an under row: the over question it is the other side of. The
    /// phone never derives this pairing itself.
    let complementQuestionKey: String?
    let current: DuringPropCurrent
    let contributors: [DuringPropContributor]
    let comparison: DuringPropComparison?
    let result: DuringPropResult?
    // Leading underscores are retained by convertFromSnakeCase.
    var _marketId: Int? = nil
    var _marketIds: [Int]? = nil
    var contributorOutcomeIds: [Int]? = nil
}

nonisolated struct DuringPropSubject: Decodable, Equatable, Sendable {
    /// Event-local identity (normalised name). Selection keys on this.
    let key: String
    let label: String
    let kind: String?
}

nonisolated struct DuringPropPredicate: Decodable, Equatable, Sendable {
    /// `count_at_least` (over) or `count_at_most` (under).
    let kind: String
    let count: Int
    let side: String
    /// "2+" / "1 or fewer" — the server's spelling.
    let label: String

    var isAtLeast: Bool { kind == "count_at_least" }
}

nonisolated struct DuringPropCurrent: Decodable, Equatable, Sendable {
    /// `quoted` · `actual_only` · `unavailable`. An unknown state is treated as
    /// unavailable: a chance is shown only when the server says it is quoted.
    let state: String
    let probability: Double?
    /// `single_source` · `blend_mean`.
    let basis: String?
    let observedAt: String?

    /// The chance a reader may be shown, or nil. A finite 0 is a real quote and
    /// stays; null, NaN, infinite or out-of-range is no chance.
    var quotedProbability: Double? {
        guard state == "quoted", let probability, probability.isFinite,
              probability >= 0, probability <= 1 else { return nil }
        return probability
    }
    var isActualOnly: Bool { state == "actual_only" }
}

nonisolated struct DuringPropContributor: Decodable, Equatable, Sendable {
    let source: String?
    let marketId: Int?
    let outcomeId: Int?
    let outcomeName: String?
    let side: String?
    let periodKey: String?
    let probability: Double?
    let observedAt: String?
}

nonisolated struct DuringPropComparison: Decodable, Equatable, Sendable {
    /// `comparable` · `unavailable`.
    let state: String
    let reason: String?
    let baseline: DuringPropBaseline?
    /// Percentage points, rounded to 0.1 by the server.
    let deltaPoints: Double?

    var isComparable: Bool { state == "comparable" }
}

nonisolated struct DuringPropBaseline: Decodable, Equatable, Sendable {
    let probability: Double?
    let observedAt: String?
    let basis: String?
}

/// The server's grade, carried verbatim — present only on `actual_only` rows,
/// which a live payload cannot produce today (`_grade_settled_prop` returns
/// `{}` until the game finishes).
nonisolated struct DuringPropResult: Decodable, Equatable, Sendable {
    let actual: Double?
    let hit: Bool?
    let isWinner: Bool?
    let resolutionSource: String?
}

nonisolated struct DuringPropCoverage: Decodable, Equatable, Sendable {
    let scope: String?
    let subjects: Int?
    let questions: Int?
    let quoted: Int?
    let actualOnly: Int?
    let unavailable: Int?
}

// MARK: - After player-props comparison (#10237)

/// `after_player_props` on `GET /api/events/{id}/game-markets` — contract
/// `10237.v1` (Authority ack v1 + 0215Z addendum), built by
/// `backend/app/utils/prop_expectation_actual.py`.
///
/// 🔴 EVERY DECISION HERE IS THE SERVER'S, AS IN ``DuringPlayerProps``. The
/// saved pregame chance, the final count, whether that count is official, and
/// whether it reached the line (`comparison.state`) are all typed upstream
/// (ruling 003). The phone never compares a count with a threshold, matches a
/// player by name, averages sources, or reads a venue's grade as the result.
///
/// ABSENT, NULL AND AN UNKNOWN CONTRACT MEAN THE SAME THING: the key is `null`
/// unless the game is finished and a question types, older servers omit it,
/// and a body the app cannot decode (or a contract it does not know) is
/// treated as absent — the page falls back to what it drew before. When it is
/// non-null the server sends `during_player_props: null` (frozen reader
/// contract), so the page never has to choose a phase itself.
nonisolated struct AfterPlayerProps: Decodable, Equatable, Sendable {
    static let supportedContract = "10237.v1"

    let contract: String?
    let stats: [AfterPropStat]
    /// One per player × stat, in the server's order — the final count is
    /// stated once per player from here, never repeated per threshold.
    var actuals: [AfterPropActual]
    var questions: [AfterPropQuestion]
    let coverage: AfterPropCoverage?

    var isSupported: Bool { contract == Self.supportedContract }

    /// The actual a question names, by its `actual_key`, and only one whose
    /// player and stat agree with the question. Never another row's.
    func actual(for question: AfterPropQuestion) -> AfterPropActual? {
        actuals.first {
            $0.actualKey == question.actualKey && $0.subject.key == question.subject.key
                && $0.statKey == question.statKey && $0.periodKey == question.periodKey
        }
    }

    func stat(_ statKey: String) -> AfterPropStat? { stats.first { $0.statKey == statKey } }
}

/// One statistic the payload has questions for, in the server's table order.
nonisolated struct AfterPropStat: Decodable, Equatable, Identifiable, Sendable {
    var id: String { statKey }
    let statKey: String
    /// "Home Runs", "Hits".
    let label: String
    let unitSingular: String
    let unitPlural: String
    let periodKey: String
    let periodLabel: String?
    /// `count_at_least` in v1.
    let predicate: String
}

/// ESPN's official final count for one player × stat, or why there is none.
nonisolated struct AfterPropActual: Decodable, Equatable, Identifiable, Sendable {
    var id: String { actualKey }
    let actualKey: String
    let subject: DuringPropSubject
    let statKey: String
    let periodKey: String
    /// `final` · `pending` · `unknown`. Anything else reads as unknown.
    let state: String
    /// Machine reason (`player_not_in_box`, `provider_not_final`, …) — never
    /// printed (notice 34), never turned into "did not play".
    let reason: String?
    let value: Int?
    /// "ESPN final statistic" when final.
    let sourceLabel: String?
    let provider: String?
    let providerEventId: String?
    let athleteId: String?
    let teamId: String?
    /// When the box was RETRIEVED — not when the play or a correction happened.
    let capturedAt: String?
    let finalityBasis: String?
    /// Changes only when the statistic changes; a re-fetch keeps it.
    let recordVersion: String?

    var isFinal: Bool { state == "final" }

    /// The official count, or nil. A verified final 0 is a real 0.
    var finalCount: Int? {
        guard isFinal, let value, value >= 0 else { return nil }
        return value
    }
}

/// One typed over question: one player, one stat, one threshold.
nonisolated struct AfterPropQuestion: Decodable, Equatable, Identifiable, Sendable {
    var id: String { questionKey }
    let questionKey: String
    /// The ``AfterPropActual`` this question is judged against.
    let actualKey: String
    let subject: DuringPropSubject
    let statKey: String
    let periodKey: String
    let predicate: DuringPropPredicate
    let expectation: AfterPropExpectation
    let comparison: AfterPropComparison?
    /// A venue's own settlement, verbatim — detail only, never the mark.
    let venueGrade: AfterPropVenueGrade?
    // Leading underscores are retained by convertFromSnakeCase.
    var _marketIds: [Int]? = nil
    var contributorOutcomeIds: [Int]? = nil
}

/// The saved pregame chance: the pin as stored before first pitch.
nonisolated struct AfterPropExpectation: Decodable, Equatable, Sendable {
    /// `available` · `unavailable`. Anything else reads as unavailable.
    let state: String
    let reason: String?
    let probability: Double?
    /// `single_source` · `blend_mean` — the server's basis, never recomputed.
    let basis: String?
    let observedAt: String?
    let contributors: [AfterPropContributor]
    let excluded: [AfterPropExcluded]

    /// The chance a reader may be shown, or nil. A finite 0 stays.
    var savedProbability: Double? {
        guard state == "available", let probability, probability.isFinite,
              probability >= 0, probability <= 1 else { return nil }
        return probability
    }
}

nonisolated struct AfterPropContributor: Decodable, Equatable, Sendable {
    let source: String?
    let marketId: Int?
    let outcomeId: Int?
    let outcomeName: String?
    let probability: Double?
    let observedAt: String?
    let admission: String?
}

nonisolated struct AfterPropExcluded: Decodable, Equatable, Sendable {
    let source: String?
    let outcomeId: Int?
    let reason: String?
}

nonisolated struct AfterPropComparison: Decodable, Equatable, Sendable {
    /// `reached` · `below` · `unknown`, drawn verbatim.
    let state: String
    let reason: String?
}

nonisolated struct AfterPropVenueGrade: Decodable, Equatable, Sendable {
    let isWinner: Bool?
    let resolutionSource: String?
}

nonisolated struct AfterPropCoverage: Decodable, Equatable, Sendable {
    let scope: String?
    let questions: Int?
    let actuals: Int?
    let `final`: Int?
    let pending: Int?
    let unknown: Int?
    let expectationAvailable: Int?
}
