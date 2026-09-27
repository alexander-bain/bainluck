import XCTest
@testable import Bain_Luck

/// #9185 / #9015 — **VoiceOver speaks the chart's percents as the readout card
/// prints them.**
///
/// #9210 put the card on `GamePlayCardView.printedLabels`: a live 0.996 prints
/// "Jaguars >99% — Patriots <1%" (Patriots at Jaguars, 14782706, 4th quarter),
/// and a finished game's settled end prints its result, 100% / 0%. The chart's
/// VoiceOver value still interpolated a bare integer, so under that card it
/// said "Jaguars 100%, Patriots 0%" — a decided game, while the card and the
/// hero both said it was not.
final class VoiceOverSpeaksTheReadoutsGuard9185Tests: XCTestCase {

    private func pt(_ t: Double, _ p: Double, _ src: String = "aggregate") -> ChartDataPoint {
        ChartDataPoint(date: Date(timeIntervalSince1970: t), probability: p, source: src)
    }

    /// Live, lopsided: the guard the card prints.
    func testALiveLopsidedPointIsSpokenWithTheGuard() {
        let value = OddsChartView.selectionReadout(for: pt(1, 0.996), homeShort: "Jaguars",
                                                   awayShort: "Patriots")
        XCTAssertEqual(value, "Jaguars >99%, Patriots <1%")
        let low = OddsChartView.selectionReadout(for: pt(1, 0.004), homeShort: "Jaguars",
                                                 awayShort: "Patriots")
        XCTAssertEqual(low, "Jaguars <1%, Patriots >99%")
    }

    /// A live 1.0 keeps the guard too, because the live hero and card guard it.
    func testALiveSettledLookingEndIsStillGuarded() {
        let value = OddsChartView.selectionReadout(for: pt(1, 1.0), homeShort: "H", awayShort: "A")
        XCTAssertEqual(value, "H >99%, A <1%")
    }

    /// Finished: the settled end is the result, as the card prints it.
    func testAFinishedGamesEndIsSpokenAsTheResult() {
        let value = OddsChartView.selectionReadout(for: pt(1, 1.0), homeShort: "Jaguars",
                                                   awayShort: "Patriots", gameFinished: true)
        XCTAssertEqual(value, "Jaguars 100%, Patriots 0%")
    }

    /// Finished does not un-guard a point that is NOT the settled end: scrubbing
    /// back to a 4th-quarter 0.996 on a finished game still says ">99%".
    func testScrubbingAFinishedGameBackToALopsidedPointKeepsTheGuard() {
        let value = OddsChartView.selectionReadout(for: pt(1, 0.996), homeShort: "H",
                                                   awayShort: "A", gameFinished: true)
        XCTAssertEqual(value, "H >99%, A <1%")
    }

    /// Spoken and printed agree for every value the card can print.
    func testSpokenPercentsAreTheCardsPrintedPercents() {
        for p in [0.0, 0.004, 0.012, 0.25, 0.495, 0.5, 0.505, 0.62, 0.988, 0.996, 1.0] {
            for finished in [false, true] {
                let printed = GamePlayCardView.printedLabels(home: p, away: 1 - p,
                                                             gameFinished: finished)
                let spoken = OddsChartView.selectionReadout(for: pt(1, p), homeShort: "H",
                                                            awayShort: "A", gameFinished: finished)
                XCTAssertEqual(spoken, "H \(printed.home), A \(printed.away ?? "")",
                               "p=\(p) finished=\(finished)")
            }
        }
    }

    /// The resting value on a live game's line whose latest point is 0.996.
    func testTheRestingValueOnALiveGameIsGuarded() {
        let points = [pt(1, 0.60), pt(2, 0.996)]
        let value = OddsChartView.accessibilityValue(dataPoints: points, selectedDate: nil,
                                                     homeShort: "Jaguars", awayShort: "Patriots")
        XCTAssertEqual(value, "Jaguars >99%, Patriots <1%")
    }

    /// #5271 — on a draw-priced sport the card withholds the away slot (`1 − home`
    /// is "away OR draw"), so VoiceOver speaks the home number alone. Before, it
    /// spoke the complement the card refuses to print.
    func testADrawPricedSportSpeaksNoAwayNumber() {
        let point = ChartDataPoint(date: Date(timeIntervalSince1970: 1), probability: 0.30,
                                   source: "aggregate", homeScore: 0, awayScore: 1)
        let value = OddsChartView.selectionReadout(for: point, homeShort: "Spain",
                                                   awayShort: "DPR Korea",
                                                   sportKey: "soccer_fifa_world_cup")
        XCTAssertEqual(value, "Spain 30%, score 0–1")
        let resting = OddsChartView.accessibilityValue(dataPoints: [pt(1, 0.30)], selectedDate: nil,
                                                       homeShort: "Spain", awayShort: "DPR Korea",
                                                       sportKey: "soccer_epl")
        XCTAssertEqual(resting, "Spain 30%")
        // A two-way sport keeps both.
        XCTAssertEqual(OddsChartView.selectionReadout(for: pt(1, 0.30), homeShort: "H", awayShort: "A",
                                                      sportKey: "americanfootball_nfl"),
                       "H 30%, A 70%")
    }

    /// The chart's overlay is told whether the game is over, from the same
    /// `EventState.isFinished(status)` the readout cards are given — otherwise a
    /// finished game's end is spoken ">99%" under a card printing "100%" — and
    /// the sport, or a soccer chart speaks the away number the card withholds.
    func testTheOverlayIsToldWhetherTheGameIsOver() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("OddsChartView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        guard let start = source.range(of: "OddsChartSelectionOverlay(selection:") else {
            return XCTFail("OddsChartSelectionOverlay call site not found")
        }
        let call = source[start.lowerBound...].prefix(1200)
        guard let close = call.range(of: ")\n") else { return XCTFail("call not closed") }
        let args = String(call[..<close.upperBound])
        XCTAssertTrue(args.contains("gameFinished: EventState.isFinished(status)"), args)
        XCTAssertTrue(args.contains("sportKey: sportKey"), args)
    }
}
