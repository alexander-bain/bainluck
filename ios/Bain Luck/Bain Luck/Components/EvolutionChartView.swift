import SwiftUI
import Charts

// MARK: - Time Range

enum EvolutionTimeRange: String, CaseIterable, Identifiable {
    case season = "Season"
    case week = "7d"
    case tournament = "Event"
    case day = "24h"
    case today = "Today"

    var id: String { rawValue }
}

// MARK: - Chart Point

private struct EvolutionPoint: Identifiable {
    let id = UUID()
    let date: Date
    let name: String
    let probability: Double
    let isCombined: Bool
}

// MARK: - Crosshair State

private struct CrosshairData: Equatable {
    let date: Date
    let entries: [(name: String, probability: Double, color: Color)]

    static func == (lhs: CrosshairData, rhs: CrosshairData) -> Bool {
        lhs.date == rhs.date && lhs.entries.count == rhs.entries.count
    }
}

// MARK: - Round Boundary

private struct EvolutionRoundBoundary: Identifiable {
    let id = UUID()
    let date: Date
    let label: String
}

// MARK: - EvolutionChartView

/// Multi-outcome probability evolution chart with interactive crosshair,
/// combined probability line, and leaderboard grid. Drop-in replacement for
/// TournamentChartView with feature parity to the web EvolutionChart.
struct EvolutionChartView: View {
    let marketId: Int
    var hours: Int = 168
    var height: CGFloat = 280
    var tournamentStart: String?
    var tournamentEnd: String?

    @State private var data: ProbabilityTimelineResponse?
    @State private var loading = true
    @State private var error: String?
    @State private var topFilter: Int = 10
    @State private var selectedNames: Set<String> = []
    @State private var highlightedName: String?
    @State private var showCombinedProbability = false
    @State private var selectedRange: EvolutionTimeRange = .week
    @State private var crosshair: CrosshairData?

    // MARK: - Colors

    /// 10-color palette matching the web EvolutionChart, optimized for light backgrounds.
    private static let evolutionColors: [Color] = [
        Color(hex: "#c41e3a"), // red (leader)
        Color(hex: "#005eb8"), // blue
        Color(hex: "#1d4ed8"), // indigo
        Color(hex: "#0e7490"), // teal
        Color(hex: "#b91c1c"), // dark red
        Color(hex: "#0369a1"), // sky
        Color(hex: "#92400e"), // amber
        Color(hex: "#4338ca"), // violet
        Color(hex: "#be185d"), // pink
        Color(hex: "#065f46"), // emerald
    ]

    private static let combinedColor = Color(hex: "#111827")

    private func colorForOutcome(name: String, index: Int) -> Color {
        if let meta = data?.outcomes.first(where: { $0.name == name }),
           let hex = meta.primaryColor {
            return Color(hex: hex)
        }
        return Self.evolutionColors[index % Self.evolutionColors.count]
    }

    // MARK: - Tournament Dates

    private var parsedTournamentStart: Date? { tournamentStart?.asDate }

    private var parsedTournamentEnd: Date? {
        if let end = tournamentEnd?.asDate { return end }
        guard let start = parsedTournamentStart else { return nil }
        return Calendar.current.date(byAdding: .day, value: 4, to: start)
    }

    private var hasTournamentDates: Bool { parsedTournamentStart != nil }

    private var roundBoundaries: [EvolutionRoundBoundary] {
        guard let start = parsedTournamentStart else { return [] }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let startOfDay = cal.startOfDay(for: start)
        let endBound = parsedTournamentEnd.map { min($0.addingTimeInterval(86400), Date()) } ?? Date()
        var boundaries: [EvolutionRoundBoundary] = []
        var dayOffset = 0
        while dayOffset < 5 {
            guard let roundDate = cal.date(byAdding: .day, value: dayOffset, to: startOfDay) else { break }
            if roundDate > endBound { break }
            let label = dayOffset < 4 ? "R\(dayOffset + 1)" : "PO"
            boundaries.append(EvolutionRoundBoundary(date: roundDate, label: label))
            dayOffset += 1
        }
        return boundaries
    }

    // MARK: - Available Time Ranges

    private var availableRanges: [EvolutionTimeRange] {
        if hasTournamentDates, let start = parsedTournamentStart, start <= Date() {
            let tournamentEnded: Bool
            if let end = parsedTournamentEnd {
                tournamentEnded = end.addingTimeInterval(86400) < Date()
            } else {
                tournamentEnded = false
            }
            return tournamentEnded
                ? [.season, .tournament]
                : [.season, .tournament, .day, .today]
        }
        return [.season, .week, .day, .today]
    }

    // MARK: - Body

