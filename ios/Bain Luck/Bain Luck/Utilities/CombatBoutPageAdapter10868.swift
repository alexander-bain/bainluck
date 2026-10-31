import SwiftUI

/// #10868 — THE COMBAT EVENT SCREEN'S PRODUCTION ADAPTER, PART ONE: PHASE,
/// THE TWO FIGHTERS' HEADLINE, THE READER HEADING AND THE FIGHT ABOUT.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on an MMA or boxing event page the two
/// fighters lead at equal prominence with exactly the chances the event hero
/// already decides — before the fight the hero's pair, during it the
/// pre-fight reading beside an admitted in-fight chance or its own words,
/// after it the pre-fight reading beside the event's own reported result.
///
/// It decides nothing the app does not already decide. Each slot is the output
/// of the authority that owns it, or that slot's own absence words:
///
///   - phase           `EventState` — finished is final; live, or suspended
///                     after the start, is during; everything else is before.
///                     The same rule as the hockey screen
///                     (`HockeyJourneyPageAdapter10868.phase`), never read from a
///                     price, a round or a result.
///   - before pair     `OpeningLineHero.resolve` + `EventDetailView.heroPairPercents`
///                     + `formatProbability`, the hero's own three calls; "current"
///                     versus "last recorded" is `EventHeadlinePhase9483.resolve`
///                     on the clock the host displays. An opening-line hero is
///                     labelled `OpeningLineHero.caption`, never "current".
///   - pre-fight pair  `PrematchReading.resolve` with its served percents (the
///                     fallback is the sportsbooks' opening line, labelled so).
///                     It carries no clock of its own, so none is printed.
///                     NOT the approved reference's figure: on the retained mma
///                     bout no `prematch_odds` is served, so this prints the
///                     opening line 68% / 32%, where the reference shows
///                     67.2% / 32.8% (the history's last pre-fight blend row).
///                     The two are different readings and never interchangeable;
///                     a last pre-fight blend row is not a pre-match pin until
///                     the baseline owner admits that comparison (Design,
///                     2026-10-31).
///   - in-fight chance during play only, the hero's pair, and only while
///                     `EventHeadlinePhase9483.resolve` calls it current — a
///                     suspended fight, an opening line, a stale or undated
///                     quote or interrupted delivery is never an in-fight chance:
///                     the slot keeps its own words and the reading stays in the
///                     history as a recorded point.
///   - pairing         `DrawPricedWinner.printablePair` on every pair, so the away
///                     fighter's figure is printed only where the app's own pair
///                     rule allows a two-sided reading (combat is undeclared in
///                     `SportVocab`, so the pair stands; a draw-priced sport keeps
///                     the home figure and withholds the away one).
///   - result          after the final only, `EventOutcome.resolve` with the
///                     served verdict (`hero_settled_result`). Never a chance, a
///                     settled contract or a history point. The METHOD, ROUND and
///                     TIME of the finish are not served on any production field
///                     (`EventDetail` has no typed finish tuple and
///                     `venue_settled_result` must not be parsed), so none is
///                     printed: that dependency is the result owner's
///                     (backend event-result capture).
///   - state words     before: the listed start (or "to be announced"); during:
///                     the app's one suspended treatment
///                     (`EventState.isSuspendedAndStarted` +
///                     `EventState.suspendedLabel(authorityPeriod:)`), the venue's
///                     settled or no-winner verdict where `EventState` says the
///                     slot may show it, else `PeriodLabel.liveStatusText`;
///                     after: "Final". No round progress is drawn: no owner serves
///                     an admitted round count.
///   - names, tints    the served names in full; `TeamShortName.shortPair` for the
///                     compact label only; `TeamTextContrast.cardColors`.
///   - identities      the hero pair is an event-level reading, not a provider
///                     original, so each fighter carries an OPAQUE presentation
///                     identity (`scope`, `heroSource`, `<event>:winner`,
///                     `home`/`away`) — never a provider market or outcome id.
///                     The host maps it to the history it opens.
///
/// The host passes what it already decided and this file never reads: the event
/// the hero prints (`vm.headline(event)`), that pair's displayed clock, whether
/// delivery is interrupted, now, and the reader's calendar. Nothing here
/// subscribes, schedules, ranks or fetches.
enum CombatBoutPageAdapter10868 {

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

