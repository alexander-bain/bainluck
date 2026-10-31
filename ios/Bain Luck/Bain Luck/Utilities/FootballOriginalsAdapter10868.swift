import SwiftUI

/// #10868 — THE FOOTBALL SCREEN'S PRODUCTION ADAPTER, PART SIX: "ALL PROPS", THE
/// ORIGINAL CATALOGUE AND ITS DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on every NFL route "All props" lists every
/// original market outcome the page serves, once each, in the page's own
/// catalogue order, and each original's Details print its own pregame chance,
/// its own later reading and its own venue grade — or that slot's own words —
/// so an old quote is never sold as today's chance.
///
/// Membership, order, identity, About, labels and the grade are the accepted
/// hockey originals adapter's (H4, `HockeyJourneyOriginalsAdapter10868`), called
/// rather than copied: `matched` (`QuestionCatalog9483.build` mapped back to its
/// served rows by build's own keys), `identity(of:)`, `aboutSection`,
/// `absenceWords`, `contractGrade` and `label`. The in-game reading is the soccer
/// adapter's (`SoccerOriginalsAdapter10868.laterReading`): H4's admission (dated,
/// at or after the listed start, recent; a settled row has no chance) plus its
/// refusal of a game-line row's sibling-capped clock, a refused quote kept as the
/// Details' historical quote with its own clock and venue — never the card figure.
///
/// The pregame reading is football's, by the same production rules:
///   - before the start, the catalogue's own price only on its own, recent clock
///     (H4's rule with the soccer adapter's own-clock guard);
///   - once started, an over-side player prop's served `pregame_mark` (H4,
///     `NFLMilestoneCard9483.cards`' basis), else the typed question matrix's own
///     pregame pin for the same market and contributor outcomes, dated before the
///     start (`SoccerPropReadingAdapter10868.option` / `.pin`), else "Pregame
///     chance unavailable" — never "not recorded": the page cannot see that.
///
/// The host passes the event, `/game-markets`, now, the reader's calendar, the
/// tint and its held selection, passed through unchanged for the leaf to resolve
/// by exact scope and identity. Nothing here fetches.
///
/// IDENTITY: the markets are read only when their served `eventId` is this
/// event's (`FootballInputIdentityAdapter10868`); another game's markets list no
/// original here, whatever their clubs and players.
///
/// PERIOD WINNERS: an original the period-winner story admitted
/// (`FootballPeriodWinnersAdapter10868.Admitted`) shows, in its Details, the
/// SAME admitted pregame trade and clock the card draws
/// (`detailsReadings`), and its contract's own bound rule text
/// (`detailsRules`); every other original is unchanged.
enum FootballOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483
    typealias H4 = HockeyJourneyOriginalsAdapter10868
    typealias R = SoccerPropReadingAdapter10868
    /// The reader's clock and calendar (the soccer prop host's shape).
    typealias Host = SoccerPropReadingAdapter10868.Host

    enum Words {
        static let heading = "All props"
        static let emptyWords = "No original props recorded for this game"
        static let unavailableChoice = "Unnamed original"
        static let pregameUnavailable = "Pregame chance unavailable"
        static let savedBeforeStart = "Saved before the start"
        static let savedBeforeKickoff = "Saved before kickoff"
        static let recorded = "Recorded"

        static func context(_ count: Int) -> String {
            count == 1 ? "1 original" : "\(count) originals"
        }
    }

    // MARK: - The page's originals

    /// The originals group for the page at `host.now`. No served outcome is no
    /// catalogue, which draws `emptyWords`.
    static func originals(_ event: EventDetail, markets: GameMarketsResponse?, host: Host, tint: Color,
                          selection: Details.Selection? = nil,
                          periodWinners: [FootballPeriodWinnersAdapter10868.Admitted] = []) -> FootballEventPageOriginals10868 {
        let phase = FootballEventPageAdapter10868.phase(event, now: host.now)
        let started = HockeyJourneyContributionAdapter10868.hasStarted(event, now: host.now)
        let own = FootballInputIdentityAdapter10868.markets(markets, for: event)
        let found = own.map { H4.matched($0, status: event.status, now: host.now) } ?? []
        let matrix = own?.gameQuestionMatrix
        let readings = FootballPeriodWinnersAdapter10868.detailsReadings(periodWinners)
        let rules = FootballPeriodWinnersAdapter10868.detailsRules(periodWinners)
        let built = found.map {
            withPeriodBinding(original($0, event: event, phase: phase, started: started, matrix: matrix, host: host),
                              reading: readings, rules: rules)
        }
        var labels: [Details.Identity: String] = [:]
        for (match, made) in zip(found, built) {
            labels[made.identity] = H4.label(match.source, event: event)
        }
        return FootballEventPageOriginals10868(
            catalogue: built.isEmpty ? nil : Details.Catalogue(scope: scope(event, phase: phase), originals: built),
            selection: selection,
            labels: labels,
            heading: Words.heading,
            context: built.isEmpty ? nil : Words.context(built.count),
            emptyWords: Words.emptyWords,
            unavailableChoice: Words.unavailableChoice,
            tint: tint)
    }

    /// One catalogue per event and phase.
    static func scope(_ event: EventDetail, phase: FootballEventPagePhase10868) -> String {
        "nfl:\(event.id):\(phase):originals"
    }

    // MARK: - One original

    /// The original with the period-winner story's admitted reading and bound
    /// rules for its exact identity, when it has them; otherwise unchanged.
    static func withPeriodBinding(_ made: Details.Original, reading readings: [Details.Identity: Details.Reading],
                                  rules: [Details.Identity: [String]]) -> Details.Original {
        let reading = readings[made.identity]
        let bound = rules[made.identity]
        guard reading != nil || bound != nil else { return made }
        let about = bound.map {
            Details.About(source: made.about.source, rules: .verified($0), provenance: made.about.provenance,
                          historicalQuote: made.about.historicalQuote)
        } ?? made.about
        return Details.Original(identity: made.identity, title: made.title, outcome: made.outcome, mode: made.mode,
                                pregame: reading ?? made.pregame, later: made.later, grade: made.grade,
                                about: about, beforeLabel: made.beforeLabel)
    }

    static func original(_ match: H4.Match, event: EventDetail, phase: FootballEventPagePhase10868,
                         started: Bool, matrix: EventQuestionMatrix?, host: Host) -> Details.Original {
        let mode: Details.Mode
        let later: Details.Reading?
        let grade: Details.Grade?
        let quote: Details.HistoricalQuote?
        switch phase {
        case .before:
            mode = .pregame
            later = nil
            grade = nil
            quote = nil
        case .live:
            let reading = SoccerOriginalsAdapter10868.laterReading(match, event: event, host: host)
            mode = .comparison(.current)
            later = reading.later
            grade = nil
            quote = reading.quote
        case .final:
            mode = .result
            later = nil
            grade = H4.contractGrade(match.source)
            quote = nil
        }
        return Details.Original(
            identity: H4.identity(of: match.source), title: match.group.question, outcome: match.outcome.label,
            mode: mode,
            pregame: pregameReading(match, started: started, event: event, matrix: matrix, host: host),
            later: later, grade: grade, about: H4.aboutSection(match.source, historicalQuote: quote))
    }

    /// Before the start: the catalogue's own price on its own recent clock.
    /// Once started: the prop's served mark, else the matrix's dated pregame
    /// pin, else its absence words.
    static func pregameReading(_ match: H4.Match, started: Bool, event: EventDetail,
                               matrix: EventQuestionMatrix?, host: Host) -> Details.Reading {
        let venue = SourceLabels.label(for: match.source.row.source)
        if started {
            if let prop = match.source.prop, QuestionCatalog9483.lineSide(match.source.row) == .over,
               let mark = R.admissible(prop.pregameMark) {
                return .value(formatProbability(mark), placement: mark,
                              provenance: SoccerMatchPageAdapter10868.joined([Words.savedBeforeStart, venue]))
            }
            let market = match.source.marketID ?? match.source.marketIDs?.first
            let option = market.flatMap { R.option($0, contributors: match.source.outcomeIDs ?? [], in: matrix) }
            guard let pin = R.pin(option, start: event.commenceTime?.asDate) else {
                return .missing(Words.pregameUnavailable)
            }
            let clock = "\(Words.savedBeforeKickoff) \(clockWords(pin.observedAt, host))"
            return .value(formatProbability(pin.probability), placement: pin.probability,
                          provenance: SoccerMatchPageAdapter10868.joined([clock, venue]))
        }
        guard let price = R.admissible(match.outcome.probability) else {
            return .missing(H4.absenceWords(match.outcome, status: event.status))
        }
        guard SoccerOriginalsAdapter10868.clockIsOwn(match.source),
              NFLMilestoneCard9483.isRecent(match.outcome.observedAt, now: host.now),
              let at = match.outcome.observedAt?.asDate
        else { return .missing(AllMarketsCatalogView9483.noRecentPrice) }
        return .value(formatProbability(price), placement: price,
                      provenance: SoccerMatchPageAdapter10868.joined(["\(Words.recorded) \(clockWords(at, host))", venue]))
    }

    private static func clockWords(_ date: Date, _ host: Host) -> String {
        SoccerMatchPageAdapter10868.clockWords(date, host: host.words)
    }
}
