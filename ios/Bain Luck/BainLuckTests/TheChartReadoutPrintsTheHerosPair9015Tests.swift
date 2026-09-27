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

    // MARK: - The labels keep the hero's <1% / >99% (second specimen)

    private func labels(home: Double, sport: String?) -> (home: String, away: String?) {
        let point = ChartDataPoint(date: Date(timeIntervalSince1970: 1_790_475_000),
                                   probability: home, source: "aggregate")
        let play = OddsChartView.playPoint(for: point, sportKey: sport)
        return GamePlayCardView.printedLabels(home: play.homeProb, away: play.awayProb)
    }

    /// Patriots at Jaguars (14782706), 4th quarter: the hero read "<1% – >99%"
    /// while the readout printed "Jaguars 100% — Patriots 0%".
    func testALiveNinetyNinePointSixReadsLikeTheHero() {
        let printed = labels(home: 0.996, sport: "americanfootball_nfl")
        XCTAssertEqual(printed.home, ">99%")
        XCTAssertEqual(printed.away, "<1%")
        let mirrored = labels(home: 0.004, sport: "americanfootball_nfl")
        XCTAssertEqual(mirrored.home, "<1%")
        XCTAssertEqual(mirrored.away, ">99%")
    }

    /// Control on the same bytes: the integers alone are the 100 and 0 the
    /// screen showed, so only the label rule moved.
    func testTheSpecimenIntegersAreTheHundredAndZeroOnScreen() {
        let point = ChartDataPoint(date: Date(timeIntervalSince1970: 1_790_475_000),
                                   probability: 0.996, source: "aggregate")
        let play = OddsChartView.playPoint(for: point, sportKey: "americanfootball_nfl")
        let printed = GamePlayCardView.printedPercents(home: play.homeProb, away: play.awayProb)
        XCTAssertEqual(printed.home, 100)
        XCTAssertEqual(printed.away, 0)
    }

    /// Between the guards the labels are the pair rule's integers, unchanged.
    func testInsideTheGuardsTheLabelsAreThePairIntegers() {
        for tenth in stride(from: 10, through: 990, by: 5) {
            let home = Double(tenth) / 1000
            let ints = readout(home: home, sport: "baseball_mlb")
            let printed = labels(home: home, sport: "baseball_mlb")
            XCTAssertEqual(printed.home, "\(ints.home)%", "home \(home)")
            XCTAssertEqual(printed.away, ints.away.map { "\($0)%" }, "home \(home)")
        }
    }

    /// The hero's own two labels, number for number, including the guards.
    func testTheLabelsMatchTheHerosFormatting() {
        for home in [0.996, 0.004, 0.255, 0.991, 0.009, 0.5] {
            let printed = labels(home: home, sport: "americanfootball_nfl")
            let duel = renderedDuelPercents(away: 1.0 - home, home: home)
            XCTAssertEqual(printed.home, formatProbability(home, renderedPercent: duel[1]), "home \(home)")
            XCTAssertEqual(printed.away, formatProbability(1.0 - home, renderedPercent: duel[0]), "home \(home)")
        }
    }

    /// Settled means settled: the same game's line ends on exactly 1.0 at
    /// `completed_at`, under "Jaguars Win" — that is the result, not a hedge.
    func testAFinishedGamesSettledEndPrintsTheResult() {
        let won = GamePlayCardView.printedLabels(home: 1.0, away: 0.0, gameFinished: true)
        XCTAssertEqual(won.home, "100%")
        XCTAssertEqual(won.away, "0%")
        let lost = GamePlayCardView.printedLabels(home: 0.0, away: 1.0, gameFinished: true)
        XCTAssertEqual(lost.home, "0%")
        XCTAssertEqual(lost.away, "100%")
    }

    /// Control: the finished exemption is for the settled end only. A live
    /// 1.0 keeps the live hero's guard, and a finished game's 4th-quarter
    /// 0.996 is still a live moment.
    func testTheExemptionIsOnlyTheFinishedGamesSettledEnd() {
        let live = GamePlayCardView.printedLabels(home: 1.0, away: 0.0)
        XCTAssertEqual(live.home, ">99%")
        XCTAssertEqual(live.away, "<1%")
        let lateButLive = GamePlayCardView.printedLabels(home: 0.996, away: 0.004, gameFinished: true)
        XCTAssertEqual(lateButLive.home, ">99%")
        XCTAssertEqual(lateButLive.away, "<1%")
    }

    func testTheFinishedFlagRidesTheCard() {
        let card = GamePlayCardView(homeTeam: "Jaguars", awayTeam: "Patriots")
        XCTAssertFalse(card.gameFinished)
        XCTAssertTrue(card.finished(true).gameFinished)
        XCTAssertTrue(card.pinningProbabilities().finished(true).pinsProbabilities)
    }

    /// #5271: a draw-priced sport still prints only the home side, guarded too.
    func testADrawPricedSportLabelsOnlyTheHomeSide() {
        let printed = labels(home: 0.996, sport: "soccer_usa_mls")
        XCTAssertNil(printed.away)
        XCTAssertEqual(printed.home, ">99%")
    }
}
