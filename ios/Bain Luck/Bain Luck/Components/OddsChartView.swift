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

    /// Per-label chip width, for the questions `chipWidthPoints` cannot answer:
    /// does THIS chip fit inside the plot, and does it hit its neighbour.
    ///
    /// `chipWidthPoints` is deliberately a conservative bound on the widest
    /// TWO-character chip and is the right basis for the spacing rule. It is the
    /// wrong basis for a five-character "Final", which is genuinely wider than
    /// any inning number and was the chip that overhung the plot.
    ///
    /// The character figure is MEASURED off the rendered chips rather than
    /// guessed: on the 2026-09-05 iPhone 17 shots (`n024-after-walkoff.png`,
    /// 3.07px/pt) "8th" renders ~22pt and "Final" ~30pt, i.e. ~4.7–5.3pt per
    /// glyph at size-10 bold plus the 4pt padding each side. 6pt per character is
    /// the round number above that, so every chip's computed width is an upper
    /// bound on its drawn width — which is the safe direction for a rule that
    /// decides whether two chips collide. `chipWidth(for: "10")` must stay at or
    /// under `chipWidthPoints`, asserted in `OddsChartEdgeLabelTests`, so the
    /// spacing constant keeps being the conservative bound it claims to be.
    static let horizontalPaddingPoints: Double = 4
    static let characterWidthPoints: Double = 6

    /// One chip strip's own type size, because the event page draws two.
    ///
    /// The MATCH chart's chips are 10pt bold with 4pt padding; the score chart
    /// below it draws the same periods at 8pt semibold with 3pt padding, under a
    /// 160pt-tall plot where a full-size chip would shout. Placing the smaller
    /// chips with the larger chip's width would drop chips that had room — the
    /// opposite defect from the one this file exists to prevent — so the width
    /// model takes the strip's metrics instead of assuming one of them.
    struct ChipMetrics: Equatable {
        let horizontalPadding: Double
        let characterWidth: Double

        /// 10pt bold, 4pt padding — the MATCH chart's strip, measured in the
        /// note above.
        static let match = ChipMetrics(
            horizontalPadding: horizontalPaddingPoints, characterWidth: characterWidthPoints)
        /// 8pt semibold, 3pt padding — the score chart's strip. 8/10 of the
        /// MATCH chart's measured 4.7–5.3pt per glyph is 3.8–4.2pt; 5pt is the
        /// round number above that, so this stays an upper bound too.
        static let score = ChipMetrics(horizontalPadding: 3, characterWidth: 5)
    }

    static func chipWidth(for label: String, metrics: ChipMetrics = .match) -> Double {
        metrics.horizontalPadding * 2 + Double(label.count) * metrics.characterWidth
    }

    /// Keep a chip's full width inside the plot (#3237).
    ///
    /// `rawX` is the chip's ideal centre — the x of the period boundary it marks,
    /// measured from the plot's leading edge. A marker at or near `x = 0` centres
    /// a chip whose left half hangs over the y-axis gutter, on top of the "100%"
    /// label; the same happens at the trailing edge against the plot's right
    /// border. Clamping the CENTRE by half the chip's width is the whole fix: the
    /// chip still names its period, it just stops overhanging the frame.
    ///
    /// A plot too narrow to hold the chip at all has no non-overlapping answer,
    /// so it centres — visibly wrong beats arbitrarily wrong.
    static func clampedCenterX(
        rawX: Double, label: String, plotWidth: Double, metrics: ChipMetrics = .match
    ) -> Double {
        let width = chipWidth(for: label, metrics: metrics)
        guard plotWidth > width else { return plotWidth / 2 }
        let half = width / 2
        return min(max(rawX, half), plotWidth - half)
    }

    /// One chip asking to be drawn: `key` is the caller's identity for it, so the
    /// placement can be matched back to a marker without this type knowing what a
    /// marker is.
    struct ChipRequest: Equatable {
        let key: Int
        let label: String
        let rawX: Double
    }

    struct ChipPlacement: Equatable {
        let key: Int
        let centerX: Double
    }

    /// Place the chips that will actually be drawn (#3237).
    ///
    /// The clamp above cannot be applied on its own: pulling a wide trailing chip
    /// inside the plot moves it INTO its neighbour. Measured on 15302915, the
    /// 10-inning walk-off — clamping alone drew "Final" over "9th" so the strip
    /// read "9Final". The spacing rule in `extractPeriodMarkers` had already
    /// passed that pair, correctly, because it measures separation against a
    /// two-character chip and neither chip had moved yet.
    ///
    /// So the last word on overlap belongs here, where the final positions are
    /// known. When two chips would touch, the EARLIER one is dropped — the same
    /// preference the spacing rule states ("keep later/more informative label"),
    /// and the right one for this case: the collision is created by the terminal
    /// chip, and "Final" is the more informative of the two. The drop cascades,
    /// because removing one chip can expose an overlap with the one before it.
    ///
    /// Requests are placed in the order given; the caller passes them in time
    /// order, which is x order on a linear axis.
    static func place(
        _ requests: [ChipRequest], plotWidth: Double, metrics: ChipMetrics = .match
    ) -> [ChipPlacement] {
        var kept: [(placement: ChipPlacement, halfWidth: Double)] = []
        for request in requests {
            let half = chipWidth(for: request.label, metrics: metrics) / 2
            let centerX = clampedCenterX(
                rawX: request.rawX, label: request.label,
                plotWidth: plotWidth, metrics: metrics)
            while let last = kept.last, centerX - half < last.placement.centerX + last.halfWidth {
                kept.removeLast()
            }
            kept.append((ChipPlacement(key: request.key, centerX: centerX), half))
        }
        return kept.map(\.placement)
    }
}

