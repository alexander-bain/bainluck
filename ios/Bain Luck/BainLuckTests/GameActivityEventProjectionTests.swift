import XCTest
@testable import Bain_Luck

@MainActor
final class GameActivityEventProjectionTests: XCTestCase {
    private func event(status: String = "live", hero: Double = 0.64, current: Double = 0.64, away: Double? = nil,
                       heroAway: Double? = nil, extra: String = "") throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":101,"home_team":"Giants","away_team":"Dodgers","sport":"baseball_mlb",
         "status":"\(status)","commence_time":"2026-10-05T12:00:00Z","home_score":4,"away_score":2,
         "hero_probability":\(hero),"hero_probability_away":\(heroAway ?? (1 - hero)),
         "hero_probability_observed_at":"2026-10-05T12:00:00Z",\(extra)
         "current_odds":{"home_probability":\(current),"away_probability":\(away ?? (1 - current)),
                         "captured_at":"2026-10-05T12:01:00Z"}}
        """.utf8))
    }

    /// #10864 — a pushed frame moves the hero to its own `p` and clock and derives
    /// away as `1 - p`, leaving the served away behind. Its clock still dates the
    /// pair, so a live game's updates are not all sent stale.
    func testPushedFramesDerivedPairKeepsTheFramesClock() throws {
        let reading = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(
            for: event(hero: 0.70, current: 0.70, heroAway: 0.32)))
        XCTAssertEqual(reading.homeRenderedPercent, 70)
        XCTAssertEqual(reading.awayRenderedPercent, 30)
        XCTAssertNotNil(reading.probabilityObservedAt)
    }

    /// #10864 — the matchup layout's badge, colour and period come from the served
    /// teams and ESPN period; a period that is itself a clock is never frozen in.
    func testMatchupFieldsComeFromServedTeamsAndAPeriodThatIsNotAClock() throws {
        let teams = """
         "home_team_data":{"abbreviation":"SF","primary_color":"fd5a1e"},
         "away_team_data":{"abbreviation":"LAD","primary_color":"#005A9C"},
        """
        let quarter = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(
            for: event(extra: teams + #""espn":{"period":"4:49 - 1st Quarter","game_clock":"4:49"},"#)))
        XCTAssertEqual(quarter.homeAbbreviation, "SF")
        XCTAssertEqual(quarter.awayAbbreviation, "LAD")
        XCTAssertEqual(quarter.homeColorHex, "#FD5A1E")
        XCTAssertEqual(quarter.awayColorHex, "#005A9C")
        XCTAssertEqual(quarter.periodLabel, "Q1")
        let minute = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(
            for: event(extra: #""espn":{"period":"67'","game_clock":"67'"},"#)))
        XCTAssertNil(minute.periodLabel, "A soccer minute is a clock and would freeze")
        let final = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(
            for: event(status: "completed", extra: #""espn":{"period":"Final","game_clock":"0:00"},"#)))
        XCTAssertNil(final.periodLabel)
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
        XCTAssertNil(GameActivitySnapshot.liveActivityReading(for: try event(status: "scheduled")))
    }

    func testFutureSuspendedGameDoesNotOfferStartBeforeKickoff() throws {
        let kickoff = try XCTUnwrap("2026-10-05T12:00:00Z".asDate)
        let paused = try event(status: "suspended")
        XCTAssertNil(GameActivitySnapshot.liveActivityReading(for: paused, now: kickoff.addingTimeInterval(-1)))
        let started = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: paused, now: kickoff))
        XCTAssertEqual(started.lifecycle, .suspended)
        XCTAssertNil(started.probabilityText)
    }

    func testFinalSuppressesForecastWithoutInventingANewClock() throws {
        let final = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event(status: "completed")))
        XCTAssertTrue(final.isTerminal)
        XCTAssertNil(final.probabilityText)
        XCTAssertNil(final.scoreObservedAt)
    }

    /// Direction 209 — a finished game carries the page's strict pregame pair
    /// (`prematch_odds` in its served whole percents), never the opening line.
    func testAFinalCarriesTheStrictPregamePairAndNeverTheOpeningLine() throws {
        let prematch = #""prematch_odds":{"home_probability":0.584,"away_probability":0.416,"home_rendered_percent":58,"away_rendered_percent":42,"source":"kalshi"},"#
        let final = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event(status: "completed", extra: prematch)))
        XCTAssertEqual(final.pregameHomePercent, 58)
        XCTAssertEqual(final.pregameAwayPercent, 42)
        XCTAssertEqual(final.sport, "baseball_mlb")
        let opening = #""opening_odds":{"home_probability":0.61,"away_probability":0.39},"#
        let openingOnly = try XCTUnwrap(GameActivitySnapshot.liveActivityReading(for: event(status: "completed", extra: opening)))
        XCTAssertNil(openingOnly.pregameHomePercent, "the opening line is not the pregame chance")
        XCTAssertNil(openingOnly.pregameAwayPercent)
    }
}
