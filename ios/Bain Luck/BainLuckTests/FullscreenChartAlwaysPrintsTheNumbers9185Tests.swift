import XCTest
import SwiftUI
@testable import Bain_Luck

/// #9185 — the fullscreen win-probability chart always prints both teams'
/// chances.
///
/// WHAT THE READER SAW: Patriots at Jaguars (`14782706`), live, Sep 27 2026.
/// Alex watched NE move 42% → 39% and opened the chart fullscreen: no
/// probability numbers anywhere. The cover hides the page hero, and its only
/// number was the page's readout card — which the page hands over only once
/// the game has a scoring play (the first quarter was 0–0), and which prints a
/// scoring play's description IN PLACE of the numbers whenever it rests on one.
///
/// Simulator frames of the same page are in `artifacts/native-9185/`. These
/// tests pin the two decisions; the frames are what show them drawn.
final class FullscreenChartAlwaysPrintsTheNumbers9185Tests: XCTestCase {

    private func point(scoringPlay: ScoringPlay? = nil) -> GamePlayPoint {
        GamePlayPoint(
            timestamp: "2026-09-27T17:30:00Z",
            homeProb: 0.61,
            awayProb: 0.39,
            homeScore: 0,
            awayScore: 0,
            period: "1",
            clock: "4:12",
            scoringPlay: scoringPlay
        )
    }

    private let touchdown: ScoringPlay = {
        let json = #"{"description":"Travis Etienne 12 yd run","type":"Touchdown"}"#
        return try! JSONDecoder().decode(ScoringPlay.self, from: Data(json.utf8))
    }()

    // MARK: - The readout exists whether or not the page gave one

    func testAZeroZeroGameStillGetsAFullscreenReadout() {
        // The page passes nil until a scoring play exists.
        let card = OddsChartView.fullscreenReadout(
            page: nil, homeTeam: "Jacksonville Jaguars", awayTeam: "New England Patriots",
            colors: nil, homeLogo: nil, awayLogo: nil)
        XCTAssertNotNil(card, "a 0–0 live game opened fullscreen must still print its numbers")
        XCTAssertEqual(card?.pinsProbabilities, true)
        XCTAssertEqual(card?.homeTeam, "Jacksonville Jaguars")
        XCTAssertEqual(card?.awayTeam, "New England Patriots")
    }

    func testThePagesOwnCardIsUsedAndPinned() {
        let page = GamePlayCardView(homeTeam: "Jaguars", awayTeam: "Patriots",
                                    homeTeamLogo: "page-logo", lastPoint: point())
        XCTAssertFalse(page.pinsProbabilities, "the inline card keeps #925's layout")
        let card = OddsChartView.fullscreenReadout(
            page: page, homeTeam: "Jacksonville Jaguars", awayTeam: "New England Patriots",
            colors: nil, homeLogo: "chart-logo", awayLogo: nil)
        XCTAssertEqual(card?.pinsProbabilities, true)
        XCTAssertEqual(card?.homeTeamLogo, "page-logo")
    }

    func testNoNamesNoCard() {
        // Nothing to name the numbers with; the chart's gutters say the same.
        XCTAssertNil(OddsChartView.fullscreenReadout(
            page: nil, homeTeam: nil, awayTeam: "Patriots",
            colors: nil, homeLogo: nil, awayLogo: nil))
    }

    func testTheFallbackCardRestsOnTheChartsLastPoint() {
        let card = OddsChartView.fullscreenReadout(
            page: nil, homeTeam: "Jaguars", awayTeam: "Patriots",
            colors: nil, homeLogo: nil, awayLogo: nil)?.resting(on: point())
        XCTAssertEqual(card?.lastPoint?.homeProb, 0.61)
    }

    // MARK: - A pinned card prints the numbers on a scoring play too

