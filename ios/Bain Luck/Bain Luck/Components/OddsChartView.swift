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

// MARK: - Time Range

enum OddsTimeRange: Int, CaseIterable, Identifiable {
    case sixHours = 6
    case twelveHours = 12
    case twentyFourHours = 24
    case fortyEightHours = 48
    case all = 0

    var id: Int { rawValue }

    var label: String {
        switch self {
        case .sixHours: return "6h"
        case .twelveHours: return "12h"
        case .twentyFourHours: return "24h"
        case .fortyEightHours: return "48h"
        case .all: return "All"
        }
    }
}

// MARK: - ViewModel

final class OddsChartViewModel: ObservableObject {
    @Published var history: EventHistoryResponse?
    @Published var loading = true
    @Published var error: String?
    @Published var selectedRange: OddsTimeRange = .twentyFourHours

    let eventId: Int

    init(eventId: Int) {
        self.eventId = eventId
    }

    @MainActor
    func load() async {
        loading = history == nil
        do {
            let hours = selectedRange == .all ? 0 : selectedRange.rawValue
            var query: [String: String] = [:]
            if hours > 0 {
                query["hours"] = "\(hours)"
            }
            history = try await APIClient.shared.fetchEventHistory(id: eventId, hours: hours == 0 ? 168 : hours)
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
    @StateObject private var vm: OddsChartViewModel

    init(eventId: Int) {
        self.eventId = eventId
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

            timeRangePicker

            if vm.loading {
                ProgressView()
                    .frame(height: 200)
            } else if let error = vm.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(height: 200)
            } else if let history = vm.history {
                let dataPoints = buildDataPoints(history)
                if dataPoints.isEmpty {
                    Text("No odds data available")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(height: 200)
                } else {
                    chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:])
                    legendView(dataPoints: dataPoints, sources: history.winProbSources ?? [:])
                }
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .task {
            await vm.load()
        }
        .onChange(of: vm.selectedRange) { _ in
            Task {
                vm.history = nil
                await vm.load()
            }
        }
    }

    // MARK: - Time Range Picker

    private var timeRangePicker: some View {
        HStack(spacing: 0) {
            ForEach(OddsTimeRange.allCases) { range in
                Button {
                    vm.selectedRange = range
                } label: {
                    Text(range.label)
                        .font(.caption2)
                        .fontWeight(vm.selectedRange == range ? .semibold : .regular)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 6)
                        .background(vm.selectedRange == range ? Color.blue.opacity(0.15) : Color.clear)
                        .foregroundStyle(vm.selectedRange == range ? .blue : .secondary)
                }
            }
        }
        .clipShape(Capsule())
        .overlay(Capsule().stroke(Color.secondary.opacity(0.2)))
    }

    // MARK: - Chart

    private func chartView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo]) -> some View {
        let uniqueSources = Set(dataPoints.map(\.source)).sorted()

        return Chart {
            // 50% reference line
            RuleMark(y: .value("Even", 0.5))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [4, 4]))
                .foregroundStyle(.gray.opacity(0.4))

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
        .frame(height: 200)
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
            guard let date = h.timestamp.asDate else { continue }
            points.append(ChartDataPoint(date: date, probability: h.homeProbability, source: "consensus"))
        }

        // Win probability source lines
        if let winProbHistory = history.winProbHistory {
            for (sourceKey, sourcePoints) in winProbHistory {
                for wp in sourcePoints {
                    guard let date = wp.timestamp.asDate else { continue }
                    points.append(ChartDataPoint(date: date, probability: wp.homeProbability, source: sourceKey))
                }
            }
        }

        return points
    }

    // MARK: - Source Styling

    private func colorForSource(_ source: String, sources: [String: WinProbSourceInfo]) -> Color {
        if source == "consensus" { return .blue }
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
