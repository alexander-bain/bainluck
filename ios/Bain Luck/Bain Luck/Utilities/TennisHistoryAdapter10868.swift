import SwiftUI

/// #10868 — THE TENNIS MATCH SCREEN'S PRODUCTION ADAPTER, PART TWO: THE
/// TWO-PLAYER WIN-PROBABILITY HISTORY (THE ANCHOR).
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on a tennis event page the anchor beside
/// the players draws only what was recorded — the last reading before the
/// scheduled start, then the match — and leaves every unrecorded stretch blank,
/// never a settlement, a pinned hero value or a line run on to now; the away
/// player's trace on a two-outcome blend is said to be the other side of that
/// blend.
///
/// It builds `FieldHistoryInput10868` from the decoded `/api/events/{id}/history`
/// body (`EventHistoryResponse`), the event (`EventDetail`), the page phase and
/// the reader's clock. Every ROW decision is the hockey screen's part two
/// (`HockeyJourneyHistoryAdapter10868`), called, not copied — the machinery the
/// combat screen also calls: it is sport-free and reads only the production
/// chart rules, so no two screens can draw one served body two ways:
///
///   - which line       `OddsChartView.primarySource(in: servedPoints(from:))`:
///                      the backend blend when served, else the sportsbook
///                      consensus — the same series the tennis reading panel reads
///                      (`OddsChartView.readoutSource`). Never a client mean.
///   - the two traces   home is the line's served value; away is the served away
///                      value, else, on the blend only, the documented complement
///                      of THAT SAME ROW through `DrawPricedWinner.printablePair` —
///                      tennis prices no draw (`SportVocab`), so the app's own pair
///                      rule allows it, exactly as `TennisChartReading9483.awayRuns`
///                      draws the blend's away line — and a note says so.
///   - not readings     a finished match's settlement row, the blend's pinned edge
///                      (`blendEdgePinned`) and blend minutes that hold only the
///                      backend's carry-forward (`BlendPreview.carriedForwardMinutes`).
///   - runs and gaps    unreadable rows break a run; `OddsChartView.observationSegments`
///                      breaks inside each stretch; `OddsChartView.gameEndDate`
///                      clips a finished match.
///   - before / match   `OddsChartView.sinceStartCut`, refused when `startIsTbd`.
///     split            The cut is at best a SCHEDULED start (the tennis finding of
///                      2026-10-20, `TennisChartReading9483`), so the baseline is
///                      worded "Before scheduled start" (`TennisChartReading9483
///                      .baselineLabel`) and a later point is a "Recorded chance"
///                      (`.recordedLabel`) — nothing claims play began. No
///                      confirmed start: one unsplit history, no before-start
///                      reading, hollow mark or guide, and the readout says the
///                      start is not confirmed.
///   - guides           the hockey machinery's (`periodSightings` admitted by
///                      `PeriodLabel.columnLabel`, scoring plays). The retained
///                      tennis bodies serve no ESPN history and no scoring plays,
///                      so none is drawn. No set-boundary guide is added: no
///                      served field dates a set.
///   - axes and words   the hockey machinery's frame, ticks, figures, source words,
///                      complement note and summary.
///
/// What is the tennis screen's own: the phase (part one's
/// `TennisMatchPageAdapter10868.phase`), match words, the players' key shapes
/// (home circle, away diamond — the headline's), and the provenance lines.
///
/// Phase scopes (the hockey screen's, read in match words):
///   before — readable rows from the listed start less one day up to the last
///            row before the scheduled start; no guides.
///   during — the last row before the scheduled start, then the match's rows up
///            to now.
///   final  — the last row before the scheduled start, then the match's rows up
///            to the match's end, without the settlement row.
///
/// Nothing here fetches, subscribes, schedules or holds state. The host's live
/// chart frames and preview overlay are not built here (owed: the owner-admitted
/// live buffer the production chart reads through `vm.enrichedChartPoints`), and
/// the held inspection is the tennis reading (part three), not this input's:
/// `inspection` is nil and Inspect is offered unavailable.
enum TennisHistoryAdapter10868 {
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
        var words: TennisMatchPageAdapter10868.Host {
            TennisMatchPageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    enum Words {
        static let title = "Win probability"
        static let beforeCaption = "Before the match"
        static let matchCaption = "Match history"
        static let notRecorded = "Not recorded"
        static let noHistory = "No recorded history"
        /// No history response at all: says nothing about whether rows exist or why.
        static let historyUnavailable = "History unavailable"
        static let hollowKey = "Hollow · before scheduled start"
        static let gapsNote = "Gaps remain blank."
        static let unconfirmedStart = "Start time not confirmed"
        static let unconfirmedStartWords = "Readings before the start and during the match are split at a confirmed start, and this match has none yet."
        static let details = "History & source details"
        static let expand = "Full chart"
        static let expandSpoken = "Expand match win probability history"
        static let inspect = "Inspect history"
    }

    /// Offered unavailable until a history details destination exists.
    static let detailsActionID = "history.details"
    /// The one action the host routes: the full-size history reader.
    static let expandActionID = "history.expand"
    /// Offered unavailable: the held inspection is the tennis reading's.
    static let inspectActionID = "history.inspect"

    static let plotHeight: CGFloat = 230

    /// The row machinery's own name for the same phase.
    static func rowPhase(_ phase: TennisEventPagePhase10868) -> HockeyJourneyPagePhase10868 {
        switch phase {
        case .before: .before
        case .during: .live
        case .final: .final
        }
    }

    // MARK: - The history

    static func history(_ response: EventHistoryResponse, event: EventDetail,
                        phase: TennisEventPagePhase10868, host: Host) -> FieldHistoryInput10868 {
        let line = Rows.line(response)
        let tints = TennisMatchPageAdapter10868.tints(event)
        // Nil when the start is not a confirmed cut: the readings still draw, unsplit.
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
        let caption: String = phase == .before ? Words.beforeCaption : Words.matchCaption
        let plotted = FieldHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                              upper: domain.upperBound.timeIntervalSince1970)
        let placedGuides: [FieldHistoryGuide10868] = phase == .before || kickoff == nil
            ? [] : Rows.guides(response, event: event, from: domain.lowerBound, through: last)
        let readout: FieldHistoryReadoutIntent10868
        if kickoff == nil {
            readout = .singleBefore(label: Words.unconfirmedStart)
        } else if phase == .during {
            readout = .beforeAndRecorded(beforeLabel: TennisChartReading9483.baselineLabel,
                                         recordedLabel: TennisChartReading9483.recordedLabel)
        } else {
            readout = .singleBefore(label: TennisChartReading9483.baselineLabel)
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
                       drawn: Rows.Drawn, phase: TennisEventPagePhase10868, kickoff: Date?,
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
            let provenance = "\(TennisChartReading9483.baselineLabel) · \(clockWords(pregame.date, host: host))"
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
                                    provenance: "\(TennisChartReading9483.recordedLabel) · \(clockWords(latest.date, host: host))")
        } else {
            recorded = .absent(words: Words.notRecorded)
        }

