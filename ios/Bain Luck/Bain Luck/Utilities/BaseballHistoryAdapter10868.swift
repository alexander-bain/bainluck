import SwiftUI

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER, PART TWO: THE
/// TWO-TEAM WIN-PROBABILITY HISTORY.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on an MLB event page the history under
/// the matrix draws only what was recorded — the last pregame reading, then
/// the game — leaves every unrecorded stretch blank, never draws a settlement
/// or a line run on to now, and says the away side of the two-outcome blend is
/// that blend's other side.
///
/// It builds `FieldHistoryInput10868` from the decoded `/api/events/{id}/history`
/// body (`EventHistoryResponse`), the event, the page phase and the reader's
/// clock by CALLING the accepted two-team history adapter (H2,
/// `HockeyJourneyHistoryAdapter10868.history`), so the hockey and baseball
/// screens read one served history the same way. Every row rule is H2's:
///
///   - which line       `OddsChartView.primarySource`: the backend blend
///                      (`aggregate_line`) where served, else the consensus.
///   - the two series   home as served; away as served, else the blend row's
///                      own two-outcome complement through
///                      `DrawPricedWinner.printablePair` — kept on baseball,
///                      whose winner market prices no draw — with H2's note that
///                      it is the other side of the same blend.
///   - removals         the settlement row a finished game appends last, the
///                      blend's pinned edge (`blendEdgePinned`) and carried-
///                      forward minutes; a finished game's rows are clipped at
///                      `OddsChartView.gameEndDate`.
///   - breaks           `OddsChartView.observationSegments` inside each stretch
///                      between unreadable rows; never a line across an unknown
///                      span.
///   - pregame split    `OddsChartView.sinceStartCut`, refused under
///                      `startIsTbd`: no confirmed start draws one unsplit
///                      history with no last pregame reading or guide.
///   - guides           `OddsChartView.periodSightings` admitted by
///                      `PeriodLabel.columnLabel` — on baseball the innings
///                      ("1st", "2nd", …) — and the served scoring plays.
///   - axes, words      H2's ticks, frame, readouts and source note.
///
/// What is baseball's own: only the expand control's spoken words ("Expand
/// baseball win probability history"); every other field is H2's, unchanged.
///
/// Where the in-game frame opens stays H2's host parameter (default: the last
/// pregame row). The host's held inspection, the window and scale controls and
/// the live preview overlay are not built here (nil), and Details and Inspect
/// stay unavailable until their owner contracts exist — the H2 obligations,
/// kept.
///
/// Nothing here fetches, subscribes, schedules or holds state.
enum BaseballHistoryAdapter10868 {
    typealias H = HockeyJourneyHistoryAdapter10868
    /// H2's host: now and the reader's calendar, time zone and locale.
    typealias Host = HockeyJourneyHistoryAdapter10868.Host

    enum Words {
        static let expandSpoken = "Expand baseball win probability history"
    }

    // MARK: - The history

    static func history(_ response: EventHistoryResponse, event: EventDetail,
                        phase: BaseballEventPagePhase10868, host: Host) -> FieldHistoryInput10868 {
        let drawn = H.history(response, event: event, phase: h2Phase(phase), host: host)
        return withExpand(drawn, drawn.expand.map {
            H.action($0.id, $0.label, spoken: Words.expandSpoken, available: $0.isAvailable)
        })
    }

    /// No history response at all — not arrived yet, or failed; the host does
    /// not say which, so neither is claimed. H2's "History unavailable" through
    /// the plot-absence channel, with no working control. The rest of the page
    /// composes from its own inputs.
    static func unavailable(event: EventDetail, phase: BaseballEventPagePhase10868) -> FieldHistoryInput10868 {
        H.unavailable(event: event, phase: h2Phase(phase))
    }

    // MARK: - Parts

    /// H2's own phase for its row rules; the three phases are the same three.
    static func h2Phase(_ phase: BaseballEventPagePhase10868) -> HockeyJourneyPagePhase10868 {
        switch phase {
        case .before: .before
        case .live: .live
        case .final: .final
        }
    }

    /// The same input with only its expand control replaced.
    static func withExpand(_ input: FieldHistoryInput10868,
                           _ expand: FieldHistoryAction10868?) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: input.title, caption: input.caption, series: input.series,
            selection: input.selection, domain: input.domain, ceiling: input.ceiling,
            yTicks: input.yTicks, xTicks: input.xTicks, guides: input.guides, breaks: input.breaks,
            readout: input.readout, markKey: input.markKey,
            comparisonExplanation: input.comparisonExplanation, notes: input.notes,
            summary: input.summary, plotHeight: input.plotHeight,
            unboundReadingWords: input.unboundReadingWords, plotUnavailableWords: input.plotUnavailableWords,
            windows: input.windows, scale: input.scale, moreOriginals: input.moreOriginals,
            details: input.details, expand: expand, inspect: input.inspect,
            previous: input.previous, next: input.next, inspection: input.inspection,
            layout: input.layout,
            probabilityLowerBound: input.probabilityLowerBound,
            probabilityRangeExplanation: input.probabilityRangeExplanation,
            selectedReadout: input.selectedReadout, inspectionRingShape: input.inspectionRingShape,
            plotAbsence: input.plotAbsence, showsKey: input.showsKey
        )
    }
}
