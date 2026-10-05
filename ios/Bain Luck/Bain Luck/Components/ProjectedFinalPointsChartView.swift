import SwiftUI
import Charts

/// Optional NFL experiment, secondary to the overall win probability.
/// The caller supplies one named book's proven full-game history and request cutoff.
///
/// #10549 (native twin of web #10539, Alex on 14781135): one chart, read at a
/// glance. The full timeline and its latest (or last) valid projection are the
/// whole view — the inspection slider is gone and nothing replaces it; the
/// readout above the plot carries both quantities and their recorded times as
/// text. The plot is taller, the sportsbook sits in "How to read this" instead
/// of an unexplained name under the heading, and the game's OBSERVED period
/// boundaries are marked where they were observed.
struct ProjectedFinalPointsChartView: View {
    let input: ProjectedFinalPointsSeries.Input
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color
    /// The history's served `period_markers`; only observed ones are drawn
    /// (`gameStateMarkers`).
    var periodMarkers: [PeriodMarkerPayload]? = nil
    var sportKey: String? = nil

    @State private var expanded = false
    @State private var detailsShown = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    static let inlinePlotHeight: CGFloat = 260
    static let expandedPlotHeight: CGFloat = 400
    /// The strip above the plot that holds the period chips, so a chip never
    /// sits on a line near the top of the scale.
    static let markerStripHeight: CGFloat = 16

    private var full: ProjectedFinalPointsSeries? { ProjectedFinalPointsSeries.build(input) }

