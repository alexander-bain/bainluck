import XCTest

/// L2-225 — the Watch's terminal-lifecycle gate for markets.
///
/// `WatchFeedEvent` has carried `status` and an `isSettled` helper since it was
/// written; `WatchFeedFutures` carried an id, a name, a category and a price. Every
/// Watch futures consumer therefore had no way to tell a settled market from a live
/// one:
///
///  * `WatchMarquee.story` could make a decided question the wrist's TOP STORY;
///  * `WatchGuessPool.buildQuestions` could ask the user to *predict* it — and then
///    grade the guess against an outcome that was already fixed;
///  * glances and the complication (whose timeline is cached) rendered it as a live
///    number with a movement delta.
///
/// A second, separate defect lived in `WatchMarquee.teamGames`: `live` is false once
/// a game settles, so the old `startText` expression fell through and rendered a
/// FINISHED game with a forward-looking start time.
///
/// `WatchFeedModels.swift`, `WatchMarquee.swift` and `WatchGuessPool.swift` are pure
/// Foundation/SwiftUI and compile into this bundle directly (project target
/// membership), so these exercise the real production types. `now` is injected
/// throughout (gotcha #44).
final class WatchFuturesLifecycleTests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!
    private let past = "2026-07-20T00:00:00Z"
    private let future = "2026-08-20T00:00:00Z"

    private func items(_ json: String) throws -> [WatchFeedItem] {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(WatchFeedResponse.self, from: Data(json.utf8)).items
    }

    private func futuresCard(
        id: Int = 1,
        status: String = "\"open\"",
        resolutionDate: String = "null",
        resolved: String = "null",
        winner: String = "null",
        probability: String = "0.42"
    ) -> String {
        """
        { "type": "futures", "score": 70,
          "data": { "id": \(id), "name": "Who wins market \(id)?",
                    "llm_sport_category": "politics",
                    "status": \(status), "resolution_date": \(resolutionDate),
                    "resolved": \(resolved), "winner": \(winner),
                    "top_outcomes": [{ "name": "Team A", "probability": \(probability),
                                       "movement": 0.03 }] } }
        """
    }

    private func decodeFutures(_ card: String) throws -> WatchFeedFutures {
        try XCTUnwrap(try items("{ \"items\": [\(card)] }").first?.futures)
    }

    // MARK: - Decode: the fields exist now, and their absence is tolerated

    func testTerminalFieldsAreDecoded() throws {
        let f = try decodeFutures(futuresCard(
            status: "\"resolved\"", resolutionDate: "\"\(past)\"",
            resolved: "true", winner: "\"Team A\""))
        XCTAssertEqual(f.status, "resolved")
        XCTAssertEqual(f.resolutionDate, past)
        XCTAssertEqual(f.resolved, true)
        XCTAssertEqual(f.winner, "Team A")
    }

    func testLegacyFuturesPayloadStillDecodesAndSurfaces() throws {
        let f = try decodeFutures("""
        { "type": "futures", "score": 70,
          "data": { "id": 3, "name": "Legacy",
                    "top_outcomes": [{ "name": "A", "probability": 0.5 }] } }
        """)
        XCTAssertNil(f.status)
        XCTAssertNil(f.resolutionDate)
        XCTAssertFalse(f.isSettled(now: now), "unknown authority is not settlement")
    }

    // MARK: - isSettled: the four authorities

    func testOpenMarketIsNotSettled() throws {
        XCTAssertFalse(
            try decodeFutures(futuresCard(resolutionDate: "\"\(future)\""))
                .isSettled(now: now))
    }

    func testEveryTerminalStatusSettles() throws {
        for status in ["resolved", "closed", "settled", "finalized", "final", "Closed"] {
            XCTAssertTrue(
                try decodeFutures(futuresCard(status: "\"\(status)\"")).isSettled(now: now),
                "status '\(status)' must settle a Watch market")
        }
    }

    func testPastResolutionDateSettlesEvenWhenStatusIsOpen() throws {
        XCTAssertTrue(
            try decodeFutures(futuresCard(resolutionDate: "\"\(past)\""))
                .isSettled(now: now))
    }

    func testResolvedFlagAndNamedWinnerSettle() throws {
        XCTAssertTrue(try decodeFutures(futuresCard(resolved: "true")).isSettled(now: now))
        XCTAssertTrue(
            try decodeFutures(futuresCard(winner: "\"Team A\"")).isSettled(now: now))
    }

    func testBlankWinnerAndFalseResolvedAreNotAuthority() throws {
        XCTAssertFalse(try decodeFutures(futuresCard(winner: "\"  \"")).isSettled(now: now))
        XCTAssertFalse(try decodeFutures(futuresCard(resolved: "false")).isSettled(now: now))
    }

    func testUnparseableResolutionDateDoesNotSettle() throws {
        XCTAssertFalse(
            try decodeFutures(futuresCard(resolutionDate: "\"garbage\""))
                .isSettled(now: now))
    }

    func testProbabilityAloneNeverSettles() throws {
        XCTAssertFalse(
            try decodeFutures(
                futuresCard(resolutionDate: "\"\(future)\"", probability: "0.99"))
                .isSettled(now: now))
    }

    // MARK: - Higher/Lower deck: never ask about a decided question

    func testGuessPoolSkipsSettledMarkets() throws {
        let feed = try items("""
        { "items": [ \(futuresCard(id: 1, status: "\"resolved\"")),
                     \(futuresCard(id: 2, resolutionDate: "\"\(past)\"")),
                     \(futuresCard(id: 3, resolved: "true")),
                     \(futuresCard(id: 4, winner: "\"Team A\"")),
                     \(futuresCard(id: 5, resolutionDate: "\"\(future)\"")) ] }
        """)
        let questions = WatchGuessPool.buildQuestions(from: feed, now: now)
        XCTAssertEqual(questions.map { $0.id }, [5],
                       "only the still-open market may become a question")
    }

    func testGuessPoolStillBuildsFromAllOpenMarkets() throws {
        let feed = try items("""
        { "items": [ \(futuresCard(id: 1, resolutionDate: "\"\(future)\"")),
                     \(futuresCard(id: 2)) ] }
        """)
        XCTAssertEqual(
            WatchGuessPool.buildQuestions(from: feed, now: now).map { $0.id }, [1, 2])
    }

    func testGuessPoolYieldsAnEmptyDeckRatherThanASettledQuestion() throws {
        let feed = try items("""
        { "items": [ \(futuresCard(id: 1, status: "\"closed\"")),
                     \(futuresCard(id: 2, resolutionDate: "\"\(past)\"")) ] }
        """)
        XCTAssertTrue(WatchGuessPool.buildQuestions(from: feed, now: now).isEmpty)
    }

    // MARK: - Marquee: a settled market is skipped, not fatal

    func testMarqueeSkipsSettledMarketAndScansOnToTheNextStory() throws {
        let feed = try items("""
        { "items": [ \(futuresCard(id: 1, status: "\"resolved\"")),
                     \(futuresCard(id: 2, resolutionDate: "\"\(future)\"")) ] }
        """)
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed, now: now))
        XCTAssertEqual(story.id, "futures-2",
                       "the settled leader must not become the top story")
    }

    func testMarqueeReturnsNilWhenEveryMarketIsSettled() throws {
        let feed = try items("""
        { "items": [ \(futuresCard(id: 1, status: "\"resolved\"")),
                     \(futuresCard(id: 2, resolved: "true")) ] }
        """)
        XCTAssertNil(WatchMarquee.marquee(from: feed, now: now),
                     "no restoration path — an honest blank beats a stale number")
    }

    func testMarqueeStillPrefersALiveGameOverAnOpenMarket() throws {
        let feed = try items("""
        { "items": [ \(futuresCard(id: 1, resolutionDate: "\"\(future)\"")),
            { "type": "event", "score": 95,
              "data": { "id": 55, "home_team": "Celtics", "away_team": "Lakers",
                        "status": "live", "current_odds": { "home_probability": 0.62 },
                        "home_team_data": { "abbreviation": "BOS" },
                        "away_team_data": { "abbreviation": "LAL" } } } ] }
        """)
        let story = try XCTUnwrap(WatchMarquee.marquee(from: feed, now: now))
        XCTAssertEqual(story.id, "event-55")
        XCTAssertEqual(story.badge, .live)
    }

    // MARK: - My Teams: a finished game must not advertise a start time

    private func gameCard(id: Int, status: String) -> String {
        """
        { "type": "event", "score": 80,
          "data": { "id": \(id), "home_team": "Boston Celtics",
                    "away_team": "Los Angeles Lakers", "status": "\(status)",
                    "commence_time": "2026-07-27T02:00:00Z",
                    "home_score": 104, "away_score": 99,
                    "current_odds": { "home_probability": 0.62 },
                    "home_team_data": { "abbreviation": "BOS" },
                    "away_team_data": { "abbreviation": "LAL" } } }
        """
    }

    func testSettledTeamGameShowsNoStartText() throws {
        let feed = try items("""
        { "items": [ \(gameCard(id: 1, status: "completed")),
                     \(gameCard(id: 2, status: "closed")) ] }
        """)
        let games = WatchMarquee.teamGames(from: feed)
        XCTAssertEqual(games.count, 2)
        for game in games {
            XCTAssertFalse(game.live)
            XCTAssertNil(game.startText,
                         "a finished game must not render a forward-looking tip-off time")
        }
    }

    func testUpcomingTeamGameKeepsItsStartText() throws {
        let feed = try items("{ \"items\": [\(gameCard(id: 3, status: "scheduled"))] }")
        let game = try XCTUnwrap(WatchMarquee.teamGames(from: feed).first)
        XCTAssertFalse(game.live)
        XCTAssertNotNil(game.startText)
    }

    func testLiveTeamGameKeepsItsClockAndNoStartText() throws {
        let feed = try items("{ \"items\": [\(gameCard(id: 4, status: "live"))] }")
        let game = try XCTUnwrap(WatchMarquee.teamGames(from: feed).first)
        XCTAssertTrue(game.live)
        XCTAssertNil(game.startText)
    }

    // MARK: - Containment: one bad card never takes its siblings

    func testMalformedSiblingsDoNotRemoveHealthyOpenMarkets() throws {
        let feed = try items("""
        { "items": [ null, "junk", 7,
                     { "type": "futures", "score": 10, "data": { "name": "no id" } },
                     \(futuresCard(id: 1, status: "\"resolved\"")),
                     \(futuresCard(id: 2, resolutionDate: "\"\(future)\"")) ] }
        """)
        XCTAssertEqual(
            WatchGuessPool.buildQuestions(from: feed, now: now).map { $0.id }, [2])
    }
}
