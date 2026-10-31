import SwiftUI

/// #10868 — THE COMBAT EVENT SCREEN'S PRODUCTION ADAPTER, PART TWO: THE
/// TWO-FIGHTER WIN-PROBABILITY HISTORY (THE ANCHOR).
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on an MMA or boxing event page the anchor
/// beside the fighters draws only what was recorded — the last pre-fight
/// reading, then the fight — and leaves every unrecorded stretch blank, never a
/// settlement, a pinned hero value or a line run on to now; the away fighter's
/// trace on a two-outcome blend is said to be the other side of that blend.
///
/// It builds `FieldHistoryInput10868` from the decoded `/api/events/{id}/history`
/// body (`EventHistoryResponse`), the event (`EventDetail`), the page phase and
/// the reader's clock. Every ROW decision is the hockey screen's part two
/// (`HockeyJourneyHistoryAdapter10868`), called, not copied: that machinery is
/// sport-free — it reads only the production chart rules — and calling it keeps
/// the two screens from ever drawing one served body two ways:
///
///   - which line       `HockeyJourneyHistoryAdapter10868.line` →
///                      `OddsChartView.primarySource(in: servedPoints(from:))`:
///                      the backend blend when served, else the sportsbook
///                      consensus. Never a client mean.
///   - the two traces   `servedRows`: home is the line's served value; away is
///                      the served away value, else, on the blend only, the
///                      documented complement of THAT SAME ROW through
///                      `DrawPricedWinner.printablePair` — combat is undeclared in
///                      `SportVocab`, so the app's own pair rule allows it — and a
///                      note says so. The complement never gains a row, a time
///                      or a break of its own.
///   - not readings     `removedIndexes`: a finished event's settlement row, the
///                      blend's pinned edge (`blendEdgePinned`) and blend minutes
///                      that hold only the backend's carry-forward
///                      (`BlendPreview.carriedForwardMinutes`).
///   - runs and gaps    `entries` + `drawn`: unreadable rows break a run;
///                      `OddsChartView.observationSegments` breaks inside each
///                      stretch; `OddsChartView.gameEndDate` clips a finished event.
///   - pre-fight split  `kickoff` → `OddsChartView.sinceStartCut`, refused when
///                      `startIsTbd`. No confirmed start: one unsplit history, no
///                      last pre-fight reading, hollow mark or guide, and the
///                      readout says the start is not confirmed.
///   - guides           `guides` (`OddsChartView.periodSightings` filtered by
///                      `PeriodLabel.columnLabel`, scoring plays worded by
///                      `ExpandedRecordedMatchMoment9483.play`). The retained
///                      combat bodies serve none, so none is drawn. No start or
///                      finish guide is added here: the production chart draws
///                      neither, and no owner serves a finish time (the official
///                      finish clock is not on any field).
///   - axes and words   `frame`, `xTicks` (`OddsChartView.xAxisPlan`/`xAxisTicks`
///                      in the reader's calendar), `yTicks`
///                      (`OddsChartView.axisLabel`), `readingFigure`
///                      (`formatProbability`, and `duelProbabilityStrings` for a
///                      complement pair), `sourceWords`, `complementNote`,
///                      `summary`.
///
/// What is the combat screen's own: the phase (part one's
/// `CombatBoutPageAdapter10868.phase`), fight words, the fighters' key shapes
/// (home circle, away diamond — the headline's), and the provenance lines.
///
/// Phase scopes (the hockey screen's, read in fight words):
///   before — readable pre-fight rows from each side's own last pre-fight row
///            less one day (inclusive) up to that row; no guides.
///   during — the last pre-fight row, then the fight's rows up to now.
///   final  — the last pre-fight row, then the fight's rows up to the event's
///            end, without the settlement row.
/// Where the in-fight frame opens is the host's admission and is still owed
/// (the hockey adapter's `inGameStart`; this file uses its default, the last
/// pre-fight row).
///
/// Nothing here fetches, subscribes, schedules or holds state. The host's held
/// inspection, the live chart frames and the preview overlay are not built
/// here: `inspection` is nil and Inspect is offered unavailable.
enum CombatHistoryAdapter10868 {
    /// The sport-free row machinery this file calls.
    typealias Rows = HockeyJourneyHistoryAdapter10868

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        /// The reader's own calendar, time zone and locale; every clock word and
        /// tick is said in it.
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        /// The row machinery's host, for its ticks.
        var rows: Rows.Host { Rows.Host(now: now, calendar: calendar, locale: locale) }

