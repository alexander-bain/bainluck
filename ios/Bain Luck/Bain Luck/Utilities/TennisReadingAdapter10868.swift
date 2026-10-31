import SwiftUI

/// #10868 — THE TENNIS MATCH SCREEN'S PRODUCTION ADAPTER, PART THREE: THE DATED
/// READING BESIDE THE HISTORY.
///
/// PILLARS: TRUTH / FORMATTING. SHIP: on a tennis event page a reader who taps
/// the history holds one recorded chance at its own time, beside the last
/// reading before the scheduled start; a tap inside a break holds the break and
/// borrows no neighbour; the full-size history always shows a dated reading
/// (the latest until one is held); and "Show latest recorded chance" is offered
/// only where it changes what is shown.
///
/// Every decision is the production tennis panel's (`TennisChartReading9483`,
/// `TennisReadingPanel9483`, `TennisReadingPin9483`) or the chart's, called, not
/// copied:
///
///   - what it reads  EXACTLY the vertices AND runs the history draws for the
///                    home player (part two's row machinery,
///                    `HockeyJourneyHistoryAdapter10868.drawn`, called with the
///                    arguments `TennisHistoryAdapter10868.history` passes): the
///                    history's line (`Rows.line`, which is the chart's
///                    `readoutSource` — the primary line whenever it is drawn),
///                    without the settlement row (`Rows.settlementIndex`, the
///                    ONE result-row rule, applied once), the blend's pinned edge
///                    and the carried-forward minutes; each run broken where the
///                    chart breaks it — at an unreadable, non-advancing or
///                    value-missing row, and by `OddsChartView.observationSegments`
///                    inside each stretch; cut at the page phase (`Rows.drawn`'s
///                    own start and stop: before play the day ending at its
///                    last reading before the scheduled start; during and after,
///                    that last reading, then the match up to now or the match's
///                    end, `OddsChartView.gameEndDate`). So the panel can never
///                    hold a point the chart beside it refuses to draw, never
///                    loses one it draws, and never reads across a break it keeps.
///   - the series     `TennisChartReading9483.Series` built from those vertices
///                    (`points`) and those runs (`segments`), through its own
///                    initializer. `TennisChartReading9483.series(…)` is NOT
///                    called: its finished-match rule would drop a second
///                    terminal 0 or 1 from rows the settlement rule already
///                    cleaned, and it would rebuild breaks from elapsed time
///                    alone. Its reading, baseline, latest, inspection, held
///                    identity and away contract (the blend's away side is its
///                    complement, printed and never looked up; the consensus
///                    supplies its own) are the Series' own, unchanged.
///   - whose body     only this event's (`TennisHistoryAdapter10868.admitted`):
///                    another event's response yields no point, no series and so
///                    no baseline, held or latest reading.
///   - JUDGMENT,      today's production chart feeds the panel its enriched
///     reported       points with no live frames, which keep the pinned edge and
///                    the carried minute; on 15327807 that offers 12:24:00Z (40%,
///                    Kalshi's carried live edge folded into the blend) and
///                    12:24:06Z (the hero's own value at read time) as "Recorded
///                    chance". Owner: Native (#9483 tennis panel); not changed here.
///   - the cut        the history's own (`Rows.kickoff`): `OddsChartView.sinceStartCut`,
///                    refused when `startIsTbd`, so an unconfirmed start has no
///                    baseline, exactly as the history draws it unsplit.
///   - a tap          `Series.inspect(at:)` at the plotted position.
///   - shown          `Series.resolve(held)`.
///   - Show latest    the panel's private rule, restated here because it is
///                    private: nothing held, no offer; a held reading, offered
///                    only when it is not the latest; a held break or a reading
///                    that is gone, offered when a latest exists. Choosing it
///                    holds the latest (`TennisReadingPin9483.holdLatest`).
///   - opening full   holds what it shows (`TennisReadingPin9483.holdShown`), so
///     size           neither a later arrival nor the return moves the reading.
///
/// Nothing here fetches, stores or schedules: the host keeps the held value as
/// page-local state and recomputes this from it on every pass.
enum TennisReadingAdapter10868 {
    typealias Rows = HockeyJourneyHistoryAdapter10868
    typealias Series = TennisChartReading9483.Series
    typealias Held = TennisChartReading9483.Held

    // MARK: - The series

