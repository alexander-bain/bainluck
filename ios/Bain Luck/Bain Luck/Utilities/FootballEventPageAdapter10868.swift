import SwiftUI

/// #10868 — THE FOOTBALL SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE, TEAMS,
/// HEADER AND THE PHASE'S PROBABILITY COMPARISON.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on every NFL route the comparison above
/// the history prints exactly the chances, scores and forecasts the event page
/// already decides — each team's win chance and projected final before the
/// game, the eight values during play, the earlier expectation against the
/// actual final after it — in the accepted 9483 headlines' own grammar.
///
/// It decides nothing the app does not already decide. Each headline input is
/// the exact value that headline's own "Mount" note names, from the public
/// parts of `EventDetailView`'s private arrangement:
///
///   - phase           `HockeyJourneyPageAdapter10868.phase` (H1): finished,
///                     live, or suspended after the start (`EventState`). The
///                     same rule, called, so two screens cannot disagree.
///   - paired          `EventDetailView.nflPairedHeadline` (private), rebuilt
///                     here from the same calls in the same order:
///                     `MLBFinalPage11284.adoptsPairedPage`, `EventOutcome.resolve`
///                     + `NFLPairedHeadline9483.final` after the final;
///                     `EventState.showsVenueSettledVerdict`, `OpeningLineHero.resolve`,
///                     `DrawPricedWinner.printablePair`,
///                     `EventDetailView.heroPairPercents` + `formatProbability` +
///                     `NFLPairedHeadline9483.priced` before and during play.
///                     The pregame line is `PrematchReading.resolve`.
///   - chance phase    `EventHeadlinePhase9483.resolve` on the clock the host
///                     displays (`vm.displayedProbabilityObservedAt`), as
///                     `headlinePhaseLabel` reads it.
///   - projected final before the game, `EventDetailView.projectionText` →
///                     `projectionFigure9483` → `projectedPair11285` (the
///                     headline's own chain). Live, `EventDetailView.liveForecast11296`
///                     (#2920 + #11296). After the final,
///                     `EventDetailView.qualifiedFinalForecast11296`.
///   - score           `EventDetailView.showsScore` and the served scores.
///   - state words     H1's `stateWords`: before, "Before game · 5:15 PM start"
///                     (or start to be announced); during play the app's one
///                     suspended treatment or `PeriodLabel.liveStatusText`
///                     (through H1 — this file calls no period rule itself);
///                     after, "Final" with the day.
///   - pregame context `EventDetailView.adoptedPregameContext9483` (private),
///                     rebuilt from its public gates: the broadcast only while
///                     `EventDetailView.showsBroadcast`, TBD through
///                     `RelativeTimeText.tbdText`, else the start in the reader's
///                     calendar.
///   - names, tints    `TeamShortName.shortPair`, `TeamTextContrast.cardColors`.
///
/// A suspended game after its start is during play, but no accepted headline
/// arm admits it (the live headline needs a live status, the pregame one an
/// unstarted game), so the page shows the suspended treatment and its
/// unavailable words — production keeps its private `nflPairedHeadlineView`
/// there. Nothing here subscribes, schedules, ranks or fetches.
///
/// IDENTITY: the ladders' projected-final pair (`pmSpreadData.projectedFinal`)
/// that the live forecast and the pregame projection fall back on is read from
/// the history the host holds, and only when that history's served `eventId` is
/// this event's (`FootballInputIdentityAdapter10868.ladder`). A foreign history
/// gives no ladder; the headline's own served values are unaffected.
enum FootballEventPageAdapter10868 {
    typealias H1 = HockeyJourneyPageAdapter10868

    /// What the host already holds, passed in unchanged.
    struct Host {
        /// `vm.displayedProbabilityObservedAt(event)`. Nil is undated: "last recorded".
        let probabilityObservedAt: Date?
        /// `vm.liveUpdateStatus == .interrupted`.
        let deliveryInterrupted: Bool
        /// `vm.history` — read here for the ladders' pair only, and only when it
        /// is this event's (`ladder(for:)`).
        let history: EventHistoryResponse?
        let now: Date
        let calendar: Calendar
        let locale: Locale

