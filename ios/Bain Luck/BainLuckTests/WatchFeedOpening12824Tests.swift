#if os(iOS)
import XCTest

final class WatchFeedOpening12824Tests: XCTestCase {
    private func event(source: String?, status: String = "live", id: Int = 51) throws -> WatchFeedItem {
        let sourceField = source.map { "\"hero_probability_source\": \"\($0)\"," } ?? ""
        let json = """
        {"type":"event","score":80,"headline":"Packers rise to 60%",
         "data":{"id":\(id),"home_team":"Green Bay Packers","away_team":"Detroit Lions",
         "status":"\(status)","home_score":7,"away_score":6,"sport":"americanfootball_nfl",
         "espn":{"period":"Q3","game_clock":"2:14"},\(sourceField)
         "current_odds":{"home_probability":0.5996}}}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(WatchFeedItem.self, from: Data(json.utf8))
    }

    func testCachedOpeningKeepsLiveScoreAndClockWithoutAChance() throws {
        let item = try event(source: "opening")
        let game = try XCTUnwrap(item.event)
        XCTAssertEqual(game.currentOdds?.homeProbability, 0.5996)
        XCTAssertNil(game.currentHomeProbability)

        let team = try XCTUnwrap(WatchMarquee.teamGames(from: [item]).first)
        XCTAssertEqual(team.id, 51)
        XCTAssertEqual(team.clock, "Q3 2:14")
        XCTAssertEqual(team.scoreline, "6–7")
        XCTAssertNil(team.split)
    }

    func testOpeningOnlyLiveGameYieldsTheMarqueeToTheBlendedGame() throws {
        let opening = try event(source: "opening")
        let blend = try event(source: "blend", id: 52)
        let story = try XCTUnwrap(WatchMarquee.marquee(from: [opening, blend]))
        XCTAssertEqual(story.id, "event-52")
        XCTAssertEqual(story.bigNumber, 60)
        XCTAssertNil(WatchMarquee.marquee(from: [opening]))
    }

    func testOpeningOnlyScheduledGameDoesNotHeadline() throws {
        let item = try event(source: "opening", status: "scheduled")
        XCTAssertNil(WatchMarquee.marquee(from: [item]))
    }

    func testSettledSourceKeepsMyTeamsFinalAndStaysOffTheMarquee() throws {
        let item = try event(source: "settled")
        XCTAssertTrue(try XCTUnwrap(item.event).isSettled)
        XCTAssertNil(WatchMarquee.marquee(from: [item]))

        let team = try XCTUnwrap(WatchMarquee.teamGames(from: [item]).first)
        XCTAssertEqual(team.resultText, "FINAL · 6–7")
        XCTAssertNil(team.split)
        XCTAssertNil(team.scoreline)
        XCTAssertFalse(team.live)
        XCTAssertNil(team.clock)
        XCTAssertNil(team.startText)
    }

    func testBlendAndUntaggedPayloadsKeepTheirExistingChance() throws {
        for source in ["blend", nil] {
            let item = try event(source: source)
            let story = try XCTUnwrap(WatchMarquee.marquee(from: [item]))
            XCTAssertEqual(story.bigNumber, 60)
            XCTAssertEqual(story.split?.leftPct, 40)
            XCTAssertEqual(story.headline, "Packers rise to 60%")
            XCTAssertEqual(WatchMarquee.teamGames(from: [item]).first?.split?.rightPct, 60)
        }
    }
}
#endif
