import Foundation

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER, PART THREE: THE RUN
/// MILESTONES STORY, BEFORE FIRST PITCH AND DURING PLAY.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: before and during an MLB game the run
/// totals card shows each offered full-game run line as a milestone ("10+
/// runs") with its pregame chance, and during play the runs so far against
/// those milestones beside each line's current chance where one is admitted —
/// or that slot's own words. After the final the card is part four's
/// (`MLBTotalTargetsCardView11284`), never this one.
///
/// Rules, each an existing owner's:
///
///   - lines        `MLBTotalsCard11284.build` on THIS event's served game
///                  question matrix — the app's own admission of a typed
///                  full-game run line (10238.v1, `count_threshold`, runs, game,
///                  `ge`, exactly one Over option, one option per line, at least
///                  `NBAEventCards9483.minimumLadderLines`), in its line order.
///                  The builder is phase-agnostic; only its option keys and
///                  lines are read here.
///   - N+           the producer's `predicate.bound` is the line's own count
///                  (Over 9.5 is "10+"), through `MLBMilestoneCard11284.milestone`.
///   - chances      the NBA ladder's reading of a typed matrix option
///                  (`NBALadderCard9483`'s point rule, production's one rule for
///                  a typed count ladder): before first pitch the option's
///                  published value while `quoted` and its own clock is recent
///                  (`NFLMilestoneCard9483.isRecent`) — that price IS the
///                  pregame chance; once play starts the producer's admitted
///                  pregame pin (`NBALadderCard9483.pin`), and beside it the
///                  quoted value only while recent, observed at or after the
///                  listed start and the game not suspended. A quote observed
///                  before the start is never the in-game chance (Design H4).
///   - reached      `PlayerPropsCardView.rungVerdict` on the runs so far —
///                  performance, never 100% and never a settlement.
///   - runs         `EventDetail.homeScore + awayScore`, dated only by
///                  `scoreObservedAt`; during play only.
///   - default      `PlayerPropsFamily.defaultTarget` over the shown pregame
///                  chances (nearest even odds), the milestone cards' own
///                  default; the host's held milestone wins.
///
/// Known limit, named not routed around: a matrix option's served clock is
/// the served row's `observed_at` verbatim; the producer's
/// `observed_at_basis` ("capped_to_sibling", seen on 57 player-prop rows of
/// the retained final and on no totals row) is not decoded by
/// `QuestionMatrixPublished`, so a sibling-capped clock could not be told
/// apart here — the NBA ladder has the same exposure. Owner: the matrix
/// producer and the app's matrix model.
///
/// No projected total is admitted for baseball (`FinalForecastComparison11296`
/// declines it), so `projection` is nil. The host passes the event,
/// `/game-markets`, now, the reader's calendar and its held milestone; nothing
/// here fetches.
enum BaseballRunMilestonesAdapter10868 {

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
        var page: BaseballGamePageAdapter10868.Host {
            BaseballGamePageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    enum Words {
        static let eyebrow = "TOTAL RUNS · BOTH TEAMS"
        static let beforeTitle = "How many runs?"
        static let liveTitle = "Runs so far against the milestones"
        static let chartTitle = "Chance of reaching each total"
        static let axisTitle = "Total runs in the game"
        static let reachedSoFar = "Reached so far"
        static let scoreUnavailable = "Score unavailable"
        static let pregameUnavailable = "Pregame chance unavailable"
        static let inGameUnavailable = "In-game chance unavailable"
        static let resultUnavailable = "Result unavailable"
        static let recorded = "Recorded"
        static let savedBeforeStart = "Saved before first pitch"
        static let scoreObserved = "Score observed"
        static let timingSuffix = "chance timing"

        static func more(_ count: Int, label: String) -> String {
            "\(count) more for \(label)"
        }
    }

    /// Axis words on the fixed 0...1 scale — scale words, not chances, so not
    /// through `formatProbability`.
    static let chanceTicks = [
        TotalMilestoneTick10868(value: 0, text: "0%"),
        TotalMilestoneTick10868(value: 0.5, text: "50%"),
        TotalMilestoneTick10868(value: 1, text: "100%"),
    ]

    /// One admitted line and the matrix option behind it.
    struct Line {
        let line: Double
        let option: QuestionMatrixOption
    }

    /// The card before first pitch and during play; nil after the final, off
    /// this event, or when the app admits no run ladder.
    static func input(_ event: EventDetail, markets: GameMarketsResponse?, host: Host,
                      selectedMilestoneID: String? = nil) -> TotalMilestoneInput10868? {
        let phase = BaseballGamePageAdapter10868.phase(event, now: host.now)
        guard phase != .final else { return nil }
        let found = lines(event, markets: markets)
        guard !found.isEmpty else { return nil }
        let runs = phase == .live ? BaseballGamePageAdapter10868.scorePair(event).map { $0.home + $0.away } : nil
        let rows = found.map { row($0, event: event, phase: phase, runs: runs, host: host) }

        let chosen = selectedMilestoneID
            ?? PlayerPropsFamily.defaultTarget(probabilities: rows.map { $0.before?.probability }).map { rows[$0].id }
        let top = max(rows.map(\.quantity).max() ?? 0, Double(runs ?? 0))
        let quantityTicks = [TotalMilestoneTick10868(value: 0, text: "0")]
            + rows.map { TotalMilestoneTick10868(value: $0.quantity, text: $0.quantityLabel) }
        let timing = chosen.flatMap { id in
            Self.timing(id, rows: rows, phase: phase)
        }
        return TotalMilestoneInput10868(
            phase: phase.totalPhase,
            eyebrow: Words.eyebrow,
            title: phase == .before ? Words.beforeTitle : Words.liveTitle,
            chartTitle: Words.chartTitle,
            quantityAxisTitle: Words.axisTitle,
            milestones: rows,
            selectedMilestoneID: chosen,
            actual: actual(runs, event: event, phase: phase, host: host),
            projection: nil,
            quantityDomain: TotalMilestoneDomain10868(lower: 0, upper: top + 1),
            quantityTicks: quantityTicks,
            chanceTicks: chanceTicks,
            timing: timing,
            markStyle: .stems)
    }

    /// The app's own admitted run lines for THIS event, each with its one
    /// matrix option. An option key the matrix does not carry exactly once is
    /// dropped, never guessed.
    static func lines(_ event: EventDetail, markets: GameMarketsResponse?) -> [Line] {
        guard let markets, markets.eventId == event.id, let matrix = markets.gameQuestionMatrix,
              let card = MLBTotalsCard11284.build(matrix, actualTotal: nil, eventID: event.id) else { return [] }
        let options = matrix.questions.flatMap(\.options)
        return card.lines.compactMap { line in
            let matches = options.filter { $0.optionKey == line.optionKey }
            guard matches.count == 1, let option = matches.first else { return nil }
            return Line(line: line.line, option: option)
        }
    }

    // MARK: - One milestone

    static func row(_ line: Line, event: EventDetail, phase: BaseballEventPagePhase10868, runs: Int?,
                    host: Host) -> TotalMilestoneRow10868 {
        let count = MLBMilestoneCard11284.milestone(line.line)
        let label = "\(count)+"
        let vocab = SportVocab.forSport(event.sport)
        let before = pregame(line.option, phase: phase, host: host)
        let reached = runs.map {
            PlayerPropsCardView.rungVerdict(servedActual: nil, servedHit: nil, threshold: line.line,
                                            boxActual: Double($0)).hit == true
        } ?? false
        let current: TotalMilestoneCurrent10868
        let performance: String?
        if phase == .live {
            current = reached ? .reached(Words.reachedSoFar) : inGame(line.option, event: event, host: host)
            performance = reached ? nil : runs.map { Words.more(max(1, count - $0), label: label) }
        } else {
            current = .unavailable(Words.inGameUnavailable)
            performance = nil
        }
        return TotalMilestoneRow10868(
            id: line.option.optionKey, quantity: Double(count), quantityLabel: label,
            title: "\(label) \(count == 1 ? vocab.unitSingular : vocab.unit)",
            before: before, beforeMissing: Words.pregameUnavailable,
            current: current, performance: performance,
            result: .unconfirmed(Words.resultUnavailable))
    }

    /// Before first pitch: the quoted price while its own clock is recent.
    /// Once play starts: the producer's admitted pregame pin.
    static func pregame(_ option: QuestionMatrixOption, phase: BaseballEventPagePhase10868,
                        host: Host) -> TotalMilestoneObservation10868? {
        let venue = SourceLabels.label(for: option.published.source)
        if phase == .before {
            guard let quoted = option.published.quotedValue,
                  NFLMilestoneCard9483.isRecent(option.published.observedAt, now: host.now),
                  let at = option.published.observedAt?.asDate else { return nil }
            return observation(quoted, at: at, lead: Words.recorded, venue: venue, host: host)
        }
        guard let pin = NBALadderCard9483.pin(option), let at = pin.at.asDate else { return nil }
        return observation(pin.probability, at: at, lead: Words.savedBeforeStart, venue: venue, host: host)
    }

    /// During play: the quoted price only while recent, observed at or after
    /// the listed start, with the game not suspended. Otherwise the slot's words.
    static func inGame(_ option: QuestionMatrixOption, event: EventDetail, host: Host) -> TotalMilestoneCurrent10868 {
        let start = event.commenceTime?.asDate
        guard let quoted = option.published.quotedValue,
              let at = option.published.observedAt?.asDate,
              NFLMilestoneCard9483.isRecent(option.published.observedAt, now: host.now),
              start.map({ at >= $0 }) ?? false,
              !EventState.isSuspendedAndStarted(event.status, commenceTime: start, now: host.now)
        else { return .unavailable(Words.inGameUnavailable) }
        let venue = SourceLabels.label(for: option.published.source)
        return .recorded(observation(quoted, at: at, lead: Words.recorded, venue: venue, host: host), movement: nil)
    }

    static func observation(_ probability: Double, at: Date, lead: String, venue: String?,
                            host: Host) -> TotalMilestoneObservation10868 {
        let clock = BaseballGamePageAdapter10868.clockWords(at, host: host.page)
        let time = BaseballGamePageAdapter10868.timeWords(at, host: host.page)
        return TotalMilestoneObservation10868(
            probability: probability, text: formatProbability(probability), timeText: time,
            accessibilityDetail: BaseballGamePageAdapter10868.joined(["\(lead) \(clock)", venue]) ?? clock)
    }

    // MARK: - The count

    static func actual(_ runs: Int?, event: EventDetail, phase: BaseballEventPagePhase10868,
                       host: Host) -> TotalMilestoneActual10868? {
        guard phase == .live else { return nil }
        guard let runs else { return .unavailable(Words.scoreUnavailable) }
        let vocab = SportVocab.forSport(event.sport)
        let observed = event.scoreObservedAt?.asDate
        let detail = observed.map { "\(Words.scoreObserved) \(BaseballGamePageAdapter10868.clockWords($0, host: host.page))" }
        return .count(TotalMilestoneCount10868(
            quantity: Double(runs), text: "\(runs)", unit: runs == 1 ? vocab.unitSingular : vocab.unit,
            clock: observed.map { BaseballGamePageAdapter10868.timeWords($0, host: host.page) },
            ruleLabel: "\(runs) so far",
            accessibilityDetail: detail ?? "\(runs) \(runs == 1 ? vocab.unitSingular : vocab.unit) so far"))
    }

    // MARK: - Timing

    static func timing(_ id: String, rows: [TotalMilestoneRow10868],
                       phase: BaseballEventPagePhase10868) -> TotalMilestoneTiming10868? {
        let matches = rows.indices.filter { rows[$0].id == id }
        guard matches.count == 1, let index = matches.first else { return nil }
        typealias T = TotalMilestoneInput10868
        let row = rows[index]
        var out = ["\(T.pregameTitle): \(row.before?.accessibilityDetail ?? row.beforeMissing)"]
        if phase == .live {
            switch row.current {
            case .recorded(let o, _): out.append("\(T.recordedTitle): \(o.accessibilityDetail)")
            case .unavailable(let words), .withheld(let words): out.append("\(T.currentStatusTitle): \(words)")
            case .reached(let words): out.append("\(T.actualSoFarTitle): \(words)")
            }
        }
        return TotalMilestoneTiming10868(milestoneID: id, title: "\(row.title) · \(Words.timingSuffix)", lines: out)
    }
}
