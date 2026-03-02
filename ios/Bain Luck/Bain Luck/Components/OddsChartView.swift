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

    init(eventId: Int) {
        self.eventId = eventId
    }

    @MainActor
    func load() async {
        loading = history == nil
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
         commenceTime: String? = nil, status: String? = nil) {
        self.eventId = eventId
        self.teamColors = teamColors
        self.commenceTime = commenceTime
        self.status = status
        _vm = StateObject(wrappedValue: OddsChartViewModel(eventId: eventId))
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
                    .lineStyle(StrokeStyle(lineWidth: marker.isGameStart ? 0.8 : 0.5, dash: [3, 3]))
                    .foregroundStyle(.white.opacity(marker.isGameStart ? 0.4 : 0.25))
                    .annotation(position: .top, alignment: .leading) {
                        Text(marker.label)
                            .font(.system(size: 8))
                            .foregroundStyle(.white.opacity(0.5))
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
        let uniqueSources = Set(dataPoints.map(\.source)).sorted()

        return HStack(spacing: 12) {
            ForEach(uniqueSources, id: \.self) { source in
                HStack(spacing: 4) {
                    Circle()
                        .fill(colorForSource(source, sources: sources))
                        .frame(width: 6, height: 6)
                    Text(displayNameForSource(source, sources: sources))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    // MARK: - Data Transformation

    private func buildDataPoints(_ history: EventHistoryResponse) -> [ChartDataPoint] {
        var points: [ChartDataPoint] = []

        // Consensus line (home probability)
        for h in history.history {
            guard let date = h.timestamp.asDate,
                  let prob = h.homeProbability else { continue }
            points.append(ChartDataPoint(date: date, probability: prob, source: "consensus"))
        }

        // Win probability source lines
        if let winProbHistory = history.winProbHistory {
            for (sourceKey, sourcePoints) in winProbHistory {
                for wp in sourcePoints {
                    guard let date = wp.timestamp.asDate,
                          let prob = wp.homeProbability else { continue }
                    points.append(ChartDataPoint(date: date, probability: prob, source: sourceKey))
                }
            }
        }

        return points
    }

    // MARK: - Source Styling

    private func colorForSource(_ source: String, sources: [String: WinProbSourceInfo]) -> Color {
        if source == "consensus" { return teamColors?.home ?? .blue }
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
        if source == "consensus" {
            return StrokeStyle(lineWidth: 2)
        }
        // Model sources get dashed lines
        let isModel = sources[source]?.type == "model"
        if isModel {
            return StrokeStyle(lineWidth: 1.5, dash: [5, 3])
        }
        return StrokeStyle(lineWidth: 1.5)
    }

    private func displayNameForSource(_ source: String, sources: [String: WinProbSourceInfo]) -> String {
        if source == "consensus" { return "Betting Odds" }
        return sources[source]?.displayName ?? source.capitalized
    }
}
