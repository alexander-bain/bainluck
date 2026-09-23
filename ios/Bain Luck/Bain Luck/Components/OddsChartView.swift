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
    /// #925 — WHEN each of period / clock / score on this point was observed:
    /// the game-state row that supplied THAT field, carried forward with it, so
    /// the readout can date what it shows ("as of 7:41 PM") instead of
    /// presenting an old game clock as something seen at this point's own time.
    ///
    /// Three dates and not one, because the three are observed by different
    /// rows — MLB serves a period with no clock, ESPN emits score-only rows, a
    /// clock-only row is the normal mid-period shape — and a row that observed
    /// one of them says nothing about the age of the other two (codex
    /// 2026-09-23: the reviewed candidate's shared date let a period-only row
    /// refresh a carried clock's age, and a clock-only row refresh a carried
    /// period's). Mirrors the web's `lib/chartGameState.ts`.
    var periodObservedAt: Date?
    var clockObservedAt: Date?
    var scoreObservedAt: Date?
    /// True when that field was carried from a row a minute or more older than
    /// this point (`OddsChartView.carriedStateIsApproximate`).
    var periodApprox: Bool = false
    var clockApprox: Bool = false
    var scoreApprox: Bool = false
    /// The backend's synthetic right-edge point (`WinProbHistoryPoint.liveEdge`):
    /// the last real value re-served at the request's own "now". It may end a
    /// line whose trailing interval is supported (`observationSegments`) and is
    /// otherwise not a reading — never a lone mark, never cadence.
    var isLiveEdge: Bool = false
}

// MARK: - Period Marker

private struct PeriodMarker: Identifiable {
    let id = UUID()
    let date: Date
    let label: String
    let isGameStart: Bool
    /// #3348 — who saw this boundary. Carried, not yet drawn: the chip strip
    /// prints observed markers exactly as before; estimated markers are never
    /// admitted to this type (see `extractPeriodMarkers`).
    var provenance: PeriodProvenance? = nil
}

/// #3348 — the provenance of one period boundary, whichever side of the wire
/// built it. `source` is an instrument name (the server's `statpal` /
/// `espn_box` / `win_prob` / `espn_state`, or this client's `espn_history` /
/// `win_prob_history`); `precision` is `boundary_observed`, `first_seen` or
/// `first_score`; `notBefore` is the last observation that showed an EARLIER
/// state, or nil when nothing bounds the start from below. A first observed
/// state is not an exact period start, and this is where that is written down.
struct PeriodProvenance: Equatable {
    /// Nil when the server sent a marker with no `source` at all — carried as
    /// unknown, never invented (#4135: a view names a source or draws none).
    let source: String?
    let precision: String?
    let notBefore: Date?

    static let clientPrecisionFirstSeen = "first_seen"
    static let clientSourceEspnHistory = "espn_history"
    static let clientSourceWinProbHistory = "win_prob_history"
}

/// #3348 — a served `period_markers` entry the client could read, normalised to
/// this chart's label vocabulary. Internal so the decode path is unit-testable.
struct ServedPeriodBoundary: Equatable {
    let label: String
    let date: Date
    /// The server said `estimated`: arithmetic, seen by nobody.
    let isEstimated: Bool
    /// A NAMED instrument saw it. Neither flag set = source missing = unknown,
    /// and unknown is drawn by nobody (`PeriodMarkerPayload.isObserved`).
    let isObserved: Bool
    let provenance: PeriodProvenance
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

    /// Take a payload the page has re-polled, if it is not older than the one on
    /// screen (#920).
    ///
    /// This exists because `preloadedHistory:` is read exactly once. SwiftUI
    /// evaluates a `StateObject`'s `wrappedValue` autoclosure on first appearance
    /// and discards it on every later body pass, so the 120 s poll's fresh
    /// payload arrived at this object's `init` and was thrown away — while
    /// `load()` below, guarded on `history == nil`, declined to fetch a
    /// replacement. Between them the chart could not advance at all, for as long
    /// as the reader kept the page open.
    ///
    /// Returns whether it took the payload, so a test can assert the refusal and
    /// not merely the absence of a change.
    @discardableResult
    @MainActor
    func adopt(_ fresh: EventHistoryResponse) -> Bool {
        guard EventHistoryFreshness.shouldAdopt(fresh, over: history) else { return false }
        history = fresh
        loading = false
        return true
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
    /// #6381 — the served `venue_settled`. Defaulted false: only the event
    /// detail page can know it, and that is this view's only call site.
    var venueSettled: Bool = false
    var homeTeamName: String?
    var awayTeamName: String?
    var homeTeamLogo: String?
    var awayTeamLogo: String?
    var homeTeamAbbrev: String?
    var awayTeamAbbrev: String?
    /// The event's sport key (`baseball_mlb`, `soccer_epl`, …).
    ///
    /// #3317. This view drew period chips for years without knowing what sport
    /// it was drawing, which is exactly how it came to stamp soccer's halves on
    /// a baseball game. Only `HalvesFromGap` reads it, and it FAILS CLOSED on
    /// nil — a chart that cannot name its sport infers nothing.
    /// `ScoreDifferentialChartView`, the other chart on this page, has taken the
    /// same `event.sport` since it was written.
    var sportKey: String?
    /// Countdown seconds until next data refresh (0 = just refreshed)
    var refreshCountdown: Int = 0
    /// Total refresh interval in seconds
    var refreshInterval: Int = 30
    /// True while the live push stream is delivering, in which case the poll is
    /// stood down and there is no next update to count down to (#2687).
    var refreshStreaming: Bool = false
    /// Shared domain from parent — ensures OddsChart and ScoreDiffChart have identical x-axes
    var forcedDomain: ClosedRange<Date>?
    /// Blends pushed to the page since it opened (#920), drawn as the live end
    /// of the backend's own aggregate line. Empty on every non-live surface.
    var liveFrames: [LiveBlendPoint] = []
    /// The page's current history, kept as a property and not merely consumed by
    /// `init`, because `init` runs once and this keeps arriving. `historyEdge`
    /// watches it; `OddsChartViewModel.adopt` decides.
    var preloadedHistory: EventHistoryResponse?
    /// Binding to expose the selected game play point (for GamePlayCardView)
    @Binding var selectedPlayPoint: GamePlayPoint?
    @StateObject private var vm: OddsChartViewModel
    @State private var selectedDate: Date?
    @State private var isFullscreen = false
    /// The drawn plot area's width, reported by each chart's own overlay. The
    /// x-axis needs it to know whether its labels clear each other (#3269); 0
    /// until the first layout pass, which is the documented fallback in
    /// `xAxisPlan`. One per chart — see `chartView`.
    @State private var inlinePlotWidth: CGFloat = 0
    @State private var fullscreenPlotWidth: CGFloat = 0
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
        status == "live" || EventState.isFinished(status)
    }

