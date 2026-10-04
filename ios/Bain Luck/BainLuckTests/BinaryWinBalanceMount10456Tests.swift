import XCTest
import SwiftUI
@testable import Bain_Luck

/// #10456 — the OddsChartView mount of the balance ink. **An admitted binary
/// game chart wears its teams' colors above and below 50%; every other chart
/// keeps today's line exactly.**
///
/// `BinaryWinChartBalanceInkTests` pins the presenter. These pin the mount's
/// three decisions:
///
/// 1. **Admission.** Only a known, two-way sport whose page serves BOTH sides
///    of the winner pair, with team colors, on a chart drawing one primary
///    line. A draw-priced sport, the fallback sport row, a missing away
///    price, missing colors or several venue lines all refuse.
/// 2. **The runs drawn are the runs the chart draws.** Verbatim and in order;
///    the one exclusion is the live edge's continued lone vertex, which the
///    plot never dots either.
/// 3. **Never hide a line the ink cannot place.** A domain the projector
///    cannot map yields no plan, so the primary marks stay.
@MainActor
final class BinaryWinBalanceMount10456Tests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_900_000_000)

    private func point(_ minutes: Double, _ p: Double, source: String = "aggregate") -> ChartDataPoint {
        ChartDataPoint(date: t0.addingTimeInterval(minutes * 60), probability: p, source: source)
    }

    private func admission(
        sport: String? = "americanfootball_nfl",
        home: Double? = 0.62, away: Double? = 0.38,
        colors: Bool = true,
        drawn: [String] = ["aggregate"], primary: String = "aggregate"
    ) -> BinaryWinBalanceAdmission {
        BinaryWinBalanceMount.admission(sportKey: sport, servedHome: home, servedAway: away,
                                        hasTeamColors: colors, drawnSources: drawn, primarySource: primary)
    }

    // MARK: 1. Admission

    func testATwoWaySportWithBothServedSidesOneLineAndColorsIsAdmitted() {
        XCTAssertEqual(admission(), .admittedBinary)
        XCTAssertEqual(admission(sport: "baseball_mlb"), .admittedBinary)
        XCTAssertEqual(admission(sport: "icehockey_nhl"), .admittedBinary)
        XCTAssertEqual(admission(drawn: ["consensus"], primary: "consensus"), .admittedBinary,
                       "the consensus line is the primary when there is no blend")
    }

    func testADrawPricedSportIsRefusedEvenWithBothSidesServed() {
        // #5271 — a soccer winner market has a third outcome; two colors
        // around 50% would claim the two sides are the whole question.
        XCTAssertEqual(admission(sport: "soccer_epl"), .refused)
        XCTAssertEqual(admission(sport: "soccer_usa_mls"), .refused)
    }

    func testASportTheVocabularyDoesNotKnowIsRefused() {
        // The fallback row holds cricket, rugby and AFL — draws are priced in
        // some of them, so "not marked draw-priced" is not evidence there.
        XCTAssertEqual(admission(sport: "cricket_test_match"), .refused)
        XCTAssertEqual(admission(sport: "rugbyleague_nrl"), .refused)
        XCTAssertEqual(admission(sport: nil), .refused)
        XCTAssertEqual(admission(sport: ""), .refused)
    }

    func testAMissingServedSideIsRefusedNeverCompleted() {
        XCTAssertEqual(admission(away: nil), .refused, "never 1 − home")
        XCTAssertEqual(admission(home: nil), .refused)
    }

    func testNoTeamColorsIsRefused() {
        XCTAssertEqual(admission(colors: false), .refused)
    }

    func testSeveralDrawnLinesOrADrawnLineThatIsNotPrimaryIsRefused() {
        XCTAssertEqual(admission(drawn: ["espn", "kalshi"], primary: "consensus"), .refused)
        XCTAssertEqual(admission(drawn: ["kalshi"], primary: "consensus"), .refused)
        XCTAssertEqual(admission(drawn: [], primary: "aggregate"), .refused)
    }

    // MARK: 2. The runs drawn are the runs the chart draws

    func testRunsAreCopiedVerbatimAndInOrderIncludingALoneObservation() {
        let segments = [[point(0, 0.55), point(1, 0.45)], [point(5, 0.7)], [point(9, 0.4), point(10, 0.6)]]
        let runs = BinaryWinBalanceMount.displayedRuns(segments: segments, continuedRun: nil)
        XCTAssertEqual(runs.count, 3)
        XCTAssertEqual(runs[1], [BinaryWinPathVertex(date: t0.addingTimeInterval(300), probability: 0.7)],
                       "a lone observation is drawn by the plot as a dot, so it stays")
        XCTAssertEqual(runs.flatMap { $0 }.map(\.probability), [0.55, 0.45, 0.7, 0.4, 0.6])
    }

    func testTheLiveEdgesContinuedLoneVertexIsNotDotted() {
        let segments = [[point(0, 0.55), point(1, 0.45)], [point(5, 0.7)]]
        let runs = BinaryWinBalanceMount.displayedRuns(segments: segments, continuedRun: 1)
        XCTAssertEqual(runs.count, 1, "the overlay's tail starts from that vertex; the plot draws no dot there")
        // A continued run that still holds a line is drawn as a line.
        let longer = [[point(0, 0.55), point(1, 0.45)], [point(5, 0.7), point(6, 0.6)]]
        XCTAssertEqual(BinaryWinBalanceMount.displayedRuns(segments: longer, continuedRun: 1).count, 2)
    }

    // MARK: 3. Never hide a line the ink cannot place

    func testAPlaceablePlanIsReturnedOnTheChartsDomain() {
        let runs = BinaryWinBalanceMount.displayedRuns(
            segments: [[point(0, 0.55), point(1, 0.45)]], continuedRun: nil)
        let plan = BinaryWinBalanceMount.plan(
            admission: .admittedBinary, runs: runs, servedHome: 0.62, servedAway: 0.38,
            gameFinished: false, xDomain: t0...t0.addingTimeInterval(600))
        XCTAssertEqual(plan?.segments, runs)
        XCTAssertEqual(plan?.home, 0.62)
        XCTAssertEqual(plan?.away, 0.38)
    }

    func testAZeroWidthDomainYieldsNoPlanSoThePrimaryLineStays() {
        let runs = BinaryWinBalanceMount.displayedRuns(segments: [[point(0, 0.55)]], continuedRun: nil)
        XCTAssertNil(BinaryWinBalanceMount.plan(
            admission: .admittedBinary, runs: runs, servedHome: 0.62, servedAway: 0.38,
            gameFinished: false, xDomain: t0...t0))
    }

    func testARefusedAdmissionOrNoRunsYieldsNoPlan() {
        let runs = BinaryWinBalanceMount.displayedRuns(
            segments: [[point(0, 0.55), point(1, 0.45)]], continuedRun: nil)
        let domain = t0...t0.addingTimeInterval(600)
        XCTAssertNil(BinaryWinBalanceMount.plan(admission: .refused, runs: runs, servedHome: 0.62,
                                                servedAway: 0.38, gameFinished: false, xDomain: domain))
        XCTAssertNil(BinaryWinBalanceMount.plan(admission: .admittedBinary, runs: [], servedHome: 0.62,
                                                servedAway: 0.38, gameFinished: false, xDomain: domain))
    }

    func testSideColorFollowsTheInksOwnTipRule() {
        XCTAssertEqual(BinaryWinBalanceMount.sideColor(probability: 0.5, home: .blue, away: .red), .blue,
                       "50% is the home side, as the ink's singleton rule says")
        XCTAssertEqual(BinaryWinBalanceMount.sideColor(probability: 0.49, home: .blue, away: .red), .red)
    }
}