// MARK: - Plot Width

/// The drawn plot area's width, carried from a chart's overlay (which is the
/// only place the plot frame is knowable) up to the chart itself.
///
/// Both charts on the event page need it: the MATCH chart to size its time axis
/// (#3269) and the score chart to place its period chips. The default of 0 means
/// "not measured yet" and every reader falls back rather than dividing by it.
struct PlotWidthPreferenceKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

// MARK: - Chart Moment

/// One Moments-Engine annotation placed on the drawn line (#1168 consumer 3, #3196).
///
/// `probability` is NOT the moment's own number — the payload doesn't carry one. It
/// is the y of the nearest REAL primary-line snapshot, so the marker sits on the
/// curve the reader can see. Interpolating a y between two snapshots would invent a
/// probability that was never captured, which is the same no-smoothing rule the line
/// itself obeys (C43 P1, `interpolationMethod(.linear)` below).
struct ChartMoment: Identifiable, Equatable {
    let id = UUID()
    let date: Date
    let label: String
    let probability: Double
    /// Signed swing, 0.0–1.0. `nil` when the server didn't send one — such a moment
    /// is still drawable, it just can never be the biggest.
    let probDelta: Double?
    let period: String?

    static func == (a: ChartMoment, b: ChartMoment) -> Bool {
        a.date == b.date && a.label == b.label && a.probability == b.probability
            && a.probDelta == b.probDelta && a.period == b.period
    }
}

/// The clutter bound on moment markers, derived the same way `PeriodChipGeometry` is
/// rather than picked.
///
/// A blowout can in principle produce a moment per scoring play; nine is the most
/// measured on an MLB game (2026-09-05 sample: 2, 9, 4). This is a ceiling on
/// legibility, not a guard against a known defect — past it the markers touch and the
/// strip stops being readable, so the SMALLEST swings are dropped and the survivors
/// keep their chronological order. Dropping small swings is the right direction: the
/// annotation exists to explain the line's big movements.
enum MomentMarkerGeometry {
    /// Outer diameter of the ringed dot, in points.
    static let markerDiameterPoints: Double = 9
    /// The most markers that fit without two of them touching: each needs its own
    /// diameter plus one diameter of clear space. Derived from the SAME measured plot
    /// width the period chips use, so the two strips cannot drift apart.
    static var maxMarkers: Int {
        Int(PeriodChipGeometry.plotWidthPoints / (markerDiameterPoints * 2))
    }
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
    /// The drawn plot area's width, reported by the chart's own overlay. The
    /// x-axis needs it to know whether its labels clear each other (#3269); 0
    /// until the first layout pass, which is the documented fallback in
    /// `xAxisPlan`.
    @State private var plotWidth: CGFloat = 0
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
                let moments = Self.chartMoments(from: history.moments, points: dataPoints)
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