    func testAScoringPlayNoLongerHidesTheNumbersWhenPinned() {
        let rows = GamePlayCardView.rows(for: point(scoringPlay: touchdown), pinsProbabilities: true)
        XCTAssertTrue(rows.probabilities, "fullscreen resting on a touchdown must still print both chances")
        XCTAssertTrue(rows.play, "and the play itself")
    }

    func testBetweenPlaysAPinnedCardPrintsOnlyTheNumbers() {
        let rows = GamePlayCardView.rows(for: point(), pinsProbabilities: true)
        XCTAssertTrue(rows.probabilities)
        XCTAssertFalse(rows.play)
    }

    /// The inline card is unchanged: #925's play-in-place-of-numbers layout,
    /// because the page hero above it already prints the numbers.
    func testTheInlineCardKeepsItsLayout() {
        let onPlay = GamePlayCardView.rows(for: point(scoringPlay: touchdown), pinsProbabilities: false)
        XCTAssertFalse(onPlay.probabilities)
        XCTAssertTrue(onPlay.play)
        let between = GamePlayCardView.rows(for: point(), pinsProbabilities: false)
        XCTAssertTrue(between.probabilities)
        XCTAssertFalse(between.play)
    }

    // MARK: - A lone venue line is the line the chart ends on

    private func pt(_ t: String, _ p: Double, _ source: String) -> ChartDataPoint {
        ChartDataPoint(date: t.asDate!, probability: p, source: source)
    }

    /// DPR Korea v Spain (15318006): one Polymarket line, no blend, no
    /// consensus — the fullscreen readout printed nothing.
    func testALonePolymarketLineGivesTheReadoutItsLastPoint() {
        let points = [
            pt("2026-09-27T16:00:00Z", 0.30, "polymarket"),
            pt("2026-09-27T18:50:00Z", 0.02, "polymarket"),
            pt("2026-09-27T17:00:00Z", 0.25, "polymarket"),
        ]
        XCTAssertNil(OddsChartView.latestPrimaryPoint(in: points), "the specimen has no primary line")
        XCTAssertEqual(OddsChartView.fullscreenRestingPoint(in: points, sportKey: nil, pageGaveCard: false)?.homeProb, 0.02)
        // #8652 stands: with the PAGE's card, no primary line keeps the page's point.
        XCTAssertNil(OddsChartView.fullscreenRestingPoint(in: points, sportKey: nil, pageGaveCard: true))
        XCTAssertNil(OddsChartView.restingPlayPoint(in: points, sportKey: nil))
    }

    /// Two unblended venues: no one number to print, so none is picked.
    func testTwoUnblendedVenuesStillRestOnNothing() {
        let points = [
            pt("2026-09-27T16:00:00Z", 0.30, "polymarket"),
            pt("2026-09-27T16:00:00Z", 0.35, "kalshi"),
        ]
        XCTAssertNil(OddsChartView.fullscreenRestingPoint(in: points, sportKey: nil, pageGaveCard: false))
    }

    /// A blend present is the blend, as before (#8652).
    func testTheBlendStillWinsWhenPresent() {
        let points = [
            pt("2026-09-27T16:00:00Z", 0.60, "aggregate"),
            pt("2026-09-27T16:05:00Z", 0.90, "polymarket"),
        ]
        XCTAssertEqual(OddsChartView.fullscreenRestingPoint(in: points, sportKey: nil, pageGaveCard: false)?.homeProb, 0.60)
    }

    // MARK: - The rig can open it

    func testTheFullscreenLaunchFlagIsOffUnlessAsked() {
        let defaults = UserDefaults(suiteName: "9185-\(UUID().uuidString)")!
        XCTAssertFalse(LaunchRig.opensChartFullscreen(defaults: defaults))
        defaults.set(true, forKey: LaunchRig.chartFullscreenKey)
        XCTAssertTrue(LaunchRig.opensChartFullscreen(defaults: defaults))
        XCTAssertEqual(LaunchRig.chartFullscreenKey, "launch_chart_fullscreen")
    }
}