        init(probabilityObservedAt: Date?, deliveryInterrupted: Bool = false,
             history: EventHistoryResponse? = nil, now: Date = Date(),
             calendar: Calendar = .current, locale: Locale = .current) {
            self.probabilityObservedAt = probabilityObservedAt
            self.deliveryInterrupted = deliveryInterrupted
            self.history = history
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        /// This event's own ladders' pair, or none.
        func ladder(for event: EventDetail) -> (home: Double?, away: Double?) {
            FootballInputIdentityAdapter10868.ladder(history, for: event)
        }

        /// H1's host, for its phase, state and clock words. Football reads no
        /// H1 projection, so no ladder is handed to it.
        var words: H1.Host {
            H1.Host(probabilityObservedAt: probabilityObservedAt, deliveryInterrupted: deliveryInterrupted,
                    ladderHome: nil, ladderAway: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    enum Words {
        /// The headline's caption for the projection, as the page spells it.
        static let projectedFinal = "Projected final"
        static let noScore = "Score unavailable"
        /// The comparison's owner declined (Design-approved words).
        static let headlineUnavailable = "Win chance unavailable"
    }

    // MARK: - Phase, teams

    static func phase(_ event: EventDetail, now: Date) -> FootballEventPagePhase10868 {
        switch H1.phase(event, now: now) {
        case .before: .before
        case .live: .live
        case .final: .final
        }
    }

    static func hockeyPhase(_ phase: FootballEventPagePhase10868) -> HockeyJourneyPagePhase10868 {
        switch phase {
        case .before: .before
        case .live: .live
        case .final: .final
        }
    }

    static func teams(_ event: EventDetail) -> FootballEventPageTeams10868 {
        let short = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        return FootballEventPageTeams10868(away: event.awayTeam, home: event.homeTeam,
                                           awayShort: short.away, homeShort: short.home,
                                           awayColor: tints.away, homeColor: tints.home)
    }

    // MARK: - Header

    static func header(_ event: EventDetail, phase: FootballEventPagePhase10868,
                       host: Host) -> FootballEventPageHeader10868 {
        let state = H1.stateWords(event, phase: hockeyPhase(phase), host: host.words).state
        return FootballEventPageHeader10868(
            state: state, score: phase == .before ? nil : scoreWords(event), aboutLabel: nil)
    }

    /// The served score once the page prints one, else its absence words.
    static func scoreWords(_ event: EventDetail) -> FootballEventPageScore10868 {
        guard let score = score(event) else { return .unavailable(Words.noScore) }
        let names = teams(event)
        return .actual(away: "\(score.away)", home: "\(score.home)",
                       spoken: "\(names.awayShort) \(score.away), \(names.homeShort) \(score.home)")
    }

    /// `EventDetailView.showsScore`'s pair, or nil.
    static func score(_ event: EventDetail) -> (away: Int, home: Int)? {
        guard EventDetailView.showsScore(status: event.status, away: event.awayScore, home: event.homeScore),
              let away = event.awayScore, let home = event.homeScore else { return nil }
        return (away, home)
    }

    // MARK: - Headline

    static func headline(_ event: EventDetail, host: Host) -> FootballEventPageHeadline10868 {
        let pagePhase = phase(event, now: host.now)
        let arm: FootballHeadlineArm10868
        switch pagePhase {
        case .before: arm = .before(beforeArm(event, host: host))
        case .live: arm = .live(liveArm(event, host: host))
        case .final: arm = .final(finalArm(event, host: host))
        }
        return FootballEventPageHeadline10868(sportKey: event.sport, arm: arm)
    }

    static func beforeArm(_ event: EventDetail, host: Host) -> FootballPregameHeadline10868 {
        FootballPregameHeadline10868(
            status: event.status,
            hasStarted: EventState.hasStarted(commenceTime: event.commenceTime?.asDate, now: host.now),
            isOpeningLine: isOpeningLine(event),
            paired: paired(event, now: host.now),
            chancePhase: chancePhase(event, host: host),
            projected: projectedPair(event, host: host),
            forecastLabel: Words.projectedFinal,
            pregameContext: pregameContext(event, host: host))
    }

    static func liveArm(_ event: EventDetail, host: Host) -> FootballLiveHeadline10868 {
        let actual = score(event)
        let center: NFLPairedHeadline9483.Center? = actual.map { .score(away: $0.away, home: $0.home, final: false) }
        return FootballLiveHeadline10868(
            status: event.status,
            paired: paired(event, now: host.now),
            chancePhase: chancePhase(event, host: host),
            baseline: PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds),
            score: center,
            forecast: EventDetailView.liveForecast11296(
                event, ladderHome: host.ladder(for: event).home, ladderAway: host.ladder(for: event).away,
                hasScore: actual != nil, now: host.now),
            gameState: H1.stateWords(event, phase: .live, host: host.words).state)
    }

    static func finalArm(_ event: EventDetail, host: Host) -> FootballFinalHeadline10868 {
        let center: NFLPairedHeadline9483.Center? = score(event).map { .score(away: $0.away, home: $0.home, final: true) }
        return FootballFinalHeadline10868(
            status: event.status,
            paired: paired(event, now: host.now),
            baseline: PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds),
            score: center,
            forecast: EventDetailView.qualifiedFinalForecast11296(event),
            finalContext: finalContext(event, host: host))
    }

    /// `EventDetailView.nflPairedHeadline`, from its public parts, in its order.
    static func paired(_ event: EventDetail, now: Date) -> NFLPairedHeadline9483? {
        guard MLBFinalPage11284.adoptsPairedPage(sportKey: event.sport, status: event.status) else { return nil }
        let actual = score(event)
        let pregame = PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)
        if EventState.isFinished(event.status) {
            let outcome = EventOutcome.resolve(status: event.status, homeScore: event.homeScore,
                                               awayScore: event.awayScore, servedResult: event.heroSettledResult)
            let homeWon: Bool? = outcome == .home ? true : outcome == .away ? false : nil
            return NFLPairedHeadline9483.final(homeWon: homeWon, score: actual, pregame: pregame)
        }
        guard !EventState.showsVenueSettledVerdict(event.status, venueSettled: event.venueSettled,
                                                    commenceTime: event.commenceTime?.asDate, now: now),
              let odds = event.currentOdds
        else { return nil }
        let shown = OpeningLineHero.resolve(odds, for: event)
        guard !shown.isOpeningLine,
              let pair = DrawPricedWinner.printablePair(away: shown.awayProbability, home: shown.homeProbability,
                                                        sport: event.sport),
              let away = pair.away
        else { return nil }
        let percents = EventDetailView.heroPairPercents(shown, away: away, home: pair.home)
        return NFLPairedHeadline9483.priced(
            awayText: formatProbability(away, renderedPercent: percents.away),
            homeText: formatProbability(pair.home, renderedPercent: percents.home),
            live: event.status == "live", score: actual, pregame: pregame)
    }

