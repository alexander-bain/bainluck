import SwiftUI

/// #10868 — THE FOOTBALL SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE TWO-TEAM
/// WIN-PROBABILITY HISTORY.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on every NFL route the history under the
/// comparison draws only what was recorded — the last pregame reading, then the
/// game — leaves every unrecorded stretch blank, never runs a settlement or a
/// pinned edge on as a reading, and says the away line is the other side of the
/// same blend.
///
/// Football is two-outcome, exactly the history the accepted hockey adapter
/// (H2, `HockeyJourneyHistoryAdapter10868`) builds: the chart's own primary line
/// (`OddsChartView.primarySource`), its observation breaks
/// (`OddsChartView.observationSegments`), the settlement row / pinned edge /
/// carried minutes removed, the pregame split at a confirmed kickoff
/// (`OddsChartView.sinceStartCut`, refused under `startIsTbd`, an unconfirmed
/// start drawing one unsplit history with no pregame baseline), the period and
/// scoring-play guides (`OddsChartView.periodSightings` + `PeriodLabel.columnLabel`,
/// `ExpandedRecordedMatchMoment9483.play`), the axes and every word. The away
/// line on the blend is the documented `1 − home` of the same row through
/// `DrawPricedWinner.printablePair` — the rule `PairedWinLines9483` draws the
/// NFL page's paired journey by. So this file CALLS H2 and changes one thing:
/// the full-chart control's spoken name says football, not hockey.
///
/// Where the live frame opens is H2's host parameter (`inGameStart`, default the
/// last pregame row). The held inspection, window/scale controls and the live
/// preview overlay are not built (H2's nil), and Details and Inspect stay offered
/// unavailable until their owner contracts exist. Nothing here fetches.
enum FootballHistoryAdapter10868 {
    typealias H2 = HockeyJourneyHistoryAdapter10868
    typealias Host = HockeyJourneyHistoryAdapter10868.Host

    enum Words {
        static let expandSpoken = "Expand football probability history"
    }

    static func history(_ response: EventHistoryResponse, event: EventDetail,
                        phase: FootballEventPagePhase10868, host: Host,
                        inGameStart: H2.InGameStart = .lastPregameRow) -> FieldHistoryInput10868 {
        let built = H2.history(response, event: event, phase: FootballEventPageAdapter10868.hockeyPhase(phase),
                               host: host, inGameStart: inGameStart)
        return footballWorded(built)
    }

    /// No history response at all (not arrived, or failed): H2's honest
    /// "History unavailable" slot, no source named, no working control.
    static func unavailable(event: EventDetail, phase: FootballEventPagePhase10868) -> FieldHistoryInput10868 {
        H2.unavailable(event: event, phase: FootballEventPageAdapter10868.hockeyPhase(phase))
    }

    /// H2's input with the full-chart control's spoken name in football's words.
    /// Every other field is H2's, unchanged; an absent control stays absent.
    static func footballWorded(_ h: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        let expand = h.expand.map {
            FieldHistoryAction10868(id: $0.id, label: $0.label, spokenLabel: Words.expandSpoken,
                                    isAvailable: $0.isAvailable)
        }
        return FieldHistoryInput10868(
            title: h.title, caption: h.caption, series: h.series,
            selection: h.selection, domain: h.domain, ceiling: h.ceiling,
            yTicks: h.yTicks, xTicks: h.xTicks, guides: h.guides, breaks: h.breaks,
            readout: h.readout, markKey: h.markKey,
            comparisonExplanation: h.comparisonExplanation, notes: h.notes,
            summary: h.summary, plotHeight: h.plotHeight,
            unboundReadingWords: h.unboundReadingWords, plotUnavailableWords: h.plotUnavailableWords,
            windows: h.windows, scale: h.scale, moreOriginals: h.moreOriginals,
            details: h.details, expand: expand, inspect: h.inspect,
            previous: h.previous, next: h.next, inspection: h.inspection,
            layout: h.layout,
            probabilityLowerBound: h.probabilityLowerBound,
            probabilityRangeExplanation: h.probabilityRangeExplanation,
            selectedReadout: h.selectedReadout, inspectionRingShape: h.inspectionRingShape,
            plotAbsence: h.plotAbsence, showsKey: h.showsKey)
    }
}
