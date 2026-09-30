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

    // MARK: - Scrubbing reads the line the card rests on

    private var lonePolymarket: [ChartDataPoint] {
        [
            pt("2026-09-27T16:00:00Z", 0.30, "polymarket"),
            pt("2026-09-27T17:00:00Z", 0.25, "polymarket"),
            pt("2026-09-27T18:50:00Z", 0.02, "polymarket"),
        ]
    }

    /// 15318006 again: the card rested on the lone line, but a scrub looked up
    /// only the primary one, so the crosshair moved and the number stayed 2%.
    func testScrubbingALoneLineSelectsItsOldPointAndReleaseReturnsToTheLatest() {
        let selection = OddsChartSelection()
        selection.select("2026-09-27T16:05:00Z".asDate)
        XCTAssertEqual(OddsChartSelectionReadout.selectedPoint(
            at: selection.date, in: lonePolymarket, sportKey: nil, pageGaveCard: false)?.homeProb, 0.30)
        selection.end()
        XCTAssertNil(OddsChartSelectionReadout.selectedPoint(
            at: selection.date, in: lonePolymarket, sportKey: nil, pageGaveCard: false))
        XCTAssertEqual(OddsChartView.fullscreenRestingPoint(
            in: lonePolymarket, sportKey: nil, pageGaveCard: false)?.homeProb, 0.02)
    }

    /// The page's card (and the inline chart) keep #8652: no primary line, no
    /// lone-line pick — for the scrub exactly as for the rest.
    func testWithThePagesCardALoneLineIsNeitherRestedOnNorScrubbed() {
        let date = "2026-09-27T16:05:00Z".asDate
        XCTAssertNil(OddsChartView.readoutSource(in: lonePolymarket, pageGaveCard: true))
        XCTAssertNil(OddsChartSelectionReadout.selectedPoint(
            at: date, in: lonePolymarket, sportKey: nil, pageGaveCard: true))
    }

    func testTwoUnblendedVenuesAreNotScrubbedEither() {
        let points = [
            pt("2026-09-27T16:00:00Z", 0.30, "polymarket"),
            pt("2026-09-27T16:00:00Z", 0.35, "kalshi"),
        ]
        XCTAssertNil(OddsChartView.readoutSource(in: points, pageGaveCard: false))
        XCTAssertNil(OddsChartSelectionReadout.selectedPoint(
            at: "2026-09-27T16:00:00Z".asDate, in: points, sportKey: nil, pageGaveCard: false))
    }

    /// With a blend drawn, a scrub reads the blend, never the venue printed
    /// nearer the finger — for either card.
    func testWithABlendTheScrubReadsTheBlend() {
        let points = [
            pt("2026-09-27T16:00:00Z", 0.60, "aggregate"),
            pt("2026-09-27T16:05:00Z", 0.90, "polymarket"),
        ]
        for pageGaveCard in [true, false] {
            XCTAssertEqual(OddsChartView.readoutSource(in: points, pageGaveCard: pageGaveCard), "aggregate")
            XCTAssertEqual(OddsChartSelectionReadout.selectedPoint(
                at: "2026-09-27T16:05:00Z".asDate, in: points, sportKey: nil,
                pageGaveCard: pageGaveCard)?.homeProb, 0.60)
        }
    }

    // MARK: - VoiceOver speaks the line the card prints

    /// 15318006: the fullscreen card printed the lone Polymarket line, while
    /// the chart's VoiceOver value looked up only the primary series and said
    /// "No probability data".
    func testVoiceOverSpeaksTheLoneLineTheFullscreenCardPrints() {
        let resting = OddsChartView.accessibilityValue(
            dataPoints: lonePolymarket, selectedDate: nil,
            homeShort: "Spain", awayShort: "DPR Korea", pageGaveCard: false)
        XCTAssertEqual(resting, "Spain 2%, DPR Korea 98%")
        let scrubbed = OddsChartView.accessibilityValue(
            dataPoints: lonePolymarket, selectedDate: "2026-09-27T16:05:00Z".asDate,
            homeShort: "Spain", awayShort: "DPR Korea", pageGaveCard: false)
        XCTAssertEqual(scrubbed, "Spain 30%, DPR Korea 70%")
    }

    /// The inline chart and the page's card keep the old value: no primary
    /// line, nothing spoken — the same rule as the card (#8652).
    func testWithThePagesCardVoiceOverStillSpeaksNoLoneLine() {
        XCTAssertEqual(OddsChartView.accessibilityValue(
            dataPoints: lonePolymarket, selectedDate: nil,
            homeShort: "Spain", awayShort: "DPR Korea"), "No probability data")
        XCTAssertEqual(OddsChartView.accessibilityValue(
            dataPoints: lonePolymarket, selectedDate: nil,
            homeShort: "Spain", awayShort: "DPR Korea", pageGaveCard: true), "No probability data")
    }

    /// Two unblended venues: no one number, so VoiceOver picks none either.
    func testVoiceOverPicksNoVenueBetweenTwo() {
        let points = [
            pt("2026-09-27T16:00:00Z", 0.30, "polymarket"),
            pt("2026-09-27T16:00:00Z", 0.35, "kalshi"),
        ]
        XCTAssertEqual(OddsChartView.accessibilityValue(
            dataPoints: points, selectedDate: nil,
            homeShort: "Spain", awayShort: "DPR Korea", pageGaveCard: false), "No probability data")
    }

    /// With a blend, VoiceOver speaks the blend for either card.
    func testVoiceOverSpeaksTheBlendWhenDrawn() {
        let points = [
            pt("2026-09-27T16:00:00Z", 0.60, "aggregate"),
            pt("2026-09-27T16:05:00Z", 0.90, "polymarket"),
        ]
        for pageGaveCard in [true, false] {
            XCTAssertEqual(OddsChartView.accessibilityValue(
                dataPoints: points, selectedDate: "2026-09-27T16:05:00Z".asDate,
                homeShort: "Spain", awayShort: "DPR Korea", pageGaveCard: pageGaveCard),
                "Spain 60%, DPR Korea 40%")
        }
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
