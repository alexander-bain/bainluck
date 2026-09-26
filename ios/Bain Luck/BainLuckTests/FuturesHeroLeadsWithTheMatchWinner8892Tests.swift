import XCTest
@testable import Bain_Luck

/// #8892 — a game container's market page led with an over/under, not who wins.
///
/// Production `/futures/61778284`, 2026-09-26 — *LoL: Cloud9 vs Team Liquid
/// (BO5) - LCS Playoffs*, `mutually_exclusive: false`. The hero read **71% "Over
/// — O/U 3.5 Games"**; "Cloud9 — Match Winner 36%" was row 6. The server now
/// names that leg as `lead_outcome_id` (#8894) and the hero leads with it.
///
/// Every other board serves `lead_outcome_id: null`, or no key at all before
/// #8894; the controls pin that those boards hero exactly what they did.
final class FuturesHeroLeadsWithTheMatchWinner8892Tests: XCTestCase {

    private static let leadId = 233052896
    private static let overId = 235154674

    // MARK: - Harness

    /// `/api/futures/61778284` as production served it ~19:15Z, every leg in
    /// payload order, plus the `lead_outcome_id` #8894 serves for it. Each
    /// argument is raw JSON; `lead: nil` omits the key, as builds before #8894 do.
    private func cloud9(
        lead: String? = "\(leadId)",
        status: String = "open",
        leadProbability: String = "0.355"
    ) throws -> FuturesMarketDetail {
        let leadKey = lead.map { "\"lead_outcome_id\": \($0)," } ?? ""
        let json = """
        {
          "id": 61778284,
          "name": "LoL: Cloud9 vs Team Liquid (BO5) - LCS Playoffs",
          "status": "\(status)",
          "mutually_exclusive": false,
          \(leadKey)
          "outcomes": [
            {"id": \(Self.overId), "name": "Over — O/U 3.5 Games", "probability": 0.71},
            {"id": 235154678, "name": "Team Liquid — Game Handicap: TL (-1.5) vs Cloud9 (+1.5)", "probability": 0.44},
            {"id": 235154676, "name": "Cloud9 — Game 2 Winner", "probability": 0.425},
            {"id": 235154677, "name": "Cloud9 — Game 3 Winner", "probability": 0.415},
            {"id": 235154675, "name": "Cloud9 — Game 1 Winner", "probability": 0.405},
            {"id": \(Self.leadId), "name": "Cloud9 — Match Winner", "probability": \(leadProbability)},
            {"id": 233176102, "name": "Over — O/U 4.5 Games", "probability": 0.34},
            {"id": 235154681, "name": "Team Liquid — Game Handicap: TL (-2.5) vs Cloud9 (+2.5)", "probability": 0.205}
          ]
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FuturesMarketDetail.self, from: Data(json.utf8))
    }

    // MARK: - The defect

    func test_theServedLeadIsDecoded() throws {
        XCTAssertEqual(try cloud9().leadOutcomeId, Self.leadId,
                       "`lead_outcome_id` must reach the model under convertFromSnakeCase")
    }

    func test_theHeroLeadsWithTheMatchWinnerNotTheMostLopsidedLeg() throws {
        let market = try cloud9()
        let hero = try XCTUnwrap(futuresDetailHeroOutcome(market))
        XCTAssertEqual(hero.id, Self.leadId, "the page heroed 71% Over — O/U 3.5 Games before #8892")
        XCTAssertEqual(hero.name, "Cloud9 — Match Winner")
    }

    /// The hero numeral is looked up in the page's one percent map by id, so the
    /// lead must print the same integer as its own row, not the leader's 71.
    func test_theHeroNumberIsTheLeadsOwnRowNumber() throws {
        let market = try cloud9()
        let hero = try XCTUnwrap(futuresDetailHeroOutcome(market))
        XCTAssertEqual(futuresDetailRenderedPercents(market.outcomes)[hero.id], 36)
    }

    // MARK: - Controls: every other board is unchanged

    func test_aBoardWithNoLeadKeyHeroesTheHighestPricedOutcomeAsBefore() throws {
        let market = try cloud9(lead: nil)
        XCTAssertNil(market.leadOutcomeId, "a build before #8894 serves no key")
        XCTAssertEqual(futuresDetailHeroOutcome(market)?.id, Self.overId)
    }

    func test_aNullLeadHeroesTheHighestPricedOutcomeAsBefore() throws {
        XCTAssertEqual(futuresDetailHeroOutcome(try cloud9(lead: "null"))?.id, Self.overId)
    }

    /// A settled hero is decided by the grade, not by a pre-game pointer.
    func test_aResolvedMarketIgnoresTheLead() throws {
        XCTAssertEqual(futuresDetailHeroOutcome(try cloud9(status: "resolved"))?.id, Self.overId)
    }

    /// A lead with no price would put an empty hero above a priced table.
    func test_anUnpricedLeadFallsBackToTheHighestPricedOutcome() throws {
        XCTAssertEqual(futuresDetailHeroOutcome(try cloud9(leadProbability: "null"))?.id, Self.overId)
    }

    /// An id not on the board (dropped by the display pipeline) never heroes.
    func test_aLeadThatIsNotOnTheBoardFallsBackToTheHighestPricedOutcome() throws {
        XCTAssertEqual(futuresDetailHeroOutcome(try cloud9(lead: "999"))?.id, Self.overId)
    }
}
