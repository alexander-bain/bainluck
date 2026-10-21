import XCTest
@testable import Bain_Luck

/// #9483 / #11356 — **a fan reads the correct team's chance at each visible
/// edge of a focused native chart, and the window follows the web chart's
/// selected rules.**
///
/// `ChartProbabilityAxis9483` is a transfer of the web helpers
/// `computeWinProbYAxis`, `teamAxisTick` and `teamAxisEdges`
/// (`frontend/lib/eventKeyStats.ts`, blob 751b4021 at 89f9ba03a2). Every
/// expected window below was produced by executing that frozen web source on
/// the same inputs, scaled ×100 at the boundary exactly as the native helper
/// scales them. These pin four things:
///
/// 1. **Units.** Readings, domain and ticks are fractions (0...1); 0.75 is a
///    75% chance. Ticks land exactly on whole-percent fractions.
/// 2. **Meaning.** On a qualified two-outcome market a coordinate below 50%
///    names the away side's chance, a cropped edge prints its own number, and
///    only a true end of the scale is a pole. A home-only line never names an
///    away side — not at a tick, not at an edge (Design's AXIS-MEANING-CASES).
/// 3. **The real recorded window.** Jaguars–Eagles 14639175, the retained
///    Oct 11 14:35–15:05Z window: 31 primary readings ending 0.515873 at 15:05Z.
///    Revealing the five source series widens 0.45...0.75 → 0.30...0.80, and
///    hiding them restores 0.45...0.75, without editing a reading. The arrays
///    are the original `home_probability` values in their retained order, from
///    REAL-CHART-CASES.json (sha256 9b64d888…) and the raw history file it binds
///    (sha256 a5d027c0…); sportsbook rows are the raw history inside the window.
///    This is not the separate 63-point whole-payload control.
/// 4. **Each rule's boundary** (few readings, minimum span, 0/100 clamp, spike
///    vs extremes, a line's end, 50% never welded to the frame, non-finite
///    readings). These are rule inputs, not game histories.
///
/// The caller still owns admission, source choice, freshness, gaps and
/// whether a market is two-sided; nothing here decides those.
@MainActor
final class ChartProbabilityAxisNamesEachEdge9483Tests: XCTestCase {

    private typealias Axis = ChartProbabilityAxis9483

    private func window(_ lower: Int, _ upper: Int, _ ticks: [Int]) -> Axis.Window {
        Axis.Window(lowerPercent: lower, upperPercent: upper, tickPercents: ticks)
    }

    // MARK: - 1. Units

    func testDomainAndTicksAreFractionsOfWholePercents() {
        let w = window(45, 75, [45, 50, 55, 60, 65, 70, 75])
        XCTAssertEqual(w.domain, 0.45...0.75)
        XCTAssertEqual(w.ticks, [0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75])
        XCTAssertEqual(Axis.full.domain, 0...1)
        XCTAssertEqual(Axis.full.ticks, [0, 0.25, 0.5, 0.75, 1])
    }

    func testAFractionIsReadAsAPercentNotAsAPercentOfAPercent() {
        XCTAssertEqual(Axis.tick(0.75, sides: .homeAndAway), Axis.Tick(text: "75%", side: .home))
        XCTAssertEqual(Axis.tick(0.55, sides: .homeOnly), Axis.Tick(text: "55%", side: .home))
        XCTAssertEqual(Axis.tick(0.45, sides: .homeAndAway), Axis.Tick(text: "55%", side: .away))
    }

    // MARK: - 2. Meaning (Design's selected axis examples)

    func testTicksOnATwoOutcomeMarketNameTheSideTheySitOn() {
        XCTAssertEqual(Axis.tick(0.25, sides: .homeAndAway), Axis.Tick(text: "75%", side: .away))
        XCTAssertEqual(Axis.tick(0.50, sides: .homeAndAway), Axis.Tick(text: "50%", side: .even))
        XCTAssertEqual(Axis.tick(0.75, sides: .homeAndAway), Axis.Tick(text: "75%", side: .home))
        XCTAssertEqual(Axis.tick(0.0, sides: .homeAndAway), Axis.Tick(text: "100%", side: .away))
        XCTAssertEqual(Axis.tick(1.0, sides: .homeAndAway), Axis.Tick(text: "100%", side: .home))
    }

