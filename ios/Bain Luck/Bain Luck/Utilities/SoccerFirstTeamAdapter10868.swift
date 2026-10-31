import Foundation

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART SIX: FIRST TEAM
/// TO SCORE.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: the first-team card keeps each original
/// outcome (both teams and Neither) with its own pre-match chance, its in-play
/// chance or its own result under the hockey stories' rules, and during play
/// the observed score checkpoints — observation times, never goal times.
///
/// Rules, each an existing owner's:
///
///   - market        the owner's admitted market id
///                   (`SoccerPropReadingAdapter10868.Markets.first`); every served
///                   row of it, in served order, is one plot row, named by its
///                   served outcome. Neither is a genuine outcome, never a player
///                   and never described as having scored.
///   - readings      part three's rules (`SoccerPropReadingAdapter10868`); a
///                   result the venue settles during play replaces the in-play
///                   reading (the leaf's own rule).
///   - words         the leaf's outcome context: caller-chosen words for a team
///                   or Neither, so nobody is called a player.
///   - checkpoints   `/history`'s `score_history`, in served order, each with its
///                   own observation clock, during play only. Never a first-scorer
///                   inference, a settlement or a goal time.
///   - axis          the fixed 0–100% scale, scale words not chances.
///
/// No confirmed first team is supplied: the leaf names it only when exactly one
/// is admitted, and the per-row results already say who won. The host passes
/// the event, `/game-markets`, `/history`, the admitted market, now, the
/// reader's calendar and its held outcome.
enum SoccerFirstTeamAdapter10868 {
    typealias R = SoccerPropReadingAdapter10868

    enum Words {
        static let title = "First team to score"
        static let plotTitle = "Pre-match chances"
        static let checkpointsTitle = "Observed scores"
        static let checkpointsNote = "Observation times, not exact goal times."
        static let timingSuffix = "chance timing"
    }

    /// The leaf's words for a team or Neither.
    static let outcomeWords = FirstScorerOutcomeContext10868(
        pregameTitle: "Pre-match chance", currentTitle: "Current chance", liveResultTitle: "Result",
        finalResultTitle: "Final result", selectionUnavailable: "Selected outcome unavailable.",
        spokenPregame: "Pre-match chance", spokenCurrent: "Current chance", spokenResult: "Result",
        selectHint: "Selects this outcome’s comparison")

    static let axis = FirstScorerAxis10868(lower: 0, upper: 1, ticks: [
        FirstScorerTick10868(value: 0, text: "0%"),
        FirstScorerTick10868(value: 0.5, text: "50%"),
        FirstScorerTick10868(value: 1, text: "100%"),
    ])

    /// The card, or nil when the admitted market serves no outcome.
    static func input(_ event: EventDetail, markets: GameMarketsResponse?, history: EventHistoryResponse?,
                      admitted: Int?, host: R.Host, selectedID: String? = nil) -> FirstScorerComparisonInput10868? {
        guard let marketID = admitted else { return nil }
        let legs = R.legs(marketID, in: markets)
        guard !legs.isEmpty else { return nil }
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        let rows = legs.map { row($0, event: event, phase: phase, host: host) }
        let chosen = selectedID ?? rows.first?.id
        return FirstScorerComparisonInput10868(
            phase: phase.firstPhase,
            title: Words.title,
            context: SourceLabels.label(for: legs.first?.row.source),
            overview: rows,
            selectedID: chosen,
            selectedRow: nil,
            plotTitle: Words.plotTitle,
            axis: axis,
            coverage: nil,
            confirmed: nil,
            timing: chosen.flatMap { id in timing(id, rows: rows, phase: phase) },
            outcome: outcomeWords,
            scorePath: phase == .live ? checkpoints(event, history: history, host: host) : nil)
    }

    static func row(_ leg: R.Leg, event: EventDetail, phase: SoccerEventPagePhase10868,
                    host: R.Host) -> FirstScorerRow10868 {
        let before = R.pregame(leg, event: event, host: host)
        let current: FirstScorerCurrent10868
        if phase == .live {
            switch R.current(leg, event: event, host: host) {
            case .recorded(let o): current = .recorded(observation(o))
            case .withheld(let words): current = .stale(words)
            case .unavailable(let words): current = .unavailable(words)
            }
        } else {
            current = .unavailable(R.Words.inPlayUnavailable)
        }
        let result: FirstScorerResult10868
        switch phase == .before ? R.Result.unconfirmed(R.Words.resultUnavailable) : R.result(leg) {
        case .won(let words): result = .won(words)
        case .lost(let words): result = .lost(words)
        case .unconfirmed(let words): result = .unconfirmed(words)
        }
        return FirstScorerRow10868(id: leg.id, name: leg.label, team: nil,
                                   pregame: before.observation.map { Self.observation($0) },
                                   pregameMissing: before.words, current: current, result: result)
    }

    static func observation(_ o: R.Observation) -> FirstScorerObservation10868 {
        FirstScorerObservation10868(probability: o.probability, text: o.text, accessibilityDetail: o.detail)
    }

    /// `score_history` as served: each checkpoint with its own observation clock.
    static func checkpoints(_ event: EventDetail, history: EventHistoryResponse?,
                            host: R.Host) -> FirstScorerScorePath10868? {
        let names = SoccerMatchPageAdapter10868.names(event)
        let words = host.words
        // Another event's score path is never this match's: only a response served
        // under this event's own id is read.
        let own = history?.eventId == event.id ? history : nil
        let observations: [FirstScorerScoreObservation10868] = (own?.scoreHistory ?? []).compactMap { point in
            guard let at = point.timestamp.asDate else { return nil }
            guard point.homeScore >= 0 else { return nil }
            guard point.awayScore >= 0 else { return nil }
            let score = "\(point.homeScore)–\(point.awayScore)"
            let spoken = "\(names.home) \(point.homeScore), \(names.away) \(point.awayScore)"
            return FirstScorerScoreObservation10868(
                id: point.timestamp, score: score, time: SoccerMatchPageAdapter10868.timeWords(at, host: words),
                accessibilityText: "\(spoken) · observed \(SoccerMatchPageAdapter10868.clockWords(at, host: words))")
        }
        guard !observations.isEmpty else { return nil }
        return FirstScorerScorePath10868(title: Words.checkpointsTitle, note: Words.checkpointsNote,
                                         observations: observations)
    }

    static func timing(_ id: String, rows: [FirstScorerRow10868], phase: SoccerEventPagePhase10868) -> FirstScorerTiming10868? {
        guard rows.filter({ $0.id == id }).count == 1, let row = rows.first(where: { $0.id == id }) else { return nil }
        var lines = ["\(outcomeWords.pregameTitle): \(row.pregame?.accessibilityDetail ?? row.pregameMissing)"]
        if phase == .live {
            if row.result.isAdmitted {
                lines.append("\(outcomeWords.liveResultTitle): \(row.result.text)")
            } else {
                switch row.current {
                case .recorded(let o): lines.append("\(outcomeWords.currentTitle): \(o.accessibilityDetail)")
                case .unavailable(let words), .stale(let words): lines.append("\(outcomeWords.currentTitle): \(words)")
                }
            }
        }
        if phase == .final {
            lines.append("\(outcomeWords.finalResultTitle): \(row.result.text)")
        }
        return FirstScorerTiming10868(playerID: id, title: "\(row.name) · \(Words.timingSuffix)", lines: lines)
    }
}
