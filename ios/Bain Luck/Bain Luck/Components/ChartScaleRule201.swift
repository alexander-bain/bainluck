import Foundation

// MARK: - One Chart Scale Rule (#12750, Rulings 201 & 202-A)
//
// Every probability chart in the app resolves its vertical scale here so no
// chart writes its own ad-hoc Y range:
//   1. `.fittedTwoWay` — two teams or two players with no draw: fitted from the
//      very first reading (`1+` finite readings, including when there are fewer
//      than 12 readings, with the 20-point minimum span and 5/10/25 grid).
//   2. `.fullZeroToHundred` — soccer and any draw-capable sport: `0` to `100`
//      (`ChartProbabilityAxis9483.full`, domain `0...1`).
//   3. `.zeroToTopValue` — Ruling 202-A: golf, futures, tournament race charts,
//      and other many-way / multi-rung markets: anchored at `0` up to a snapped
//      ceiling just above the top value shown.

nonisolated enum ChartScaleRule201 {

    nonisolated enum Mode: Equatable, Sendable {
        case fittedTwoWay
        case fullZeroToHundred
        case zeroToTopValue
    }

    nonisolated struct ZeroBasedWindow: Equatable, Sendable {
        let ceilingFraction: Double
        let ticks: [Double]

        var domain: ClosedRange<Double> { 0 ... ceilingFraction }
    }

    /// Resolves whether a match-winner game chart uses a fitted two-way window
    /// or the full `0...100%` scale (soccer and any draw-capable sport).
    static func gameMode(sportKey: String?) -> Mode {
        if DrawPricedWinner.sportPricesADraw(sportKey) {
            return .fullZeroToHundred
        }
        guard let key = sportKey?.lowercased(), !key.isEmpty else {
            return .fittedTwoWay
        }
        for prefix in ["soccer", "cricket", "boxing", "rugby", "rugbyunion", "rugbyleague", "chess"] {
            if key == prefix || key.hasPrefix("\(prefix)_") {
                return .fullZeroToHundred
            }
        }
        return .fittedTwoWay
    }

    /// Convenience predicate matching `gameMode(sportKey:) == .fullZeroToHundred`.
    static func usesZeroToHundredVerticalScale(sportKey: String?) -> Bool {
        gameMode(sportKey: sportKey) == .fullZeroToHundred
    }

    /// Resolves the Y-axis window for any game win-probability chart (`OddsChartView`,
    /// `DiscoverPictureChartPanel191A`, etc.).
    /// - Draw-capable sports (`soccer`, `cricket`, `boxing`, `rugby`, `chess`) always
    ///   receive `ChartProbabilityAxis9483.full` (`0...100%`).
    /// - Two-team / two-player non-draw sports receive a fitted window from the first
    ///   reading (`ChartProbabilityAxis9483.window`), including when `< 12` readings exist.
    static func gameWindow(
        sportKey: String?,
        readings: [Double],
        mustShow: [Double] = []
    ) -> ChartProbabilityAxis9483.Window {
        switch gameMode(sportKey: sportKey) {
        case .fullZeroToHundred:
            return ChartProbabilityAxis9483.full
        case .fittedTwoWay, .zeroToTopValue:
            return ChartProbabilityAxis9483.window(readings: readings, mustShow: mustShow)
        }
    }

    /// Ruling 202-A (`0` to top value shown, percent `0...100` domain) for
    /// futures and multi-outcome market charts (`EvolutionChartView`).
    static func futuresCeilingPercent(peakPercent: Double) -> Double {
        let peak = peakPercent.isFinite ? max(0, peakPercent) : 50
        if peak <= 26 { return 30 }
        if peak <= 46 { return 50 }
        if peak <= 56 { return 60 }
        if peak <= 76 { return 80 }
        return 100
    }

    /// Ruling 202-A (`0` to top value shown, fraction `0...1` domain) for golf
    /// tournament charts (`EventAtlasGolfTournament11666`) and multi-rung prop
    /// ladders (`NBAEventCards9483`, `NFLEventCards9483`, `MLBFinalCards11284`,
    /// `PlayerMilestoneProfileView`).
    static func zeroToTopCeilingFraction(peakFraction: Double, fullScale: Bool = false) -> Double {
        if fullScale { return 1.0 }
        let peak = peakFraction.isFinite ? max(0, peakFraction) : 1.0
        if peak <= 0.18 { return 0.20 }
        if peak <= 0.28 { return 0.30 }
        if peak <= 0.45 { return 0.50 }
        if peak <= 0.70 { return 0.75 }
        return 1.0
    }

    /// Ruling 202-A (`0` to top value shown, fraction `0...1` domain) for
    /// tournament contender race charts (`RaceChart` / `RaceChartView`).
    static func raceCeilingFraction(
        peakFraction: Double,
        steps: [Double] = [0.10, 0.25, 0.50, 0.75, 1.00],
        headroom: Double = 1.15
    ) -> Double {
        let safePeak = peakFraction.isFinite ? max(0, peakFraction) : 0
        let wanted = safePeak * headroom
        return steps.first { $0 >= wanted } ?? 1.0
    }

    /// Ruling 202-A zero-based window (`0...ceiling` plus clean leading Y ticks)
    /// for multi-rung prop and milestone ladders (`NBA`, `NFL`, `MLB`).
    static func manyWayWindow(values: [Double]) -> ZeroBasedWindow {
        let finite = values.filter(\.isFinite)
        guard let peak = finite.max() else {
            return ZeroBasedWindow(ceilingFraction: 1.0, ticks: [0, 0.5, 1.0])
        }
        let ceiling = zeroToTopCeilingFraction(peakFraction: peak, fullScale: false)
        let ticks: [Double]
        switch ceiling {
        case 0.20:
            ticks = [0, 0.10, 0.20]
        case 0.30:
            ticks = [0, 0.15, 0.30]
        case 0.50:
            ticks = [0, 0.25, 0.50]
        case 0.75:
            ticks = [0, 0.25, 0.50, 0.75]
        default:
            ticks = [0, 0.50, 1.00]
        }
        return ZeroBasedWindow(ceilingFraction: ceiling, ticks: ticks)
    }
}
