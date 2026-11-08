import Foundation

/// #10873 — what "Get probability" says, decided by the same rules the detail
/// screens draw with.
///
/// Nothing here re-derives a number. A game answer walks the event hero's own
/// branches in the hero's own order (`EventDetailView`'s centre column):
/// finished → venue-settled → the price pair. The pair comes from
/// `OpeningLineHero` + `DrawPricedWinner.printablePair`, its printed tenths
/// from `EventHeadlineTenths10090.pair` (#10090), and whether it is CURRENT or LAST
/// RECORDED from `EventHeadlinePhase9483` on the quote's own clock. A market
/// answer reads `FuturesDetailRowValue` (Won / Lost / price) and
/// `futuresDetailRenderedPercents`, the market page's row value and integers.
/// So Siri and the screen one tap away cannot print two numbers for one
/// observation.
///
/// Four rules the screens already keep, kept here too:
///  - A settled game or market answers with its RESULT, never a price.
///  - A draw-priced match has no separate away chance (`DrawPricedWinner`). The
///    away side answers "not shown", never `1 − home`.
///  - A price with no readable clock is never called current.
///  - A missing number is said to be missing. No figure is made up to fill it.
///
/// Free of AppIntents, so the decision is testable as plain values.
struct ProbabilityAnswer10873: Equatable, Sendable {
    enum Kind: String, Equatable, Sendable {
        /// A current, dated chance on a game that is scheduled or live.
        case current
        /// A price that is no longer current: older than the shared stale bound,
        /// undated, on a game that started and is not live, or on a closed market.
        case lastRecorded
        /// The server's opening-line hero (`OpeningLineHero`): nobody has quoted
        /// the game since the line was posted.
        case openingLine
        /// The game or market is settled and this is its result.
        case result
        /// Over, or stopped, with no result to name.
        case noResult
        /// No number is shown for this outcome.
        case unavailable
        /// The prices could not be reached.
        case offline
    }

    let kind: Kind
    /// The whole answer as one sentence or two: what Siri says, what Shortcuts
    /// shows, and what VoiceOver reads. One string so the three cannot drift.
    let text: String
    /// The printed figure ("62%", "<1%"), when the answer carries one.
    let figure: String?
    /// Both teams' printed figures, on a both-teams game answer
    /// (`gameBothSides`). The away figure is nil when the detail withholds it.
    var figures: Figures? = nil

    struct Figures: Equatable, Sendable {
        let away: String?
        let home: String
    }
}

/// Which side of a game an outcome names.
nonisolated enum GameSide10873: String, CaseIterable, Sendable {
    case away
    case home
}

extension ProbabilityAnswer10873 {
    /// The game's own label, in the search row's order ("away vs home").
    nonisolated static func matchup(away: String, home: String) -> String {
        "\(away) vs \(home)"
    }

    // MARK: - Games

    static func game(_ event: EventDetail, side: GameSide10873, now: Date = Date()) -> Self {
        if let settled = settledGame(event, side: side, now: now) { return settled }
        let team = side == .home ? event.homeTeam : event.awayTeam
        let subject = matchup(away: event.awayTeam, home: event.homeTeam)
        let stopped = stoppedStatus(event, now: now)
        guard let pair = pricePair(event, now: now) else {
            return unavailableGame(subject: subject, team: team, status: stopped)
        }

        let figure: String
        switch side {
        case .home:
            figure = pair.homeFigure
        case .away:
            guard let away = pair.awayFigure else {
                // #5271: the slot is withheld on the detail, so it is here.
                return Self(kind: .unavailable,
                            text: joined(stopped, "Bain Luck doesn't show a separate chance for \(team) in \(subject). It shows \(event.homeTeam)'s chance only."),
                            figure: nil)
            }
            figure = away
        }

        switch pair.reading {
        case .openingLine:
            return Self(kind: .openingLine,
                        text: joined(stopped, "\(subject): \(team) \(figure), from the opening line. No newer price has been quoted."),
                        figure: figure)
        case .current(let context):
            return Self(kind: .current,
                        text: joined(stopped, "\(subject): \(team) \(figure), current win chance.\(context)"),
                        figure: figure)
        case .lastRecorded(let when):
            return Self(kind: .lastRecorded,
                        text: joined(stopped, "\(subject): \(team) \(figure), last recorded win chance\(when)."),
                        figure: figure)
        }
    }

