import XCTest
@testable import Bain_Luck

final class EntertainmentCollapsedLadder4751Tests: XCTestCase {
    private func decode(_ flag: String) throws -> EntMarketRow {
        let json = """
        {"q":"A threshold market","market_id":4751,"src":"kalshi",
         "prob":95,"outcome_count":3,"top_outcomes":[
         {"name":"Above 30","prob":95,"delta_24h":12},
         {"name":"Above 20","prob":90},{"name":"Above 10","prob":20}]
         \(flag)}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EntMarketRow.self, from: Data(json.utf8))
    }

    func testExplicitRefusalSurvivesDecodingWithoutLosingDestination() throws {
        let row = try decode(",\"ladder_treatment_refused\":true")
        XCTAssertTrue(row.refusesLadderPrices)
        XCTAssertEqual(row.marketId, 4751)
        XCTAssertEqual(row.q, "A threshold market")
        XCTAssertEqual(row.topOutcomes.count, 3)
    }

    func testOlderCachedPayloadAndExplicitFalseKeepTheirExistingBehavior() throws {
        for flag in ["", ",\"ladder_treatment_refused\":null", ",\"ladder_treatment_refused\":false"] {
            let row = try decode(flag)
            XCTAssertFalse(row.refusesLadderPrices)
            XCTAssertEqual(row.prob, 95)
        }
    }
}
