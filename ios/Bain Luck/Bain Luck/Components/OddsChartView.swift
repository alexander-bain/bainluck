import SwiftUI
import Charts
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "oddsChart")

// MARK: - Chart Data Point

private struct ChartDataPoint: Identifiable {
    let id = UUID()
    let date: Date
    let probability: Double
    let source: String
}

// MARK: - Period Marker

private struct PeriodMarker: Identifiable {
    let id = UUID()
    let date: Date
    let label: String
    let isGameStart: Bool
}

// MARK: - Time Range

enum OddsTimeRange: String, CaseIterable, Identifiable {
    case all
    case sinceStart

    var id: String { rawValue }

    var label: String {
        switch self {
        case .all: return "All"
        case .sinceStart: return "Since Start"
        }
    }
}

// MARK: - ViewModel

final class OddsChartViewModel: ObservableObject {
    @Published var history: EventHistoryResponse?
    @Published var loading = true
    @Published var error: String?
    @Published var selectedRange: OddsTimeRange = .all

    let eventId: Int

    init(eventId: Int, preloaded: EventHistoryResponse? = nil) {
        self.eventId = eventId
        if let preloaded {
            self.history = preloaded
            self.loading = false
        }
    }

    @MainActor
    func load() async {
        guard history == nil else { return }  // Skip if preloaded
        loading = true
        do {
            history = try await APIClient.shared.fetchEventHistory(id: eventId, hours: 168)
            error = nil
            loading = false
        } catch {
            self.error = error.localizedDescription
            loading = false
            logger.error("Failed to load history for event \(self.eventId): \(error)")
        }
    }
}

// MARK: - View

struct OddsChartView: View {
    let eventId: Int
    var teamColors: (away: Color, home: Color)?
    var commenceTime: String?
    var status: String?
    @StateObject private var vm: OddsChartViewModel

    private var gameStartDate: Date? {
        commenceTime?.asDate
    }

    private var isGameStarted: Bool {
        status == "live" || status == "completed" || status == "closed"
    }

    /// Show the All / Since Start picker only when the game has started
    /// and we know when it started.
    private var showPicker: Bool {
        isGameStarted && gameStartDate != nil
    }

