import Foundation

// MARK: - Game / Series question matrix (#10238)

/// `game_question_matrix` on `GET /api/events/{id}/game-markets` and
/// `series_question_matrix` on `GET /api/events/{id}/related-futures` — one
/// shape, frozen as contract `10238.v1` (Authority, §1–§11).
///
/// 🔴 EVERY DECISION HERE IS THE SERVER'S. The question, its kind, label,
/// sides, unit, period, the published value and its basis, the raw source
/// evidence, the result, the lifecycle, the completeness and the comparison
/// delta are all typed upstream (ruling 003). The phone never computes a
/// label, delta, complement, sum, side or grouping. A row the server could
/// not type arrives as `named_options` and keeps its served labels.
///
/// ABSENT AND NULL MEAN THE SAME THING: the value is `null` when no question
/// is built, and older servers omit the key. Both decode to nil, and nil keeps
/// today's sections exactly as they are. A value this client cannot read also
/// decodes to nil (`LenientDecode`), so the matrix can never take the legacy
/// arrays of the same response down with it.
nonisolated struct EventQuestionMatrix: Decodable, Equatable, Sendable {
    let contract: String?
    /// `game` | `series` — equals every question's `display_scope`.
    let displayScope: String?
    /// Server order. Clients key on `questionKey`, never on position.
    var questions: [QuestionMatrixQuestion]
    let seriesMarketsCount: QuestionMatrixSeriesCount?
    let coverage: QuestionMatrixCoverage?
    /// Questions this client could not read. Each was skipped alone, so one
    /// malformed question never erases its siblings (gotcha #42).
    var droppedQuestions: Int = 0

    private enum CodingKeys: String, CodingKey {
        case contract, displayScope, questions, seriesMarketsCount, coverage
    }

    init(contract: String? = "10238.v1", displayScope: String?, questions: [QuestionMatrixQuestion],
         seriesMarketsCount: QuestionMatrixSeriesCount? = nil, coverage: QuestionMatrixCoverage? = nil) {
        self.contract = contract
        self.displayScope = displayScope
        self.questions = questions
        self.seriesMarketsCount = seriesMarketsCount
        self.coverage = coverage
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        contract = try? c.decodeIfPresent(String.self, forKey: .contract)
        displayScope = try? c.decodeIfPresent(String.self, forKey: .displayScope)
        let lossy = try? c.decodeIfPresent(LossyArray<QuestionMatrixQuestion>.self, forKey: .questions)
        questions = lossy?.elements ?? []
        droppedQuestions = lossy?.dropped ?? 0
        seriesMarketsCount = try? c.decodeIfPresent(QuestionMatrixSeriesCount.self, forKey: .seriesMarketsCount)
        coverage = try? c.decodeIfPresent(QuestionMatrixCoverage.self, forKey: .coverage)
    }

    func question(_ key: String) -> QuestionMatrixQuestion? {
        questions.first { $0.questionKey == key }
    }
}

/// Which payload a matrix came from. The two never share a key space: one
/// market can sit in both with different comparison states (rider R6), and
/// each is read on its own — never reconciled against the other.
nonisolated enum QuestionMatrixScope: String, Sendable, Hashable {
    case game
    case series

    /// The #9524 reconciliation section (§11). Never `props:`/`duringProps:`.
    var sectionPrefix: String {
        switch self {
        case .game: "gameQuestions:"
        case .series: "seriesQuestions:"
        }
    }

    func sectionKey(_ questionKey: String) -> String { sectionPrefix + questionKey }
}

/// The four kinds a question can be (§4.1). Anything else this build does not
/// know is read as `namedOptions`: served labels, generic choices.
nonisolated enum QuestionMatrixKind: String, Sendable {
    case countThreshold = "count_threshold"
    case signedHandicap = "signed_handicap"
    case namedOptions = "named_options"
    case rankPredicate = "rank_predicate"
}

