import SwiftUI
import Charts

// MARK: - Round Boundary Marker

private struct RoundBoundary: Identifiable {
    let id = UUID()
    let date: Date
    let label: String
}

// MARK: - Time Range

enum TournamentTimeRange: String, CaseIterable, Identifiable {
    case week = "7d"
    case tournament = "Event"
    case day = "24h"

    var id: String { rawValue }
}

/// Multi-participant probability evolution chart with leaderboard grid.
/// Inspired by DataGolf — shows probability trends over time for tournaments,
/// championships, and multi-outcome futures markets.
///
/// When `tournamentStart` / `tournamentEnd` are provided, derives round
/// boundary markers (R1, R2, R3, R4) and offers a tournament-scoped time range.
struct TournamentChartView: View {
    let marketId: Int
    var hours: Int = 168
    var height: CGFloat = 280
    /// Tournament start date (ISO 8601). Enables round markers + "Event" time range.
    var tournamentStart: String?
    /// Tournament end date (ISO 8601). Defaults to start + 4 days if nil.
    var tournamentEnd: String?

    @State private var data: ProbabilityTimelineResponse?
    @State private var loading = true
    @State private var error: String?
    @State private var errorIsRetryable = false
    @State private var topFilter: Int = 10
    @State private var selectedNames: Set<String> = []
    @State private var selectedRange: TournamentTimeRange = .week

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

    // MARK: - Tournament Dates

    private var parsedTournamentStart: Date? {
        tournamentStart?.asDate
    }

    private var parsedTournamentEnd: Date? {
        if let end = tournamentEnd?.asDate { return end }
        // Default: 4 days after start (standard golf tournament)
        guard let start = parsedTournamentStart else { return nil }
        return Calendar.current.date(byAdding: .day, value: 4, to: start)
    }

    private var hasTournamentDates: Bool {
        parsedTournamentStart != nil
    }

    private var isGolf: Bool {
        data?.sportCategory?.lowercased() == "golf"
    }

    /// Derive round boundary markers from tournament dates.
    /// Each round starts at UTC midnight of the corresponding day.
    private var roundBoundaries: [RoundBoundary] {
        guard let start = parsedTournamentStart else { return [] }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!

        // Align to start of day in UTC
        let startOfDay = cal.startOfDay(for: start)
        let endBound = parsedTournamentEnd.map { min($0.addingTimeInterval(86400), Date()) } ?? Date()

        var boundaries: [RoundBoundary] = []
        var dayOffset = 0
        while dayOffset < 5 { // Max 5 rounds (4 regular + playoff)
            guard let roundDate = cal.date(byAdding: .day, value: dayOffset, to: startOfDay) else { break }
            if roundDate > endBound { break }
            let label = dayOffset < 4 ? "R\(dayOffset + 1)" : "PO"
            boundaries.append(RoundBoundary(date: roundDate, label: label))
            dayOffset += 1
        }
        return boundaries
    }

    // MARK: - Body

