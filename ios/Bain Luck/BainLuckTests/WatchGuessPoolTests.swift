import XCTest

/// L2-180: guards the Watch Higher/Lower question pool.
///
/// The bug (mirror of web L2-178): `WatchGuessViewModel` built questions from
/// BOTH event and futures cards and submitted `question.id` as `market_id`. An
/// event card carries an events-table id, so submitting it poisoned
/// `user_predictions` — and because Event and FuturesMarket ids share a numeric
/// namespace, a collision silently joined the row to an unrelated futures market.
///
/// `WatchFeedModels.swift` and `WatchGuessPool.swift` are pure Foundation and are
/// compiled into this test bundle directly (see the project's target membership),
/// so these run without pulling WatchKit into the iOS test host.
final class WatchGuessPoolTests: XCTestCase {

    private func decode(_ json: String) throws -> WatchFeedResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(WatchFeedResponse.self, from: Data(json.utf8))
    }

    // MARK: - The core regression: an Event/Futures numeric-ID collision

    /// A mixed feed where the event AND the futures share numeric id 7. The pool
    /// must produce exactly one question — the FUTURES — and its id must be the
    /// futures market id, never the event id.
    func testEventFuturesIdCollisionYieldsOnlyFuturesQuestion() throws {
        let feed = try decode("""
        {
          "items": [
            { "type": "event", "score": 80,
              "data": { "id": 7, "home_team": "Celtics", "away_team": "Lakers",
                        "status": "live", "current_odds": { "home_probability": 0.62 } } },
            { "type": "futures", "score": 70,
              "data": { "id": 7, "name": "Who wins MVP?",
                        "top_outcomes": [ { "name": "Jokic", "probability": 0.40 } ] } }
          ],
          "total": 2, "limit": 8, "offset": 0, "has_more": false
        }
        """)

        let questions = WatchGuessPool.buildQuestions(from: feed.items)

        // Only the futures card became a question.
        XCTAssertEqual(questions.count, 1)
        let q = try XCTUnwrap(questions.first)
        // The id is the futures market id (which here collides with the event id),
        // and it originated from the futures card — proven by its title/subject.
        XCTAssertEqual(q.id, 7)
        XCTAssertEqual(q.title, "Who wins MVP?")
        XCTAssertEqual(q.subject, "Jokic")
        // It is NOT the event framing ("<Away> vs <Home>" / "<Home> to win").
        XCTAssertNotEqual(q.title, "Lakers vs Celtics")
        XCTAssertNotEqual(q.subject, "Celtics to win")
    }

    // MARK: - Only futures become questions

    func testMixedFeedProducesOnlyFuturesQuestions() throws {
        let feed = try decode("""
        {
          "items": [
            { "type": "event", "score": 90,
              "data": { "id": 100, "home_team": "A", "away_team": "B",
                        "status": "live", "current_odds": { "home_probability": 0.55 } } },
            { "type": "futures", "score": 80,
              "data": { "id": 200, "name": "Q1",
                        "top_outcomes": [ { "name": "Yes", "probability": 0.40 } ] } },
            { "type": "concept", "score": 70, "data": { "key": "k", "name": "Some Event" } },
            { "type": "futures", "score": 60,
              "data": { "id": 201, "name": "Q2",
                        "top_outcomes": [ { "name": "No", "probability": 0.30 } ] } }
          ],
          "total": 4, "limit": 8, "offset": 0, "has_more": false
        }
        """)

        let questions = WatchGuessPool.buildQuestions(from: feed.items)
        XCTAssertEqual(questions.count, 2)
        XCTAssertEqual(Set(questions.map(\.id)), [200, 201])
        // No event id leaked into the pool.
        XCTAssertFalse(questions.map(\.id).contains(100))
    }

    // MARK: - Band filtering is preserved (near-certain outcomes are unplayable)

    func testOutOfBandFuturesAreExcluded() throws {
        let feed = try decode("""
        {
          "items": [
            { "type": "futures", "score": 80,
              "data": { "id": 1, "name": "Locked",
                        "top_outcomes": [ { "name": "Sure", "probability": 0.99 } ] } },
            { "type": "futures", "score": 80,
              "data": { "id": 2, "name": "Playable",
                        "top_outcomes": [ { "name": "Maybe", "probability": 0.50 } ] } },
            { "type": "futures", "score": 80,
              "data": { "id": 3, "name": "NoOutcomes", "top_outcomes": [] } }
          ],
          "total": 3, "limit": 8, "offset": 0, "has_more": false
        }
        """)

        let questions = WatchGuessPool.buildQuestions(from: feed.items)
        XCTAssertEqual(questions.map(\.id), [2])
    }
}
