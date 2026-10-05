import XCTest
@testable import Bain_Luck

final class GameActivityEventProjectionTests: XCTestCase {
    private func event(status: String = "live", hero: Double = 0.64, current: Double = 0.64, away: Double? = nil) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":101,"home_team":"Giants","away_team":"Dodgers","sport":"baseball_mlb",
         "status":"\(status)","home_score":4,"away_score":2,
         "hero_probability":\(hero),"hero_probability_away":\(1 - hero),
         "hero_probability_observed_at":"2026-10-05T12:00:00Z",
         "current_odds":{"home_probability":\(current),"away_probability":\(away ?? (1 - current)),
                         "captured_at":"2026-10-05T12:01:00Z"}}
        """.utf8))
    }

    func testOnlyTheMatchingProducerClockDatesThePhoneReading() throws {
        let matched = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event()))
        XCTAssertNotNil(matched.probabilityObservedAt)
        XCTAssertNil(matched.scoreObservedAt, "Price receipt does not date the score")
        let moved = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event(current: 0.78)))
        XCTAssertEqual(moved.homeRenderedPercent, 78)
        XCTAssertNil(moved.probabilityObservedAt, "Old hero clock cannot date a different phone number")
    }

    func testChangedAwayPairDoesNotBorrowHeroClock() throws {
        let reading = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(
            for: event(hero: 0.455, current: 0.455, away: 0.60)))
        XCTAssertEqual(reading.homeRenderedPercent, 46)
        XCTAssertNil(reading.probabilityObservedAt)
    }

    func testUpcomingOpeningLineDoesNotStartThisLiveSlice() throws {
        XCTAssertNil(GameActivitySnapshot.liveActivityReading(for: event(status: "scheduled")))
    }

    func testFinalSuppressesForecastWithoutInventingANewClock() throws {
        let final = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event(status: "completed")))
        XCTAssertTrue(final.isTerminal)
        XCTAssertNil(final.probabilityText)
        XCTAssertNil(final.scoreObservedAt)
    }
}
