import XCTest
@testable import Bain_Luck

/// #9022 — a NOVELTY & FUN card says what its number is the chance OF.
///
/// `/related-futures` serves one entry per outcome. `NoveltyCardView` printed the
/// market label and the probability, never `outcomeName`, so on 15315948
/// (GT vs STAN) the "4th Quarter" winner market drew three cards all titled
/// "Georgia Tech vs Stanford: 4th Quarter" — one read 12%, the Tie leg, unnamed.
/// The page carried 24 such cards from three markets.
///
/// Fixtures are production's own rows from 15315948's `/related-futures`
/// (2026-09-27 02:54Z), split across sides the way the server filed them.
final class NoveltyCardNamesItsOutcome9022Tests: XCTestCase {

    private func leg(_ outcomeId: Int, market: Int, _ label: String, _ outcome: String, _ prob: Double) -> RelatedFuture {
        let json = """
        {"market_id": \(market), "market_name": "\(label)", "clean_label": "\(label)",
         "outcome_id": \(outcomeId), "outcome_name": "\(outcome)", "probability": \(prob),
         "display_category": "novelty", "source": "kalshi"}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(RelatedFuture.self, from: Data(json.utf8))
    }

    private let winner = "Georgia Tech vs Stanford: 4th Quarter"
    private let total = "Georgia Tech vs Stanford: 4th Quarter Total"

    private lazy var away: [RelatedFuture] = [
        leg(1, market: 62157416, winner, "Georgia Tech wins 4th Quarter", 0.485),
        leg(2, market: 62400775, total, "Over 20.5 4Q points scored", 0.33),
    ]
    private lazy var home: [RelatedFuture] = [
        leg(3, market: 62157416, winner, "Stanford wins 4th Quarter", 0.35),
        leg(4, market: 62157416, winner, "Tie 4th Quarter", 0.15),
        leg(5, market: 62400775, total, "Over 2.5 4Q points scored", 0.785),
        leg(6, market: 62400775, total, "Over 13.5 4Q points scored", 0.515),
        leg(7, market: 62400775, total, "Over 27.5 4Q points scored", 0.14),
    ]

    func testOneCardPerMarketNotOnePerOutcome() {
        let cards = noveltyCards(away + home)
        XCTAssertEqual(cards.map(\.marketId), [62157416, 62400775],
                       "legs of one market arrive split across sides — they fold into ONE card")
        XCTAssertEqual(cards.map(\.label), [winner, total])
    }

    func testTheTieLegIsNamedBesideItsNumber() {
        let card = noveltyCards(away + home)[0]
        let printed = card.legs.map { (noveltyLegName($0, in: card), $0.probability) }
        XCTAssertEqual(printed.map(\.0), ["Georgia Tech wins 4th Quarter", "Stanford wins 4th Quarter", "Tie 4th Quarter"],
                       "strongest first, and every leg carries its outcome — the old card printed 15% with no name")
        XCTAssertEqual(printed.map(\.1), [0.485, 0.35, 0.15])
    }

    func testEveryLegOfAMultiOutcomeMarketIsNamed() {
        for card in noveltyCards(away + home) {
            for l in card.legs {
                XCTAssertEqual(noveltyLegName(l, in: card), l.outcomeName,
                               "\(card.label): a bare number is the #9022 defect")
            }
        }
    }

    func testAnOutcomeFiledOnBothSidesIsOneLeg() {
        let tie = home[1]
        let cards = noveltyCards(away + home + [tie])
        XCTAssertEqual(cards[0].legs.filter { $0.outcomeId == tie.outcomeId }.count, 1)
    }

    func testALoneYesLegLetsTheQuestionSpeak() {
        let question = "Will the Honey Deuce sell 500,000 cups?"
        let yes = leg(8, market: 99, question, "Yes", 0.62)
        let card = noveltyCards([yes])[0]
        XCTAssertNil(noveltyLegName(yes, in: card), "the label is the claim; 'Yes 62%' adds nothing")

        let named = leg(9, market: 98, winner, "Tie 4th Quarter", 0.15)
        let lone = noveltyCards([named])[0]
        XCTAssertEqual(noveltyLegName(named, in: lone), "Tie 4th Quarter",
                       "a lone leg whose outcome is NOT the label still names itself — the 5% floor can leave one leg")
    }
}
