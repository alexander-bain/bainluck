import SwiftUI
import Charts
import Combine
import os

private let logger = Logger(subsystem: "com.bainluck", category: "oddsChart")

// MARK: - Chart Data Point

/// One observed probability point for the win-probability chart.
/// Internal (not private) so the pure `OddsChartView.chartPoints(from:)` transform
/// can be unit-tested — SwiftUI bodies aren't rendered in tests (see BainLuckTests).
struct ChartDataPoint: Identifiable {
    let id = UUID()
    let date: Date
    /// The plotted value IS the home win probability (0.0–1.0), read straight up a
    /// single 0–100 axis (L2-216). This replaced the old mirrored ±50 delta, where the
    /// same "80%" appeared both above and below center; native now matches the web's
    /// single 0–100 blended axis (L2-131).
    let probability: Double
    let source: String
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

/// UX-P090 — the minimum separation between two period chips, as a fraction of the
/// chart's duration (equivalently, of its width — the x-axis is linear).
///
/// Named and non-private so the geometry that justifies it can be asserted in a
/// test rather than only argued in a comment: a chip is ~28pt wide on a ~345pt
/// plot area, so anything below ~8.3% draws chips that overlap. See the derivation
/// at the call site in `extractPeriodMarkers`.
enum PeriodChipGeometry {
    /// Widest realistic chip: 2 characters at size 10 bold (~20pt) + 4pt padding
    /// each side. Two-digit innings ("10") are reachable since #1831's 1…N ladder.
    static let chipWidthPoints: Double = 28
    /// Plot area on a common phone layout: 393pt screen − 32pt card padding −
    /// 24pt rotated team-label gutter = 337pt. Asserted against those three
    /// numbers in `EventScreenLayoutTests`, so it cannot drift into a fiction that
    /// the spacing fraction below is then derived from.
    static let plotWidthPoints: Double = 337
    /// The fraction actually applied — DERIVED, not a hand-picked literal.
    ///
    /// It was briefly written as `0.09`, "the derived 8.3% rounded up for safety",
    /// and the round-up was not safe: it is an absolute threshold in disguise, and
    /// on a LONG chart it grows past the real gap between periods. A 12-inning game
    /// over four hours has innings 1,200s apart against a 9% threshold of 1,296s,
    /// so the padding would have deleted a real inning chip — trading an overlap
    /// defect for a missing-data defect. `EventScreenLayoutTests` caught it.
    ///
    /// Keeping it exactly `chipWidth / plotWidth` is what makes it a pure
    /// no-overlap rule: it drops a chip if and only if there is genuinely no room
    /// for one, which is the most information the strip can carry without
    /// collisions. Beyond about 12 periods there IS no room, and dropping is then
    /// the correct behaviour rather than a compromise.
    static var minSpacingFraction: Double { chipWidthPoints / plotWidthPoints }
}

/// UX-P090 — the width of the rotated home/away team gutter to the left of the
/// plot area. Named because THREE things must agree on it: the inline chart row,
/// the fullscreen chart row, and the legend's leading indent. When it was a bare
/// `24` in two places and absent from the third, the legend sat 24pt to the left
/// of the data it labels.
let chartTeamGutterWidth: CGFloat = 24

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
    /// Countdown seconds until next data refresh (0 = just refreshed)
    var refreshCountdown: Int = 0
    /// Total refresh interval in seconds
    var refreshInterval: Int = 30
    /// True while the live push stream is delivering, in which case the poll is
    /// stood down and there is no next update to count down to (#2687).
    var refreshStreaming: Bool = false
    /// Shared domain from parent — ensures OddsChart and ScoreDiffChart have identical x-axes
    var forcedDomain: ClosedRange<Date>?
    /// Binding to expose the selected game play point (for GamePlayCardView)
    @Binding var selectedPlayPoint: GamePlayPoint?
    @StateObject private var vm: OddsChartViewModel
    @State private var selectedDate: Date?
    @State private var isFullscreen = false
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var chartHeight: CGFloat {
        guard sizeClass == .regular else { return 260 }
        // Medium breakpoint (~320pt) for iPad Air landscape / split-view
        #if os(iOS)
        let bounds = UIScreen.main.bounds
        if bounds.width > bounds.height { return 320 }
        #endif
        return 380
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
         refreshCountdown: Int = 0, refreshInterval: Int = 30,
         refreshStreaming: Bool = false,
         forcedDomain: ClosedRange<Date>? = nil,
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
        self.refreshCountdown = refreshCountdown
        self.refreshInterval = refreshInterval
        self.refreshStreaming = refreshStreaming
        self.forcedDomain = forcedDomain
        _selectedPlayPoint = selectedPlayPoint
        _vm = StateObject(wrappedValue: OddsChartViewModel(eventId: eventId, preloaded: preloadedHistory))
    }

