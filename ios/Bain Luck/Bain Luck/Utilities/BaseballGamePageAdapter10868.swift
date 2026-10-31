import SwiftUI

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE,
/// STATE WORDS AND THE PAIRED COMPARISON MATRIX.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on an MLB event page the before, during
/// and final matrix prints exactly the win chances and runs the rest of the
/// event page already decides — before first pitch each team's chance, during
/// play the pregame chance beside the current one and the runs so far, after
/// the final the pregame chance beside the final runs and the result — or
/// each slot's own words for why it has none.
///
/// It decides nothing the app does not already decide. Each slot is the output
/// of the authority that owns it, or that slot's own absence words:
///
///   - phase           `EventState` — finished is final; live, or suspended
///                     after the start, is during play; everything else is
///                     before. The hockey screen's rule
///                     (`HockeyJourneyPageAdapter10868.phase`), never read from a
///                     price, an inning or a result.
///   - two outcomes    baseball's winner market prices no draw
///                     (`SportVocab` "baseball": `winnerMarketPricesADraw:
///                     false`), so `DrawPricedWinner.printablePair` keeps both
///                     sides of every pair; `applies` asks it rather than
///                     assuming it.
///   - current pair    `OpeningLineHero.resolve` + `EventDetailView.heroPairPercents`
///                     + `formatProbability`, the hero's own three calls, so the
///                     matrix and the hero never round one price differently.
///                     "Current" versus "last recorded" is
///                     `EventHeadlinePhase9483.resolve` on the clock the host
///                     displays (`vm.displayedProbabilityObservedAt`); an
///                     opening-line hero is `OpeningLineHero.caption`. A pair
///                     the venue has already settled
///                     (`EventState.showsVenueSettledVerdict`) is a result, never
///                     a chance: the slot keeps its own words.
///   - pregame pair    `PrematchReading.resolve` with its served percents, named
///                     by its own caption word ("Pre-match", or "Opened" on the
///                     `opening_odds` fallback) and, when served, its venue
///                     through `SourceLabels.label`. It carries no clock of its
///                     own, so none is printed.
///   - runs            `EventDetail.homeScore/awayScore`, dated only by the
///                     producer's own `scoreObservedAt`; after the start only.
///   - state words     before: the listed start, or that it is to be announced;
///                     during: the app's one suspended treatment
///                     (`EventState.isSuspendedAndStarted` +
///                     `EventState.suspendedLabel(authorityPeriod:)`), else the
///                     inning through `PeriodLabel.liveStatusText` ("Middle 3rd");
///                     after: "Final". ESPN's inning carries no observation time
///                     of its own, so the score's clock never dates it.
///   - projection      before the start, `EventDetailView.projectionText` only
///                     where the projected-final format table admits the sport
///                     (`LiveProjectedFinalAdmission2920.format(forSport:)`);
///                     during play, `LiveProjectedFinal2920.page`; after the
///                     final, `FinalForecastComparison11296.qualified`. All three
///                     decline baseball today (the run line is pinned at ±1.5,
///                     `SportVocab.sportsbookSpreadIsAMargin: false`), so every
///                     phase prints the slot's absence words until those owners
///                     admit baseball; this file must not route around them.
///   - result          after the final only, `EventOutcome.resolve` with the
///                     served verdict (`hero_settled_result`). Never a chance.
///   - names, tints    the served names whole, `TeamShortName.shortPair` for the
///                     narrow grid only, `TeamTextContrast.cardColors`.
///   - source names    the served `win_probability_sources[...].displayName`
///                     only; an unnamed source is left unnamed.
///
/// Not served on any production field, so not printed: outs, the count and
/// base runners (`ESPNData` decodes `period` and `gameClock` only). The owner
/// of that dependency is the ESPN game-state producer and its event model.
///
/// The host passes what it already decided and this file never reads: the event
/// the hero prints (`vm.headline(event)`), that pair's displayed clock, whether
/// delivery is interrupted, now, and the reader's calendar. Nothing here
/// subscribes, schedules, ranks or fetches.
enum BaseballGamePageAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        /// `vm.displayedProbabilityObservedAt(event)`. Nil is undated, which reads
        /// as "last recorded", never "current".
        let probabilityObservedAt: Date?
        /// `vm.liveUpdateStatus == .interrupted`.
        let deliveryInterrupted: Bool
        let now: Date
        /// The reader's own calendar, time zone and locale; clock words are said in it.
        let calendar: Calendar
        let locale: Locale

        init(probabilityObservedAt: Date?, deliveryInterrupted: Bool = false, now: Date = Date(),
             calendar: Calendar = .current, locale: Locale = .current) {
            self.probabilityObservedAt = probabilityObservedAt
            self.deliveryInterrupted = deliveryInterrupted
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }
    }

    /// The fixed reader words. Plain chance and availability language only.
    enum Words {
        static let winChance = "Win chance"
        static let currentChance = "Current chance"
        static let lastRecordedChance = "Last recorded chance"
        static let pregameChance = "Pregame chance"
        static let runs = "Runs"
        static let finalRuns = "Final runs"
        static let winChanceUnavailable = "Win chance unavailable"
        static let pregameChanceUnavailable = "Pregame chance unavailable"
        static let scoreUnavailable = "Score unavailable"
        static let won = "Won"
        static let lost = "Lost"
        static let beforeFirstPitch = "Before first pitch"
        static let firstPitch = "First pitch"
        static let firstPitchToBeAnnounced = "First pitch time to be announced"
        static let live = "Live"
        static let inningUnavailable = "Inning unavailable"
        /// The inning comes from ESPN's game state, which serves no time of its own.
        static let stateSource = "Game state from ESPN"
        static let final = "Final"
        static let recorded = "Recorded"
        static let scoreObserved = "Score observed"
        static let finalScore = "Final score"
        static let projectedFinal = "Projected final"
        static let projectionUnavailable = "Projected final unavailable"
        static let projectionWithheld = "Projected final unavailable for this game state"
        static let spokenLabel = "Baseball win chances and runs"
    }

    // MARK: - Phase

    /// The screen's one phase. Never read from a score, an inning or a price.
    static func phase(_ event: EventDetail, now: Date) -> BaseballEventPagePhase10868 {
        if EventState.isFinished(event.status) { return .final }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: now) {
            return .live
        }
        return .before
    }

    /// The `mlb` route: the MLB sport key the app's own MLB pages read
    /// (`MLBFinalPage11284.sportKey`), on a winner market with no draw. Which
    /// games get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        event.sport == MLBFinalPage11284.sportKey && !DrawPricedWinner.sportPricesADraw(event.sport)
    }

    /// The pair `TeamShortName` decides for this matchup.
    static func names(_ event: EventDetail) -> (away: String, home: String) {
        TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
    }

    static func tints(_ event: EventDetail) -> (away: Color, home: Color) {
        TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                    homeHex: event.homeTeamData?.primaryColor)
    }

    // MARK: - Headline

    static func headline(_ event: EventDetail, host: Host) -> BaseballHeadlineInput10868 {
        let pagePhase = phase(event, now: host.now)
        let shown = names(event)
        let colors = tints(event)
        let home = BaseballTeam10868(name: event.homeTeam,
                                     short: shown.home == event.homeTeam ? nil : shown.home, tint: colors.home)
        let away = BaseballTeam10868(name: event.awayTeam,
                                     short: shown.away == event.awayTeam ? nil : shown.away, tint: colors.away)
        let state = stateWords(event, phase: pagePhase, host: host)
        return BaseballHeadlineInput10868(
            eyebrow: event.metadata?.league,
            state: state.state,
            stateContext: state.context,
            home: home,
            away: away,
            matrix: matrix(event, phase: pagePhase, host: host),
            projection: projection(event, phase: pagePhase, names: shown, host: host),
            spokenLabel: Words.spokenLabel)
    }

    static func matrix(_ event: EventDetail, phase: BaseballEventPagePhase10868, host: Host) -> BaseballMatrix10868 {
        switch phase {
        case .before:
            return .before(beforeMatrix(event, host: host))
        case .live:
            return .live(liveMatrix(event, host: host))
        case .final:
            return .final(finalMatrix(event, host: host))
        }
    }

    static func beforeMatrix(_ event: EventDetail, host: Host) -> BaseballBeforeMatrix10868 {
        let chance = currentPair(event, host: host)
        let missing = BaseballSlot10868.unavailable(Words.winChanceUnavailable)
        return BaseballBeforeMatrix10868(
            chance: BaseballColumn10868(title: chance?.title ?? Words.winChance, provenance: chance?.provenance),
            home: BaseballBeforeRow10868(chance: chance?.home ?? missing),
            away: BaseballBeforeRow10868(chance: chance?.away ?? missing))
    }

    static func liveMatrix(_ event: EventDetail, host: Host) -> BaseballLiveMatrix10868 {
        let pregame = pregameChance(event)
        let current = currentPair(event, host: host)
        let runs = runSlots(event, host: host, final: false)
        let noPregame = BaseballSlot10868.unavailable(Words.pregameChanceUnavailable)
        let noCurrent = BaseballSlot10868.unavailable(Words.winChanceUnavailable)
        return BaseballLiveMatrix10868(
            pregameChance: BaseballColumn10868(title: Words.pregameChance, provenance: pregame?.provenance),
            currentChance: BaseballColumn10868(title: current?.title ?? Words.currentChance,
                                               provenance: current?.provenance),
            runs: BaseballColumn10868(title: Words.runs, provenance: runs.provenance),
            home: BaseballLiveRow10868(pregameChance: pregame?.home ?? noPregame,
                                       currentChance: current?.home ?? noCurrent, runs: runs.home),
            away: BaseballLiveRow10868(pregameChance: pregame?.away ?? noPregame,
                                       currentChance: current?.away ?? noCurrent, runs: runs.away))
    }

    static func finalMatrix(_ event: EventDetail, host: Host) -> BaseballFinalMatrix10868 {
        let pregame = pregameChance(event)
        let runs = runSlots(event, host: host, final: true)
        let noPregame = BaseballSlot10868.unavailable(Words.pregameChanceUnavailable)
        let results = resultWords(event)
        return BaseballFinalMatrix10868(
            pregameChance: BaseballColumn10868(title: Words.pregameChance, provenance: pregame?.provenance),
            finalRuns: BaseballColumn10868(title: Words.finalRuns, provenance: runs.provenance),
            home: BaseballFinalRow10868(pregameChance: pregame?.home ?? noPregame, finalRuns: runs.home,
                                        result: results.home),
            away: BaseballFinalRow10868(pregameChance: pregame?.away ?? noPregame, finalRuns: runs.away,
                                        result: results.away))
    }

    // MARK: - Slots

    /// One column's two values and its provenance line.
    struct PairSlots: Equatable {
        let title: String
        let home: BaseballSlot10868
        let away: BaseballSlot10868
        let provenance: String?
    }

    /// The pair the hero prints, through the hero's own calls. Nil when the
    /// event serves no current odds, the venue has already settled the game,
    /// or the hero would print no pair.
    static func currentPair(_ event: EventDetail, host: Host) -> PairSlots? {
        guard let odds = event.currentOdds,
              !EventState.showsVenueSettledVerdict(event.status, venueSettled: event.venueSettled,
                                                    commenceTime: event.commenceTime?.asDate, now: host.now)
        else { return nil }
        let shown = OpeningLineHero.resolve(odds, for: event)
        guard let pair = DrawPricedWinner.printablePair(
                away: shown.awayProbability, home: shown.homeProbability, sport: event.sport),
              let away = pair.away, admissible(pair.home), admissible(away)
        else { return nil }
        let percents = EventDetailView.heroPairPercents(shown, away: away, home: pair.home)
        let reading = EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: event.commenceTime?.asDate, isOpeningLine: shown.isOpeningLine,
            observedAt: host.probabilityObservedAt, deliveryInterrupted: host.deliveryInterrupted, now: host.now)
        let title: String
        if shown.isOpeningLine {
            title = OpeningLineHero.caption
        } else {
            title = reading == .current ? Words.currentChance : Words.lastRecordedChance
        }
        let clock = host.probabilityObservedAt.map { "\(Words.recorded) \(clockWords($0, host: host))" }
        let source = sourceName(event.heroProbabilitySource, in: event)
        return PairSlots(
            title: title,
            home: probability(pair.home, rendered: percents.home),
            away: probability(away, rendered: percents.away),
            provenance: joined([clock, source]))
    }

    /// The last reading before the start, through `PrematchReading`.
    static func pregameChance(_ event: EventDetail) -> PairSlots? {
        guard let reading = PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds),
              let pair = DrawPricedWinner.printablePair(
                away: reading.awayProbability, home: reading.homeProbability, sport: event.sport),
              let away = pair.away
        else { return nil }
        let percents = reading.percents
        let venue = reading.isServed ? SourceLabels.label(for: reading.source) : nil
        return PairSlots(
            title: Words.pregameChance,
            home: probability(pair.home, rendered: percents.count == 2 ? percents[1] : nil),
            away: probability(away, rendered: percents.count == 2 ? percents[0] : nil),
            provenance: joined([reading.captionWord, venue]))
    }

    /// The score, dated by the producer's own observation clock during play;
    /// "Final score" after the final.
    static func runSlots(_ event: EventDetail, host: Host, final: Bool)
        -> (home: BaseballSlot10868, away: BaseballSlot10868, provenance: String?) {
        guard let pair = scorePair(event) else {
            let missing = BaseballSlot10868.unavailable(Words.scoreUnavailable)
            return (missing, missing, nil)
        }
        let provenance: String? = final
            ? Words.finalScore
            : event.scoreObservedAt?.asDate.map { "\(Words.scoreObserved) \(clockWords($0, host: host))" }
        let vocab = SportVocab.forSport(event.sport)
        return (runsSlot(pair.home, vocab: vocab), runsSlot(pair.away, vocab: vocab), provenance)
    }

    /// After the final: the served verdict's result words, never a chance and
    /// never read from a probability.
    static func resultWords(_ event: EventDetail) -> (home: String?, away: String?) {
        switch EventOutcome.resolve(status: event.status, homeScore: event.homeScore,
                                    awayScore: event.awayScore, servedResult: event.heroSettledResult) {
        case .home: (Words.won, Words.lost)
        case .away: (Words.lost, Words.won)
        case .draw, .undecided: (nil, nil)
        }
    }

    // MARK: - State words

    static func stateWords(_ event: EventDetail, phase: BaseballEventPagePhase10868, host: Host)
        -> (state: String, context: String?) {
        let start = event.commenceTime?.asDate
        switch phase {
        case .before:
            guard let start else { return (Words.beforeFirstPitch, nil) }
            let day = dayWords(start, host: host)
            if event.startIsTbd == true { return (Words.beforeFirstPitch, "\(day) · \(Words.firstPitchToBeAnnounced)") }
            return (Words.beforeFirstPitch, "\(day) · \(Words.firstPitch) \(timeWords(start, host: host))")
        case .live:
            let hasState = event.espn?.period != nil || event.espn?.gameClock != nil
            // A started suspended game wears the app's one suspended treatment
            // (`StatusBadge`'s words, #4021/#9208), never a stoppage named here.
            if EventState.isSuspendedAndStarted(event.status, commenceTime: start, now: host.now) {
                return (EventState.suspendedLabel(authorityPeriod: event.espn?.period),
                        hasState ? Words.stateSource : nil)
            }
            guard let inning = PeriodLabel.liveStatusText(period: event.espn?.period, gameClock: event.espn?.gameClock)
            else { return (Words.live, Words.inningUnavailable) }
            return (inning, Words.stateSource)
        case .final:
            return (Words.final, start.map { dayWords($0, host: host) })
        }
    }

    // MARK: - Projection

    static func projection(_ event: EventDetail, phase: BaseballEventPagePhase10868,
                           names: (away: String, home: String), host: Host) -> BaseballProjection10868 {
        switch phase {
        case .before:
            // The hero's own string, only where the format table admits the sport.
            guard let format = LiveProjectedFinalAdmission2920.format(forSport: event.sport),
                  let text = EventDetailView.projectionText(
                    event, ladderHome: nil, ladderAway: nil, hasScore: false, now: host.now)
            else { return unavailableProjection(Words.projectionUnavailable) }
            return BaseballProjection10868(title: format.label, reading: .value(text, spoken: text))
        case .live:
            switch LiveProjectedFinal2920.page(event, now: host.now) {
            case .admitted(let printed):
                let reading = LiveProjectedFinal2920.pairText(printed, awayName: names.away, homeName: names.home)
                let spoken = LiveProjectedFinal2920.spokenText(printed, awayName: names.away, homeName: names.home)
                return BaseballProjection10868(title: printed.label, reading: .value(reading, spoken: spoken))
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
            let text = FinalForecastComparison11296.pairText(c, awayName: names.away, homeName: names.home)
            return BaseballProjection10868(title: c.label, reading: .value(text, spoken: text))
        }
    }

    private static func unavailableProjection(_ words: String) -> BaseballProjection10868 {
        BaseballProjection10868(title: Words.projectedFinal, reading: .unavailable(words))
    }

    // MARK: - Words

    static func probability(_ value: Double, rendered: Int?) -> BaseballSlot10868 {
        let text = formatProbability(value, renderedPercent: rendered)
        return .value(text, spoken: spokenPercent(text))
    }

    /// A run count, said in the sport's own unit words (`SportVocab`).
    static func runsSlot(_ count: Int, vocab: SportVocab) -> BaseballSlot10868 {
        .value("\(count)", spoken: "\(count) \(count == 1 ? vocab.unitSingular : vocab.unit)")
    }

    /// `formatProbability`'s figure said in words; the figure itself is unchanged.
    static func spokenPercent(_ text: String) -> String {
        text.replacingOccurrences(of: "<", with: "under ")
            .replacingOccurrences(of: ">", with: "over ")
            .replacingOccurrences(of: "%", with: " percent")
    }

    /// The served display name for a probability source, or nil.
    static func sourceName(_ source: String?, in event: EventDetail) -> String? {
        guard let source, let served = event.winProbabilitySources?[source]?.displayName,
              !served.isEmpty, served != source else { return nil }
        return served
    }

    /// "Oct 1, 5:15 PM" in the reader's zone — the event page's own date style.
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

    private static func admissible(_ value: Double) -> Bool {
        value.isFinite && (0...1).contains(value)
    }

    static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
