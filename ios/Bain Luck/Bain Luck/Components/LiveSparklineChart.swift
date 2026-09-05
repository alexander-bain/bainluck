import Charts
import SwiftUI

/// The MATCH primitive at GLYPH size (#2911's "sizes glyph/card/full", D58 = A).
///
/// It answers ONE question — has this number been moving just now — that the full
/// chart answers slowly. So it has no axes, no legend, no tooltip and no source
/// toggles, and it draws the blend only ("the blend is the product").
///
/// It is the phone's counterpart to `frontend/components/event/LiveSparkline.tsx`
/// and the two are deliberately built together (native/023's precedent, #3032):
/// patching one surface alone makes web and app say different things about the
/// same match.
///
/// NO SMOOTHING (RULINGS-BATCH-2026-08-30, LIVE UPDATES 2). Every vertex is a
/// reading the server actually produced — `.interpolationMethod(.linear)` is load
/// bearing, not a default. A spline on a ten-minute window would be mostly
/// invented probabilities that no source ever quoted.
struct LiveSparklineChart: View {

    // MARK: - The contract

    /// The narrowest y-axis this glyph will ever draw, in probability (0-1).
    ///
    /// #3313. The web glyph pinned y to the FULL 0-100% range, to stop an
    /// auto-scaled axis turning a one-point wobble into a mountain. That concern
    /// is real and this constant keeps it. What that rule got wrong is the other
    /// side: a 24pt box holding the whole 0-100 range resolves one percentage
    /// point to 0.24pt, so it cannot show the movement it exists to report.
    ///
    /// Measured against production over 26 live events, 2026-09-05 14:05 PT — of
    /// the 16 carrying at least `minimumPoints` in the window, **15 drew less
    /// vertical travel than twice the line's own stroke width**. Only three were
    /// actually flat; eight had moved five points or more, and a Cubs-Marlins
    /// game had swung 19 — the most dramatic thing on its page — which the
    /// full-range axis rendered as 4.6px of wiggle. The glyph was not reporting
    /// calm markets, it was hiding live ones.
    ///
    /// The axis is therefore the data's own range widened to at least this span,
    /// never narrower. One number bounds both failure modes: a 1-point wobble
    /// spans a twentieth of the box and still reads flat, while a 19-point swing
    /// fills it because the floor is a FLOOR and a wider range widens the axis.
    ///
    /// ONE CONTRACT with the web: `MIN_SPAN` in `LiveSparkline.tsx` carries the
    /// same number and each side pins the literal in its own test, the same
    /// arrangement `CEILING_STEPS` / `RaceChart.ceilingSteps` uses. Change one and
    /// the other side's test fails, which is the point.
    static let minimumSpan: Double = 0.2

    /// Below this many readings there is no shape to show, only noise.
    ///
    /// STRICTER than drawability, and deliberately a separate number: two points
    /// draw a line (that is `OddsChartView.hasDrawableLine`, #3278) but two points
    /// on a ten-minute glance is a single segment whose slope is one reading's
    /// worth of noise. `isDrawable` requires BOTH.
    static let minimumPoints = 3

    /// The window, in minutes. The ruling says ten.
    static let windowMinutes = 10

    /// Points of clearance kept at the top and bottom of the plot so the stroke is
    /// not sliced when a reading sits on the edge of the domain. See the call site.
    static let strokeInset: CGFloat = 1

    // MARK: - Inputs

    /// The same `ChartDataPoint`s the full chart is built from — the event page
    /// already holds them, so the glyph costs no new fetch.
    let points: [ChartDataPoint]
    var windowMinutes: Int = LiveSparklineChart.windowMinutes
    var width: CGFloat = 96
    var height: CGFloat = 24
    /// Overridable for ONE reason: `minimumSpan: 1.0` reproduces the old
    /// full-0-100 axis exactly (any range under 1.0 slides to 0...1), so the
    /// render camera can photograph BEFORE and AFTER from a single code path with
    /// one fixture. Production never passes it.
    var minimumSpan: Double = LiveSparklineChart.minimumSpan
    /// Injected so the window is testable. The clock is read by the caller, never
    /// baked into a fixture (gotcha #44).
    var now: Date = Date()

    // MARK: - Pure rules (unit-tested in LiveSparklineDomainTests)

    /// The blend, or the single consensus line when there is no blend — the one
    /// series this glyph is allowed to draw. Reuses the full chart's own choice so
    /// the glyph can never disagree with the chart below it about which line is
    /// the story.
    static func primarySeries(in points: [ChartDataPoint]) -> [ChartDataPoint] {
        let primary = OddsChartView.primarySource(in: points)
        return points.filter { $0.source == primary }
    }