    func testTicksOnAHomeOnlyLineAlwaysPrintTheHomeChance() {
        XCTAssertEqual(Axis.tick(0.25, sides: .homeOnly), Axis.Tick(text: "25%", side: .home))
        XCTAssertEqual(Axis.tick(0.50, sides: .homeOnly), Axis.Tick(text: "50%", side: .home))
        XCTAssertEqual(Axis.tick(0.75, sides: .homeOnly), Axis.Tick(text: "75%", side: .home))
        XCTAssertEqual(Axis.tick(0.0, sides: .homeOnly), Axis.Tick(text: "0%", side: .home))
        XCTAssertEqual(Axis.tick(1.0, sides: .homeOnly), Axis.Tick(text: "100%", side: .home))
    }

    func testACropAcrossEvenNamesBothSidesWithItsOwnNumbersAndNoPole() {
        let edges = Axis.edges(of: window(45, 75, [45, 50, 55, 60, 65, 70, 75]), sides: .homeAndAway)
        XCTAssertEqual(edges.bottom, Axis.Edge(side: .away, percent: 55, isPole: false))
        XCTAssertEqual(edges.top, Axis.Edge(side: .home, percent: 75, isPole: false))
    }

    func testACropEntirelyOnTheHomeSideNeverAcquiresAnAwayEdge() {
        let crop = window(60, 80, [60, 65, 70, 75, 80])
        for sides in [Axis.Sides.homeAndAway, .homeOnly] {
            let edges = Axis.edges(of: crop, sides: sides)
            XCTAssertEqual(edges.bottom, Axis.Edge(side: .home, percent: 60, isPole: false), "\(sides)")
            XCTAssertEqual(edges.top, Axis.Edge(side: .home, percent: 80, isPole: false), "\(sides)")
        }
    }

    func testOnlyTheTrueEndsOfATwoOutcomeScaleArePoles() {
        let edges = Axis.edges(of: Axis.full, sides: .homeAndAway)
        XCTAssertEqual(edges.bottom, Axis.Edge(side: .away, percent: 100, isPole: true))
        XCTAssertEqual(edges.top, Axis.Edge(side: .home, percent: 100, isPole: true))
    }

    func testTheBottomOfAHomeOnlyScaleIsTheHomeSideAtZeroNotAnAwayWin() {
        let edges = Axis.edges(of: Axis.full, sides: .homeOnly)
        XCTAssertEqual(edges.bottom, Axis.Edge(side: .home, percent: 0, isPole: false))
        XCTAssertEqual(edges.top, Axis.Edge(side: .home, percent: 100, isPole: true))
    }

    func testAHomeOnlyWindowFromZeroKeepsItsHomeReadingWhenItWidens() {
        // The shape of the draw-priced home-only case (0–60 → 0–75 → 0–60):
        // label cases only; no away pole and no 1 − home appear at either width.
        for top in [60, 75] {
            let edges = Axis.edges(of: window(0, top, Array(stride(from: 0, through: top, by: top == 60 ? 10 : 25))),
                                   sides: .homeOnly)
            XCTAssertEqual(edges.bottom, Axis.Edge(side: .home, percent: 0, isPole: false))
            XCTAssertEqual(edges.top, Axis.Edge(side: .home, percent: top, isPole: false))
        }
    }

    func testAnEdgeOnEvenIsSpokenAsFiftyFifty() {
        let below = Axis.edges(of: window(20, 50, [20, 25, 30, 35, 40, 45, 50]), sides: .homeAndAway)
        XCTAssertEqual(below.top, Axis.Edge(side: .even, percent: 50, isPole: false))
        XCTAssertEqual(below.bottom, Axis.Edge(side: .away, percent: 80, isPole: false))
        let above = Axis.edges(of: window(50, 70, [50, 55, 60, 65, 70]), sides: .homeAndAway)
        XCTAssertEqual(above.bottom, Axis.Edge(side: .even, percent: 50, isPole: false))
        XCTAssertEqual(above.top, Axis.Edge(side: .home, percent: 70, isPole: false))
        // A home-only line has no even side: 50 is the home side at 50%.
        XCTAssertEqual(Axis.edges(of: window(50, 70, [50, 55, 60, 65, 70]), sides: .homeOnly).bottom,
                       Axis.Edge(side: .home, percent: 50, isPole: false))
    }