    /// Show the All / Since Start picker only when the game has started
    /// and we know when it started.
    private var showPicker: Bool {
        isGameStarted && gameStartDate != nil
    }

    /// Short team name: prefer ESPN abbreviation (e.g. "BOS"), fall back to the
    /// shared rule.
    ///
    /// #3430 — these two are the chart's two y-axis labels, one at each end of
    /// the same axis, and they are the only thing saying which way is which. On
    /// Clemson–LSU both read `TIGERS`, so a 100%-green curve told the reader
    /// nothing at all. The pair rule widens both until they separate.
    private var axisLabels: (away: String, home: String) {
        guard let away = awayTeamName, let home = homeTeamName else {
            return (awayTeamAbbrev ?? "Away", homeTeamAbbrev ?? "Home")
        }
        return TeamShortName.shortPair(
            away: away, home: home,
            awayServed: awayTeamAbbrev, homeServed: homeTeamAbbrev
        )
    }
    private var homeShort: String { axisLabels.home }
    private var awayShort: String { axisLabels.away }

    init(eventId: Int, teamColors: (away: Color, home: Color)? = nil,
         commenceTime: String? = nil, status: String? = nil,
         venueSettled: Bool = false,
         homeTeamName: String? = nil, awayTeamName: String? = nil,
         homeTeamLogo: String? = nil, awayTeamLogo: String? = nil,
         homeTeamAbbrev: String? = nil, awayTeamAbbrev: String? = nil,
         sportKey: String? = nil,
         refreshCountdown: Int = 0, refreshInterval: Int = 30,
         refreshStreaming: Bool = false,
         forcedDomain: ClosedRange<Date>? = nil,
         selectedPlayPoint: Binding<GamePlayPoint?> = .constant(nil),
         preloadedHistory: EventHistoryResponse? = nil,
         liveFrames: [LiveBlendPoint] = []) {
        self.eventId = eventId
        self.teamColors = teamColors
        self.commenceTime = commenceTime
        self.status = status
        self.venueSettled = venueSettled
        self.homeTeamName = homeTeamName
        self.awayTeamName = awayTeamName
        self.homeTeamLogo = homeTeamLogo
        self.awayTeamLogo = awayTeamLogo
        self.homeTeamAbbrev = homeTeamAbbrev
        self.awayTeamAbbrev = awayTeamAbbrev
        self.sportKey = sportKey
        self.refreshCountdown = refreshCountdown
        self.refreshInterval = refreshInterval
        self.refreshStreaming = refreshStreaming
        self.forcedDomain = forcedDomain
        self.liveFrames = liveFrames
        self.preloadedHistory = preloadedHistory
        _selectedPlayPoint = selectedPlayPoint
        _vm = StateObject(wrappedValue: OddsChartViewModel(eventId: eventId, preloaded: preloadedHistory))
    }

    /// #3410 — whether the payload holds a single reading, anywhere.
    ///
    /// Distinct from `hasDrawableLine`, which asks whether the SELECTED range can
    /// join two points of one source. This asks the prior question: is there
    /// anything in this payload at all, in any range, from any source? When the
    /// answer is no, no picker, no source toggle and no amount of waiting on this
    /// payload can put a line on the screen.
    static func hasNoReadings(in allPoints: [ChartDataPoint]) -> Bool {
        allPoints.isEmpty
    }

    /// What that section says, in the tense the game is actually in.
    ///
    /// #3859 — the sentence took NO state at all. On the full-time LAFC 2 — Real
    /// Salt Lake 2 (15304990), under a navigation bar reading `FT 90'+4'`, it said
    /// *"No win probability readings for this game YET"* — a reading that will
    /// never arrive, because nothing writes win-prob snapshots for a match that is
    /// over. It is #3821's defect two cards higher on the same page, and #3465's
    /// two cards lower than that; all three are Alex's standing ruling that
    /// settled means settled, which binds an empty state's copy as tightly as it
    /// binds a hero.
    ///
    /// The population is not a curiosity: every one of the ten most recently
    /// settled events sampled for #3859 held ZERO win-prob snapshots.
    ///
    /// Like ``EventState/noGameMarketsLine(status:)``, the settled reading NAMES
    /// NO CAUSE. This branch covers a match no source ever modelled and a match
    /// whose readings we simply never captured, and the view cannot tell them
    /// apart — so it drops the false promise and claims nothing in its place.
    ///
    /// Takes the raw status, not a `settled` flag, so the status test stays in
    /// ``EventState/isFinished(_:)`` where every other native reading of "is it
    /// over?" already comes from.
    /// #6381 — and the SECOND settled reading, added for the same reason as the
    /// first. A match the venue has already graded is over, so "yet" is the
    /// same false promise here as it is on a `completed` row; the hero one
    /// screen up now says "Settled" and this line sat under it still
    /// offering more readings to come. It takes the served flag and the clock
    /// rather than a precomputed boolean, so the test stays in `EventState`
    /// where every other native reading of "is it over?" comes from.
    ///
    /// `now` is injected for the reason gotcha #44 exists: the settled reading
    /// asks the CLOCK, so a test that could not pass one would be asserting
    /// against whatever today is. It caught itself here — the first draft took
    /// no `now`, and the "yet survives on a future fixture" case passed the
    /// real date into a fixed-anchor test and went red.
    static func noReadingsLine(
        status: String?,
        venueSettled: Bool = false,
        commenceTime: Date? = nil,
        now: Date = Date()
    ) -> String {
        let over = EventState.isFinished(status)
            || EventState.showsVenueSettledVerdict(
                status, venueSettled: venueSettled, commenceTime: commenceTime, now: now)
        return over
            ? "No win probability readings for this game."
            : "No win probability readings for this game yet."
    }

    /// True once the payload has LOADED and holds nothing. Deliberately false
    /// while loading and on error, so a slow network never reads as an empty
    /// game — those two states have their own answers below.
    private var noReadings: Bool {
        guard !vm.loading, vm.error == nil, let history = vm.history else { return false }
        return Self.hasNoReadings(in: buildDataPoints(history))
    }