nonisolated struct QuestionMatrixQuestion: Decodable, Equatable, Identifiable, Sendable {
    var id: String { questionKey }
    /// Deterministic and opaque — never a price, clock, index or position.
    let questionKey: String
    /// Typed kinds only; nil for `named_options`.
    var propositionKey: String? = nil
    var displayScope: String? = nil
    let kind: String
    /// Server-written; for `named_options` the served market name verbatim.
    let label: String
    var marketName: String? = nil
    var sourceArray: String? = nil
    var quantity: QuestionMatrixQuantity? = nil
    var period: QuestionMatrixPeriod? = nil
    var subject: QuestionMatrixSubject? = nil
    var predicate: QuestionMatrixPredicate? = nil
    /// Handicap only: the opposite side's question. Never derived here.
    var complementQuestionKey: String? = nil
    var typing: QuestionMatrixTyping? = nil
    var lifecycle: QuestionMatrixLifecycle? = nil
    var options: [QuestionMatrixOption]
    var missingOptions: [QuestionMatrixMissingOption]? = nil
    var optionCounts: QuestionMatrixOptionCounts? = nil
    /// true | false | nil (unknown). A capped list never claims complete.
    var complete: Bool? = nil
    /// Per-source raw sums, written by the server only when every returned
    /// option has a raw value from that source. The phone never sums.
    var sourceTotals: [QuestionMatrixSourceTotal]? = nil

    /// The kind as a reader may be shown it. `named_options`, an unknown kind,
    /// and a typed kind the server also marked `untyped` all read as named
    /// options: such a question never enters a count, handicap or rank column.
    var columnKind: QuestionMatrixKind {
        guard let kind = QuestionMatrixKind(rawValue: kind) else { return .namedOptions }
        if kind != .namedOptions, typing?.state != "typed" { return .namedOptions }
        return kind
    }

    /// Whether the question may offer a "more options" disclosure. It needs
    /// evidence that options are hidden — `complete:false` alone means the
    /// server cannot vouch for the whole list, not that a row is missing
    /// (#10465: m:64118681, 14 loaded, 14 returned, 0 missing).
    /// Every kind: a server-identified missing leg. Named options also: a
    /// served truncation, declared > loaded or loaded > returned. A typed kind
    /// never reads truncation as evidence — its other leg is its own question
    /// (A4 native rider). Read from the served kind, so a typed kind marked
    /// untyped stays typed.
    var offersMoreOptions: Bool {
        guard complete == false else { return false }
        if max(optionCounts?.missingIdentified ?? 0, missingOptions?.count ?? 0) > 0 { return true }
        let served = QuestionMatrixKind(rawValue: kind) ?? .namedOptions
        guard served == .namedOptions, let counts = optionCounts else { return false }
        if let declared = counts.declared, let loaded = counts.loaded, declared > loaded { return true }
        if let loaded = counts.loaded, let returned = counts.returned, loaded > returned { return true }
        return false
    }

    func option(_ key: String) -> QuestionMatrixOption? {
        options.first { $0.optionKey == key }
    }
}

nonisolated struct QuestionMatrixQuantity: Decodable, Equatable, Sendable {
    let key: String
    let singular: String?
    let plural: String?
    let integer: Bool?
}

nonisolated struct QuestionMatrixPeriod: Decodable, Equatable, Sendable {
    let key: String
    let label: String?
}

nonisolated struct QuestionMatrixSubject: Decodable, Equatable, Sendable {
    /// count: game|home|away · handicap: home|away.
    let side: String?
    let label: String?
}

nonisolated struct QuestionMatrixPredicate: Decodable, Equatable, Sendable {
    let relation: String?
    let bound: Double?
    let line: Double?
}

nonisolated struct QuestionMatrixTyping: Decodable, Equatable, Sendable {
    /// `typed` | `untyped`.
    let state: String
    /// One of `untyped_period|unit|subject|predicate` when untyped.
    let reason: String?
}

nonisolated struct QuestionMatrixLifecycle: Decodable, Equatable, Sendable {
    /// `open` | `suspended` | `settled` | `unknown` — from the question's own
    /// market(s), never from the event. A finished game leaves an open Series
    /// open.
    let state: String
    let marketStatus: String?
}

nonisolated struct QuestionMatrixOption: Decodable, Equatable, Identifiable, Sendable {
    var id: String { optionKey }
    /// `o:` + the sorted contributor outcome ids — the #9524 identity.
    let optionKey: String
    /// The served outcome name verbatim.
    let label: String
    /// `home|away|draw|contender|category|over|under`, only when the server
    /// proved it; otherwise `category`.
    var side: String? = nil
    var marketIds: [Int]? = nil
    var contributorOutcomeIds: [Int]? = nil
    let published: QuestionMatrixPublished
    var sourceEvidence: [QuestionMatrixSourceEvidence]? = nil
    var result: QuestionMatrixResult? = nil
    var comparison: QuestionMatrixComparison? = nil
}

nonisolated struct QuestionMatrixPublished: Decodable, Equatable, Sendable {
    let value: Double?
    /// `quoted` · `refused` · `unpriced` · `result` · `unblended_equivalents`.
    let valueState: String
    /// `published_blend` · `published_source_display` · `result` · `unknown`.
    let basis: String?
    /// The served row's source; nil for a blend.
    let source: String?
    /// Verbatim from the served row (game); nil on the Series path (U2).
    let observedAt: String?

    /// The chance a reader may be shown, or nil. Only a `quoted` state shows
    /// a number; a finite 0 is a real quote and stays (F1). Null, NaN,
    /// infinite or out-of-range is no chance.
    var quotedValue: Double? {
        guard valueState == "quoted", let value, value.isFinite, value >= 0, value <= 1 else { return nil }
        return value
    }
}

