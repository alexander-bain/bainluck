import SwiftUI

/// #10868 — THE HOCKEY JOURNEY SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE,
/// HEADER AND THE PAIRED COMPARISON MATRIX.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `nhl-journey` the before, during and
/// final matrix prints exactly the chances, goals and forecasts the rest of the
/// event page already decides, in the screen's own paired grammar.
///
/// It decides nothing the app does not already decide. Each slot is the output
/// of the authority that owns it, or that slot's own absence words:
///
///   - phase           `EventState` — finished, live, suspended after the start.
///   - current pair    `OpeningLineHero.resolve` + `EventDetailView.heroPairPercents`
///                     + `formatProbability`, the hero's own three calls, so the
///                     matrix and hero can never round one price differently.
///                     "Current" versus "last recorded" is
///                     `EventHeadlinePhase9483.resolve` on the clock the host
///                     displays (`vm.displayedProbabilityObservedAt`).
///   - pregame pair    `PrematchReading.resolve` with its served percents. It
///                     carries no clock of its own, so none is printed.
///   - goals           `EventDetail.homeScore/awayScore`, dated only by the
///                     producer's `scoreObservedAt` and named by `scoreSource`.
///   - state words     `PeriodLabel.liveStatusText` during play.
///   - forecasts       before the start, `EventDetailView.projectionText`'s gates
///                     AND the projected-final format table
///                     (`LiveProjectedFinalAdmission2920.format(forSport:)`, native's
///                     port of web's `projectedFinalFormat`) — web's
///                     `eventPageProjectedPair` withholds a pregame pair the table
///                     refuses, and native's hero gate alone does not ask, so this
///                     file asks both and the two platforms print one answer;
///                     during play, `LiveProjectedFinal2920.page` and
///                     `LivePregameComparison11296`; after the final,
///                     `FinalForecastComparison11296`. A refusal prints the slot's
///                     absence words, never a reference value. Today the format
///                     table, #11296's unit table and #2920 all decline hockey, so
///                     every hockey forecast slot is absent until those owners admit
///                     hockey; this file must not route around them.
///   - result          `EventOutcome.resolve` with the served verdict.
///   - names and tints `TeamShortName.shortPair`, `TeamTextContrast.cardColors`.
///   - source names    the served `win_probability_sources[...].displayName` only;
///                     an unnamed source is left unnamed rather than guessed.
///
/// The host passes what it already decided and this file never reads: the event
/// the hero prints (`vm.headline(event)`), that pair's displayed clock, whether
/// delivery is interrupted, `/history`'s ladder pair, now, and the reader's
/// calendar. Nothing here subscribes, schedules, ranks or fetches.
enum HockeyJourneyPageAdapter10868 {

    /// What the host already holds, passed in unchanged.
    struct Host {
        /// `vm.displayedProbabilityObservedAt(event)`. Nil is undated, which reads
        /// as "last recorded", never "current".
        let probabilityObservedAt: Date?
        /// `vm.liveUpdateStatus == .interrupted`.
        let deliveryInterrupted: Bool
        /// `vm.history?.pmSpreadData?.projectedFinal`, the ladders' pregame pair.
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

    /// The fixed words the matrix prints around the values.
    enum Words {
        static let winChance = "Win chance"
        static let currentChance = "Current chance"
        static let lastRecordedChance = "Last recorded chance"
        static let pregameChance = "Pregame chance"
        static let projectedGoals = "Projected goals"
        static let goals = "Goals"
        static let finalGoals = "Final goals"
        static let projectedFinal = "Projected final"
        static let pregameForecast = "Pregame forecast"
        static let noChance = "No recorded chance"
        static let noScore = "Score unavailable"
        static let noPregameForecast = "No pregame forecast"
        static let noInGameForecast = "No in-game forecast"
        static let forecastWithheld = "Forecast withheld"
        static let won = "Won"
        static let lost = "Lost"
        static let spokenLabel = "Hockey win chances, score and forecast"
        static let aboutLabel = "About these sources"
        /// The period and clock come from ESPN's game state, which serves no time of its own.
        static let stateSource = "Game state from ESPN"
    }

