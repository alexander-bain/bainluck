import SwiftUI

/// #10868 — THE TENNIS MATCH SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE, THE
/// TWO PLAYERS' HEADLINE, THE SET SCORE, THE READER HEADING AND THE ABOUT.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on a tennis event page the two players
/// lead at equal prominence with exactly the chances the event hero already
/// decides — before the match the hero's pair, during it the pre-match reading
/// beside an admitted current chance or its own words, after it the pre-match
/// reading beside the event's own reported result — with the set score in sets
/// beside them once play has started.
///
/// It decides nothing the app does not already decide. Each slot is the output
/// of the authority that owns it, or that slot's own absence words:
///
///   - applies         `TennisChartReading9483.applies` (the sport key starts
///                     with "tennis"), the gate every tennis surface uses.
///   - phase           `EventState` — finished is final; live, or suspended
///                     after the start, is during; everything else is before.
///                     The same rule as the hockey and combat screens, never read
///                     from a price, a set count or a result.
///   - two outcomes    tennis prices no draw: `DrawPricedWinner.printablePair`
///                     (SportVocab `winnerMarketPricesADraw: false`) keeps the
///                     away figure on every pair; nothing here complements one.
///   - before pair     `OpeningLineHero.resolve` + `EventDetailView.heroPairPercents`
///                     + `formatProbability`, the hero's own three calls; its label
///                     is `EventHeadlinePhase9483.resolve(...).label` on the clock the
///                     host displays ("Current win chance" / "Last recorded win
///                     chance"), or `OpeningLineHero.caption` on an opening-line hero.
///   - pre-match pair  `PrematchReading.resolve` with its served percents, labelled
///                     as the production final tennis headline labels it
///                     (`TennisFinalHeadline9483.servedLabel` / `.openingLabel`). It
///                     carries no clock of its own, so none is printed.
///   - current chance  during play only, the hero's pair, and only while
///                     `EventHeadlinePhase9483.resolve` calls it current — a
///                     suspended match, an opening line, a stale or undated quote
///                     or interrupted delivery is never a current chance: the slot
///                     keeps its own words and the reading stays in the history.
///   - final pair and  `TennisFinalHeadline9483.resolve` — the production final
///     result          tennis headline (`EventDetailView.tennisFinalHeadline`), fed
///                     exactly as the page feeds it: `EventOutcome.resolve` with the
///                     served verdict, the scoreboard when `EventDetailView.showsScore`
///                     draws it, `PrematchReading.resolve`. Its printed chance and
///                     Won/Lost are the figures; the raw value is the same reading
///                     through the same pair rule.
///   - set score       `homeScore` / `awayScore`, only where `EventDetailView.showsScore`
///                     draws them, named in `SportVocab.scoreboardUnit` ("sets"), home
///                     first as the names are; its provenance is `scoreObservedAt`
///                     and only the score's — it never dates the state words. GAMES
///                     within a set are NOT on any decoded field: the served
///                     `linescore` (`sets`, `home_games`, `away_games`) is not
///                     decoded by `EventDetail` and `box_score_data` carries only
///                     `players` for tennis, so no games figure is printed
///                     (dependency: Native model `EventDetail` decoding `linescore`).
///   - state words     before: the listed start (or "to be announced"); during:
///                     the venue's settled or no-winner verdict where `EventState`
///                     lets this slot show it, else the app's one suspended
///                     treatment (`EventState.isSuspendedAndStarted` +
///                     `EventState.suspendedLabel(authorityPeriod:)`), else
///                     `PeriodLabel.liveStatusText`, else "Live"; after: "Final"
///                     with the event's own winner.
///   - names, tints    the served names in full; `TeamShortName.shortPair` for the
///                     compact label only; `TeamTextContrast.cardColors`; home
///                     circle, away diamond — the history's keys.
///   - identities      the hero pair is an event-level reading, not a provider
///                     original, so each player carries an OPAQUE presentation
///                     identity (`tennis:<event>:winner`, `event-hero`,
///                     `<event>:winner`, `home`/`away`) — never a provider market or
///                     outcome id. The host maps it to the history it opens.
///
/// The host passes what it already decided and this file never reads: the event
/// the hero prints (`vm.headline(event)`), that pair's displayed clock, whether
/// delivery is interrupted, now, and the reader's calendar. Nothing here
/// subscribes, schedules, ranks or fetches.
enum TennisMatchPageAdapter10868 {

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

