import Foundation

/// The ONE time window both stacked event-page charts are drawn in (#1833, #8481).
///
/// Lifted out of `EventDetailView.sharedChartDomain` so the window can be
/// computed — and tested — as a function of the page's inputs, the reader's
/// All / Since Start choice among them.
///
/// #8481 — THE CHOICE WAS NOT AN INPUT. Alex's installed TestFlight 1.0.1(20)
/// recording of Brewers @ Phillies (15318131), 2026-09-24 ~3:50 PM PDT, 45
/// minutes in: tapping All drew the green Win Probability line out through the
/// y-axis and gutter toward the screen edge, while the axis still opened at
/// 3:05 PM. The range lived privately in the probability chart's view model;
/// this window ignored it and always opened at first pitch, so the chart drew
/// its pre-game points LEFT of its own domain, and the Score Differential chart
/// below never heard the choice at all. Alex, same day: exactly ONE All / Since
/// Start control, above Win Probability, governs BOTH charts.
///
/// So the page holds the choice, this window reads it, and both charts are
/// handed the same window and cut their ink to it.
enum SharedChartWindow {

    /// How far before the scheduled start an axis may open. It is two numbers
    /// that must agree, so it is one constant:
    ///   * the warm-up margin — a real early start is minutes, not hours, so an
    ///     ESPN row earlier than this belongs to a previous game (#1833);
    ///   * the All window's floor — the web's rule (`computeSharedChartDomain`,
    ///     L2-163 item 2c): once a game is under way, All shows the run-up, not
    ///     three days of flat pre-game drift squeezing the game into a sliver.
    static let preStartMargin: TimeInterval = 2 * 60 * 60

    /// The shared domain, or `nil` when each chart should take its own from what
    /// it drew (not started, no trustworthy start, nothing to anchor an end on).
    static func domain(
        status: String?,
        commenceTime: String?,
        history: EventHistoryResponse?,
        range: OddsTimeRange,
        now: Date = Date()
    ) -> ClosedRange<Date>? {
        guard let scheduledStart = commenceTime?.asDate else { return nil }
        // #7878 D — a stored start the payload says is NOT a start (Kalshi's
        // expected resolution hour, `commence_time_is_kickoff: false`) cannot
        // open the axis either. It is the far end of the match: an axis from
        // there puts the whole contest off the left edge however the chart
        // filters its points. `nil` is the existing fallback — each chart
        // takes its own domain from what it drew.
        guard OddsChartView.sinceStartCut(
            commenceTime: scheduledStart,
            commenceTimeIsKickoff: history?.commenceTimeIsKickoff
        ) != nil else { return nil }

        // Use actual game start (first ESPN data point) instead of scheduled
        // time — a game that starts early/late should anchor to when it really
        // began, not when it was listed.
        //
        // #1833: but `min()` here is unbounded backwards, and in-game rows from
        // the PREVIOUS NIGHT'S game were landing on this event. On Alex's
        // 2026-08-13 Sox–Jays specimen the earliest period-bearing ESPN row was
        // 2026-08-12T23:34, so this opened the x-axis ~20 hours before first
        // pitch: a 22-hour domain for a 2.5-hour game, which is what reduced the
        // time labels to unreadable soup on a phone.
        //
        // The backend now filters those rows (app/utils/game_window.py), but a
        // chart domain must not depend on upstream cleanliness to stay legible.
        // A real early start is minutes, not hours — so accept an earlier anchor
        // only within a warm-up margin and otherwise trust the schedule.
        let earliestPlausibleStart = scheduledStart.addingTimeInterval(-preStartMargin)
        let actualStart: Date
        if let espn = history?.espnHistory,
           let firstEspn = espn.first(where: { $0.period != nil && !($0.period?.isEmpty ?? true) }),
           let espnDate = firstEspn.timestamp.asDate {
            let candidate = min(scheduledStart, espnDate.addingTimeInterval(-60))
            actualStart = max(candidate, earliestPlausibleStart)
        } else {
            actualStart = scheduledStart
        }

        // #8481 — All opens at the first reading, but never earlier than the
        // margin. Never LATER than the game's own start either: All is a
        // superset of Since Start, so it can only widen the window.
        let start: Date
        switch range {
        case .sinceStart:
            start = actualStart
        case .all:
            let firstReading = earliestReading(in: history) ?? actualStart
            start = min(actualStart, max(firstReading, earliestPlausibleStart))
        }

        // Build a domain only when the upper bound is at/after the lower bound.
        // A market-less / aged-out closed game can have history whose only points
        // predate the scheduled start (pre-game odds snapshot, no in-game data);
        // a "stuck live" event can have a future start. Either yields an inverted
        // ClosedRange, and `lower...upper` TRAPS when lower > upper — the crash on
        // tapping a market-less card (#1092). Return nil in that case so the child
        // charts compute their own safe domain from their data points.
        func domain(upTo end: Date) -> ClosedRange<Date>? {
            let upper = end.addingTimeInterval(30)
            return upper >= start ? start...upper : nil
        }

        // For completed games: use last game data point, NOT completedAt
        // (completedAt is a backend processing timestamp, often 30-45 min after game end)
        if EventState.isFinished(status) {
            let lastEspn = history?.espnHistory?.last?.timestamp.asDate
            let lastOdds = history?.history.last?.timestamp.asDate
            if let gameEnd = [lastEspn, lastOdds].compactMap({ $0 }).max(),
               let range = domain(upTo: gameEnd) {
                return range
            }
            // Fallback to completedAt only if no game data
            if let ca = history?.completedAt, let end = ca.asDate,
               let range = domain(upTo: end) {
                return range
            }
            return nil
        }
        if status == "live" {
            let upper = now.addingTimeInterval(60)
            return upper >= start ? start...upper : nil
        }
        return nil
    }

    /// The earliest timestamp on any series the probability chart can draw from.
    static func earliestReading(in history: EventHistoryResponse?) -> Date? {
        guard let history else { return nil }
        var stamps: [String] = history.history.map(\.timestamp)
        stamps += history.aggregateLine?.map(\.timestamp) ?? []
        stamps += history.espnHistory?.map(\.timestamp) ?? []
        for points in (history.winProbHistory ?? [:]).values {
            stamps += points.map(\.timestamp)
        }
        for points in (history.bookmakerHistory ?? [:]).values {
            stamps += points.map(\.timestamp)
        }
        return stamps.compactMap(\.asDate).min()
    }

    /// Whether a point may be drawn in a chart handed `domain`. A chart's scale
    /// does not clip its marks, so a point outside its own domain is drawn
    /// outside its own plot — through the axis, into the gutter (#8481).
    static func contains(_ date: Date, in domain: ClosedRange<Date>?) -> Bool {
        guard let domain else { return true }
        return domain.contains(date)
    }
}
