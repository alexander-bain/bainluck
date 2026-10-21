import XCTest
@testable import Bain_Luck

/// #9483 / #11356 — **an iPhone reader follows one clear probability line,
/// reads the correct team's chance at each edge of a focused window, and can
/// open Sources without the line, its time axis or the plot box moving.**
///
/// The host half of Design's native single-trajectory brief: what
/// `OddsChartView` hands `ChartProbabilityAxis9483` (whose own rules are pinned
/// in `ChartProbabilityAxisNamesEachEdge9483Tests`), what the gutter and the
/// end label say, and the wiring that keeps the line's identity, the Sources
/// disclosure and the TipKit attachment seams in place.
///
/// Every expected window below was computed from the frozen web rules (the
/// same rules the helper transfers) on the same inputs. The Jaguars–Eagles
/// values are the retained 14639175 window (Oct 11 14:35–15:05Z, 31 blend
/// readings ending 0.515873), in their original order; their instants here are
/// evenly spaced inside that window because only the ORDER (which reading is a
/// line's last) reaches the range rules. Native keys the sportsbook series
/// `consensus` where the web case named it `sportsbooks_consensus`.
///
/// UNEXECUTED when written: authored without a Swift compiler, to be run by
/// Native's single Apple executor at its qualification boundary.
@MainActor
final class ChartSingleTrajectory11356Tests: XCTestCase {

    private typealias Axis = ChartProbabilityAxis9483
    private typealias Chart = OddsChartView

    private static let windowStart = Date(timeIntervalSince1970: 1_791_729_300) // 2026-10-11T14:35:00Z
    private static let windowLength: TimeInterval = 30 * 60

    private func window(_ lower: Int, _ upper: Int, _ ticks: [Int]) -> Axis.Window {
        Axis.Window(lowerPercent: lower, upperPercent: upper, tickPercents: ticks)
    }

    /// `values` as one source's points, in order, spread across the window.
    private func series(_ values: [Double], source: String,
                        from start: Date = windowStart,
                        over length: TimeInterval = windowLength) -> [ChartDataPoint] {
        let step = values.count > 1 ? length / Double(values.count - 1) : 0
        return values.enumerated().map { index, value in
            ChartDataPoint(date: start.addingTimeInterval(Double(index) * step), probability: value, source: source)
        }
    }

    private func ramp(_ a: Double, _ b: Double, _ n: Int) -> [Double] {
        (0..<n).map { a + (b - a) * Double($0) / Double(n - 1) }
    }

    // MARK: - The real recorded window (Jaguars–Eagles 14639175)

    private let jaxMain: [Double] = [
        0.717791, 0.6979, 0.668393, 0.658436, 0.658225, 0.66001, 0.664191, 0.678234, 0.513586,
        0.489777, 0.491252, 0.491173, 0.491699, 0.492127, 0.502546, 0.512279, 0.538764, 0.539359,
        0.542035, 0.546801, 0.528168, 0.507077, 0.545058, 0.542734, 0.538679, 0.558333, 0.545699,
        0.546621, 0.541488, 0.528012, 0.515873
    ]