                        chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:],
                                  periodMarkers: periodMarkers, moments: moments)
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

                    // Indented onto the SAME left margin as the plot area and the
                    // legend, for the reason UX-P090 gives above: three rows that
                    // belong to one chart do not get three different margins.
                    momentCaption(moments)
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
                    let moments = Self.chartMoments(from: history.moments, points: dataPoints)
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

                                chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:],
                                          periodMarkers: periodMarkers, moments: moments)
                            }
                            legendView(dataPoints: dataPoints, sources: history.winProbSources ?? [:])
                            momentCaption(moments)
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
        visibleMarkers: [PeriodMarker],
        moments: [ChartMoment]
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

        // Moments (#3196) — drawn LAST so they sit on top of the line they annotate.
        //
        // In the PRIMARY LINE'S OWN COLOUR, ringed. A marker is a point on this curve
        // that matters, not a second data series, and colouring it by actor team
        // would put a third and fourth colour on a chart whose whole rule is that
        // the blend is one number ("the blend is the product"). The ring is what
        // separates it from the line without a new hue.
        ForEach(moments) { moment in
            PointMark(
                x: .value("Moment", moment.date),
                y: .value("Win probability", moment.probability)
            )
            .symbolSize(momentSymbolArea)
            .foregroundStyle(colorForSource(Self.primarySource(in: dataPoints), sources: sources))
            .annotation(position: .overlay, spacing: 0) {
                Circle()
                    .stroke(Color(.systemBackground), lineWidth: 1.5)
                    .frame(width: MomentMarkerGeometry.markerDiameterPoints,
                           height: MomentMarkerGeometry.markerDiameterPoints)
            }
            .accessibilityLabel(Text(moment.label))
        }
    }

    /// `symbolSize` is an AREA in square points, so the diameter has to be squared —
    /// passing the diameter draws a dot roughly a third of the intended width.
    private var momentSymbolArea: CGFloat {
        let d = CGFloat(MomentMarkerGeometry.markerDiameterPoints)
        return d * d
    }

    private func chartView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo],
                           periodMarkers: [PeriodMarker], moments: [ChartMoment]) -> some View {
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
            chartContent(dataPoints: dataPoints, sources: sources,
                         visibleMarkers: visibleMarkers, moments: moments)
        }
        .chartYScale(domain: yMin...yMax)
        .accessibilityLabel(Text("Win probability over time"))
        .accessibilityValue(Text(Self.accessibilityValue(
            dataPoints: dataPoints, selectedDate: selectedDate,
            homeShort: homeShort, awayShort: awayShort, moments: moments)))
        .chartXScale(domain: xAxisDomain(for: dataPoints))
        // Period marker labels positioned inside chart via overlay.
        //
        // #3237, two corrections in one place, because they are the same mistake:
        // `proxy.position(forX:)` is measured from the PLOT AREA's origin, while
        // this GeometryReader spans the WHOLE chart — the y-axis gutter included.
        // Positioning a plot-relative x in chart space drew every chip a gutter's
        // width to the LEFT of the inning it marks, and put the first chip on top
        // of the "100%" axis label. So: convert into chart space with
        // `plotFrame.minX`, and clamp the centre so the chip's own width stays
        // inside the plot at both ends.
        .chartOverlay { proxy in
            GeometryReader { geo in
                let plotFrame = geo[proxy.plotAreaFrame]
                let placements = PeriodChipGeometry.place(
                    visibleMarkers.enumerated().compactMap { index, marker in
                        proxy.position(forX: marker.date).map {
                            PeriodChipGeometry.ChipRequest(
                                key: index, label: marker.label, rawX: Double($0))
                        }
                    },
                    plotWidth: plotFrame.width
                )
                // The x-axis needs the same width the chips do (#3269).
                Color.clear.preference(
                    key: PlotWidthPreferenceKey.self, value: plotFrame.width)
                // Small floating period chips near the top of the chart
                ForEach(placements, id: \.key) { placement in
                    let marker = visibleMarkers[placement.key]
                    Text(marker.label)
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(.ultraThinMaterial)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                        .position(x: plotFrame.minX + placement.centerX, y: 10)
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
            let plan = Self.xAxisPlan(for: xAxisDomain(for: dataPoints), plotWidth: plotWidth)
            AxisMarks(values: .stride(by: plan.component, count: plan.count)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(
                    format: plan.format,
                    anchor: Self.xAxisLabelAnchor(index: value.index, count: value.count)
                )
                .font(.system(size: 9))
            }
        }
        .onPreferenceChange(PlotWidthPreferenceKey.self) { width in
            plotWidth = width
        }
        .chartXSelection(value: $selectedDate)
    }

    // MARK: - Moment Caption

    /// The story of the chart in one line, with nothing tapped (#3196).
    ///
    /// Renders NOTHING when there are no drawable moments — no empty state, no "no
    /// key moments yet". Alex's ruling on #871 is that an absent explanation beats an
    /// unhelpful one, and the chart is already complete without this row.
    @ViewBuilder
    private func momentCaption(_ moments: [ChartMoment]) -> some View {
        if let headline = Self.headlineMoment(in: moments),
           let kicker = Self.momentCaptionKicker(count: moments.count) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Circle()
                    .fill(.secondary)
                    .frame(width: 5, height: 5)
                    .alignmentGuide(.firstTextBaseline) { $0[.bottom] - 1 }
                Text(kicker)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(Self.momentCaptionText(for: headline))
                    .font(.caption2)
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
        }
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

    // MARK: - Moments (pure, unit-tested in OddsChartMomentsTests)

    /// How close a scrub has to land to a moment before the read-out names it. The
    /// same window `enrichWithGameState` already uses to attach a scoring play to a
    /// snapshot — named here so the two cannot drift into disagreeing about what
    /// "at this point in the game" means.
    static let momentMatchWindowSeconds: TimeInterval = 60

    /// Pure transform: decoded payload moments → drawable markers on the primary line.
    ///
    /// Four rules, each of which is a test in `OddsChartMomentsTests`:
    ///
    /// 1. **Unusable rows are dropped here and only here.** No timestamp we can parse,
    ///    or no label to say, and the row cannot be drawn or read aloud. This is the
    ///    single place that judgement is made; `GameMomentPoint` is all-optional
    ///    precisely so a bad row lands here instead of failing the whole decode.
    /// 2. **A moment outside the drawn range is dropped.** `filterPoints` narrows the
    ///    line under "Since Start"; without this rule a pregame moment would be
    ///    clamped onto the left edge and read as something that happened at first
    ///    pitch. Same test `visibleMarkers` applies to period gridlines.
    /// 3. **The y is a real snapshot, never an interpolation** (see `ChartMoment`).
    /// 4. **There is no confidence gate here.** `routes/events.py` already selects
    ///    `confidence >= 0.5` and honours the `moments:surface_enabled` kill switch.
    ///    A second threshold on the client would silently narrow a decision the
    ///    server owns and would need an App Store release to change; a 0.51 moment
    ///    draws, and a test pins that so nobody adds one.
    static func chartMoments(from moments: [GameMomentPoint]?,
                             points: [ChartDataPoint]) -> [ChartMoment] {
        guard let moments, !moments.isEmpty, !points.isEmpty else { return [] }
        // THE RANGE IS THE PRIMARY LINE'S, not every source's. A marker anchors to a
        // primary snapshot (`nearestSnapshot`), so bounding it by the union of all
        // sources would admit a moment that ESPN saw after our blend stopped and then
        // anchor it to the blend's last point — a clamp wearing an in-range check,
        // which is exactly what rule 2 exists to prevent. (The period gridlines below
        // legitimately use the full range: a RuleMark has no y to clamp.)
        let primary = primarySource(in: points)
        let primaryDates = points.filter { $0.source == primary }.map(\.date)
        guard let minDate = primaryDates.min(), let maxDate = primaryDates.max() else { return [] }

        let drawable: [ChartMoment] = moments.compactMap { raw in
            guard let ts = raw.ts, let date = ts.asDate else { return nil }
            guard let label = raw.label?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !label.isEmpty else { return nil }
            guard date >= minDate, date <= maxDate else { return nil }
            guard let anchor = nearestSnapshot(to: date, in: points) else { return nil }
            return ChartMoment(
                date: date,
                label: label,
                probability: anchor.probability,
                probDelta: raw.probDelta,
                period: raw.period?.trimmingCharacters(in: .whitespacesAndNewlines)
            )
        }

        let sorted = drawable.sorted { $0.date < $1.date }
        guard sorted.count > MomentMarkerGeometry.maxMarkers else { return sorted }
        // Over the legibility ceiling: keep the biggest swings, then restore
        // chronological order so the strip still reads left-to-right as the game.
        let kept = sorted
            .sorted { abs($0.probDelta ?? 0) > abs($1.probDelta ?? 0) }
            .prefix(MomentMarkerGeometry.maxMarkers)
        return kept.sorted { $0.date < $1.date }
    }

    /// The one moment worth printing under the chart: the largest absolute swing.
    /// `nil` when nothing is drawable, which is the caption's cue to render no row at
    /// all — on #871 Alex ruled that nothing beats unhelpful, and a caption that says
    /// "no key moments" is the unhelpful thing.
    static func headlineMoment(in moments: [ChartMoment]) -> ChartMoment? {
        moments.max { abs($0.probDelta ?? 0) < abs($1.probDelta ?? 0) }
    }

    /// Kicker for the caption. One moment is not a comparison, so calling it the
    /// "biggest" would be a small lie about how much the chart knows.
    static func momentCaptionKicker(count: Int) -> String? {
        switch count {
        case 0: return nil
        case 1: return "Key moment"
        default: return "Biggest swing"
        }
    }

    /// Caption body: the period, when the server sent one, then the label it wrote.
    /// The label already carries the swing ("… — win prob +93.5 pts"), so nothing is
    /// recomputed or reworded on the client.
    static func momentCaptionText(for moment: ChartMoment) -> String {
        guard let period = moment.period, !period.isEmpty else { return moment.label }
        return "\(period) · \(moment.label)"
    }

    /// The moment a scrub is pointing at, or nil. Nearest wins, but only inside
    /// `momentMatchWindowSeconds` — beyond that the reader is looking at ordinary
    /// line, and naming a moment half a game away would be worse than silence.
    static func nearestMoment(to date: Date, in moments: [ChartMoment]) -> ChartMoment? {
        moments
            .min { abs($0.date.timeIntervalSince(date)) < abs($1.date.timeIntervalSince(date)) }
            .flatMap { abs($0.date.timeIntervalSince(date)) <= momentMatchWindowSeconds ? $0 : nil }
    }

    /// Latest real snapshot on the primary line (used for the resting accessibility
    /// read-out when nothing is scrubbed).
    static func latestPrimaryPoint(in points: [ChartDataPoint]) -> ChartDataPoint? {
        let primary = primarySource(in: points)
        return points.filter { $0.source == primary }.max { $0.date < $1.date }
    }

    /// Human/VoiceOver read-out for a snapshot, in the SAME probability basis as
    /// the plotted line and axis labels (home %, away %, plus real game state).
    static func selectionReadout(for point: ChartDataPoint, homeShort: String, awayShort: String,
                                 moment: ChartMoment? = nil) -> String {
        let homePct = Int((point.probability * 100).rounded())
        let awayPct = 100 - homePct
        var parts = ["\(homeShort) \(homePct)%", "\(awayShort) \(awayPct)%"]
        if let hs = point.homeScore, let a = point.awayScore { parts.append("score \(hs)–\(a)") }
        if let period = point.period, !period.isEmpty { parts.append(period) }
        if let clock = point.clock, !clock.isEmpty { parts.append(clock) }
        // The cause goes LAST: a VoiceOver reader wants the number first and the
        // story after it, the same order the sighted reader gets from the line and
        // then the caption.
        if let moment { parts.append(moment.label) }
        return parts.joined(separator: ", ")
    }

    /// Accessibility value for the chart: the scrubbed snapshot when one is
    /// selected, else the latest primary snapshot. Always the 0–100 basis.
    static func accessibilityValue(dataPoints: [ChartDataPoint], selectedDate: Date?,
                                   homeShort: String, awayShort: String,
                                   moments: [ChartMoment] = []) -> String {
        let point: ChartDataPoint?
        var moment: ChartMoment?
        if let selectedDate {
            point = nearestSnapshot(to: selectedDate, in: dataPoints)
            moment = nearestMoment(to: selectedDate, in: moments)
        } else {
            point = latestPrimaryPoint(in: dataPoints)
        }
        guard let point else { return "No probability data" }
        return selectionReadout(for: point, homeShort: homeShort, awayShort: awayShort,
                                moment: moment)
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
    ///
    /// The 20- and 45-minute rungs are there because the geometric fit needs
    /// somewhere to land. Without them the ladder jumps 30 → 60 minutes, and a
    /// 2½-hour game — the most common chart in the app — falls off the 30-minute
    /// rung and lands on hours: MEASURED on 15302914 (Arizona @ Houston, 155
    /// minutes), the axis went from six colliding labels to `9 PM · 10 PM`, two
    /// labels for a whole game. 45-minute ticks put four back, with the minutes
    /// they are actually read for.
    private static let xAxisStrides: [(component: Calendar.Component, count: Int, seconds: TimeInterval)] = [
        (.minute, 5, 300), (.minute, 10, 600), (.minute, 15, 900), (.minute, 20, 1200),
        (.minute, 30, 1800), (.minute, 45, 2700),
        (.hour, 1, 3600), (.hour, 2, 7200), (.hour, 3, 10800), (.hour, 4, 14400),
        (.hour, 6, 21600), (.hour, 8, 28800), (.hour, 12, 43200),
        (.day, 1, 86400), (.day, 2, 172800), (.day, 7, 604800),
        (.day, 14, 1209600), (.day, 30, 2592000), (.day, 60, 5184000),
        (.day, 90, 7776000), (.day, 180, 15552000), (.day, 365, 31536000),
    ]

    /// How many labels of each style fit legibly at 9pt across a phone-width
    /// chart. Longer labels get a smaller budget — that is the whole mechanism
    /// that stops the smear.
    ///
    /// This is the FALLBACK budget, used only when the plot's width has not been
    /// measured yet (the first frame, and any caller that has no geometry). Once
    /// a width is known the fit is geometric — see `xAxisFits` — because a count
    /// budget cannot know that #3237 moved the end labels.
    private static func maxTicks(for style: XAxisPlan.LabelStyle) -> Int {
        switch style {
        case .timeOfDay: return 6
        case .hourOfDay: return 6
        case .dayAndHour: return 5
        case .calendarDay: return 6
        }
    }

    /// The widest label a style can print, in points, at the axis's own 9pt font.
    ///
    /// MEASURED, not estimated. `OddsChartAxisFitTests` re-renders every label
    /// each style can produce — every hour × minute, every weekday, every month —
    /// with the real font and fails if any is wider than the number here. A
    /// guessed budget is what put a wrong time on the axis (see `xAxisFits`), so
    /// this one is re-measured by the suite on every run.
    ///
    /// The date formats follow the DEVICE's locale, not the app's copy, so the
    /// measurement covers a locale set rather than `en_US` alone: German is the
    /// widest of them at both coarse styles ("04 Uhr", "28. Sept." against "4 AM"
    /// and "Sep 28"). Pinning the widest costs an English reader about one label
    /// on a multi-week chart and is the cheap direction to be wrong in — the
    /// alternative is a German reader getting the collision this fix exists to
    /// remove.
    static func xAxisLabelWidth(for style: XAxisPlan.LabelStyle) -> CGFloat {
        switch style {
        case .timeOfDay: return 41    // "12:30 PM"
        case .hourOfDay: return 31    // "04 Uhr"
        case .dayAndHour: return 50   // "Wed 12 AM"
        case .calendarDay: return 40  // "28. Sept."
        }
    }

    /// Ink-free space required between two neighbouring labels, in points.
    static let xAxisLabelMinGap: CGFloat = 6

    /// The tick spacing, in points, that an axis of `labelCount` labels of this
    /// width needs before two of them touch.
    ///
    /// **The END pairs are the binding constraint, and #3237 is why.** Every
    /// interior label is CENTRED on its tick, so two neighbours clear each other
    /// at `width + gap` of spacing. The first and last labels are anchored
    /// INWARD — the first grows right from its tick, the last grows left — so the
    /// pair at each end needs *half a label more*: `1.5 × width + gap`. When
    /// there are only two labels, both are end labels and they grow towards each
    /// other, so that pair needs `2 × width + gap`.
    ///
    /// The count budget this replaced was calibrated for centred labels, before
    /// the anchors moved. MEASURED on the live Ball State @ Ohio State chart
    /// (14793398, 2026-09-05 10:16 PT): a 47-minute domain took the 10-minute
    /// stride, 62pt of spacing, and 41pt labels — comfortable for a centred pair
    /// (47pt needed) and 3pt short for the anchored end pair (68pt needed). The
    /// phone drew `12:30 PM` and `12:40 PM` with their ink touching, and the "1"
    /// of the second label disappeared into the "M" of the first: the axis read
    /// **12:30 PM · 2:40 PM · 12:50 PM**, a time that never happened.
    ///
    /// This is 024's own lesson applied to itself — a rule that MOVES an element
    /// invalidates every spacing decision taken before the move.
    static func xAxisRequiredSpacing(labelWidth: CGFloat, labelCount: Int) -> CGFloat {
        if labelCount <= 2 { return 2 * labelWidth + xAxisLabelMinGap }
        return 1.5 * labelWidth + xAxisLabelMinGap
    }

    /// Does a stride's labels clear each other across a plot this wide?
    ///
    /// `intervals` is the nominal tick count (`duration / strideSeconds`), the
    /// same estimate the stride ladder uses; the label count is one more than the
    /// intervals that fit. Nothing here moves a tick or a domain — it only
    /// decides which stride is coarse enough to label.
    static func xAxisFits(
        intervals: Double, plotWidth: CGFloat, style: XAxisPlan.LabelStyle
    ) -> Bool {
        guard plotWidth > 0 else { return false }
        guard intervals > 0 else { return true }
        let spacing = plotWidth / CGFloat(intervals)
        let labelCount = Int(intervals.rounded(.down)) + 1
        return spacing >= xAxisRequiredSpacing(
            labelWidth: xAxisLabelWidth(for: style), labelCount: labelCount)
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
    ///
    /// `plotWidth` is the drawn plot area's width in points, measured by the
    /// chart itself. Pass 0 (the default) when it is not known yet: the fit then
    /// falls back to the per-style count budget, which is what every caller used
    /// before the geometry was available.
    static func xAxisPlan(
        for domain: ClosedRange<Date>, plotWidth: CGFloat = 0,
        calendar: Calendar = .current
    ) -> XAxisPlan {
        let duration = max(domain.upperBound.timeIntervalSince(domain.lowerBound), 0)
        let spansMultipleDays = !calendar.isDate(
            domain.lowerBound, inSameDayAs: domain.upperBound)

        for candidate in xAxisStrides {
            let style = labelStyle(
                strideSeconds: candidate.seconds, spansMultipleDays: spansMultipleDays)
            let ticks = duration / candidate.seconds
            let fits = plotWidth > 0
                ? xAxisFits(intervals: ticks, plotWidth: plotWidth, style: style)
                : ticks <= Double(maxTicks(for: style))
            if fits {
                return XAxisPlan(
                    component: candidate.component, count: candidate.count, labelStyle: style)
            }
        }
        let last = xAxisStrides[xAxisStrides.count - 1]
        return XAxisPlan(component: last.component, count: last.count, labelStyle: .calendarDay)
    }

    /// Where a time label hangs off its own tick (#3237).
    ///
    /// `anchor: .top` centres every label on its tick, which is right in the
    /// middle of the axis and wrong at both ends: the last tick sits ON the
    /// plot's trailing edge, so half the label is outside the plot and SwiftUI
    /// truncates what is left. Measured on 15303441 (Athletics @ Mariners,
    /// 2026-09-05): the axis drew `Fri 11 PM · Sat 12 AM · S…`, and "S…" is the
    /// END of the game — the part of the chart people actually read.
    ///
    /// So the two end labels hang INWARD: the last label's trailing edge sits on
    /// its tick and it grows left, the first label's leading edge sits on its
    /// tick and it grows right. Everything between still centres. Nothing moves
    /// the ticks themselves — this is labelling only, no change to the domain or
    /// the drawn line.
    ///
    /// `count <= 1` is the degenerate single-tick axis: centring is the least
    /// wrong thing when the same label is both ends.
    static func xAxisLabelAnchor(index: Int, count: Int) -> UnitPoint {
        guard count > 1 else { return .top }
        if index <= 0 { return .topLeading }
        if index >= count - 1 { return .topTrailing }
        return .top
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
