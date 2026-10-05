import XCTest
@testable import Bain_Luck

@MainActor
final class GameActivityScoreObservationTests: XCTestCase {
    private func detail(_ changes: [String: Any] = [:]) throws -> EventDetail {
        var value: [String: Any] = [
            "id": 42, "home_team": "Home", "away_team": "Away", "status": "live",
            "home_score": 0, "away_score": 1, "score_source": "statpal",
            "score_observed_at": "2026-10-05T00:00:00Z",
            "hero_probability": 0.6, "hero_probability_away": 0.4,
            "hero_probability_observed_at": "2026-10-05T00:01:00Z"
        ]
        for (key, replacement) in changes { value[key] = replacement }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: value))
    }

    func testServedScoreProducerClockDatesZeroScoreIndependentlyOfPrice() throws {
        let event = try detail()
        XCTAssertEqual(event.scoreSource, "statpal")
        let snapshot = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event))
        XCTAssertEqual(snapshot.homeScore, 0)
        XCTAssertEqual(snapshot.scoreObservedAt, "2026-10-05T00:00:00Z".asDate)
        XCTAssertEqual(snapshot.probabilityObservedAt, "2026-10-05T00:01:00Z".asDate)
        XCTAssertNotEqual(snapshot.scoreObservedAt, snapshot.probabilityObservedAt)
    }

    func testMissingAttributionClockOrCompleteTupleCannotBorrowOtherClocks() throws {
        let cases: [[String: Any]] = [
            ["score_source": NSNull()], ["score_source": "  "],
            ["score_observed_at": NSNull()], ["score_observed_at": "invalid"],
            ["home_score": NSNull()], ["away_score": NSNull()],
            ["home_score": -1], ["away_score": -1],
            ["score_observed_at": "2026-10-05T00:00:00"]
        ]
        for changes in cases {
            let event = try detail(changes.merging([
                "updated_at": "2026-10-05T00:02:00Z",
                "timestamp": "2026-10-05T00:02:00Z"
            ]) { first, _ in first })
            let snapshot = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event))
            XCTAssertNil(snapshot.scoreObservedAt)
        }
    }

    func testOlderPayloadWithoutScoreObservationStillDecodes() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let event = try decoder.decode(EventDetail.self, from: Data(
            #"{"id":42,"home_team":"Home","away_team":"Away","status":"live","home_score":0,"away_score":1}"#.utf8))
        XCTAssertNil(event.scoreSource)
        XCTAssertNil(event.scoreObservedAt)
        XCTAssertNil(GameActivitySnapshot.liveActivityReading(for: event)?.scoreObservedAt)
    }
}
