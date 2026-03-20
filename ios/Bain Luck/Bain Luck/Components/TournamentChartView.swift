import SwiftUI
import Charts

/// Multi-participant probability evolution chart with leaderboard grid.
/// Inspired by DataGolf — shows probability trends over time for tournaments,
/// championships, and multi-outcome futures markets.
struct TournamentChartView: View {
    let marketId: Int
    var hours: Int = 168
    var height: CGFloat = 280

    @State private var data: ProbabilityTimelineResponse?
    @State private var loading = true
    @State private var error: String?
    @State private var topFilter: Int = 10
    @State private var selectedNames: Set<String> = []

    // MARK: - Colors

    private static let positionColors: [Color] = [
        .blue, .red, .green, .purple, .orange,
        .cyan, .pink, .indigo, Color(hex: "#ca8a04"), .teal,
    ]

    private func colorForOutcome(name: String, index: Int) -> Color {
        // Use team primary_color if available
        if let meta = data?.outcomes.first(where: { $0.name == name }),
           let hex = meta.primaryColor {
            return Color(hex: hex)
        }
        return Self.positionColors[index % Self.positionColors.count]
    }

    // MARK: - Body

    var body: some View {
        Group {
            if loading {
                ProgressView()
                    .frame(height: height)
            } else if let error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(height: height)
            } else if let _ = data, chartEntries.count >= 2 {
                VStack(spacing: 0) {
                    controlBar
                    chartSection
                    leaderboardGrid
                }
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
        .task {
            await loadData()
        }
    }

    // MARK: - Load Data

    private func loadData() async {
        loading = data == nil
        do {
            let result = try await APIClient.shared.fetchProbabilityTimeline(
                marketId: marketId, top: 50, hours: hours
            )
            data = result
            // Default: select top 3
            if selectedNames.isEmpty {
                selectedNames = Set(result.outcomes.prefix(3).map(\.name))
            }
            error = nil
            loading = false
        } catch {
            self.error = "Failed to load timeline"
            loading = false
        }
    }

    // MARK: - Computed

    private var displayedOutcomes: [TimelineOutcomeMeta] {
        guard let data else { return [] }
        let filtered = data.outcomes.filter { $0.name != "Field" }
        if topFilter >= filtered.count { return filtered }
        return Array(filtered.prefix(topFilter))
    }

    private var displayedNames: [String] {
        displayedOutcomes.map(\.name)
    }

    private struct ChartPoint: Identifiable {
        let id = UUID()
        let date: Date
        let name: String
        let probability: Double
    }

    private var chartEntries: [ChartPoint] {
        guard let data else { return [] }
        let names = Set(displayedNames)
        var points: [ChartPoint] = []
        for entry in data.timeline {
            guard let date = entry.timestamp.asDate else { continue }
            for (name, prob) in entry.outcomes where names.contains(name) {
                points.append(ChartPoint(
                    date: date,
                    name: name,
                    probability: prob * 100
                ))
            }
        }
        return points
    }

    private var effectiveSelected: Set<String> {
        selectedNames.isEmpty ? Set(displayedNames.prefix(3)) : selectedNames
    }

    // MARK: - Control Bar

    private var controlBar: some View {
        HStack {
            Text("Show")
                .font(.caption2)
                .foregroundStyle(.secondary)

            HStack(spacing: 0) {
                ForEach([5, 10, 20], id: \.self) { n in
                    Button {
                        topFilter = n
                    } label: {
                        Text("Top \(n)")
                            .font(.caption2)
                            .fontWeight(.medium)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(topFilter == n ? Color.primary : Color.clear)
                            .foregroundStyle(topFilter == n ? Color(.systemBackground) : .secondary)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color(.separator), lineWidth: 0.5)
            )

            Spacer()
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(.secondarySystemGroupedBackground).opacity(0.5))
    }

    // MARK: - Chart

    private var chartSection: some View {
        Chart(chartEntries) { point in
            LineMark(
                x: .value("Time", point.date),
                y: .value("Probability", point.probability)
            )
            .foregroundStyle(by: .value("Participant", point.name))
            .lineStyle(StrokeStyle(
                lineWidth: effectiveSelected.contains(point.name) ? 2.5 : 1,
                lineCap: .round
            ))
            .opacity(effectiveSelected.isEmpty || effectiveSelected.contains(point.name) ? 1 : 0.1)
        }
        .chartForegroundStyleScale(mapping: { (name: String) -> Color in
            let idx = displayedNames.firstIndex(of: name) ?? 0
            return colorForOutcome(name: name, index: idx)
        })
        .chartYAxis {
            AxisMarks(position: .leading) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text("\(Int(v))%")
                            .font(.caption2)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { value in
                AxisGridLine()
                AxisValueLabel(format: hours <= 48 ? .dateTime.hour() : .dateTime.month(.abbreviated).day())
            }
        }
        .chartLegend(.hidden)
        .frame(height: height)
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    // MARK: - Leaderboard Grid

    private var leaderboardGrid: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                Text("#")
                    .frame(width: 24, alignment: .leading)
                Text("Participant")
                Spacer()
                Text("Prob")
                    .frame(width: 50, alignment: .trailing)
                Text("24h")
                    .frame(width: 50, alignment: .trailing)
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color(.secondarySystemGroupedBackground).opacity(0.5))

            Divider()

            ForEach(Array(displayedOutcomes.enumerated()), id: \.element.name) { index, outcome in
                let isSelected = effectiveSelected.contains(outcome.name)
                let color = colorForOutcome(name: outcome.name, index: index)
                let probPct = (outcome.currentProbability ?? 0) * 100
                let changePct = (outcome.probabilityChange24h ?? 0) * 100

                Button {
                    toggleSelection(outcome.name)
                } label: {
                    HStack(spacing: 6) {
                        // Position + color dot
                        HStack(spacing: 4) {
                            Circle()
                                .fill(color)
                                .frame(width: 6, height: 6)
                                .opacity(isSelected ? 1 : 0.3)
                            Text("\(index + 1)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
                        .frame(width: 24, alignment: .leading)

                        // Logo + Name
                        if let logo = outcome.logoSmall {
                            TeamLogoView(
                                url: logo,
                                teamName: outcome.name,
                                color: color,
                                size: 18
                            )
                        }
                        Text(outcome.name)
                            .font(.subheadline)
                            .fontWeight(isSelected ? .semibold : .regular)
                            .foregroundStyle(isSelected ? .primary : .secondary)
                            .lineLimit(1)

                        if let record = outcome.record {
                            Text(record)
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }

                        Spacer()

                        // Probability with mini bar
                        HStack(spacing: 4) {
                            GeometryReader { geo in
                                ZStack(alignment: .leading) {
                                    RoundedRectangle(cornerRadius: 2)
                                        .fill(Color(.separator).opacity(0.3))
                                    RoundedRectangle(cornerRadius: 2)
                                        .fill(color.opacity(0.6))
                                        .frame(width: geo.size.width * min(1, probPct / 100))
                                }
                            }
                            .frame(width: 24, height: 4)

                            Text(probPct < 1 && probPct > 0
                                 ? String(format: "%.1f%%", probPct)
                                 : "\(Int(probPct.rounded()))%")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .monospacedDigit()
                                .foregroundStyle(.primary)
                        }
                        .frame(width: 50, alignment: .trailing)

                        // 24h change
                        Text(changePct > 0 ? "+\(String(format: "%.1f", changePct))%"
                             : changePct < 0 ? "\(String(format: "%.1f", changePct))%"
                             : "—")
                            .font(.caption)
                            .fontWeight(.medium)
                            .monospacedDigit()
                            .foregroundStyle(
                                changePct > 0 ? .green :
                                changePct < 0 ? .red : .secondary
                            )
                            .frame(width: 50, alignment: .trailing)
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 8)
                    .background(isSelected ? Color.accentColor.opacity(0.05) : Color.clear)
                }
                .buttonStyle(.plain)

                if index < displayedOutcomes.count - 1 {
                    Divider().padding(.leading, 40)
                }
            }
        }
    }

    // MARK: - Actions

    private func toggleSelection(_ name: String) {
        if selectedNames.contains(name) {
            selectedNames.remove(name)
        } else {
            selectedNames.insert(name)
        }
    }
}
