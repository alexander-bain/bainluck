import XCTest
@testable import Bain_Luck

/// #9170 — the Novelty card names each team once, the way the page does.
///
/// Fixtures are production's own rows from 14781702's `/related-futures`
/// (SEA vs WSH, 2026-09-27 16:46Z): the card read
/// "SEA Seahawks vs WAS Commanders: 4th Quarter Spread" over legs
/// "SEA Seahawks wins 4Q by over 2.5 points", and the page header says WSH.
final class NoveltyCardNamesTeamsOnce9170Tests: XCTestCase {

    private func leg(_ outcomeId: Int, market: Int, name: String, clean: String,
                     _ outcome: String, _ prob: Double) -> RelatedFuture {
        let json = """
        {"market_id": \(market), "market_name": "\(name)", "clean_label": "\(clean)",
         "outcome_id": \(outcomeId), "outcome_name": "\(outcome)", "probability": \(prob),
         "display_category": "novelty", "source": "kalshi"}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(RelatedFuture.self, from: Data(json.utf8))
    }

    // market_name carries Kalshi's trailing space; clean_label does not.
    private let spreadName = "SEA Seahawks vs WAS Commanders: 4th Quarter Spread "
    private let spreadClean = "SEA Seahawks vs WAS Commanders: 4th Quarter Spread"

    private lazy var spread: [RelatedFuture] = [
        leg(235784821, market: 62400197, name: spreadName, clean: spreadClean, "SEA Seahawks wins 4Q by over 2.5 points", 0.5),
        leg(235784822, market: 62400197, name: spreadName, clean: spreadClean, "SEA Seahawks wins 4Q by over 3.5 points", 0.38),
        leg(235784824, market: 62400197, name: spreadName, clean: spreadClean, "WAS Commanders wins 4Q by over 2.5 points", 0.265),
    ]

    func testTheCardTitleNamesEachTeamOnce() {
        let card = noveltyCards(spread)[0]
        XCTAssertEqual(card.label, "Seahawks vs Commanders: 4th Quarter Spread")
    }

    func testEveryLegNamesItsTeamByNickname() {
        let card = noveltyCards(spread)[0]
        XCTAssertEqual(card.legs.map { noveltyLegName($0, in: card) }, [
            "Seahawks wins 4Q by over 2.5 points",
            "Seahawks wins 4Q by over 3.5 points",
            "Commanders wins 4Q by over 2.5 points",
        ])
    }

    func testTheMatchupRuleOnlyTouchesItsOwnShape() {
        // No ticker: the page's own "Seahawks vs. Commanders" titles stay put.
        XCTAssertEqual(TickerMatchupName.display("Seahawks vs. Commanders: O/U 34.5"),
                       "Seahawks vs. Commanders: O/U 34.5")
        // Capitals that are not a matchup are never cut.
        XCTAssertEqual(TickerMatchupName.display("US Open: Will the Honey Deuce sell 500,000 cups?"),
                       "US Open: Will the Honey Deuce sell 500,000 cups?")
        XCTAssertEqual(TickerMatchupName.display("NBA Finals MVP"), "NBA Finals MVP")
        // A multi-word nickname and `vs.` both parse.
        XCTAssertEqual(TickerMatchupName.display("POR Trail Blazers vs. LA Lakers: 1st Half Winner"),
                       "Trail Blazers vs. Lakers: 1st Half Winner")
        // Two teams sharing a nickname keep their tickers — they are the only difference.
        XCTAssertEqual(TickerMatchupName.display("USA Basketball vs CAN Basketball: 1st Half"),
                       "USA Basketball vs CAN Basketball: 1st Half")
        // A leg is only rewritten with the tickers ITS title names.
        XCTAssertEqual(TickerMatchupName.display("WAS Commanders wins 4Q", matchup: "Georgia Tech vs Stanford: 4th Quarter"),
                       "WAS Commanders wins 4Q")
    }

    func testANonTickerCardIsUnchanged() {
        let gt = leg(1, market: 62157416, name: "Georgia Tech vs Stanford: 4th Quarter",
                     clean: "Georgia Tech vs Stanford: 4th Quarter", "Georgia Tech wins 4th Quarter", 0.485)
        let card = noveltyCards([gt])[0]
        XCTAssertEqual(card.label, "Georgia Tech vs Stanford: 4th Quarter")
        XCTAssertEqual(noveltyLegName(gt, in: card), "Georgia Tech wins 4th Quarter")
    }
}