/// One contributor's own raw leg — the display value can differ (a squeeze,
/// the totals over-axis), so this is shown beside it, never as the quote.
nonisolated struct QuestionMatrixSourceEvidence: Decodable, Equatable, Sendable {
    let source: String?
    let marketId: Int?
    let outcomeId: Int?
    let legSide: String?
    let rawProbability: Double?
    let observedAt: String?
}

nonisolated struct QuestionMatrixResult: Decodable, Equatable, Sendable {
    /// `open` · `won` · `lost` · `unknown` · `void` (reserved; v1 never emits).
    let state: String
    let evidenceKind: String?

    /// The grade the #9524 fences order on. Only the server's `won`/`lost`
    /// grade; `unknown`, `void`, `open` or anything else is no grade.
    var isWinner: Bool? {
        switch state {
        case "won": true
        case "lost": false
        default: nil
        }
    }
}

nonisolated struct QuestionMatrixComparison: Decodable, Equatable, Sendable {
    /// `comparable` · `unavailable`.
    let state: String
    let reason: String?
    let baseline: QuestionMatrixBaseline?
    let latest: QuestionMatrixLatest?
    /// Percentage points, rounded to 0.1 by the server.
    let deltaPoints: Double?

    /// Rider R5's caption — the only words a delta may carry. Never "since
    /// kickoff" or "since start".
    static let caption = "since the saved pregame price"

    /// The delta a reader may be shown, and the latest price it sits beside
    /// (R5: only beside `latest`, never beside the published value). Nil
    /// unless the server says `comparable` and served both numbers.
    var shownDelta: (points: Double, latest: QuestionMatrixLatest)? {
        guard state == "comparable", let latest, let deltaPoints, deltaPoints.isFinite,
              let probability = latest.probability, probability.isFinite else { return nil }
        return (deltaPoints, latest)
    }
}

nonisolated struct QuestionMatrixBaseline: Decodable, Equatable, Sendable {
    let probability: Double?
    let observedAt: String?
    /// `pregame_pin` is the only v1 basis.
    let basis: String?
}

nonisolated struct QuestionMatrixLatest: Decodable, Equatable, Sendable {
    let probability: Double?
    let observedAt: String?
}

/// A leg the server loaded but did not return. Never carries a price.
nonisolated struct QuestionMatrixMissingOption: Decodable, Equatable, Sendable {
    let optionKey: String
    let outcomeId: Int?
    let label: String?
    let side: String?
    /// `unpriced` | `unavailable`.
    let valueState: String?
}

nonisolated struct QuestionMatrixOptionCounts: Decodable, Equatable, Sendable {
    let declared: Int?
    let loaded: Int?
    let returned: Int?
    let missingIdentified: Int?
}

nonisolated struct QuestionMatrixSourceTotal: Decodable, Equatable, Sendable {
    let source: String
    let rawSum: Double?
    let legs: Int?
}

nonisolated struct QuestionMatrixSeriesCount: Decodable, Equatable, Sendable {
    let eligible: Int?
    let returned: Int?
}

nonisolated struct QuestionMatrixCoverage: Decodable, Equatable, Sendable {
    /// Always `rows_served_by_this_response` — never provider-wide.
    let scope: String?
    let questions: Int?
    let options: Int?
    let buildErrors: Int?
}

// MARK: - Lenient decode

/// An optional payload key that decodes to nil — never throws — when it is
/// absent, null, or a shape this build cannot read. Used for additive keys
/// that must not be able to fail the response that carries them.
@propertyWrapper
nonisolated struct LenientDecode<Value: Decodable & Equatable & Sendable>: Decodable, Equatable, Sendable {
    var wrappedValue: Value?

    init(wrappedValue: Value?) {
        self.wrappedValue = wrappedValue
    }

    init(from decoder: Decoder) throws {
        wrappedValue = try? decoder.singleValueContainer().decode(Value.self)
    }
}

extension KeyedDecodingContainer {
    /// An absent key is "no value", not a thrown error (the synthesized init
    /// calls `decode`, not `decodeIfPresent`, for a wrapper property).
    func decode<Value>(_ type: LenientDecode<Value>.Type, forKey key: Key) throws -> LenientDecode<Value> {
        (try? decodeIfPresent(type, forKey: key)) ?? LenientDecode(wrappedValue: nil)
    }
}
