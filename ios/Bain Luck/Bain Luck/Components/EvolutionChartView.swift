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
/// combined probability line, and leaderboard grid. Feature parity with the web
/// EvolutionChart.
///
/// It replaced `TournamentChartView`, which was deleted along with the RACE
/// chart's arrival (#2911) after sitting with zero call sites: a dead chart in
/// a tree whose next job is "every chart becomes a primitive" is a thing
/// somebody eventually ports.
struct EvolutionChartView: View {
    let marketId: Int
    var hours: Int = 168
    var height: CGFloat = 280
    var tournamentStart: String?
    var tournamentEnd: String?

    @State private var data: ProbabilityTimelineResponse?
    @State private var loading = true
    @State private var error: String?
    @State private var errorIsRetryable = false
    @State private var topFilter: Int = 10
    @State private var selectedNames: Set<String> = []
    @State private var highlightedName: String?
    @State private var showCombinedProbability = false
    @State private var selectedRange: EvolutionTimeRange = .week
    @State private var crosshair: CrosshairData?

    /// #4373 — the leaderboard's numeric columns are measured in the face they are
    /// drawn in, so they need the size the reader is actually at.
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

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
                emptyState(error, retryable: errorIsRetryable)
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

    private func emptyState(_ message: String, retryable: Bool = false) -> some View {
        VStack(spacing: 6) {
            Image(systemName: retryable ? "exclamationmark.triangle" : "doc.text")
                .font(.system(size: 16))
                .foregroundStyle(.tertiary)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            if !retryable {
                Text("Prices update every 1-2 hours for this market")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            if retryable {
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
    }

    // MARK: - Load Data

    private func loadData() async {
        loading = data == nil
        errorIsRetryable = false
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
        } catch let apiError as APIError {
            if apiError.isCancellation {
                // Task cancelled (e.g. view disappeared) — don't show error
                return
            }
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

    /// 🔴 #4199 — THREE GROUPS COMPETED FOR ONE ROW AND `Text` WAS THE ONLY THING
    /// IN IT THAT COULD GIVE, so SwiftUI took the width out of the words. At 402pt
    /// the bar read `Sea/son  7d  24/h  To-/day`; at 375pt it degraded to about one
    /// character per line (`Se/aso/n`). This is the control that decides what the
    /// chart underneath is showing, and it was unreadable at every phone width —
    /// not a narrow-phone edge case, the default state.
    ///
    /// ✅ TWO MODIFIERS AND A LAST RESORT. `lineLimit(1)` alone would only convert
    /// wrapping into truncation — the same information loss, which is #3966's
    /// finding — so each chip also claims its intrinsic width with `fixedSize`.
    /// That guarantees whole words and makes the row's real ink visible to the
    /// layout, and `ViewThatFits` then picks the widest arm that actually fits:
    /// roomy padding, else compact, else a horizontal scroller.
    ///
    /// **NO SECOND COPY OF THE ARITHMETIC.** There is deliberately no width model
    /// here to compare against — `ViewThatFits` measures the real chips at the real
    /// Dynamic Type size, so it cannot drift from a literal the way #3817's
    /// per-character bound did. `EvolutionControlBarLayoutTests` hosts these very
    /// views and asserts the row is ONE line tall at 375 and 402 across the
    /// vocabulary, including the mid-tournament `Event` variant.
    ///
    /// **`minimumScaleFactor` was measured and rejected** before this — see
    /// `CalibrationSourceTableGeometry`: SwiftUI scales sibling `Text` together, so
    /// it shrinks every chip in the row to half-rescue one, and still truncates.
    private var controlBar: some View {
        EvolutionControlBar(
            availableRanges: availableRanges,
            selectedRange: $selectedRange,
            showCombinedProbability: $showCombinedProbability,
            topFilter: $topFilter,
            onRangeChange: {
                crosshair = nil
                Task { await loadData() }
            }
        )
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
        // #4373 — sized ONCE, here, off the outcomes this render is about to draw,
        // and handed to the header and every row. Two callers measuring separately
        // is how a header stops sitting over its own column.
        let columns = EvolutionLeaderboardGeometry.columns(
            for: displayedOutcomes, at: dynamicTypeSize)

        return VStack(spacing: 0) {
            EvolutionLeaderboardHeader(columns: columns)

            Divider()

            ForEach(Array(displayedOutcomes.enumerated()), id: \.element.name) { index, outcome in
                let isSelected = effectiveSelected.contains(outcome.name)
                let isHighlighted = highlightedName == nil || highlightedName == outcome.name
                let color = colorForOutcome(name: outcome.name, index: index)

                Button {
                    toggleSelection(outcome.name)
                } label: {
                    EvolutionLeaderboardRow(
                        position: index + 1,
                        outcome: outcome,
                        color: color,
                        isSelected: isSelected,
                        isHighlighted: isHighlighted,
                        columns: columns)
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

// MARK: - Control Bar

/// The Evolution chart's control bar, as its own view so the suite can host and
/// measure the real thing rather than a model of it (#4199).
/// The leaderboard's column headings.
///
/// Extracted with `EvolutionLeaderboardRow` (#4373) so the header and the rows are
/// the same two widths by construction rather than by two people remembering to
/// change both — the previous pair of `50`s had already stopped matching what was
/// under them.
struct EvolutionLeaderboardHeader: View {
    let columns: EvolutionLeaderboardGeometry.Columns

    var body: some View {
        HStack {
            Text("#")
                .frame(width: 24, alignment: .leading)
            Text("Participant")
            Spacer()
            Text("Prob")
                .frame(width: columns.prob, alignment: .trailing)
            if let change = columns.change {
                Text("24h")
                    .frame(width: change, alignment: .trailing)
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .padding(.horizontal)
        .padding(.vertical, 6)
        .background(Color.cardBackground.opacity(0.5))
    }
}

/// One leaderboard row: position, participant, probability, 24-hour change.
///
/// 🔴 #4373 — THE MINI BAR IS GONE FROM THE `Prob` CELL, and that is the fix.
/// `EvolutionLeaderboardGeometry` carries the measurements; the short version is
/// that a 50pt cell spent 28 of its points on a 24pt bar and left 22 for a number
/// that needs 43.5, so the number wrapped its percent sign onto a second line on
/// every row of every leaderboard at every width.
///
/// The number is `lineLimit(1)` as well as measured. The measurement is what makes
/// it fit; the line limit is what makes a future miss show up as a clipped digit
/// rather than as this defect coming quietly back.
struct EvolutionLeaderboardRow: View {
    let position: Int
    let outcome: TimelineOutcomeMeta
    let color: Color
    let isSelected: Bool
    let isHighlighted: Bool
    let columns: EvolutionLeaderboardGeometry.Columns

    private var probPct: Double { (outcome.currentProbability ?? 0) * 100 }
    private var changePct: Double { (outcome.probabilityChange24h ?? 0) * 100 }

    var body: some View {
        HStack(spacing: 6) {
            // Position + color dot
            HStack(spacing: 4) {
                Circle()
                    .fill(color)
                    .frame(width: 6, height: 6)
                    .opacity(isSelected ? 1 : 0.3)
                Text("\(position)")
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

            Text(EvolutionLeaderboardGeometry.probLabel(probPct))
                .font(.subheadline)
                .fontWeight(.semibold)
                .monospacedDigit()
                .lineLimit(1)
                .foregroundStyle(.primary)
                .frame(width: columns.prob, alignment: .trailing)

            if let change = columns.change {
                Text(EvolutionLeaderboardGeometry.changeLabel(changePct))
                    .font(.caption)
                    .fontWeight(.medium)
                    .monospacedDigit()
                    .lineLimit(1)
                    .foregroundStyle(
                        changePct > 0 ? .green :
                        changePct < 0 ? .red : .secondary
                    )
                    .frame(width: change, alignment: .trailing)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(isSelected ? Color.accentColor.opacity(0.05) : Color.clear)
        // The delta leaves the SCREEN at accessibility sizes, never the row. Said
        // as one sentence because four separate elements is four swipes to learn
        // one line of a table.
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            "\(position). \(outcome.name), "
            + "\(EvolutionLeaderboardGeometry.probLabel(probPct)), "
            + EvolutionLeaderboardGeometry.spokenChange(changePct))
    }
}

struct EvolutionControlBar: View {
    /// Chip padding for the two single-row arms, roomiest first.
    ///
    /// 🔴 THERE IS NO PADDING THAT FITS EIGHT CHIPS ON ONE ROW AT 375pt, and finding
    /// that out is what the third arm below exists for. Measured by
    /// `EvolutionControlBarLayoutTests`: the four-range bar wants ~399pt at 8pt
    /// padding and ~351pt at 5pt, while the card on an iPhone SE gives the bar about
    /// **310pt**. Even zero padding leaves ~271pt of pure ink plus the checkbox and
    /// the group gaps. A third rung at 4pt was tried and photographed: it still
    /// overflowed, and `ViewThatFits` fell through to a horizontal scroller that put
    /// `Top 20` off the right edge — the same defect, quieter.
    static let chipPaddings: [CGFloat] = [8, 5]

    let availableRanges: [EvolutionTimeRange]
    @Binding var selectedRange: EvolutionTimeRange
    @Binding var showCombinedProbability: Bool
    @Binding var topFilter: Int
    var onRangeChange: () -> Void = {}

    var body: some View {
        VStack(spacing: 8) {
            ViewThatFits(in: .horizontal) {
                row(chipPadding: Self.chipPaddings[0])
                row(chipPadding: Self.chipPaddings[1])
                stackedRows(chipPadding: Self.chipPaddings[0])
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color.cardBackground.opacity(0.5))
    }

    /// The three groups, defined once. Every arm composes THESE, so no arm can
    /// disagree with another about what the bar contains or how a chip is drawn —
    /// the one-row and two-row layouts differ only in where the groups are put.
    ///
    /// Each chip carries `lineLimit(1)` AND `fixedSize`. The pair is the whole fix:
    /// `lineLimit` alone turns wrapping into truncation, which loses the same
    /// information (#3966), and `fixedSize` alone would still let a chip wrap.
    ///
    /// Exposed to the suite so a test can measure a chosen arm directly — asking
    /// `ViewThatFits` which one it picked is not something a test can do.
    @ViewBuilder
    func rangeGroup(chipPadding: CGFloat) -> some View {
        HStack(spacing: 0) {
            ForEach(availableRanges) { range in
                Button {
                    selectedRange = range
                    onRangeChange()
                } label: {
                    Text(range.rawValue)
                        .font(.caption2)
                        .fontWeight(selectedRange == range ? .semibold : .regular)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .padding(.horizontal, chipPadding)
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

    @ViewBuilder
    func sumToggle(chipPadding: CGFloat) -> some View {
        Button {
            showCombinedProbability.toggle()
        } label: {
            HStack(spacing: 4) {
                Image(systemName: showCombinedProbability ? "checkmark.square.fill" : "square")
                    .font(.system(size: 11))
                Text("Sum")
                    .font(.caption2)
                    .fontWeight(.medium)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            .padding(.horizontal, chipPadding)
            .padding(.vertical, 5)
            .foregroundStyle(showCombinedProbability ? .blue : .secondary)
        }
    }

    @ViewBuilder
    func topGroup(chipPadding: CGFloat) -> some View {
        HStack(spacing: 0) {
            ForEach([5, 10, 20], id: \.self) { n in
                Button {
                    topFilter = n
                } label: {
                    Text("Top \(n)")
                        .font(.caption2)
                        .fontWeight(.medium)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                        .padding(.horizontal, chipPadding)
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

    /// All three groups on one row — the layout the bar has always had, now with
    /// chips that keep their words.
    @ViewBuilder
    func row(chipPadding: CGFloat) -> some View {
        HStack(spacing: 8) {
            rangeGroup(chipPadding: chipPadding)
            Spacer(minLength: 0)
            sumToggle(chipPadding: chipPadding)
            topGroup(chipPadding: chipPadding)
        }
    }

    /// 🔴 THE ARM THAT MAKES THE NARROW PHONE HONEST. Ranges above, `Sum` and the
    /// `Top N` group below. Its width is the wider of the two rows rather than the
    /// sum of all three groups, so it fits any phone — which is why it is the LAST
    /// arm and why there is no scroller behind it: a terminal arm that always fits
    /// leaves no case for one, and a fallback that can never be reached is a branch
    /// nobody will ever have tested.
    ///
    /// A second ROW is not the defect this ship fixes. #4199 is about words broken
    /// mid-syllable — `Se/aso/n` — not about a control that takes two lines. Every
    /// chip here is whole, on one line, and on screen; nothing is truncated and
    /// nothing has to be scrolled to.
    @ViewBuilder
    func stackedRows(chipPadding: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                rangeGroup(chipPadding: chipPadding)
                Spacer(minLength: 0)
            }
            HStack(spacing: 8) {
                sumToggle(chipPadding: chipPadding)
                topGroup(chipPadding: chipPadding)
                Spacer(minLength: 0)
            }
        }
    }
}