    func testTheSpokenEdgeSaysViewForACropAndAxisForAPole() {
        let crop = Axis.edges(of: window(45, 75, [45, 50, 55, 60, 65, 70, 75]), sides: .homeAndAway)
        XCTAssertEqual(Axis.edgeSentence(.top, crop.top, homeName: "JAX", awayName: "PHI"),
                       "the top of this view is JAX at 75%.")
        XCTAssertEqual(Axis.edgeSentence(.bottom, crop.bottom, homeName: "JAX", awayName: "PHI"),
                       "the bottom of this view is PHI at 55%.")
        let full = Axis.edges(of: Axis.full, sides: .homeAndAway)
        XCTAssertEqual(Axis.edgeSentence(.bottom, full.bottom, homeName: "JAX", awayName: "PHI"),
                       "the bottom of this axis is PHI at 100%.")
        let even = Axis.edges(of: window(50, 70, [50, 55, 60, 65, 70]), sides: .homeAndAway)
        XCTAssertEqual(Axis.edgeSentence(.bottom, even.bottom, homeName: "JAX", awayName: "PHI"),
                       "the bottom of this view is 50/50.")
        let homeOnly = Axis.edges(of: Axis.full, sides: .homeOnly)
        XCTAssertEqual(Axis.edgeSentence(.bottom, homeOnly.bottom, homeName: "VFB", awayName: "ATM"),
                       "the bottom of this view is VFB at 0%.")
    }

    // MARK: - 3. The real recorded window (Jaguars–Eagles 14639175)

    /// Bain Luck blend, 14:35–15:05Z, 31 readings, retained order.
    private let jaxMain: [Double] = [
        0.717791, 0.6979, 0.668393, 0.658436, 0.658225, 0.66001, 0.664191, 0.678234, 0.513586,
        0.489777, 0.491252, 0.491173, 0.491699, 0.492127, 0.502546, 0.512279, 0.538764, 0.539359,
        0.542035, 0.546801, 0.528168, 0.507077, 0.545058, 0.542734, 0.538679, 0.558333, 0.545699,
        0.546621, 0.541488, 0.528012, 0.515873
    ]