    // MARK: - Phase

    /// The screen's one phase. A finished status is final; a live status, or a
    /// suspension after the start, is during play; everything else is before.
    /// Never read from a score, a clock or a price.
    static func phase(_ event: EventDetail, now: Date) -> HockeyJourneyPagePhase10868 {
        if EventState.isFinished(event.status) { return .final }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: now) {
            return .live
        }
        return .before
    }

    // MARK: - Header

    static func header(_ event: EventDetail, phase: HockeyJourneyPagePhase10868) -> HockeyJourneyPageHeader10868 {
        let title: String
        switch phase {
        case .before:
            title = "\(event.homeTeam) vs \(event.awayTeam)"
        case .live:
            title = score(event).map { "\(event.homeTeam) \($0.home)–\($0.away) \(event.awayTeam)" }
                ?? "\(event.homeTeam) vs \(event.awayTeam)"
        case .final:
            title = score(event).map { "Final: \(event.homeTeam) \($0.home)–\($0.away) \(event.awayTeam)" }
                ?? "Final: \(event.homeTeam) vs \(event.awayTeam)"
        }
        return HockeyJourneyPageHeader10868(eyebrow: nil, title: title, aboutLabel: Words.aboutLabel)
    }

    // MARK: - Headline

    static func headline(_ event: EventDetail, host: Host) -> HockeyJourneyHeadlineInput10868 {
        let pagePhase = Self.phase(event, now: host.now)
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let home = HockeyJourneyTeam10868(name: event.homeTeam, short: names.home == event.homeTeam ? nil : names.home,
                                          tint: tints.home)
        let away = HockeyJourneyTeam10868(name: event.awayTeam, short: names.away == event.awayTeam ? nil : names.away,
                                          tint: tints.away)
        let state = stateWords(event, phase: pagePhase, host: host)
        return HockeyJourneyHeadlineInput10868(
            state: state.state, stateContext: state.context, home: home, away: away,
            matrix: matrix(event, phase: pagePhase, host: host),
            historicalForecast: pagePhase == .live ? historicalForecast(event, names: names, host: host) : nil,
            spokenLabel: Words.spokenLabel)
    }

    static func matrix(_ event: EventDetail, phase: HockeyJourneyPagePhase10868, host: Host) -> HockeyJourneyMatrix10868 {
        switch phase {
        case .before:
            let chance = currentPair(event, host: host)
            let forecast = pregamePair(event, host: host)
            return .before(HockeyJourneyBeforeMatrix10868(
                chance: HockeyJourneyColumn10868(title: chance?.title ?? Words.winChance, provenance: chance?.provenance),
                projectedGoals: HockeyJourneyColumn10868(title: Words.projectedGoals, provenance: forecast?.provenance),
                home: HockeyJourneyBeforeRow10868(chance: chance?.home ?? .absent(Words.noChance),
                                                  projectedGoals: forecast?.home ?? .absent(Words.noPregameForecast)),
                away: HockeyJourneyBeforeRow10868(chance: chance?.away ?? .absent(Words.noChance),
                                                  projectedGoals: forecast?.away ?? .absent(Words.noPregameForecast))))
        case .live:
            let pregame = pregameChance(event)
            let current = currentPair(event, host: host)
            let goals = goalSlots(event, host: host, final: false)
            let projected = liveProjection(event, host: host)
            return .during(HockeyJourneyDuringMatrix10868(
                pregameChance: HockeyJourneyColumn10868(title: Words.pregameChance, provenance: pregame?.provenance),
                currentChance: HockeyJourneyColumn10868(title: current?.title ?? Words.lastRecordedChance,
                                                        provenance: current?.provenance),
                goals: HockeyJourneyColumn10868(title: Words.goals, provenance: goals.provenance),
                projectedFinal: HockeyJourneyColumn10868(title: Words.projectedFinal, provenance: projected.provenance),
                home: HockeyJourneyDuringRow10868(pregameChance: pregame?.home ?? .absent(Words.noChance),
                                                  currentChance: current?.home ?? .absent(Words.noChance),
                                                  goals: goals.home, projectedFinal: projected.home),
                away: HockeyJourneyDuringRow10868(pregameChance: pregame?.away ?? .absent(Words.noChance),
                                                  currentChance: current?.away ?? .absent(Words.noChance),
                                                  goals: goals.away, projectedFinal: projected.away)))
        case .final:
            let pregame = pregameChance(event)
            let goals = goalSlots(event, host: host, final: true)
            let forecast = finalForecast(event)
            let outcome = EventOutcome.resolve(status: event.status, homeScore: event.homeScore,
                                               awayScore: event.awayScore, servedResult: event.heroSettledResult)
            let results: (home: String?, away: String?) = switch outcome {
            case .home: (Words.won, Words.lost)
            case .away: (Words.lost, Words.won)
            case .draw, .undecided: (nil, nil)
            }
            return .final(HockeyJourneyFinalMatrix10868(
                pregameChance: HockeyJourneyColumn10868(title: Words.pregameChance, provenance: pregame?.provenance),
                finalGoals: HockeyJourneyColumn10868(title: Words.finalGoals, provenance: goals.provenance),
                pregameForecast: HockeyJourneyColumn10868(title: Words.pregameForecast, provenance: forecast?.provenance),
                home: HockeyJourneyFinalRow10868(pregameChance: pregame?.home ?? .absent(Words.noChance),
                                                 finalGoals: goals.home,
                                                 pregameForecast: forecast?.home ?? .absent(Words.noPregameForecast),
                                                 result: results.home, difference: nil),
                away: HockeyJourneyFinalRow10868(pregameChance: pregame?.away ?? .absent(Words.noChance),
                                                 finalGoals: goals.away,
                                                 pregameForecast: forecast?.away ?? .absent(Words.noPregameForecast),
                                                 result: results.away, difference: nil)))
        }
    }

