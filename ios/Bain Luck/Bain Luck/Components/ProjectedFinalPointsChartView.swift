import SwiftUI
import Charts

/// Optional NFL experiment, secondary to the overall win probability.
/// The caller supplies one named book's proven full-game history and request cutoff.
struct ProjectedFinalPointsChartView: View {
    let input: ProjectedFinalPointsSeries.Input
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    @State private var selectedDate: Date?
    @State private var expanded = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var full: ProjectedFinalPointsSeries? { ProjectedFinalPointsSeries.build(input) }
    private var inspected: ProjectedFinalPointsSeries? {
        if let selectedDate { return ProjectedFinalPointsSeries.at(selectedDate, input: input) }
        return full
    }

    var body: some View {
        if let full {
            content(full: full, height: 210)
                .sheet(isPresented: $expanded) {
                    NavigationStack {
                        ScrollView { content(full: full, height: 330).padding() }
                            .navigationTitle("Projected final points")
                            .navigationBarTitleDisplayMode(.inline)
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) {
                                    Button("Done") { expanded = false }
                                }
                            }
                    }
                }
        }
    }

    private func content(full: ProjectedFinalPointsSeries, height: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                Text("Projected final points").font(.headline).fixedSize(horizontal: false, vertical: true)
                Spacer()
                if !expanded {
                    Button { expanded = true } label: { Image(systemName: "arrow.up.left.and.arrow.down.right") }
                        .accessibilityLabel("Expand projected final points")
                }
            }
            Text("\(full.sourceName) · Recorded captures")
                .font(.caption).foregroundStyle(.secondary)
            if let series = inspected {
                readout(series)
                plot(series, full: full)
                    .frame(height: height)
                if series.latestIntervalUnavailable {
                    Text("Latest interval unavailable. Last recorded projection shown.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            } else {
                Text("No usable projection recorded by this time.")
                    .font(.subheadline).foregroundStyle(.secondary)
                Color.clear.frame(height: height).accessibilityHidden(true)
            }
            if full.end > full.start {
                Slider(value: Binding(
                    get: { min(max((selectedDate ?? full.end).timeIntervalSince1970, full.start.timeIntervalSince1970), full.end.timeIntervalSince1970) },
                    set: { selectedDate = Date(timeIntervalSince1970: $0) }
                ), in: full.start.timeIntervalSince1970...full.end.timeIntervalSince1970)
                .accessibilityLabel("Inspect recorded projections and scores")
                .accessibilityValue((selectedDate ?? full.end).formatted(date: .abbreviated, time: .standard))
            }
            if let selectedDate {
                HStack(alignment: .top) {
                    Text("Inspecting \(selectedDate.formatted(date: .abbreviated, time: .standard))")
                        .font(.caption).fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Button("Latest") { self.selectedDate = nil }.font(.caption)
                }
            }
            Text("Solid: projected final points. Dashed: points actually scored. Gaps mean no usable capture; forecasts are not results.")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        // No implicit movement or animation; inspection also respects Reduce Motion.
        .accessibilityIdentifier("projected-final-points-10239")
    }

    private func readout(_ series: ProjectedFinalPointsSeries) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            let layout = dynamicTypeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8)) : AnyLayout(HStackLayout(alignment: .top, spacing: 20))
            layout {
                teamReadout(homeTeam, forecast: series.latest.home, actual: series.latestActual?.home, color: homeColor)
                teamReadout(awayTeam, forecast: series.latest.away, actual: series.latestActual?.away, color: awayColor)
            }
            Text("Projection recorded \(series.latest.at.formatted(date: .abbreviated, time: .standard))")
                .font(.caption).foregroundStyle(.secondary)
            if let actual = series.latestActual {
                Text("Score recorded \(actual.at.formatted(date: .abbreviated, time: .standard))")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    private func teamReadout(_ team: String, forecast: Double, actual: Double?, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(team).font(.subheadline.bold()).foregroundStyle(color)
            Text("\(forecast.formatted(.number.precision(.fractionLength(0...1)))) projected")
                .font(.subheadline.monospacedDigit())
            if let actual {
                Text("\(actual.formatted(.number.precision(.fractionLength(0...1)))) scored")
                    .font(.caption.monospacedDigit()).foregroundStyle(.secondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }

    private func plot(_ series: ProjectedFinalPointsSeries, full: ProjectedFinalPointsSeries) -> some View {
        Chart {
            ForEach(Array(series.segments.enumerated()), id: \.offset) { segment in
                ForEach([0, 1], id: \.self) { side in
                    ForEach(Array(segment.element.enumerated()), id: \.offset) { entry in
                        let point = entry.element
                        let value = side == 0 ? point.home : point.away
                        LineMark(x: .value("Recorded", point.at), y: .value("Projected points", value),
                                 series: .value("Line", "forecast-\(segment.offset)-\(side)"))
                            .interpolationMethod(.stepEnd)
                            .foregroundStyle(side == 0 ? homeColor : awayColor)
                            .lineStyle(StrokeStyle(lineWidth: 2.5))
                        PointMark(x: .value("Recorded", point.at), y: .value("Projected points", value))
                            .foregroundStyle(side == 0 ? homeColor : awayColor)
                            .symbol(side == 0 ? .circle : .diamond)
                            .symbolSize(22)
                    }
                }
            }
            ForEach([0, 1], id: \.self) { side in
                ForEach(Array(drawnActuals(series).enumerated()), id: \.offset) { entry in
                    LineMark(x: .value("Score recorded", entry.element.at),
                             y: .value("Points scored", side == 0 ? entry.element.home : entry.element.away),
                             series: .value("Line", "actual-\(side)"))
                        .interpolationMethod(.stepEnd)
                        .foregroundStyle((side == 0 ? homeColor : awayColor).opacity(0.8))
                        .lineStyle(StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                    if drawnActuals(series).count == 1 {
                        PointMark(x: .value("Score recorded", entry.element.at),
                                  y: .value("Points scored", side == 0 ? entry.element.home : entry.element.away))
                            .foregroundStyle((side == 0 ? homeColor : awayColor).opacity(0.8))
                            .symbol(.square)
                            .symbolSize(18)
                    }
                }
            }
            if let selectedDate {
                RuleMark(x: .value("Inspecting", selectedDate)).foregroundStyle(.secondary.opacity(0.5))
            }
        }
        .chartXScale(domain: full.start...max(full.end, full.start.addingTimeInterval(1)))
        .chartYScale(domain: 0...series.yMax)
        .chartYAxis { AxisMarks(values: series.yTicks) }
        .chartXSelection(value: $selectedDate)
        .chartLegend(.hidden)
        // Full values, team names and recorded times are in the accessible readout;
        // the adjustable slider provides the same inspection without dragging.
        .accessibilityHidden(true)
    }

    private func drawnActuals(_ series: ProjectedFinalPointsSeries) -> [ProjectedFinalPointsSeries.Actual] {
        var points = series.actualSteps.filter { $0.at >= series.start }
        if let prior = series.actualSteps.last(where: { $0.at < series.start }) {
            points.insert(.init(at: series.start, home: prior.home, away: prior.away), at: 0)
        }
        if let last = points.last, last.at < series.end {
            // Holds recorded score state, never appended to the forecast series.
            points.append(.init(at: series.end, home: last.home, away: last.away))
        }
        return points
    }
}