    private let jaxSources: [String: [Double]] = [
        "consensus": [
            0.7309, 0.7087, 0.6756, 0.6592, 0.6588, 0.6639, 0.6686, 0.6875, 0.5515, 0.5025, 0.5049, 0.5083,
            0.505, 0.5074, 0.5116, 0.5277, 0.5701, 0.5718, 0.5722, 0.5708, 0.5497, 0.5274, 0.5641, 0.5821,
            0.5685, 0.6006, 0.579, 0.5887, 0.5847, 0.577, 0.555
        ],
        "kalshi": [
            0.715, 0.705, 0.665, 0.635, 0.655, 0.655, 0.655, 0.655, 0.66, 0.665, 0.69, 0.525, 0.525, 0.525,
            0.525, 0.525, 0.525, 0.525, 0.535, 0.525, 0.56, 0.535, 0.545, 0.575, 0.565, 0.565, 0.565,
            0.575, 0.565, 0.555, 0.545, 0.545, 0.575, 0.585, 0.565, 0.565, 0.615, 0.585, 0.585, 0.585,
            0.575, 0.545, 0.53
        ],
        "polymarket": [
            0.725, 0.685, 0.68, 0.665, 0.675, 0.64, 0.655, 0.655, 0.655, 0.665, 0.645, 0.525, 0.525, 0.53,
            0.52, 0.55, 0.525, 0.53, 0.565, 0.565, 0.54, 0.57, 0.565, 0.57, 0.565, 0.575, 0.585, 0.56,
            0.56, 0.545, 0.57, 0.575, 0.59, 0.555, 0.57, 0.575, 0.62, 0.605, 0.595, 0.585, 0.59, 0.565,
            0.545, 0.525
        ],
        "espn": [
            0.7262, 0.7049, 0.6704, 0.6546, 0.6543, 0.6838, 0.4946, 0.4918, 0.4962, 0.4894, 0.4977, 0.5094,
            0.5705, 0.5926, 0.5725, 0.5255, 0.5992, 0.5822, 0.5745, 0.5679, 0.5679, 0.5631, 0.5634
        ],
        "stat_model": [
            0.6727, 0.6722, 0.6709, 0.668, 0.668, 0.668, 0.6666, 0.4401, 0.4023, 0.4023, 0.4023, 0.4023,
            0.3979, 0.3939, 0.3862, 0.38, 0.38, 0.38, 0.38, 0.3752, 0.3739, 0.3739, 0.369, 0.368, 0.3676,
            0.3676, 0.3676
        ],
    ]

    /// The chart's points: the blend and all five source series, every one of
    /// them inside the window, exactly as `filterPoints` would hand them over.
    private func jaxPoints() -> [ChartDataPoint] {
        series(jaxMain, source: "aggregate")
            + jaxSources.keys.sorted().flatMap { series(jaxSources[$0] ?? [], source: $0) }
    }

    private func jaxWindow(sourcesOpen: Bool) -> Axis.Window {
        let points = jaxPoints()
        return Chart.probabilityWindow9483(
            points: points,
            defaultSources: Chart.defaultVisibleSources(in: points),
            revealed: sourcesOpen ? Chart.revealableSources9483(in: points) : [])
    }

    func testTheRecordedWindowWidensWhenSourcesOpensAndRestoresWhenItCloses() {
        XCTAssertEqual(jaxWindow(sourcesOpen: false), window(45, 75, [45, 50, 55, 60, 65, 70, 75]),
                       "closed: the blend's own window")
        XCTAssertEqual(jaxWindow(sourcesOpen: true), window(30, 80, [30, 40, 50, 60, 70, 80]),
                       "open: widened to the revealed lines")
        XCTAssertEqual(jaxWindow(sourcesOpen: false), window(45, 75, [45, 50, 55, 60, 65, 70, 75]),
                       "reclosed: the same focused window again")
    }

    /// #11356's defect: the five vendor lines sat in the payload, undrawn, and
    /// still set the zoom for the one line drawn. Closed, they size nothing.
    func testASourceThatIsNotDrawnNeverSizesTheWindow() {
        let points = jaxPoints()
        let closed = jaxWindow(sourcesOpen: false)
        let blendAlone = Chart.probabilityWindow9483(
            points: series(jaxMain, source: "aggregate"), defaultSources: ["aggregate"], revealed: [])
        XCTAssertEqual(closed, blendAlone)
        XCTAssertGreaterThan(Set(points.map(\.source)).count, 1, "control: the payload does carry the sources")
        XCTAssertNotEqual(closed, jaxWindow(sourcesOpen: true), "control: drawing them does widen it")
    }

    func testEveryDrawnLineStaysInsideItsWindowAndTheLineIsUnedited() {
        let points = jaxPoints()
        let before = points.map { "\($0.source)@\($0.date.timeIntervalSince1970)=\($0.probability)" }
        for open in [false, true] {
            let w = jaxWindow(sourcesOpen: open)
            XCTAssertTrue(jaxMain.allSatisfy { w.domain.contains($0) }, "\(w)")
            if open {
                for (name, values) in jaxSources {
                    XCTAssertTrue(values.allSatisfy { w.domain.contains($0) }, name)
                }
            }
        }
        XCTAssertEqual(points.map { "\($0.source)@\($0.date.timeIntervalSince1970)=\($0.probability)" }, before)
    }

