import Foundation

/// #10873 — what "Get probability" says, decided by the same rules the detail
/// screens draw with.
///
/// Nothing here re-derives a number. A game answer walks the event hero's own
/// branches in the hero's own order (`EventDetailView`'s centre column):
/// finished → venue-settled → the price pair. The pair comes from
/// `OpeningLineHero` + `DrawPricedWinner.printablePair`, its integers from
/// `EventDetailView.heroPairPercents`, and whether it is CURRENT or LAST
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
        let team = side == .home ? event.homeTeam : event.awayTeam
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
                let text = winnerSide == side
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

        // A stopped game keeps its badge word beside whatever the pair says —
        // only once it has started (#4021: the hero asks the clock too).
        let stopped = EventState.isSuspendedAndStarted(event.status, commenceTime: commence, now: now)
            ? "Game status: \(EventState.suspendedLabel(authorityPeriod: event.espn?.period))."
            : nil

        // 4. The price pair, exactly as the hero resolves it.
        guard let odds = event.currentOdds else {
            return unavailableGame(subject: subject, team: team, status: stopped)
        }
        let shown = OpeningLineHero.resolve(odds, for: event)
        guard let pair = DrawPricedWinner.printablePair(
            away: shown.awayProbability, home: shown.homeProbability, sport: event.sport)
        else {
            return unavailableGame(subject: subject, team: team, status: stopped)
        }

        let figure: String
        switch side {
        case .home:
            if let away = pair.away {
                let percents = EventDetailView.heroPairPercents(shown, away: away, home: pair.home)
                figure = formatProbability(pair.home, renderedPercent: percents.home)
            } else {
                // Draw-priced: the lone home number, rounded alone (#5271).
                figure = formatProbability(pair.home)
            }
        case .away:
            guard let away = pair.away else {
                // #5271: the slot is withheld on the detail, so it is here.
                return Self(kind: .unavailable,
                            text: joined(stopped, "Bain Luck doesn't show a separate chance for \(team) in \(subject). It shows \(event.homeTeam)'s chance only."),
                            figure: nil)
            }
            let percents = EventDetailView.heroPairPercents(shown, away: away, home: pair.home)
            figure = formatProbability(away, renderedPercent: percents.away)
        }

        if shown.isOpeningLine {
            return Self(kind: .openingLine,
                        text: joined(stopped, "\(subject): \(team) \(figure), from the opening line. No newer price has been quoted."),
                        figure: figure)
        }

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
            return Self(kind: .current,
                        text: joined(stopped, "\(subject): \(team) \(figure), current win chance.\(context)"),
                        figure: figure)
        }
        let when = Liquidity.preciseObservedAt(observedAt).map { ", recorded \($0)" }
            ?? ". No time was recorded for it"
        return Self(kind: .lastRecorded,
                    text: joined(stopped, "\(subject): \(team) \(figure), last recorded win chance\(when)."),
                    figure: figure)
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
        switch FuturesDetailRowValue.of(outcome, marketStatus: market.status) {
        case .verdict(let verdict):
            let word = verdict == .won ? "won" : "lost"
            return Self(kind: .result, text: "\(market.name): \(outcome.name) \(word).", figure: nil)
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
