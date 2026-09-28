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
        let source = duelProbabilityStrings(away: away, home: home)
        XCTAssertEqual(source.home, "44%")
        XCTAssertEqual(source.away, "56%")
        let labels = GamePlayCardView.printedLabels(home: home, away: away)
        XCTAssertEqual(labels.home, "44%")
        XCTAssertEqual(labels.away, "56%")
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
}