    // MARK: - What Sources can add

    func testSourcesListsEveryOtherSourceInTheWindowBehindABlendOnly() {
        let points = jaxPoints()
        XCTAssertEqual(Chart.revealableSources9483(in: points),
                       ["consensus", "espn", "kalshi", "polymarket", "stat_model"],
                       "sportsbook consensus first, then by key; the count is the list's, never a constant")
        let threeSources = points.filter { ["aggregate", "kalshi", "polymarket", "espn"].contains($0.source) }
        XCTAssertEqual(Chart.revealableSources9483(in: threeSources), ["espn", "kalshi", "polymarket"])
        // Without a blend every line is already drawn: nothing to disclose.
        let noBlend = points.filter { $0.source != "aggregate" }
        XCTAssertEqual(Chart.revealableSources9483(in: noBlend), [])
        XCTAssertEqual(Set(Chart.defaultVisibleSources(in: noBlend)), Set(jaxSources.keys),
                       "control: the fail-closed full set is drawn instead")
    }

    // MARK: - Checkpoints and live minutes (the web call site's inputs)

    private func checkpoint(_ rev: Int64, _ date: Date, _ p: Double) -> PublicationJourney4974.Checkpoint {
        PublicationJourney4974.Checkpoint(
            vertex: PublicationCheckpointVertex(rev: rev, t: date.ISO8601Format(), p: p), date: date)
    }

    /// Every drawn checkpoint counts as a reading; only the LATEST is also
    /// forced onto the plot. Each wrong routing gives a different window.
    func testEveryCheckpointIsAReadingAndOnlyTheLatestMustShow() {
        let survivors = series(ramp(0.60, 0.70, 60), source: "aggregate")
        let early = checkpoint(1, Self.windowStart.addingTimeInterval(30), 0.20)
        let latest = checkpoint(2, Self.windowStart.addingTimeInterval(1_700), 0.66)
        let w = Chart.probabilityWindow9483(points: survivors, defaultSources: ["aggregate"], revealed: [],
                                            checkpoints: [latest, early], blendSurvivors: survivors)
        XCTAssertEqual(w, window(45, 70, [45, 50, 55, 60, 65, 70]))
        // What each wrong routing would have drawn (the frozen web rules on the same input):
        XCTAssertNotEqual(w, window(20, 70, [20, 30, 40, 50, 60, 70]), "every checkpoint forced on the plot")
        XCTAssertNotEqual(w, window(55, 75, [55, 60, 65, 70, 75]), "checkpoints left out of the readings")
    }

    /// Under a checkpoint mount the blend's drawn points are its survivors,
    /// not the raw series: a reading the recorded window cut out sizes nothing.
    func testUnderAMountTheBlendIsSizedByWhatTheMountStillDraws() {
        let raw = series([0.05] + ramp(0.60, 0.70, 30), source: "aggregate")
        let survivors = Array(raw.dropFirst())
        let mounted = Chart.probabilityWindow9483(points: raw, defaultSources: ["aggregate"], revealed: [],
                                                  checkpoints: [], blendSurvivors: survivors)
        let unmounted = Chart.probabilityWindow9483(points: survivors, defaultSources: ["aggregate"], revealed: [])
        XCTAssertEqual(mounted, unmounted)
    }

    func testAMinuteRangeIsTwoDifferentObservationsInOneMinute() {
        let t = Self.windowStart
        let points = [
            ChartDataPoint(date: t, probability: 0.55, source: "aggregate"),
            ChartDataPoint(date: t.addingTimeInterval(20), probability: 0.85, source: "aggregate"),
            ChartDataPoint(date: t.addingTimeInterval(40), probability: 0.55, source: "aggregate"),
            ChartDataPoint(date: t.addingTimeInterval(60), probability: 0.6, source: "aggregate"),
            ChartDataPoint(date: t.addingTimeInterval(120), probability: 0.6, source: "aggregate"),
            ChartDataPoint(date: t.addingTimeInterval(130), probability: 0.6, source: "aggregate"),
        ]
        XCTAssertEqual(Chart.liveMinuteRangeEnds9483(points), [0.55, 0.85],
                       "a lone reading and a minute of one repeated value carry no range")
    }