    static func isOpeningLine(_ event: EventDetail) -> Bool {
        event.currentOdds.map { OpeningLineHero.resolve($0, for: event).isOpeningLine } ?? false
    }

    /// The pair's subject and age on the displayed clock (`headlinePhaseLabel`).
    static func chancePhase(_ event: EventDetail, host: Host) -> EventHeadlinePhase9483? {
        EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: event.commenceTime?.asDate,
            isOpeningLine: isOpeningLine(event), observedAt: host.probabilityObservedAt,
            deliveryInterrupted: host.deliveryInterrupted, now: host.now)
    }

    /// The headline's printed integers: `projectionText` → `projectionFigure9483`
    /// → `projectedPair11285`. A figure that is not a plain pair is none.
    static func projectedPair(_ event: EventDetail, host: Host) -> FootballPointsPair10868? {
        let ladder = host.ladder(for: event)
        guard let text = EventDetailView.projectionText(
            event, ladderHome: ladder.home, ladderAway: ladder.away,
            hasScore: score(event) != nil, now: host.now),
              let pair = EventDetailView.projectedPair11285(EventDetailView.projectionFigure9483(text))
        else { return nil }
        return FootballPointsPair10868(away: pair.away, home: pair.home)
    }

    /// `adoptedPregameContext9483`'s broadcast and start, from its public gates.
    static func pregameContext(_ event: EventDetail, host: Host) -> String? {
        var parts: [String] = []
        if let broadcast = event.espn?.broadcast,
           EventDetailView.showsBroadcast(status: event.status, commenceTime: event.commenceTime?.asDate,
                                          now: host.now) {
            parts.append(broadcast)
        }
        if event.startIsTbd == true {
            if let tbd = RelativeTimeText.tbdText(for: event.commenceTime, now: host.now, relativeDays: false) {
                parts.append(tbd)
            }
        } else if let date = event.commenceTime?.asDate {
            parts.append(H1.clockWords(date, host: host.words))
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// "Final · Sun, Oct 11" — H1's final state and its day.
    static func finalContext(_ event: EventDetail, host: Host) -> String {
        let words = H1.stateWords(event, phase: .final, host: host.words)
        return [words.state, words.context].compactMap { $0 }.joined(separator: " · ")
    }
}
