import Foundation

// MARK: - #683 a recorded interval is never drawn as a live reading
//
// The archive store (calibration, PR #11083) gives a settled Kalshi question the
// price journey our polls never captured. Each of those prices is a candle from
// Kalshi's own record: one hour (or one minute) of trading, served at the
// candle's CLOSE with `interval_start`, `period_minutes`, `price_basis` and
// `provenance: kalshi_archive`. Decoded as an ordinary point it reads as a price
// we watched at that instant, which it is not. The payload's metadata is not the
// reader's: this file turns it into the two things a reader actually sees — one
// short line under the chart, and the interval in the scrub readout.
//
// Nothing here moves, smooths or hides a point. A mark that is present but
// unreadable still labels its value as recorded, never as live.

nonisolated enum EvolutionArchiveProvenance {
    static let kalshiArchive = "kalshi_archive"
    static let tradedInterval = "traded_interval"
    static let quoteOnly = "quote_only"

    /// The marks of the values the chart draws: the lines in `names`, the entries
    /// at or after `cutoff`. `values` counts every drawn value, archived or not.
    static func drawnMarks(
        in timeline: [TimelineEntry], names: Set<String>, cutoff: Date?
    ) -> (marks: [TimelineArchiveMark], values: Int) {
        var marks: [TimelineArchiveMark] = []
        var values = 0
        for entry in timeline {
            guard let date = entry.timestamp.asDate else { continue }
            if let cutoff, date < cutoff { continue }
            for name in entry.outcomes.keys where names.contains(name) {
                values += 1
                if let mark = entry.archive?[name] { marks.append(mark) }
            }
        }
        return (marks, values)
    }

    /// The one line under the chart, or nil when nothing drawn is archived.
    ///
    /// Says whose record, at what grain and on what basis — only as far as the
    /// marks agree. A word the marks do not all support is left out rather than
    /// guessed: mixed grains drop "hourly", an unreadable basis drops "trades".
    static func note(marks: [TimelineArchiveMark], drawnValues: Int) -> String? {
        guard !marks.isEmpty else { return nil }
        let lead = marks.count >= drawnValues ? "These prices are" : "Some prices here are"
        let grain = grainWord(marks.map(\.periodMinutes)).map { "\($0) " } ?? ""
        let record: String
        switch basis(marks.map(\.priceBasis)) {
        case .traded: record = "\(grain)record of trades"
        case .quoted: record = "\(grain)record of quotes (no trades)"
        case .mixed: record = "\(grain)record of trades and quotes"
        case .unknown: record = grain.isEmpty ? "record" : "\(grain)record"
        }
        return "\(lead) from \(owner(marks)) \(record), not live readings."
    }

    /// The scrub readout's line for an instant that holds archived values, or nil.
    static func readoutLine(marks: [TimelineArchiveMark]) -> String? {
        guard !marks.isEmpty else { return nil }
        let source = "From \(owner(marks)) record"
        switch basis(marks.map(\.priceBasis)) {
        case .traded: return "\(source) · traded"
        case .quoted: return "\(source) · quote, no trades"
        case .mixed, .unknown: return source
        }
    }

    /// The interval an archived instant stands for, `start...close`, when every
    /// mark at that instant names the same readable start. Nil otherwise: the
    /// readout then prints the close as it prints any instant.
    static func interval(closingAt close: Date, marks: [TimelineArchiveMark]) -> ClosedRange<Date>? {
        let starts = Set(marks.map(\.intervalStart))
        guard starts.count == 1, let stamp = starts.first ?? nil,
              let start = stamp.asDate, start < close else { return nil }
        return start...close
    }

    // MARK: - Words

    enum Basis: Equatable { case traded, quoted, mixed, unknown }

    static func basis(_ values: [String?]) -> Basis {
        let set = Set(values)
        if set == [tradedInterval] { return .traded }
        if set == [quoteOnly] { return .quoted }
        if set == [tradedInterval, quoteOnly] { return .mixed }
        return .unknown
    }

    static func grainWord(_ periods: [Int?]) -> String? {
        switch Set(periods) {
        case [60]: return "hourly"
        case [1]: return "minute-by-minute"
        default: return nil
        }
    }

    /// "Kalshi's" only when every mark says the record is Kalshi's.
    private static func owner(_ marks: [TimelineArchiveMark]) -> String {
        marks.allSatisfy { $0.provenance == kalshiArchive } ? "Kalshi's" : "the market's"
    }
}