        /// Part one's host, so the history says its clocks in the headline's words.
        var words: CombatBoutPageAdapter10868.Host {
            CombatBoutPageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    enum Words {
        static let title = "Win probability"
        static let beforeCaption = "Before the fight"
        static let fightCaption = "Fight history"
        static let preFight = "Pre-fight"
        static let recorded = "Recorded"
        static let lastPreFight = "Last pre-fight"
        static let notRecorded = "Not recorded"
        static let noHistory = "No recorded history"
        /// No history response at all: says nothing about whether rows exist or why.
        static let historyUnavailable = "History unavailable"
        static let hollowKey = "Hollow · last pre-fight"
        static let gapsNote = "Gaps remain blank."
        static let unconfirmedStart = "Start time not confirmed"
        static let unconfirmedStartWords = "Pre-fight and fight readings are split at a confirmed start, and this fight has none yet."
        static let details = "History & source details"
        static let expand = "Full chart"
        static let expandSpoken = "Expand fight win probability history"
        static let inspect = "Inspect history"
    }

    /// Offered unavailable until a history details destination exists.
    static let detailsActionID = "history.details"
    /// The one action the host routes: the full-size history reader.
    static let expandActionID = "history.expand"
    /// Offered unavailable until an owner-admitted inspection and its held reader exist.
    static let inspectActionID = "history.inspect"

    static let plotHeight: CGFloat = 230

    /// The row machinery's own name for the same phase.
    static func rowPhase(_ phase: CombatEventPagePhase10868) -> HockeyJourneyPagePhase10868 {
        switch phase {
        case .before: .before
        case .during: .live
        case .final: .final
        }
    }

    // MARK: - The history

    static func history(_ response: EventHistoryResponse, event: EventDetail,
                        phase: CombatEventPagePhase10868, host: Host) -> FieldHistoryInput10868 {
        // Another event's history never draws here: only a response served under
        // this event's own id reaches the rows. A foreign one reads exactly like a
        // missing one; the rest of the page composes from its own inputs.
        guard response.eventId == event.id else { return unavailable(event: event, phase: phase) }
        let line = Rows.line(response)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        // Nil when the start is not a confirmed kick-off: the readings still draw, unsplit.
        let kickoff = Rows.kickoff(response, event: event)
        let entries = Rows.entries(Rows.servedRows(response, line: line, sport: event.sport),
                                   removing: Rows.removedIndexes(response, event: event, line: line))
        let end: Date = phase == .final
            ? min(OddsChartView.gameEndDate(status: event.status, history: response) ?? host.now, host.now)
            : host.now
        let rowPhase = Self.rowPhase(phase)
        let home = Rows.drawn(entries, side: .home, phase: rowPhase, kickoff: kickoff,
                              gapStart: event.commenceTime?.asDate, end: end, now: host.now,
                              opening: nil, line: line)
        let away = Rows.drawn(entries, side: .away, phase: rowPhase, kickoff: kickoff,
                              gapStart: event.commenceTime?.asDate, end: end, now: host.now,
                              opening: nil, line: line)

        let dates = (home.runs + away.runs).flatMap { $0.map(\.date) }
        guard let first = dates.min(), let last = dates.max() else {
            return absence(response, event: event, line: line, phase: phase, tints: tints,
                           plot: FieldHistoryPlotAbsence10868(title: Words.noHistory, words: nil))
        }
        let domain = Rows.frame(first, last)
        let complement = Rows.drawsComplement(away)
            ? Rows.complementNote(away: event.awayTeam, home: event.homeTeam) : nil

        let homeSeries = series(Rows.seriesID(line: line, eventId: response.eventId, side: .home), side: .home,
                                name: event.homeTeam, shape: .circle, tint: tints.home,
                                drawn: home, phase: phase, kickoff: kickoff, host: host)
        let awaySeries = series(Rows.seriesID(line: line, eventId: response.eventId, side: .away), side: .away,
                                name: event.awayTeam, shape: .diamond, tint: tints.away,
                                drawn: away, phase: phase, kickoff: kickoff, host: host)
        // Each part on its own line, so the one large initializer below stays
        // cheap to type-check.
        let caption: String = phase == .before ? Words.beforeCaption : Words.fightCaption
        let plotted = FieldHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                              upper: domain.upperBound.timeIntervalSince1970)
        let placedGuides: [FieldHistoryGuide10868] = phase == .before || kickoff == nil
            ? [] : Rows.guides(response, event: event, from: domain.lowerBound, through: last)
        let readout: FieldHistoryReadoutIntent10868
        if kickoff == nil {
            readout = .singleBefore(label: Words.unconfirmedStart)
        } else if phase == .during {
            readout = .beforeAndRecorded(beforeLabel: Words.preFight, recordedLabel: Words.recorded)
        } else {
            readout = .singleBefore(label: Words.preFight)
        }
        let hollow: String? = kickoff == nil ? nil : Words.hollowKey
        var notes: [String] = [Rows.sourceWords(line)]
        if let complement { notes.append(complement) }
        notes.append(Words.gapsNote)
        var said: String = Rows.summary([(event.homeTeam, !home.runs.isEmpty), (event.awayTeam, !away.runs.isEmpty)])
        if let complement { said += " \(complement)" }
        let inspect: FieldHistoryAction10868? = phase == .during
            ? Rows.action(inspectActionID, Words.inspect, available: false) : nil
        return FieldHistoryInput10868(
            title: Words.title,
            caption: caption,
            series: [homeSeries, awaySeries],
            selection: .none,
            domain: plotted,
            ceiling: 1,
            yTicks: Rows.yTicks(),
            xTicks: Rows.xTicks(domain, host: host.rows),
            guides: placedGuides,
            breaks: [],
            readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: hollow, filled: nil),
            comparisonExplanation: nil,
            notes: notes,
            summary: said,
            plotHeight: plotHeight,
            unboundReadingWords: Words.notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: Rows.action(detailsActionID, Words.details, available: false),
            expand: Rows.action(expandActionID, Words.expand, spoken: Words.expandSpoken),
            inspect: inspect,
            previous: nil, next: nil, inspection: nil)
    }

    // MARK: - One trace

    static func series(_ id: String, side: Rows.Side, name: String, shape: FieldHistoryShape10868, tint: Color,
                       drawn: Rows.Drawn, phase: CombatEventPagePhase10868, kickoff: Date?,
                       host: Host) -> FieldHistorySeries10868 {
        let hollow = drawn.pregameDrawn ? drawn.lastPregame?.entry.row.index : nil
        let runs = drawn.runs.enumerated().map { number, run in
            FieldHistoryRun10868(id: "\(id)#run-\(number + 1)", points: run.map { vertex in
                FieldHistoryPoint10868(id: Rows.pointID(id, vertex.entry.row.timestamp),
                                       x: vertex.date.timeIntervalSince1970, probability: vertex.value,
                                       style: vertex.entry.row.index == hollow ? .hollow : .filled)
            })
        }

        let before: FieldHistoryReading10868
        if let pregame = drawn.lastPregame {
            let figure = Rows.readingFigure(pregame, side: side)
            let provenance = "\(Words.lastPreFight) · \(clockWords(pregame.date, host: host))"
            before = drawn.pregameDrawn
                ? .observation(pointID: Rows.pointID(id, pregame.entry.row.timestamp), figure: figure,
                               provenance: provenance)
                : .independent(figure: figure, provenance: provenance)
        } else {
            // With no confirmed start the baseline slot says why it holds no reading.
            before = .absent(words: kickoff == nil ? Words.unconfirmedStartWords : Words.notRecorded)
        }

        let recorded: FieldHistoryReading10868
        if phase == .during, let kickoff, let latest = drawn.runs.last?.last, latest.date >= kickoff {
            recorded = .observation(pointID: Rows.pointID(id, latest.entry.row.timestamp),
                                    figure: Rows.readingFigure(latest, side: side),
                                    provenance: "\(Words.recorded) \(clockWords(latest.date, host: host))")
        } else {
            recorded = .absent(words: Words.notRecorded)
        }

        return FieldHistorySeries10868(id: id, name: name, shape: shape, tint: tint, runs: runs, links: [],
                                       labelPointID: nil, before: before, recorded: recorded,
                                       absentWords: Words.noHistory, choose: nil)
    }

    static func clockWords(_ date: Date, host: Host) -> String {
        CombatBoutPageAdapter10868.clockWords(date, host: host.words)
    }

    // MARK: - Nothing to draw

    /// Nothing to draw, in the owner's words: no point, axis or guide is offered
    /// under it, and the domain is a placeholder the leaf never draws under an absence.
    static func absence(_ response: EventHistoryResponse, event: EventDetail, line: Rows.Line,
                        phase: CombatEventPagePhase10868, tints: (away: Color, home: Color),
                        plot: FieldHistoryPlotAbsence10868) -> FieldHistoryInput10868 {
        func empty(_ side: Rows.Side, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color) -> FieldHistorySeries10868 {
            FieldHistorySeries10868(id: Rows.seriesID(line: line, eventId: response.eventId, side: side), name: name,
                                    shape: shape, tint: tint, runs: [], links: [], labelPointID: nil,
                                    before: .absent(words: Words.notRecorded), recorded: .absent(words: Words.notRecorded),
                                    absentWords: Words.noHistory, choose: nil)
        }
        return FieldHistoryInput10868(
            title: Words.title,
            caption: phase == .before ? Words.beforeCaption : Words.fightCaption,
            series: [empty(.home, event.homeTeam, .circle, tints.home), empty(.away, event.awayTeam, .diamond, tints.away)],
            selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: Words.preFight),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: [Rows.sourceWords(line)],
            summary: Words.noHistory,
            plotHeight: plotHeight,
            unboundReadingWords: Words.notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: Rows.action(detailsActionID, Words.details, available: false),
            expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil,
            plotAbsence: plot)
    }

    /// No history response at all — not arrived yet, or failed; the host does
    /// not say which, so neither is claimed. The chart slot says "History
    /// unavailable" through the plot-absence channel, names no source, draws
    /// nothing and offers no working control. The rest of the page composes from
    /// its own inputs. The real load/error/retry contract stays Native's.
    static func unavailable(event: EventDetail, phase: CombatEventPagePhase10868) -> FieldHistoryInput10868 {
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        func empty(_ side: Rows.Side, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color) -> FieldHistorySeries10868 {
            FieldHistorySeries10868(id: Rows.seriesID(line: .blend, eventId: event.id, side: side), name: name,
                                    shape: shape, tint: tint, runs: [], links: [], labelPointID: nil,
                                    before: .absent(words: Words.historyUnavailable),
                                    recorded: .absent(words: Words.historyUnavailable),
                                    absentWords: Words.historyUnavailable, choose: nil)
        }
        return FieldHistoryInput10868(
            title: Words.title,
            caption: phase == .before ? Words.beforeCaption : Words.fightCaption,
            series: [empty(.home, event.homeTeam, .circle, tints.home), empty(.away, event.awayTeam, .diamond, tints.away)],
            selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: Words.historyUnavailable),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: [],
            summary: Words.historyUnavailable,
            plotHeight: plotHeight,
            unboundReadingWords: Words.historyUnavailable,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: Rows.action(detailsActionID, Words.details, available: false),
            expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil,
            plotAbsence: FieldHistoryPlotAbsence10868(title: Words.historyUnavailable, words: nil))
    }
}