    /// The fixed words. Fight words both MMA and boxing use — nothing here names
    /// an MMA-only finish or a boxing-only scorecard.
    enum Words {
        static let currentChance = "Current chance"
        static let lastRecordedChance = "Last recorded chance"
        static let preMatchChance = "Pre-match chance"
        static let inFightChance = "In-fight chance"
        static let officialResult = "Official result"
        static let noChance = "No recorded chance"
        static let noInFightChance = "No in-fight chance"
        static let notPrinted = "Win chance unavailable"
        static let resultNotReported = "Result unavailable"
        static let won = "Won"
        static let lost = "Lost"
        static let draw = "Draw"
        static let recordedOnEvent = "Recorded on the event"
        static let lastBeforeStart = "Last reading before the start"
        static let openingLine = "Sportsbooks’ opening line"
        static let graphicLabel = "Fighters’ win chances"
        static let notRecorded = "Not recorded"
        static let empty = "No fighters in this update"
        static let aboutLabel = "About this fight"
        static let aboutHint = "Opens the timing of each chance, the result and sources"
        static let openHint = "Opens this fighter’s history"
        static let unavailableWords = "Fighter unavailable in this update"
        static let previewAbsence = "History in the chart"
        static let beforeFight = "Before the fight"
        static let scheduledStart = "Scheduled start"
        static let startToBeAnnounced = "Start time to be announced"
        static let live = "Live"
        static let final = "Final"
        static let headlineUnavailable = "The fighters’ chances aren’t available for this fight state."
        static let blendName = "Bain Luck"
        static let updateInterrupted = "Update interrupted · showing the last recorded chances"

        // About.
        static let aboutTitle = "About this fight"
        static let aboutChancesTitle = "Chances"
        static let aboutResultTitle = "Official result"
        static let aboutHistoryTitle = "History and sources"
        static let noFinishDetail = "Finish details unavailable."
        static let noResultYet = "Result unavailable."
        static let noHeroPair = "Win chance unavailable."
        static let noPrematchPair = "Pre-match chance not recorded."
        static let noInFightAdmitted = "In-fight chance unavailable. Recorded readings remain in the history."
        static let historyWords = "The chart draws recorded readings only. Times without a reading stay blank, and no line is drawn across them."
    }

    /// The opaque presentation source of the hero pair's identities. A token,
    /// never a venue: nothing names it to the reader.
    static let heroSource = "event-hero"

    // MARK: - Phase