    /// A live minute's spike is inked, so while live it is on the plot; a
    /// finished (or not-live) chart keeps the percentile's focus.
    func testLiveMinuteEndsWidenTheWindowOnlyWhileLive() {
        var points = series(ramp(0.50, 0.60, 40), source: "aggregate",
                            over: 39 * 60)
        let minute = points[20].date
        points += [
            ChartDataPoint(date: minute.addingTimeInterval(20), probability: 0.85, source: "aggregate"),
            ChartDataPoint(date: minute.addingTimeInterval(40), probability: 0.55, source: "aggregate"),
        ]
        points.sort { $0.date < $1.date }
        let notLive = Chart.probabilityWindow9483(points: points, defaultSources: ["aggregate"], revealed: [],
                                                  liveAndOpen: false)
        let live = Chart.probabilityWindow9483(points: points, defaultSources: ["aggregate"], revealed: [],
                                               liveAndOpen: true)
        XCTAssertEqual(notLive, window(45, 70, [45, 50, 55, 60, 65, 70]))
        XCTAssertEqual(live, window(40, 90, [40, 50, 60, 70, 80, 90]))
    }

    // MARK: - What the axis means

    func testTheAxisIsTwoSidedOnlyOnTheAdmittedTwoOutcomeQuestion() {
        XCTAssertEqual(Chart.axisSides9483(sportKey: "americanfootball_nfl", servedHome: 0.52, servedAway: 0.48),
                       .homeAndAway)
        XCTAssertEqual(Chart.axisSides9483(sportKey: "americanfootball_nfl", servedHome: 0.52, servedAway: nil),
                       .homeOnly, "an unserved away side is never assumed, never 1 − home")
        XCTAssertEqual(Chart.axisSides9483(sportKey: "soccer_uefa_champs_league", servedHome: 0.32, servedAway: 0.45),
                       .homeOnly, "a draw-priced question has no away pole (#10318)")
        XCTAssertEqual(Chart.axisSides9483(sportKey: nil, servedHome: 0.5, servedAway: 0.5), .homeOnly)
        XCTAssertEqual(Chart.axisSides9483(sportKey: "", servedHome: 0.5, servedAway: 0.5), .homeOnly)
    }

    func testThePolesSayTheirDirectionAndTheReadingAtTheirEdge() {
        let jax = Chart.AxisPlan9483(sides: .homeAndAway, window: window(45, 75, [45, 50, 55, 60, 65, 70, 75]),
                                     revealed: [])
        XCTAssertEqual(jax.homePoleSentence(homeName: "JAX", awayName: "PHI"),
                       "The line rises towards JAX: the top of this view is JAX at 75%.")
        XCTAssertEqual(jax.awayPoleSentence(homeName: "JAX", awayName: "PHI"),
                       "The line falls towards PHI: the bottom of this view is PHI at 55%.")

        let homeSide = Chart.AxisPlan9483(sides: .homeAndAway, window: window(60, 80, [60, 65, 70, 75, 80]),
                                          revealed: [])
        XCTAssertEqual(homeSide.awayPoleSentence(homeName: "JAX", awayName: "PHI"),
                       "The line falls towards PHI: the bottom of this view is JAX at 60%.",
                       "a window entirely above 50% never acquires an away edge")

        let full = Chart.AxisPlan9483(sides: .homeAndAway, window: Axis.full, revealed: [])
        XCTAssertEqual(full.awayPoleSentence(homeName: "GB", awayName: "DAL"),
                       "The line falls towards DAL: the bottom of this axis is DAL at 100%.")

        // Stuttgart–Atlético 15330334 on Native's own cutoff (see the window test below).
        let stuttgart = Chart.AxisPlan9483(sides: .homeOnly, window: window(0, 75, [0, 25, 50, 75]), revealed: [])
        XCTAssertEqual(stuttgart.homePoleSentence(homeName: "VFB", awayName: "ATM"),
                       "The line rises towards VFB: the top of this view is VFB at 75%. "
                       + "The bottom of this view is VFB at 0%.")
    }

