import Foundation

/// #8509 — when each period was first seen in `win_prob_history`, the same on
/// every open.
///
/// `win_prob_history` is a Swift `Dictionary` keyed by source, and both charts
/// used to walk it with `for (_, points) in …` and let the FIRST SOURCE ITERATED
/// claim each label. Dictionary order is not stable between two decodes of the
/// same bytes, so one open of Mets @ Rangers (15318166) drew 1st · 2nd · 3rd ·
/// 5th … with no 4th and another open drew the 4th and moved the 9th: whichever
/// source came first placed the chip, and a chip placed a few minutes over lets
/// the chart's spacing rule drop a neighbour.
///
/// The rule now: a label is placed at the EARLIEST time ANY source saw it,
/// which is what "first seen" says, with ties going to the alphabetically first
/// source. Nothing about it depends on iteration order.
enum WinProbPeriodSightings {
    struct Sighting: Equatable {
        let label: String
        let date: Date
        /// The previous period-bearing reading in the SAME source: the period
        /// began after it (#3348 `notBefore`). Nil for a source's first reading.
        let notBefore: Date?
    }

    /// The earliest sighting of every label, ordered by time (then label).
    ///
    /// `admits` filters readings by time before anything else (the score chart
    /// keeps only its game window), so `notBefore` is also taken from the
    /// readings it admits.
    static func earliest(
        in history: [String: [WinProbHistoryPoint]]?,
        sportKey: String?,
        admits: (Date) -> Bool = { _ in true }
    ) -> [Sighting] {
        var best: [String: Sighting] = [:]
        for source in (history ?? [:]).keys.sorted() {
            let readings = (history?[source] ?? [])
                .compactMap { point -> (period: String, date: Date)? in
                    guard let gs = point.gameState, let date = point.timestamp.asDate else { return nil }
                    guard admits(date) else { return nil }
                    if let period = gs.period, !period.isEmpty { return (period, date) }
                    if let inning = gs.inning, inning > 0 { return ("Top \(inning)", date) }
                    return nil
                }
                .sorted { $0.date < $1.date }

            var previous: Date?
            for reading in readings {
                let label = PeriodLabel.normalize(reading.period, sport: sportKey)
                if !label.isEmpty, best[label].map({ reading.date < $0.date }) ?? true {
                    best[label] = Sighting(label: label, date: reading.date, notBefore: previous)
                }
                previous = reading.date
            }
        }
        return best.values.sorted { ($0.date, $0.label) < ($1.date, $1.label) }
    }
}
