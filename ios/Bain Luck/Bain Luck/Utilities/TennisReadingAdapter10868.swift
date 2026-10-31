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
/// `TennisReadingPanel9483`, `TennisReadingPin9483`), called, not copied:
///
///   - the series     `TennisChartReading9483.series` — its own sort, its own
///                    breaks (`OddsChartView.observationSegments`), its own
///                    finished-match result-row rule, its own away contract
///                    (the blend's away side is its complement, printed and never
///                    looked up; the consensus supplies its own).
///   - what it reads  EXACTLY the rows the history draws as readings (part two's
///                    row machinery, `HockeyJourneyHistoryAdapter10868`): the
///                    history's line (`Rows.line`, which is the chart's
///                    `readoutSource` — the primary line whenever it is drawn),
///                    without the settlement, the blend's pinned edge and the
///                    carried-forward minutes, clipped at the match's end
///                    (`OddsChartView.gameEndDate`) and at now. So the panel can
///                    never hold a point the chart beside it refuses to draw.
///                    JUDGMENT, reported: today's production chart feeds the
///                    panel its enriched points with no live frames, which keep
///                    the pinned edge and the carried minute; on 15327807 that
///                    offers 12:24:00Z (40%, Kalshi's carried live edge folded
///                    into the blend) and 12:24:06Z (the hero's own value at read
///                    time) as "Recorded chance". Owner: Native (#9483 tennis
///                    panel); not changed here.
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

    /// The history's readings as chart points, in served order.
    static func points(_ response: EventHistoryResponse, event: EventDetail, now: Date) -> [ChartDataPoint] {
        let line = Rows.line(response)
        let entries = Rows.entries(Rows.servedRows(response, line: line, sport: event.sport),
                                   removing: Rows.removedIndexes(response, event: event, line: line))
        let limit: Date = EventState.isFinished(event.status)
            ? min(OddsChartView.gameEndDate(status: event.status, history: response) ?? now, now)
            : now
        return entries.compactMap { entry -> ChartDataPoint? in
            guard let date = entry.date, date <= limit, let home = Rows.value(entry.row, .home) else { return nil }
            return ChartDataPoint(date: date, probability: home, source: line.rawValue)
        }
    }

    /// The production tennis series over those readings, or nil with none.
    static func series(_ response: EventHistoryResponse, event: EventDetail, now: Date) -> Series? {
        let line = Rows.line(response)
        return TennisChartReading9483.series(
            eventId: response.eventId, points: points(response, event: event, now: now),
            source: line.rawValue, scheduledStart: Rows.kickoff(response, event: event),
            gameStart: event.commenceTime?.asDate, finished: EventState.isFinished(event.status),
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
