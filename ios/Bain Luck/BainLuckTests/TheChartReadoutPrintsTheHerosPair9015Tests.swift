import Foundation
import XCTest
@testable import Bain_Luck

/// #9015 — Oregon at USC (14870010), live in Q3: the hero read Oregon 75% –
/// USC 25% while the readout above the chart read "Trojans 26% — Ducks 75%".
///
/// The chart's 02:10Z `aggregate_line` point was home 0.255. The readout
/// rounded each side on its own — 25.5 up to 26, 74.5 up to 75 — so a
/// half-cent moment printed 101 and a USC number the hero never showed.
final class TheChartReadoutPrintsTheHerosPair9015Tests: XCTestCase {

    private func readout(home: Double, sport: String?) -> (home: Int, away: Int?) {
        let point = ChartDataPoint(date: Date(timeIntervalSince1970: 1_790_475_000),
                                   probability: home, source: "aggregate")
        let play = OddsChartView.playPoint(for: point, sportKey: sport)
        return GamePlayCardView.printedPercents(home: play.homeProb, away: play.awayProb)
    }

    /// The specimen, through the same path a scrub and the resting readout take.
    func testTheSpecimenPrintsTwentyFiveBesideSeventyFive() {
        let printed = readout(home: 0.255, sport: "americanfootball_ncaaf")
        XCTAssertEqual(printed.home, 25)
        XCTAssertEqual(printed.away, 75)
    }

    /// Control on the same bytes: the old per-side rounding is the 26 + 75 the
    /// screen showed, so the specimen does sit on the boundary.
    func testTheSpecimenUnderPerSideRoundingIsTheHundredAndOneOnScreen() {
        let away = 1.0 - 0.255
        XCTAssertEqual(Int((0.255 * 100).rounded()) + Int((away * 100).rounded()), 101)
    }

    /// Whichever side is the favourite, the pair sums to 100 across the
    /// half-cent grid the venues quote on.
    func testEveryHalfCentMomentSumsToOneHundred() {
        for tenth in stride(from: 5, through: 995, by: 5) {
            let home = Double(tenth) / 1000
            let printed = readout(home: home, sport: "baseball_mlb")
            XCTAssertEqual(printed.home + (printed.away ?? -1000), 100, "home \(home)")
        }
    }

    /// The readout and the hero's local rule agree number for number.
    func testTheReadoutMatchesTheDuelRuleTheHeroUses() {
        for home in [0.255, 0.745, 0.505, 0.495, 0.075, 0.925] {
            let printed = readout(home: home, sport: "americanfootball_nfl")
            let duel = renderedDuelPercents(away: 1.0 - home, home: home)
            XCTAssertEqual(printed.home, duel[1], "home \(home)")
            XCTAssertEqual(printed.away, duel[0], "home \(home)")
        }
    }

    /// #5271 stays: a draw-priced sport prints the home side alone, on the
    /// contract's scalar rule.
    func testADrawPricedSportStillPrintsOnlyTheHomeSide() {
        let printed = readout(home: 0.565, sport: "soccer_usa_mls")
        XCTAssertNil(printed.away)
        XCTAssertEqual(printed.home, renderedPercent(0.565))
        XCTAssertEqual(printed.home, 57)
    }
}
