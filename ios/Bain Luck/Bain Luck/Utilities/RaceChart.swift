import Foundation

// MARK: - The RACE chart contract (#2911), ported to the phone
//
// #2911 names three chart primitives and asks for one contract behind all of
// them: MATCH (two-party win probability over time), RACE (multi-participant
// probability over time), OUTCOME BARS (the non-time form). This file is the
// RACE primitive's pure half — the arithmetic, the windows and the axis rules,
// with no SwiftUI in it so every rule below can be unit-tested. The drawing
// lives in `Components/RaceChartView.swift`.
//
// It is a PORT, not an invention: `frontend/lib/contenderChart.ts` is the
// contract of record and every rule here has its counterpart there, named in
// the comment. Where the two differ the web is right and this file is a bug.
//
// The doctrine the web module states, restated because it is the whole point:
//
//   - **No smoothing, ever.** Straight segments between real observations.
//     Movement IS the product and a smoother is a machine for hiding it.
//   - **Gaps stay gaps.** A day with no reading is absent — never interpolated,
//     never carried forward.
//   - **Zero stays; the top moves.** The y-axis is always anchored at 0, so a
//     contender at 9% is drawn at 9% of the ceiling. What adapts is the
//     CEILING, in four coarse steps, and only because it is labelled.
//
// Every probability here is a 0–1 FRACTION and a missing price is `nil`, never
// 0 — the same rule the hub models carry.

// MARK: - Points and series

/// One daily reading off the hub payload's per-row `trend` array.
nonisolated struct RaceChartPoint: Equatable, Sendable {
    /// `YYYY-MM-DD`. Kept as the payload's string, not a `Date`: the series is a
    /// series of DAYS, and parsing would reintroduce the midnight-UTC question
    /// that day arithmetic exists to keep out of this module.
    let date: String
    let probability: Double
}

/// One contender's line.
nonisolated struct RaceChartSeries: Equatable, Sendable, Identifiable {
    let entityKey: String
    let displayName: String
    /// Position in the drawn set, which is what picks the colour. Colours live
    /// in the view; an index keeps this file free of SwiftUI and testable.
    let colorIndex: Int
    /// The board's current blended number. Nullable — a contender with no price.
    let probability: Double?
    let points: [RaceChartPoint]

    var id: String { entityKey }
}

// MARK: - Ranges

/// A range is either a WINDOW (a date, meaning something) or a TIMEFRAME (a
/// duration, meaning a length). `contenderChart.ts`'s `ChartRange`.
nonisolated enum RaceChartRange: String, Equatable, Sendable, CaseIterable {
    /// Since the main draw began. The default where it can be drawn.
    case draw
    /// Since qualifying began.
    case qual
    case day
    case week
    case month
    case all

    /// Chip text. Short — six of these share one row on a phone.
    var label: String {
        switch self {
        case .draw: return "Draw"
        case .qual: return "Quals"
        case .day: return "1D"
        case .week: return "1W"
        case .month: return "1M"
        case .all: return "ALL"
        }
    }

    var isWindow: Bool { self == .draw || self == .qual }

    /// How many trailing days a duration covers. `nil` means "everything".
    var days: Int? {
        switch self {
        case .day: return 1
        case .week: return 7
        case .month: return 30
        case .draw, .qual, .all: return nil
        }
    }
}

/// Where each window starts, as `YYYY-MM-DD`, or `nil` for "we cannot say".
nonisolated struct RaceChartWindowStarts: Equatable, Sendable {
    let draw: String?
    let qual: String?

    /// Neither window can be dated. Not spelled `none`: a static `none` on a
    /// struct is the one name Swift will happily resolve to `Optional.none` in
    /// a context that takes an optional, and this value's whole job is to be
    /// the non-optional "we cannot say".
    static let undated = RaceChartWindowStarts(draw: nil, qual: nil)

    func start(for range: RaceChartRange) -> String? {
        switch range {
        case .draw: return draw
        case .qual: return qual
        default: return nil
        }
    }
}

// MARK: - The rules