    /// Both teams in one answer, the game page's "60% vs 40%", so Siri has
    /// nothing more to ask once a game is picked. On Alex's phone (1.0.6
    /// TestFlight, Nov 9) Siri stopped on "Running your shortcut" right where
    /// the action used to ask "Which team?". Each figure, its clock and its
    /// wording come from the same `pricePair` read `game(_:side:)` uses, so the
    /// two can never print different numbers; a settled game answers with its
    /// result in the winner's words, and a draw-priced match still prints the
    /// home chance alone (#5271).
    static func gameBothSides(_ event: EventDetail, now: Date = Date()) -> Self {
        if let settled = settledGame(event, side: nil, now: now) { return settled }
        let subject = matchup(away: event.awayTeam, home: event.homeTeam)
        let stopped = stoppedStatus(event, now: now)
        guard let pair = pricePair(event, now: now) else {
            return Self(kind: .unavailable,
                        text: joined(stopped, "Bain Luck has no chances to show for \(subject) right now."),
                        figure: nil)
        }

        let named: String
        let chance: String
        var note = ""
        if let away = pair.awayFigure {
            named = "\(event.awayTeam) \(away), \(event.homeTeam) \(pair.homeFigure)"
            chance = "chances"
        } else {
            named = "\(event.homeTeam) \(pair.homeFigure)"
            chance = "chance"
            note = " Bain Luck doesn't show a separate chance for \(event.awayTeam)."
        }
        let figures = Figures(away: pair.awayFigure, home: pair.homeFigure)
        switch pair.reading {
        case .openingLine:
            return Self(kind: .openingLine,
                        text: joined(stopped, "\(subject): \(named), from the opening line.\(note) No newer price has been quoted."),
                        figure: nil, figures: figures)
        case .current(let context):
            return Self(kind: .current,
                        text: joined(stopped, "\(subject): \(named), current win \(chance).\(note)\(context)"),
                        figure: nil, figures: figures)
        case .lastRecorded(let when):
            return Self(kind: .lastRecorded,
                        text: joined(stopped, "\(subject): \(named), last recorded win \(chance)\(when).\(note)"),
                        figure: nil, figures: figures)
        }
    }

    /// The hero's first three branches: finished, settled at the venue, closed
    /// with no winner. Nil while the game is priced. A finished game is worded
    /// for `side`, or for its winner when `side` is nil.
    private static func settledGame(_ event: EventDetail, side: GameSide10873?, now: Date) -> Self? {
        let subject = matchup(away: event.awayTeam, home: event.homeTeam)
        let commence = event.commenceTime?.asDate

        // 1. Finished: the hero prints the verdict, not a price.
        if EventState.isFinished(event.status) {
            let outcome = EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                servedResult: event.heroSettledResult
            )
            let score = finalScore(event)
            switch outcome {
            case .undecided:
                return Self(kind: .noResult,
                            text: "\(subject) is final. No result has been recorded.",
                            figure: nil)
            case .draw:
                return Self(kind: .result,
                            text: "\(subject) ended in a draw\(score).",
                            figure: nil)
            case .home, .away:
                let winnerSide: GameSide10873 = outcome == .home ? .home : .away
                let winner = winnerSide == .home ? event.homeTeam : event.awayTeam
                let asked = side ?? winnerSide
                let team = asked == .home ? event.homeTeam : event.awayTeam
                let text = winnerSide == asked
                    ? "\(team) won \(subject)\(score)."
                    : "\(team) lost \(subject). \(winner) won\(score)."
                return Self(kind: .result, text: text, figure: nil)
            }
        }

        // 2. Settled at the venue before our own status caught up: the venue's
        //    verdict, verbatim (the hero's rule — never parsed into a score).
        if EventState.showsVenueSettledVerdict(
            event.status, venueSettled: event.venueSettled,
            commenceTime: commence, now: now) {
            if let verdict = event.venueSettledResult,
               !verdict.trimmingCharacters(in: .whitespaces).isEmpty {
                return Self(kind: .result, text: "\(subject) is settled: \(verdict).", figure: nil)
            }
            return Self(kind: .result,
                        text: "\(subject) is settled. No final score has been recorded.",
                        figure: nil)
        }

