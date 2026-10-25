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
            revealed: sourcesOpen ? Chart.revealableSources9483(in: points, withheld: []) : [])
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
        XCTAssertEqual(Chart.revealableSources9483(in: points, withheld: []),
                       ["consensus", "espn", "kalshi", "polymarket", "stat_model"],
                       "sportsbook consensus first, then by key; the count is the list's, never a constant")
        let threeSources = points.filter { ["aggregate", "kalshi", "polymarket", "espn"].contains($0.source) }
        XCTAssertEqual(Chart.revealableSources9483(in: threeSources, withheld: []), ["espn", "kalshi", "polymarket"])
        // Without a blend every line is already drawn: nothing to disclose.
        let noBlend = points.filter { $0.source != "aggregate" }
        XCTAssertEqual(Chart.revealableSources9483(in: noBlend, withheld: []), [])
        XCTAssertEqual(Set(Chart.defaultVisibleSources(in: noBlend)), Set(jaxSources.keys),
                       "control: the fail-closed full set is drawn instead")
    }

    // MARK: - Which sources Sources may reveal (the selected web rule)

    /// One served `stat_model` group, decoded as the app decodes it: one point
    /// per entry of `timeSources`, each entry the raw `time_source` JSON
    /// fragment (`nil` = the key is absent). Synthetic: these are causal
    /// controls for the rule, not recorded games.
    private func servedGroup(_ timeSources: [String?]) throws -> [WinProbHistoryPoint] {
        let items = timeSources.enumerated().map { index, raw -> String in
            let timeSource = raw.map { ",\"time_source\":\($0)" } ?? ""
            return "{\"timestamp\":\"2026-10-11T14:\(10 + index % 50):00Z\",\"home_probability\":0.6,"
                + "\"game_state\":{\"period\":\"2\",\"clock\":\"10:00\",\"home_score\":7,\"away_score\":3\(timeSource)}}"
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode([WinProbHistoryPoint].self, from: Data("[\(items.joined(separator: ","))]".utf8))
    }

    private let wallClock: String? = "\"wall_clock\""
    private let espnClock: String? = "\"espn\""

    func testTheModelIsWithheldOnlyWhenMostOfItsWholeGroupIsWallClocked() throws {
        func withheld(_ timeSources: [String?]) throws -> Set<String> {
            Chart.withheldSources9483(served: ["stat_model": try servedGroup(timeSources),
                                               "aggregate": try servedGroup([wallClock, wallClock, wallClock])])
        }
        XCTAssertEqual(try withheld([wallClock, wallClock, espnClock]), ["stat_model"], "2 of 3: a majority")
        XCTAssertEqual(try withheld([wallClock, wallClock, wallClock, espnClock, espnClock]), ["stat_model"])
        XCTAssertEqual(try withheld([wallClock, wallClock, espnClock, espnClock]), [], "exactly half is not a majority")
        XCTAssertEqual(try withheld([wallClock, wallClock]), [], "two points are never judged")
        XCTAssertEqual(try withheld([espnClock, espnClock, espnClock]), [])
        XCTAssertEqual(try withheld([wallClock, nil, nil]), [], "a missing clock is not wall-clock")
        XCTAssertEqual(Chart.withheldSources9483(served: ["espn": try servedGroup([wallClock, wallClock, wallClock])]),
                       [], "the rule is the model's only")
        XCTAssertEqual(Chart.withheldSources9483(served: nil), [])
    }

    /// The retained real groups (C3-RETAINED-INPUT-EXPECTATIONS.json) all KEEP
    /// the model, so they are controls only; the counts are theirs, the points
    /// are rebuilt to those counts. Stuttgart 15330334 serves no model at all.
    func testTheRetainedClockedModelsStayEligible() throws {
        XCTAssertEqual(Chart.withheldSources9483(served: ["stat_model": try servedGroup(Array(repeating: espnClock, count: 27))]),
                       [], "Jaguars 14639175: 27 ESPN-clocked")
        XCTAssertEqual(Chart.withheldSources9483(served: ["stat_model": try servedGroup(Array(repeating: espnClock, count: 18))]),
                       [], "Bears 14780549 one-side: 18 ESPN-clocked")
        XCTAssertEqual(Chart.withheldSources9483(
            served: ["stat_model": try servedGroup(Array(repeating: espnClock, count: 101) + [nil])]),
                       [], "Bears 14780549 final: 101 ESPN-clocked and one missing")
        XCTAssertEqual(Chart.withheldSources9483(served: ["aggregate": try servedGroup([espnClock, espnClock, espnClock])]),
                       [], "Stuttgart shape: no model group")
    }

    /// A withheld model leaves all three things Sources owns: the count, the
    /// lines and the window. The Jaguars window opens to 30–80 only because of
    /// the model's 0.37s; withheld (as if the same group had been wall-clocked)
    /// the open window is the other four sources', 45–75.
    func testAWithheldModelIsNotCountedDrawnOrSized() {
        let points = jaxPoints()
        let revealed = Chart.revealableSources9483(in: points, withheld: ["stat_model"])
        XCTAssertEqual(revealed, ["consensus", "espn", "kalshi", "polymarket"])
        XCTAssertEqual(Chart.probabilityWindow9483(points: points, defaultSources: Chart.defaultVisibleSources(in: points),
                                                   revealed: revealed),
                       window(45, 75, [45, 50, 55, 60, 65, 70, 75]))
        XCTAssertEqual(jaxWindow(sourcesOpen: true), window(30, 80, [30, 40, 50, 60, 70, 80]),
                       "control: eligible, the model widens it")
        let noBlend = points.filter { $0.source != "aggregate" }
        XCTAssertTrue(Chart.defaultVisibleSources(in: noBlend).contains("stat_model"),
                      "the no-blend fallback still draws every line; only the new disclosure obeys the rule")
    }

    /// `time_source` is additive: absent, null or a shape this build cannot
    /// read is nil, and never costs the point, its fields or its siblings.
    func testAnUnreadableTimeSourceNeverDropsAPointOrItsFields() throws {
        let group = try servedGroup(["7", "null", "{\"x\":1}", nil, espnClock, wallClock])
        XCTAssertEqual(group.count, 6, "every point decoded")
        XCTAssertEqual(group.map { $0.gameState?.timeSource }, [nil, nil, nil, nil, "espn", "wall_clock"])
        for point in group {
            XCTAssertEqual(point.homeProbability, 0.6)
            XCTAssertEqual(point.gameState?.period, "2")
            XCTAssertEqual(point.gameState?.clock, "10:00")
            XCTAssertEqual(point.gameState?.homeScore, 7)
            XCTAssertEqual(point.gameState?.awayScore, 3)
            XCTAssertNil(point.gameState?.inning)
        }
        XCTAssertEqual(Chart.withheldSources9483(served: ["stat_model": Array(group.prefix(4)) + [group[5]]]), [],
                       "unreadable is never counted as wall-clock")
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
        XCTAssertEqual(Chart.endLabelCenter9483(end: end, size: size, lineYBeneath: 120, plot: plot, topReserve: 20,
                                                ink: noInk),
                       CGPoint(x: 224, y: 50))
        // Fell in: below.
        XCTAssertEqual(Chart.endLabelCenter9483(end: end, size: size, lineYBeneath: 30, plot: plot, topReserve: 20,
                                                ink: noInk),
                       CGPoint(x: 224, y: 70))
        // A climb to the top with no room above the dot (the chips' band): below.
        XCTAssertEqual(Chart.endLabelCenter9483(end: CGPoint(x: 250, y: 22), size: size, lineYBeneath: 120,
                                                plot: plot, topReserve: 20, ink: noInk),
                       CGPoint(x: 224, y: 32))
        // Never past the plot's left edge.
        XCTAssertEqual(Chart.endLabelCenter9483(end: CGPoint(x: 10, y: 100), size: size, lineYBeneath: nil,
                                                plot: plot, topReserve: 20, ink: noInk).x, 20)
    }

    // MARK: - The end label clears the final climb (C2)

    private let noInk: (ClosedRange<CGFloat>) -> ClosedRange<CGFloat>? = { _ in nil }

    /// The ink of `runs` (and lone `marks`) as the chart measures it for a 3pt line.
    private func ink(_ runs: [[CGPoint]], marks: [CGPoint] = []) -> (ClosedRange<CGFloat>) -> ClosedRange<CGFloat>? {
        { span in
            Chart.inkExtent9483(runs: runs, marks: marks, across: span, halfStroke: 1.5,
                                markRadius: Chart.inkMarkRadius9483)
        }
    }

    /// Whether a plate centred at `center` lies on that ink.
    private func plateCoversInk(_ center: CGPoint, _ size: CGSize,
                                _ ink: (ClosedRange<CGFloat>) -> ClosedRange<CGFloat>?) -> Bool {
        guard let line = ink((center.x - size.width / 2)...(center.x + size.width / 2)) else { return false }
        return center.y + size.height / 2 > line.lowerBound && center.y - size.height / 2 < line.upperBound
    }

    /// A 270pt plot showing 25–100 (Packers-shaped final, #11356) or 0–75 (its
    /// mirror, a collapse); a 50 × 14 plate. Geometry controls, not renders.
    private let platePlot = CGSize(width: 300, height: 270)
    private let plate = CGSize(width: 50, height: 14)
    private func yOnTopWindow(_ p: CGFloat) -> CGFloat { (1 - (p - 0.25) / 0.75) * 270 }
    private func yOnBottomWindow(_ p: CGFloat) -> CGFloat { (1 - p / 0.75) * 270 }

    func testAFinalClimbToTheTopIsNotPaintedOutByItsLabel() {
        let climb = [(150, 0.80), (230, 0.92), (250, 0.96), (270, 0.99), (290, 1.0)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnTopWindow(CGFloat($0.1))) }
        let end = CGPoint(x: 290, y: 0)
        let placed = Chart.endLabelCenter9483(end: end, size: plate, lineYBeneath: yOnTopWindow(0.96),
                                              plot: platePlot, topReserve: 20, ink: ink([climb]))
        XCTAssertFalse(plateCoversInk(placed, plate, ink([climb])), "\(placed)")
        XCTAssertEqual(placed.x, 259)
        XCTAssertEqual(placed.y, 34.42, accuracy: 0.001, "just below the climb's ink, not further")
        // Removal control: without the ink the frame's placement sits on the climb.
        let blind = Chart.endLabelCenter9483(end: end, size: plate, lineYBeneath: yOnTopWindow(0.96),
                                             plot: platePlot, topReserve: 20, ink: noInk)
        XCTAssertEqual(blind, CGPoint(x: 259, y: 27))
        XCTAssertTrue(plateCoversInk(blind, plate, ink([climb])), "control: the case bites")
    }

    func testAFinalCollapseToTheBottomIsNotPaintedOutByItsLabel() {
        let fall = [(150, 0.20), (230, 0.08), (250, 0.04), (270, 0.01), (290, 0.0)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnBottomWindow(CGFloat($0.1))) }
        let end = CGPoint(x: 290, y: 270)
        let placed = Chart.endLabelCenter9483(end: end, size: plate, lineYBeneath: yOnBottomWindow(0.04),
                                              plot: platePlot, topReserve: 20, ink: ink([fall]))
        XCTAssertFalse(plateCoversInk(placed, plate, ink([fall])), "\(placed)")
        XCTAssertEqual(placed.y, 235.58, accuracy: 0.001, "just above the collapse's ink")
        let blind = Chart.endLabelCenter9483(end: end, size: plate, lineYBeneath: yOnBottomWindow(0.04),
                                             plot: platePlot, topReserve: 20, ink: noInk)
        XCTAssertEqual(blind, CGPoint(x: 259, y: 261))
        XCTAssertTrue(plateCoversInk(blind, plate, ink([fall])), "control: the case bites")
    }

    /// The ink is read only once the frame moved the label, and the step is
    /// the web's bounded one.
    func testTheLabelStepsOnlyWhenTheFrameMovedItAndNeverFurtherThanTheBound() {
        let size = CGSize(width: 40, height: 16)
        let plot = CGSize(width: 300, height: 200)
        XCTAssertEqual(Chart.endLabelCenter9483(end: CGPoint(x: 250, y: 60), size: size, lineYBeneath: 120,
                                                plot: plot, topReserve: 20, ink: { _ in 52...70 }),
                       CGPoint(x: 224, y: 50), "at its preferred spot the label never moves for the ink")
        // A climb so steep under the plate that clearing it is a 56pt jump
        // (bound: max(2 × 14, 10% × 270) = 28): the frame's placement stands.
        let steep = [(200, 0.75), (240, 0.80), (257, 0.90), (274, 0.97), (290, 1.0)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnTopWindow(CGFloat($0.1))) }
        XCTAssertEqual(Chart.endLabelCenter9483(end: CGPoint(x: 290, y: 0), size: plate,
                                                lineYBeneath: yOnTopWindow(0.90), plot: platePlot,
                                                topReserve: 20, ink: ink([steep])),
                       CGPoint(x: 259, y: 27))
    }

    /// The ink is the drawn runs: a break between runs has none, and a lone
    /// mark counts at its own radius.
    func testTheInkIsWhatTheLineDrawsAndNeverABridgedGap() {
        let span: ClosedRange<CGFloat> = 234...284
        let broken = [[CGPoint(x: 200, y: 100), CGPoint(x: 230, y: 90)], [CGPoint(x: 288, y: 5), CGPoint(x: 290, y: 0)]]
        XCTAssertNil(Chart.inkExtent9483(runs: broken, marks: [], across: span, halfStroke: 1.5, markRadius: 2),
                     "nothing is drawn across the break")
        let joined = Chart.inkExtent9483(runs: [broken.flatMap { $0 }], marks: [], across: span,
                                         halfStroke: 1.5, markRadius: 2)
        XCTAssertNotNil(joined, "control: one run does lay ink there")
        let unplaced = [[CGPoint(x: 200, y: 100), CGPoint(x: 230, y: 90), CGPoint(x: CGFloat.nan, y: 50),
                         CGPoint(x: 288, y: 5), CGPoint(x: 290, y: 0)]]
        XCTAssertNil(Chart.inkExtent9483(runs: unplaced, marks: [], across: span, halfStroke: 1.5, markRadius: 2),
                     "a vertex with no place is never bridged")
        XCTAssertEqual(Chart.inkExtent9483(runs: [], marks: [CGPoint(x: 260, y: 30)], across: span,
                                           halfStroke: 1.5, markRadius: 2), 28...32)
        XCTAssertNil(Chart.inkExtent9483(runs: [], marks: [CGPoint(x: 287, y: 30)], across: span,
                                         halfStroke: 1.5, markRadius: 2))
    }

    /// The finished end's dot (Design N3) may only sit on a mark the line
    /// draws: the primary line's own last reading, never a value it lacks and
    /// never another source's point.
    func testTheEndDotSitsOnlyOnADrawnPrimaryMark() {
        let blend = series([0.62, 0.81, 0.97], source: "aggregate")
        let points = blend + series([0.6, 0.7], source: "consensus")
        let ink = Chart.primaryInk9483(dataPoints: points, checkpoints: nil, gameStart: nil)
        XCTAssertEqual(ink.runs.map { $0.map(\.probability) }, [[0.62, 0.81, 0.97]])
        let last = blend[2]
        XCTAssertTrue(ink.draws(date: last.date, probability: last.probability))
        XCTAssertFalse(ink.draws(date: last.date, probability: 1.0), "no terminal 100% the line never drew")
        XCTAssertFalse(ink.draws(date: points[3].date, probability: 0.6), "another source's point")
        let lone = Chart.primaryInk9483(dataPoints: [blend[0]], checkpoints: nil, gameStart: nil)
        XCTAssertEqual(lone.marks.map(\.probability), [0.62], "a lone reading is a drawn dot")
        XCTAssertTrue(lone.draws(date: blend[0].date, probability: 0.62))
    }

    // MARK: - A steep finish leaves the plate off and the key names the reading

    /// A gentle finish keeps its plate where it was placed: clear of the line,
    /// above a gentle climb and below a gentle fall, unmoved by the frame.
    func testAGentleFinishKeepsItsPlate() {
        let climb = [(100, 0.55), (200, 0.60), (290, 0.66)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnTopWindow(CGFloat($0.1))) }
        let up = Chart.endLabelCenter9483(end: climb[2], size: plate, lineYBeneath: yOnTopWindow(0.60),
                                          plot: platePlot, topReserve: 20, ink: ink([climb]))
        XCTAssertEqual(up.x, 259)
        XCTAssertEqual(up.y, climb[2].y - 2 - plate.height / 2, accuracy: 0.001, "its preferred spot, above the dot")
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: up, size: plate, ink: ink([climb])))
        let fall = [(100, 0.45), (200, 0.40), (290, 0.34)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnBottomWindow(CGFloat($0.1))) }
        let down = Chart.endLabelCenter9483(end: fall[2], size: plate, lineYBeneath: yOnBottomWindow(0.40),
                                            plot: platePlot, topReserve: 20, ink: ink([fall]))
        XCTAssertEqual(down.y, fall[2].y + 2 + plate.height / 2, accuracy: 0.001, "below the dot")
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: down, size: plate, ink: ink([fall])))
    }

    /// A climb or collapse the accepted bounded step DOES clear keeps its
    /// plate: the step lands it exactly on the ink's edge, which is clear.
    func testAFinishTheBoundedStepClearsKeepsItsPlate() {
        let climb = [(150, 0.80), (230, 0.92), (250, 0.96), (270, 0.99), (290, 1.0)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnTopWindow(CGFloat($0.1))) }
        let up = Chart.endLabelCenter9483(end: CGPoint(x: 290, y: 0), size: plate, lineYBeneath: yOnTopWindow(0.96),
                                          plot: platePlot, topReserve: 20, ink: ink([climb]))
        XCTAssertEqual(up.y, 34.42, accuracy: 0.001, "control: C2's step")
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: up, size: plate, ink: ink([climb])))
        let fall = [(150, 0.20), (230, 0.08), (250, 0.04), (270, 0.01), (290, 0.0)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnBottomWindow(CGFloat($0.1))) }
        let down = Chart.endLabelCenter9483(end: CGPoint(x: 290, y: 270), size: plate,
                                            lineYBeneath: yOnBottomWindow(0.04), plot: platePlot,
                                            topReserve: 20, ink: ink([fall]))
        XCTAssertEqual(down.y, 235.58, accuracy: 0.001, "control: C2's step")
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: down, size: plate, ink: ink([fall])))
    }

    /// The deciding case (Lane1b 2332Z, Design's STEEP-FINISH-LABEL-FALLBACK):
    /// .80 → .90 → .97 → 1.0 over the last 50pt needs a 35.5pt step against a
    /// 28pt bound, so the bounded placement stays on the climb — and the plate
    /// is left off rather than painted over it.
    func testASteepClimbTheBoundCannotClearLeavesThePlateOff() {
        let steep = [(200, 0.75), (240, 0.80), (257, 0.90), (274, 0.97), (290, 1.0)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnTopWindow(CGFloat($0.1))) }
        let placed = Chart.endLabelCenter9483(end: CGPoint(x: 290, y: 0), size: plate,
                                              lineYBeneath: yOnTopWindow(0.90), plot: platePlot,
                                              topReserve: 20, ink: ink([steep]))
        XCTAssertEqual(placed, CGPoint(x: 259, y: 27), "the accepted bounded placement, unchanged")
        XCTAssertTrue(plateCoversInk(placed, plate, ink([steep])), "control: painted there, it covers the climb")
        XCTAssertFalse(Chart.endLabelPlateClears9483(center: placed, size: plate, ink: ink([steep])),
                       "the plate is left off a climb it would cover")
    }

    /// Its mirror: a collapse to 0% too steep to step above.
    func testASymmetricCollapseLeavesThePlateOff() {
        let collapse = [(200, 0.25), (240, 0.20), (257, 0.10), (274, 0.03), (290, 0.0)]
            .map { CGPoint(x: CGFloat($0.0), y: yOnBottomWindow(CGFloat($0.1))) }
        let placed = Chart.endLabelCenter9483(end: CGPoint(x: 290, y: 270), size: plate,
                                              lineYBeneath: yOnBottomWindow(0.10), plot: platePlot,
                                              topReserve: 20, ink: ink([collapse]))
        XCTAssertEqual(placed, CGPoint(x: 259, y: 261), "the accepted bounded placement, unchanged")
        XCTAssertTrue(plateCoversInk(placed, plate, ink([collapse])), "control: the case bites")
        XCTAssertFalse(Chart.endLabelPlateClears9483(center: placed, size: plate, ink: ink([collapse])))
    }

    /// The decision reads the final rectangle wherever it landed: a plate the
    /// frame never moved is still left off the ink under it. Touching is clear;
    /// a break in the line has no ink to cover.
    func testThePlateDecisionReadsTheFinalRectangleMovedOrNot() {
        let size = CGSize(width: 40, height: 16)
        let unmoved = Chart.endLabelCenter9483(end: CGPoint(x: 250, y: 60), size: size, lineYBeneath: 120,
                                               plot: CGSize(width: 300, height: 200), topReserve: 20,
                                               ink: { _ in 52...70 })
        XCTAssertEqual(unmoved, CGPoint(x: 224, y: 50), "control: the placement does not move for this ink")
        XCTAssertFalse(Chart.endLabelPlateClears9483(center: unmoved, size: size, ink: { _ in 52...70 }))
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: unmoved, size: size, ink: { _ in 58...70 }),
                      "an edge that only touches the plate is clear")
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: unmoved, size: size, ink: { _ in 10...42 }))
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: unmoved, size: size, ink: noInk))
        let broken = [[CGPoint(x: 150, y: 50), CGPoint(x: 200, y: 50)], [CGPoint(x: 248, y: 50), CGPoint(x: 250, y: 60)]]
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: unmoved, size: size, ink: ink(broken)),
                      "nothing is drawn across the break, so nothing is covered")
        XCTAssertFalse(Chart.endLabelPlateClears9483(center: unmoved, size: size, ink: ink([broken.flatMap { $0 }])),
                       "control: joined, the same points do lay ink under the plate")
    }

    /// A plate the bounded step put on the ink's edge keeps it, even when
    /// `edge + h/2 − h/2` misses the edge by one ulp (Lane1b C1's specimen,
    /// through the real placement). The touch allowance stays sub-pixel: a
    /// third of a point of real overlap still drops the plate.
    func testAPlateSteppedOntoTheInksEdgeIsClearDespiteRounding() throws {
        let climb = [CGPoint(x: 169, y: 37.603193728308504), CGPoint(x: 203, y: 26.76989447121026),
                     CGPoint(x: 274, y: 19.885678711051654), CGPoint(x: 290, y: 0)]
        let placed = Chart.endLabelCenter9483(end: CGPoint(x: 290, y: 0), size: plate,
                                              lineYBeneath: 26.76989447121026, plot: platePlot,
                                              topReserve: 20, ink: ink([climb]))
        XCTAssertEqual(placed.x, 259)
        XCTAssertNotEqual(placed.y, 27, "control: the frame moved it and the step ran")
        let line = try XCTUnwrap(ink([climb])((placed.x - plate.width / 2)...(placed.x + plate.width / 2)))
        let overlap = line.upperBound - (placed.y - plate.height / 2)
        XCTAssertGreaterThan(overlap, 0, "control: the stepped plate's top misses the ink's edge by rounding")
        XCTAssertLessThan(overlap, Chart.endLabelPlateTouch9483)
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: placed, size: plate, ink: ink([climb])),
                      "a plate stepped onto the ink's edge is kept")
        // Both edges allow the same rounding (a collapse's `edge − h/2` is
        // exact for whole plate heights, so no placement reaches this arm)…
        let size = CGSize(width: 40, height: 16)
        let center = CGPoint(x: 224, y: 50)
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: center, size: size, ink: { _ in (58 - 0.005)...70 }))
        XCTAssertTrue(Chart.endLabelPlateClears9483(center: center, size: size, ink: { _ in 10...(42 + 0.005) }))
        // …and stay bounded: one @3x pixel of overlap is real cover, above and below.
        XCTAssertFalse(Chart.endLabelPlateClears9483(center: center, size: size, ink: { _ in (58 - 1.0 / 3)...70 }))
        XCTAssertFalse(Chart.endLabelPlateClears9483(center: center, size: size, ink: { _ in 10...(42 + 1.0 / 3) }))
    }

    /// What the primary key prints: the last DRAWN primary reading, named for
    /// whose chance it is, in the end label's words — never a value the line
    /// lacks, and the same whether Sources is open or not.
    func testTheKeyNamesTheLastDrawnReadingWhoseChanceItWas() throws {
        let climb = series([0.80, 0.90, 0.97], source: "aggregate")
        let points = climb + series([0.78, 0.88, 0.95], source: "consensus") + series([0.7, 0.9], source: "kalshi")
        let end = try XCTUnwrap(Chart.finishedEnd9483(dataPoints: points, checkpoints: nil, finished: true))
        XCTAssertEqual(end.date, climb[2].date)
        XCTAssertEqual(end.probability, 0.97, "the blend's last reading, not another source's")
        let ink = Chart.primaryInk9483(dataPoints: points, checkpoints: nil, gameStart: nil)
        XCTAssertEqual(Chart.endKeyReading9483(end, ink: ink, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "GB 97%")
        XCTAssertEqual(Chart.endKeyReading9483(end, ink: ink, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       Chart.endLabelText9483(probability: 0.97, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "the plate's own words and rounding")
        // Sources open draws more lines from the SAME points; the key's inputs
        // never include that state, and the blend alone gives the same reading.
        let blendOnly = Chart.finishedEnd9483(dataPoints: climb, checkpoints: nil, finished: true)
        XCTAssertEqual(blendOnly?.probability, end.probability)
        XCTAssertEqual(blendOnly?.date, end.date)

        let collapse = series([0.40, 0.12, 0.03], source: "aggregate")
        let low = try XCTUnwrap(Chart.finishedEnd9483(dataPoints: collapse, checkpoints: nil, finished: true))
        let lowInk = Chart.primaryInk9483(dataPoints: collapse, checkpoints: nil, gameStart: nil)
        XCTAssertEqual(Chart.endKeyReading9483(low, ink: lowInk, sides: .homeAndAway, homeShort: "GB", awayShort: "DAL"),
                       "DAL 97%", "a qualified two-outcome axis names the side the dot sits on")
        XCTAssertEqual(Chart.endKeyReading9483(low, ink: lowInk, sides: .homeOnly, homeShort: "GB", awayShort: "DAL"),
                       "GB 3%", "a home-only line never invents the away complement")

        XCTAssertNil(Chart.endKeyReading9483((date: climb[2].date, probability: 1.0), ink: ink, sides: .homeAndAway,
                                             homeShort: "GB", awayShort: "DAL"),
                     "no terminal 100% the line never drew")
        XCTAssertNil(Chart.finishedEnd9483(dataPoints: points, checkpoints: nil, finished: false),
                     "an unfinished line has no end reading")
        XCTAssertNil(Chart.finishedEnd9483(dataPoints: series([0.7, 0.9], source: "kalshi"), checkpoints: nil,
                                           finished: true),
                     "no primary line, no reading")
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

    /// Design R2: the held tennis dot rides the line its readings come from,
    /// so it wears that line's colour, never the home team's. Revealed lines
    /// and the gutter's named poles keep their own colours.
    func testTheHeldTennisDotWearsItsLinesColour() throws {
        let chart = try chartCode()
        XCTAssertTrue(chart.contains("TennisHeldReadingMarker9483(pin:tennisPin,selection:selection,series:tennis,"
                                     + "proxy:proxy,plotFrame:plotFrame,color:colorForSource(tennis.source,sources:sources),"
                                     + "awayColor:nil)"))
        XCTAssertFalse(chart.contains("color:teamColors?.home??.accentColor"), "the held dot takes the home colour again")
        XCTAssertTrue(chart.contains("case\"consensus\":baseColor=teamColors?.home??.blue"),
                      "control: a revealed sportsbook line keeps its own colour")
    }

    /// C3's wiring: the count and the lines/window both read the one
    /// eligibility, taken from the served groups; the fallback never does.
    func testSourcesEligibilityIsTheServedGroupsAtEveryDisclosureSite() throws {
        let chart = try chartCode()
        XCTAssertEqual(count("Self.revealableSources9483(in:dataPoints,withheld:withheldSources9483)", in: chart), 2,
                       "the key's count and the axis plan (its lines and window)")
        XCTAssertEqual(count("revealableSources9483(in", in: chart), 3,
                       "control: the definition and those two; no third, unfiltered caller")
        XCTAssertTrue(chart.contains("Self.withheldSources9483(served:vm.history?.winProbHistory)"),
                      "judged on the whole served group, not on the drawn window")
        XCTAssertTrue(chart.contains("staticfuncdefaultVisibleSources(inpoints:[ChartDataPoint])->[String]{"
                                     + "ifpoints.contains(where:{$0.source==\"aggregate\"}){return[\"aggregate\"]}"
                                     + "returnArray(Set(points.map(\\.source))).sorted()}"),
                      "the no-blend fallback is unchanged")
    }

    /// C2/N3's wiring: the label measures the primary line's drawn ink at its
    /// stroke, and the end dot is static, in the primary line's colour.
    func testTheEndLabelReadsThePrimaryInkAndTheEndDotIsStatic() throws {
        let chart = try chartCode()
        XCTAssertTrue(chart.contains("finishedEndLabel9483(finishedEnd,line:endLine,"
                                     + "ink:Self.primaryInk9483(dataPoints:dataPoints,checkpoints:checkpoints,gameStart:gameStartDate),"
                                     + "sides:axis.sides,proxy:proxy,plotFrame:plotFrame,"
                                     + "color:colorForSource(Self.primarySource(in:dataPoints),sources:sources),"
                                     + "halfStroke:strokeStyleForSource(Self.primarySource(in:dataPoints),sources:sources).lineWidth/2)"))
        let start = try XCTUnwrap(chart.range(of: "privatefuncfinishedEndLabel9483("))
        let end = try XCTUnwrap(chart.range(of: "staticfunclineY9483(", range: start.upperBound..<chart.endIndex))
        let label = String(chart[start.lowerBound..<end.lowerBound])
        XCTAssertTrue(label.contains("ifink.draws(date:end.date,probability:end.probability){Circle().fill(color)"),
                      "a dot only on a drawn mark")
        XCTAssertTrue(label.contains("ink:{spaninSelf.inkExtent9483(runs:runs,marks:marks,across:span,"
                                     + "halfStroke:halfStroke,markRadius:Self.inkMarkRadius9483)}"))
        for animated in ["animation", "withAnimation", "repeatForever", "phaseAnimator", "LiveChartEndpointFeedback"] {
            XCTAssertFalse(label.contains(animated), "the finished end animates: \(animated)")
        }
    }

    /// The steep-finish fallback's wiring: the plate is painted only behind
    /// the decision, the end dot never is, and every Sources state hands the
    /// primary key the one reading, taken before it branches.
    func testTheSteepFinishFallbackIsWiredAndTheKeyCarriesTheReading() throws {
        let chart = try chartCode()
        let start = try XCTUnwrap(chart.range(of: "privatefuncfinishedEndLabel9483("))
        let end = try XCTUnwrap(chart.range(of: "staticfunclineY9483(", range: start.upperBound..<chart.endIndex))
        let label = String(chart[start.lowerBound..<end.lowerBound])
        let decision = try XCTUnwrap(label.range(of:
            "ifSelf.endLabelPlateClears9483(center:center,size:size,ink:{spaninSelf.inkExtent9483(runs:runs,"
            + "marks:marks,across:span,halfStroke:halfStroke,markRadius:Self.inkMarkRadius9483)}){Text(text)"),
            "the plate is painted only where it clears the drawn primary ink")
        XCTAssertEqual(count("Text(text)", in: label), 1, "no second, ungated plate")
        let dot = try XCTUnwrap(label.range(of: "ifink.draws(date:end.date,probability:end.probability){Circle()"))
        XCTAssertLessThan(dot.lowerBound, decision.lowerBound, "the end dot stands outside the plate's decision")

        XCTAssertTrue(chart.contains("letfinishedEnd=liveSplit==nil?Self.finishedEnd9483(dataPoints:dataPoints,"
                                     + "checkpoints:checkpoints,finished:EventState.isFinished(status)):nil"),
                      "the plot's end and the key's are one function")
        XCTAssertTrue(chart.contains("letendReading=finishedEndKeyReading9483(dataPoints:dataPoints)ifhasBlend{"),
                      "the reading is taken once, before the Sources branch")
        XCTAssertEqual(count("legendKey(\"aggregate\",sources:sources,isPrimary:true,reading:endReading)", in: chart), 2,
                       "inline and full size, Sources open or closed")
        XCTAssertTrue(chart.contains("reading:source==Self.primarySource(in:dataPoints)?endReading:nil)"),
                      "without a blend, the primary line's key")
        let readStart = try XCTUnwrap(chart.range(of: "privatefuncfinishedEndKeyReading9483("))
        let readEnd = try XCTUnwrap(chart.range(of: "privatefuncendLabelInk9483(", range: readStart.upperBound..<chart.endIndex))
        let reader = String(chart[readStart.lowerBound..<readEnd.lowerBound])
        for state in ["sourcesOpen", "SourcesOpen", "plotFrame", "proxy", "revealed", "axisPlan9483"] {
            XCTAssertFalse(reader.contains(state), "the key reading moves with \(state)")
        }
        XCTAssertTrue(reader.contains("Self.endKeyReading9483(end,ink:Self.primaryInk9483(dataPoints:dataPoints,"
                                      + "checkpoints:checkpoints,gameStart:gameStartDate),"),
                      "the same drawn primary ink the end dot sits on")
    }
}