    enum Side: Equatable {
        case home
        case away
    }

    /// The fixed reader words.
    enum Words {
        static let currentChance = "Current win chance"
        static let currentUnavailable = "Current win chance unavailable"
        static let matchResult = "Match result"
        static let noChance = "Win chance unavailable"
        static let preMatchUnavailable = "Pre-match chance unavailable"
        static let resultUnavailable = "Result unavailable"
        static let won = "Won"
        static let lost = "Lost"
        static let recordedOnEvent = "Recorded on the event"
        static let lastBeforeStart = "Last reading before the start"
        static let openingLine = "Sportsbooks’ opening line"
        static let graphicLabel = "Players’ win chances"
        static let empty = "No players in this update"
        static let aboutLabel = "About this match"
        static let aboutHint = "Opens the timing of each chance, the result and the score"
        static let openHint = "Opens this player’s history"
        static let unavailableWords = "Player unavailable in this update"
        static let previewAbsence = "History in the chart"
        static let beforeMatch = "Before the match"
        static let scheduledStart = "Scheduled start"
        static let startToBeAnnounced = "Start time to be announced"
        static let live = "Live"
        static let final = "Final"
        static let setScoreUnavailable = "Set score unavailable"
        static let headlineUnavailable = "The players’ chances aren’t available for this match state."
        static let blendName = "Bain Luck"
        static let updateInterrupted = "Update interrupted · showing the last recorded chances"
        static let scoreRecorded = "Score recorded"

        // About.
        static let aboutTitle = "About this match"
        static let aboutChancesTitle = "Chances"
        static let aboutScoreTitle = "Score"
        static let aboutResultTitle = "Match result"
        static let aboutHistoryTitle = "History and sources"
        static let noHeroPair = "Win chance unavailable."
        static let noPrematchPair = "Pre-match chance unavailable."
        static let noCurrentAdmitted = "Current win chance unavailable. Recorded readings remain in the history."
        static let noScoreYet = "Set score unavailable."
        static let gamesUnavailable = "Games within each set unavailable."
        static let noResultYet = "Result unavailable."
        static let historyWords = "The chart draws recorded readings only. Times without a reading stay blank, and no line is drawn across them. A reading before the scheduled start does not show that play had begun."
    }

    /// The opaque presentation source of the hero pair's identities. A token,
    /// never a venue: nothing names it to the reader.
    static let heroSource = "event-hero"

    // MARK: - Applies and phase

    /// Tennis only, by the gate every tennis surface already uses.
    static func applies(_ event: EventDetail) -> Bool {
        TennisChartReading9483.applies(sportKey: event.sport)
    }

