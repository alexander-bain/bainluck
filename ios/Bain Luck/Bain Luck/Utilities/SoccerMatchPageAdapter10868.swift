import SwiftUI

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE,
/// HEADER AND THE THREE-OUTCOME HEADLINE.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: the soccer match screen names home win,
/// Draw and away win as three equal outcomes and prints for each exactly the
/// chance the event page already prints — or that outcome's own words for why
/// it has none — beside the state, date, score, clock and projected final the
/// page already decides.
///
/// It decides nothing the app does not already decide. Each slot is the output
/// of the authority that owns it, or that slot's own absence words:
///
///   - phase           `EventState` — finished, live, suspended after the start.
///   - home chance     the hero's own calls for a draw-priced sport:
///                     `OpeningLineHero.resolve` on `currentOdds`, then
///                     `DrawPricedWinner.printablePair`, then `formatProbability`
///                     on the home side ALONE (EventDetailView's draw-priced arm
///                     rounds the lone side by itself, never through a pair).
///                     "Current" versus "last recorded" is
///                     `EventHeadlinePhase9483.resolve` on the clock the host
///                     displays (`vm.displayedProbabilityObservedAt`).
///   - pre-match       `PrematchReading.resolve` (served ladder, else the
///                     `opening_odds` fallback, named by its own caption word),
///                     through `DrawPricedWinner.printablePair`: home only.
///   - Draw, away      NEVER derived. `DrawPricedWinner.printablePair` ignores
///                     an away figure on a draw-priced sport — the served
///                     `current_odds.away_probability` / `prematch_odds` away is
///                     a two-way number that absorbs the draw (#5271) — and the
///                     event payload carries no draw at all. Both slots keep
///                     their own absence words. The dependency is named, not
///                     routed around: a genuine current three-way writer and its
///                     price is #1011 (Live owns the forward slice); the served
///                     three-way groups on `/game-markets` are not a headline
///                     contract (#5328, and Design's 11449 boundary: no
///                     `GameMarketOther`/matchup shortcut, no
///                     `FinalGameWinnerQuote`), so they are not read here.
///   - score           `EventDetail.homeScore/awayScore`, dated only by the
///                     producer's own `scoreObservedAt`; after the start only.
///   - match clock     `PeriodLabel.liveStatusText` during play, else the slot's
///                     absence words. A started suspended match wears the app's
///                     one suspended treatment (`EventState.isSuspendedAndStarted`
///                     + `EventState.suspendedLabel`).
///   - projection      before the start, `EventDetailView.projectionText` (the
///                     hero's own string) only where the projected-final format
///                     table admits the sport (`LiveProjectedFinalAdmission2920
///                     .format(forSport:)`, as H1 asks both); during play,
///                     `LiveProjectedFinal2920.page` — admitted prints, refused
///                     or absent says so (no ladder fallback, as H1); after the
///                     final, `FinalForecastComparison11296.qualified`. The
///                     actual-versus-projection sentence has no owner, so the
///                     contract's `comparison` stays nil.
///   - result words    `EventOutcome.resolve` with the served verdict.
///   - names, tints    `TeamShortName.shortPair`, `TeamTextContrast.cardColors`.
///
/// The host passes what it already decided and this file never reads: the event
/// the hero prints (`vm.headline(event)`), that pair's displayed clock, whether
/// delivery is interrupted, `/history`'s ladder pair, now, and the reader's
/// calendar. Nothing here subscribes, schedules, ranks or fetches.
enum SoccerMatchPageAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        /// `vm.displayedProbabilityObservedAt(event)`. Nil is undated, which reads
        /// as "last recorded", never "current".
        let probabilityObservedAt: Date?
        /// `vm.liveUpdateStatus == .interrupted`.
        let deliveryInterrupted: Bool
        /// `vm.history?.pmSpreadData?.projectedFinal`, read only by the pre-match
        /// projected final the hero prints.
        let ladderHome: Double?
        let ladderAway: Double?
        let now: Date
        /// The reader's own calendar, time zone and locale; clock words are said in it.
        let calendar: Calendar
        let locale: Locale

        init(probabilityObservedAt: Date?, deliveryInterrupted: Bool = false,
             ladderHome: Double? = nil, ladderAway: Double? = nil, now: Date = Date(),
             calendar: Calendar = .current, locale: Locale = .current) {
            self.probabilityObservedAt = probabilityObservedAt
            self.deliveryInterrupted = deliveryInterrupted
            self.ladderHome = ladderHome
            self.ladderAway = ladderAway
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }
    }

    /// The fixed reader words. Plain chance and availability language only.
    enum Words {
        static let beforeKickoff = "Before kickoff"
        static let kickoff = "Kickoff"
        static let kickoffToBeAnnounced = "Kickoff time to be announced"
        static let inPlay = "In play"
        static let final = "Final"
        static let draw = "Draw"
        static let won = "won"
        static let preMatchChance = "Pre-match chance"
        static let openingChance = "Opening chance"
        static let winChanceUnavailable = "Win chance unavailable"
        static let preMatchNotRecorded = "Pre-match chance not recorded"
        static let drawChanceUnavailable = "Draw chance unavailable"
        static let awayChanceUnavailable = "Away win chance unavailable"
        static let recorded = "Recorded"
        static let scoreObserved = "Score observed"
        static let finalScore = "Final score"
        static let scoreUnavailable = "Score unavailable"
        static let clockUnavailable = "Match clock unavailable"
        static let projectedFinal = "Projected final"
        static let projectionUnavailable = "Projected final unavailable"
        static let projectionWithheld = "Projected final unavailable for this match state"
        static let aboutLabel = "About this match"

        static func outcome(_ team: String) -> String { "\(team) win" }
    }

    // MARK: - Phase

    /// The screen's one phase. A finished status is final; a live status, or a
    /// suspension after the start, is during play; everything else is before.
    /// Never read from a score, a clock or a price.
    static func phase(_ event: EventDetail, now: Date) -> SoccerEventPagePhase10868 {
        if EventState.isFinished(event.status) { return .final }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: now) {
            return .live
        }
        return .before
    }

    /// The pair `TeamShortName` decides for this matchup, shared by every part.
    static func names(_ event: EventDetail) -> (away: String, home: String) {
        TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
    }

    // MARK: - Header

    static func header(_ event: EventDetail, host: Host) -> SoccerEventPageHeader10868 {
        let pagePhase = phase(event, now: host.now)
        let shown = names(event)
        return SoccerEventPageHeader10868(
            state: stateWords(event, phase: pagePhase, names: shown, host: host),
            date: dateWords(event, phase: pagePhase, host: host),
            home: shown.home,
            away: shown.away,
            score: pagePhase == .before ? nil : score(event, phase: pagePhase, names: shown, host: host),
            clock: pagePhase == .live ? clock(event) : nil,
            projection: projection(event, phase: pagePhase, names: shown, host: host),
            aboutLabel: Words.aboutLabel)
    }

    static func stateWords(_ event: EventDetail, phase: SoccerEventPagePhase10868,
                           names: (away: String, home: String), host: Host) -> String {
        switch phase {
        case .before:
            return Words.beforeKickoff
        case .live:
            // A started suspended match wears the app's one suspended treatment
            // (`StatusBadge`'s words, #4021/#9208), never a stoppage named here.
            if EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: host.now) {
                return EventState.suspendedLabel(authorityPeriod: event.espn?.period)
            }
            return Words.inPlay
        case .final:
            let outcome = EventOutcome.resolve(status: event.status, homeScore: event.homeScore,
                                               awayScore: event.awayScore, servedResult: event.heroSettledResult)
            switch outcome {
            case .home: return "\(Words.final) · \(names.home) \(Words.won)"
            case .away: return "\(Words.final) · \(names.away) \(Words.won)"
            case .draw: return "\(Words.final) · \(outcome.drawLabel ?? Words.draw)"
            case .undecided: return Words.final
            }
        }
    }

    /// "Mon, Oct 12 · Kickoff 5:00 AM" before the start; the day alone after it.
    static func dateWords(_ event: EventDetail, phase: SoccerEventPagePhase10868, host: Host) -> String? {
        guard let start = event.commenceTime?.asDate else { return nil }
        let day = dayWords(start, host: host)
        guard phase == .before else { return day }
        if event.startIsTbd == true { return "\(day) · \(Words.kickoffToBeAnnounced)" }
        return "\(day) · \(Words.kickoff) \(timeWords(start, host: host))"
    }

    /// The producer's score, dated only by its own observation clock.
    static func score(_ event: EventDetail, phase: SoccerEventPagePhase10868,
                      names: (away: String, home: String), host: Host) -> SoccerEventPageScore10868 {
        guard let pair = scorePair(event) else { return .unavailable(Words.scoreUnavailable) }
        let spoken = "\(names.home) \(pair.home), \(names.away) \(pair.away)"
        if phase == .final {
            return .actual(home: "\(pair.home)", away: "\(pair.away)", context: Words.finalScore,
                           spoken: "\(Words.final): \(spoken)")
        }
        let context = event.scoreObservedAt?.asDate.map { "\(Words.scoreObserved) \(clockWords($0, host: host))" }
        return .actual(home: "\(pair.home)", away: "\(pair.away)", context: context, spoken: spoken)
    }

    /// The period and clock as the app's one rule says them, or their absence.
    /// ESPN's period and clock carry no observation time of their own, so none
    /// is printed with them; the score keeps its own clock.
    static func clock(_ event: EventDetail) -> SoccerSlotText11449 {
        guard let text = PeriodLabel.liveStatusText(period: event.espn?.period, gameClock: event.espn?.gameClock) else {
            return .unavailable(Words.clockUnavailable)
        }
        return .value(text)
    }

    static func projection(_ event: EventDetail, phase: SoccerEventPagePhase10868,
                           names: (away: String, home: String), host: Host) -> SoccerEventPageProjection10868 {
        switch phase {
        case .before:
            // The hero's own string, only where the format table admits the sport.
            guard let format = LiveProjectedFinalAdmission2920.format(forSport: event.sport),
                  let text = EventDetailView.projectionText(
                    event, ladderHome: host.ladderHome, ladderAway: host.ladderAway, hasScore: false, now: host.now)
            else { return unavailableProjection(Words.projectionUnavailable) }
            return SoccerEventPageProjection10868(title: format.label, reading: .value(text), comparison: nil)
        case .live:
            switch LiveProjectedFinal2920.page(event, now: host.now) {
            case .admitted(let printed):
                let reading = LiveProjectedFinal2920.pairText(printed, awayName: names.away, homeName: names.home)
                return SoccerEventPageProjection10868(title: printed.label, reading: .value(reading), comparison: nil)
            case .withheld:
                return unavailableProjection(Words.projectionWithheld)
            case .notLive, .absent:
                return unavailableProjection(Words.projectionUnavailable)
            }
        case .final:
            guard let qualified = FinalForecastComparison11296.qualified(
                sport: event.sport, status: event.status, homeScore: event.homeScore, awayScore: event.awayScore,
                actualPeriod: FinalForecastComparison11296.actualPeriod(
                    sport: event.sport, servedFinalScorePeriod: event.finalScorePeriod),
                projection: event.pregameProjection)
            else { return unavailableProjection(Words.projectionUnavailable) }
            let c = qualified.comparison
            return SoccerEventPageProjection10868(
                title: c.label,
                reading: .value(FinalForecastComparison11296.pairText(c, awayName: names.away, homeName: names.home)),
                comparison: nil)
        }
    }

    private static func unavailableProjection(_ words: String) -> SoccerEventPageProjection10868 {
        SoccerEventPageProjection10868(title: Words.projectedFinal, reading: .unavailable(words), comparison: nil)
    }

    // MARK: - Headline

    /// Home win, Draw and away win, in that fixed order. Before the start and
    /// during play the primary reading is the hero's current (or last recorded)
    /// home chance; during play the pre-match reading sits beside it. After the
    /// final the pre-match reading is the primary one — the result is in the
    /// state words, never a chance.
    static func headline(_ event: EventDetail, host: Host) -> SoccerThreeOutcomeHeadlineInput11449 {
        let pagePhase = phase(event, now: host.now)
        let shown = names(event)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let pregame = preMatch(event)
        let primary: (heading: SoccerReadingHeading11449, home: String?)
        let comparison: (heading: SoccerReadingHeading11449, home: String?)?
        switch pagePhase {
        case .before:
            primary = current(event, host: host)
            comparison = nil
        case .live:
            primary = current(event, host: host)
            comparison = pregame
        case .final:
            primary = pregame
            comparison = nil
        }
        let primaryMissing = pagePhase == .final ? Words.preMatchNotRecorded : Words.winChanceUnavailable
        let home = SoccerOutcomeSlot11449(
            label: Words.outcome(shown.home), color: tints.home,
            primary: primary.home, comparison: comparison?.home,
            primaryUnavailable: primaryMissing, comparisonUnavailable: Words.preMatchNotRecorded)
        let draw = SoccerOutcomeSlot11449(
            label: Words.draw, color: DS.textSecondary, primary: nil, comparison: nil,
            primaryUnavailable: Words.drawChanceUnavailable, comparisonUnavailable: Words.drawChanceUnavailable)
        let away = SoccerOutcomeSlot11449(
            label: Words.outcome(shown.away), color: tints.away, primary: nil, comparison: nil,
            primaryUnavailable: Words.awayChanceUnavailable, comparisonUnavailable: Words.awayChanceUnavailable)
        return SoccerThreeOutcomeHeadlineInput11449(
            home: home, draw: draw, away: away,
            primaryHeading: primary.heading, comparisonHeading: comparison?.heading)
    }

    /// The hero's pair, through the hero's own calls, home side only. The
    /// heading is "Opening line" on an opening hero, else the phase label.
    static func current(_ event: EventDetail, host: Host) -> (heading: SoccerReadingHeading11449, home: String?) {
        let fallback = SoccerReadingHeading11449(title: EventHeadlinePhase9483.lastRecorded.label, context: nil)
        guard let odds = event.currentOdds else { return (fallback, nil) }
        let shown = OpeningLineHero.resolve(odds, for: event)
        let reading = EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: event.commenceTime?.asDate, isOpeningLine: shown.isOpeningLine,
            observedAt: host.probabilityObservedAt, deliveryInterrupted: host.deliveryInterrupted, now: host.now)
        let title = shown.isOpeningLine ? OpeningLineHero.caption : (reading ?? .lastRecorded).label
        let clock = host.probabilityObservedAt.map { "\(Words.recorded) \(clockWords($0, host: host))" }
        let heading = SoccerReadingHeading11449(
            title: title, context: joined([clock, sourceName(event.heroProbabilitySource, in: event)]))
        guard let pair = DrawPricedWinner.printablePair(
            away: shown.awayProbability, home: shown.homeProbability, sport: event.sport),
            pair.home.isFinite, (0...1).contains(pair.home)
        else { return (heading, nil) }
        // A draw-priced sport's lone side is rounded alone, as the hero rounds it.
        return (heading, formatProbability(pair.home))
    }

    /// The last reading before the start, through `PrematchReading`, home only.
    static func preMatch(_ event: EventDetail) -> (heading: SoccerReadingHeading11449, home: String?) {
        guard let reading = PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds) else {
            return (SoccerReadingHeading11449(title: Words.preMatchChance, context: nil), nil)
        }
        let title = reading.isServed ? Words.preMatchChance : Words.openingChance
        let venue = reading.isServed ? SourceLabels.label(for: reading.source) : nil
        let heading = SoccerReadingHeading11449(title: title, context: venue)
        guard let pair = DrawPricedWinner.printablePair(
            away: reading.awayProbability, home: reading.homeProbability, sport: event.sport)
        else { return (heading, nil) }
        return (heading, formatProbability(pair.home))
    }

    // MARK: - Words

    /// The served display name for a probability source, or nil. An unnamed
    /// source is left unnamed rather than guessed.
    static func sourceName(_ source: String?, in event: EventDetail) -> String? {
        guard let source, let served = event.winProbabilitySources?[source]?.displayName,
              !served.isEmpty, served != source else { return nil }
        return served
    }

    /// "Oct 12, 5:54 AM" in the reader's zone — the event page's own date style.
    static func clockWords(_ date: Date, host: Host) -> String {
        date.formatted(style(host).month(.abbreviated).day().hour().minute())
    }

    static func timeWords(_ date: Date, host: Host) -> String {
        date.formatted(style(host).hour().minute())
    }

    static func dayWords(_ date: Date, host: Host) -> String {
        date.formatted(style(host).weekday(.abbreviated).month(.abbreviated).day())
    }

    private static func style(_ host: Host) -> Date.FormatStyle {
        Date.FormatStyle(locale: host.locale, calendar: host.calendar, timeZone: host.calendar.timeZone)
    }

    /// Both scores, or nil when either is missing or negative.
    static func scorePair(_ event: EventDetail) -> (home: Int, away: Int)? {
        guard let home = event.homeScore, let away = event.awayScore, home >= 0, away >= 0 else { return nil }
        return (home, away)
    }

    static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