    /// The home player's trace exactly as the history draws it: the same rows,
    /// removals, phase cut, frame end and breaks, through the same call
    /// `TennisHistoryAdapter10868.history` makes. Nil for another event's body.
    static func drawn(_ response: EventHistoryResponse, event: EventDetail, now: Date) -> Rows.Drawn? {
        guard let response = TennisHistoryAdapter10868.admitted(response, for: event) else { return nil }
        let line = Rows.line(response)
        let phase = TennisMatchPageAdapter10868.phase(event, now: now)
        let entries = Rows.entries(Rows.servedRows(response, line: line, sport: event.sport),
                                   removing: Rows.removedIndexes(response, event: event, line: line))
        let end: Date = phase == .final
            ? min(OddsChartView.gameEndDate(status: event.status, history: response) ?? now, now)
            : now
        return Rows.drawn(entries, side: .home, phase: TennisHistoryAdapter10868.rowPhase(phase),
                          kickoff: Rows.kickoff(response, event: event), gapStart: event.commenceTime?.asDate,
                          end: end, now: now, opening: nil, line: line)
    }

    /// The drawn runs as chart points on the history's line, run by run, in
    /// time order. Two runs are never joined. Another event's body has none.
    static func runs(_ response: EventHistoryResponse, event: EventDetail, now: Date) -> [[ChartDataPoint]] {
        guard let response = TennisHistoryAdapter10868.admitted(response, for: event),
              let drawn = drawn(response, event: event, now: now) else { return [] }
        let source = Rows.line(response).rawValue
        return drawn.runs.map { run in
            run.map { ChartDataPoint(date: $0.date, probability: $0.value, source: source) }
        }
    }

    /// Every drawn reading, oldest first — the runs, end to end.
    static func points(_ response: EventHistoryResponse, event: EventDetail, now: Date) -> [ChartDataPoint] {
        runs(response, event: event, now: now).flatMap { $0 }
    }

    /// The production tennis series over exactly the drawn readings and runs,
    /// or nil with none. The scheduled start is the history's own cut
    /// (`Rows.kickoff`); the history response is where a consensus reading's
    /// own away side is looked up.
    static func series(_ response: EventHistoryResponse, event: EventDetail, now: Date) -> Series? {
        // Another event's body yields no series, so no baseline, held or latest reading.
        guard let response = TennisHistoryAdapter10868.admitted(response, for: event) else { return nil }
        let segments = runs(response, event: event, now: now)
        let points = segments.flatMap { $0 }
        guard !points.isEmpty else { return nil }
        return Series(eventId: response.eventId, source: Rows.line(response).rawValue, points: points,
                      segments: segments, scheduledStart: Rows.kickoff(response, event: event),
                      history: response)
    }

    // MARK: - Holding

    /// A tap on the history at a plotted position (seconds since 1970).
    static func inspect(_ position: Double, in series: Series) -> Held? {
        series.inspect(at: Date(timeIntervalSince1970: position))
    }

    /// "Show latest recorded chance": the newest observation, held like any other.
    static func latest(in series: Series) -> Held? {
        series.latest.map { .reading($0) }
    }

    /// Opening the full-size history holds what it shows; a held value stays.
    static func opening(_ held: Held?, in series: Series) -> Held? {
        guard held == nil, case .reading(let reading, held: false) = series.resolve(nil) else { return held }
        return .reading(reading)
    }

    /// The production panel's offer rule (`TennisReadingPanel9483.offersLatest`).
    static func offersLatest(_ held: Held?, in series: Series) -> Bool {
        guard held != nil else { return false }
        if case .reading(let reading, _) = series.resolve(held) { return reading != series.latest }
        return series.latest != nil
    }

    // MARK: - The reading

    /// The composed screen's reading: what the series shows for `held`, its
    /// baseline, and the players in the headline's compact names and tints.
    static func reading(_ series: Series, held: Held?, event: EventDetail, now: Date) -> TennisEventPageReading10868 {
        let players = TennisMatchPageAdapter10868.players(event)
        let tints = TennisMatchPageAdapter10868.tints(event)
        return TennisEventPageReading10868(
            shown: series.resolve(held), baseline: series.baseline, scheduledStart: series.scheduledStart,
            homeName: players[0].shortName, awayName: players[1].shortName,
            homeTint: tints.home, awayTint: tints.away,
            offersLatest: offersLatest(held, in: series), now: now)
    }
}
