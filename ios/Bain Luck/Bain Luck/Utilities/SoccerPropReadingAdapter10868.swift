import Foundation

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART THREE: ONE
/// ORIGINAL OUTCOME'S READINGS, SHARED BY THE GOAL, BOTH-TEAMS, FIRST-TEAM AND
/// HALF-BY-HALF STORIES.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: every soccer prop story prints, for each
/// original outcome, the same pre-match chance, in-play chance and result
/// under the same rules as the hockey stories — or that slot's own words.
///
/// It decides nothing the app does not already decide. The rules are hockey's
/// accepted H3/H4 rules, applied to the rows `/game-markets` serves:
///
///   - WHICH MARKET     the owner's admission (`Markets`), by exact venue market
///                      id. Nothing here parses a market title to find "both
///                      teams to score" or a half: the 10238 matrix serves these
///                      soccer markets as `named_options` with `period`,
///                      `predicate` and `quantity` null, and Design ruled the
///                      title is not the contract. The admission is the host's
///                      until an owner types them — still owed (#10238 producer
///                      typing; Native for the binding).
///   - legs             every served row of that market id, in served order:
///                      `other` rows (`GameMarketOther`) and the
///                      `GameMarketOutcome` arrays (`totals`, `spreads`,
///                      `team_totals`, `period_markets`). Read through the
///                      catalogue's own row (`QuestionCatalog9483.row`).
///   - identity         the row's served `contributor_outcome_ids` joined with
///                      "+", else the row id `market_name-outcome_name` (H4's
///                      side identity). Never a position or a label.
///   - pre-match        before the start (`HockeyJourneyContributionAdapter10868
///                      .hasStarted`, `NFLMilestoneCard9483.cards`' rule): the
///                      row's own catalogue price while `NFLMilestoneCard9483
///                      .isRecent` finds its own `observed_at` recent. Once
///                      started: the matrix option's stored pre-match pin for
///                      the SAME market and contributor outcomes — its
///                      `pregame_reading` when available (#11125), else its
///                      `comparison.baseline` whose basis is `pregame_pin` (the
///                      same stored pin, the only v1 basis) — observed strictly
///                      before the listed start. Never the opening line, never a
///                      current or settled price, never a neighbour.
///   - in-play          H4's order: a row the venue already settled has no
///                      chance; no price is "no in-game reading"; undated is no
///                      recent update; observed before the listed start is no
///                      in-game reading; not recent is no recent update; else
///                      the catalogue's own price, read at its own observation
///                      instant. One addition H4 asks for by name ("an
///                      unprovably recent quote cannot be the in-game current
///                      slot"): a `GameMarketOutcome` row's clock can be a
///                      sibling's — the producer serves `observed_at_basis:
///                      "capped_to_sibling"` on `totals` and `period_markets`
///                      rows (measured in the retained live body: five totals,
///                      three period rows, all reading 15%) and
///                      `GameMarketOutcome` does not decode that key — so such a
///                      row is never the current chance. Dependency: decode
///                      `observed_at_basis` (Models/FuturesModels.swift, #9483).
///   - period rows      (Design, wave-1 review 2026-10-31) a market about one
///                      period of the match — a half the owner admitted
///                      (`Markets.halves`) — may show a current chance only on
///                      the owner's own evidence that THIS period is still being
///                      played. A recent price alone is not that evidence: the
///                      retained live body still quotes the first half's home
///                      result at 99.9% (12:54Z, 54 minutes after kickoff), the
///                      row Design's review names as retained after the half. No
///                      field the app decodes carries it:
///                        · `QuestionMatrixQuestion.lifecycle` is the question's
///                          own venue market status, "never from the event"
///                          (`_lifecycle`, backend event_question_matrix.py) —
///                          `open` on both half markets at 12:56Z, so open means
///                          not yet graded, not in play;
///                        · `QuestionMatrixQuestion.period` names a period (and
///                          is null on both half markets), never its state;
///                        · `ClosedPeriodOutcome.windowClosed` (#10850) proves a
///                          period CLOSED, for NFL/NCAAF/NBA/WNBA `period_markets`
///                          half rows only — soccer is excluded by name;
///                        · the server's #1588 window filter keeps a row whose
///                          window it cannot prove closed, so a served row is not
///                          proof of an open one;
///                        · `ESPNData.period` / `gameClock` are absent on the
///                          retained live body (and `HalfScores` from
///                          `espn_history` proves a half OVER, never open).
///                      So `periodCurrent` never returns a current chance: a
///                      dated quote on its own clock is kept only as that dated
///                      recorded quote, under the in-play absence words, and the
///                      result stays `result(_:)` — the venue's grade, else
///                      unknown. No time elapsed since kickoff is read and no
///                      second settlement policy is made. MISSING OWNER INPUT: a
///                      per-period in-play state for the admitted half market
///                      (the #10238 matrix producer, or the #1588 window owner
///                      extended to soccer halves), or a served soccer live
///                      period (`espn.period`) with a PeriodLabel question that
///                      names the half in play.
///   - result           H4's settlement rule (`HockeyJourneyOriginalsAdapter10868
///                      .settlement`: `is_winner` with a venue's own
///                      `resolution_source`, never the retraction). A matrix
///                      grade (`result.isWinner`) that disagrees leaves it
///                      unconfirmed — this file never picks one side. Unknown
///                      is not loss.
///   - words            `formatProbability`; `SoccerMatchPageAdapter10868`'s
///                      clock words; venues through `SourceLabels.label`.
enum SoccerPropReadingAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        /// Part one's host, for its clock words only.
        var words: SoccerMatchPageAdapter10868.Host {
            SoccerMatchPageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    /// The owner's admission: which exact venue markets each story reads.
    /// Supplied by the host; never found here from a title.
    struct Markets: Equatable {
        /// One period of the half-by-half story: its market and the owner's
        /// period identity and words.
        struct Half: Equatable {
            let marketID: Int
            let periodID: String
            let label: String
        }

        /// Full-match goal totals, in milestone order.
        var goals: [Int]
        var both: Int?
        var first: Int?
        /// In period order.
        var halves: [Half]
        /// Markets of `goals` whose served row clock the owner has proved is
        /// that row's own observation — the producer's `observed_at_basis`
        /// absent, not `capped_to_sibling`. `GameMarketOutcome` does not decode
        /// that key yet (Models/FuturesModels.swift, #9483), so no owner can
        /// supply this today and none is assumed: empty keeps every totals
        /// row's clock unproven (part four).
        var ownClockGoals: Set<Int>
        /// The owner's exact-score descriptor (part ten,
        /// `SoccerExactScoreAdapter10868`); nil offers no exact-score map.
        var exactScore: SoccerExactScoreAdapter10868.Descriptor?

        init(goals: [Int] = [], both: Int? = nil, first: Int? = nil, halves: [Half] = [],
             ownClockGoals: Set<Int> = [], exactScore: SoccerExactScoreAdapter10868.Descriptor? = nil) {
            self.goals = goals
            self.both = both
            self.first = first
            self.halves = halves
            self.ownClockGoals = ownClockGoals
            self.exactScore = exactScore
        }
    }

    /// Reader words. Plain chance and availability language only.
    enum Words {
        static let preMatchNotRecorded = "Pre-match chance not recorded"
        static let chanceUnavailable = AllMarketsCatalogView9483.unavailablePrice
        /// `AllMarketsCatalogView9483.noRecentPrice`, the page's one spelling.
        static let noRecentUpdate = AllMarketsCatalogView9483.noRecentPrice
        static let inPlayUnavailable = "In-play chance unavailable"
        static let settledNoChance = "No current chance after settlement"
        static let resultUnavailable = "Result unavailable"
        static let notStarted = "Not started"
        static let savedBeforeStart = "saved before kickoff"
        static let recorded = "recorded"

        /// A period's dated recorded quote, never its current chance:
        /// "In-play chance unavailable · 99.9% recorded Oct 12, 5:54 AM · Polymarket".
        static func periodQuote(_ figure: String, clock: String, venue: String?) -> String {
            let recordedQuote = "\(figure) \(recorded) \(clock)"
            return SoccerMatchPageAdapter10868.joined([inPlayUnavailable, recordedQuote, venue]) ?? inPlayUnavailable
        }
    }

    // MARK: - Legs

    /// One served original outcome of an admitted market.
    struct Leg: Equatable {
        let marketID: Int
        /// H4's side identity: contributor ids, else the row id.
        let id: String
        /// The served outcome name, trimmed; the market text when blank.
        let label: String
        /// The catalogue's own reading of the row.
        let row: QuestionCatalog9483.Row
        let contributors: [Int]
        let isWinner: Bool?
        let resolutionSource: String?
        /// Served on `GameMarketOutcome` rows only.
        let threshold: Double?
        /// False for a `GameMarketOutcome` row, whose clock can be a sibling's.
        let clockIsOwn: Bool
        /// The matrix option for the same market and contributor outcomes.
        let option: QuestionMatrixOption?
    }

    /// Every served row of `marketID`, in the catalogue's array order and
    /// served order within each array.
    static func legs(_ marketID: Int, in data: GameMarketsResponse?) -> [Leg] {
        guard let data else { return [] }
        let matrix = data.gameQuestionMatrix
        var out: [Leg] = []
        let outcomes = (data.totals ?? []) + (data.spreads ?? []) + (data.teamTotals ?? []) + (data.periodMarkets ?? [])
        for o in outcomes where belongs(marketID, one: o._marketId, many: o._marketIds) {
            out.append(leg(marketID, row: QuestionCatalog9483.row(o), marketName: o.marketName,
                           outcomeName: o.outcomeName, contributors: o.contributorOutcomeIds,
                           isWinner: o.isWinner, resolutionSource: o.resolutionSource,
                           threshold: o.threshold, clockIsOwn: false, matrix: matrix))
        }
        for o in data.other ?? [] where belongs(marketID, one: o._marketId, many: o._marketIds) {
            out.append(leg(marketID, row: QuestionCatalog9483.row(o), marketName: o.marketName,
                           outcomeName: o.outcomeName, contributors: o.contributorOutcomeIds,
                           isWinner: o.isWinner, resolutionSource: o.resolutionSource,
                           threshold: nil, clockIsOwn: true, matrix: matrix))
        }
        return out
    }

    private static func belongs(_ marketID: Int, one: Int?, many: [Int]?) -> Bool {
        one == marketID || (many ?? []).contains(marketID)
    }

    private static func leg(_ marketID: Int, row: QuestionCatalog9483.Row, marketName: String, outcomeName: String,
                            contributors: [Int]?, isWinner: Bool?, resolutionSource: String?, threshold: Double?,
                            clockIsOwn: Bool, matrix: EventQuestionMatrix?) -> Leg {
        let ids = contributors ?? []
        let trimmed = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        return Leg(marketID: marketID,
                   id: ids.isEmpty ? "\(marketName)-\(outcomeName)" : ids.map(String.init).joined(separator: "+"),
                   label: trimmed.isEmpty ? marketName : trimmed,
                   row: row, contributors: ids, isWinner: isWinner, resolutionSource: resolutionSource,
                   threshold: threshold, clockIsOwn: clockIsOwn,
                   option: option(marketID, contributors: ids, in: matrix))
    }

    /// The one matrix option naming exactly this market and these contributor
    /// outcomes; nil when none or more than one does.
    static func option(_ marketID: Int, contributors: [Int], in matrix: EventQuestionMatrix?) -> QuestionMatrixOption? {
        guard !contributors.isEmpty, let matrix else { return nil }
        let wanted = Set(contributors)
        var found: [QuestionMatrixOption] = []
        for question in matrix.questions {
            for candidate in question.options
            where (candidate.marketIds ?? []).contains(marketID) && Set(candidate.contributorOutcomeIds ?? []) == wanted {
                found.append(candidate)
            }
        }
        return found.count == 1 ? found[0] : nil
    }

    // MARK: - Readings

    /// One shown chance: raw value for geometry, the figure, a short clock and
    /// the full clock and venue.
    struct Observation: Equatable {
        let probability: Double
        let text: String
        let clock: String?
        let detail: String
    }

    enum Pregame: Equatable {
        case value(Observation)
        case missing(String)

        var observation: Observation? {
            if case .value(let observation) = self { return observation }
            return nil
        }

        /// The figure's full detail, or the missing words — the timing line.
        var words: String {
            switch self {
            case .value(let observation): observation.detail
            case .missing(let words): words
            }
        }
    }

    enum Current: Equatable {
        case recorded(Observation)
        /// A quote exists but may not be the current chance.
        case withheld(String)
        case unavailable(String)

        var words: String {
            switch self {
            case .recorded(let observation): observation.detail
            case .withheld(let words), .unavailable(let words): words
            }
        }
    }

    enum Result: Equatable {
        case won(String)
        case lost(String)
        case unconfirmed(String)

        var text: String {
            switch self {
            case .won(let text), .lost(let text), .unconfirmed(let text): text
            }
        }

        var isAdmitted: Bool {
            if case .unconfirmed = self { return false }
            return true
        }
    }

    /// Before the start: the row's own price on its own recent clock. Once
    /// started: the stored pre-match pin for the same original, or its absence.
    static func pregame(_ leg: Leg, event: EventDetail, host: Host) -> Pregame {
        let venue = SourceLabels.label(for: leg.row.source)
        if HockeyJourneyContributionAdapter10868.hasStarted(event, now: host.now) {
            guard let pin = pin(leg.option, start: event.commenceTime?.asDate) else {
                return .missing(Words.preMatchNotRecorded)
            }
            return .value(observation(pin.probability, at: pin.observedAt, lead: Words.savedBeforeStart,
                                      venue: venue, host: host))
        }
        guard leg.clockIsOwn else { return .missing(Words.noRecentUpdate) }
        guard let price = quoted(leg, event: event, host: host) else { return .missing(Words.chanceUnavailable) }
        guard NFLMilestoneCard9483.isRecent(leg.row.observedAt, now: host.now),
              let at = leg.row.observedAt?.asDate else { return .missing(Words.noRecentUpdate) }
        return .value(observation(price, at: at, lead: Words.recorded, venue: venue, host: host))
    }

    /// During play, in H4's order, with the sibling-clock refusal.
    static func current(_ leg: Leg, event: EventDetail, host: Host) -> Current {
        if settlement(leg) != nil { return .unavailable(Words.settledNoChance) }
        guard let price = quoted(leg, event: event, host: host) else { return .unavailable(Words.inPlayUnavailable) }
        guard leg.clockIsOwn, let at = leg.row.observedAt?.asDate else { return .withheld(Words.noRecentUpdate) }
        if let start = event.commenceTime?.asDate, at < start { return .unavailable(Words.inPlayUnavailable) }
        guard NFLMilestoneCard9483.isRecent(leg.row.observedAt, now: host.now) else {
            return .withheld(Words.noRecentUpdate)
        }
        return .recorded(observation(price, at: at, lead: Words.recorded,
                                     venue: SourceLabels.label(for: leg.row.source), host: host))
    }

    /// During play, for a row about one period of the match (an admitted half).
    /// Never the current chance — no decoded field proves this period is still
    /// being played (header: `period rows`). In H4's order: a row the venue
    /// already settled has no chance; no price is "In-play chance unavailable";
    /// a clock that is not provably its own, or none, is no recent update;
    /// observed before the listed start is no in-play reading; otherwise the
    /// quote is kept as a dated recorded quote, stale or not, under the in-play
    /// absence words. The result is `result(_:)` alone.
    static func periodCurrent(_ leg: Leg, event: EventDetail, host: Host) -> Current {
        if settlement(leg) != nil { return .unavailable(Words.settledNoChance) }
        guard let price = quoted(leg, event: event, host: host) else { return .unavailable(Words.inPlayUnavailable) }
        guard leg.clockIsOwn, let at = leg.row.observedAt?.asDate else { return .withheld(Words.noRecentUpdate) }
        if let start = event.commenceTime?.asDate, at < start { return .unavailable(Words.inPlayUnavailable) }
        let clock = SoccerMatchPageAdapter10868.clockWords(at, host: host.words)
        return .withheld(Words.periodQuote(formatProbability(price), clock: clock,
                                           venue: SourceLabels.label(for: leg.row.source)))
    }

    /// The served settlement, unless the matrix grade disagrees. Unknown is not loss.
    static func result(_ leg: Leg) -> Result {
        guard let won = settlement(leg) else { return .unconfirmed(Words.resultUnavailable) }
        if let graded = leg.option?.result?.isWinner, graded != won { return .unconfirmed(Words.resultUnavailable) }
        return won ? .won(OutcomeVerdict.won.label) : .lost(OutcomeVerdict.lost.label)
    }

    /// H4's settlement rule on this leg's served fields.
    static func settlement(_ leg: Leg) -> Bool? {
        HockeyJourneyOriginalsAdapter10868.settlement(isWinner: leg.isWinner, resolutionSource: leg.resolutionSource)
    }

    /// The catalogue's own price for the row, read at the row's own observation
    /// instant (so its live-staleness rule judges currentness separately), or
    /// at now when undated.
    static func quoted(_ leg: Leg, event: EventDetail, host: Host) -> Double? {
        let instant = leg.row.observedAt?.asDate ?? host.now
        return admissible(QuestionCatalog9483.reading(leg.row, status: event.status, now: instant).probability)
    }

    /// The stored pre-match pin: `pregame_reading` when available, else the
    /// comparison baseline whose basis is `pregame_pin`. Only one observed
    /// strictly before the listed start (or with no start to compare against
    /// when the listing has none — then the pin's own basis is the claim).
    static func pin(_ option: QuestionMatrixOption?, start: Date?) -> (probability: Double, observedAt: Date)? {
        guard let option else { return nil }
        var candidate: (Double, Date)?
        if let reading = option.pregameReading, reading.state == "available",
           let value = admissible(reading.probability), let at = reading.observedAt?.asDate {
            candidate = (value, at)
        } else if let comparison = option.comparison, comparison.state == "comparable",
                  let baseline = comparison.baseline, baseline.basis == "pregame_pin",
                  let value = admissible(baseline.probability), let at = baseline.observedAt?.asDate {
            candidate = (value, at)
        }
        guard let found = candidate else { return nil }
        if let start, found.1 >= start { return nil }
        return (probability: found.0, observedAt: found.1)
    }

    static func observation(_ value: Double, at: Date, lead: String, venue: String?, host: Host) -> Observation {
        let words = host.words
        let full = "\(lead) \(SoccerMatchPageAdapter10868.clockWords(at, host: words))"
        return Observation(probability: value, text: formatProbability(value),
                           clock: SoccerMatchPageAdapter10868.timeWords(at, host: words),
                           detail: SoccerMatchPageAdapter10868.joined([full, venue]) ?? full)
    }

    /// A finite probability in 0...1, or nil. A real 0 stays.
    static func admissible(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }

    // MARK: - The score the stories share

    /// The match's goals so far (or final), dated by the producer's own clock.
    struct Goals: Equatable {
        let home: Int
        let away: Int
        var total: Int { home + away }
        let observedAt: Date?
    }

    static func goals(_ event: EventDetail) -> Goals? {
        SoccerMatchPageAdapter10868.scorePair(event).map {
            Goals(home: $0.home, away: $0.away, observedAt: event.scoreObservedAt?.asDate)
        }
    }

    /// "Valladolid 4, Albacete 0 · score observed Oct 12, 5:54 AM".
    static func goalsDetail(_ goals: Goals, event: EventDetail, final: Bool, host: Host) -> String {
        let names = SoccerMatchPageAdapter10868.names(event)
        let pair = "\(names.home) \(goals.home), \(names.away) \(goals.away)"
        if final { return "\(SoccerMatchPageAdapter10868.Words.final): \(pair)" }
        guard let at = goals.observedAt else { return pair }
        return "\(pair) · score observed \(SoccerMatchPageAdapter10868.clockWords(at, host: host.words))"
    }

    /// "Observed 5:54 AM", "Final", or nil when undated.
    static func goalsClock(_ goals: Goals, final: Bool, host: Host) -> String? {
        if final { return SoccerMatchPageAdapter10868.Words.final }
        return goals.observedAt.map { "Observed \(SoccerMatchPageAdapter10868.timeWords($0, host: host.words))" }
    }
}
