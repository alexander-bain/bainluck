import XCTest
@testable import Bain_Luck

@MainActor
final class ComplementDisplayTie9321Tests: XCTestCase {
    func testChartAndSourceStringsMatchTheServedHeroAt445() {
        let home = 0.445, away = 1 - home
        let served = renderedDuelPercents(away: 0.555, home: home)
        XCTAssertEqual(served, [56, 44])
        let chart = GamePlayCardView.printedPercents(home: home, away: away)
        XCTAssertEqual(chart.home, served[1])
        XCTAssertEqual(chart.away, served[0])
        let source = duelProbabilityStrings(away: away, home: home, complementaryAway: true)
        XCTAssertEqual(source.home, "44%")
        XCTAssertEqual(source.away, "56%")
    }

    func testPushedHeroReceiptMatchesTheServedPairWithoutChangingRawValues() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let event = try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Home","away_team":"Away","sport":"tennis_atp","status":"live",
         "current_odds":{"home_probability":0.445,"away_probability":0.5549999999999999}}
        """.utf8))
        let printed = LivePriceActivity.displayedPercents(in: event)
        XCTAssertEqual(printed.home, 44)
        XCTAssertEqual(printed.away, 56)
        XCTAssertEqual(event.currentOdds?.homeProbability, 0.445)
        XCTAssertEqual(event.currentOdds?.awayProbability, 1 - 0.445)
    }

    func testHalfPercentTiesAndNeighborsMatchServerDecimalComplements() {
        for thousandths in [255, 435, 445, 555, 565, 585, 745] {
            for offset in [-1, 0, 1] {
                let millionths = thousandths * 1000 + offset
                let home = Double(millionths) / 1_000_000
                let serverAway = Double(1_000_000 - millionths) / 1_000_000
                let expected = renderedDuelPercents(away: serverAway, home: home)
                let point = ChartDataPoint(date: Date(timeIntervalSince1970: 1_790_475_000),
                                          probability: home, source: "aggregate")
                let play = OddsChartView.playPoint(for: point, sportKey: "baseball_mlb")
                let printed = GamePlayCardView.printedPercents(home: play.homeProb, away: play.awayProb)
                XCTAssertEqual(printed.home, expected[1], "home \(home)")
                XCTAssertEqual(printed.away, expected[0], "home \(home)")
                XCTAssertEqual(play.homeProb, home)
                XCTAssertEqual(play.awayProb, 1 - home)
            }
        }
    }

    func testIndependentBookmakerInputsKeepTheOriginalContract() {
        for (away, home) in [(1 - 0.445, 0.445), (0.53, 0.53), (0.7, 0.2)] {
            let printed = duelProbabilityStrings(away: away, home: home)
            let ordinary = renderedDuelPercents(away: away, home: home)
            XCTAssertEqual(printed.away, formatProbability(away, renderedPercent: ordinary[0]))
            XCTAssertEqual(printed.home, formatProbability(home, renderedPercent: ordinary[1]))
        }
        XCTAssertEqual(renderedDuelPercents(away: 1 - 0.445, home: 0.445), [55, 45])
        XCTAssertEqual(complementDisplayPercents(away: 0.7, home: 0.2), [70, 20])
    }

    func testCompleteServedPairWinsButPartialPairsDoNotMix() {
        XCTAssertEqual(complementDisplayPercents(away: 1 - 0.445, home: 0.445,
                                               servedAway: 61, servedHome: 39), [61, 39])
        XCTAssertEqual(complementDisplayPercents(away: 1 - 0.445, home: 0.445,
                                               servedAway: 61, servedHome: nil), [56, 44])
    }

    func testWithheldDrawSideStaysWithheld() {
        let point = ChartDataPoint(date: Date(timeIntervalSince1970: 1_790_475_000),
                                  probability: 0.445, source: "aggregate")
        let play = OddsChartView.playPoint(for: point, sportKey: "soccer_usa_mls")
        let chart = GamePlayCardView.printedPercents(home: play.homeProb, away: play.awayProb)
        XCTAssertNil(chart.away)
        XCTAssertEqual(chart.home, renderedPercent(0.445))
        let row = duelProbabilityStrings(away: nil, home: 0.445, complementaryAway: true)
        XCTAssertEqual(row.away, "—")
        XCTAssertEqual(row.home, "45%")
    }

    func testLiveBoundaryLabelsAndFinalResultsStayDistinct() {
        for home in [0.005, 0.995] {
            let row = duelProbabilityStrings(away: 1 - home, home: home, complementaryAway: true)
            XCTAssertEqual(row.home, home < 0.5 ? "<1%" : ">99%")
            XCTAssertEqual(row.away, home < 0.5 ? ">99%" : "<1%")
        }
        let won = GamePlayCardView.printedPercents(home: 1, away: 0)
        XCTAssertEqual(won.home, 100)
        XCTAssertEqual(won.away, 0)
        let lost = GamePlayCardView.printedPercents(home: 0, away: 1)
        XCTAssertEqual(lost.home, 0)
        XCTAssertEqual(lost.away, 100)
    }
}