        // 3. Closed at the venue with no winner (the badge's own words).
        if EventState.showsVenueClosedNoWinner(
            event.status, venueSettled: event.venueSettled,
            venueClosedNoWinner: event.venueClosedNoWinner,
            commenceTime: commence, now: now) {
            return Self(kind: .noResult, text: "\(subject) ended with no winner.", figure: nil)
        }
        return nil
    }

    /// A stopped game keeps its badge word beside whatever the pair says —
    /// only once it has started (#4021: the hero asks the clock too).
    private static func stoppedStatus(_ event: EventDetail, now: Date) -> String? {
        EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: now)
            ? "Game status: \(EventState.suspendedLabel(authorityPeriod: event.espn?.period))."
            : nil
    }

    /// The hero's price pair (step 4), decided once for either answer.
    private struct PricePair {
        enum Reading {
            case openingLine
            case current(context: String)
            case lastRecorded(when: String)
        }
        /// Nil on a draw-priced match: the detail withholds the away slot (#5271).
        let awayFigure: String?
        let homeFigure: String
        let reading: Reading
    }

    /// The pair exactly as the hero resolves it; nil when it has none.
    private static func pricePair(_ event: EventDetail, now: Date) -> PricePair? {
        guard let odds = event.currentOdds else { return nil }
        let shown = OpeningLineHero.resolve(odds, for: event)
        guard let pair = DrawPricedWinner.printablePair(
            away: shown.awayProbability, home: shown.homeProbability, sport: event.sport)
        else { return nil }

        // #10090 (Alex item 39): the hero prints the pair in tenths, so the
        // answer speaks the hero's own strings. Whole numbers here said "23%"
        // beside a hero printing 22.5% (Patriots v Packers, Nov 8).
        // Draw-priced: the away slot is withheld and the lone home number is
        // printed un-normalised, as the hero prints it (#5271).
        let printed = EventHeadlineTenths10090.pair(home: pair.home, away: pair.away)
        let awayFigure: String? = printed.away
        let homeFigure: String = printed.home

        if shown.isOpeningLine {
            return PricePair(awayFigure: awayFigure, homeFigure: homeFigure, reading: .openingLine)
        }
        let commence = event.commenceTime?.asDate
        let observedAt = event.heroProbabilityObservedAt?.asDate
        let phase = EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: commence, isOpeningLine: false,
            observedAt: observedAt, now: now)
        if phase == .current {
            let context: String
            if event.status == "live" {
                context = liveScore(event).map { " Live: \($0)." } ?? " Live."
            } else if let start = startText(event) {
                context = " Starts \(start)."
            } else {
                context = ""
            }
            return PricePair(awayFigure: awayFigure, homeFigure: homeFigure, reading: .current(context: context))
        }
        let when = Liquidity.preciseObservedAt(observedAt).map { ", recorded \($0)" }
            ?? ". No time was recorded for it"
        return PricePair(awayFigure: awayFigure, homeFigure: homeFigure, reading: .lastRecorded(when: when))
    }

    private static func unavailableGame(subject: String, team: String, status: String?) -> Self {
        Self(kind: .unavailable,
             text: joined(status, "Bain Luck has no chance to show for \(team) in \(subject) right now."),
             figure: nil)
    }

    /// ", Away 3, Home 2" when both scores are held, else nothing.
    private static func finalScore(_ event: EventDetail) -> String {
        guard let away = event.awayScore, let home = event.homeScore else { return "" }
        return ", \(event.awayTeam) \(away), \(event.homeTeam) \(home)"
    }

    private static func liveScore(_ event: EventDetail) -> String? {
        guard let away = event.awayScore, let home = event.homeScore else { return nil }
        return "\(event.awayTeam) \(away), \(event.homeTeam) \(home)"
    }

    /// The start, absolute (a spoken "Tomorrow" goes stale in a saved shortcut).
    /// A placeholder time says TBD, the search row's and hero's rule (#8841).
    static func startText(_ event: EventDetail) -> String? {
        startText(commenceTime: event.commenceTime, startIsTbd: event.startIsTbd == true)
    }

    static func startText(commenceTime: String?, startIsTbd: Bool) -> String? {
        if startIsTbd {
            return RelativeTimeText.tbdText(for: commenceTime, relativeDays: false)
        }
        guard let date = commenceTime?.asDate else { return nil }
        return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }

    // MARK: - Markets

    static func market(_ market: FuturesMarketDetail, outcomeID: Int, now: Date = Date()) -> Self {
        guard let outcome = market.outcomes.first(where: { $0.id == outcomeID }) else {
            return Self(kind: .unavailable,
                        text: "That outcome is no longer listed in \(market.name).",
                        figure: nil)
        }
        // The page's own read, `marketSource` included, so a settled Polymarket
        // row the page calls "Result unknown" is never answered as Lost (#698).
        switch FuturesDetailRowValue.of(outcome, marketStatus: market.status, marketSource: market.source) {
        case .verdict(let verdict):
            let word = verdict == .won ? "won" : "lost"
            return Self(kind: .result, text: "\(market.name): \(outcome.name) \(word).", figure: nil)
        case .resultUnknown(let lastRecorded):
            // #698: settled, result not known. The page prints "Result unknown"
            // and, for a finite price, "Last recorded N%" — never a chance, a
            // Won or a Lost.
            let recorded = lastRecorded.map {
                " Its last recorded chance was \(formatProbability($0, renderedPercent: futuresDetailRenderedPercents(market.outcomes)[outcome.id]))."
            } ?? ""
            return Self(kind: .noResult,
                        text: "\(market.name) has closed. The result for \(outcome.name) is not known.\(recorded)",
                        figure: nil)
        case .none:
            return Self(kind: .unavailable,
                        text: "\(market.name): Bain Luck has no price for \(outcome.name) right now.",
                        figure: nil)
        case .price(let probability):
            let percent = futuresDetailRenderedPercents(market.outcomes)[outcome.id]
            let figure = formatProbability(probability, renderedPercent: percent)
            // The outcome's own clock: a verified answer's OLDEST included
            // observation, otherwise the row's price stamp.
            let stamp = outcome.observedAt ?? outcome.lastUpdated
            let when = Liquidity.preciseObservedAt(stamp?.asDate)
            let closed = market.status == "resolved"
            let undated = when == nil
            if !closed, !undated,
               !SourceAge.isStale(stamp, now: now, after: SourceAge.futuresStaleAfter) {
                return Self(kind: .current,
                            text: "\(market.name): \(outcome.name) \(figure), current chance as of \(when!).",
                            figure: figure)
            }
            let recorded = when.map { ", recorded \($0)" } ?? ". No time was recorded for it"
            let lead = closed ? "\(market.name) has closed. " : "\(market.name): "
            let body = closed
                ? "The last recorded chance for \(outcome.name) was \(figure)\(recorded)."
                : "\(outcome.name) \(figure), last recorded chance\(recorded)."
            return Self(kind: .lastRecorded, text: lead + body, figure: figure)
        }
    }

    // MARK: - Failures

    /// Why the detail could not be read, in words that do not name a status code.
    static func failure(_ error: Error, subject: String) -> Self {
        if isOffline(error) {
            return Self(kind: .offline,
                        text: "Bain Luck couldn't reach its prices for \(subject). Check your connection and try again.",
                        figure: nil)
        }
        if case APIError.httpError(let status, _) = error, status == 404 {
            return Self(kind: .unavailable,
                        text: "\(subject) is no longer available in Bain Luck.",
                        figure: nil)
        }
        return Self(kind: .unavailable,
                    text: "Bain Luck couldn't load \(subject) right now.",
                    figure: nil)
    }

    static func isOffline(_ error: Error) -> Bool {
        let underlying: Error
        if case APIError.networkError(let inner) = error {
            underlying = inner
        } else {
            underlying = error
        }
        guard let url = underlying as? URLError else { return false }
        switch url.code {
        case .notConnectedToInternet, .networkConnectionLost, .timedOut,
             .cannotFindHost, .cannotConnectToHost, .dnsLookupFailed,
             .dataNotAllowed, .internationalRoamingOff:
            return true
        default:
            return false
        }
    }

    /// The answer, then the stopped game's status word when there is one.
    private static func joined(_ status: String?, _ body: String) -> String {
        guard let status else { return body }
        return "\(body) \(status)"
    }
}