    var body: some View {
        VStack(spacing: 8) {
            // Chart title + status + time range picker.
            //
            // UX-P090 — THIS ROW WAS EXACTLY AT ITS LIMIT AND HAD NOWHERE TO GO.
            // Measured on a LIVE game (the state with the most in the row): title
            // ~105 + "Live" chip ~46 + the two-segment picker ~125 + countdown ring
            // 20 + fullscreen button 24 + ~40 of HStack gaps = ~360pt, against
            // 361pt of usable width on an iPhone 16 and 343pt on an SE. One point
            // of headroom on the common phone and 17pt of overflow on the small
            // one — so SwiftUI resolved it the only way it can in a fixed HStack,
            // by compressing and truncating the title.
            //
            // #1772 is what makes this urgent rather than cosmetic: Dynamic Type
            // now actually scales this text, so every step above the default size
            // pushes a row that had one point of slack further into truncation.
            //
            // `ViewThatFits` picks the single row when it genuinely fits and drops
            // the picker to its own line when it does not. Nothing is hidden and
            // nothing is truncated at any type size — the row reflows, which is
            // what the fixed HStack could not do.
            ViewThatFits(in: .horizontal) {
                HStack {
                    chartTitleAndStatus
                    Spacer()
                    if showPicker { timeRangePicker }
                    chartHeaderTrailingControls
                }
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        chartTitleAndStatus
                        Spacer()
                        chartHeaderTrailingControls
                    }
                    if showPicker {
                        HStack {
                            timeRangePicker
                            Spacer()
                        }
                    }
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
                    Text("No probability data available")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .frame(height: chartHeight)
                } else {
                    // Chart with vertical team labels alongside Y-axis
                    HStack(spacing: 0) {
                        // Vertical team labels on left (#2903 — the run is stated so
                        // a long name truncates instead of clipping, and the gutter
                        // reserves the rotated footprint instead of overdrawing the
                        // section heading beside it).
                        VStack {
                            let run = ChartGutter.run(chartHeight: chartHeight, verticalPadding: 8)
                            // Home team (top)
                            ChartGutterLabel(run: run) {
                                HStack(spacing: 3) {
                                    if let logo = homeTeamLogo, let url = URL(string: logo) {
                                        AsyncImage(url: url) { img in
                                            img.resizable().scaledToFit()
                                        } placeholder: { EmptyView() }
                                        .frame(width: 14, height: 14)
                                    }
                                    Text(homeShort.uppercased())
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(teamColors?.home ?? .blue)
                                        .lineLimit(1)
                                }
                            }
                            Spacer()
                            // Away team (bottom)
                            ChartGutterLabel(run: run) {
                                HStack(spacing: 3) {
                                    if let logo = awayTeamLogo, let url = URL(string: logo) {
                                        AsyncImage(url: url) { img in
                                            img.resizable().scaledToFit()
                                        } placeholder: { EmptyView() }
                                        .frame(width: 14, height: 14)
                                    }
                                    Text(awayShort.uppercased())
                                        .font(.system(size: 11, weight: .bold))
                                        .foregroundStyle(teamColors?.away ?? .red)
                                        .lineLimit(1)
                                }
                            }
                        }
                        .frame(width: chartTeamGutterWidth)
                        .padding(.vertical, 8)

                        chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:], periodMarkers: periodMarkers)
                            .onChange(of: selectedDate) { _, newDate in
                                updateSelectedPoint(date: newDate, dataPoints: dataPoints, history: history)
                            }
                    }
                    .frame(height: chartHeight)

