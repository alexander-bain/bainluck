import Foundation

// MARK: - Focused probability axis (#9483 / #11356)
//
// The web chart's selected Y axis, for the native chart: which window of the
// 0–1 scale the plot spans, where its ticks sit, and what each tick and each
// edge says. A transfer, rule for rule, of `computeWinProbYAxis`,
// `teamAxisTick` and `teamAxisEdges` in `frontend/lib/eventKeyStats.ts`
// (blob 751b4021, accepted at 89f9ba03a2 and live at ba2d7db89c). The rules'
// reasons and the production measurements behind them are in that file's
// docstrings; they are not repeated here.
//
// Units. The web helper reads percentages (0–100); native readings are
// fractions (0...1), so 0.75 is a 75% chance, never 0.75%. The conversion is
// made here and nowhere else: readings come in as fractions, the grid is
// snapped in whole percents, and `domain` / `ticks` go back out as fractions
// of those whole percents (45 → 0.45), so every tick sits exactly on the value
// the chart is handed.
//
// This file only SIZES and LABELS what the caller already plots. The caller
// supplies:
//   - the readings of every line it actually draws (the primary line, plus the
//     revealed source lines while Sources is open) and every drawn checkpoint,
//     already admitted, already cut to the chart's time window. Checkpoints
//     count toward the sample floor, the percentiles and the 50% test like any
//     other reading. Nothing here selects a source, decides freshness,
//     kickoff, period or settlement, or re-times an observation.
//   - the values that must stay on the plot (`mustShow`): each drawn line's
//     last reading, the LATEST checkpoint only (earlier checkpoints are
//     readings, not must-show), each revealed source's low and high, and the
//     primary line's minute-range ends — those only while the game is live and
//     not closed (web `OddsChart.tsx`, `primaryMinuteRanges`).
//   - whether the question is a qualified complementary two-outcome market
//     (`.homeAndAway`) or a home-only line (`.homeOnly`, e.g. draw-priced,
//     `DrawPricedWinner`). That is the caller's existing admission; a sport
//     key, two team names, a crossing of 50% or a pair of unrelated quotes is
//     never proof that an away side exists, and nothing here infers one.
//
// Nothing here edits a reading: no smoothing, re-sampling, clamping, deleted
// point or synthetic end. Too few readings choose the full 0–1 window, and
// that window is axis furniture only — it draws no line and states no value.