    /// The five source series inside the same window, as the web case revealed them.
    private let jaxSources: [String: [Double]] = [
        "sportsbooks_consensus": [
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

    /// Sources closed: the primary's readings, its end on the plot.
    private func closedWindow() -> Axis.Window {
        Axis.window(readings: jaxMain, mustShow: [jaxMain[jaxMain.count - 1]])
    }

    /// Sources open: every drawn line's readings; each line's end and each
    /// revealed source's low and high stay on the plot (the web call site's list).
    private func openWindow() -> Axis.Window {
        let order = ["sportsbooks_consensus", "kalshi", "polymarket", "espn", "stat_model"]
        let sources = order.compactMap { jaxSources[$0] }
        let readings = jaxMain + sources.flatMap { $0 }
        let mustShow = [jaxMain[jaxMain.count - 1]]
            + sources.flatMap { [$0[$0.count - 1], $0.min()!, $0.max()!] }
        return Axis.window(readings: readings, mustShow: mustShow)
    }

    func testTheRecordedInputIsTheRetainedWindow() {
        XCTAssertEqual(jaxMain.count, 31)
        XCTAssertEqual(jaxMain.last, 0.515873)
        XCTAssertEqual(jaxSources.mapValues(\.count),
                       ["sportsbooks_consensus": 31, "kalshi": 43, "polymarket": 44, "espn": 23, "stat_model": 27])
    }

    func testRevealingSourcesWidensAndHidingThemRestoresTheFocusedWindow() {
        let closed = closedWindow()
        XCTAssertEqual(closed, window(45, 75, [45, 50, 55, 60, 65, 70, 75]))
        XCTAssertEqual(closed.domain, 0.45...0.75)

        let open = openWindow()
        XCTAssertEqual(open, window(30, 80, [30, 40, 50, 60, 70, 80]))
        XCTAssertEqual(open.domain, 0.30...0.80)

        XCTAssertEqual(closedWindow(), closed, "closing Sources restores the same focused window")
    }

    func testTheRecordedLineAndItsEndStayInsideBothWindows() {
        for w in [closedWindow(), openWindow()] {
            XCTAssertTrue(jaxMain.allSatisfy { w.domain.contains($0) }, "\(w)")
            XCTAssertTrue(w.domain.contains(0.5), "the line crosses 50%, so 50% is on the plot")
            XCTAssertTrue(w.tickPercents.contains(50))
        }
        let open = openWindow()
        for (name, series) in jaxSources {
            XCTAssertTrue(series.allSatisfy { open.domain.contains($0) }, name)
        }
    }

    func testTheRecordedWindowsEdgesNameTheirOwnSides() {
        let closed = Axis.edges(of: closedWindow(), sides: .homeAndAway)
        XCTAssertEqual(closed.top, Axis.Edge(side: .home, percent: 75, isPole: false))
        XCTAssertEqual(closed.bottom, Axis.Edge(side: .away, percent: 55, isPole: false))
        let open = Axis.edges(of: openWindow(), sides: .homeAndAway)
        XCTAssertEqual(open.top, Axis.Edge(side: .home, percent: 80, isPole: false))
        XCTAssertEqual(open.bottom, Axis.Edge(side: .away, percent: 70, isPole: false))
        // Were the caller to hold the same readings as home-only, nothing names an away side.
        let homeOnly = openWindow().tickPercents.map { Axis.tick(percent: $0, sides: .homeOnly) }
        XCTAssertTrue(homeOnly.allSatisfy { $0.side == .home })
        XCTAssertEqual(homeOnly.map(\.text), ["30%", "40%", "50%", "60%", "70%", "80%"])
    }

    // MARK: - 4. Each rule's boundary (expected values from the frozen web helper)

    private func ramp(_ a: Double, _ b: Double, _ n: Int) -> [Double] {
        (0..<n).map { a + (b - a) * Double($0) / Double(n - 1) }
    }

    func testTooFewReadingsKeepTheFullAxisAndDrawNothing() {
        XCTAssertEqual(Axis.window(readings: []), Axis.full)
        XCTAssertEqual(Axis.window(readings: [0.55, 0.6, 0.62]), Axis.full)
        XCTAssertEqual(Axis.window(readings: Array(repeating: 0.6, count: 11)), Axis.full)
    }

    func testAWobbleAtEvenIsNotMagnifiedPastTheMinimumSpan() {
        let flat = Array(repeating: 0.5, count: 6) + Array(repeating: 0.51, count: 6)
        XCTAssertEqual(Axis.window(readings: flat), window(40, 65, [40, 45, 50, 55, 60, 65]))
    }

    func testTheClampAtZeroAndOneHundredGivesTheSpanBackAtTheOtherEnd() {
        XCTAssertEqual(Axis.window(readings: ramp(0.02, 0.04, 12)), window(0, 20, [0, 5, 10, 15, 20]))
        XCTAssertEqual(Axis.window(readings: ramp(0.96, 0.98, 12)), window(80, 100, [80, 85, 90, 95, 100]))
    }

    func testALineThatUsesTheRangeKeepsTheOldAxis() {
        XCTAssertEqual(Axis.window(readings: ramp(0.1, 0.9, 20)), Axis.full)
    }

    func testAHomeSideLineThatNeverReachesEvenSpendsNoAxisOnIt() {
        let w = Axis.window(readings: ramp(0.62, 0.78, 20))
        XCTAssertEqual(w, window(60, 80, [60, 65, 70, 75, 80]))
        XCTAssertFalse(w.domain.contains(0.5))
    }

    func testAnEarlySpikeDoesNotSetTheScale() {
        let readings = [0.21, 0.92] + Array(repeating: 0.4, count: 98)
        XCTAssertEqual(Axis.window(readings: readings), window(35, 55, [35, 40, 45, 50, 55]))
    }

    func testALinesEndIsAlwaysOnThePlot() {
        let readings = ramp(0.34, 0.45, 40) + [1.0]
        XCTAssertEqual(Axis.window(readings: readings, mustShow: [1.0]), window(25, 100, [25, 50, 75, 100]))
    }

    func testEvenIsNeverWeldedToTheFrame() {
        XCTAssertEqual(Axis.window(readings: ramp(0.36, 0.5, 20)), window(30, 55, [30, 35, 40, 45, 50, 55]))
        XCTAssertEqual(Axis.window(readings: ramp(0.5, 0.64, 20)), window(45, 70, [45, 50, 55, 60, 65, 70]))
    }

    func testNonFiniteReadingsAreSkippedNotReadAsZero() {
        let readings = ramp(0.6, 0.7, 12) + [.nan, .infinity]
        XCTAssertEqual(Axis.window(readings: readings, mustShow: [.nan]), window(55, 75, [55, 60, 65, 70, 75]))
        // Eleven finite readings plus junk is still too few.
        XCTAssertEqual(Axis.window(readings: Array(repeating: 0.6, count: 11) + [.nan, -Double.infinity]), Axis.full)
    }

    func testTheWindowDoesNotDependOnHowTheCallerQualifiedTheSides() {
        // The window is sized from readings alone; sides only change what labels say.
        let w = closedWindow()
        XCTAssertEqual(Axis.edges(of: w, sides: .homeOnly).top, Axis.edges(of: w, sides: .homeAndAway).top)
        XCTAssertNotEqual(Axis.edges(of: w, sides: .homeOnly).bottom, Axis.edges(of: w, sides: .homeAndAway).bottom)
    }
}