nonisolated enum RaceChart {
    /// How many contenders the legend names and the chart draws.
    /// Alex's Kalshi reference shows exactly three, which settled 3-vs-5.
    static let seriesCount = 3

    /// The ceiling ladder (#2451). Coarse deliberately: a continuous fit-to-max
    /// would rescale the plot every time the leader moved a point, and an axis
    /// that changes daily makes movement unreadable.
    static let ceilingSteps: [Double] = [0.1, 0.25, 0.5, 1.0]

    /// Room above the leader so the top line is not welded to the frame.
    static let ceilingHeadroom = 1.15

    /// ESPN's own word for the rounds played before the draw proper.
    private static let qualifyingRoundPrefix = "qualifying"

    // MARK: Building series

    /// The top N still-standing rows as chart series, in board order.
    ///
    /// Rows without a probability are skipped: a result is not a standing, and
    /// a settled contender has no live line to draw. `chartSeries` on the web.
    static func series(from rows: [TournamentHubBoardRow], limit: Int = seriesCount) -> [RaceChartSeries] {
        rows
            .filter { $0.probability != nil }
            .prefix(limit)
            .enumerated()
            .map { index, row in
                RaceChartSeries(
                    entityKey: row.entityKey,
                    displayName: row.displayName,
                    colorIndex: index,
                    probability: row.probability,
                    points: (row.trend ?? []).compactMap(point)
                )
            }
    }

    private static func point(_ raw: TournamentHubTrendPoint) -> RaceChartPoint? {
        guard let date = raw.date, isoDay(date) != nil,
              let probability = raw.probability, probability.isFinite else { return nil }
        return RaceChartPoint(date: date, probability: probability)
    }

    // MARK: Windowing

    /// The points a range draws.
    ///
    /// A window filters by DATE and a timeframe by DURATION, and the duration is
    /// measured back from the SERIES' LAST READING, not from `now`. Anchoring on
    /// `now` looks more correct and is worse: a field whose prices went dark
    /// three weeks ago would draw blank and read as "no data" when the truth is
    /// "no RECENT data" — which the price-age sentence already says in words.
    static func points(
        _ points: [RaceChartPoint],
        in range: RaceChartRange,
        starts: RaceChartWindowStarts
    ) -> [RaceChartPoint] {
        if range.isWindow {
            guard let start = starts.start(for: range) else { return points }
            // String comparison, deliberately: both sides are `YYYY-MM-DD`,
            // which sorts lexicographically exactly as it sorts chronologically.
            return points.filter { $0.date >= start }
        }
        guard let days = range.days, let last = points.last,
              let end = dayNumber(last.date) else { return points }
        let first = end - (days - 1)
        return points.filter { (dayNumber($0.date) ?? Int.min) >= first }
    }

    /// Whether a range has two readings to join.
    ///
    /// A single point is not a line, and joining it to an assumed origin would
    /// draw a movement that never happened — so the chip is offered disabled
    /// rather than lying.
    static func isDrawable(
        _ series: [RaceChartSeries],
        range: RaceChartRange,
        starts: RaceChartWindowStarts
    ) -> Bool {
        series.contains { points($0.points, in: range, starts: starts).count >= 2 }
    }

    /// The chips, in order: the windows the payload can date, then the durations.
    /// A window with no start is not offered at all — an option that cannot be
    /// honoured is worse than an absent one.
    static func availableRanges(starts: RaceChartWindowStarts) -> [RaceChartRange] {
        var out: [RaceChartRange] = []
        if starts.draw != nil { out.append(.draw) }
        if starts.qual != nil { out.append(.qual) }
        out.append(contentsOf: [.day, .week, .month, .all])
        return out
    }

    /// What the chart opens on: the main draw where it can be drawn, else `ALL`.
    ///
    /// `ALL` is the floor because with a field's prices dark the narrow windows
    /// are the empty ones, and a chart that opens blank on a market with a month
    /// of history is the worse failure. The tournament window has to EARN the
    /// default by having two readings in it.
    static func defaultRange(
        series: [RaceChartSeries],
        starts: RaceChartWindowStarts
    ) -> RaceChartRange {
        if starts.draw != nil, isDrawable(series, range: .draw, starts: starts) { return .draw }
        return .all
    }

    // MARK: The y-axis

    /// The top of the y-axis (#2451). Always anchored at 0; only the top moves,
    /// and only onto one of four steps.
    static func ceiling(
        _ series: [RaceChartSeries],
        range: RaceChartRange,
        starts: RaceChartWindowStarts
    ) -> Double {
        var max = 0.0
        for entry in series {
            for point in points(entry.points, in: range, starts: starts) where point.probability > max {
                max = point.probability
            }
            // The board's current number too: a contender whose history is one
            // reading draws no line, but its legend value is on screen and the
            // axis must be able to contain it.
            if let current = entry.probability, current.isFinite, current > max { max = current }
        }
        let wanted = max * ceilingHeadroom
        return ceilingSteps.first { $0 >= wanted } ?? 1.0
    }

    /// The y-axis labels, top to bottom (#2451).
    ///
    /// Three of them — top, middle, zero — and never more: the plot is ~110pt
    /// tall on a phone and a fourth rule would collide with its neighbours. The
    /// zero line is always drawn because it is the claim the whole scale rests
    /// on. A moving ceiling with no labels would be strictly worse than a fixed
    /// one; the labels are the other half of the fix, not a decoration on it.
    static func yLabels(ceiling: Double) -> [(probability: Double, label: String)] {
        [ceiling, ceiling / 2, 0].map {
            ($0, "\(Int(($0 * 100).rounded()))%")
        }
    }

    // MARK: The x-axis

    /// Every date any drawn series observed, sorted and deduped.
    ///
    /// A union rather than per-series so two contenders' lines line up in time.
    /// Giving each line its own x-scale would put Monday under Thursday and make
    /// crossing lines mean nothing.
    static func domain(
        _ series: [RaceChartSeries],
        range: RaceChartRange,
        starts: RaceChartWindowStarts
    ) -> [String] {
        var seen = Set<String>()
        for entry in series {
            for point in points(entry.points, in: range, starts: starts) { seen.insert(point.date) }
        }
        return seen.sorted()
    }

    /// How long the drawn window actually is, in days — the sentence beside the
    /// ticks. Three dates tell a reader WHERE they are; "30 days" tells them how
    /// much of the story they are looking at, which the chips alone cannot
    /// confirm (`ALL` on a field with four readings is four days, not history).
    static func spanDays(
        _ series: [RaceChartSeries],
        range: RaceChartRange,
        starts: RaceChartWindowStarts
    ) -> Int? {
        let dates = domain(series, range: range, starts: starts)
        guard let first = dates.first.flatMap(dayNumber),
              let last = dates.last.flatMap(dayNumber), dates.count >= 2 else { return nil }
        return Swift.max(0, last - first)
    }

    /// `2026-08-26` -> `26 Aug`. Day-first, because the month repeats and the
    /// day does not.
    static func shortDateLabel(_ iso: String) -> String {
        let parts = iso.split(separator: "-")
        guard parts.count >= 3, let month = Int(parts[1]), let day = Int(parts[2]),
              (1...12).contains(month) else { return iso }
        let months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return "\(day) \(months[month - 1])"
    }

    // MARK: Window starts

    /// The chart's two window starts for a hub payload.
    ///
    /// ⚠️ **NEITHER DATE IS EVER A CONSTANT HERE.** `30 August` is a fact about
    /// the 2026 US Open; written into this file it would be wrong for the
    /// Australian Open in January and — worse — wrong SILENTLY, because a chart
    /// drawn from the wrong start still draws.
    ///
    /// The two are read differently on purpose. **The main draw is PUBLISHED**:
    /// `main_draw_starts_at` is the register's own value. **Qualifying is
    /// OBSERVED**: nothing in the payload names the day it began, and inventing
    /// "five days before the main draw" would be a rule about one tournament
    /// wearing the shape of a fact — so it is the earliest day a qualifying
    /// match finished on, and absent when there are no qualifying rows.
    ///
    /// `QUAL` is dropped when it is not STRICTLY earlier than `DRAW`: two chips
    /// that draw the same window are one chip and a puzzle.
    static func windowStarts(
        mainDrawStartsAt: String?,
        results: [TournamentHubResult]
    ) -> RaceChartWindowStarts {
        let draw = isoDay(mainDrawStartsAt)
        var qualifying: String?
        for match in results where isQualifying(match) {
            guard let day = isoDay(match.completedAt) else { continue }
            if let earliest = qualifying, earliest <= day { continue }
            qualifying = day
        }
        let qual: String? = {
            guard let qualifying else { return nil }
            guard let draw else { return qualifying }
            return qualifying < draw ? qualifying : nil
        }()
        return RaceChartWindowStarts(draw: draw, qual: qual)
    }

    /// Either round field may say a match was played in qualifying.
    static func isQualifying(_ result: TournamentHubResult) -> Bool {
        [result.round, result.sourceRound].contains {
            $0?.trimmingCharacters(in: .whitespaces).lowercased().hasPrefix(qualifyingRoundPrefix) == true
        }
    }

    /// The local day an ISO timestamp names, or `nil` if it is not one.
    ///
    /// The LEADING TEN CHARACTERS, not a UTC conversion:
    /// `main_draw_starts_at` is `2026-08-30T11:00:00-04:00`, and the
    /// tournament's own answer to "what day did play start" is the one printed
    /// on the ticket, not the one a UTC conversion would give an evening
    /// session.
    static func isoDay(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespaces)
        guard trimmed.count >= 10 else { return nil }
        let day = String(trimmed.prefix(10))
        let parts = day.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
              let year = Int(parts[0]), let month = Int(parts[1]), let dayOfMonth = Int(parts[2]),
              (1...12).contains(month), (1...31).contains(dayOfMonth), year > 0 else { return nil }
        return day
    }

    /// Whole days since 1970-01-01 for a `YYYY-MM-DD`.
    ///
    /// Civil arithmetic (Howard Hinnant's `days_from_civil`) rather than
    /// `Calendar`, so the answer does not depend on the device's timezone or
    /// locale — a windowing rule that moves with the reader's clock is exactly
    /// the branch gotcha #44 exists to forbid.
    static func dayNumber(_ iso: String) -> Int? {
        guard let day = isoDay(iso) else { return nil }
        let parts = day.split(separator: "-")
        guard let y = Int(parts[0]), let m = Int(parts[1]), let d = Int(parts[2]) else { return nil }
        let year = m <= 2 ? y - 1 : y
        let era = (year >= 0 ? year : year - 399) / 400
        let yearOfEra = year - era * 400                                  // [0, 399]
        let dayOfYear = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1    // [0, 365]
        let dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear
        return era * 146_097 + dayOfEra - 719_468
    }

    /// Short legend name: `Aryna Sabalenka` -> `A. Sabalenka`.
    static func legendName(_ displayName: String) -> String {
        let parts = displayName.split(separator: " ").filter { !$0.isEmpty }
        guard parts.count >= 2, let initial = parts[0].first else { return displayName }
        return "\(initial). \(parts.dropFirst().joined(separator: " "))"
    }
}
