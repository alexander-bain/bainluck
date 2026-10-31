import SwiftUI

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART TWO: THE WIN
/// PROBABILITY HISTORY UNDER THREE NAMED OUTCOMES.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on the soccer match screen the history
/// draws only the home win chance that was recorded — the last pre-match
/// reading, then the match — leaves every unrecorded stretch blank, and keeps
/// Draw and the away win in its key with their own words for why they have no
/// line, never a line made from the home one.
///
/// It builds `FieldHistoryInput10868` from the decoded `/api/events/{id}/history`
/// body (`EventHistoryResponse`), the event, the page phase and the reader's
/// clock. Every row rule is the accepted hockey history adapter's (H2,
/// `HockeyJourneyHistoryAdapter10868`), called rather than copied, so the two
/// screens read one served history the same way:
///
///   - which line       `HockeyJourneyHistoryAdapter10868.line` →
///                      `OddsChartView.primarySource`: the backend blend
///                      (`aggregate_line`) where served, else the consensus.
///   - removals         its `removedIndexes`: the settlement row a finished
///                      match appends last, the blend's pinned edge
///                      (`blendEdgePinned`) and carried-forward minutes.
///   - breaks           its `drawn`: `OddsChartView.observationSegments` inside
///                      each stretch between unreadable rows; never a line
///                      across an unknown span.
///   - pre-match split  its `kickoff` (`OddsChartView.sinceStartCut`, refused
///                      under `startIsTbd`); no confirmed start draws one
///                      unsplit history with no last pre-match reading.
///   - guides, axes     its `guides`, `xTicks`, `yTicks`, `frame`.
///   - the home series  its `series`, so the hollow last pre-match point and
///                      the readouts are H2's; only the `before` slot's words
///                      are re-said in a match's terms (`matchWorded`).
///
/// What is soccer's own, and why:
///
///   - ONLY THE HOME WIN IS DRAWN. Soccer prices a draw, so the away side is
///     NOT read from any served row: on the blend `aggregate_line` serves home
///     only (H2's complement is withheld by `DrawPricedWinner.printablePair`),
///     and on the consensus the served `away_probability` is a two-way figure
///     that absorbs the draw (#5271, #1011's data defect) — the production rule
///     ignores it on a draw-priced sport, and so does this file.
///   - Draw and the away win are KEY ENTRIES WITH NO RUNS. Each keeps its own
///     words. The dependency is named, not manufactured: `WinProbHistoryPoint`
///     decodes home only, `win_prob_snapshots.draw_probability` has no writer
///     (DrawPricedWinner.swift), and genuine three-way history and phase
///     baselines are #1011 (Live owns the forward writer) with group coherence
///     under #5328.
///
/// Phase scopes are H2's (before: the listed start less one day up to the last
/// pre-match row; live: the last pre-match row, then the match up to now;
/// final: the same up to the match's end, without the settlement row). Where
/// the in-game frame opens is still the host's (H2's `inGameStart`, default
/// last pre-match row). The host's held inspection, the window and scale
/// controls and the live preview overlay are not built here (nil), and Details
/// and Inspect stay unavailable until their owner contracts exist.
///
/// Nothing here fetches, subscribes, schedules or holds state.
enum SoccerHistoryAdapter10868 {
    typealias H = HockeyJourneyHistoryAdapter10868
    /// H2's host: now and the reader's calendar, time zone and locale.
    typealias Host = HockeyJourneyHistoryAdapter10868.Host

    enum Words {
        static let title = "Win probability"
        static let beforeCaption = "Before kickoff"
        static let gameCaption = "Match history"
        static let preMatch = "Pre-match"
        static let recorded = "Recorded"
        static let draw = "Draw"
        static let notRecorded = "Not recorded"
        static let noHistory = "No recorded history"
        static let historyUnavailable = "History unavailable"
        static let drawHistoryUnavailable = "Draw chance history unavailable"
        static let awayHistoryUnavailable = "Away win chance history unavailable"
        static let hollowKey = "Hollow · last pre-match"
        static let lastPreMatch = "Last pre-match"
        static let unconfirmedKickoff = "Kickoff time not confirmed"
        static let unconfirmedKickoffWords =
            "Pre-match and match readings are split at a confirmed kickoff, and this match has none yet."
        static let expandSpoken = "Expand soccer win probability history"

        /// "Draw and Albacete win chance history unavailable."
        static func drawAndAwayNote(away: String) -> String {
            "Draw and \(away) win chance history unavailable."
        }
    }

    static let drawShape: FieldHistoryShape10868 = .diamond

    // MARK: - The history