nonisolated enum ChartProbabilityAxis9483 {

    /// What the axis below 50% means. Supplied by the caller, never derived.
    nonisolated enum Sides: Equatable, Sendable {
        /// A qualified complementary two-outcome market: a coordinate above 50%
        /// is the home side's chance, below it the away side's (`1 − home`, which
        /// on this market IS the away side's chance), and 50% is even.
        case homeAndAway
        /// A home-only line (#10318): the bottom is "the home side does not
        /// win", not the away side, so every tick is the home side's chance and
        /// no tick or edge names an away side.
        case homeOnly
    }

    /// Whose chance a tick or an edge prints.
    nonisolated enum Side: Equatable, Sendable {
        case home, away, even
    }

    /// The window the plot spans, snapped to a whole-percent grid.
    nonisolated struct Window: Equatable, Sendable {
        /// Bottom of the plot, whole percent of the home side's chance.
        let lowerPercent: Int
        /// Top of the plot, whole percent of the home side's chance.
        let upperPercent: Int
        /// Tick positions, whole percents, bottom to top.
        let tickPercents: [Int]

        /// The plot's Y domain on the native 0...1 scale.
        var domain: ClosedRange<Double> { Double(lowerPercent) / 100 ... Double(upperPercent) / 100 }

        /// The tick positions on the native 0...1 scale.
        var ticks: [Double] { tickPercents.map { Double($0) / 100 } }
    }

    /// What one tick prints, and whose chance it is.
    nonisolated struct Tick: Equatable, Sendable {
        let text: String
        let side: Side
    }

    /// The reading at one edge of the drawn window.
    nonisolated struct Edge: Equatable, Sendable {
        let side: Side
        /// The chance of `side` at this edge, whole percent.
        let percent: Int
        /// True only at a true end of the scale: the home side at 100%, or on a
        /// two-outcome market the away side at 100%. A cropped edge is never a pole.
        let isPole: Bool
    }

    nonisolated struct Edges: Equatable, Sendable {
        let top: Edge
        let bottom: Edge
    }

    /// The 0–1 axis the chart drew before this window existed.
    static let full = Window(lowerPercent: 0, upperPercent: 100, tickPercents: [0, 25, 50, 75, 100])

    /// Below this many readings a percentile is not a percentile — keep the full axis.
    static let minSamples = 12
    /// Narrowest window ever shown, in percentage points, so a 2-point wobble is
    /// not magnified into drama.
    static let minSpanPercent = 20
    /// Share of the plot the p2..p98 core must keep before the true extremes are
    /// preferred over the percentile window (web rule 1b, #7837).
    static let minCoreShare = 0.5
    /// Grid steps in percentage points; 50 is a multiple of each, so it is
    /// always on the grid when it is in range.
    static let stepsPercent = [5, 10, 25]
    static let maxIntervals = 5

    // MARK: - Range

    /// The window for the readings the chart draws (`computeWinProbYAxis`).
    ///
    /// `readings` and `mustShow` are fractions (0...1); non-finite values are
    /// skipped, never coerced to zero. Rules, in the web helper's order:
    /// 1. p2..p98 rather than min/max, so an early spike does not set the scale —
    ///    1b. unless that core keeps at least half the full range, in which case
    ///    the true extremes are used;
    /// 5. every `mustShow` value is inside the window (a line's end is never cut off);
    /// 2. 50% is inside the window if, and only if, the readings reach it;
    /// 3. the window is at least 20 points tall;
    /// 4. bounds snap outward to a 5/10/25 grid anchored at 0, inside 0...100;
    ///    50 is never left welded to the frame, and the 0/100 clamp gives the
    ///    minimum span back at the other end.
    static func window(readings: [Double], mustShow: [Double] = []) -> Window {
        let values = readings.map { $0 * 100 }.filter(\.isFinite)
        guard values.count >= minSamples else { return full }

        let sorted = values.sorted()
        var lo = percentile(sorted, 0.02)
        var hi = percentile(sorted, 0.98)

        // Rule 1b — compared before any widening rule, so it is core vs full.
        let fullLo = sorted[0]
        let fullHi = sorted[sorted.count - 1]
        let fullSpan = fullHi - fullLo
        if fullSpan > 0 && (hi - lo) / fullSpan >= minCoreShare {
            lo = fullLo
            hi = fullHi
        }

        // Rule 5.
        for required in mustShow {
            let v = required * 100
            guard v.isFinite else { continue }
            lo = Swift.min(lo, v)
            hi = Swift.max(hi, v)
        }

        // Rule 2 — decided on the raw extremes, because one crossing print is one marker.
        let touchesEven = fullLo <= 50 && fullHi >= 50
        if touchesEven {
            lo = Swift.min(lo, 50)
            hi = Swift.max(hi, 50)
        }

        // Rule 3.
        let minSpan = Double(minSpanPercent)
        if hi - lo < minSpan {
            let mid = (lo + hi) / 2
            lo = mid - minSpan / 2
            hi = mid + minSpan / 2
        }

        // Rule 4.
        let step = stepsPercent.first { (hi - lo) / Double($0) <= Double(maxIntervals) }
            ?? stepsPercent[stepsPercent.count - 1]
        var snappedLo = gridPercent((lo / Double(step)).rounded(.down) * Double(step))
        var snappedHi = gridPercent((hi / Double(step)).rounded(.up) * Double(step))

        if touchesEven && snappedHi == 50 { snappedHi = Swift.min(100, 50 + step) }
        if touchesEven && snappedLo == 50 { snappedLo = Swift.max(0, 50 - step) }

        if snappedHi - snappedLo < minSpanPercent {
            if snappedLo == 0 {
                snappedHi = Swift.min(100, snappedLo + minSpanPercent)
            } else {
                snappedLo = Swift.max(0, snappedHi - minSpanPercent)
            }
        }

        return Window(lowerPercent: snappedLo, upperPercent: snappedHi,
                      tickPercents: Array(stride(from: snappedLo, through: snappedHi, by: step)))
    }

    /// Linear-interpolated percentile of an ascending array (the web `percentile`).
    static func percentile(_ sorted: [Double], _ q: Double) -> Double {
        let i = q * Double(sorted.count - 1)
        let lo = Int(i.rounded(.down))
        let hi = Swift.min(lo + 1, sorted.count - 1)
        return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - Double(lo))
    }

    /// A snapped bound, held inside 0...100 before it becomes an `Int`, so no
    /// reading — however malformed — can trap the conversion.
    private static func gridPercent(_ value: Double) -> Int {
        guard value.isFinite else { return value > 0 ? 100 : 0 }
        return Int(Swift.min(100, Swift.max(0, value)))
    }

    // MARK: - Labels

    /// What a tick at `axisValue` (a fraction of the home side's chance) prints
    /// (`teamAxisTick`). On a two-outcome market a tick below 50% prints the
    /// away side's chance (0.25 → away "75%"), so the bottom of a full axis is
    /// the away side at 100%; a cropped tick prints its own number, never 100%.
    /// A home-only line prints the home side's chance at every tick.
    static func tick(_ axisValue: Double, sides: Sides) -> Tick {
        tick(percent: wholePercent(axisValue), sides: sides)
    }

    static func tick(percent: Int, sides: Sides) -> Tick {
        guard sides == .homeAndAway else { return Tick(text: "\(percent)%", side: .home) }
        if percent == 50 { return Tick(text: "50%", side: .even) }
        return percent > 50
            ? Tick(text: "\(percent)%", side: .home)
            : Tick(text: "\(100 - percent)%", side: .away)
    }

    /// The reading at each edge of the drawn window (`teamAxisEdges`). The edges
    /// are the window, not the data: a window whose top is 80% has the home side
    /// at 80% there, and each edge names the side its own tick names, so a
    /// window entirely on the home side has the home side at both edges.
    static func edges(of window: Window, sides: Sides) -> Edges {
        func edge(_ percent: Int) -> Edge {
            let side = tick(percent: percent, sides: sides).side
            return Edge(side: side,
                        percent: side == .away ? 100 - percent : percent,
                        isPole: percent == 100 || (percent == 0 && sides == .homeAndAway))
        }
        return Edges(top: edge(window.upperPercent), bottom: edge(window.lowerPercent))
    }

    /// The spoken description of one edge, as the web axis says it: "the top of
    /// this view is JAX at 75%." A pole is "this axis"; a cropped edge is "this
    /// view", so a crop is never read out as the team's 100% end.
    static func edgeSentence(_ position: EdgePosition, _ edge: Edge,
                             homeName: String, awayName: String) -> String {
        let noun = edge.isPole ? "axis" : "view"
        switch edge.side {
        case .even: return "the \(position.word) of this \(noun) is 50/50."
        case .home: return "the \(position.word) of this \(noun) is \(homeName) at \(edge.percent)%."
        case .away: return "the \(position.word) of this \(noun) is \(awayName) at \(edge.percent)%."
        }
    }

    nonisolated enum EdgePosition: Equatable, Sendable {
        case top, bottom

        var word: String {
            switch self {
            case .top: return "top"
            case .bottom: return "bottom"
            }
        }
    }

    /// The whole percent of a fraction, rounded the way `OddsChartView.axisLabel`
    /// rounds, so 0.55 (55.00000000000001 after scaling) is 55.
    private static func wholePercent(_ value: Double) -> Int {
        Int((value * 100).rounded())
    }
}