    /// The screen's one phase. Never read from a price, a set count or a result.
    static func phase(_ event: EventDetail, now: Date) -> TennisEventPagePhase10868 {
        if EventState.isFinished(event.status) { return .final }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: now) {
            return .during
        }
        return .before
    }

    // MARK: - Players

    /// One displayed player: the served name, its compact label, chart key and tint.
    struct Player: Equatable {
        let side: Side
        let name: String
        /// Nil when the compact label is the whole name.
        let compact: String?
        let shape: FieldHeadlineKeyShape10868
        let tint: Color
        let ref: FieldChooserOriginalRef10868

        var shortName: String { compact ?? name }
    }

    /// Home first (circle), then away (diamond) — the same keys the history draws.
    static func players(_ event: EventDetail) -> [Player] {
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let tints = Self.tints(event)
        let home = Player(side: .home, name: event.homeTeam,
                          compact: names.home == event.homeTeam ? nil : names.home,
                          shape: .circle, tint: tints.home, ref: ref(event, .home))
        let away = Player(side: .away, name: event.awayTeam,
                          compact: names.away == event.awayTeam ? nil : names.away,
                          shape: .diamond, tint: tints.away, ref: ref(event, .away))
        return [home, away]
    }

    static func tints(_ event: EventDetail) -> (away: Color, home: Color) {
        TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                    homeHex: event.homeTeamData?.primaryColor)
    }

    static func scope(_ event: EventDetail) -> String {
        "tennis:\(event.id):winner"
    }

    static func ref(_ event: EventDetail, _ side: Side) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope(event), source: heroSource, marketID: "\(event.id):winner",
                                     outcomeID: side == .home ? "home" : "away")
    }

    // MARK: - Pairs

    /// One player's figure: the raw probability and the owner's whole figure.
    struct Figure: Equatable {
        let probability: Double
        let text: String
    }

    /// One labelled pair. `away` is nil only where the pair rule withholds it
    /// (never in tennis: no draw is priced).
    struct Pair: Equatable {
        let label: String
        let home: Figure
        let away: Figure?
        let detail: String
        /// True only for the hero pair `EventHeadlinePhase9483` calls current.
        let isCurrent: Bool
    }

    /// The pair the hero prints, through the hero's own calls and the pair rule.
    static func heroPair(_ event: EventDetail, host: Host) -> Pair? {
        guard let odds = event.currentOdds else { return nil }
        let shown = OpeningLineHero.resolve(odds, for: event)
        guard let printable = DrawPricedWinner.printablePair(
            away: shown.awayProbability, home: shown.homeProbability, sport: event.sport),
              printable.home.isFinite else { return nil }
        let homeText: String
        var away: Figure?
        if let awayValue = printable.away, awayValue.isFinite {
            let percents = EventDetailView.heroPairPercents(shown, away: awayValue, home: printable.home)
            homeText = formatProbability(printable.home, renderedPercent: percents.home)
            away = Figure(probability: awayValue, text: formatProbability(awayValue, renderedPercent: percents.away))
        } else {
            homeText = formatProbability(printable.home)
        }
        let reading = EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: event.commenceTime?.asDate, isOpeningLine: shown.isOpeningLine,
            observedAt: host.probabilityObservedAt, deliveryInterrupted: host.deliveryInterrupted, now: host.now)
        let label: String
        if shown.isOpeningLine {
            label = OpeningLineHero.caption
        } else {
            label = (reading ?? .lastRecorded).label
        }
        let clock = host.probabilityObservedAt.map { "Recorded \(clockWords($0, host: host))" }
        let source: String? = shown.isOpeningLine ? Words.openingLine : heroSourceName(event)
        return Pair(label: label, home: Figure(probability: printable.home, text: homeText), away: away,
                    detail: joined([clock, source]) ?? label, isCurrent: !shown.isOpeningLine && reading == .current)
    }

    /// The last reading before the start, through `PrematchReading`, labelled as
    /// the production final tennis headline labels it.
    static func prematchPair(_ event: EventDetail) -> Pair? {
        guard let reading = PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds),
              let printable = DrawPricedWinner.printablePair(
                away: reading.awayProbability, home: reading.homeProbability, sport: event.sport)
        else { return nil }
        let percents = reading.percents
        let homeText: String
        var away: Figure?
        if let awayValue = printable.away {
            homeText = formatProbability(printable.home, renderedPercent: percents.count == 2 ? percents[1] : nil)
            away = Figure(probability: awayValue,
                          text: formatProbability(awayValue, renderedPercent: percents.count == 2 ? percents[0] : nil))
        } else {
            homeText = formatProbability(printable.home)
        }
        let label = reading.isServed ? TennisFinalHeadline9483.servedLabel : TennisFinalHeadline9483.openingLabel
        let detail = reading.isServed
            ? joined([Words.lastBeforeStart, SourceLabels.label(for: reading.source)]) ?? Words.lastBeforeStart
            : Words.openingLine
        return Pair(label: label, home: Figure(probability: printable.home, text: homeText), away: away,
                    detail: detail, isCurrent: false)
    }

    /// The hero's source in reader words: the blend is "Bain Luck"
    /// (`OddsChartView`'s own name for it), any other served key only by its
    /// served display name. An unnamed source stays unnamed.
    static func heroSourceName(_ event: EventDetail) -> String? {
        guard let key = event.heroProbabilitySource else { return nil }
        if key == "blend" { return Words.blendName }
        guard let served = event.winProbabilitySources?[key]?.displayName, !served.isEmpty, served != key else {
            return nil
        }
        return served
    }

    /// The production final tennis headline, fed exactly as the page feeds it.
    static func finalHeadline(_ event: EventDetail) -> TennisFinalHeadline9483 {
        TennisFinalHeadline9483.resolve(
            awayName: event.awayTeam, homeName: event.homeTeam, sportKey: event.sport,
            outcome: outcome(event), score: scoreboard(event),
            pregame: PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds))
    }

    static func outcome(_ event: EventDetail) -> EventOutcome {
        EventOutcome.resolve(status: event.status, homeScore: event.homeScore, awayScore: event.awayScore,
                             servedResult: event.heroSettledResult)
    }

    /// The scoreboard the hero draws, or nil where it draws none.
    static func scoreboard(_ event: EventDetail) -> (away: Int, home: Int)? {
        guard EventDetailView.showsScore(status: event.status, away: event.awayScore, home: event.homeScore),
              let home = event.homeScore, let away = event.awayScore else { return nil }
        return (away: away, home: home)
    }

    // MARK: - Headline

    /// What one player shows in the phase: the plan, its tied observations and
    /// the result association (read at the final only).
    struct PlayerReadings: Equatable {
        let plan: FieldChooserDisplayPlan10868
        let before: FieldMovementObservation10868?
        let later: FieldMovementObservation10868?
        let finish: FieldChooserReading10868
        let status: String
    }

    static func headline(_ event: EventDetail, host: Host) -> FieldHeadlineInput10868 {
        let phase = Self.phase(event, now: host.now)
        let players = Self.players(event)
        var catalogue: [FieldChooserOriginal10868] = []
        var pairs: [FieldMovementPair10868] = []
        var finishes: [FieldFinishPlace10868] = []
        for player in players {
            let reading = readings(player.side, event: event, phase: phase, host: host)
            catalogue.append(FieldChooserOriginal10868(
                ref: player.ref, name: player.name, plan: reading.plan,
                preview: FieldChooserPreview10868(history: nil, absence: Words.previewAbsence),
                movement: nil, clock: nil, result: nil, browseStatus: reading.status, accent: player.tint))
            pairs.append(FieldMovementPair10868(ref: player.ref, before: reading.before, later: reading.later,
                                                movement: nil, observation: nil))
            finishes.append(FieldFinishPlace10868(ref: player.ref, reading: reading.finish))
        }
        let slots = players.map {
            FieldHeadlineSlot10868(ref: $0.ref, name: $0.name, compactName: $0.compact, keyShape: $0.shape)
        }
        return FieldHeadlineInput10868(
            scope: scope(event), catalogue: catalogue, displayed: slots, pairs: pairs, finishes: finishes,
            state: state(event, phase: phase, host: host),
            phase: TennisEventPageModel10868.headlinePhase(phase),
            copy: copy(event), unavailableWords: Words.unavailableWords)
    }

    static func copy(_ event: EventDetail) -> FieldHeadlineCopy10868 {
        FieldHeadlineCopy10868(
            eyebrow: event.metadata?.league, title: "\(event.homeTeam) vs \(event.awayTeam)",
            graphicLabel: Words.graphicLabel, beforeLabel: TennisFinalHeadline9483.servedLabel,
            recordedLabel: Words.currentChance, beforeUnavailable: Words.preMatchUnavailable,
            recordedUnavailable: Words.currentUnavailable, finishLabel: Words.matchResult,
            finishUnavailable: Words.resultUnavailable, empty: Words.empty, aboutLabel: Words.aboutLabel,
            aboutHint: Words.aboutHint, openHint: Words.openHint)
    }

    /// One player's readings for the phase. Each plan reading and its tied
    /// observation are the same value, so the headline's one-association rule
    /// shows the figure.
    static func readings(_ side: Side, event: EventDetail, phase: TennisEventPagePhase10868,
                         host: Host) -> PlayerReadings {
        let finish = finishReading(side, event: event, phase: phase)
        switch phase {
        case .before:
            let pair = heroPair(event, host: host)
            let tied = observation(pair, side: side, fallbackLabel: Words.currentChance, missing: Words.noChance)
            return PlayerReadings(plan: .single(tied.reading), before: tied.observation, later: nil,
                                  finish: finish, status: pair?.label ?? Words.noChance)
        case .during:
            let before = observation(prematchPair(event), side: side, fallbackLabel: TennisFinalHeadline9483.servedLabel,
                                     missing: Words.preMatchUnavailable)
            let hero = heroPair(event, host: host)
            let admitted = (hero?.isCurrent == true) ? hero : nil
            let current = admittedCurrent(admitted, side: side)
            return PlayerReadings(plan: .comparison(before: before.reading, later: current.reading),
                                  before: before.observation, later: current.observation, finish: finish,
                                  status: current.observation == nil ? Words.currentUnavailable : Words.currentChance)
        case .final:
            let before = observation(prematchPair(event), side: side, fallbackLabel: TennisFinalHeadline9483.servedLabel,
                                     missing: Words.preMatchUnavailable)
            return PlayerReadings(plan: .single(before.reading), before: before.observation, later: nil,
                                  finish: finish, status: finishStatus(finish))
        }
    }

    /// A pair side as a plan reading and the observation it is tied to; the
    /// owner's missing words when the pair holds nothing for this side.
    static func observation(_ pair: Pair?, side: Side, fallbackLabel: String,
                            missing: String) -> (reading: FieldChooserReading10868, observation: FieldMovementObservation10868?) {
        guard let pair else {
            return (FieldChooserReading10868(label: fallbackLabel, value: .missing(missing)), nil)
        }
        let sided: Figure? = side == .home ? pair.home : pair.away
        guard let figure = sided else {
            return (FieldChooserReading10868(label: pair.label, value: .missing(Words.noChance)), nil)
        }
        let reading = FieldChooserReading10868(label: pair.label, value: .recorded(text: figure.text, detail: pair.detail))
        return (reading, FieldMovementObservation10868(probability: figure.probability, reading: reading))
    }

    /// The current slot: an admitted current pair labelled "Current win
    /// chance", else that slot's own words.
    static func admittedCurrent(_ pair: Pair?, side: Side) -> (reading: FieldChooserReading10868, observation: FieldMovementObservation10868?) {
        guard let pair else {
            return (FieldChooserReading10868(label: Words.currentChance, value: .missing(Words.currentUnavailable)), nil)
        }
        let relabelled = Pair(label: Words.currentChance, home: pair.home, away: pair.away,
                              detail: pair.detail, isCurrent: true)
        return observation(relabelled, side: side, fallbackLabel: Words.currentChance, missing: Words.currentUnavailable)
    }

    /// The event's own reported result for one player, through the production
    /// final tennis headline (`EventOutcome`). Read at the final only.
    static func finishReading(_ side: Side, event: EventDetail, phase: TennisEventPagePhase10868) -> FieldChooserReading10868 {
        guard phase == .final else {
            return FieldChooserReading10868(label: Words.matchResult, value: .missing(Words.resultUnavailable))
        }
        let headline = finalHeadline(event)
        let verdict = side == .home ? headline.home.won : headline.away.won
        guard let won = verdict else {
            return FieldChooserReading10868(label: Words.matchResult, value: .missing(Words.resultUnavailable))
        }
        return FieldChooserReading10868(label: Words.matchResult,
                                        value: .recorded(text: won ? Words.won : Words.lost, detail: Words.recordedOnEvent))
    }

    private static func finishStatus(_ finish: FieldChooserReading10868) -> String {
        switch finish.value {
        case .recorded(let text, _): return text
        case .missing(let words): return words
        }
    }

    // MARK: - State

    /// The set score in sets, home first, once play has started; else nil.
    static func setScore(_ event: EventDetail, phase: TennisEventPagePhase10868) -> String? {
        guard phase != .before, let board = scoreboard(event) else { return nil }
        return "\(board.home)\u{2013}\(board.away)"
    }

    static func setUnit(_ event: EventDetail) -> String? {
        let unit = SportVocab.forSport(event.sport).scoreboardUnit
        return unit.isEmpty ? nil : unit
    }

    /// "0–1 sets": the set score with its unit, once play has started; else nil.
    static func scoreWords(_ event: EventDetail, phase: TennisEventPagePhase10868) -> String? {
        guard let score = setScore(event, phase: phase) else { return nil }
        return setUnit(event).map { "\(score) \($0)" } ?? score
    }

    /// The score's own provenance — its capture clock, never the state's.
    static func scoreDetail(_ event: EventDetail, host: Host) -> String? {
        event.scoreObservedAt?.asDate.map { "\(Words.scoreRecorded) \(clockWords($0, host: host))" }
    }

    static func state(_ event: EventDetail, phase: TennisEventPagePhase10868, host: Host) -> FieldHeadlineState10868 {
        let start = event.commenceTime?.asDate
        switch phase {
        case .before:
            let caption = event.startIsTbd == true ? Words.startToBeAnnounced : Words.scheduledStart
            let detail = event.startIsTbd == true ? start.map { dayWords($0, host: host) } : start.map { clockWords($0, host: host) }
            let spoken = joined([Words.beforeMatch, caption, detail]) ?? Words.beforeMatch
            return FieldHeadlineState10868(figure: Words.beforeMatch, unit: nil, caption: caption, detail: detail,
                                           spoken: spoken, progress: nil)
        case .during:
            let words = duringWords(event, host: host)
            guard let score = setScore(event, phase: phase) else {
                let caption = joined([words.caption, Words.setScoreUnavailable])
                return FieldHeadlineState10868(figure: words.figure, unit: nil, caption: caption, detail: nil,
                                               spoken: joined([words.figure, caption]) ?? words.figure, progress: nil)
            }
            let caption = joined([words.figure, words.caption])
            let detail = scoreDetail(event, host: host)
            let spoken = joined([scoreWords(event, phase: phase), caption, detail]) ?? score
            return FieldHeadlineState10868(figure: score, unit: setUnit(event), caption: caption, detail: detail,
                                           spoken: spoken, progress: nil)
        case .final:
            let caption = joined([Words.final, winnerWords(event)]) ?? Words.final
            let day = start.map { dayWords($0, host: host) }
            guard let score = setScore(event, phase: phase) else {
                return FieldHeadlineState10868(figure: Words.final, unit: nil, caption: winnerWords(event), detail: day,
                                               spoken: joined([caption, day]) ?? caption, progress: nil)
            }
            let spoken = joined([caption, scoreWords(event, phase: phase), day]) ?? caption
            return FieldHeadlineState10868(figure: score, unit: setUnit(event), caption: caption, detail: day,
                                           spoken: spoken, progress: nil)
        }
    }

    /// During play: the venue's own verdict where `EventState` lets this slot
    /// show it (the served result string verbatim, never parsed); else the
    /// suspended treatment for a started suspended match; else the live text.
    static func duringWords(_ event: EventDetail, host: Host) -> (figure: String, caption: String?) {
        let start = event.commenceTime?.asDate
        if EventState.showsVenueSettledVerdict(event.status, venueSettled: event.venueSettled,
                                               commenceTime: start, now: host.now) {
            return (EventState.venueSettledLabel, event.venueSettledResult)
        }
        if EventState.showsVenueClosedNoWinner(event.status, venueSettled: event.venueSettled,
                                               venueClosedNoWinner: event.venueClosedNoWinner,
                                               commenceTime: start, now: host.now) {
            return (EventState.venueClosedNoWinnerLabel, nil)
        }
        if EventState.isSuspendedAndStarted(event.status, commenceTime: start, now: host.now) {
            return (EventState.suspendedLabel(authorityPeriod: event.espn?.period), nil)
        }
        let live = PeriodLabel.liveStatusText(period: event.espn?.period, gameClock: event.espn?.gameClock)
        return (live ?? Words.live, nil)
    }

    /// "Alejandro Davidovich Fokina won" from the production final headline,
    /// else its absence words.
    static func winnerWords(_ event: EventDetail) -> String {
        let headline = finalHeadline(event)
        if headline.home.won == true { return "\(event.homeTeam) won" }
        if headline.away.won == true { return "\(event.awayTeam) won" }
        return Words.resultUnavailable
    }

    // MARK: - Reader heading, notice and About

    /// The one-line match words above full-size content.
    static func readerHeader(_ event: EventDetail, host: Host) -> TennisEventPageReaderHeader10868 {
        let phase = Self.phase(event, now: host.now)
        let players = Self.players(event)
        let matchup = TennisMatchContext9483.matchup(home: players[0].shortName, away: players[1].shortName)
        switch phase {
        case .before:
            return TennisEventPageReaderHeader10868(
                title: matchup, state: heroPair(event, host: host).map { pairWords($0, event: event) })
        case .during:
            let words = duringWords(event, host: host)
            let score = scoreWords(event, phase: phase) ?? Words.setScoreUnavailable
            return TennisEventPageReaderHeader10868(title: matchup, state: joined([score, words.figure, words.caption]))
        case .final:
            let result = TennisMatchContext9483.result(
                finished: true, homeScore: scoreboard(event)?.home, awayScore: scoreboard(event)?.away,
                sportKey: event.sport)
            return TennisEventPageReaderHeader10868(
                title: joined([matchup, result]) ?? matchup,
                state: prematchPair(event).map { pairWords($0, event: event) })
        }
    }

    /// "Pre-match win chance · Fokina 46% · Tiafoe 55%", compact names; a
    /// withheld side is left out rather than guessed.
    static func pairWords(_ pair: Pair, event: EventDetail) -> String {
        let players = Self.players(event)
        let home = "\(players[0].shortName) \(pair.home.text)"
        let away = pair.away.map { "\(players[1].shortName) \($0.text)" }
        return joined([pair.label, home, away]) ?? pair.label
    }

    /// The owner's status words under the headline: only an interrupted delivery.
    static func notice(host: Host) -> String? {
        host.deliveryInterrupted ? Words.updateInterrupted : nil
    }

    /// The match About, in the owner's words: which chances are shown and how
    /// they are timed, what the event record holds for the score and result,
    /// and how the history is drawn. No source link: no production field
    /// serves one.
    static func about(_ event: EventDetail, host: Host) -> TennisEventPageAbout10868 {
        let phase = Self.phase(event, now: host.now)
        var chances: [String] = []
        if phase == .before {
            if let hero = heroPair(event, host: host) {
                chances.append("\(pairWords(hero, event: event)). \(hero.detail).")
            } else {
                chances.append(Words.noHeroPair)
            }
        } else if let pre = prematchPair(event) {
            chances.append("\(pairWords(pre, event: event)). \(pre.detail).")
        } else {
            chances.append(Words.noPrematchPair)
        }
        if phase == .during, heroPair(event, host: host)?.isCurrent != true {
            chances.append(Words.noCurrentAdmitted)
        }
        var sections = [TennisEventPageAboutSection10868(title: Words.aboutChancesTitle, paragraphs: chances)]
        if phase != .before {
            var score: [String] = []
            if let named = scoreWords(event, phase: phase) {
                score.append((joined([named, scoreDetail(event, host: host)]) ?? named) + ".")
            } else {
                score.append(Words.noScoreYet)
            }
            score.append(Words.gamesUnavailable)
            sections.append(TennisEventPageAboutSection10868(title: Words.aboutScoreTitle, paragraphs: score))
        }
        let result: [String]
        if phase == .final, winnerWords(event) != Words.resultUnavailable {
            result = ["\(winnerWords(event)), as recorded on the event."]
        } else {
            result = [Words.noResultYet]
        }
        sections.append(TennisEventPageAboutSection10868(title: Words.aboutResultTitle, paragraphs: result))
        sections.append(TennisEventPageAboutSection10868(title: Words.aboutHistoryTitle, paragraphs: [Words.historyWords]))
        return TennisEventPageAbout10868(title: Words.aboutTitle, sections: sections)
    }

    // MARK: - Words

    /// "Oct 3, 5:20 PM" in the reader's zone — the event page's own date style.
    static func clockWords(_ date: Date, host: Host) -> String {
        date.formatted(style(host).month(.abbreviated).day().hour().minute())
    }

    static func dayWords(_ date: Date, host: Host) -> String {
        date.formatted(style(host).weekday(.abbreviated).month(.abbreviated).day())
    }

    private static func style(_ host: Host) -> Date.FormatStyle {
        Date.FormatStyle(locale: host.locale, calendar: host.calendar, timeZone: host.calendar.timeZone)
    }

    static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
