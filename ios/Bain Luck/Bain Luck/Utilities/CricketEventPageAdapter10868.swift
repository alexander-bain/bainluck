import SwiftUI

/// #10868 — THE CRICKET TEST-MATCH SCREEN'S PRODUCTION ADAPTER, PART ONE:
/// PHASE, TITLE, READER HEADING, THE THREE-ORIGINAL HEADLINE AND THE MATCH
/// ABOUT.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `cricket-live` the headline names the
/// home side, the away side and the draw / tie, each with its own chance or
/// that slot's own words — the away side is never shown the remainder after the
/// home side's chance, which on a match that can be drawn carries the draw — and
/// a finished match shows the reported result, never a settled 0% or 100%.
///
/// It decides nothing the app does not already decide. Each slot is the output
/// of the authority that owns it, or that slot's own absence words:
///
///   - phase           `EventState` — finished, live, or a stoppage after the
///                     start (`isSuspendedAndStarted`); never a score or price.
///   - pregame         `PrematchReading.resolve` (the server's pregame ladder,
///                     else `opening_odds`) with its served whole percents. It
///                     carries no clock, so none is printed — only its word.
///   - latest pair     `OpeningLineHero.resolve` + `EventDetailView.heroPairPercents`
///                     + `formatProbability`, the hero's own three calls, so this
///                     headline and the hero can never round one price two ways.
///                     "Current" versus "last recorded" is `EventHeadlinePhase9483`
///                     on the clock the host displays. During play an opening
///                     line, or a pair observed before the listed start, is not
///                     an in-play reading and is never shown as one.
///   - the away side   `DrawPricedWinner.printablePair` (the app's one two-slot
///                     rule) AND `isComplementPair` (RenderedPercent.swift, the
///                     app's measured complement-pair band). See `independentAway`.
///   - the draw / tie  no production model the event page holds decodes a draw
///                     price (`EventDetail`, `CurrentOdds`, `PrematchOdds` and
///                     `HistoryPoint` have no draw field), so it is always that
///                     slot's own words. Named dependency in the return.
///   - result          `EventOutcome.resolve` with the served verdict
///                     (`hero_settled_result`); `OutcomeVerdict` / `EventOutcome`
///                     words. Unknown is not loss: no verdict is "Result
///                     unavailable".
///   - score state     no cricket scoreboard reaches the app: `homeScore` /
///                     `awayScore` are whole numbers and null on every retained
///                     cricket body, and no runs/wickets/overs/target field exists.
///                     The state is always "Score unavailable". Named dependency.
///   - names, tints    the served team names; `TeamTextContrast.cardColors`.
///   - source words    the served `win_probability_sources[…].displayName` only,
///                     through `HockeyJourneyPageAdapter10868.sourceName`.
///   - clock words     `HockeyJourneyPageAdapter10868.clockWords` / `timeWords` /
///                     `dayWords`, the candidate's one reader-calendar formatter.
///
/// The rows carry no original reference (`ref` is nil, so they are static): the
/// headline's pair is the page's blended probability, not one venue contract,
/// and no production field links it to an original in the catalogue.
///
/// The host passes what it already decided and this file never reads: the event
/// the hero prints, that pair's displayed clock, whether delivery is
/// interrupted, now and the reader's calendar. Nothing here subscribes,
/// schedules, ranks or fetches.
enum CricketEventPageAdapter10868 {

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