    var body: some View {
        Group {
            if loading {
                ProgressView()
                    .frame(height: height)
            } else if let error {
                emptyState(error)
            } else if let _ = data, chartEntries.count < 2 {
                emptyState("Limited price history available")
            } else if let _ = data, chartEntries.count >= 2 {
                VStack(spacing: 0) {
                    controlBar
                    chartSection
                    if crosshair != nil {
                        crosshairTooltip
                    }
                    leaderboardGrid
                }
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            }
        }
        .task {
            if hasTournamentDates, let start = parsedTournamentStart, start <= Date() {
                selectedRange = .tournament
            }
            await loadData()
        }
    }

    // MARK: - Empty State

    private func emptyState(_ message: String) -> some View {
        VStack(spacing: 6) {
            Image(systemName: "doc.text")
                .font(.system(size: 16))
                .foregroundStyle(.tertiary)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text("Prices update every 1-2 hours for this market")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .frame(height: height * 0.5)
        .frame(maxWidth: .infinity)
    }

    // MARK: - Load Data

    private func loadData() async {
        loading = data == nil
        do {
            let fetchHours: Int
            switch selectedRange {
            case .season:
                fetchHours = 4320 // ~6 months
            case .week:
                fetchHours = hours
            case .tournament:
                if let start = parsedTournamentStart {
                    fetchHours = max(Int(Date().timeIntervalSince(start) / 3600) + 12, 48)
                } else {
                    fetchHours = hours
                }
            case .day:
                fetchHours = 24
            case .today:
                fetchHours = 24
            }
            let result = try await APIClient.shared.fetchProbabilityTimeline(
                marketId: marketId, top: 50, hours: fetchHours
            )
            data = result
            if selectedNames.isEmpty {
                selectedNames = Set(result.outcomes.prefix(3).map(\.name))
            }
            error = nil
            loading = false
        } catch {
            self.error = "Limited price history available"
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

    private var displayedNames: [String] { displayedOutcomes.map(\.name) }

    private var effectiveSelected: Set<String> {
        selectedNames.isEmpty ? Set(displayedNames.prefix(3)) : selectedNames
    }

    /// Time-filtered cutoff date for chart entries.
    private var timeCutoff: Date? {
        switch selectedRange {
        case .season:
            return nil
        case .week:
            return Calendar.current.date(byAdding: .day, value: -7, to: Date())
        case .tournament:
            guard let start = parsedTournamentStart else { return nil }
            return start.addingTimeInterval(-3600 * 6)
        case .day:
            return Calendar.current.date(byAdding: .hour, value: -24, to: Date())
        case .today:
            return Calendar.current.startOfDay(for: Date())
        }
    }

    private var chartEntries: [EvolutionPoint] {
        guard let data else { return [] }
        let names = Set(displayedNames)
        let cutoff = timeCutoff
        var points: [EvolutionPoint] = []
        // Track latest known probabilities for the combined line
        var latestProbs: [String: Double] = [:]

        for entry in data.timeline {
            guard let date = entry.timestamp.asDate else { continue }
            if let cutoff, date < cutoff { continue }

            for (name, prob) in entry.outcomes where names.contains(name) {
                points.append(EvolutionPoint(
                    date: date,
                    name: name,
                    probability: prob * 100,
                    isCombined: false
                ))
                if effectiveSelected.contains(name) {
                    latestProbs[name] = prob * 100
                }
            }

            // Combined probability line
            if showCombinedProbability, effectiveSelected.count > 1, !latestProbs.isEmpty {
                let combined = min(100, latestProbs.values.reduce(0, +))
                points.append(EvolutionPoint(
                    date: date,
                    name: "_combined",
                    probability: combined,
                    isCombined: true
                ))
            }
        }
        return points
    }

    // MARK: - Control Bar

    private var controlBar: some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                // Time range picker
                HStack(spacing: 0) {
                    ForEach(availableRanges) { range in
                        Button {
                            selectedRange = range
                            crosshair = nil
                            Task { await loadData() }
                        } label: {
                            Text(range.rawValue)
                                .font(.caption2)
                                .fontWeight(selectedRange == range ? .semibold : .regular)
                                .padding(.horizontal, 8)
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

                Spacer()

                // Combined toggle
                Button {
                    showCombinedProbability.toggle()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: showCombinedProbability ? "checkmark.square.fill" : "square")
                            .font(.system(size: 11))
                        Text("Sum")
                            .font(.caption2)
                            .fontWeight(.medium)
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .foregroundStyle(showCombinedProbability ? .blue : .secondary)
                }

                // Top N filter
                HStack(spacing: 0) {
                    ForEach([5, 10, 20], id: \.self) { n in
                        Button {
                            topFilter = n
                        } label: {
                            Text("Top \(n)")
                                .font(.caption2)
                                .fontWeight(.medium)
                                .padding(.horizontal, 8)
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
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color.cardBackground.opacity(0.5))
    }

    // MARK: - Chart

    private var chartSection: some View {
        let entries = chartEntries
        let visibleBoundaries: [EvolutionRoundBoundary]
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

            // Crosshair vertical line
            if let crosshair {
                RuleMark(x: .value("Crosshair", crosshair.date))
                    .lineStyle(StrokeStyle(lineWidth: 1, dash: [3, 2]))
                    .foregroundStyle(.primary.opacity(0.3))
            }

            // Data lines
            ForEach(entries) { point in
                let isSelected = point.isCombined || effectiveSelected.contains(point.name)
                let isHighlighted = highlightedName == nil || highlightedName == point.name

                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Probability", point.probability)
                )
                .foregroundStyle(by: .value("Participant", point.name))
                .lineStyle(StrokeStyle(
                    lineWidth: point.isCombined ? 2.2 :
                        (highlightedName == point.name ? 2.5 :
                            (isSelected ? 1.8 : 0.8)),
                    lineCap: .round,
                    dash: point.isCombined ? [7, 4] : []
                ))
                .opacity(point.isCombined
                    ? (highlightedName != nil ? 0.45 : 0.9)
                    : (isSelected && isHighlighted ? 1 : (isSelected ? 0.2 : 0.1)))
            }
        }
        .chartForegroundStyleScale(mapping: { (name: String) -> Color in
            if name == "_combined" { return Self.combinedColor }
            let idx = displayedNames.firstIndex(of: name) ?? 0
            return colorForOutcome(name: name, index: idx)
        })
        // Round boundary labels
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

                // Touch overlay for crosshair
                Color.clear
                    .contentShape(Rectangle())
                    .gesture(
                        DragGesture(minimumDistance: 0)
                            .onChanged { drag in
                                updateCrosshair(at: drag.location, proxy: proxy, geometry: geo)
                            }
                            .onEnded { _ in
                                crosshair = nil
                            }
                    )
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
            AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(
                    format: (selectedRange == .day || selectedRange == .today)
                        ? .dateTime.hour()
                        : selectedRange == .tournament
                            ? .dateTime.weekday(.abbreviated).day()
                            : .dateTime.month(.abbreviated).day()
                )
            }
        }
        .chartLegend(.hidden)
        .frame(height: height)
        .padding(.horizontal)
        .padding(.vertical, 8)
    }

    // MARK: - Crosshair Update

    private func updateCrosshair(at location: CGPoint, proxy: ChartProxy, geometry: GeometryProxy) {
        guard let date: Date = proxy.value(atX: location.x) else { return }
        let entries = chartEntries.filter { !$0.isCombined }
        // Find closest timestamp
        guard let closest = entries.min(by: {
            abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
        }) else { return }

        let matchDate = closest.date
        let matchEntries = entries
            .filter { $0.date == matchDate && effectiveSelected.contains($0.name) }
            .sorted { $0.probability > $1.probability }

        let coloredEntries: [(name: String, probability: Double, color: Color)] = matchEntries.map { point in
            let idx = displayedNames.firstIndex(of: point.name) ?? 0
            let color = colorForOutcome(name: point.name, index: idx)
            return (name: point.name, probability: point.probability, color: color)
        }

        if !coloredEntries.isEmpty {
            crosshair = CrosshairData(date: matchDate, entries: coloredEntries)
        }
    }

    // MARK: - Crosshair Tooltip

    private var crosshairTooltip: some View {
        guard let crosshair else { return AnyView(EmptyView()) }
        let dateStr: String
        if selectedRange == .day || selectedRange == .today {
            dateStr = crosshair.date.formatted(.dateTime.hour().minute())
        } else {
            dateStr = crosshair.date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
        }

        return AnyView(
            VStack(alignment: .leading, spacing: 4) {
                Text(dateStr)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                ForEach(Array(crosshair.entries.prefix(8).enumerated()), id: \.offset) { _, entry in
                    HStack(spacing: 6) {
                        Circle()
                            .fill(entry.color)
                            .frame(width: 6, height: 6)
                        Text(entry.name)
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                        Spacer()
                        Text(String(format: "%.1f%%", entry.probability))
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .monospacedDigit()
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color.cardBackground.opacity(0.95))
        )
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
                let isHighlighted = highlightedName == nil || highlightedName == outcome.name
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
                            .opacity(isHighlighted ? 1 : 0.4)

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
                             : "-")
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
                .simultaneousGesture(
                    LongPressGesture(minimumDuration: 0.3)
                        .onEnded { _ in
                            withAnimation(.easeInOut(duration: 0.15)) {
                                highlightedName = highlightedName == outcome.name ? nil : outcome.name
                            }
                        }
                )

                if index < displayedOutcomes.count - 1 {
                    Divider().padding(.leading, 40)
                }
            }

            // Footer: selected count + reset
            HStack {
                Text("\(effectiveSelected.count) of \(displayedOutcomes.count) selected")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Spacer()
                if !selectedNames.isEmpty {
                    Button("Reset") {
                        selectedNames = []
                        highlightedName = nil
                    }
                    .font(.caption2)
                    .foregroundStyle(.blue)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
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
