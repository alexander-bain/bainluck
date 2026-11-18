import XCTest
@testable import Bain_Luck

final class WidgetLiveGamesNoOpening12824Tests: XCTestCase {

    func testLiveGamesWidgetRejectsOpeningTaggedFeedItemsAndAdmitsCurrentBlends() throws {
        let json = """
        {
          "items": [
            {
              "type": "event",
              "headline": "Opening-only cached live row",
              "data": {
                "id": 7001,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Boston Celtics",
                "away_team": "Toronto Raptors",
                "status": "live",
                "home_score": 68,
                "away_score": 72,
                "hero_probability_source": "opening",
                "current_odds": {
                  "home_probability": 0.64,
                  "away_probability": 0.36,
                  "home_rendered_percent": 64,
                  "away_rendered_percent": 36
                }
              }
            },
            {
              "type": "event",
              "headline": "Live blend row",
              "data": {
                "id": 7002,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "New York Knicks",
                "away_team": "Miami Heat",
                "status": "live",
                "home_score": 81,
                "away_score": 77,
                "hero_probability_source": "blend",
                "current_odds": {
                  "home_probability": 0.61,
                  "away_probability": 0.39,
                  "home_rendered_percent": 61,
                  "away_rendered_percent": 39
                }
              }
            }
          ]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try decoder.decode(WidgetFeedResponse.self, from: Data(json.utf8))
        XCTAssertEqual(feed.items.count, 2)

        let openingEvent = try XCTUnwrap(feed.items[0].data)
        let blendEvent = try XCTUnwrap(feed.items[1].data)

        XCTAssertEqual(openingEvent.heroProbabilitySource, "opening")
        XCTAssertFalse(WidgetLifecycle.admitsLiveProbability(openingEvent))

        XCTAssertEqual(blendEvent.heroProbabilitySource, "blend")
        XCTAssertTrue(WidgetLifecycle.admitsLiveProbability(blendEvent))
    }
}
