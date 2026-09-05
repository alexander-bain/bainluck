import SwiftUI
import Charts

// MARK: - The RACE chart (#2911)
//
// Multi-participant probability over time: the US Open contender chart, drawn
// on the phone. The arithmetic is all in `Utilities/RaceChart.swift` and is
// unit-tested there; this file is only the drawing.
//
// Structure adopted from Alex's Kalshi reference: legend of the top three above
// the chart, exactly three lines in the legend's colours with endpoint dots,
// range chips below. **Adaptation, not imitation** — Kalshi's rows carry
// two-sided green/red price pills, which is a trading format and we do not copy
// it. What is taken is the STRUCTURE.
//
// Three departures from `frontend/components/tournament/ContenderChart.tsx`,
// all deliberate, none of them numeric:
//
//  1. **No contender picker.** The web chart lets a reader add lines up to six.
//     This draws the board's top three and says so in the legend. The picker is
//     the next increment, not a thing to half-build: a partly-wired picker that
//     recolours lines is worse than three lines that always mean the same three.
//  2. **Three x-axis ticks, from the drawn domain.** The web module computes a
//     tiered tick stride against a measured pixel width (`axisTickStrides`);
//     that is a machine for fitting labels into an SVG whose width the module
//     knows. Swift Charts owns its own layout, so the ticks here are the
//     domain's first, middle and last day — which is what the tiered version
//     resolves to at phone width anyway, and it cannot disagree with the
//     footer, which reads the same domain.
//  3. **`ALL` is the fallback default, `Draw` the real one** — same rule as the
//     web (`defaultChartRange`), stated here because it is the one behaviour a
//     reader would notice changing.
//
// The numbers are NOT a departure. Ceiling ladder, headroom, three y-labels,
// window semantics, drawability and the endpoint dot all come from
// `RaceChart`, which is a line-by-line port of `lib/contenderChart.ts`.

/// Everything the chart draws, computed once by the presentation layer.
nonisolated struct RaceChartData: Equatable, Sendable {
    let series: [RaceChartSeries]
    let ranges: [RaceChartRange]
    let initialRange: RaceChartRange
    let starts: RaceChartWindowStarts
    /// Set when there is nothing to draw. A sentence, never a blank frame.
    let emptyNote: String?
}

struct RaceChartView: View {
    let data: RaceChartData

    @State private var range: RaceChartRange

    init(data: RaceChartData) {
        self.data = data
        _range = State(initialValue: data.initialRange)
    }

    /// The line colours, in draw order. The same six the web uses
    /// (`--series-1…6` in `globals.css`), so a contender is the same colour on
    /// both surfaces.
    static let seriesColors: [Color] = [
        Color(red: 0.15, green: 0.39, blue: 0.92),  // #2563EB
        Color(red: 0.96, green: 0.62, blue: 0.04),  // #F59E0B
        Color(red: 0.58, green: 0.64, blue: 0.72),  // #94A3B8
        Color(red: 0.49, green: 0.23, blue: 0.93),  // #7C3AED
        Color(red: 0.03, green: 0.57, blue: 0.70),  // #0891B2
        Color(red: 0.86, green: 0.15, blue: 0.47),  // #DB2777
    ]