    /// #3410 — what the section says when it has nothing to say.
    ///
    /// Photographed 2026-09-06 on a live esports match and the Chimaev–Whittaker
    /// fight (`artifacts-native-033/esports-15305748.png`,
    /// `mma-chimaev-15305758.png`): both drew a "Win Probability ● Live" heading,
    /// a live dot, an All / Since Start picker, a fullscreen button and a "View
    /// Probability Models" link — roughly 260pt of the phone — around a payload
    /// with `points: 0` and every one of `history`, `espn_history`,
    /// `win_prob_history`, `bookmaker_history` and `win_prob_sources` empty.
    ///
    /// #3278 made the middle of that frame say something true. It did not stop the
    /// frame being built, and chrome is a promise: a range picker says there is a
    /// range worth picking, a live dot says a number is moving. Ruling 027 — a
    /// surface earns its chrome — and the precedent is one line further down THIS
    /// page, where a game with no markets says so in a single sentence and draws
    /// nothing else.
    private var noReadingsNote: some View {
        HStack(spacing: 8) {
            Image(systemName: "chart.xyaxis.line")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(Self.noReadingsLine(
                status: status,
                venueSettled: venueSettled,
                commenceTime: commenceTime?.asDate))
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The live edge of the payload the PAGE holds, which is not necessarily the
    /// one this chart is drawing. `nil` until the page has any reading at all.
    private var historyEdge: Date? {
        preloadedHistory.flatMap(EventHistoryFreshness.lastReading(in:))
    }

    var body: some View {
        VStack(spacing: 8) {
            if noReadings {
                noReadingsNote
            } else {
                chartSection
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
        // #920. The page re-polls every 120 s and hands the result down; until
        // this existed, every one of those payloads was dropped on the floor by
        // a `StateObject` that only reads its initial value. Keyed on the live
        // edge rather than the payload because `EventHistoryResponse` is not
        // `Equatable` — and a date is the right key anyway: it changes exactly
        // when there is something new to draw.
        .onChange(of: historyEdge) { _, _ in
            guard let preloadedHistory else { return }
            vm.adopt(preloadedHistory)
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

    @ViewBuilder
    private var chartSection: some View {
        Group {
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
                let enrichedPoints = Self.enrichWithGameState(allPoints, history: history)
                let dataPoints = filterPoints(enrichedPoints)
                let periodMarkers = extractPeriodMarkers(history, filteredPoints: dataPoints)
                let moments = Self.chartMoments(from: history.moments, points: dataPoints)
                // #3278 — "drawable", not "non-empty". See `hasDrawableLine`: one
                // snapshot in the window rendered the whole frame around no line.
                if !Self.hasDrawableLine(in: dataPoints) {
                    Text(Self.emptyChartMessage(
                        range: vm.selectedRange,
                        hasAnyPointInRange: !dataPoints.isEmpty,
                        allIsDrawable: Self.hasDrawableLine(in: enrichedPoints),
                        status: status
                    ))
                        .font(.caption)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
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
                                    if let url = ChartGutterCrest.resolvedURL(
                                        servedURL: homeTeamLogo, teamName: homeTeamName, sportKey: sportKey) {
                                        ChartGutterCrest(url: url)
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
                                    if let url = ChartGutterCrest.resolvedURL(
                                        servedURL: awayTeamLogo, teamName: awayTeamName, sportKey: sportKey) {
                                        ChartGutterCrest(url: url)
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
                                  periodMarkers: periodMarkers, moments: moments,
                                  plotWidth: $inlinePlotWidth)
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
    }

    // MARK: - Gutter Crest (#3988 → #4117)

    // The crest and the ladder call that picks it now live on `ChartGutterCrest`
    // in `ChartGutterLabel.swift`, beside the label they sit next to. #3988 fixed
    // this gutter and by doing so made the Score Differential gutter 200pt below
    // it the next private rung — #4117 — so the shared thing is a shared thing.
    // The measurement that justified the ladder call is on `resolvedURL` there.

    // MARK: - Fullscreen Chart

    private var fullscreenChart: some View {
        NavigationView {
            Group {
                if let history = vm.history {
                    let allPoints = buildDataPoints(history)
                    let enrichedPoints = Self.enrichWithGameState(allPoints, history: history)
                    let dataPoints = filterPoints(enrichedPoints)
                    let periodMarkers = extractPeriodMarkers(history, filteredPoints: dataPoints)
                    let moments = Self.chartMoments(from: history.moments, points: dataPoints)
                    // #3278 — the same drawability test the inline chart uses. This
                    // branch used to render literally nothing (a blank sheet under a
                    // nav bar) when there were no points, and the full frame around
                    // no line when there was one. Both now say what is true, and the
                    // picker stays so "All" is reachable from here too.
                    if !Self.hasDrawableLine(in: dataPoints) {
                        VStack(spacing: 12) {
                            if showPicker {
                                HStack {
                                    Spacer()
                                    timeRangePicker
                                    Spacer()
                                }
                            }
                            Text(Self.emptyChartMessage(
                                range: vm.selectedRange,
                                hasAnyPointInRange: !dataPoints.isEmpty,
                                allIsDrawable: Self.hasDrawableLine(in: enrichedPoints),
                                status: status
                            ))
                                .font(.callout)
                                .multilineTextAlignment(.center)
                                .foregroundStyle(.secondary)
                            Spacer()
                        }
                        .padding()
                    } else {
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
                                        // #4117 — the same crest as the inline gutter.
                                        // #3988 fixed the chart above and left its own
                                        // fullscreen twin bare 120 lines below it, which
                                        // is the whole reason the crest is now shared
                                        // rather than written per call site.
                                        ChartGutterLabel(run: run) {
                                            HStack(spacing: 3) {
                                                if let url = ChartGutterCrest.resolvedURL(
                                                    servedURL: homeTeamLogo, teamName: homeTeamName, sportKey: sportKey) {
                                                    ChartGutterCrest(url: url)
                                                }
                                                Text(homeShort.uppercased())
                                                    .font(.system(size: 10, weight: .bold))
                                                    .foregroundStyle(teamColors?.home ?? .blue)
                                                    .lineLimit(1)
                                            }
                                        }
                                        Spacer()
                                        ChartGutterLabel(run: run) {
                                            HStack(spacing: 3) {
                                                if let url = ChartGutterCrest.resolvedURL(
                                                    servedURL: awayTeamLogo, teamName: awayTeamName, sportKey: sportKey) {
                                                    ChartGutterCrest(url: url)
                                                }
                                                Text(awayShort.uppercased())
                                                    .font(.system(size: 10, weight: .bold))
                                                    .foregroundStyle(teamColors?.away ?? .red)
                                                    .lineLimit(1)
                                            }
                                        }
                                    }
                                }
                                .frame(width: chartTeamGutterWidth)
                                .padding(.vertical, 12)

                                chartView(dataPoints: dataPoints, sources: history.winProbSources ?? [:],
                                          periodMarkers: periodMarkers, moments: moments,
                                          plotWidth: $fullscreenPlotWidth)
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
        } else if EventState.isFinished(status) {
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
        guard EventState.isFinished(status) else { return nil }
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
        if EventState.isFinished(status), let endDate = gameEndDate {
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
    ///
    /// **Every marker sits on a time the feed actually observed (#6718).** A
    /// period nobody saw begin is ABSENT from the chart; it is never drawn at
    /// the scheduled commence time. Alex, 2026-09-14: "align meaningful
    /// sport-specific state markers to evidenced times… scheduled kickoff/
    /// capture timestamps are not automatically actual start/finish."
    /// `ScoreDifferentialChartView` — the other half of the same event page —
    /// has always worked this way, using the scheduled start as a filter floor
    /// and never as a marker position.
    private func extractPeriodMarkers(_ history: EventHistoryResponse, filteredPoints: [ChartDataPoint]) -> [PeriodMarker] {
        var firstSeen: [(label: String, date: Date)] = []
        var seenLabels: Set<String> = []
        // #3348 — provenance per label, kept beside `firstSeen` rather than
        // widening the tuple every existing line reads.
        var provenance: [String: PeriodProvenance] = [:]

        // Try ESPN history first (has explicit period field)
        if let espnHistory = history.espnHistory, espnHistory.count >= 2 {
            let sorted = espnHistory
                .compactMap { point -> (period: String, date: Date)? in
                    guard let period = point.period, !period.isEmpty,
                          let date = point.timestamp.asDate else { return nil }
                    return (period, date)
                }
                .sorted { $0.date < $1.date }

            // The previous period-bearing observation in THIS series: the
            // period began after it (#3348 `notBefore`).
            var previous: Date?
            for point in sorted {
                let label = normalizePeriodLabel(point.period)
                guard !label.isEmpty else { continue }
                if !seenLabels.contains(label) {
                    seenLabels.insert(label)
                    firstSeen.append((label, point.date))
                    provenance[label] = PeriodProvenance(
                        source: PeriodProvenance.clientSourceEspnHistory,
                        precision: PeriodProvenance.clientPrecisionFirstSeen,
                        notBefore: previous)
                }
                previous = point.date
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

                var previous: Date?
                for point in sorted {
                    let label = normalizePeriodLabel(point.period)
                    guard !label.isEmpty else { continue }
                    if !seenLabels.contains(label) {
                        seenLabels.insert(label)
                        firstSeen.append((label, point.date))
                        provenance[label] = PeriodProvenance(
                            source: PeriodProvenance.clientSourceWinProbHistory,
                            precision: PeriodProvenance.clientPrecisionFirstSeen,
                            notBefore: previous)
                    }
                    previous = point.date
                }
            }
        }

        // #3348 — the served `period_markers`, read for the first time.
        //
        // OBSERVED markers only. A period this client did not see in either
        // log above is added at the time the server's instrument saw it; a
        // period it did see keeps its own chip where it is and gains the
        // server's provenance (`precision`, `not_before`) — nothing already
        // drawn moves. ESTIMATED markers (`source: "estimated"`, arithmetic on
        // the scheduled start) are NOT admitted: this chart has never drawn a
        // period nobody observed (#6718), and the web labels them `~Q1` while
        // this side keeps them absent — both are "not presented as observed";
        // whether the phone should also draw the labelled estimate is a
        // product call, recorded as open in the #3348 delivery, not decided
        // here. Unknown stays unknown.
        //
        // ONE EVIDENCE TUPLE PER CHIP. `timestamp / source / precision /
        // notBefore` describe ONE observation; a chip this client placed from
        // its own first-seen row keeps its own tuple, and the server's
        // `precision` / `not_before` — which describe the server's timestamp,
        // not the client's — are never copied onto it (codex 2026-09-23: the
        // reviewed candidate transplanted server certainty onto a local marker
        // at a potentially different time). A served marker for a label already
        // drawn is therefore ignored entirely; the chip does not move and its
        // provenance does not change.
        //
        // `isObserved`, not `!isEstimated`: a marker with no `source` is
        // unknown, and unknown is not admitted as observed.
        let servedMarkers = Self.servedPeriodMarkers(from: history.periodMarkers, sportKey: sportKey)
        Self.admitServedMarkers(servedMarkers, firstSeen: &firstSeen, seenLabels: &seenLabels, provenance: &provenance)

        // #6718 — NOTHING IS INSERTED HERE, AND THAT IS THE FIX.
        //
        // This is where a first-period marker used to be invented: if the feed
        // opened in Q2, a "Q1" was inferred from the labels present and placed
        // at `gameStartDate` — which is `commenceTime`, the SCHEDULED kickoff.
        // Two separate claims, both unevidenced: that the period happened at
        // all, and that it began when the fixture was listed to begin. A game
        // that starts late (weather, a preceding fixture, a broadcast window)
        // got a labelled boundary minutes or hours from anything observed, and
        // the chart read as though we had watched it.
        //
        // The server now states this rule on its own side: as of #6718 a
        // `boundary_observed` marker always carries a `not_before` lower bound,
        // and a transition the feed never bracketed is omitted rather than
        // pinned to kickoff. Absent beats invented on both sides of the wire.
        //
        // Do not reinstate this from the served `period_markers` either without
        // reading `not_before` — the app does not decode that payload yet, and
        // a marker is only as good as the bound it ships with.

        // Halftime inferred from a pause — gated on the sport actually playing
        // halves (#3317). The rule, why the previous `firstSeen.isEmpty` guard
        // was only half of one, and the production measurement that condemned
        // it, are all in `HalvesFromGap`; this is only the call.
        if firstSeen.isEmpty, !seenLabels.contains("HT") {
            let inferred = HalvesFromGap.markers(
                sportKey: sportKey,
                espnDates: (history.espnHistory ?? []).compactMap { $0.timestamp.asDate }
            )
            if !inferred.isEmpty {
                firstSeen = inferred
                seenLabels = Set(inferred.map(\.label))
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
            .map { PeriodMarker(date: $1.date, label: $1.label, isGameStart: false,
                                provenance: provenance[$1.label]) }
    }

    /// #3348 — the admission rule for served markers, pure so it is testable
    /// without a view: only an OBSERVED marker is admitted, only for a label
    /// nothing has drawn yet, and it arrives with its own evidence tuple. A
    /// label already drawn is skipped whole — its chip does not move and its
    /// provenance is not rewritten with the server's.
    static func admitServedMarkers(
        _ served: [ServedPeriodBoundary],
        firstSeen: inout [(label: String, date: Date)],
        seenLabels: inout Set<String>,
        provenance: inout [String: PeriodProvenance]
    ) {
        for marker in served where marker.isObserved {
            guard !seenLabels.contains(marker.label) else { continue }
            seenLabels.insert(marker.label)
            firstSeen.append((marker.label, marker.date))
            provenance[marker.label] = marker.provenance
        }
    }

    /// #3348 — the served `period_markers` this client can read, in date order.
    ///
    /// Pure and internal so the decode path is testable without a view. Drops a
    /// marker with no parseable timestamp or no period label this chart can
    /// print; keeps estimated AND unknown-source markers, FLAGGED, so the
    /// caller decides — the caller above admits only `isObserved`. `source` is
    /// carried verbatim; an unknown word names an instrument this client has
    /// not heard of and still counts as observed, while a MISSING source does
    /// not.
    static func servedPeriodMarkers(from markers: [PeriodMarkerPayload]?, sportKey: String?) -> [ServedPeriodBoundary] {
        guard let markers, !markers.isEmpty else { return [] }
        return markers
            .compactMap { m -> ServedPeriodBoundary? in
                guard let raw = m.timestamp, let date = raw.asDate,
                      let period = m.period, !period.isEmpty else { return nil }
                let label = PeriodLabel.normalize(period, sport: sportKey)
                guard !label.isEmpty else { return nil }
                return ServedPeriodBoundary(
                    label: label,
                    date: date,
                    isEstimated: m.isEstimated,
                    isObserved: m.isObserved,
                    provenance: PeriodProvenance(
                        source: m.source,
                        precision: m.precision,
                        notBefore: m.notBefore?.asDate))
            }
            .sorted { $0.date < $1.date }
    }

    // `inferFirstPeriodLabel(from:)` was removed with #6718. It answered "which
    // period is missing from the front of this list" so a marker could be
    // manufactured for it; nothing needs that question now that the answer is
    // never drawn. Its behaviour is pinned as a control in
    // `AChartMarkerSitsOnAnObservedTime6718Tests` so the defect stays provable.

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
            // One series per RUN of observations rather than per source (#7878).
            // Swift Charts joins whatever shares a series value, so a single
            // identifier per source drew one straight segment across a capture
            // hole — a flat line and no line became the same picture. Splitting
            // the identifier leaves the hole empty, which is what we actually
            // know. This is the same no-invention rule as `.interpolationMethod`
            // below, applied at the scale where it was still being broken.
            let segments = Self.observationSegments(points, gameStart: gameStartDate)
            ForEach(Array(segments.enumerated()), id: \.offset) { index, segment in
                ForEach(segment) { point in
                    LineMark(
                        x: .value("Time", point.date),
                        y: .value("Win probability", point.probability),
                        series: .value("Source", "\(source)#\(index)")
                    )
                    .foregroundStyle(color)
                    .lineStyle(stroke)
                    // Observed journey only — connect real snapshots with straight
                    // segments. Monotone/curve interpolation invented probability
                    // movement between sparse samples that was never captured, violating
                    // the settled no-smoothing ruling (C43 P1).
                    .interpolationMethod(.linear)
                }
                // A run of one is a real observation that no `LineMark` can
                // draw (it needs two points to join), so it would silently
                // vanish — losing data to a fix meant to stop losing data.
                if segment.count == 1, let only = segment.first {
                    PointMark(
                        x: .value("Time", only.date),
                        y: .value("Win probability", only.probability)
                    )
                    .foregroundStyle(color)
                    .symbolSize(18)
                }
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
                    .stroke(Color.systemBackground, lineWidth: 1.5)
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

    /// `plotWidth` is the caller's OWN measurement, not a shared one. The inline
    /// chart and the fullscreen sheet are the same view at two widths, and a
    /// single `@State` between them would let the sheet's 800pt plot decide the
    /// inline chart's axis for as long as it takes the inline chart to re-report
    /// its 293pt. Two bindings, no crosstalk.
    private func chartView(dataPoints: [ChartDataPoint], sources: [String: WinProbSourceInfo],
                           periodMarkers: [PeriodMarker], moments: [ChartMoment],
                           plotWidth: Binding<CGFloat>) -> some View {
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
            let plan = Self.xAxisPlan(
                for: xAxisDomain(for: dataPoints), plotWidth: plotWidth.wrappedValue)
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
            plotWidth.wrappedValue = width
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
        Self.chartPoints(from: history, liveFrames: liveFrames)
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
    /// - Parameter liveFrames: blends pushed to this page since it opened. Empty
    ///   for every caller that is not the live event page, which is why the
    ///   parameter is defaulted: this transform's other callers ask a question
    ///   about a payload, not about a socket.
    static func chartPoints(
        from history: EventHistoryResponse,
        liveFrames: [LiveBlendPoint] = []
    ) -> [ChartDataPoint] {
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
                var point = ChartDataPoint(date: date, probability: prob, source: sourceKey)
                point.isLiveEdge = wp.liveEdge == true
                points.append(point)
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

        return extendingBlendToLiveEdge(points, with: liveFrames, history: history)
    }

    /// Carry the blend forward to the frames the page has actually been pushed
    /// (#920), so the chart's right edge reaches the same moment the hero does.
    ///
    /// Three refusals, and each one is the whole point of doing this here rather
    /// than at the call site:
    ///
    /// 1. **No blend on the payload ⇒ no live edge.** A pushed frame carries the
    ///    aggregate, so appending it where the backend published no
    ///    `aggregate_line` would MINT the blend series on the client — the exact
    ///    thing `chartPoints`' first guarantee refuses, and worse than it looks:
    ///    `defaultVisibleSources` returns `["aggregate"]` the moment one such
    ///    point exists, so a single minted point would hide the consensus line
    ///    the reader was actually reading and draw nothing in its place.
    /// 2. **Settled means settled.** A finished payload is never extended. The
    ///    match is over, the backend's history is the complete journey, and a
    ///    late frame must not add a twitch past the end of the game.
    /// 3. **Only past the backend's own edge.** The 120 s poll keeps swallowing
    ///    this buffer's older half. Re-drawing a moment the payload already
    ///    covers would put two points on one timestamp, so the buffer only ever
    ///    contributes the part the server has not caught up to yet — and shrinks
    ///    to nothing by itself when it does.
    static func extendingBlendToLiveEdge(
        _ points: [ChartDataPoint],
        with liveFrames: [LiveBlendPoint],
        history: EventHistoryResponse
    ) -> [ChartDataPoint] {
        guard !liveFrames.isEmpty else { return points }
        guard !EventState.isFinished(history.status), history.completedAt == nil else { return points }

        let publishedEdge = points
            .filter { $0.source == "aggregate" }
            .map(\.date)
            .max()
        guard let publishedEdge else { return points }

        var extended = points
        for frame in liveFrames where frame.date > publishedEdge {
            extended.append(
                ChartDataPoint(date: frame.date, probability: frame.homeProbability, source: "aggregate")
            )
        }
        return extended
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

    // MARK: - Drawability (#3278, pure, unit-tested in OddsChartEmptyStateTests)

    /// Whether these points can actually produce a LINE.
    ///
    /// #3278 — the chart used to branch on `points.isEmpty`, but "not empty" and
    /// "drawable" are different questions and the gap between them is what a reader
    /// saw as a broken card: a live match five minutes after the first ball had ONE
    /// snapshot in the "Since Start" window, so the frame rendered in full — both
    /// rotated player labels, the gridlines, the legend — around no line at all,
    /// because a `LineMark` needs two points to join.
    ///
    /// The rule is PER SERIES, not per point. `chartContent` draws one series per
    /// visible source, so two sources holding one point each is two points and still
    /// no line; a total-count test (`count >= 2`) would call that drawable and
    /// reproduce the same empty frame. Only a source that has two of its own points
    /// draws anything.
    static func hasDrawableLine(in points: [ChartDataPoint]) -> Bool {
        let visible = Set(defaultVisibleSources(in: points))
        var perSource: [String: Int] = [:]
        for point in points where visible.contains(point.source) {
            perSource[point.source, default: 0] += 1
            if perSource[point.source]! >= 2 { return true }
        }
        return false
    }

    // MARK: - Observation gaps (#7878, pure, unit-tested in
    // AStalledCaptureDrawsAGapNotALine7878Tests)

    /// A capture hole long enough that joining across it would invent the
    /// interval, expressed BOTH ways because either test alone is wrong.
    ///
    /// Measured against production on 2026-09-21 over every in-game snapshot of
    /// the preceding 18 h (9,163 Kalshi intervals, 6,987 Polymarket):
    ///
    /// | | Kalshi | Polymarket |
    /// |---|---|---|
    /// | median interval | 48.0 s | 33.4 s |
    /// | p99 interval | 227.1 s | 138.9 s |
    /// | longest interval | 7,444.9 s | 371.9 s |
    /// | worst series' max ÷ its own median | 74.4× | 13.3× |
    ///
    /// `floor` sits above Kalshi's p99 AND above the longest in-game interval
    /// Polymarket produced at all, so ordinary slow polling never trips it.
    /// `cadenceMultiple` sits above the worst ratio any Polymarket series
    /// reached, so a legitimately SPARSE series is judged against its own
    /// rhythm rather than a stranger's — a 2-minute-cadence series and a
    /// 10-second one do not share a notion of "late".
    ///
    /// Requiring both is what makes this safe rather than merely tuned: over
    /// that window the floor alone flags 34 intervals, the ratio alone flags 34,
    /// and the conjunction flags 32 — they agree almost everywhere, so the rule
    /// is not balanced on a knife edge. Polymarket, the healthy control, flags
    /// ZERO under all three variants, and 30 of 133 Kalshi in-game events flag
    /// at least once.
    static let gapFloor: TimeInterval = 600
    static let gapCadenceMultiple: Double = 15

    /// Split one source's points into runs that may honestly be joined.
    ///
    /// Swift Charts joins every point sharing a `series` value, so a single
    /// series identifier per source is what draws a straight line across a
    /// three-hour hole — the reader cannot tell "nothing happened" from "we
    /// stopped watching", because both are one flat segment. Breaking the
    /// series is the whole fix: each run gets its own identifier and Charts
    /// leaves the hole empty.
    ///
    /// Two deliberate refusals:
    ///
    /// 1. **Pre-match intervals are never broken.** A market opens days before
    ///    play and sleeps overnight, so pre-commence series legitimately hold
    ///    multi-hour holes — measured p99 2.2 h, longest 5.6 DAYS. Applying an
    ///    in-game threshold there would shatter every healthy pre-match line
    ///    into confetti, a far worse lie than the one being fixed. Only
    ///    intervals with BOTH ends at or after `gameStart` are candidates, and
    ///    a nil `gameStart` breaks nothing at all.
    ///
    ///    This uses the SCHEDULED commence (Alex, 2026-09-14: a scheduled
    ///    kickoff is not an evidenced start), which means a hole in play that
    ///    began before the scheduled time is left joined. That is the cheap
    ///    direction to be wrong in: a missed break shows what we show today,
    ///    while a false break invents a hole in a line that never had one.
    ///
    /// 2. **The cadence is the series' own.** The median is taken over the
    ///    in-game intervals being judged, so the rule cannot import a fast
    ///    series' expectations into a slow one.
    ///
    /// A series whose gap leaves a run of one point is returned as a run of one
    /// — the caller draws those as a mark rather than dropping them, because a
    /// lone observation is something we genuinely saw and a `LineMark` needs two
    /// points to render.
    ///
    /// **The synthetic live edge is not an observation** (`isLiveEdge`, codex
    /// 2026-09-23 on #7547/#7878 D). It is the last real value re-served at the
    /// request's "now", so it neither seeds the cadence nor splits a run, and
    /// it is never returned alone — a run of one there would be a mark at an
    /// instant nobody read. It is kept for one job only, the web's
    /// (`chartObservationSupport.ts`): the anchor of the TRAILING interval. A
    /// supported trailing interval ends the last run at it, as today; an
    /// unsupported one ends the line at the last real observation, with nothing
    /// drawn after it.
    static func observationSegments(
        _ points: [ChartDataPoint],
        gameStart: Date?,
        floor: TimeInterval = OddsChartView.gapFloor,
        cadenceMultiple: Double = OddsChartView.gapCadenceMultiple
    ) -> [[ChartDataPoint]] {
        let ordered = points.filter { !$0.isLiveEdge }.sorted { $0.date < $1.date }
        guard !ordered.isEmpty else { return [] }
        let liveEdge = points.filter(\.isLiveEdge).max { $0.date < $1.date }

        var segments: [[ChartDataPoint]] = [ordered]
        var median: TimeInterval?
        if ordered.count > 1, let gameStart {
            // The series' own in-game rhythm. Taken over exactly the intervals
            // the rule can act on, so a long pre-match sleep cannot inflate it
            // and thereby excuse a real in-game hole.
            var inGameIntervals: [TimeInterval] = []
            for (previous, current) in zip(ordered, ordered.dropFirst())
            where previous.date >= gameStart {
                inGameIntervals.append(current.date.timeIntervalSince(previous.date))
            }
            if !inGameIntervals.isEmpty {
                let sortedIntervals = inGameIntervals.sorted()
                let cadence = sortedIntervals[sortedIntervals.count / 2]
                median = cadence

                segments = []
                var run: [ChartDataPoint] = [ordered[0]]
                for (previous, current) in zip(ordered, ordered.dropFirst()) {
                    let interval = current.date.timeIntervalSince(previous.date)
                    let inGame = previous.date >= gameStart && current.date >= gameStart
                    if inGame, interval > floor, interval > cadenceMultiple * cadence {
                        segments.append(run)
                        run = [current]
                    } else {
                        run.append(current)
                    }
                }
                segments.append(run)
            }
        }

        // The trailing interval, judged by the same three conditions. No
        // in-game cadence (or no `gameStart`) means nothing is judged.
        if let liveEdge, let lastReal = ordered.last, liveEdge.date > lastReal.date {
            let interval = liveEdge.date.timeIntervalSince(lastReal.date)
            var unsupported = false
            if let gameStart, let median, lastReal.date >= gameStart {
                unsupported = interval > floor && interval > cadenceMultiple * median
            }
            if !unsupported {
                segments[segments.count - 1].append(liveEdge)
            }
        }
        return segments
    }

    /// What to say instead of an empty frame (#3278).
    ///
    /// D27's honest-empty rule: an empty screen is not an answer. This never invents
    /// a range — the picker keeps saying what is selected and the chart keeps
    /// obeying it. It points at "All" only when `allIsDrawable` says All genuinely
    /// has a line to show, so the suggestion can never send a reader to a second
    /// empty frame.
    ///
    /// #3859 — THREE OF THESE FOUR SENTENCES WERE TENSED and none of them could
    /// see the game's state, so a finished match was told to keep waiting. `status`
    /// is REQUIRED rather than defaulted: a default is exactly how ``noReadingsNote``
    /// came to print "yet" over a full-time header for as long as it did, and a
    /// future call site that has not thought about the tense should fail to compile
    /// rather than quietly pick the promising one.
    ///
    /// READ THE FOUR AS A BLOCK, not row by row — that is #3823's lesson. A per-row
    /// rule can be right on every row and still leave the card saying one thing six
    /// times. It does not happen here: the settled set holds exactly as many
    /// distinct sentences as the unsettled one, which
    /// `testTheSettledSetSaysAsMuchAsTheUnsettledOne` pins.
    ///
    /// "No probability data available" is untensed already and is left alone.
    static func emptyChartMessage(
        range: OddsTimeRange,
        hasAnyPointInRange: Bool,
        allIsDrawable: Bool,
        status: String?
    ) -> String {
        let over = EventState.isFinished(status)
        guard range == .sinceStart else {
            guard hasAnyPointInRange else { return "No probability data available" }
            return over
                ? "Not enough readings to draw a line."
                : "Not enough readings yet to draw a line."
        }
        let lead: String
        if hasAnyPointInRange {
            lead = over
                ? "Not enough readings since the start to draw a line."
                : "Not enough readings since the start to draw a line yet."
        } else {
            lead = over ? "No readings since the start." : "No readings since the start yet."
        }
        // "Switch to", not "Tap": this view runs on macOS too (it branches on
        // `os(iOS)` for the fullscreen presentation), where there is nothing to tap.
        //
        // The offer survives settlement deliberately: on a finished game "All" still
        // holds the pre-match market, and a reader who cannot see a line since the
        // first whistle is exactly the reader that helps.
        return allIsDrawable ? lead + " Switch to All for the pre-match market." : lead
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
    /// Static and internal (was a private instance method) so #925's dating of
    /// carried state can be pinned on the exact shape it runs on.
    static func enrichWithGameState(_ points: [ChartDataPoint], history: EventHistoryResponse) -> [ChartDataPoint] {
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
        // #925 — THREE observation clocks, one per field the readout prints,
        // because the three are observed by different rows: MLB serves
        // `period: null` on most ESPN rows (a score row must not refresh the
        // AGE of a half-inning last seen minutes earlier), and a clock-only
        // row is the normal mid-period shape (it must not refresh the age of
        // the period it never saw). Same contract as the web's
        // `carryGameStateForward` (`lib/chartGameState.ts`).
        var lastPeriodObservedAt: Date?
        var lastClockObservedAt: Date?
        var lastScoreObservedAt: Date?
        /// Cursor into `espnByTime`: every row strictly before the current
        /// point's cutoff has already been folded into the accumulators above.
        var espnIdx = 0

        for i in sorted.indices {
            let pointDate = sorted[i].date

            // The latest ESPN row this point may read. Rows up to the END OF
            // THE POINT'S OWN MINUTE count as this point's observation (the
            // web keys its rows by minute and calls a same-minute row exact by
            // construction); a row in a LATER minute never reaches an earlier
            // point. The +90s look-ahead this replaces let a first observation
            // at 20:32:30 stand, unmarked and exact, on the 20:31:00 price —
            // a state nobody had seen yet, at a minute the reader can tell
            // apart (codex 2026-09-23 correction).
            let cutoff = Self.observationCutoff(for: pointDate)

            // EVERY row this point may read, not just the newest one. The three
            // `last*` values above are ACCUMULATORS — each field keeps the last
            // row that actually carried it — so every row has to be walked for
            // them to accumulate. Sampling only `espnByTime.last(where:)` reads
            // one row per point and silently drops every row that falls BETWEEN
            // two points, which is most of them: prices are sparser than ESPN
            // rows, and the rows that go missing are exactly the ones this ship
            // is about (a score-only row is the common MLB shape, so the period
            // seen three minutes earlier never reached the accumulator and the
            // reader got NO half-inning at all rather than a dated one).
            // Points and rows are both sorted ascending and `cutoff` rises with
            // them, so one cursor over the rows visits each exactly once.
            while espnIdx < espnByTime.count, espnByTime[espnIdx].date < cutoff {
                let row = espnByTime[espnIdx]
                if let hs = row.point.homeScore {
                    lastScore = (hs, row.point.awayScore ?? lastScore?.away ?? 0)
                    // A row that REPEATS the score is still an observation of it.
                    lastScoreObservedAt = row.date
                }
                if let p = row.point.period, !p.isEmpty {
                    lastPeriod = p
                    lastPeriodObservedAt = row.date
                }
                if let c = row.point.gameClock, !c.isEmpty {
                    lastClock = c
                    lastClockObservedAt = row.date
                }
                espnIdx += 1
            }

            // Forward-fill game state, each field dated by the row that saw IT.
            sorted[i].homeScore = lastScore?.home
            sorted[i].awayScore = lastScore?.away
            sorted[i].period = lastPeriod
            sorted[i].clock = lastClock
            sorted[i].periodObservedAt = lastPeriod == nil ? nil : lastPeriodObservedAt
            sorted[i].clockObservedAt = lastClock == nil ? nil : lastClockObservedAt
            sorted[i].scoreObservedAt = lastScore == nil ? nil : lastScoreObservedAt
            sorted[i].periodApprox = Self.carriedStateIsApproximate(pointDate: pointDate, observedAt: sorted[i].periodObservedAt)
            sorted[i].clockApprox = Self.carriedStateIsApproximate(pointDate: pointDate, observedAt: sorted[i].clockObservedAt)
            sorted[i].scoreApprox = Self.carriedStateIsApproximate(pointDate: pointDate, observedAt: sorted[i].scoreObservedAt)

            // Check for scoring play at this timestamp (within 60s)
            sorted[i].scoringPlay = playsByTime.first(where: {
                abs($0.date.timeIntervalSince(pointDate)) < 60
            })?.play
        }

        return sorted
    }

    /// #925 — the first instant an ESPN row is TOO NEW for a point to read:
    /// the start of the minute after the point's own. A row inside the point's
    /// minute is the same observation at the chart's resolution; a row in the
    /// next minute is a later observation and belongs to later points.
    static func observationCutoff(for pointDate: Date) -> Date {
        let minute = floor(pointDate.timeIntervalSince1970 / 60) * 60
        return Date(timeIntervalSince1970: minute + 60)
    }

    /// #925 — is a field on a point CARRIED from an older observation?
    ///
    /// The row that supplied the field is `observedAt`; the point the reader is
    /// scrubbing is `pointDate`. Sixty seconds is the chart's own resolution
    /// (the web keys its rows by minute and calls a same-minute carry exact by
    /// construction). No observation at all is not "approximate": there is
    /// nothing to be stale about (a late first observation leaves the minutes
    /// before it with no state, not with a doubtful one).
    static let carriedStateApproximateAfterSeconds: TimeInterval = 60

    static func carriedStateIsApproximate(pointDate: Date, observedAt: Date?) -> Bool {
        guard let observedAt else { return false }
        return pointDate.timeIntervalSince(observedAt) >= carriedStateApproximateAfterSeconds
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
            // #5271 — nil on a draw-priced sport rather than the complement.
            awayProb: DrawPricedWinner.printablePair(
                away: 1.0 - nearest.probability,
                home: nearest.probability,
                sport: sportKey)?.away,
            homeScore: nearest.homeScore,
            awayScore: nearest.awayScore,
            period: nearest.period,
            clock: nearest.clock,
            scoringPlay: nearest.scoringPlay,
            periodObservedAt: nearest.periodObservedAt,
            clockObservedAt: nearest.clockObservedAt,
            scoreObservedAt: nearest.scoreObservedAt,
            periodApprox: nearest.periodApprox,
            clockApprox: nearest.clockApprox,
            scoreApprox: nearest.scoreApprox
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
            /// "Wed 6 PM" — the domain spans more than one calendar day, hourly
            /// or coarser ticks.
            case dayAndHour
            /// "Wed 6:45 PM" — spans days AND ticks finer than an hour.
            ///
            /// #3269. Without this style a sub-hour stride across midnight took
            /// `dayAndHour` and dropped the minutes, so two different ticks
            /// printed the same label: MEASURED on 15302915 (the Yankees @
            /// Padres walk-off, 9:40 PM - 12:15 AM) the axis read
            /// **Fri 9 PM · Fri 10 PM · Fri 11 PM · Fri 11 PM** at 45-minute
            /// ticks. A duplicate label is the same lie as a wrong one.
            case dayAndTime
            /// "Sep 3" — the domain spans days, ticks a day or coarser.
            case calendarDay
            /// "Sep 2026" — ticks a season or coarser, where a bare "Sep 3"
            /// would repeat itself a year apart.
            case monthAndYear
        }

        let component: Calendar.Component
        let count: Int
        let labelStyle: LabelStyle

        var format: Date.FormatStyle {
            switch labelStyle {
            case .timeOfDay: return .dateTime.hour().minute()
            case .hourOfDay: return .dateTime.hour()
            case .dayAndHour: return .dateTime.weekday(.abbreviated).hour()
            case .dayAndTime: return .dateTime.weekday(.abbreviated).hour().minute()
            case .calendarDay: return .dateTime.month(.abbreviated).day()
            case .monthAndYear: return .dateTime.month(.abbreviated).year()
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
        case .dayAndTime: return 4
        case .calendarDay: return 6
        case .monthAndYear: return 5
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
        case .timeOfDay: return 41     // "12:30 PM"
        case .hourOfDay: return 31     // "04 Uhr"
        case .dayAndHour: return 50    // "Wed 12 AM"
        case .dayAndTime: return 63    // "Mo, 10:58 Uhr"
        case .calendarDay: return 40   // "28. Sept."
        case .monthAndYear: return 49  // "Sept. 2026"
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
    /// same estimate the stride ladder uses. Nothing here moves a tick or a
    /// domain — it only decides which stride is coarse enough to label.
    ///
    /// **The count charged here is the SMALLEST the stride can draw, and #3400 is
    /// why.** `xAxisRequiredSpacing` gets *cheaper* as the count grows: three
    /// labels have a centred interior one and cost `1.5 × width`, two are both
    /// end labels growing towards each other and cost `2 × width`. So the
    /// optimistic count is the unsafe one, and a nominal `intervals` in **[2, 3)**
    /// is exactly where the drawn count is genuinely ambiguous — the axis draws
    /// two ticks or three depending on where the stride's origin falls relative
    /// to the domain's edges, which is the charting framework's business, not
    /// ours. `floor(intervals) + 1` assumed three every time and charged the
    /// interior rate for an axis that drew two.
    ///
    /// MEASURED on two LIVE US Open charts, master `79f34e4e`, iPhone 17 at
    /// 3.0px/pt, plot width 302.7pt: 15304537 (Tabilo v Zverev) took the
    /// 30-minute stride at 103.7pt of spacing and 15304445 (Tien v Mensik) the
    /// 45-minute stride at 119.3pt, both against the 132pt an end pair needs.
    /// Both drew two ticks and printed `Sat 11:08SPaMt 11:38 PM` — one smear
    /// where two times belong. On the same build 15293316 (Atlante v Atlas) had
    /// 145.3pt and cleared, so the requirement was never wrong; the count was.
    ///
    /// Charging `floor` costs at most half a label width on a domain that would
    /// have drawn three, and only inside that one band — the conservative
    /// direction, for the same reason `xAxisLabelWidth` pins the widest locale.
    static func xAxisFits(
        intervals: Double, plotWidth: CGFloat, style: XAxisPlan.LabelStyle
    ) -> Bool {
        guard plotWidth > 0 else { return false }
        guard intervals > 0 else { return true }
        let spacing = plotWidth / CGFloat(intervals)
        let labelCount = Int(intervals.rounded(.down))
        return spacing >= xAxisRequiredSpacing(
            labelWidth: xAxisLabelWidth(for: style), labelCount: labelCount)
    }

    /// Which label a stride needs.
    ///
    /// The rule underneath all four cases is that **no two ticks may print the
    /// same label**: a label must carry every field that changes between
    /// neighbouring ticks. So minutes appear exactly when the stride is
    /// sub-hourly (in or out of one day), the weekday appears exactly when the
    /// domain crosses one, and the year appears once the ticks are far enough
    /// apart that a month-and-day would come round again (#3269).
    private static func labelStyle(
        strideSeconds: TimeInterval, spansMultipleDays: Bool
    ) -> XAxisPlan.LabelStyle {
        if strideSeconds >= 180 * 86400 { return .monthAndYear }
        if strideSeconds >= 86400 { return .calendarDay }
        if spansMultipleDays { return strideSeconds < 3600 ? .dayAndTime : .dayAndHour }
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
    ///
    /// `sportKey` is passed for #4888: it is consulted for a BARE period number
    /// and nothing else, because that is the one period string carrying no unit
    /// noun of its own. Every verbose period this chart actually receives today
    /// is still read from its noun.
    private func normalizePeriodLabel(_ raw: String) -> String {
        PeriodLabel.normalize(raw, sport: sportKey)
    }
}