    var body: some View {
        if let full {
            let markers = Self.gameStateMarkers(periodMarkers, sportKey: sportKey, series: full,
                                                floor: input.kickoffAt ?? input.scoreObservationStartAt)
            content(full: full, markers: markers, height: Self.inlinePlotHeight)
                .sheet(isPresented: $expanded) {
                    NavigationStack {
                        ScrollView { content(full: full, markers: markers, height: Self.expandedPlotHeight).padding() }
                            .navigationTitle("Projected final points")
                            #if os(iOS)
                            .navigationBarTitleDisplayMode(.inline)
                            #endif
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) {
                                    Button("Done") { expanded = false }
                                }
                            }
                    }
                }
        }
    }

    private func content(full: ProjectedFinalPointsSeries, markers: [GameStateMarker], height: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                Text("Projected final points").font(.headline).fixedSize(horizontal: false, vertical: true)
                Spacer()
                if !expanded {
                    Button { expanded = true } label: { Image(systemName: "arrow.up.left.and.arrow.down.right") }
                        .accessibilityLabel("Expand projected final points")
                }
            }
            readout(full)
            if full.latestIntervalUnavailable {
                Text("Latest interval unavailable. Last recorded projection shown.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            // The chip strip is added on top, so it never eats the plot's height.
            plot(full, markers: markers)
                .frame(height: height + (markers.isEmpty ? 0 : Self.markerStripHeight))
            Text(Self.legend(for: full))
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            DisclosureGroup("How to read this", isExpanded: $detailsShown) {
                VStack(alignment: .leading, spacing: 8) {
                    Text(Self.sourceExplanation(for: full))
                    if !markers.isEmpty {
                        Text(Self.markerExplanation)
                    }
                }
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.top, 4)
            }
            .font(.caption)
        }
        // No implicit movement or animation, so there is nothing for Reduce Motion to stop.
        .accessibilityIdentifier("projected-final-points-10239")
    }

    /// #10478 — before kickoff nothing has been scored, so the legend never
    /// names a dashed line the chart does not draw.
    static func legend(for full: ProjectedFinalPointsSeries) -> String {
        full.actualSteps.isEmpty
            ? "Solid: projected final points. Gaps mean no usable capture; forecasts are not results."
            : "Solid: projected final points. Dashed: points actually scored. Gaps mean no usable capture; forecasts are not results."
    }

    /// #10549 — the one sportsbook, named where it is explained. True
    /// one-book semantics: never a blend, an average or our own forecast.
    static func sourceExplanation(for full: ProjectedFinalPointsSeries) -> String {
        "Projection source: \(full.sourceName). Each team's projected final points come from that one sportsbook's "
            + "expected winning margin and total points for the full game, recorded together. It is not the Bain Luck "
            + "probability above and not an average of sources. The last projection is never joined to the score."
    }

    static let markerExplanation =
        "The thin vertical lines mark each period break (Q1–Q4, HT, OT) at the time it was observed. "
        + "A break first seen in progress can be a little after it began."

    private func readout(_ series: ProjectedFinalPointsSeries) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            let layout = dynamicTypeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8)) : AnyLayout(HStackLayout(alignment: .top, spacing: 20))
            layout {
                teamReadout(homeTeam, forecast: series.latest.home, actual: series.latestActual?.home, color: homeColor)
                teamReadout(awayTeam, forecast: series.latest.away, actual: series.latestActual?.away, color: awayColor)
            }
            Text("\(Self.readingLabel(for: series)) recorded \(series.latest.at.formatted(date: .abbreviated, time: .shortened))")
                .font(.caption).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let actual = series.latestActual {
                Text("Score recorded \(actual.at.formatted(date: .abbreviated, time: .shortened))")
                    .font(.caption).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Which projection the readout prints: the latest while it can still
    /// move, the last one once the game is over.
    static func readingLabel(for series: ProjectedFinalPointsSeries) -> String {
        series.phase == .after ? "Last projection" : "Latest projection"
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

    // MARK: - Game-state markers

    /// One period boundary this chart draws.
    struct GameStateMarker: Equatable {
        let label: String
        let at: Date
        /// `boundary_observed`: the instrument saw the period begin. Anything
        /// else it admitted is a first observation of the period in progress.
        let boundaryObserved: Bool
    }

    /// #10549 — the period boundaries drawn here, by the phone's own evidence
    /// rule (#3348 / #6718, `OddsChartView.servedPeriodMarkers`): only a served
    /// marker a NAMED instrument observed, at its own timestamp. An estimated
    /// or source-less marker is absent, never drawn as timing. Nothing before
    /// the game (a scheduled page draws forecasts only, and the span's
    /// pre-game hour is not game state: `floor` is the observed start the
    /// mount floored the scores at), nothing after the drawn span (so nothing
    /// later than now on a live game), and the span is never stretched to
    /// reach one. One marker per period, the earliest.
    static func gameStateMarkers(_ markers: [PeriodMarkerPayload]?, sportKey: String?,
                                 series: ProjectedFinalPointsSeries, floor: Date?) -> [GameStateMarker] {
        guard series.phase != .before, let floor else { return [] }
        let from = max(floor, series.start)
        var seen: Set<String> = []
        return OddsChartView.servedPeriodMarkers(from: markers, sportKey: sportKey)
            .filter { $0.isObserved && $0.date >= from && $0.date <= series.end }
            .compactMap { boundary -> GameStateMarker? in
                guard seen.insert(boundary.label).inserted else { return nil }
                return GameStateMarker(label: boundary.label, at: boundary.date,
                                       boundaryObserved: boundary.provenance.precision == "boundary_observed")
            }
    }

    /// What VoiceOver hears for the markers the eye sees.
    static func markersSpoken(_ markers: [GameStateMarker]) -> String {
        guard !markers.isEmpty else { return "" }
        return "Game state marked on the chart: " + markers.map { marker in
            "\(PeriodLabel.spoken(marker.label)) \(marker.boundaryObserved ? "began" : "first seen in progress") "
                + marker.at.formatted(date: .omitted, time: .shortened)
        }.joined(separator: ", ") + "."
    }

    // MARK: - Plot

    private func plot(_ series: ProjectedFinalPointsSeries, markers: [GameStateMarker]) -> some View {
        Chart {
            ForEach(Array(markers.enumerated()), id: \.offset) { _, marker in
                RuleMark(x: .value("Period", marker.at))
                    .lineStyle(StrokeStyle(lineWidth: 0.75, dash: [4, 4]))
                    .foregroundStyle(.secondary.opacity(0.5))
            }
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
        }
        .chartXScale(domain: series.start...max(series.end, series.start.addingTimeInterval(1)))
        .chartYScale(domain: 0...series.yMax)
        .chartYAxis { AxisMarks(values: series.yTicks) }
        .chartLegend(.hidden)
        // The chips ride the shared placement (#3237 / #3817): measured widths,
        // kept inside the plot, a chip dropped only when there is no room for it
        // — its rule line stays. They sit in a strip above the plot.
        .chartOverlay { proxy in
            GeometryReader { geo in
                let plotFrame = geo[proxy.plotAreaFrame]
                let placements = PeriodChipGeometry.place(
                    markers.enumerated().compactMap { index, marker in
                        proxy.position(forX: marker.at).map {
                            PeriodChipGeometry.ChipRequest(key: index, label: marker.label, rawX: Double($0))
                        }
                    },
                    plotWidth: plotFrame.width,
                    metrics: .score)
                ForEach(placements, id: \.key) { placement in
                    Text(markers[placement.key].label)
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 3)
                        .padding(.vertical, 1)
                        .position(x: plotFrame.minX + placement.centerX,
                                  y: plotFrame.minY - Self.markerStripHeight / 2)
                }
            }
        }
        .padding(.top, markers.isEmpty ? 0 : Self.markerStripHeight)
        // Values, team names and recorded times are in the readout above; this
        // element speaks the span and the game-state markers it draws.
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Projected final points chart, \(series.start.formatted(date: .omitted, time: .shortened)) to \(series.end.formatted(date: .omitted, time: .shortened))")
        .accessibilityValue(Self.markersSpoken(markers))
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
