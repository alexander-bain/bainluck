import XCTest
@testable import Bain_Luck

/// #8902 — a SEASON OUTLOOK row that is a player's chance names the player.
///
/// The tile printed the market label and the number only. On 15318868
/// (LAD @ SF) the server serves "NL Reliever of the Year Winner?" as
/// `season_stat`, so the Dodgers tile read "NL Reliever of the Year 3%" — the
/// team's chance, to a reader — when it is Tanner Scott's. On 14782152
/// (CAR @ CLE) the Panthers tile read "NFC Defensive Player of the Month 53%"
/// for Devin Lloyd.
///
/// The fixtures are production's own rows from those events' `/related-futures`
/// (2026-09-26), team rows included: the team rows must stay unnamed.
final class SeasonOutlookNamesThePlayer8902Tests: XCTestCase {

    private func future(_ outcome: String, _ market: String) -> RelatedFuture {
        let json = """
        {"market_id": 1, "market_name": "\(market)", "outcome_id": 1,
         "outcome_name": "\(outcome)", "probability": 0.03, "display_category": "season_stat"}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(RelatedFuture.self, from: Data(json.utf8))
    }

    func testAPlayersRowIsNamed() {
        XCTAssertEqual(seasonOutlookPlayerName(future("Tanner Scott", "NL Reliever of the Year Winner?"),
                                               teamName: "Los Angeles Dodgers"), "Tanner Scott")
        XCTAssertEqual(seasonOutlookPlayerName(future("Ryan Walker", "NL Reliever of the Year Winner?"),
                                               teamName: "San Francisco Giants"), "Ryan Walker")
        XCTAssertEqual(seasonOutlookPlayerName(future("Edwin Díaz", "NL Reliever of the Year Winner?"),
                                               teamName: "Los Angeles Dodgers"), "Edwin Díaz")
        XCTAssertEqual(seasonOutlookPlayerName(future("Devin Lloyd", "NFC Defensive Player of the Month in September"),
                                               teamName: "Carolina Panthers"), "Devin Lloyd")
        XCTAssertEqual(seasonOutlookPlayerName(future("Harold Fannin Jr.", "AFC Offensive Player of the Month in September"),
                                               teamName: "Cleveland Browns"), "Harold Fannin Jr.")
    }

    func testATeamsOwnRowIsNotNamed() {
        // Every team spelling production serves in this tile: full, city-only, abbreviated.
        XCTAssertNil(seasonOutlookPlayerName(future("Washington Capitals", "Presidents' Trophy"),
                                             teamName: "Washington Capitals"))
        XCTAssertNil(seasonOutlookPlayerName(future("Philadelphia Flyers", "Presidents' Trophy"),
                                             teamName: "Philadelphia Flyers"))
        XCTAssertNil(seasonOutlookPlayerName(future("Chicago WS", "AL Central Winner"),
                                             teamName: "Chicago White Sox"))
        XCTAssertNil(seasonOutlookPlayerName(future("Carolina", "NFC South Division"),
                                             teamName: "Carolina Panthers"))
        XCTAssertNil(seasonOutlookPlayerName(future("LAD", "Win Total"),
                                             teamName: "Los Angeles Dodgers"))
    }

    func testAnswersAndLinesAreNotNames() {
        for outcome in ["Yes", "No", "Over 92.5", "Under 92.5", "92.5+ wins", "Field"] {
            XCTAssertNil(seasonOutlookPlayerName(future(outcome, "Dodgers Win Total"),
                                                 teamName: "Los Angeles Dodgers"), outcome)
        }
    }
}