    /// The screen's one phase. Never read from a price, a round or a result.
    static func phase(_ event: EventDetail, now: Date) -> CombatEventPagePhase10868 {
        if EventState.isFinished(event.status) { return .final }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: now) {
            return .during
        }
        return .before
    }

    /// MMA and boxing only; which combat events get this screen is the adopting owner's call.
    static func applies(_ event: EventDetail) -> Bool {
        let sport = (event.sport ?? "").lowercased()
        return sport.hasPrefix("mma_") || sport.hasPrefix("boxing_")
    }

    // MARK: - Fighters

    /// One displayed fighter: the served name, its compact label, chart key and tint.
    struct Fighter: Equatable {
        let side: Side
        let name: String
        /// Nil when the compact label is the whole name.
        let compact: String?
        let shape: FieldHeadlineKeyShape10868
        let tint: Color
        let ref: FieldChooserOriginalRef10868
    }

    /// Home first (circle), then away (diamond) — the same keys the history draws.
    static func fighters(_ event: EventDetail) -> [Fighter] {
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let home = Fighter(side: .home, name: event.homeTeam,
                           compact: names.home == event.homeTeam ? nil : names.home,
                           shape: .circle, tint: tints.home, ref: ref(event, .home))
        let away = Fighter(side: .away, name: event.awayTeam,
                           compact: names.away == event.awayTeam ? nil : names.away,
                           shape: .diamond, tint: tints.away, ref: ref(event, .away))
        return [home, away]
    }

    static func scope(_ event: EventDetail) -> String {
        "combat:\(event.id):winner"
    }

    static func ref(_ event: EventDetail, _ side: Side) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope(event), source: heroSource, marketID: "\(event.id):winner",
                                     outcomeID: side == .home ? "home" : "away")
    }

    // MARK: - Pairs

    /// One fighter's figure: the raw probability and the owner's whole figure.
    struct Figure: Equatable {
        let probability: Double
        let text: String
    }

    /// One labelled pair. `away` is nil where the pair rule withholds it.
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
            label = reading == .current ? Words.currentChance : Words.lastRecordedChance
        }
        let clock = host.probabilityObservedAt.map { "Recorded \(clockWords($0, host: host))" }
        let source = shown.isOpeningLine ? Words.openingLine : heroSourceName(event)
        return Pair(label: label, home: Figure(probability: printable.home, text: homeText), away: away,
                    detail: joined([clock, source]) ?? label, isCurrent: !shown.isOpeningLine && reading == .current)
    }

    /// The last reading before the start, through `PrematchReading`.
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
        let label = reading.isServed ? Words.preMatchChance : OpeningLineHero.caption
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

    // MARK: - Headline

    /// What one fighter shows in the phase: the plan, its tied observations and
    /// the result association (read at the final only).
    struct FighterReadings: Equatable {
        let plan: FieldChooserDisplayPlan10868
        let before: FieldMovementObservation10868?
        let later: FieldMovementObservation10868?
        let finish: FieldChooserReading10868
        let status: String
    }

    static func headline(_ event: EventDetail, host: Host) -> FieldHeadlineInput10868 {
        let phase = Self.phase(event, now: host.now)
        let fighters = Self.fighters(event)
        let readings = fighters.map { Self.readings($0.side, event: event, phase: phase, host: host) }
        var catalogue: [FieldChooserOriginal10868] = []
        var pairs: [FieldMovementPair10868] = []
        var finishes: [FieldFinishPlace10868] = []
        for (fighter, reading) in zip(fighters, readings) {
            catalogue.append(FieldChooserOriginal10868(
                ref: fighter.ref, name: fighter.name, plan: reading.plan,
                preview: FieldChooserPreview10868(history: nil, absence: Words.previewAbsence),
                movement: nil, clock: nil, result: nil, browseStatus: reading.status, accent: fighter.tint))
            pairs.append(FieldMovementPair10868(ref: fighter.ref, before: reading.before, later: reading.later,
                                                movement: nil, observation: nil))
            finishes.append(FieldFinishPlace10868(ref: fighter.ref, reading: reading.finish))
        }
        let slots = fighters.map {
            FieldHeadlineSlot10868(ref: $0.ref, name: $0.name, compactName: $0.compact, keyShape: $0.shape)
        }
        return FieldHeadlineInput10868(
            scope: scope(event), catalogue: catalogue, displayed: slots, pairs: pairs, finishes: finishes,
            state: state(event, phase: phase, host: host),
            phase: CombatEventPageModel10868.headlinePhase(phase),
            copy: copy(event), unavailableWords: Words.unavailableWords)
    }

    static func copy(_ event: EventDetail) -> FieldHeadlineCopy10868 {
        FieldHeadlineCopy10868(
            eyebrow: event.metadata?.league, title: "\(event.homeTeam) vs \(event.awayTeam)",
            graphicLabel: Words.graphicLabel, beforeLabel: Words.preMatchChance, recordedLabel: Words.inFightChance,
            beforeUnavailable: Words.notRecorded, recordedUnavailable: Words.noInFightChance,
            finishLabel: Words.officialResult, finishUnavailable: Words.resultNotReported,
            empty: Words.empty, aboutLabel: Words.aboutLabel, aboutHint: Words.aboutHint, openHint: Words.openHint)
    }

    /// One fighter's readings for the phase. Each plan reading and its tied
    /// observation are the same value, so the headline's one-association rule
    /// shows the figure.
    static func readings(_ side: Side, event: EventDetail, phase: CombatEventPagePhase10868,
                         host: Host) -> FighterReadings {
        let finish = finishReading(side, event: event, phase: phase)
        switch phase {
        case .before:
            let pair = heroPair(event, host: host)
            let tied = observation(pair, side: side, fallbackLabel: Words.preMatchChance, missing: Words.noChance)
            return FighterReadings(plan: .single(tied.reading), before: tied.observation, later: nil,
                                   finish: finish, status: pair?.label ?? Words.noChance)
        case .during:
            let before = observation(prematchPair(event), side: side, fallbackLabel: Words.preMatchChance,
                                     missing: Words.noChance)
            let hero = heroPair(event, host: host)
            let admitted = (hero?.isCurrent == true) ? hero : nil
            let current = admittedInFight(admitted, side: side)
            return FighterReadings(plan: .comparison(before: before.reading, later: current.reading),
                                   before: before.observation, later: current.observation,
                                   finish: finish, status: current.observation == nil ? Words.noInFightChance : Words.inFightChance)
        case .final:
            let before = observation(prematchPair(event), side: side, fallbackLabel: Words.preMatchChance,
                                     missing: Words.noChance)
            return FighterReadings(plan: .single(before.reading), before: before.observation, later: nil,
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
        let figure: Figure? = side == .home ? pair.home : pair.away
        guard let figure else {
            return (FieldChooserReading10868(label: pair.label, value: .missing(Words.notPrinted)), nil)
        }
        let reading = FieldChooserReading10868(label: pair.label, value: .recorded(text: figure.text, detail: pair.detail))
        return (reading, FieldMovementObservation10868(probability: figure.probability, reading: reading))
    }

    /// The in-fight slot: an admitted current pair labelled "In-fight chance",
    /// else that slot's own words.
    static func admittedInFight(_ pair: Pair?, side: Side) -> (reading: FieldChooserReading10868, observation: FieldMovementObservation10868?) {
        guard let pair else {
            return (FieldChooserReading10868(label: Words.inFightChance, value: .missing(Words.noInFightChance)), nil)
        }
        let relabelled = Pair(label: Words.inFightChance, home: pair.home, away: pair.away,
                              detail: pair.detail, isCurrent: true)
        return observation(relabelled, side: side, fallbackLabel: Words.inFightChance, missing: Words.noInFightChance)
    }

    /// The event's own reported result for one fighter, through `EventOutcome`.
    /// Before the final it is never read by the headline; it still says only
    /// what the event record holds.
    static func finishReading(_ side: Side, event: EventDetail, phase: CombatEventPagePhase10868) -> FieldChooserReading10868 {
        let words = resultWords(event)
        let mine: String? = side == .home ? words?.home : words?.away
        guard phase == .final, let mine else {
            return FieldChooserReading10868(label: Words.officialResult, value: .missing(Words.resultNotReported))
        }
        return FieldChooserReading10868(label: Words.officialResult, value: .recorded(text: mine, detail: Words.recordedOnEvent))
    }

    /// "Won"/"Lost" or "Draw" per side, or nil while `EventOutcome` names no result.
    static func resultWords(_ event: EventDetail) -> (home: String, away: String)? {
        switch EventOutcome.resolve(status: event.status, homeScore: event.homeScore, awayScore: event.awayScore,
                                    servedResult: event.heroSettledResult) {
        case .home: return (Words.won, Words.lost)
        case .away: return (Words.lost, Words.won)
        case .draw: return (Words.draw, Words.draw)
        case .undecided: return nil
        }
    }

    private static func finishStatus(_ finish: FieldChooserReading10868) -> String {
        switch finish.value {
        case .recorded(let text, _): return text
        case .missing(let words): return words
        }
    }

    // MARK: - State

    static func state(_ event: EventDetail, phase: CombatEventPagePhase10868, host: Host) -> FieldHeadlineState10868 {
        let start = event.commenceTime?.asDate
        switch phase {
        case .before:
            let caption = event.startIsTbd == true ? Words.startToBeAnnounced : Words.scheduledStart
            let detail = event.startIsTbd == true ? start.map { dayWords($0, host: host) } : start.map { clockWords($0, host: host) }
            let spoken = joined([Words.beforeFight, caption, detail]) ?? Words.beforeFight
            return FieldHeadlineState10868(figure: Words.beforeFight, unit: nil, caption: caption, detail: detail,
                                           spoken: spoken, progress: nil)
        case .during:
            let words = duringWords(event, host: host)
            let spoken = joined([words.figure, words.caption]) ?? words.figure
            return FieldHeadlineState10868(figure: words.figure, unit: nil, caption: words.caption, detail: nil,
                                           spoken: spoken, progress: nil)
        case .final:
            let caption = finalCaption(event)
            let detail = start.map { dayWords($0, host: host) }
            let spoken = joined([Words.final, caption, detail]) ?? Words.final
            return FieldHeadlineState10868(figure: Words.final, unit: nil, caption: caption, detail: detail,
                                           spoken: spoken, progress: nil)
        }
    }

    /// During play: the venue's own verdict where `EventState` lets this slot
    /// show it (the served result string verbatim, never parsed); else the
    /// suspended treatment for a started suspended fight; else the live text.
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

    /// "Roman Kopylov won" from the event's own result, else its absence words.
    static func finalCaption(_ event: EventDetail) -> String {
        switch EventOutcome.resolve(status: event.status, homeScore: event.homeScore, awayScore: event.awayScore,
                                    servedResult: event.heroSettledResult) {
        case .home: return "\(event.homeTeam) won"
        case .away: return "\(event.awayTeam) won"
        case .draw: return Words.draw
        case .undecided: return Words.resultNotReported
        }
    }

    // MARK: - Reader heading, notice and About

    /// The one-line fight words above full-size content.
    static func readerHeader(_ event: EventDetail, host: Host) -> CombatEventPageReaderHeader10868 {
        let phase = Self.phase(event, now: host.now)
        let matchup = "\(event.homeTeam) vs \(event.awayTeam)"
        let title: String
        switch phase {
        case .before, .during:
            title = matchup
        case .final:
            let caption = finalCaption(event)
            title = caption == Words.resultNotReported ? "\(Words.final) · \(matchup)" : caption
        }
        let pair = phase == .before ? heroPair(event, host: host) : prematchPair(event)
        return CombatEventPageReaderHeader10868(title: title, state: pair.map { pairWords($0, event: event) })
    }

    /// "Opening line · Gautier 68% · Kopylov 32%", compact names; a withheld
    /// side is left out rather than guessed.
    static func pairWords(_ pair: Pair, event: EventDetail) -> String {
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let home = "\(names.home) \(pair.home.text)"
        let away = pair.away.map { "\(names.away) \($0.text)" }
        return joined([pair.label, home, away]) ?? pair.label
    }

    /// The owner's status words under the headline: only an interrupted delivery.
    static func notice(host: Host) -> String? {
        host.deliveryInterrupted ? Words.updateInterrupted : nil
    }

    /// The fight About, in the owner's words: which chances are shown and how
    /// they are timed, what the event record holds for the result, and how the
    /// history is drawn. No source link: no production field serves one.
    static func about(_ event: EventDetail, host: Host) -> CombatEventPageAbout10868 {
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
            chances.append(Words.noInFightAdmitted)
        }
        var result: [String] = []
        if phase == .final, resultWords(event) != nil {
            result.append("\(finalCaption(event)), as recorded on the event.")
            result.append(Words.noFinishDetail)
        } else {
            result.append(Words.noResultYet)
        }
        return CombatEventPageAbout10868(title: Words.aboutTitle, sections: [
            CombatEventPageAboutSection10868(title: Words.aboutChancesTitle, paragraphs: chances),
            CombatEventPageAboutSection10868(title: Words.aboutResultTitle, paragraphs: result),
            CombatEventPageAboutSection10868(title: Words.aboutHistoryTitle, paragraphs: [Words.historyWords]),
        ])
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
