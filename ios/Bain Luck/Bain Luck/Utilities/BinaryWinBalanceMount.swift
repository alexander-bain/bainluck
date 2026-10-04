import SwiftUI

// MARK: - Binary win chart balance ink: the OddsChartView mount (#10456)
//
// `BinaryWinChartBalanceInk` (lane1b's accepted source) presents; this decides
// WHEN it may, and hands it exactly what the chart already draws. Everything
// here fails closed: any `nil` keeps today's primary line, untouched.
//
// Deliberately NOT mounted: `BinaryWinPairedReadout` at rest. #9517 (Alex's
// rage shake #162) removed the resting readout row from the inline chart
// because the hero directly above already prints both teams' numbers; a
// resting two-team key would put that duplicate back. Both values stay
// readable — the hero above, the scrub card under a finger, and fullscreen's
// own resting row.

enum BinaryWinBalanceMount {

    /// Whether this chart may wear the balance ink. Admitted only when every
    /// one of these holds; anything else is `.refused`:
    ///   - the sport is one `SportVocab` KNOWS (the fallback row holds
    ///     cricket, rugby, AFL… — sports whose winner market can price a draw)
    ///     and its winner market does not price a draw (#5271);
    ///   - the page serves BOTH sides of the winner pair (`current_odds` home
    ///     AND away) — the two-outcome question is published, not assumed;
    ///   - the page supplied team colors (the ink has nothing to wear without);
    ///   - the chart draws exactly ONE line and it is the primary series. A
    ///     chart showing several unblended venue lines stays as it is.
    static func admission(
        sportKey: String?,
        servedHome: Double?,
        servedAway: Double?,
        hasTeamColors: Bool,
        drawnSources: [String],
        primarySource: String
    ) -> BinaryWinBalanceAdmission {
        guard let sportKey, !sportKey.isEmpty else { return .refused }
        let vocab = SportVocab.forSport(sportKey)
        guard vocab != .unscoredInPoints, !vocab.winnerMarketPricesADraw else { return .refused }
        guard servedHome != nil, servedAway != nil else { return .refused }
        guard hasTeamColors else { return .refused }
        guard drawnSources == [primarySource] else { return .refused }
        return .admittedBinary
    }

    /// The primary series' runs exactly as `chartContent` draws them as solid
    /// evidence: every run, in order, verbatim. The one exclusion is the run
    /// the live edge continues when it is left with a lone vertex — the plot
    /// draws no dot there (the overlay's tail starts from it), so the ink must
    /// not either. The trailing live-edge interval itself is never in
    /// `segments` (it is the overlay's), so solid ink never extends across it.
    static func displayedRuns(
        segments: [[ChartDataPoint]],
        continuedRun: Int?
    ) -> [[BinaryWinPathVertex]] {
        segments.enumerated().compactMap { index, segment in
            if segment.count == 1, index == continuedRun { return nil }
            return segment.map(BinaryWinPathVertex.init)
        }
    }

    /// The plan to draw, or `nil` to keep today's line. Only returns a plan
    /// whose geometry PLACES on the chart's own domains (`chartXScale(domain:)`
    /// and `chartYScale(domain: 0...1)`), so the primary marks are never hidden
    /// behind ink that then draws nothing.
    ///
    /// `.linear` is attested because the primary `LineMark` it replaces is
    /// `.interpolationMethod(.linear)` — and only for that reason.
    static func plan(
        admission: BinaryWinBalanceAdmission,
        runs: [[BinaryWinPathVertex]],
        servedHome: Double?,
        servedAway: Double?,
        gameFinished: Bool,
        xDomain: ClosedRange<Date>
    ) -> BinaryWinBalancePlan? {
        guard let plan = BinaryWinChartBalanceInk.plan(
            admission: admission, segments: runs, interpolation: .linear,
            home: servedHome, away: servedAway, gameFinished: gameFinished) else { return nil }
        let unit = BinaryWinChartBalanceInk.linearProjector(
            xDomain: xDomain, plotRect: CGRect(x: 0, y: 0, width: 1, height: 1))
        guard BinaryWinBalanceGeometry(plan: plan, project: unit) != nil else { return nil }
        return plan
    }

    /// The side a point sits on, by the ink's own rule (`home >= 50%` is the
    /// home side) — for the marks the chart still draws on the inked line
    /// (moments, the live-edge tail), so they wear the line's color at that point.
    static func sideColor(probability: Double, home: Color, away: Color) -> Color {
        probability >= BinaryWinChartBalanceInk.even ? home : away
    }
}
