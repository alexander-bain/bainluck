import XCTest
@testable import Bain_Luck

/// #10873 — "Which game or market?" from a Spotlight or Shortcuts tile offered
/// only Cancel (Nov 9): no suggestions. It now offers the top answer to each of
/// today's trending searches, public rows only.
final class TrendingSuggestions10873Tests: XCTestCase {
    private func response(game id: Int, away: String, home: String) throws -> SearchResponse {
        let json = """
        {"query": "q", "results": [{"id": \(id), "sport": "basketball_nba", "home_team": "\(home)", "away_team": "\(away)",
                      "commence_time": "2026-11-12T00:00:00Z", "status": "scheduled"}],
         "futures": [], "total": 1}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchResponse.self, from: Data(json.utf8))
    }

    func testEachTrendingSearchOffersItsTopAnswerInTrendingOrderOnce() async throws {
        let celtics = try response(game: 1, away: "Boston Celtics", home: "Toronto Raptors")
        let lakers = try response(game: 2, away: "Los Angeles Lakers", home: "Detroit Pistons")
        let rows = await TrendingSuggestions10873.entities(
            trending: { ["celtics", "  ", "lakers", "boston", "nothing"] },
            search: { query in
                switch query {
                case "celtics", "boston": return celtics
                case "lakers": return lakers
                default: throw URLError(.badServerResponse)
                }
            })
        XCTAssertEqual(rows.map(\.recordID), [1, 2], "Celtics first, Lakers next, Boston's repeat and the failure dropped")
        XCTAssertEqual(rows.first?.title, ProbabilityAnswer10873.matchup(away: "Boston Celtics", home: "Toronto Raptors"))
    }

    func testAFailedTrendingReadOffersNothing() async {
        let rows = await TrendingSuggestions10873.entities(trending: { throw URLError(.notConnectedToInternet) },
                                                          search: { _ in XCTFail("no search without trending"); throw URLError(.unknown) })
        XCTAssertTrue(rows.isEmpty)
    }

    func testOnlyAHandfulIsAsked() async throws {
        let one = try response(game: 9, away: "A", home: "B")
        let asked = AskedCounter()
        _ = await TrendingSuggestions10873.entities(
            trending: { (1...12).map { "q\($0)" } },
            search: { _ in await asked.add(); return one })
        let count = await asked.count
        XCTAssertEqual(count, TrendingSuggestions10873.limit)
    }

    func testNothingPrivateIsRead() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Intents/TrendingSuggestions10873.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        for privateRead in ["fetchPins", "RecentSearches", "PinManager", "fetchProfile"] {
            XCTAssertFalse(source.contains(privateRead), privateRead)
        }
    }
}

private actor AskedCounter {
    var count = 0
    func add() { count += 1 }
}