                    // UX-P090 — the legend hung off the card's left edge while the
                    // thing it describes started 24pt further in, behind the
                    // rotated team gutter. Two rows that belong to one chart, on
                    // two different left margins. Indenting by the SAME gutter
                    // width the chart row uses puts the legend under the plot area
                    // it labels; the 2pt lifts it off the x-axis tick labels, which
                    // sit flush against the bottom of the chart's own frame.
                    legendView(dataPoints: dataPoints, sources: history.winProbSources ?? [:])
                        .padding(.leading, chartTeamGutterWidth)
                        .padding(.top, 2)
                        .frame(maxWidth: .infinity, alignment: .leading)
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
        #if os(iOS)
        .fullScreenCover(isPresented: $isFullscreen) {
            fullscreenChart
        }
        #else
        .sheet(isPresented: $isFullscreen) {
            fullscreenChart
                .frame(minWidth: 800, minHeight: 500)
        }
        #endif
    }

    // MARK: - Fullscreen Chart

    private var fullscreenChart: some View {
        NavigationView {
            Group {
                if let history = vm.history {
                    let allPoints = buildDataPoints(history)
                    let enrichedPoints = enrichWithGameState(allPoints, history: history)
                    let dataPoints = filterPoints(enrichedPoints)
                    let periodMarkers = extractPeriodMarkers(history, filteredPoints: dataPoints)
                    if !dataPoints.isEmpty {
                        VStack(spacing: 8) {
                            if showPicker {
                                HStack {
                                    Spacer()
                                    timeRangePicker
                                    Spacer()
                                }
                            }
                            HStack(spacing: 0) {
                                // #2903 — fullscreen has no fixed chart height, so the
                                // run is measured rather than assumed.
                                GeometryReader { geo in
                                    let run = ChartGutter.run(chartHeight: geo.size.height, verticalPadding: 0)
                                    VStack {
                                        ChartGutterLabel(run: run) {
                                            Text(homeShort.uppercased())
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundStyle(teamColors?.home ?? .blue)
                                                .lineLimit(1)
                                        }
                                        Spacer()
                                        ChartGutterLabel(run: run) {
                                            Text(awayShort.uppercased())
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundStyle(teamColors?.away ?? .red)
                                                .lineLimit(1)
                                        }
                                    }
                                }
                                .frame(width: chartTeamGutterWidth)
                                .padding(.vertical, 12)

                                chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:], periodMarkers: periodMarkers)
                            }
                            legendView(dataPoints: dataPoints, sources: history.winProbSources ?? [:])
                        }
                        .padding()
                    }
                }
            }
            .navigationTitle("Win Probability")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                if status == "live" {
                    ToolbarItem(placement: .cancellationAction) {
                        refreshCountdownRing
                    }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button { isFullscreen = false } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    // MARK: - Time Range Picker

    // UX-P090 — extracted so the one-row and two-row header arms of `ViewThatFits`
    // are the SAME views in a different arrangement. Inlining them twice is how the
    // two arms drift, and a drift here is invisible: only one arm renders at a time,
    // on a screen size the author may not be testing.
    @ViewBuilder
    private var chartTitleAndStatus: some View {
        Text("Win Probability")
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundStyle(.primary)
            // The title is the one thing in this row that must never be clipped;
            // the picker and controls are all fixed-size, so without this SwiftUI
            // takes the space out of the only flexible child.
            .fixedSize(horizontal: false, vertical: true)
            .layoutPriority(1)
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
    }

    @ViewBuilder
    private var chartHeaderTrailingControls: some View {
        // Refresh countdown ring — only when an actual auto-refresh request
        // is scheduled, which the event VM installs for LIVE events only.
        // Scheduled/completed pages perform no periodic reload, so a cycling
        // countdown there would imply freshness work that never happens (C43 P2).
        if status == "live" {
            refreshCountdownRing
        }
        Button {
            isFullscreen = true
        } label: {
            Image(systemName: "arrow.up.left.and.arrow.down.right")
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .padding(6)
        }
    }

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

    // MARK: - Refresh Countdown Ring

    @ViewBuilder
    private var refreshCountdownRing: some View {
        // While the stream delivers there is no scheduled request, so a ring
        // counting to zero and stopping is chrome describing something that is
        // not happening — the same C43 defect the countdown was introduced to
        // fix, arriving from the push side.
        if refreshStreaming {
            LivePushDot(diameter: 22)
        } else {
            countdownRing
        }
    }

    private var countdownRing: some View {
        let total = max(refreshInterval, 1)
        let progress = Double(total - refreshCountdown) / Double(total)
        let ringColor: Color = status == "live" ? Color(hex: "#10B981") : .secondary

        return ZStack {
            Circle()
                .stroke(Color.secondary.opacity(0.15), lineWidth: 2)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(ringColor, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                .rotationEffect(.degrees(-90))
            Text("\(refreshCountdown)")
                .font(.system(size: 8, weight: .bold, design: .monospaced))
                .foregroundStyle(.secondary)
        }
        .frame(width: 22, height: 22)
    }

    // MARK: - Data Filtering

    /// When "Since Start" is selected, only show data from game start onward.
    /// Uses a "smart start" approach: if there's a gap >30 min between
    /// commence_time and the first data point, start from the first data point
    /// instead — prevents empty chart space from schedule delays.
    private var gameEndDate: Date? {
        guard status == "completed" || status == "closed" else { return nil }
        // Prefer actual game data endpoints (ESPN, stat_model) over completedAt
        // (completedAt is a backend processing timestamp, often 30-45 min after game end)
        var candidates: [Date] = []
        if let espn = vm.history?.espnHistory, let last = espn.last, let d = last.timestamp.asDate {
            candidates.append(d)
        }
        if let wp = vm.history?.winProbHistory {
            for (source, points) in wp where source == "espn" || source == "stat_model" || source == "mlb" || source == "fangraphs" {
                if let last = points.last, let d = last.timestamp.asDate {
                    candidates.append(d)
                }
            }
        }
        if let latest = candidates.max() {
            return latest.addingTimeInterval(120)
        }
        // Fallback to completedAt only if no game-end data
        if let ca = vm.history?.completedAt, let d = ca.asDate {
            return d
        }
        return nil
    }

    private func filterPoints(_ points: [ChartDataPoint]) -> [ChartDataPoint] {
        var filtered = points

        // Always clip post-game data for completed games (prevents Kalshi/Polymarket drift toward 50%)
        if (status == "completed" || status == "closed"), let endDate = gameEndDate {
            filtered = filtered.filter { $0.date <= endDate }
        }

        guard vm.selectedRange == .sinceStart,
              let startDate = gameStartDate,
              isGameStarted else {
            return filtered
        }
        filtered = filtered.filter { $0.date >= startDate }

        guard let firstPoint = filtered.first else {
            return filtered
        }
        let gap = firstPoint.date.timeIntervalSince(startDate)
        if gap > 1800 {
            let adjustedStart = firstPoint.date.addingTimeInterval(-60)
            return filtered.filter { $0.date >= adjustedStart }
        }
        return filtered
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

        // Supplement with win_prob_history game_state (stat_model, espn sources have period/inning)
        if let wpHistory = history.winProbHistory {
            for (_, points) in wpHistory {
                let sorted = points
                    .compactMap { point -> (period: String, date: Date)? in
                        guard let gs = point.gameState,
                              let date = point.timestamp.asDate else { return nil }
                        if let period = gs.period, !period.isEmpty {
                            return (period, date)
                        }
                        if let inning = gs.inning, inning > 0 {
                            return ("Top \(inning)", date)
                        }
                        return nil
                    }
                    .sorted { $0.date < $1.date }

                for point in sorted {
                    let label = normalizePeriodLabel(point.period)
                    guard !label.isEmpty, !seenLabels.contains(label) else { continue }
                    seenLabels.insert(label)
                    firstSeen.append((label, point.date))
                }
            }
        }

        // If data doesn't include the first period, add one at game commence time.
        // This ensures e.g. Q1 always appears even if ESPN sync started in Q2.
        if isGameStarted, let startDate = gameStartDate, !firstSeen.isEmpty {
            let firstPeriodLabel = inferFirstPeriodLabel(from: firstSeen.map(\.label))
            if let firstPeriodLabel, !seenLabels.contains(firstPeriodLabel) {
                firstSeen.insert((firstPeriodLabel, startDate), at: 0)
            }
        }

        // Soccer halftime detection: if we have NO period markers at all
        // but ESPN history shows a time gap >8 minutes (halftime break),
        // insert a "HT" marker at the gap.
        // NOTE: Only trigger when firstSeen is truly empty. The previous
        // condition also triggered when all labels were numeric (allSatisfy(\.isNumber)),
        // but baseball inning markers ARE numeric ("1","2"..."9") — that caused
        // soccer "2H" to overwrite correct inning markers on baseball win prob charts.
        if firstSeen.isEmpty,
           let espnHistory = history.espnHistory, espnHistory.count >= 5 {
            let espnDates = espnHistory.compactMap { $0.timestamp.asDate }.sorted()
            for i in 1..<espnDates.count {
                let gap = espnDates[i].timeIntervalSince(espnDates[i - 1])
                if gap > 480 { // >8 minute gap = likely halftime
                    let htDate = espnDates[i - 1].addingTimeInterval(gap / 2)
                    if !seenLabels.contains("HT") {
                        firstSeen.removeAll()
                        seenLabels.removeAll()
                        firstSeen.append(("1H", espnDates.first!))
                        firstSeen.append(("HT", htDate))
                        firstSeen.append(("2H", espnDates[i]))
                        seenLabels = ["1H", "HT", "2H"]
                    }
                    break
                }
            }
        }

        let sorted = firstSeen.sorted { $0.date < $1.date }

        // Dedup markers that are too close together, so the floating period chips
        // in `.chartOverlay` do not overlap each other.
        //
        // UX-P090 — THE OLD 3% WAS ARITHMETICALLY TOO SMALL TO DO ITS OWN JOB, and
        // that is measurable rather than aesthetic. The threshold is a fraction of
        // the chart's DURATION, and the x-axis is linear, so it is equally a
        // fraction of the chart's WIDTH. The plot area is about 345pt on an
        // iPhone 16 (393pt screen − 32pt card padding − 24pt rotated team gutter),
        // so 3% bought ~10pt of separation between two chips that are each ~28pt
        // wide (a 2-character label at size 10, plus 4pt horizontal padding each
        // side, centred by `.position`). Two chips 10pt apart on centre overlap by
        // roughly two thirds of their width. The comment claimed it "prevents
        // Q3/Q4 overlap"; it prevented the two markers from being drawn at
        // literally the same x, which is a different thing.
        //
        // The chip needs its own width in separation, so the floor is
        // chipWidth / plotWidth ≈ 28/337 ≈ 8.3%. Rounded UP to 9% to cover the
        // wider labels that actually exist — "OT2", and the two-digit innings that
        // #1831's 1…N ladder made reachable ("10", "11").
        //
        // WHAT THIS DOES NOT DROP, checked before changing it: real period
        // boundaries are far coarser than 9% of a game. Nine innings across a 3h
        // chart are ~20 min apart against a 16.2 min threshold; four NBA quarters
        // across 2.5h are ~35 min apart against 13.5 min. So every genuine period
        // still draws its chip — this removes collisions, not information. The
        // absolute floor stays at 3 minutes for very short domains, where the
        // percentage alone would go to zero.
        let chartDuration: TimeInterval
        if let first = filteredPoints.first?.date, let last = filteredPoints.last?.date {
            chartDuration = last.timeIntervalSince(first)
        } else {
            chartDuration = 3600
        }
        let minSpacing = max(chartDuration * Self.periodChipMinSpacingFraction, 180)

        var deduped: [(label: String, date: Date)] = []
        for item in sorted {
            if let last = deduped.last {
                if item.date.timeIntervalSince(last.date) < minSpacing {
                    // Replace previous with this one (keep later/more informative label)
                    deduped[deduped.count - 1] = item
                    continue
                }
            }
            deduped.append(item)
        }

        return deduped
            .enumerated()
            .map { PeriodMarker(date: $1.date, label: $1.label, isGameStart: false) }
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

    // MARK: - Chart Content Builder (extracted to reduce type-checker load)

    @ChartContentBuilder
    private func chartContent(
        dataPoints: [ChartDataPoint],
        sources: [String: WinProbSourceInfo],
        visibleMarkers: [PeriodMarker]
    ) -> some ChartContent {
        // 50% reference line (single 0–100 axis: even is 0.5)
        RuleMark(y: .value("Even", 0.5))
            .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [4, 4]))
            .foregroundStyle(.gray.opacity(0.4))

        // Selection indicator
        if let selectedDate {
            RuleMark(x: .value("Selected", selectedDate))
                .lineStyle(StrokeStyle(lineWidth: 1.0))
                .foregroundStyle(.primary.opacity(0.4))
        }

        // Data lines. When the backend blend exists it is the ONLY default line
        // ("the blend is the product" — one number per question); source detail
        // never competes with it here. Absent a blend we fail closed to the full
        // set with the sportsbook consensus as primary (L2-216).
        ForEach(Self.defaultVisibleSources(in: dataPoints), id: \.self) { source in
            let points = dataPoints.filter { $0.source == source }
            let color = colorForSource(source, sources: sources)
            let stroke = strokeStyleForSource(source, sources: sources)
            ForEach(points) { point in
                LineMark(
                    x: .value("Time", point.date),
                    y: .value("Win probability", point.probability),
                    series: .value("Source", source)
                )
                .foregroundStyle(color)
                .lineStyle(stroke)
                // Observed journey only — connect real snapshots with straight
                // segments. Monotone/curve interpolation invented probability
                // movement between sparse samples that was never captured, violating
                // the settled no-smoothing ruling (C43 P1).
                .interpolationMethod(.linear)
            }
        }

        // Period markers — light vertical gridlines at inning/quarter boundaries
        ForEach(visibleMarkers) { marker in
            RuleMark(x: .value("Period", marker.date))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
                .foregroundStyle(.secondary.opacity(0.25))
        }
    }

    private func chartView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo], periodMarkers: [PeriodMarker]) -> some View {
        // Filter period markers to visible data range
        let visibleMarkers: [PeriodMarker]
        if let minDate = dataPoints.map(\.date).min(),
           let maxDate = dataPoints.map(\.date).max() {
            visibleMarkers = periodMarkers.filter { $0.date >= minDate && $0.date <= maxDate }
        } else {
            visibleMarkers = periodMarkers
        }

        // Single 0–100 win-probability Y-axis (L2-216): the line is the HOME team's
        // win probability read straight up the scale. Replaces the old mirrored ±50
        // dual-axis where the same "80%" appeared both above and below center. Matches
        // the web chart (L2-131).
        let yMin = 0.0
        let yMax = 1.0

        return Chart {
            chartContent(dataPoints: dataPoints, sources: sources, visibleMarkers: visibleMarkers)
        }
        .chartYScale(domain: yMin...yMax)
        .accessibilityLabel(Text("Win probability over time"))
        .accessibilityValue(Text(Self.accessibilityValue(
            dataPoints: dataPoints, selectedDate: selectedDate,
            homeShort: homeShort, awayShort: awayShort)))
        .chartXScale(domain: xAxisDomain(for: dataPoints))
        // Period marker labels positioned inside chart via overlay
        .chartOverlay { proxy in
            GeometryReader { geo in
                // Small floating period chips near the top of the chart
                ForEach(Array(visibleMarkers.enumerated()), id: \.element.id) { index, marker in
                    if let xPos = proxy.position(forX: marker.date) {
                        Text(marker.label)
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(.ultraThinMaterial)
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                            .position(x: xPos, y: 10)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: Self.yAxisTicks) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.3))
                AxisValueLabel {
                    if let v = value.as(Double.self) {
                        Text(Self.axisLabel(for: v))
                            .font(.system(size: 9))
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .chartXAxis {
            let plan = Self.xAxisPlan(for: xAxisDomain(for: dataPoints))
            AxisMarks(values: .stride(by: plan.component, count: plan.count)) { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(format: plan.format, anchor: .top)
                    .font(.system(size: 9))
            }
        }
        .chartXSelection(value: $selectedDate)
    }

    // MARK: - Legend

    private func legendView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo]) -> some View {
        // Legend mirrors what is actually drawn: blend-only when a backend blend
        // exists, else the fail-closed full set (L2-216).
        let uniqueSources = Self.defaultVisibleSources(in: dataPoints)
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
        Self.chartPoints(from: history)
    }

    /// Pure transform: decoded event history → observed chart points.
    ///
    /// Three C43 truth guarantees live here (unit-tested in `OddsChartPointsTests`):
    /// 1. **No client aggregation.** The only "aggregate" (Bain Luck blend) source
    ///    is the backend's canonical weighted, staleness-aware `aggregateLine`. When
    ///    it is absent we fail closed — the chart falls back to the sportsbook
    ///    "consensus" as primary rather than relabelling a locally reconstructed
    ///    arithmetic mean as the blend ("the blend is the product").
    /// 2. **No shape guessing.** Every backend-valid probability is retained; we do
    ///    not delete near-50% observations, which erased legitimate 50/50 crossings.
    /// 3. Rendering connects these observed points with straight segments (see the
    ///    `.linear` interpolation in `chartContent`) — no invented curve.
    static func chartPoints(from history: EventHistoryResponse) -> [ChartDataPoint] {
        var points: [ChartDataPoint] = []
        let multiSource = !(history.winProbHistory?.isEmpty ?? true)

        // Sportsbook consensus (backend-computed) — always present as a real line.
        for h in history.history {
            guard let date = h.timestamp.asDate,
                  let prob = h.homeProbability else { continue }
            points.append(ChartDataPoint(date: date, probability: prob, source: "consensus"))
        }

        guard multiSource else {
            // Sportsbooks-only mode: "consensus" is the sole aggregation.
            return points
        }

        // Other win-probability sources (ESPN, Kalshi, Polymarket, model, …).
        // Retain every backend-valid observation: the consumer cannot tell an
        // upstream placeholder from a real swing using two probabilities alone, and
        // the old near-50% deletion dropped genuine even-game crossings (C43 P1).
        for (sourceKey, sourcePoints) in history.winProbHistory ?? [:] {
            for wp in sourcePoints {
                guard let date = wp.timestamp.asDate,
                      let prob = wp.homeProbability else { continue }
                points.append(ChartDataPoint(date: date, probability: prob, source: sourceKey))
            }
        }

        // The ONLY Bain Luck aggregate is the backend canonical line. If it is
        // missing we do NOT synthesize a client arithmetic mean labelled
        // "aggregate": that would show a *different* Bain Luck number precisely when
        // backend aggregation failed. Fail closed — consensus stays primary (C43 P1).
        if let aggregateLine = history.aggregateLine, !aggregateLine.isEmpty {
            for p in aggregateLine {
                guard let date = p.timestamp.asDate else { continue }
                points.append(ChartDataPoint(date: date, probability: p.homeProbability, source: "aggregate"))
            }
        }

        return points
    }

    // MARK: - Primary line & 0–100 axis (pure, unit-tested in OddsChartAxisTests)

    /// The source key whose line is the primary read: the backend blend when
    /// present, otherwise the sportsbook consensus (fail closed — never a client
    /// mean; see `chartPoints`).
    static func primarySource(in points: [ChartDataPoint]) -> String {
        points.contains { $0.source == "aggregate" } ? "aggregate" : "consensus"
    }

    /// Sources drawn on the chart by default. When the backend blend exists it is
    /// the ONLY default line ("the blend is the product" — one number per
    /// question); source divergence is not a comparison surface here. Absent a
    /// blend we fail closed to the full set, with consensus first (L2-216).
    static func defaultVisibleSources(in points: [ChartDataPoint]) -> [String] {
        if points.contains(where: { $0.source == "aggregate" }) { return ["aggregate"] }
        return Array(Set(points.map(\.source))).sorted()
    }

    /// Fixed 0–100 axis tick positions (probability basis, 0.0–1.0).
    static let yAxisTicks: [Double] = [0, 0.25, 0.5, 0.75, 1.0]

    /// UX-P090 — see `PeriodChipGeometry`. Held here so the dedup call site reads
    /// as one named thing rather than a bare literal.
    static let periodChipMinSpacingFraction: Double = PeriodChipGeometry.minSpacingFraction

    /// Axis / read-out label for a probability value on the single 0–100 axis.
    /// No mirroring: 0.8 → "80%" everywhere (unlike the old ±50 delta axis).
    static func axisLabel(for value: Double) -> String {
        "\(Int((value * 100).rounded()))%"
    }

    /// Nearest REAL observed snapshot on the primary line to a scrub date. Never
    /// interpolates — returns an actual captured point (or nil for an empty line).
    static func nearestSnapshot(to date: Date, in points: [ChartDataPoint]) -> ChartDataPoint? {
        let primary = primarySource(in: points)
        return points
            .filter { $0.source == primary }
            .min { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) }
    }

    /// Latest real snapshot on the primary line (used for the resting accessibility
    /// read-out when nothing is scrubbed).
    static func latestPrimaryPoint(in points: [ChartDataPoint]) -> ChartDataPoint? {
        let primary = primarySource(in: points)
        return points.filter { $0.source == primary }.max { $0.date < $1.date }
    }

    /// Human/VoiceOver read-out for a snapshot, in the SAME probability basis as
    /// the plotted line and axis labels (home %, away %, plus real game state).
    static func selectionReadout(for point: ChartDataPoint, homeShort: String, awayShort: String) -> String {
        let homePct = Int((point.probability * 100).rounded())
        let awayPct = 100 - homePct
        var parts = ["\(homeShort) \(homePct)%", "\(awayShort) \(awayPct)%"]
        if let hs = point.homeScore, let a = point.awayScore { parts.append("score \(hs)–\(a)") }
        if let period = point.period, !period.isEmpty { parts.append(period) }
        if let clock = point.clock, !clock.isEmpty { parts.append(clock) }
        return parts.joined(separator: ", ")
    }

    /// Accessibility value for the chart: the scrubbed snapshot when one is
    /// selected, else the latest primary snapshot. Always the 0–100 basis.
    static func accessibilityValue(dataPoints: [ChartDataPoint], selectedDate: Date?,
                                   homeShort: String, awayShort: String) -> String {
        let point: ChartDataPoint?
        if let selectedDate {
            point = nearestSnapshot(to: selectedDate, in: dataPoints)
        } else {
            point = latestPrimaryPoint(in: dataPoints)
        }
        guard let point else { return "No probability data" }
        return selectionReadout(for: point, homeShort: homeShort, awayShort: awayShort)
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
        guard let date, let nearest = Self.nearestSnapshot(to: date, in: dataPoints) else {
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
            name = "Sportsbook Consensus"
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
        case "stat_model", "bainluck_model": return "Statistical Model"
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

    /// Compute x-axis domain. Uses forcedDomain when available for chart alignment.
    private func xAxisDomain(for dataPoints: [ChartDataPoint]) -> ClosedRange<Date> {
        if let forced = forcedDomain { return forced }
        let dates = dataPoints.map(\.date)
        guard let minDate = dates.min(), let maxDate = dates.max() else {
            let now = Date()
            return now...now
        }
        let range = maxDate.timeIntervalSince(minDate)
        let padding = max(range * 0.02, 60)
        return minDate.addingTimeInterval(-padding)...maxDate.addingTimeInterval(padding)
    }

    // MARK: - X-Axis Ticks

    /// How to tick and label the time axis for one chart domain.
    ///
    /// The axis used to hard-code a 15/30/**60**-minute stride and an
    /// `hour().minute()` label, whatever the span. That is fine for the case it
    /// was written against — a three-hour game — and unreadable for anything
    /// else: an UPCOMING match carries hours of pre-match history, so Alex's
    /// Shelton–Shapovalov page (24 + 47 points over a **17-hour** span, measured
    /// 2026-09-03) drew ~18 hourly labels of the form "11:18 PM" into ~350 points
    /// of width, which overprint into a smear. It also never named a day, so a
    /// domain crossing midnight labelled two different days identically.
    ///
    /// So the stride is chosen from the domain: the smallest natural interval
    /// whose tick count fits the label's own budget (short labels tolerate more
    /// ticks than "Wed 6 AM" does), and the label carries a weekday exactly when
    /// the domain spans more than one calendar day. No smoothing, no invented
    /// points — this is labelling only.
    struct XAxisPlan: Equatable {
        enum LabelStyle: Equatable {
            /// "6:45 PM" — within one day, ticks finer than an hour.
            case timeOfDay
            /// "6 PM" — within one day, hourly or coarser ticks.
            case hourOfDay
            /// "Wed 6 PM" — the domain spans more than one calendar day.
            case dayAndHour
            /// "Sep 3" — the domain spans days, ticks a day or coarser.
            case calendarDay
        }

        let component: Calendar.Component
        let count: Int
        let labelStyle: LabelStyle

        var format: Date.FormatStyle {
            switch labelStyle {
            case .timeOfDay: return .dateTime.hour().minute()
            case .hourOfDay: return .dateTime.hour()
            case .dayAndHour: return .dateTime.weekday(.abbreviated).hour()
            case .calendarDay: return .dateTime.month(.abbreviated).day()
            }
        }
    }

    /// Candidate strides, coarsening. `seconds` is nominal (used only to estimate
    /// a tick count); the axis itself strides by the calendar component, so DST
    /// and month length stay the calendar's problem, not ours.
    private static let xAxisStrides: [(component: Calendar.Component, count: Int, seconds: TimeInterval)] = [
        (.minute, 5, 300), (.minute, 10, 600), (.minute, 15, 900), (.minute, 30, 1800),
        (.hour, 1, 3600), (.hour, 2, 7200), (.hour, 3, 10800), (.hour, 4, 14400),
        (.hour, 6, 21600), (.hour, 8, 28800), (.hour, 12, 43200),
        (.day, 1, 86400), (.day, 2, 172800), (.day, 7, 604800),
        (.day, 14, 1209600), (.day, 30, 2592000), (.day, 60, 5184000),
        (.day, 90, 7776000), (.day, 180, 15552000), (.day, 365, 31536000),
    ]

    /// How many labels of each style fit legibly at 9pt across a phone-width
    /// chart. Longer labels get a smaller budget — that is the whole mechanism
    /// that stops the smear.
    private static func maxTicks(for style: XAxisPlan.LabelStyle) -> Int {
        switch style {
        case .timeOfDay: return 6
        case .hourOfDay: return 6
        case .dayAndHour: return 5
        case .calendarDay: return 6
        }
    }

    private static func labelStyle(
        strideSeconds: TimeInterval, spansMultipleDays: Bool
    ) -> XAxisPlan.LabelStyle {
        if strideSeconds >= 86400 { return .calendarDay }
        if spansMultipleDays { return .dayAndHour }
        return strideSeconds < 3600 ? .timeOfDay : .hourOfDay
    }

    /// Pick the finest stride whose labels still fit. Falls through to the
    /// coarsest candidate for a domain wider than a month, so a chart always has
    /// an axis — an unlabelled axis is not an improvement on a crowded one.
    static func xAxisPlan(
        for domain: ClosedRange<Date>, calendar: Calendar = .current
    ) -> XAxisPlan {
        let duration = max(domain.upperBound.timeIntervalSince(domain.lowerBound), 0)
        let spansMultipleDays = !calendar.isDate(
            domain.lowerBound, inSameDayAs: domain.upperBound)

        for candidate in xAxisStrides {
            let style = labelStyle(
                strideSeconds: candidate.seconds, spansMultipleDays: spansMultipleDays)
            let ticks = duration / candidate.seconds
            if ticks <= Double(maxTicks(for: style)) {
                return XAxisPlan(
                    component: candidate.component, count: candidate.count, labelStyle: style)
            }
        }
        let last = xAxisStrides[xAxisStrides.count - 1]
        return XAxisPlan(component: last.component, count: last.count, labelStyle: .calendarDay)
    }

    // MARK: - Period Label Normalization

    /// Normalize ESPN period strings to user-friendly labels.
    /// Matches web's normalizePeriodLabel() in periodMarkers.ts
    /// Delegates to `PeriodLabel.normalize` — the single implementation (#1831).
    /// This file used to carry its own copy; the two had drifted.
    private func normalizePeriodLabel(_ raw: String) -> String {
        PeriodLabel.normalize(raw)
    }
}