    /// The last `minutes` of readings, oldest first.
    ///
    /// Sorted explicitly: served series are chronological but a pushed point is
    /// APPENDED, and an out-of-order vertex draws a line that doubles back.
    static func windowed(
        _ points: [ChartDataPoint],
        minutes: Int,
        now: Date
    ) -> [ChartDataPoint] {
        let cutoff = now.addingTimeInterval(-Double(minutes) * 60)
        return points
            .filter { $0.date >= cutoff && $0.probability.isFinite }
            .sorted { $0.date < $1.date }
    }

    /// Whether this glyph may draw at all.
    ///
    /// #3278's rule applies here too, one size down: "not empty" is not
    /// "drawable", and a glyph that renders around no line is the same defect the
    /// full chart just closed. `hasDrawableLine` is the shared predicate — per
    /// SERIES, over the visible sources — and is not re-derived here as a count
    /// test. The glyph's own `minimumPoints` floor sits ON TOP of it.
    ///
    /// The glyph's honest-empty is to draw NOTHING, not to say a sentence: it has
    /// no frame to leave stranded, and it lives beside a full chart that already
    /// explains itself. A flat line would be the dishonest option — it implies a
    /// steady market we have no readings for.
    static func isDrawable(_ windowed: [ChartDataPoint]) -> Bool {
        guard OddsChartView.hasDrawableLine(in: windowed) else { return false }
        return windowed.count >= minimumPoints
    }

    /// The y-axis this series should be drawn against.
    ///
    /// Slides rather than squashes at the edges: a series sitting at 96% gets
    /// 0.80...1.0, not a compressed box, so the span a reader judges travel
    /// against is the same everywhere on the axis.
    static func domain(
        for values: [Double],
        minimumSpan: Double = LiveSparklineChart.minimumSpan
    ) -> ClosedRange<Double> {
        guard !values.isEmpty else { return 0...1 }
        let clamped = values.map { min(1, max(0, $0)) }
        let lo = clamped.min()!
        let hi = clamped.max()!
        let floor = min(1, max(0, minimumSpan))
        if hi - lo >= floor { return lo...hi }
        let mid = (lo + hi) / 2
        var lower = mid - floor / 2
        var upper = mid + floor / 2
        if lower < 0 { lower = 0; upper = floor }
        if upper > 1 { lower = 1 - floor; upper = 1 }
        return lower...upper
    }

    /// Net direction over the window, which is what the colour encodes.
    ///
    /// Net, not peak-to-trough, and that is a real limitation stated rather than
    /// hidden: a market that swung ten points out and came back reads as its small
    /// net move. With the span floor in place the SHAPE now carries that story, so
    /// the colour is a summary beside a legible line rather than the only signal —
    /// which is exactly why the shape fix had to come first.
    static func isRising(_ windowed: [ChartDataPoint]) -> Bool {
        guard let first = windowed.first, let last = windowed.last else { return true }
        return last.probability >= first.probability
    }

    // MARK: - Body

    var body: some View {
        let series = Self.windowed(
            Self.primarySeries(in: points),
            minutes: windowMinutes,
            now: now)
        if Self.isDrawable(series) {
            let range = Self.domain(for: series.map(\.probability), minimumSpan: minimumSpan)
            let rising = Self.isRising(series)
            Chart(series) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Win probability", min(1, max(0, point.probability)))
                )
                .interpolationMethod(.linear)
                .lineStyle(StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                .foregroundStyle(rising ? Color(hex: "#10B981") : Color(hex: "#EF4444"))
            }
            .chartYScale(domain: range)
            .chartXAxis(.hidden)
            .chartYAxis(.hidden)
            .chartLegend(.hidden)
            // native/024's lesson one size down: a rule that MOVES an element
            // invalidates every spacing decision taken before the move. Under the
            // old full-0-100 axis real data almost never reached the frame, so a
            // stroke centred on the extreme reading was never noticeably sliced.
            // With a span floor the opposite holds BY CONSTRUCTION — whenever the
            // range exceeds the floor the domain IS that range, so the highest and
            // lowest readings sit exactly on the edges. Caught by reading the
            // raster (72px of ink in a 72px box), not by a test.
            // `STROKE_INSET` in LiveSparkline.tsx is the web's half of this.
            .chartPlotStyle { $0.padding(.vertical, Self.strokeInset) }
            .frame(width: width, height: height)
            .accessibilityElement()
            .accessibilityLabel(Self.accessibilityLabel(for: series, minutes: windowMinutes))
        }
    }

    static func accessibilityLabel(for windowed: [ChartDataPoint], minutes: Int) -> String {
        guard let first = windowed.first, let last = windowed.last else {
            return "No recent readings"
        }
        let from = Int((min(1, max(0, first.probability)) * 100).rounded())
        let to = Int((min(1, max(0, last.probability)) * 100).rounded())
        return "Last \(minutes) minutes: \(from)% to \(to)%"
    }
}
