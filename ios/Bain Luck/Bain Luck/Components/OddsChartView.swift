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
    /// Delta from 50% for mirrored Y-axis (home positive, away negative)
    var delta: Double { probability - 0.5 }
    // Game state carried through for play-by-play card
    var homeScore: Int?
    var awayScore: Int?
    var period: String?
    var clock: String?
    var scoringPlay: ScoringPlay?
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
    var homeTeamName: String?
    var awayTeamName: String?
    var homeTeamLogo: String?
    var awayTeamLogo: String?
    var homeTeamAbbrev: String?
    var awayTeamAbbrev: String?
    /// Binding to expose the selected game play point (for GamePlayCardView)
    @Binding var selectedPlayPoint: GamePlayPoint?
    @StateObject private var vm: OddsChartViewModel
    @State private var selectedDate: Date?
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var chartHeight: CGFloat {
        sizeClass == .regular ? 380 : 260
    }

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

    /// Short team name: prefer ESPN abbreviation (e.g. "BOS"), fall back to last word
    private var homeShort: String {
        homeTeamAbbrev ?? homeTeamName?.split(separator: " ").last.map(String.init) ?? "Home"
    }
    private var awayShort: String {
        awayTeamAbbrev ?? awayTeamName?.split(separator: " ").last.map(String.init) ?? "Away"
    }

    init(eventId: Int, teamColors: (away: Color, home: Color)? = nil,
         commenceTime: String? = nil, status: String? = nil,
         homeTeamName: String? = nil, awayTeamName: String? = nil,
         homeTeamLogo: String? = nil, awayTeamLogo: String? = nil,
         homeTeamAbbrev: String? = nil, awayTeamAbbrev: String? = nil,
         selectedPlayPoint: Binding<GamePlayPoint?> = .constant(nil),
         preloadedHistory: EventHistoryResponse? = nil) {
        self.eventId = eventId
        self.teamColors = teamColors
        self.commenceTime = commenceTime
        self.status = status
        self.homeTeamName = homeTeamName
        self.awayTeamName = awayTeamName
        self.homeTeamLogo = homeTeamLogo
        self.awayTeamLogo = awayTeamLogo
        self.homeTeamAbbrev = homeTeamAbbrev
        self.awayTeamAbbrev = awayTeamAbbrev
        _selectedPlayPoint = selectedPlayPoint
        _vm = StateObject(wrappedValue: OddsChartViewModel(eventId: eventId, preloaded: preloadedHistory))
    }

    var body: some View {
        VStack(spacing: 8) {
            // Chart title + status + time range picker
            HStack {
                Text("Win Probability")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(.primary)
                if status == "live" {
                    HStack(spacing: 4) {
                        Circle().fill(.green).frame(width: 6, height: 6)
                        Text("Live").font(.caption2).fontWeight(.medium).foregroundStyle(.green)
                    }
                } else if status == "completed" || status == "closed" {
                    HStack(spacing: 4) {
                        Circle().fill(.secondary).frame(width: 6, height: 6)
                        Text("Final").font(.caption2).fontWeight(.medium).foregroundStyle(.secondary)
                    }
                }
                Spacer()
                if showPicker {
                    timeRangePicker
                }
            }

            if vm.loading {
                ProgressView()
                    .frame(height: chartHeight)
            } else if let error = vm.error {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .frame(height: chartHeight)
            } else if let history = vm.history {
                let allPoints = buildDataPoints(history)
                let enrichedPoints = enrichWithGameState(allPoints, history: history)
                let dataPoints = filterPoints(enrichedPoints)
                let periodMarkers = extractPeriodMarkers(history, filteredPoints: dataPoints)
                if dataPoints.isEmpty {
                    Text("No odds data available")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(height: chartHeight)
                } else {
                    // Chart with vertical team labels alongside Y-axis
                    HStack(spacing: 0) {
                        // Vertical team labels on left
                        VStack {
                            // Home team (top)
                            HStack(spacing: 2) {
                                if let logo = homeTeamLogo, let url = URL(string: logo) {
                                    AsyncImage(url: url) { img in
                                        img.resizable().scaledToFit()
                                    } placeholder: { EmptyView() }
                                    .frame(width: 10, height: 10)
                                }
                                Text(homeShort.uppercased())
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundStyle(teamColors?.home ?? .blue)
                                    .lineLimit(1)
                            }
                            .fixedSize()
                            .rotationEffect(.degrees(-90))
                            Spacer()
                            // Away team (bottom)
                            HStack(spacing: 2) {
                                if let logo = awayTeamLogo, let url = URL(string: logo) {
                                    AsyncImage(url: url) { img in
                                        img.resizable().scaledToFit()
                                    } placeholder: { EmptyView() }
                                    .frame(width: 10, height: 10)
                                }
                                Text(awayShort.uppercased())
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundStyle(teamColors?.away ?? .red)
                                    .lineLimit(1)
                            }
                            .fixedSize()
                            .rotationEffect(.degrees(-90))
                        }
                        .frame(width: 20)
                        .padding(.vertical, 8)

                        chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:], periodMarkers: periodMarkers)
                            .onChange(of: selectedDate) { _, newDate in
                                updateSelectedPoint(date: newDate, dataPoints: dataPoints, history: history)
                            }
                    }
                    .frame(height: chartHeight)

                    legendView(dataPoints: dataPoints, sources: history.winProbSources ?? [:])
                }
            }
        }
        .padding()
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
    /// Uses a firstSeen dictionary to produce exactly one marker per unique
    /// normalized period label (e.g., Q1, Q2, Q3, Q4 for basketball).
    /// Matches the web's `derivePeriodBoundaries()` approach.
    /// Adds a Q1/P1/1H marker at game commence time if ESPN data starts later.
    private func extractPeriodMarkers(_ history: EventHistoryResponse, filteredPoints: [ChartDataPoint]) -> [PeriodMarker] {
        var firstSeen: [(label: String, date: Date)] = []
        var seenLabels: Set<String> = []

        // Try ESPN history first (has explicit period field)
        if let espnHistory = history.espnHistory, espnHistory.count >= 2 {
            let sorted = espnHistory
                .compactMap { point -> (period: String, date: Date)? in
                    guard let period = point.period, !period.isEmpty,
                          let date = point.timestamp.asDate else { return nil }
                    return (period, date)
                }
                .sorted { $0.date < $1.date }

            for point in sorted {
                let label = normalizePeriodLabel(point.period)
                guard !label.isEmpty, !seenLabels.contains(label) else { continue }
                seenLabels.insert(label)
                firstSeen.append((label, point.date))
            }
        }

        // If ESPN data doesn't include the first period, add one at game commence time.
        // This ensures e.g. Q1 always appears even if ESPN sync started in Q2.
        if isGameStarted, let startDate = gameStartDate, !firstSeen.isEmpty {
            let firstPeriodLabel = inferFirstPeriodLabel(from: firstSeen.map(\.label))
            if let firstPeriodLabel, !seenLabels.contains(firstPeriodLabel) {
                firstSeen.insert((firstPeriodLabel, startDate), at: 0)
            }
        }

        return firstSeen
            .sorted { $0.date < $1.date }
            .map { PeriodMarker(date: $0.date, label: $0.label, isGameStart: false) }
    }

    /// Infer the first period label from existing labels.
    /// If we see Q2, Q3, Q4 → the missing first is Q1.
    /// If we see P2, P3 → the missing first is P1.
    /// If we see 2H → the missing first is 1H.
    private func inferFirstPeriodLabel(from labels: [String]) -> String? {
        guard let first = labels.first else { return nil }
        if first.hasPrefix("Q") && first != "Q1" { return "Q1" }
        if first.hasPrefix("P") && first != "P1" { return "P1" }
        if first.hasSuffix("H") && first != "1H" { return "1H" }
        // Baseball: if first inning marker is "2" or higher
        if let num = Int(first), num > 1 { return "1" }
        return nil
    }

    // MARK: - Chart

    private func chartView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo], periodMarkers: [PeriodMarker]) -> some View {
        let uniqueSources = Set(dataPoints.map(\.source)).sorted()

        // Filter period markers to visible data range
        let visibleMarkers: [PeriodMarker]
        if let minDate = dataPoints.map(\.date).min(),
           let maxDate = dataPoints.map(\.date).max() {
            visibleMarkers = periodMarkers.filter { $0.date >= minDate && $0.date <= maxDate }
        } else {
            visibleMarkers = periodMarkers
        }

        // Mirrored Y-axis: compute delta range with symmetric padding
        let deltas = dataPoints.map(\.delta)
        let absMax = max(abs(deltas.min() ?? 0), abs(deltas.max() ?? 0), 0.05)
        let yPad = absMax * 0.1
        let yMin = -(absMax + yPad)
        let yMax = absMax + yPad

        return Chart {
            // 50% reference line (at delta = 0)
            RuleMark(y: .value("Even", 0.0))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [4, 4]))
                .foregroundStyle(.gray.opacity(0.4))

            // Selection indicator
            if let selectedDate {
                RuleMark(x: .value("Selected", selectedDate))
                    .lineStyle(StrokeStyle(lineWidth: 1.0))
                    .foregroundStyle(.primary.opacity(0.4))
            }

            // Period marker lines (one per period: Q1, Q2, Q3, Q4 etc.)
            ForEach(visibleMarkers) { marker in
                RuleMark(x: .value("Period", marker.date))
                    .lineStyle(StrokeStyle(lineWidth: 1.0, dash: [5, 5]))
                    .foregroundStyle(.secondary.opacity(0.4))
                    .annotation(position: .overlay, alignment: .topLeading, spacing: 0) {
                        Text(marker.label)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 3)
                            .padding(.vertical, 1)
                            .padding(.top, 2)
                    }
            }

            // Data lines
            ForEach(uniqueSources, id: \.self) { source in
                let points = dataPoints.filter { $0.source == source }
                ForEach(points) { point in
                    LineMark(
                        x: .value("Time", point.date),
                        y: .value("Delta", point.delta),
                        series: .value("Source", source)
                    )
                    .foregroundStyle(colorForSource(source, sources: sources))
                    .lineStyle(strokeStyleForSource(source, sources: sources))
                    .interpolationMethod(.monotone)
                }
            }
        }
        .chartYScale(domain: yMin...yMax)
        .chartXScale(domain: xAxisDomain(for: dataPoints))
        .chartYAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.3))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        let pct = Int(50 + abs(v * 100))
                        Text("\(pct)%")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(format: .dateTime.hour().minute(), anchor: .top)
                    .font(.caption2)
            }
        }
        .chartXSelection(value: $selectedDate)
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

        return FlowLayout(spacing: 8) {
            ForEach(ordered, id: \.self) { source in
                let isPrimary = source == "aggregate" || (source == "consensus" && !ordered.contains("aggregate"))
                HStack(spacing: 4) {
                    if isPrimary {
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
            // - "aggregate" = Bain Luck combined line (bold primary)
            // - "consensus" = sportsbook mean (shown at reduced opacity)
            // - other sources: ESPN, Kalshi, Polymarket, model, etc.

            // Sportsbook consensus
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

            // Prefer backend aggregate line (weighted median with staleness decay);
            // fall back to naive client-side averaging (matches web behavior).
            if let aggregateLine = history.aggregateLine, !aggregateLine.isEmpty {
                for p in aggregateLine {
                    guard let date = p.timestamp.asDate else { continue }
                    points.append(ChartDataPoint(date: date, probability: p.homeProbability, source: "aggregate"))
                }
            } else {
                // Fallback: average all available source values at each minute bucket
                let nonAggPoints = points // all points added so far (consensus + other sources)
                var buckets: [Int: [Double]] = [:] // minute-bucket → probabilities
                var bucketDates: [Int: Date] = [:]
                for p in nonAggPoints {
                    let bucket = Int(p.date.timeIntervalSince1970 / 60)
                    buckets[bucket, default: []].append(p.probability)
                    if bucketDates[bucket] == nil { bucketDates[bucket] = p.date }
                }
                for (bucket, values) in buckets {
                    let avg = values.reduce(0, +) / Double(values.count)
                    if let date = bucketDates[bucket] {
                        points.append(ChartDataPoint(date: date, probability: avg, source: "aggregate"))
                    }
                }
            }
        } else {
            // Sportsbooks-only mode:
            // - "consensus" = sportsbook mean (bold primary, the only aggregation)
            for h in history.history {
                guard let date = h.timestamp.asDate,
                      let prob = h.homeProbability else { continue }
                points.append(ChartDataPoint(date: date, probability: prob, source: "consensus"))
            }
        }

        return points
    }

    // MARK: - Game State Enrichment

    /// Enrich chart data points with game state (score, period, clock, scoring play)
    /// by matching against ESPN history and scoring plays, then forward-filling.
    private func enrichWithGameState(_ points: [ChartDataPoint], history: EventHistoryResponse) -> [ChartDataPoint] {
        // Build time-indexed lookups from ESPN history
        var espnByTime: [(date: Date, point: ESPNHistoryPoint)] = []
        for ep in history.espnHistory ?? [] {
            if let date = ep.timestamp.asDate {
                espnByTime.append((date, ep))
            }
        }
        espnByTime.sort { $0.date < $1.date }

        // Build scoring plays lookup
        var playsByTime: [(date: Date, play: ScoringPlay)] = []
        for sp in history.scoringPlays ?? [] {
            if let ts = sp.timestamp, let date = ts.asDate {
                playsByTime.append((date, sp))
            }
        }
        playsByTime.sort { $0.date < $1.date }

        // Sort points by time for forward-fill
        var sorted = points.sorted { $0.date < $1.date }
        var lastScore: (home: Int, away: Int)?
        var lastPeriod: String?
        var lastClock: String?

        for i in sorted.indices {
            let pointDate = sorted[i].date

            // Find nearest ESPN history point (within 90s)
            if let nearest = espnByTime.last(where: { $0.date <= pointDate.addingTimeInterval(90) }) {
                if let hs = nearest.point.homeScore { lastScore = (hs, nearest.point.awayScore ?? lastScore?.away ?? 0) }
                if let p = nearest.point.period, !p.isEmpty { lastPeriod = p }
                if let c = nearest.point.gameClock, !c.isEmpty { lastClock = c }
            }

            // Forward-fill game state
            sorted[i].homeScore = lastScore?.home
            sorted[i].awayScore = lastScore?.away
            sorted[i].period = lastPeriod
            sorted[i].clock = lastClock

            // Check for scoring play at this timestamp (within 60s)
            sorted[i].scoringPlay = playsByTime.first(where: {
                abs($0.date.timeIntervalSince(pointDate)) < 60
            })?.play
        }

        return sorted
    }

    /// Update the selected play point binding based on chart selection.
    private func updateSelectedPoint(date: Date?, dataPoints: [ChartDataPoint], history: EventHistoryResponse) {
        guard let date else {
            selectedPlayPoint = nil
            return
        }

        // Find the primary source points (aggregate or consensus)
        let primarySource = dataPoints.contains(where: { $0.source == "aggregate" }) ? "aggregate" : "consensus"
        let primaryPoints = dataPoints.filter { $0.source == primarySource }.sorted { $0.date < $1.date }

        // Find nearest point
        guard let nearest = primaryPoints.min(by: {
            abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date))
        }) else {
            selectedPlayPoint = nil
            return
        }

        selectedPlayPoint = GamePlayPoint(
            timestamp: nearest.date.ISO8601Format(),
            homeProb: nearest.probability,
            awayProb: 1.0 - nearest.probability,
            homeScore: nearest.homeScore,
            awayScore: nearest.awayScore,
            period: nearest.period,
            clock: nearest.clock,
            scoringPlay: nearest.scoringPlay
        )
    }

    // MARK: - Source Styling

    private func colorForSource(_ source: String, sources: [String: WinProbSourceInfo]) -> Color {
        let hasAggregate = vm.history?.aggregateLine != nil && isMultiSource(vm.history!)
        let baseColor: Color

        switch source {
        case "aggregate": return Color(hex: "#059669") // Emerald green, always full opacity
        case "consensus": baseColor = teamColors?.home ?? .blue
        default:
            if let info = sources[source], let hex = info.color {
                baseColor = Color(hex: hex)
            } else {
                // Fallback colors for known sources
                switch source {
                case "espn": baseColor = .orange
                case "bainluck_model": baseColor = .purple
                case "kalshi": baseColor = Color(hex: "#22c55e")
                case "polymarket": baseColor = Color(hex: "#3b82f6")
                case "mlb": baseColor = Color(hex: "#0d9488")
                default: baseColor = .gray
                }
            }
        }

        // When aggregate is present, secondary sources render at reduced opacity
        // to match web behavior where non-primary lines are semi-transparent
        return hasAggregate ? baseColor.opacity(0.5) : baseColor
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
        // Aggregate line — just "Bain Luck" with no type suffix (matches web)
        if source == "aggregate" { return "Bain Luck" }

        // Resolve display name
        let name: String
        let type: String
        switch source {
        case "consensus":
            name = "Betting Odds"
            type = "market"
        default:
            name = sources[source]?.displayName ?? fallbackDisplayName(source)
            type = sources[source]?.type ?? fallbackType(source)
        }

        // Add type suffix like web: "Kalshi (market)", "ESPN (model)"
        return "\(name) (\(type))"
    }

    /// Fallback display names matching web's FALLBACK_SOURCE_CONFIG
    private func fallbackDisplayName(_ source: String) -> String {
        switch source {
        case "espn": return "ESPN"
        case "stat_model", "bainluck_model": return "Bain Luck Model"
        case "kalshi": return "Kalshi"
        case "polymarket": return "Polymarket"
        case "mlb": return "MLB Model"
        default: return source.capitalized
        }
    }

    /// Fallback source types matching web's FALLBACK_SOURCE_CONFIG
    private func fallbackType(_ source: String) -> String {
        switch source {
        case "espn", "stat_model", "bainluck_model", "mlb":
            return "model"
        case "kalshi", "polymarket":
            return "market"
        default:
            return "model"
        }
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
    /// Matches web's normalizePeriodLabel() in periodMarkers.ts
    private func normalizePeriodLabel(_ raw: String) -> String {
        var s = raw.trimmingCharacters(in: .whitespaces)

        // Reject pre-game date strings like "Wed, March 25th at 10:00 PM EDT"
        // These leak from ESPN status_detail during game transitions
        let months = "January|February|March|April|May|June|July|August|September|October|November|December"
        if s.range(of: months, options: [.regularExpression, .caseInsensitive]) != nil { return "" }
        if s.range(of: #"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\bat\b"#, options: [.regularExpression, .caseInsensitive]) != nil { return "" }

        // Strip clock prefix: "11:05 - 1st Quarter" → "1st Quarter"
        if let dashRange = s.range(of: #"^[\d.:]+\s*-\s*"#, options: .regularExpression) {
            s = String(s[dashRange.upperBound...])
        }

        // Strip "End of " / "Start of " prefix
        if let prefixRange = s.range(of: #"^(?:end|start)\s+of\s+"#, options: [.regularExpression, .caseInsensitive]) {
            s = String(s[prefixRange.upperBound...])
        }

        let lower = s.lowercased()

        // Halftime
        if lower == "halftime" || lower == "half time" || lower == "ht" { return "HT" }

        // Overtime variants
        if lower == "overtime" || lower == "ot" { return "OT" }
        if let match = lower.range(of: #"^(\d+)\w*\s+overtime$"#, options: .regularExpression) {
            let digits = s[match].filter(\.isNumber)
            return "OT\(digits)"
        }

        // Basketball / Football quarters: "1st Quarter" → "Q1"
        if let match = s.range(of: #"^(\d+)\w*\s+[Qq]uarter$"#, options: .regularExpression) {
            let digits = s[match].filter(\.isNumber)
            return "Q\(digits)"
        }
        // Plain ordinals for quarters
        if lower == "1st" { return "Q1" }
        if lower == "2nd" { return "Q2" }
        if lower == "3rd" { return "Q3" }
        if lower == "4th" { return "Q4" }

        // Hockey periods: "1st Period" → "P1"
        if let match = s.range(of: #"^(\d+)\w*\s+[Pp]eriod$"#, options: .regularExpression) {
            let digits = s[match].filter(\.isNumber)
            return "P\(digits)"
        }

        // Soccer halves: "1st Half" → "1H"
        if let match = s.range(of: #"^(\d+)\w*\s+[Hh]alf$"#, options: .regularExpression) {
            let digits = s[match].filter(\.isNumber)
            return "\(digits)H"
        }

        // Baseball innings: "Top 3rd" / "Bottom 3rd" / "Mid 3rd" → "3"
        if let match = s.range(of: #"^(?:top|bottom|mid|end)\s+(\d+)"#, options: [.regularExpression, .caseInsensitive]) {
            let digits = s[match].filter(\.isNumber)
            return digits
        }

        // Plain ordinal inning: "3rd" → "3"
        if let match = s.range(of: #"^(\d+)(?:st|nd|rd|th)$"#, options: [.regularExpression, .caseInsensitive]) {
            let digits = s[match].filter(\.isNumber)
            return digits
        }

        // Already short: "Q1", "P2", "1H", "OT", "OT1", etc.
        if s.range(of: #"^(Q\d|P\d|\d+H|OT\d?|HT|\d+)$"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return s.uppercased()
        }

        // Intermission
        if lower.contains("intermission") { return "INT" }

        return s
    }
}