    /// Native's Stuttgart subset ends on the blend's 20:51Z 0.055763 (the
    /// ESPN-plus-120-second cutoff), not the selected web frame's later 9%.
    /// That end must stay on the plot, which spans more than 50 points and so
    /// snaps to the 25-point grid: 0–75 closed AND open, where the web frame's
    /// 0–60 → 0–75 came from its later end. A different admitted subset, not a
    /// defect; no point is restored to match the web pixels. Shape only — the
    /// retained rows are Native's to mount.
    func testAHomeOnlyLineEndingNearZeroKeepsItsEndOnThePlot() {
        let line = series([0.298947] + ramp(0.35, 0.5845, 60) + ramp(0.5, 0.06, 50) + [0.055763],
                          source: "aggregate")
        let w = Chart.probabilityWindow9483(points: line, defaultSources: ["aggregate"], revealed: [])
        XCTAssertEqual(w, window(0, 75, [0, 25, 50, 75]))
        XCTAssertTrue(w.domain.contains(0.055763), "the last recorded chance is on the plot")
        let ticks = w.tickPercents.map { Axis.tick(percent: $0, sides: .homeOnly) }
        XCTAssertTrue(ticks.allSatisfy { $0.side == .home }, "no away tick on a draw-priced line")
    }

    // MARK: - The end of a finished line