    static func color(_ index: Int) -> Color {
        seriesColors[index % seriesColors.count]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let note = data.emptyNote {
                Text(note)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
            } else {
                legend
                plot
                controls
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(accessibilityLabel)
    }

    // MARK: Legend

    private var legend: some View {
        // Wraps rather than scrolls: a horizontal `ScrollView` here would put a
        // legend entry off-screen AND make the whole card unrasterisable by
        // `ImageRenderer`, which is how native render evidence goes quietly
        // blank.
        FlowingLegend(spacing: 12) {
            ForEach(data.series) { entry in
                HStack(spacing: 5) {
                    Circle()
                        .fill(Self.color(entry.colorIndex))
                        .frame(width: 7, height: 7)
                    Text(RaceChart.legendName(entry.displayName))
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                    Text(formatProbabilityOrDash(entry.probability))
                        .font(.caption2.weight(.bold).monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                }
            }
        }
    }

    // MARK: Plot

    private var plot: some View {
        Chart {
            ForEach(data.series) { entry in
                let drawn = RaceChart.points(entry.points, in: range, starts: data.starts)
                ForEach(drawn, id: \.date) { point in
                    LineMark(
                        x: .value("Day", Self.date(point.date)),
                        y: .value("Probability", point.probability),
                        series: .value("Contender", entry.entityKey)
                    )
                    .foregroundStyle(Self.color(entry.colorIndex))
                    .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                    // NO SMOOTHING, EVER. Straight segments between real
                    // observations — movement IS the product and a curve fitter
                    // is a machine for hiding it.
                    .interpolationMethod(.linear)
                }
                if let last = drawn.last {
                    PointMark(
                        x: .value("Day", Self.date(last.date)),
                        y: .value("Probability", last.probability)
                    )
                    .foregroundStyle(Self.color(entry.colorIndex))
                    .symbolSize(36)
                }
            }
        }
        .chartYScale(domain: 0...ceiling)
        .chartYAxis {
            AxisMarks(position: .leading, values: RaceChart.yLabels(ceiling: ceiling).map(\.probability)) { mark in
                AxisGridLine().foregroundStyle(DS.border)
                AxisValueLabel {
                    if let value = mark.as(Double.self) {
                        Text("\(Int((value * 100).rounded()))%")
                            .font(.system(size: 9).monospacedDigit())
                            .foregroundStyle(DS.textMuted)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: xTicks.map(Self.date)) { mark in
                AxisGridLine().foregroundStyle(DS.border.opacity(0.6))
                AxisValueLabel {
                    if let date = mark.as(Date.self) {
                        Text(RaceChart.shortDateLabel(Self.isoDay(date)))
                            .font(.system(size: 9))
                            .foregroundStyle(DS.textMuted)
                    }
                }
            }
        }
        .frame(height: 118)
    }

    // MARK: Controls

    private var controls: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                ForEach(data.ranges, id: \.self) { candidate in
                    let drawable = RaceChart.isDrawable(data.series, range: candidate, starts: data.starts)
                    Button {
                        range = candidate
                    } label: {
                        Text(candidate.label)
                            .font(.system(size: 10, weight: .bold))
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(
                                candidate == range ? DS.textPrimary.opacity(0.08) : Color.clear,
                                in: Capsule()
                            )
                            .foregroundStyle(
                                candidate == range ? DS.textPrimary
                                    : (drawable ? DS.textSecondary : DS.textMuted.opacity(0.5))
                            )
                    }
                    .buttonStyle(.plain)
                    // A range with fewer than two readings is offered DISABLED
                    // rather than drawn empty. A chart that blanks on a tap
                    // reads as broken; a greyed chip reads as "not yet".
                    .disabled(!drawable)
                }
                Spacer(minLength: 4)
            }

            if let footer = footerText {
                Text(footer)
                    .font(.system(size: 9))
                    .foregroundStyle(DS.textMuted)
            }
        }
    }

    // MARK: Derived

    private var ceiling: Double {
        RaceChart.ceiling(data.series, range: range, starts: data.starts)
    }

    private var domain: [String] {
        RaceChart.domain(data.series, range: range, starts: data.starts)
    }

    /// Up to three days spread across the drawn window, at 0, ⅓ and ⅔ of it.
    ///
    /// ⚠️ **THE LAST DAY IS DELIBERATELY NOT A TICK, AND THIS IS MEASURED.** A
    /// tick on the domain's right edge draws its gridline and then loses its
    /// label: Swift Charts clips an axis label that would overflow the chart's
    /// bounds, and `collisionResolution: .disabled` does not save it (tried,
    /// `artifacts-native-010/A3`). An unlabelled rule at the edge is worse than
    /// no rule there — it looks like a date the chart forgot to print. So the
    /// ticks sit INSIDE the window and the footer names both of its ends, which
    /// is UX-P207's rule anyway: the ticks are positions inside the window, not
    /// the definition of it. `RaceChart.domain` is what defines it, and the
    /// footer and the accessibility label both read that.
    private var xTicks: [String] {
        let dates = domain
        guard dates.count >= 2 else { return dates }
        var out: [String] = []
        for index in [0, dates.count / 3, (dates.count * 2) / 3] {
            let candidate = dates[index]
            if !out.contains(candidate) { out.append(candidate) }
        }
        return out
    }

    /// "30d shown · 5 Aug – 4 Sep". The chips say which window; this says how
    /// much of the story it is — `ALL` on a field with four readings is four
    /// days, not all of history, and only this line can say so.
    private var footerText: String? {
        let dates = domain
        guard dates.count >= 2, let span = RaceChart.spanDays(data.series, range: range, starts: data.starts) else {
            return nil
        }
        let from = RaceChart.shortDateLabel(dates[0])
        let to = RaceChart.shortDateLabel(dates[dates.count - 1])
        return "\(span)d shown · \(from) – \(to)"
    }

    /// Read to a screen reader off the DOMAIN, not off the ticks: the ticks are
    /// positions inside the window, not the definition of it, and a reader told
    /// "3 Aug to 31 Aug" while the footer says "30d shown" has been given the
    /// same disagreement in two modalities.
    private var accessibilityLabel: String {
        if let note = data.emptyNote { return note }
        let names = data.series.map(\.displayName).joined(separator: ", ")
        guard let footer = footerText else { return "Title odds trend for \(names)." }
        return "Title odds trend for \(names). \(footer)."
    }

    // MARK: Day ↔ Date

    /// A `YYYY-MM-DD` day as an instant, pinned to UTC noon.
    ///
    /// Noon, not midnight, so no device timezone can round the plotted point
    /// onto the day before — the chart's x-values then mean the same day the
    /// payload named, everywhere on earth.
    static func date(_ iso: String) -> Date {
        guard let day = RaceChart.dayNumber(iso) else { return Date(timeIntervalSince1970: 0) }
        return Date(timeIntervalSince1970: Double(day) * 86_400 + 43_200)
    }

    /// The inverse, for axis labels. Same UTC pinning.
    static func isoDay(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC") ?? .gmt
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        guard let y = parts.year, let m = parts.month, let d = parts.day else { return "" }
        return String(format: "%04d-%02d-%02d", y, m, d)
    }
}

// MARK: - A legend that wraps

/// Lays its children out left to right and wraps onto a new line.
///
/// `Layout` rather than a `ScrollView`: `ImageRenderer` will not rasterise a
/// horizontal scroll view's content — it returns a plausible-looking blank
/// image rather than failing — and the legend is the one part of this card that
/// a render test most needs to see.
private struct FlowingLegend: Layout {
    var spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        let rows = layout(subviews: subviews, width: width)
        let height = rows.reduce(0) { $0 + $1.height } + spacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width ?? rows.map(\.width).max() ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in layout(subviews: subviews, width: bounds.width) {
            var x = bounds.minX
            for index in row.indices {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), anchor: .topLeading, proposal: .unspecified)
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row {
        var indices: [Int] = []
        var width: CGFloat = 0
        var height: CGFloat = 0
    }

    private func layout(subviews: Subviews, width: CGFloat) -> [Row] {
        var rows: [Row] = []
        var current = Row()
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let projected = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            if !current.indices.isEmpty && projected > width {
                rows.append(current)
                current = Row()
            }
            current.width = current.indices.isEmpty ? size.width : current.width + spacing + size.width
            current.height = max(current.height, size.height)
            current.indices.append(index)
        }
        if !current.indices.isEmpty { rows.append(current) }
        return rows
    }
}