        /// The hockey candidate's host, for its clock and source words only.
        var clock: HockeyJourneyPageAdapter10868.Host {
            HockeyJourneyPageAdapter10868.Host(probabilityObservedAt: probabilityObservedAt,
                                               deliveryInterrupted: deliveryInterrupted, now: now,
                                               calendar: calendar, locale: locale)
        }
    }

    /// The fixed words; the approved reference's own where it wrote them.
    enum Words {
        static let pregame = "Pregame"
        static let current = "Current"
        static let lastRecorded = "Last recorded"
        static let currentChance = "Current chance"
        static let lastRecordedChance = "Last recorded chance"
        static let match = "Match"
        static let drawSubject = "Draw / tie"
        static let winChanceUnavailable = "Win chance unavailable"
        static let drawChanceUnavailable = "Draw chance unavailable"
        static let pregameUnavailable = "Pregame chance unavailable"
        /// During play with no in-play reading: the opening line, or a pair from
        /// before the listed start, stays in the pregame slot and the history.
        static let inPlayUnavailable = "In-play chance unavailable"
        static let resultUnavailable = "Result unavailable"
        static let scoreUnavailable = "Score unavailable"
        /// The reference's result words (`CricketLifecycle.tsx` Expectations).
        static let winner = "Winner"
        static let noDrawOrTie = "No draw / tie"
        static let finalResult = "Final result"
        static let beforePlay = "Before play"
        static let live = "Live"
        static let final = "Final"
        static let startToBeAnnounced = "start time to be announced"
        static let aboutLabel = "About this match"
        static let aboutTitle = "How this match is shown"
    }

    /// The screen's three originals, in the reference's order.
    enum Original: String, CaseIterable {
        case home
        case away
        case draw
    }

    // MARK: - Phase

    /// The screen's one phase. A finished status is the final; a live status,
    /// or a stoppage after the start, is during play; everything else is
    /// before. Never read from a score, a clock or a price.
    static func phase(_ event: EventDetail, now: Date) -> CricketHeadlinePhase10868 {
        if EventState.isFinished(event.status) { return .completed }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(event.status, commenceTime: event.commenceTime?.asDate, now: now) {
            return .during
        }
        return .before
    }

    /// A scope word for identities.
    static func phaseWord(_ phase: CricketHeadlinePhase10868) -> String {
        switch phase {
        case .before: "before"
        case .during: "during"
        case .completed: "completed"
        }
    }

    // MARK: - Title and reader heading

    static func title(_ event: EventDetail, host: Host) -> CricketEventPageTitle10868 {
        CricketEventPageTitle10868(eyebrow: stateWords(event, host: host),
                                   title: "\(event.homeTeam) · \(event.awayTeam)")
    }

    /// The compact words above full-size content: the reported winner at the
    /// final, else the two sides; the state line under it.
    static func readerHeader(_ event: EventDetail, host: Host) -> CricketEventPageReaderHeader10868 {
        let pagePhase = phase(event, now: host.now)
        var title = "\(event.homeTeam) · \(event.awayTeam)"
        if pagePhase == .completed {
            switch outcome(event) {
            case .home: title = "\(event.homeTeam) won"
            case .away: title = "\(event.awayTeam) won"
            case .draw: title = "\(event.homeTeam) · \(event.awayTeam) · \(EventOutcome.draw.drawLabel ?? Words.final)"
            case .undecided: break
            }
        }
        let state = pagePhase == .before ? stateWords(event, host: host) : "\(stateWords(event, host: host)) · \(Words.scoreUnavailable)"
        return CricketEventPageReaderHeader10868(title: title, state: state)
    }

    /// The phase in words. A stoppage after the start wears the app's one
    /// treatment (`StatusBadge`'s words, #4021/#9208), never a word this file
    /// names for itself. No period or clock is printed: no cricket match state
    /// reaches the app.
    static func stateWords(_ event: EventDetail, host: Host) -> String {
        let start = event.commenceTime?.asDate
        switch phase(event, now: host.now) {
        case .before:
            guard let start else { return Words.beforePlay }
            let day = HockeyJourneyPageAdapter10868.dayWords(start, host: host.clock)
            if event.startIsTbd == true { return "\(Words.beforePlay) · \(day) · \(Words.startToBeAnnounced)" }
            let time = HockeyJourneyPageAdapter10868.timeWords(start, host: host.clock)
            return "\(Words.beforePlay) · \(day), \(time) start"
        case .during:
            if EventState.isSuspendedAndStarted(event.status, commenceTime: start, now: host.now) {
                return EventState.suspendedLabel(authorityPeriod: event.espn?.period)
            }
            return Words.live
        case .completed:
            return Words.final
        }
    }

    // MARK: - Headline

    static func headline(_ event: EventDetail, host: Host) -> CricketHeadlineInput10868 {
        let pagePhase = phase(event, now: host.now)
        let latest = currentPair(event, host: host)
        let rows = Self.rows(event, phase: pagePhase, latest: latest, host: host)
        // Before play the one slot is the latest pre-match reading, captioned
        // by what it is; during play and at the final the slots carry their own
        // labels and there is no caption.
        let caption: String? = pagePhase == .before ? latest?.title : nil
        let label: String = comparisonLabel(rows, latest: latest)
        let state: CricketHeadlineState10868? = pagePhase == .before ? nil : .unavailable(Words.scoreUnavailable)
        return CricketHeadlineInput10868(
            phase: pagePhase,
            caption: caption,
            beforeLabel: Words.pregame,
            comparisonLabel: label,
            outcomeLabel: Words.match,
            outcomeMissing: Words.resultUnavailable,
            rows: rows,
            state: state)
    }

    /// "Last recorded" only over a figure the pair's own clock calls stale;
    /// otherwise the slot is the current one, shown or unavailable.
    static func comparisonLabel(_ rows: [CricketOutlookRow10868], latest: CurrentPair?) -> String {
        let showsFigure = rows.contains { $0.comparison.observation != nil }
        return showsFigure && latest?.currentness == .lastRecorded ? Words.lastRecorded : Words.current
    }

    /// The three originals at this phase, in the reference's order.
    static func rows(_ event: EventDetail, phase: CricketHeadlinePhase10868, latest: CurrentPair?,
                     host: Host) -> [CricketOutlookRow10868] {
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let pregame = pregameReadings(event)
        let inPlay: (home: CricketOutlookReading10868, away: CricketOutlookReading10868)? =
            phase == .during ? inPlayReadings(event, latest: latest, host: host) : nil
        let result: EventOutcome? = phase == .completed ? outcome(event) : nil
        var out: [CricketOutlookRow10868] = []
        for original in Original.allCases {
            let before: CricketOutlookReading10868
            let comparison: CricketOutlookReading10868
            switch phase {
            case .before:
                before = slot(original, home: latest?.home, away: latest?.away,
                              missing: Words.winChanceUnavailable)
                comparison = .unavailable(Words.inPlayUnavailable)
            case .during:
                before = slot(original, home: pregame.home, away: pregame.away, missing: Words.pregameUnavailable)
                comparison = slot(original, home: inPlay?.home, away: inPlay?.away, missing: Words.inPlayUnavailable)
            case .completed:
                before = slot(original, home: pregame.home, away: pregame.away, missing: Words.pregameUnavailable)
                comparison = .unavailable(Words.inPlayUnavailable)
            }
            out.append(CricketOutlookRow10868(
                id: rowID(event, original), subject: subject(event, original), shape: shape(original),
                tint: tint(original, tints: tints), ref: nil, before: before, comparison: comparison,
                movement: nil, finish: result.map { finish($0, original: original) }))
        }
        return out
    }

    /// One original's reading from a home/away pair; the draw is always its words.
    static func slot(_ original: Original, home: CricketOutlookReading10868?, away: CricketOutlookReading10868?,
                     missing: String) -> CricketOutlookReading10868 {
        switch original {
        case .home: home ?? .unavailable(missing)
        case .away: away ?? .unavailable(missing)
        case .draw: .unavailable(Words.drawChanceUnavailable)
        }
    }

    // MARK: - Readings

    /// The pair the hero prints, through the hero's own calls, said per side.
    struct CurrentPair: Equatable {
        /// "Opening line", "Current chance" or "Last recorded chance".
        let title: String
        let isOpeningLine: Bool
        /// `EventHeadlinePhase9483`'s answer; nil on the opening arm and at the final.
        let currentness: EventHeadlinePhase9483?
        let home: CricketOutlookReading10868
        let away: CricketOutlookReading10868
    }

    static func currentPair(_ event: EventDetail, host: Host) -> CurrentPair? {
        guard let odds = event.currentOdds else { return nil }
        let shown = OpeningLineHero.resolve(odds, for: event)
        guard let home = shown.homeProbability, home.isFinite, home >= 0, home <= 1 else { return nil }
        let reading = EventHeadlinePhase9483.resolve(
            status: event.status, commenceTime: event.commenceTime?.asDate, isOpeningLine: shown.isOpeningLine,
            observedAt: host.probabilityObservedAt, deliveryInterrupted: host.deliveryInterrupted, now: host.now)
        let title: String
        if shown.isOpeningLine {
            title = OpeningLineHero.caption
        } else {
            title = reading == .current ? Words.currentChance : Words.lastRecordedChance
        }
        // The hero's own whole-percent decision for this pair, read whether or
        // not the away figure is shown, so home rounds exactly as the hero does.
        var percents: (away: Int?, home: Int?)?
        if let away = shown.awayProbability, away.isFinite {
            percents = EventDetailView.heroPairPercents(shown, away: away, home: home)
        }
        let clock = host.probabilityObservedAt.map { "Recorded \(HockeyJourneyPageAdapter10868.clockWords($0, host: host.clock))" }
        let source = HockeyJourneyPageAdapter10868.sourceName(event.heroProbabilitySource, in: event)
        let detail = joined([clock, source]) ?? title
        let homeReading = observed(home, rendered: percents?.home, detail: detail)
        let awayReading: CricketOutlookReading10868
        if let away = independentAway(shown.awayProbability, home: home, sport: event.sport) {
            awayReading = observed(away, rendered: percents?.away, detail: detail)
        } else {
            awayReading = .unavailable(Words.winChanceUnavailable)
        }
        return CurrentPair(title: title, isOpeningLine: shown.isOpeningLine, currentness: reading,
                           home: homeReading, away: awayReading)
    }

    /// During play: the latest pair, but only as an in-play reading. The
    /// opening line is a pre-start quote; a pair observed before the listed
    /// start is too. Neither is shown in the in-play slot — the first is the
    /// pregame slot's own value, and both stay in the history.
    static func inPlayReadings(_ event: EventDetail, latest: CurrentPair?,
                               host: Host) -> (home: CricketOutlookReading10868, away: CricketOutlookReading10868)? {
        guard let latest else { return nil }
        if latest.isOpeningLine {
            return (.unavailable(Words.inPlayUnavailable), .unavailable(Words.inPlayUnavailable))
        }
        if let observed = host.probabilityObservedAt, let start = event.commenceTime?.asDate, observed < start {
            return (.withheld(Words.inPlayUnavailable), .withheld(Words.inPlayUnavailable))
        }
        return (latest.home, latest.away)
    }

    /// The last reading before the start, through `PrematchReading`.
    static func pregameReadings(_ event: EventDetail) -> (home: CricketOutlookReading10868?,
                                                          away: CricketOutlookReading10868?) {
        guard let reading = PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds) else {
            return (nil, nil)
        }
        let source = reading.isServed ? HockeyJourneyPageAdapter10868.sourceName(reading.source, in: event) : nil
        let detail = joined([reading.captionWord, source]) ?? reading.captionWord
        let percents = reading.percents
        let home = observed(reading.homeProbability, rendered: percents.count == 2 ? percents[1] : nil, detail: detail)
        var away: CricketOutlookReading10868 = .unavailable(Words.winChanceUnavailable)
        if !reading.awayIsComplement,
           let value = independentAway(reading.awayProbability, home: reading.homeProbability, sport: event.sport) {
            away = observed(value, rendered: percents.count == 2 ? percents[0] : nil, detail: detail)
        }
        return (home, away)
    }

    /// THE AWAY SIDE'S OWN READING ON A SCREEN THAT LISTS A DRAW / TIE, or nil.
    ///
    /// Two existing rules, both of which must agree:
    ///   1. `DrawPricedWinner.printablePair` — the app's one two-slot rule. It
    ///      withholds the away figure on a sport DECLARED draw-priced
    ///      (`SportVocab.winnerMarketPricesADraw`). Today only soccer is
    ///      declared, in all three runtimes; cricket is deliberately not
    ///      ("nobody has measured those markets", SportVocab.swift:81-84), so for
    ///      cricket this rule alone passes the figure through.
    ///   2. `isComplementPair` — the app's measured band (0.99–1.01) for a
    ///      pair whose two figures are complements. This is the Test-match
    ///      screen: its design lists a Draw / tie original beside the two
    ///      sides, so a draw is a real outcome here, and an away figure that is
    ///      only `1 − home` is "the home side does not win" — away OR draw
    ///      (#5271's defect). The app itself records that
    ///      `current_odds.away_probability` IS the backend's rounded `1 − home`
    ///      (EventDetailView.swift, the note on `heroPairPercents`), while
    ///      `opening_odds` is de-vigged across every outcome a
    ///      book quotes and so is the away side's own price when a draw is
    ///      quoted (backend `draw_priced_winner.away_is_the_complement`). This is
    ///      that function's evidence test, applied because this screen lists a
    ///      draw — not inferred from a sport key.
    ///
    /// It only ever removes a figure; it never derives, rescales or replaces one.
    /// The proper owner fix is declaring Test cricket draw-priced (#5271's
    /// rule, one row in each runtime once measured); then rule 1 alone answers.
    static func independentAway(_ away: Double?, home: Double?, sport: String?) -> Double? {
        guard let home, home.isFinite,
              let pair = DrawPricedWinner.printablePair(away: away, home: home, sport: sport),
              let printable = pair.away, printable.isFinite, printable >= 0, printable <= 1,
              !isComplementPair([printable, home])
        else { return nil }
        return printable
    }

    static func observed(_ value: Double, rendered: Int?, detail: String) -> CricketOutlookReading10868 {
        .observed(CricketOutlookObservation10868(probability: value,
                                                 text: formatProbability(value, renderedPercent: rendered),
                                                 detail: detail))
    }

    // MARK: - Result

    static func outcome(_ event: EventDetail) -> EventOutcome {
        EventOutcome.resolve(status: event.status, homeScore: event.homeScore, awayScore: event.awayScore,
                             servedResult: event.heroSettledResult)
    }

    /// The reported match outcome for one original, in the reference's words.
    /// No verdict is the owner's missing words, never a loss. No contract grade
    /// is attached: the headline's pair is not an original contract; each
    /// original's own grade stays in its Details (part three).
    static func finish(_ outcome: EventOutcome, original: Original) -> CricketOutlookFinish10868 {
        guard let words = outcomeWords(outcome, original: original) else {
            return CricketOutlookFinish10868(outcome: .unavailable(Words.resultUnavailable), grade: nil)
        }
        return CricketOutlookFinish10868(
            outcome: .admitted(CricketOutlookFinalWord10868(text: words, symbolName: nil, detail: Words.finalResult)),
            grade: nil)
    }

    static func outcomeWords(_ outcome: EventOutcome, original: Original) -> String? {
        let draw = EventOutcome.draw.drawLabel
        switch (outcome, original) {
        case (.undecided, _): return nil
        case (.home, .home), (.away, .away): return Words.winner
        case (.home, .away), (.away, .home): return OutcomeVerdict.lost.label
        case (.home, .draw), (.away, .draw): return Words.noDrawOrTie
        case (.draw, _): return draw
        }
    }

    // MARK: - Identity, names and keys

    static func rowID(_ event: EventDetail, _ original: Original) -> String {
        "cricket:\(event.id):\(original.rawValue)"
    }

    static func subject(_ event: EventDetail, _ original: Original) -> String {
        switch original {
        case .home: event.homeTeam
        case .away: event.awayTeam
        case .draw: Words.drawSubject
        }
    }

    /// The reference's three keys by position; part two draws the same shapes.
    static func shape(_ original: Original) -> CricketOutlookShape10868 {
        switch original {
        case .home: .circle
        case .away: .diamond
        case .draw: .square
        }
    }

    static func tint(_ original: Original, tints: (away: Color, home: Color)) -> Color {
        switch original {
        case .home: tints.home
        case .away: tints.away
        case .draw: DS.textSecondary
        }
    }

    // MARK: - About

    /// How this page reads the match, in plain words.
    static func about(_ event: EventDetail, host: Host) -> CricketEventPageAbout10868 {
        var paragraphs = [
            "Each outcome's chance is shown with the time it was recorded. The chances are separate readings: they are not adjusted to add up to 100%.",
            "A Test match can end in a draw. The draw chance is unavailable here, so \(event.awayTeam)'s chance is shown only when it is that side's own chance, never what is left after \(event.homeTeam)'s chance.",
            "Scores, overs, wickets and targets are unavailable here, so no innings, chase or wickets-remaining story is shown.",
        ]
        if phase(event, now: host.now) == .completed {
            paragraphs.append("The result is the reported match result. A finished match's 0% or 100% is a result, not a chance, and is never shown as one.")
        }
        return CricketEventPageAbout10868(title: Words.aboutTitle, paragraphs: paragraphs)
    }

    // MARK: - Words

    static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