    var body: some View {
        Group {
            if loading {
                ProgressView()
                    .frame(height: height)
            } else if let error {
                VStack(spacing: 6) {
                    Image(systemName: errorIsRetryable ? "exclamationmark.triangle" : "doc.text")
                        .font(.system(size: 16))
                        .foregroundStyle(.tertiary)
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    if !errorIsRetryable {
                        Text("Prices update every 1\u{2013}2 hours for this market")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    if errorIsRetryable {
                        Button {
                            Task { await loadData() }
                        } label: {
                            Label("Retry", systemImage: "arrow.clockwise")
                                .font(.caption)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .padding(.top, 4)
                    }
                }
                .frame(height: height * 0.5)
                .frame(maxWidth: .infinity)
            } else if let _ = data, chartEntries.count < 2 {
                VStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .font(.system(size: 16))
                        .foregroundStyle(.tertiary)
                    Text("Limited price history available")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("Prices update every 1–2 hours for this market")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                .frame(height: height * 0.5)
                .frame(maxWidth: .infinity)
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
            // Default to tournament range when dates are available and event has started
            if hasTournamentDates, let start = parsedTournamentStart, start <= Date() {
                selectedRange = .tournament
            }
            await loadData()
        }
    }

    // MARK: - Load Data

    private func loadData() async {
        loading = data == nil
        errorIsRetryable = false
        do {
            let fetchHours: Int
            switch selectedRange {
            case .week: fetchHours = hours
            case .tournament:
                if let start = parsedTournamentStart {
                    fetchHours = max(Int(Date().timeIntervalSince(start) / 3600) + 12, 48)
                } else {
                    fetchHours = hours
                }
            case .day: fetchHours = 24
            }
            let result = try await APIClient.shared.fetchProbabilityTimeline(
                marketId: marketId, top: 50, hours: fetchHours
            )
            data = result
            // Default: select top 3
            if selectedNames.isEmpty {
                selectedNames = Set(result.outcomes.prefix(3).map(\.name))
            }
            error = nil
            loading = false
        } catch let apiError as APIError {
            if apiError.isCancellation { return }
            switch apiError {
            case .networkError:
                self.error = "Connection failed. Check your network."
                errorIsRetryable = true
            case .httpError(let code, _) where code == 404:
                self.error = "Market history not available"
                errorIsRetryable = false
            case .httpError(let code, _) where code >= 500:
                self.error = "Server error. Try again in a moment."
                errorIsRetryable = true
            case .httpError:
                self.error = "Failed to load timeline"
                errorIsRetryable = true
            case .decodingError:
                self.error = "Failed to load timeline"
                errorIsRetryable = true
            case .invalidURL:
                self.error = "Failed to load timeline"
                errorIsRetryable = false
            }
            loading = false
        } catch {
            self.error = "Failed to load timeline"
            errorIsRetryable = true
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
            // Filter by time range
            if selectedRange == .tournament, let start = parsedTournamentStart {
                let rangeStart = start.addingTimeInterval(-3600 * 6) // 6 hours before tournament
                if date < rangeStart { continue }
            }
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
        HStack(spacing: 8) {
            // Time range picker (only when tournament dates exist)
            if hasTournamentDates {
                HStack(spacing: 0) {
                    ForEach(TournamentTimeRange.allCases) { range in
                        Button {
                            selectedRange = range
                            Task { await loadData() }
                        } label: {
                            Text(range.rawValue)
                                .font(.caption2)
                                .fontWeight(selectedRange == range ? .semibold : .regular)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(selectedRange == range ? Color.blue.opacity(0.15) : Color.clear)
                                .foregroundStyle(selectedRange == range ? .blue : .secondary)
                        }
                    }
                }
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.secondary.opacity(0.2), lineWidth: 0.5)
                )
            }

            Spacer()

            // Top N filter
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
                            .foregroundStyle(topFilter == n ? Color.systemBackground : .secondary)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(Color.barTrack, lineWidth: 0.5)
            )
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color.cardBackground.opacity(0.5))
    }

    // MARK: - Chart

    private var chartSection: some View {
        let entries = chartEntries
        let visibleBoundaries: [RoundBoundary]
        if let minDate = entries.map(\.date).min(),
           let maxDate = entries.map(\.date).max() {
            visibleBoundaries = roundBoundaries.filter { $0.date >= minDate && $0.date <= maxDate }
        } else {
            visibleBoundaries = roundBoundaries
        }

        return Chart {
            // Round boundary vertical lines
            ForEach(visibleBoundaries) { boundary in
                RuleMark(x: .value("Round", boundary.date))
                    .lineStyle(StrokeStyle(lineWidth: 0.7, dash: [4, 3]))
                    .foregroundStyle(.secondary.opacity(0.3))
            }

            // Data lines
            ForEach(entries) { point in
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
        }
        .chartForegroundStyleScale(mapping: { (name: String) -> Color in
            let idx = displayedNames.firstIndex(of: name) ?? 0
            return colorForOutcome(name: name, index: idx)
        })
        // Round boundary labels floating inside chart
        .chartOverlay { proxy in
            GeometryReader { geo in
                ForEach(visibleBoundaries) { boundary in
                    if let xPos = proxy.position(forX: boundary.date) {
                        Text(boundary.label)
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(.ultraThinMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                            .position(x: xPos, y: 12)
                    }
                }
            }
        }
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
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(format: selectedRange == .day ? .dateTime.hour() : .dateTime.month(.abbreviated).day())
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
            .background(Color.cardBackground.opacity(0.5))

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
                                        .fill(Color.barTrack.opacity(0.3))
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
