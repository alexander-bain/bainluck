import XCTest
@testable import Bain_Luck

/// Ruling 208-A — on Alex's phone (Nov 16) Siri passed "the next Patriots game"
/// to search word for word. Search finds nothing for that phrase and 24 games for
/// "Patriots", so Siri offered futures. A team name must find that team's live
/// or next game before anything else.
final class SiriTeamGames208ATests: XCTestCase {
    func testWhatAReaderSaysIsReducedToWhatSearchMatches() {
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("the next Patriots game"), "Patriots")
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("Patriots game tonight"), "Patriots")
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("the Patriots' game"), "Patriots")
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("what's the chance of the Lakers game"), "Lakers")
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("Patriots vs Jets"), "Patriots vs Jets")
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("Patriots at the Jets"), "Patriots at Jets")
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("New England"), "New England")
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("Super Bowl winner"), "Super Bowl winner")
        // Nothing left after the fillers: the reply is searched as said.
        XCTAssertEqual(GameOrMarketCatalog10873.spokenQuery("the next game"), "the next game")
    }

    func testALiveGameComesFirstThenTheSoonestUpcomingThenFinished() throws {
        let now = Date(timeIntervalSince1970: 1_794_870_000) // Mon 2026-11-16 ~20:20Z
        let response = try Self.response("""
        [{"id":1,"home_team":"Bills","away_team":"Patriots","status":"completed","commence_time":"2026-11-09T18:00:00Z"},
         {"id":2,"home_team":"Patriots","away_team":"Jets","status":"scheduled","commence_time":"2026-12-27T18:00:00Z"},
         {"id":3,"home_team":"Chargers","away_team":"Patriots","status":"scheduled","commence_time":"2026-11-30T18:00:00Z"},
         {"id":4,"home_team":"Patriots","away_team":"Dolphins","status":"live","commence_time":"2026-11-16T18:00:00Z"}]
        """)
        let ids = GameOrMarketCatalog10873.entities(from: response, now: now).filter { $0.kind == .game }.map(\.recordID)
        XCTAssertEqual(ids, [4, 3, 2, 1])
    }

    func testGamesComeBeforeFutures() throws {
        let response = try Self.response("""
        [{"id":3,"home_team":"Chargers","away_team":"Patriots","status":"scheduled","commence_time":"2026-11-30T18:00:00Z"}]
        """, futures: #"[{"id":900,"name":"NFL Super Bowl Winner","source":"kalshi","status":"open"}]"#)
        let kinds = GameOrMarketCatalog10873.entities(from: response).map(\.kind)
        XCTAssertEqual(kinds, [.game, .market])
    }

    private static func response(_ results: String, futures: String = "[]") throws -> SearchResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchResponse.self, from: Data(
            #"{"query":"Patriots","results":\#(results),"futures":\#(futures)}"#.utf8))
    }
}