    static func history(_ response: EventHistoryResponse, event: EventDetail,
                        phase: SoccerEventPagePhase10868, host: Host) -> FieldHistoryInput10868 {
        // Another event's history never draws here: only a response served under
        // this event's own id reaches the rows. A foreign one reads exactly like a
        // missing one; the rest of the page composes from its own inputs.
        guard response.eventId == event.id else { return unavailable(event: event, phase: phase) }
        let drawnPhase = hockeyPhase(phase)
        let names = SoccerMatchPageAdapter10868.names(event)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let line = H.line(response)
        let kickoff = H.kickoff(response, event: event)
        let entries = H.entries(H.servedRows(response, line: line, sport: event.sport),
                                removing: H.removedIndexes(response, event: event, line: line))
        let end: Date = phase == .final
            ? min(OddsChartView.gameEndDate(status: event.status, history: response) ?? host.now, host.now)
            : host.now
        let home = H.drawn(entries, side: .home, phase: drawnPhase, kickoff: kickoff,
                           gapStart: event.commenceTime?.asDate, end: end, now: host.now,
                           opening: nil, line: line)

        let draw = absentSeries(id: drawID(line: line, eventId: response.eventId), name: Words.draw,
                                shape: drawShape, tint: DS.textSecondary, words: Words.drawHistoryUnavailable)
        let away = absentSeries(id: H.seriesID(line: line, eventId: response.eventId, side: .away),
                                name: SoccerMatchPageAdapter10868.Words.outcome(names.away), shape: .square,
                                tint: tints.away, words: Words.awayHistoryUnavailable)

        let dates = home.runs.flatMap { $0.map(\.date) }
        guard let first = dates.min(), let last = dates.max() else {
            let empty = absentSeries(id: H.seriesID(line: line, eventId: response.eventId, side: .home),
                                     name: SoccerMatchPageAdapter10868.Words.outcome(names.home), shape: .circle,
                                     tint: tints.home, words: Words.noHistory)
            return emptyInput(phase: phase, series: [empty, draw, away], notes: [H.sourceWords(line)],
                              summary: Words.noHistory,
                              plot: FieldHistoryPlotAbsence10868(title: Words.noHistory, words: nil))
        }
        let domain = H.frame(first, last)
        let homeSeries = matchWorded(
            H.series(H.seriesID(line: line, eventId: response.eventId, side: .home), side: .home,
                     name: SoccerMatchPageAdapter10868.Words.outcome(names.home), shape: .circle,
                     tint: tints.home, drawn: home, phase: drawnPhase, kickoff: kickoff, host: host),
            drawn: home, kickoff: kickoff, host: host)
        // Each part on its own line, so the one large initializer below stays
        // cheap to type-check.
        let caption: String = phase == .before ? Words.beforeCaption : Words.gameCaption
        let plotted = FieldHistoryDomain10868(lower: domain.lowerBound.timeIntervalSince1970,
                                              upper: domain.upperBound.timeIntervalSince1970)
        let placedGuides: [FieldHistoryGuide10868] = phase == .before || kickoff == nil
            ? [] : H.guides(response, event: event, from: domain.lowerBound, through: last)
        let readout: FieldHistoryReadoutIntent10868
        if kickoff == nil {
            readout = .singleBefore(label: Words.unconfirmedKickoff)
        } else if phase == .live {
            readout = .beforeAndRecorded(beforeLabel: Words.preMatch, recordedLabel: Words.recorded)
        } else {
            readout = .singleBefore(label: Words.preMatch)
        }
        let hollow: String? = kickoff == nil ? nil : Words.hollowKey
        let notes: [String] = [H.sourceWords(line), Words.drawAndAwayNote(away: names.away), H.Words.gapsNote]
        let homeName = SoccerMatchPageAdapter10868.Words.outcome(names.home)
        let said = "\(homeName) chance, recorded observations only. \(Words.drawAndAwayNote(away: names.away))"
        let inspect: FieldHistoryAction10868? = phase == .live
            ? H.action(H.inspectActionID, H.Words.inspect, available: false) : nil
        return FieldHistoryInput10868(
            title: Words.title,
            caption: caption,
            series: [homeSeries, draw, away],
            selection: .none,
            domain: plotted,
            ceiling: 1,
            yTicks: H.yTicks(),
            xTicks: H.xTicks(domain, host: host),
            guides: placedGuides,
            breaks: [],
            readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: hollow, filled: nil),
            comparisonExplanation: nil,
            notes: notes,
            summary: said,
            plotHeight: H.plotHeight,
            unboundReadingWords: Words.notRecorded,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: H.action(H.detailsActionID, H.Words.details, available: false),
            expand: H.action(H.expandActionID, H.Words.expand, spoken: Words.expandSpoken),
            inspect: inspect,
            previous: nil, next: nil, inspection: nil)
    }

    /// No history response at all — not arrived yet, or failed; the host does
    /// not say which, so neither is claimed. The chart slot says "History
    /// unavailable" through the plot-absence channel, draws nothing and offers
    /// no working control. The rest of the page composes from its own inputs.
    static func unavailable(event: EventDetail, phase: SoccerEventPagePhase10868) -> FieldHistoryInput10868 {
        let names = SoccerMatchPageAdapter10868.names(event)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let series = [
            absentSeries(id: H.seriesID(line: .blend, eventId: event.id, side: .home),
                         name: SoccerMatchPageAdapter10868.Words.outcome(names.home), shape: .circle,
                         tint: tints.home, words: Words.historyUnavailable),
            absentSeries(id: drawID(line: .blend, eventId: event.id), name: Words.draw, shape: drawShape,
                         tint: DS.textSecondary, words: Words.historyUnavailable),
            absentSeries(id: H.seriesID(line: .blend, eventId: event.id, side: .away),
                         name: SoccerMatchPageAdapter10868.Words.outcome(names.away), shape: .square,
                         tint: tints.away, words: Words.historyUnavailable),
        ]
        return emptyInput(phase: phase, series: series, notes: [], summary: Words.historyUnavailable,
                          plot: FieldHistoryPlotAbsence10868(title: Words.historyUnavailable, words: nil),
                          readoutLabel: Words.historyUnavailable, unbound: Words.historyUnavailable)
    }

    // MARK: - Parts

    /// H2's own phase for its row rules; the three phases are the same three.
    static func hockeyPhase(_ phase: SoccerEventPagePhase10868) -> HockeyJourneyPagePhase10868 {
        switch phase {
        case .before: .before
        case .live: .live
        case .final: .final
        }
    }

    /// H2's home series with its `before` slot said in a match's words: the same
    /// reading bound the same way (drawn → the exact point; not drawn → an
    /// independent figure; none → its reason), "Last pre-match" where H2 says
    /// "Last pregame". Every other field is H2's, unchanged.
    static func matchWorded(_ series: FieldHistorySeries10868, drawn: H.Drawn, kickoff: Date?,
                            host: Host) -> FieldHistorySeries10868 {
        let before: FieldHistoryReading10868
        if let pregame = drawn.lastPregame {
            let figure = H.readingFigure(pregame, side: .home)
            let provenance = "\(Words.lastPreMatch) · \(H.clockWords(pregame.date, host: host))"
            before = drawn.pregameDrawn
                ? .observation(pointID: H.pointID(series.id, pregame.entry.row.timestamp), figure: figure,
                               provenance: provenance)
                : .independent(figure: figure, provenance: provenance)
        } else {
            before = .absent(words: kickoff == nil ? Words.unconfirmedKickoffWords : Words.notRecorded)
        }
        return FieldHistorySeries10868(id: series.id, name: series.name, shape: series.shape, tint: series.tint,
                                       runs: series.runs, links: series.links, labelPointID: series.labelPointID,
                                       before: before, recorded: series.recorded, absentWords: series.absentWords,
                                       choose: series.choose)
    }

    /// The Draw entry's identity, beside H2's home and away series ids.
    static func drawID(line: H.Line, eventId: Int) -> String {
        "\(line == .blend ? "blend" : "consensus"):\(eventId):draw"
    }

    /// A key entry with no runs and its own words in every slot.
    static func absentSeries(id: String, name: String, shape: FieldHistoryShape10868, tint: Color,
                             words: String) -> FieldHistorySeries10868 {
        FieldHistorySeries10868(id: id, name: name, shape: shape, tint: tint, runs: [], links: [],
                                labelPointID: nil, before: .absent(words: words), recorded: .absent(words: words),
                                absentWords: words, choose: nil)
    }

    /// Nothing to draw, in the owner's words: no point, axis or guide is offered
    /// under it, and the domain is a placeholder the leaf never draws under an
    /// absence.
    static func emptyInput(phase: SoccerEventPagePhase10868, series: [FieldHistorySeries10868], notes: [String],
                           summary: String, plot: FieldHistoryPlotAbsence10868,
                           readoutLabel: String = Words.preMatch,
                           unbound: String = Words.notRecorded) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: Words.title,
            caption: phase == .before ? Words.beforeCaption : Words.gameCaption,
            series: series,
            selection: .none,
            domain: FieldHistoryDomain10868(lower: 0, upper: 1),
            ceiling: 1, yTicks: [], xTicks: [], guides: [], breaks: [],
            readout: .singleBefore(label: readoutLabel),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: nil),
            comparisonExplanation: nil,
            notes: notes,
            summary: summary,
            plotHeight: H.plotHeight,
            unboundReadingWords: unbound,
            plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil,
            details: H.action(H.detailsActionID, H.Words.details, available: false),
            expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil,
            plotAbsence: plot)
    }
}