    func testTheEndLabelNamesTheSideItsDotSitsOn() {
        XCTAssertEqual(Chart.endLabelText9483(probability: 0.97, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "GB 97%")
        XCTAssertEqual(Chart.endLabelText9483(probability: 0.03, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "DAL 97%", "below 50% the dot is the away side's, as the tick beside it says")
        XCTAssertEqual(Chart.endLabelText9483(probability: 0.5, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "GB 50%")
        XCTAssertEqual(Chart.endLabelText9483(probability: 1, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "GB 100%")
        XCTAssertEqual(Chart.endLabelText9483(probability: 0, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "DAL 100%")
        XCTAssertEqual(Chart.endLabelText9483(probability: 0.055763, sides: .homeOnly,
                                              homeShort: "VFB", awayShort: "ATM"),
                       "VFB 6%", "a home-only line names the home side's chance, never a 94% away")
        XCTAssertNil(Chart.endLabelText9483(probability: .nan, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"))
        XCTAssertNil(Chart.endLabelText9483(probability: 1.2, sides: .homeOnly, homeShort: "GB", awayShort: "DAL"))
    }

    func testTheEndLabelStepsOffTheLineItEnds() {
        let size = CGSize(width: 40, height: 16)
        let plot = CGSize(width: 300, height: 200)
        let end = CGPoint(x: 250, y: 60)
        // Climbed in: the line under the label is lower on screen, so the label sits above.
        XCTAssertEqual(Chart.endLabelCenter9483(end: end, size: size, lineYBeneath: 120, plot: plot, topReserve: 20),
                       CGPoint(x: 224, y: 50))
        // Fell in: below.
        XCTAssertEqual(Chart.endLabelCenter9483(end: end, size: size, lineYBeneath: 30, plot: plot, topReserve: 20),
                       CGPoint(x: 224, y: 70))
        // A climb to the top with no room above the dot (the chips' band): below.
        XCTAssertEqual(Chart.endLabelCenter9483(end: CGPoint(x: 250, y: 22), size: size, lineYBeneath: 120,
                                                plot: plot, topReserve: 20),
                       CGPoint(x: 224, y: 32))
        // Never past the plot's left edge.
        XCTAssertEqual(Chart.endLabelCenter9483(end: CGPoint(x: 10, y: 100), size: size, lineYBeneath: nil,
                                                plot: plot, topReserve: 20).x, 20)
    }

    // MARK: - The gutter

    func testThePolesArrowIsTakenOutOfTheNamesRunNotOutOfTheText() {
        XCTAssertEqual(Chart.gutterNameRun9483(run: 100, fontSize: 12), 100 - 12 - ChartGutter.crestSpacing)
        XCTAssertEqual(Chart.gutterNameRun9483(run: 5, fontSize: 12), 0)
    }

    // MARK: - Wiring (source scans; the body is not rendered in tests)

    private func chartCode() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components/OddsChartView.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func count(_ needle: String, in text: String) -> Int {
        text.components(separatedBy: needle).count - 1
    }

    func testThePlotDrawsTheFocusedWindowClippedWithFixedWidthTicks() throws {
        let chart = try chartCode()
        XCTAssertTrue(chart.contains("structOddsChartView:View{"), "control: the scan reads the chart")
        XCTAssertTrue(chart.contains(".chartYScale(domain:axis.window.domain)"))
        XCTAssertFalse(chart.contains(".chartYScale(domain:yMin...yMax)"), "the fixed 0–1 scale is back")
        XCTAssertTrue(chart.contains(".chartPlotStyle{plotinplot.clipped()}"),
                      "a percentile-cut spike would paint over the axis and the card")
        XCTAssertTrue(chart.contains("AxisMarks(position:.leading,values:axis.window.ticks)"))
        XCTAssertTrue(chart.contains("Text(Self.widestTickLabel9483).font(.system(size:axisFontSize)).hidden()"),
                      "a tick label that does not reserve \"100%\" moves the plot's left edge with the window")
        XCTAssertEqual(count("letaxis=axisPlan9483(dataPoints:dataPoints,checkpoints:checkpoints,", in: chart), 2,
                       "inline and full size each plan one axis for gutter and plot")
        XCTAssertEqual(count("checkpoints:checkpoints,axis:axis,", in: chart), 2)
    }

    func testTheLineKeepsOneIdentity() throws {
        let chart = try chartCode()
        for retired in ["BinaryWinChartBalanceInkLayer(", "balancePlan(", "pairedLineColors(",
                        "BinaryWinBalanceMount.sideColor(", "paired?.home"] {
            XCTAssertFalse(chart.contains(retired), "the line takes team colours again: \(retired)")
        }
        XCTAssertTrue(chart.contains("lineColor:colorForSource(liveSplit.source,sources:sources),"),
                      "the live tail wears the line's own colour")
        XCTAssertTrue(chart.contains("case\"aggregate\":returnColor(hex:\"#059669\")"))
    }

    /// The arrival halo is the end of the line it rides, so it wears that
    /// line's colour — never the home team's over an emerald blend. Only the
    /// colour moved: the finished page's resting dot stays still (`activity:
    /// nil`, `isLive: false`) and the live gates are the ones it had.
    func testTheArrivalHaloWearsThePrimaryLinesColour() throws {
        let chart = try chartCode()
        let start = try XCTUnwrap(chart.range(of: "LiveChartEdgeMarker(selection:selection,"))
        let end = try XCTUnwrap(chart.range(of: "ifletfinishedEnd{", range: start.upperBound..<chart.endIndex))
        let feedback = String(chart[start.lowerBound..<end.lowerBound])
        XCTAssertFalse(feedback.contains("teamColors"), "a halo takes the home team's colour again")
        XCTAssertTrue(feedback.contains("activity:priceActivity,pulseColor:colorForSource(liveSplit.source,sources:sources))"),
                      "live: the halo and the tail share the line's colour")
        XCTAssertTrue(feedback.contains("LiveChartEndpointFeedback(selection:selection,activity:nil,probability:probability,"
                                        + "isLive:false,color:colorForSource(PublicationCheckpointMount4974.blendSource,"
                                        + "sources:sources))"),
                      "finished: the resting dot is the checkpoint layer's colour and never animates")
        XCTAssertTrue(feedback.contains("isLive:EventPriceStreaming.isEligible(status)&&liveUpdateStatus!=.interrupted"
                                        + "&&quoteIsCurrent,color:colorForSource(Self.primarySource(in:dataPoints),"
                                        + "sources:sources))"),
                      "fallback: the ring is the colour of the primary line its point is taken from")
    }

    func testSourcesIsOneToggleThatAddsLinesUnderThePrimary() throws {
        let chart = try chartCode()
        XCTAssertTrue(chart.contains("sourcesOpen:$inlineSourcesOpen,rail:false)"))
        XCTAssertTrue(chart.contains("sourcesOpen:$fullscreenSourcesOpen,rail:true)"),
                      "the full-size key is the one-row rail")
        XCTAssertEqual(count("fullscreenSourcesOpen=inlineSourcesOpenisFullscreen=true", in: chart), 2,
                       "every way into full size starts on the inline choice")
        XCTAssertTrue(chart.contains("sourcesShowButton(count:revealable.count,"),
                      "the count is the eligible sources', never a constant")
        // Revealed lines are drawn BEFORE the primary, so the primary is on top.
        let revealed = try XCTUnwrap(chart.range(of: "ForEach(axis.revealed,id:\\.self)"))
        let primary = try XCTUnwrap(chart.range(of: "ForEach(Self.defaultVisibleSources(in:dataPoints),id:\\.self)"))
        XCTAssertLessThan(revealed.lowerBound, primary.lowerBound)
    }

    /// The Sources control is easy to tap: both its states hit-test a frame at
    /// least 44pt tall and wide (the caption alone is ~26pt), laid in the key's
    /// own row AFTER the plot's fixed frame, so the extra height never comes
    /// out of the plot box.
    func testTheSourcesToggleHitsA44PointFrameOutsideThePlot() throws {
        let chart = try chartCode()
        let show = try XCTUnwrap(chart.range(of: "privatefuncsourcesShowButton("))
        let hide = try XCTUnwrap(chart.range(of: "privatefuncsourcesHideButton("))
        let after = try XCTUnwrap(chart.range(of: "privatefuncisMultiSource(", range: hide.upperBound..<chart.endIndex))
        let buttons = String(chart[show.lowerBound..<after.lowerBound])
        XCTAssertEqual(count(".frame(minWidth:44,minHeight:44,alignment:.leading).contentShape(Rectangle())", in: buttons), 2,
                       "each state's shape is laid on its 44pt frame, not on the caption")
        XCTAssertFalse(buttons.contains(".padding(.vertical,6).contentShape("), "the ~26pt target is back")
        XCTAssertTrue(chart.contains("tennis:tennis)}.frame(height:chartHeight)legendView(dataPoints:dataPoints,"
                                     + "sources:history.winProbSources??[:],sourcesOpen:$inlineSourcesOpen,rail:false)"),
                      "inline: the key sits below the fixed-height plot")
        XCTAssertTrue(chart.contains(".frame(height:enlargedPlotFloor)legendView(dataPoints:dataPoints,"
                                     + "sources:history.winProbSources??[:],sourcesOpen:$fullscreenSourcesOpen,rail:true)"),
                      "full size: the key is its own row under the plot row")
    }

    /// The four seams UX's later TipKit re-cut attaches to (HOST-COMPOSITION-
    /// CONSTRAINTS-AB5B), held by name.
    func testTheTipKitAttachmentSeamsAreKept() throws {
        let chart = try chartCode()
        XCTAssertTrue(chart.contains("staticfuncprimarySource(in"), "(a) the drawn primary line's name")
        XCTAssertTrue(chart.contains("@Environment(\\.chartScrubSurfaces)privatevarscrubSurfaces"), "(a)")
        XCTAssertTrue(chart.contains("tennis:tennis)}.frame(height:chartHeight)"),
                      "(a)/(b) the one inline chart container, framed at the inline height")
        XCTAssertEqual(count("selection.end()", in: chart), 1, "(c) one scrub end")
        XCTAssertTrue(chart.contains("iflettennis,letdate=selection.date{tennisPin.hold(tennis.inspect(at:date))}selection.end()"),
                      "(c) the onEnd still runs with the selection alive before end()")
    }

    /// The plot owner reads no finger state (#8651): the new end label is static.
    func testTheNewChartPartsReadNoFingerState() throws {
        let chart = try chartCode()
        let start = try XCTUnwrap(chart.range(of: "extensionOddsChartView{structAxisPlan9483"))
        let end = try XCTUnwrap(chart.range(of: "structChartGutterDirection9483:View{",
                                            range: start.upperBound..<chart.endIndex))
        XCTAssertFalse(chart[start.lowerBound..<end.lowerBound].contains("selection"))
    }
}