    // MARK: - Slots

    /// One column's two values and its provenance line.
    struct PairSlots: Equatable {
        let title: String
        let home: HockeyJourneySlot10868
        let away: HockeyJourneySlot10868
        let provenance: String?
    }

    /// The pair the hero prints, through the hero's own calls. Nil when the
    /// event serves no current odds or the hero would print no pair.
    static func currentPair(_ event: EventDetail, host: Host) -> PairSlots? {
        guard let odds = event.currentOdds else { return nil }
        let shown = OpeningLineHero.resolve(odds, for: event)
        guard let home = shown.homeProbability, let away = shown.awayProbability,
              home.isFinite, away.isFinite else { return nil }
        let percents = EventDetailView.heroPairPercents(shown, away: away, home: home)
        let reading = EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: event.commenceTime?.asDate, isOpeningLine: shown.isOpeningLine,
            observedAt: host.probabilityObservedAt, deliveryInterrupted: host.deliveryInterrupted, now: host.now)
        let title: String
        if shown.isOpeningLine {
            title = OpeningLineHero.caption
        } else {
            title = reading == .current ? Words.currentChance : Words.lastRecordedChance
        }
        let clock = host.probabilityObservedAt.map { "Recorded \(clockWords($0, host: host))" }
        let source = sourceName(event.heroProbabilitySource, in: event)
        return PairSlots(
            title: title,
            home: probability(home, rendered: percents.home),
            away: probability(away, rendered: percents.away),
            provenance: joined([clock, source]))
    }

    /// The last reading before the start, through `PrematchReading`.
    static func pregameChance(_ event: EventDetail) -> PairSlots? {
        guard let reading = PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds) else {
            return nil
        }
        let percents = reading.percents
        let source = reading.isServed ? sourceName(reading.source, in: event) : nil
        return PairSlots(
            title: Words.pregameChance,
            home: probability(reading.homeProbability, rendered: percents.count == 2 ? percents[1] : nil),
            away: probability(reading.awayProbability, rendered: percents.count == 2 ? percents[0] : nil),
            provenance: joined([reading.captionWord, source]))
    }

    /// Before the start: the pair `EventDetailView.projectionText` admits — and
    /// only where the projected-final format table admits the sport too, as
    /// web's `eventPageProjectedPair` requires (hockey's puck line is refused
    /// there; whether hockey's pregame pair should print is Design's open
    /// HOCKEY-PREGAME-FORECAST-PRECISION decision, and this one guard is the
    /// whole switch).
    static func pregamePair(_ event: EventDetail, host: Host) -> PairSlots? {
        guard LiveProjectedFinalAdmission2920.format(forSport: event.sport) != nil else { return nil }
        return admittedPregamePair(event, host: host)
    }

    /// The raw pair `EventDetailView.projectionText`'s own source selection
    /// admits — the sportsbooks' pregame pair where the sport's spread is a
    /// margin, else the ladders' — said per side at its own precision through
    /// `NBALadderCard9483.number` (a whole number stays whole, a projection keeps
    /// one decimal): 3.5 / 2.5 prints "3.5" / "2.5", never a rounded "4" / "3".
    /// Admission stays that function's alone; nothing here re-qualifies a pair.
    static func admittedPregamePair(_ event: EventDetail, host: Host) -> PairSlots? {
        guard EventDetailView.projectionText(
            event, ladderHome: host.ladderHome, ladderAway: host.ladderAway, hasScore: false, now: host.now) != nil
        else { return nil }
        let vocab = SportVocab.forSport(event.sport)
        let sportsbooks: (home: Double, away: Double)?
        if vocab.sportsbookSpreadIsAMargin,
           let home = event.currentOdds?.projectedHomeScore, let away = event.currentOdds?.projectedAwayScore,
           home >= 0, away >= 0 {
            sportsbooks = (home, away)
        } else {
            sportsbooks = nil
        }
        guard let pair = sportsbooks ?? zip2(host.ladderHome, host.ladderAway) else { return nil }
        let books = event.currentOdds?.bookmakerCount
        let provenance: String
        if sportsbooks != nil {
            provenance = books.map { "Sportsbooks before the start · \($0) \($0 == 1 ? "book" : "books")" }
                ?? "Sportsbooks before the start"
        } else {
            provenance = "Prediction-market lines before the start"
        }
        return PairSlots(title: Words.projectedGoals,
                         home: forecastSlot(pair.home), away: forecastSlot(pair.away), provenance: provenance)
    }

    /// The live score, dated by the producer's own observation clock.
    static func goalSlots(_ event: EventDetail, host: Host, final: Bool)
        -> (home: HockeyJourneySlot10868, away: HockeyJourneySlot10868, provenance: String?) {
        guard let pair = score(event) else {
            return (.absent(Words.noScore), .absent(Words.noScore), nil)
        }
        let observed = event.scoreObservedAt?.asDate.map { "score observed \(clockWords($0, host: host))" }
        let source = event.scoreSource.map(sourceWord)
        return (goalsSlot(pair.home), goalsSlot(pair.away), joined([source, observed]))
    }

    /// During play: the admitted in-play pair, or the slot's absence words.
    static func liveProjection(_ event: EventDetail, host: Host)
        -> (home: HockeyJourneySlot10868, away: HockeyJourneySlot10868, provenance: String?) {
        switch LiveProjectedFinal2920.page(event, now: host.now) {
        case .admitted(let printed):
            return (goalsSlot(printed.home), goalsSlot(printed.away), printed.label)
        case .withheld:
            return (.absent(Words.forecastWithheld), .absent(Words.forecastWithheld), nil)
        case .notLive, .absent:
            return (.absent(Words.noInGameForecast), .absent(Words.noInGameForecast), nil)
        }
    }

    /// During play: the retained pregame forecast beneath an admitted current
    /// one, only where `LivePregameComparison11296` admits it.
    static func historicalForecast(_ event: EventDetail, names: (away: String, home: String),
                                   host: Host) -> HockeyJourneyHistoricalForecast10868? {
        guard case .admitted(let current) = LiveProjectedFinal2920.page(event, now: host.now),
              let comparison = LivePregameComparison11296.resolve(
                status: event.status, sport: event.sport, commenceTime: event.commenceTime,
                current: current, projection: event.pregameProjection)
        else { return nil }
        return HockeyJourneyHistoricalForecast10868(
            title: Words.pregameForecast,
            reading: LivePregameComparison11296.pairText(comparison, awayName: names.away, homeName: names.home),
            provenance: nil)
    }

    /// After the final: the comparison `FinalForecastComparison11296` admits.
    static func finalForecast(_ event: EventDetail) -> PairSlots? {
        guard let qualified = FinalForecastComparison11296.qualified(
            sport: event.sport, status: event.status, homeScore: event.homeScore, awayScore: event.awayScore,
            actualPeriod: FinalForecastComparison11296.actualPeriod(sport: event.sport,
                                                                   servedFinalScorePeriod: event.finalScorePeriod),
            projection: event.pregameProjection)
        else { return nil }
        // The served halves the comparison was qualified from, at their own
        // precision — the cards round them, this matrix keeps a 2.5 a 2.5.
        let c = qualified.comparison
        return PairSlots(title: Words.pregameForecast, home: forecastSlot(qualified.home), away: forecastSlot(qualified.away),
                         provenance: "\(c.label) · \(c.bookmakerCount) \(c.bookmakerCount == 1 ? "book" : "books")")
    }

    // MARK: - State words

    static func stateWords(_ event: EventDetail, phase: HockeyJourneyPagePhase10868, host: Host)
        -> (state: String, context: String?) {
        let start = event.commenceTime?.asDate
        switch phase {
        case .before:
            guard let start else { return ("Before game", nil) }
            if event.startIsTbd == true { return ("Before game · start time to be announced", dayWords(start, host: host)) }
            return ("Before game · \(timeWords(start, host: host)) start", dayWords(start, host: host))
        case .live:
            // A started suspended game wears the app's one suspended treatment
            // (`StatusBadge`'s order and words, #4021/#9208), never a stoppage
            // this file names for itself.
            let state = EventState.isSuspendedAndStarted(event.status, commenceTime: start, now: host.now)
                ? EventState.suspendedLabel(authorityPeriod: event.espn?.period)
                : PeriodLabel.liveStatusText(period: event.espn?.period, gameClock: event.espn?.gameClock) ?? "Live"
            // ESPN's period and clock carry no observation time of their own, and a
            // held newer score (`LiveEventScoreReconciliation`) replaces only the
            // score tuple and its clock — so the state is never dated by the score's
            // clock. The score keeps its own clock in the goals column.
            let hasState = event.espn?.period != nil || event.espn?.gameClock != nil
            return (state, hasState ? Words.stateSource : nil)
        case .final:
            return ("Final", start.map { dayWords($0, host: host) })
        }
    }

    // MARK: - Words

    static func probability(_ value: Double, rendered: Int?) -> HockeyJourneySlot10868 {
        let text = formatProbability(value, renderedPercent: rendered)
        return .value(text, spoken: spokenPercent(text))
    }

    static func goalsSlot(_ count: Int) -> HockeyJourneySlot10868 {
        .value("\(count)", spoken: count == 1 ? "1 goal" : "\(count) goals")
    }

    /// A forecast in goals at its own precision; the spoken words say the same figure.
    static func forecastSlot(_ goals: Double) -> HockeyJourneySlot10868 {
        let text = NBALadderCard9483.number(goals)
        return .value(text, spoken: text == "1" ? "1 goal" : "\(text) goals")
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

    /// The score producer's name as served ("espn" reads "ESPN").
    static func sourceWord(_ source: String) -> String {
        source.lowercased() == "espn" ? "ESPN" : source
    }

    /// "Oct 3, 6:45 PM" in the reader's zone — the event page's own date style.
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

    private static func score(_ event: EventDetail) -> (home: Int, away: Int)? {
        guard let home = event.homeScore, let away = event.awayScore, home >= 0, away >= 0 else { return nil }
        return (home, away)
    }

    private static func zip2(_ home: Double?, _ away: Double?) -> (home: Double, away: Double)? {
        guard let home, let away else { return nil }
        return (home, away)
    }

    private static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