    init(eventId: Int, teamColors: (away: Color, home: Color)? = nil,
         commenceTime: String? = nil, status: String? = nil,
         preloadedHistory: EventHistoryResponse? = nil) {
        self.eventId = eventId
        self.teamColors = teamColors
        self.commenceTime = commenceTime
        self.status = status
        _vm = StateObject(wrappedValue: OddsChartViewModel(eventId: eventId, preloaded: preloadedHistory))
    }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Text("Odds Chart")
                    .font(.subheadline)
                    .fontWeight(.medium)
                Spacer()
            }

            if showPicker {
                timeRangePicker
            }

            if vm.loading {
                ProgressView()
                    .frame(height: 260)
            } else if let error = vm.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(height: 260)
            } else if let history = vm.history {
                let allPoints = buildDataPoints(history)
                let dataPoints = filterPoints(allPoints)
                let periodMarkers = extractPeriodMarkers(history, filteredPoints: dataPoints)
                if dataPoints.isEmpty {
                    Text("No odds data available")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(height: 260)
                } else {
                    chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:], periodMarkers: periodMarkers)
                    legendView(dataPoints: dataPoints, sources: history.winProbSources ?? [:])
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .task {
            // Default to "Since Start" for started games with a known commence time
            if isGameStarted && gameStartDate != nil {
                vm.selectedRange = .sinceStart
            }
            await vm.load()
        }
    }

    // MARK: - Time Range Picker

    private var timeRangePicker: some View {
        HStack(spacing: 0) {
            ForEach(OddsTimeRange.allCases) { range in
                Button {
                    vm.selectedRange = range
                    AnalyticsService.trackChartTimeRange(eventId: eventId, range: range.label)
                } label: {
                    Text(range.label)
                        .font(.caption2)
                        .fontWeight(vm.selectedRange == range ? .semibold : .regular)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(vm.selectedRange == range ? Color.blue.opacity(0.15) : Color.clear)
                        .foregroundStyle(vm.selectedRange == range ? .blue : .secondary)
                }
            }
        }
        .clipShape(Capsule())
        .overlay(Capsule().stroke(Color.secondary.opacity(0.2)))
    }

    // MARK: - Data Filtering

    /// When "Since Start" is selected, only show data from game start onward.
    /// Uses a "smart start" approach: if there's a gap >30 min between
    /// commence_time and the first data point, start from the first data point
    /// instead — prevents empty chart space from schedule delays.
    private func filterPoints(_ points: [ChartDataPoint]) -> [ChartDataPoint] {
        guard vm.selectedRange == .sinceStart,
              let startDate = gameStartDate,
              isGameStarted else {
            return points
        }
        let postStart = points.filter { $0.date >= startDate }
        guard let firstPoint = postStart.first else {
            return postStart
        }
        // If first data point is >30 min after commence_time, skip the gap
        let gap = firstPoint.date.timeIntervalSince(startDate)
        if gap > 1800 {
            // Start 1 minute before the first data point for slight padding
            let adjustedStart = firstPoint.date.addingTimeInterval(-60)
            return postStart.filter { $0.date >= adjustedStart }
        }
        return postStart
    }

    // MARK: - Period Markers

    /// Extract period boundary markers from ESPN history data.
    /// Returns a "Start" marker at commenceTime plus a marker at each period transition.
    /// The start marker position is adjusted to match filtered data range.
    private func extractPeriodMarkers(_ history: EventHistoryResponse, filteredPoints: [ChartDataPoint]) -> [PeriodMarker] {
        var markers: [PeriodMarker] = []

        // Game start marker — position at the earliest filtered data point
        // to avoid creating empty chart space from schedule delays
        if let startDate = gameStartDate, isGameStarted {
            var markerDate = startDate
            if vm.selectedRange == .sinceStart, let firstPoint = filteredPoints.first {
                let gap = firstPoint.date.timeIntervalSince(startDate)
                if gap > 1800 {
                    markerDate = firstPoint.date
                }
            }
            markers.append(PeriodMarker(date: markerDate, label: "Start", isGameStart: true))
        }

        // Period boundary markers from ESPN history
        guard let espnHistory = history.espnHistory, espnHistory.count >= 2 else {
            return markers
        }

        var lastPeriod: String? = nil
        for point in espnHistory {
            guard let period = point.period, !period.isEmpty,
                  let date = point.timestamp.asDate else { continue }

            if period != lastPeriod {
                if lastPeriod != nil {
                    // Period changed — mark the start of the new period
                    markers.append(PeriodMarker(date: date, label: period, isGameStart: false))
                }
                lastPeriod = period
            }
        }

        return markers
    }

    // MARK: - Chart

    private func chartView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo], periodMarkers: [PeriodMarker]) -> some View {
        let uniqueSources = Set(dataPoints.map(\.source)).sorted()

        // Filter period markers to visible data range
        let visibleMarkers: [PeriodMarker]
        if vm.selectedRange == .sinceStart, let startDate = gameStartDate {
            visibleMarkers = periodMarkers.filter { $0.date >= startDate }
        } else {
            visibleMarkers = periodMarkers
        }

        return Chart {
            // 50% reference line
            RuleMark(y: .value("Even", 0.5))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [4, 4]))
                .foregroundStyle(.gray.opacity(0.4))

            // Period marker lines
            ForEach(visibleMarkers) { marker in
                RuleMark(x: .value("Period", marker.date))
                    .lineStyle(StrokeStyle(lineWidth: marker.isGameStart ? 1.2 : 1.0, dash: [3, 3]))
                    .foregroundStyle(.secondary.opacity(marker.isGameStart ? 0.7 : 0.5))
                    .annotation(position: .top, alignment: .leading) {
                        Text(normalizePeriodLabel(marker.label))
                            .font(.system(size: 10, weight: .medium))
                            .foregroundStyle(.primary.opacity(0.7))
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(Color(.systemGray5))
                            .clipShape(RoundedRectangle(cornerRadius: 3))
                            .padding(.leading, 2)
                    }
            }

            // Data lines
            ForEach(uniqueSources, id: \.self) { source in
                let points = dataPoints.filter { $0.source == source }
                ForEach(points) { point in
                    LineMark(
                        x: .value("Time", point.date),
                        y: .value("Probability", point.probability),
                        series: .value("Source", source)
                    )
                    .foregroundStyle(colorForSource(source, sources: sources))
                    .lineStyle(strokeStyleForSource(source, sources: sources))
                    .interpolationMethod(.monotone)
                }
            }
        }
        .chartYScale(domain: 0...1)
        .chartXScale(domain: xAxisDomain(for: dataPoints))
        .chartYAxis {
            AxisMarks(values: [0.0, 0.25, 0.5, 0.75, 1.0]) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.3))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text("\(Int(v * 100))%")
                            .font(.caption2)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.3))
                AxisValueLabel(format: .dateTime.hour().minute(), anchor: .top)
                    .font(.caption2)
            }
        }
        .frame(height: 260)
    }

    // MARK: - Legend

    private func legendView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo]) -> some View {
        // Order: aggregate first (if present), then consensus, then other sources sorted
        let uniqueSources = Set(dataPoints.map(\.source)).sorted()
        let ordered = uniqueSources.sorted { a, b in
            if a == "aggregate" { return true }
            if b == "aggregate" { return false }
            if a == "consensus" { return true }
            if b == "consensus" { return false }
            return a < b
        }

        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(ordered, id: \.self) { source in
                    let isPrimary = source == "aggregate" || (source == "consensus" && !ordered.contains("aggregate"))
                    HStack(spacing: 4) {
                        if isPrimary {
                            // Thick bar for primary line
                            RoundedRectangle(cornerRadius: 1)
                                .fill(colorForSource(source, sources: sources))
                                .frame(width: 14, height: 3)
                        } else {
                            Circle()
                                .fill(colorForSource(source, sources: sources))
                                .frame(width: 6, height: 6)
                        }
                        Text(displayNameForSource(source, sources: sources))
                            .font(.caption2)
                            .foregroundStyle(isPrimary ? .primary : .secondary)
                    }
                }
            }
        }
    }

    // MARK: - Multi-Source Detection

    /// Whether the history has non-sportsbook sources (ESPN, Kalshi, model, etc.)
    private func isMultiSource(_ history: EventHistoryResponse) -> Bool {
        guard let winProbHistory = history.winProbHistory else { return false }
        return !winProbHistory.isEmpty
    }

    // MARK: - Data Transformation

    private func buildDataPoints(_ history: EventHistoryResponse) -> [ChartDataPoint] {
        var points: [ChartDataPoint] = []
        let multiSource = isMultiSource(history)

        if multiSource {
            // Multi-source mode:
            // - "aggregate" = backend-computed weighted median across ALL sources (bold primary)
            // - "consensus" = sportsbook mean (shown at equal weight to other sources)
            // - other sources: ESPN, Kalshi, Polymarket, model, etc.

            // Backend aggregate line (weighted median + staleness decay + smoothing)
            if let aggregateLine = history.aggregateLine {
                for p in aggregateLine {
                    guard let date = p.timestamp.asDate else { continue }
                    points.append(ChartDataPoint(date: date, probability: p.homeProbability, source: "aggregate"))
                }
            }

            // Sportsbook consensus (now a regular-weight source, not the primary)
            for h in history.history {
                guard let date = h.timestamp.asDate,
                      let prob = h.homeProbability else { continue }
                points.append(ChartDataPoint(date: date, probability: prob, source: "consensus"))
            }

            // Other win probability sources
            for (sourceKey, sourcePoints) in history.winProbHistory ?? [:] {
                for wp in sourcePoints {
                    guard let date = wp.timestamp.asDate,
                          let prob = wp.homeProbability else { continue }
                    points.append(ChartDataPoint(date: date, probability: prob, source: sourceKey))
                }
            }
        } else {
            // Sportsbooks-only mode:
            // - "consensus" = sportsbook mean (bold primary, the only aggregation)
            // - No other sources to show
            for h in history.history {
                guard let date = h.timestamp.asDate,
                      let prob = h.homeProbability else { continue }
                points.append(ChartDataPoint(date: date, probability: prob, source: "consensus"))
            }
        }

        return points
    }

    // MARK: - Source Styling

    private func colorForSource(_ source: String, sources: [String: WinProbSourceInfo]) -> Color {
        switch source {
        case "aggregate": return Color(hex: "#059669") // Emerald green, matches web "Bain Luck" line
        case "consensus": return teamColors?.home ?? .blue
        default: break
        }
        if let info = sources[source], let hex = info.color {
            return Color(hex: hex)
        }
        // Fallback colors for known sources
        switch source {
        case "espn": return .orange
        case "bainluck_model": return .purple
        case "kalshi": return Color(hex: "#22c55e")
        case "polymarket": return Color(hex: "#3b82f6")
        case "fangraphs": return Color(hex: "#0d9488")
        default: return .gray
        }
    }

    private func strokeStyleForSource(_ source: String, sources: [String: WinProbSourceInfo]) -> StrokeStyle {
        if source == "aggregate" {
            // Meta-aggregate across all sources — boldest line
            return StrokeStyle(lineWidth: 3.0)
        }
        if source == "consensus" {
            // Check if aggregate exists — if so, consensus is secondary
            let hasAggregate = vm.history?.aggregateLine != nil && isMultiSource(vm.history!)
            if hasAggregate {
                // Regular weight, same as other sources
                return StrokeStyle(lineWidth: 1.5)
            }
            // Sportsbooks-only: consensus is the primary line
            return StrokeStyle(lineWidth: 2.5)
        }
        // Model sources get dashed lines, thinner
        let isModel = sources[source]?.type == "model"
        if isModel {
            return StrokeStyle(lineWidth: 1.5, dash: [5, 3])
        }
        // Market sources (Kalshi, Polymarket) — thin solid
        return StrokeStyle(lineWidth: 1.5)
    }

    private func displayNameForSource(_ source: String, sources: [String: WinProbSourceInfo]) -> String {
        if source == "aggregate" { return "Bain Luck" }
        if source == "consensus" { return "Betting Odds" }
        return sources[source]?.displayName ?? source.capitalized
    }

    // MARK: - X-Axis Domain

    /// Compute a tight x-axis domain from the data points with small padding.
    private func xAxisDomain(for dataPoints: [ChartDataPoint]) -> ClosedRange<Date> {
        let dates = dataPoints.map(\.date)
        guard let minDate = dates.min(), let maxDate = dates.max() else {
            let now = Date()
            return now...now
        }
        let range = maxDate.timeIntervalSince(minDate)
        let padding = max(range * 0.02, 60) // At least 1 minute padding
        return minDate.addingTimeInterval(-padding)...maxDate.addingTimeInterval(padding)
    }

    // MARK: - Period Label Normalization

    /// Normalize ESPN period strings to user-friendly labels.
    private func normalizePeriodLabel(_ raw: String) -> String {
        let lower = raw.lowercased().trimmingCharacters(in: .whitespaces)

        // Already short/friendly
        if ["start", "ot", "ot1", "ot2", "ot3", "ot4", "so"].contains(lower) {
            return raw
        }

        // Basketball / Football quarters
        if lower.hasPrefix("1st quarter") || lower == "1st" { return "Q1" }
        if lower.hasPrefix("2nd quarter") || lower == "2nd" { return "Q2" }
        if lower.hasPrefix("3rd quarter") || lower == "3rd" { return "Q3" }
        if lower.hasPrefix("4th quarter") || lower == "4th" { return "Q4" }

        // Hockey / Soccer halves/periods
        if lower.hasPrefix("1st period") { return "P1" }
        if lower.hasPrefix("2nd period") { return "P2" }
        if lower.hasPrefix("3rd period") { return "P3" }
        if lower.hasPrefix("1st half") { return "H1" }
        if lower.hasPrefix("2nd half") { return "H2" }

        // Baseball innings
        if lower.contains("inning") {
            let digits = raw.filter(\.isNumber)
            if !digits.isEmpty { return "\(digits)th" }
        }

        // Halftime / Intermission
        if lower.contains("halftime") || lower.contains("half time") { return "HT" }
        if lower.contains("intermission") { return "INT" }

        // Overtime variants
        if lower.contains("overtime") { return "OT" }

        return raw
    }
}
