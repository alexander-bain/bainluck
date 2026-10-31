import Foundation

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART FIVE: BOTH
/// TEAMS TO SCORE.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: the both-teams card keeps each original
/// outcome's own pre-match chance, its in-play chance under the hockey
/// stories' rules, each team's goals once play has started and, after the
/// final, each outcome's own result — or that slot's own words.
///
/// Rules, each an existing owner's:
///
///   - market        the owner's admitted market id
///                   (`SoccerPropReadingAdapter10868.Markets.both`); every served
///                   row of it, in served order, is one outcome. Yes and No are
///                   independent readings — never a complement, never
///                   normalised (55% and 45.5% in the retained match).
///   - readings      part three's rules (`SoccerPropReadingAdapter10868`).
///   - default pick  the outcome `QuestionCatalog9483.propOutcomeSide` reads as
///                   the over side ("Yes"), else the first served outcome.
///   - goals         `EventDetail.homeScore/awayScore` after the start, dated
///                   only by `scoreObservedAt`. A team with a goal "has scored" —
///                   an observed sporting fact, never the prop's settlement.
///
/// Whether the market's condition is the full match is the owner's admission;
/// nothing here reads a title. The host passes the event, `/game-markets`, the
/// admitted market, now, the reader's calendar and its held outcome.
enum SoccerBothTeamsAdapter10868 {
    typealias R = SoccerPropReadingAdapter10868

    enum Words {
        static let eyebrow = "BOTH TEAMS TO SCORE"
        static let beforeContext = "At least one goal each"
        static let actualGoals = "Actual goals"
        static let finalGoals = "Final goals"
        static let scoreUnavailable = "Score unavailable"
        static let notStarted = R.Words.notStarted
        static let hasScored = "has scored"
        static let yetToScore = "yet to score"
        static let timingSuffix = "chance timing"
    }

    /// The card, or nil when the admitted market serves no outcome.
    static func input(_ event: EventDetail, markets: GameMarketsResponse?, admitted: Int?, host: R.Host,
                      selectedOutcomeID: String? = nil) -> BothTeamsScoreInput10868? {
        guard let marketID = admitted else { return nil }
        let legs = R.legs(marketID, in: markets)
        guard !legs.isEmpty else { return nil }
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        let outcomes = legs.map { outcome($0, event: event, phase: phase, host: host) }
        let fallback = legs.first { QuestionCatalog9483.propOutcomeSide($0.label) == .over } ?? legs.first
        let chosen = selectedOutcomeID ?? fallback?.id
        return BothTeamsScoreInput10868(
            phase: phase.bothPhase,
            eventID: String(event.id),
            marketID: String(marketID),
            eyebrow: Words.eyebrow,
            subtitle: nil,
            title: nil,
            beforeContext: Words.beforeContext,
            outcomes: outcomes,
            selectedOutcomeID: chosen,
            scoring: scoring(event, phase: phase, host: host),
            timing: chosen.flatMap { id in timing(id, outcomes: outcomes, legs: legs, phase: phase) })
    }

    static func outcome(_ leg: R.Leg, event: EventDetail, phase: SoccerEventPagePhase10868,
                        host: R.Host) -> BothTeamsOutcome10868 {
        let before = R.pregame(leg, event: event, host: host)
        let current: BothTeamsCurrent10868
        if phase == .live {
            switch R.current(leg, event: event, host: host) {
            case .recorded(let o): current = .recorded(observation(o), movement: nil)
            case .withheld(let words): current = .withheld(words)
            case .unavailable(let words): current = .unavailable(words)
            }
        } else {
            current = .unavailable(R.Words.inPlayUnavailable)
        }
        let result: BothTeamsResult10868
        switch phase == .before ? R.Result.unconfirmed(R.Words.resultUnavailable) : R.result(leg) {
        case .won(let words): result = .won(words)
        case .lost(let words): result = .lost(words)
        case .unconfirmed(let words): result = .unconfirmed(words)
        }
        return BothTeamsOutcome10868(id: leg.id, label: leg.label, before: before.observation.map { Self.observation($0) },
                                     beforeMissing: before.words, current: current, result: result)
    }

    static func observation(_ o: R.Observation) -> BothTeamsObservation10868 {
        BothTeamsObservation10868(probability: o.probability, text: o.text, timeText: o.clock,
                                  accessibilityDetail: o.detail)
    }

    /// Both teams' goals, read during play and after the final only.
    static func scoring(_ event: EventDetail, phase: SoccerEventPagePhase10868, host: R.Host) -> BothTeamsScoring10868 {
        let names = SoccerMatchPageAdapter10868.names(event)
        let final = phase == .final
        let title = final ? Words.finalGoals : Words.actualGoals
        guard phase != .before, let goals = R.goals(event) else {
            let words = phase == .before ? Words.notStarted : Words.scoreUnavailable
            return BothTeamsScoring10868(
                title: title,
                home: BothTeamsTeam10868(name: names.home, actual: .unavailable(words)),
                away: BothTeamsTeam10868(name: names.away, actual: .unavailable(words)),
                clock: nil, accessibilityDetail: nil)
        }
        return BothTeamsScoring10868(
            title: title,
            home: BothTeamsTeam10868(name: names.home, actual: .count(text: "\(goals.home)",
                                                                       status: final ? nil : status(goals.home))),
            away: BothTeamsTeam10868(name: names.away, actual: .count(text: "\(goals.away)",
                                                                       status: final ? nil : status(goals.away))),
            clock: R.goalsClock(goals, final: final, host: host),
            accessibilityDetail: R.goalsDetail(goals, event: event, final: final, host: host))
    }

    /// One team's own count: an observed sporting state, never a settlement.
    static func status(_ goals: Int) -> String {
        goals > 0 ? Words.hasScored : Words.yetToScore
    }

    static func timing(_ id: String, outcomes: [BothTeamsOutcome10868], legs: [R.Leg],
                       phase: SoccerEventPagePhase10868) -> BothTeamsTiming10868? {
        guard outcomes.filter({ $0.id == id }).count == 1,
              let index = outcomes.firstIndex(where: { $0.id == id }) else { return nil }
        typealias T = BothTeamsScoreInput10868
        let outcome = outcomes[index]
        var lines = ["\(T.pregameTitle): \(outcome.before?.accessibilityDetail ?? outcome.beforeMissing)"]
        if phase == .live {
            switch outcome.current {
            case .recorded(let o, _): lines.append("\(T.currentTitle): \(o.accessibilityDetail)")
            case .unavailable(let words), .withheld(let words), .reached(let words):
                lines.append("\(T.currentTitle): \(words)")
            }
        }
        if phase == .final {
            let settled: Bool
            if case .unconfirmed = outcome.result { settled = false } else { settled = true }
            let venue = settled ? SourceLabels.label(for: legs[index].row.source) : nil
            lines.append(SoccerMatchPageAdapter10868.joined(["\(T.resultTitle): \(outcome.result.text)",
                                                             venue.map { "settled by \($0)" }]) ?? outcome.result.text)
        }
        return BothTeamsTiming10868(outcomeID: id, title: "\(outcome.label) · \(Words.timingSuffix)", lines: lines)
    }
}