        return FieldHistorySeries10868(id: id, name: name, shape: shape, tint: tint, runs: runs, links: [],
                                       labelPointID: nil, before: before, recorded: recorded,
                                       absentWords: Words.noHistory, choose: nil)
    }

    static func clockWords(_ date: Date, host: Host) -> String {
        TennisMatchPageAdapter10868.clockWords(date, host: host.words)
    }

    // MARK: - Nothing to draw

    /// Nothing to draw, in the owner's words: no point, axis or guide is offered
    /// under it, and the domain is a placeholder the leaf never draws under an absence.
    static func absence(_ response: EventHistoryResponse, event: EventDetail, line: Rows.Line,
                        phase: TennisEventPagePhase10868, tints: (away: Color, home: Color),
                        plot: FieldHistoryPlotAbsence10868) -> FieldHistoryInput10868 {
        func empty(_ side: Rows.Side, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color) -> FieldHistorySeries10868 {
            FieldHistorySeries10868(id: Rows.seriesID(line: line, eventId: response.eventId, side: side), name: name,
                                    shape: shape, tint: tint, runs: [], links: [], labelPointID: nil,
                                    before: .absent(words: Words.notRecorded), recorded: .absent(words: Words.notRecorded),
                                    absentWords: Words.noHistory, choose: nil)
        }
        return FieldHistoryInput10868(
            title: Words.title,
            caption: phase == .before ? Words.beforeCaption : Words.matchCaption,
            series: [empty(.home, event.homeTeam, .circle, tints.home), empty(.away, event.awayTeam, .diamond, tints.away)],
            selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: TennisChartReading9483.baselineLabel),
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
    static func unavailable(event: EventDetail, phase: TennisEventPagePhase10868) -> FieldHistoryInput10868 {
        let tints = TennisMatchPageAdapter10868.tints(event)
        func empty(_ side: Rows.Side, _ name: String, _ shape: FieldHistoryShape10868, _ tint: Color) -> FieldHistorySeries10868 {
            FieldHistorySeries10868(id: Rows.seriesID(line: .blend, eventId: event.id, side: side), name: name,
                                    shape: shape, tint: tint, runs: [], links: [], labelPointID: nil,
                                    before: .absent(words: Words.historyUnavailable),
                                    recorded: .absent(words: Words.historyUnavailable),
                                    absentWords: Words.historyUnavailable, choose: nil)
        }
        return FieldHistoryInput10868(
            title: Words.title,
            caption: phase == .before ? Words.beforeCaption : Words.matchCaption,
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
