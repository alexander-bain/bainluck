import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class FineAndTennisHeadlinesOvernight5Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T08:00:00Z")!

    private struct StubEventDetailProvider: EventDetailProviding {
        let detail: EventDetail
        let history: EventHistoryResponse
        var markets: GameMarketsResponse? = nil

        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                RelatedFuturesResponse.self,
                from: Data(#"{"event_id":\#(eventId),"home_team":"Home","away_team":"Away","markets":[]}"#.utf8)
            )
        }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                TeamProgressionResponse.self,
                from: Data(#"{"event_id":\#(eventId),"home":null,"away":null}"#.utf8)
            )
        }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse {
            if let markets { return markets }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                GameMarketsResponse.self,
                from: Data(#"{"event_id":\#(eventId),"player_props":[],"period_markets":[],"other_markets":[]}"#.utf8)
            )
        }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse {
            LineMovementResponse(
                eventId: eventId,
                movements: [],
                explanation: nil,
                disagreementExplanation: nil,
                disagreementData: nil,
                context: nil,
                cached: nil,
                createdAt: nil
            )
        }
    }

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    // MARK: - Fixtures

    private func nflAfterFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127051,
          "sport": "americanfootball_nfl",
          "home_team": "New England Patriots",
          "away_team": "Green Bay Packers",
          "commence_time": "2026-11-08T18:00:00Z",
          "completed_at": "2026-11-08T21:14:00Z",
          "status": "completed",
          "home_score": 27,
          "away_score": 45,
          "hero_settled_result": "away",
          "home_team_data": {
            "abbreviation": "NE",
            "primary_color": "#002244",
            "record": "5-12"
          },
          "away_team_data": {
            "abbreviation": "GB",
            "primary_color": "#203731",
            "record": "11-6"
          },
          "prematch_odds": {
            "home_probability": 0.62,
            "away_probability": 0.38,
            "home_rendered_percent": 62,
            "away_rendered_percent": 38,
            "source": "kalshi"
          },
          "pregame_projection": {
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-08T18:00:00Z",
            "earliest_captured_at": "2026-11-08T16:30:00Z",
            "latest_captured_at": "2026-11-08T17:55:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game",
            "projected_home_score": 24.5,
            "projected_away_score": 21.0
          },
          "win_probability_sources": {
            "betting": { "value": 0.62, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.61, "display_name": "Kalshi" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.61, "observed_at": "2026-11-08T17:58:00Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.62, "count": 5, "observed_at": "2026-11-08T17:57:00Z" }
            ]
          }
        }
        """)
    }

    private func mlbAfterFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127052,
          "sport": "baseball_mlb",
          "home_team": "Los Angeles Dodgers",
          "away_team": "Milwaukee Brewers",
          "commence_time": "2026-10-16T00:08:00Z",
          "completed_at": "2026-10-16T03:02:00Z",
          "status": "completed",
          "home_score": 5,
          "away_score": 2,
          "hero_settled_result": "home",
          "home_team_data": {
            "abbreviation": "LAD",
            "primary_color": "#005A9C",
            "record": "98-64"
          },
          "away_team_data": {
            "abbreviation": "MIL",
            "primary_color": "#12284B",
            "record": "93-69"
          },
          "standings_context": {
            "stakes": "NLCS Game 3"
          },
          "box_score_data": {
            "away_period_scores": [0, 1, 0, 0, 0, 1, 0, 0, 0],
            "home_period_scores": [2, 0, 1, 0, 0, 2, 0, 0, null]
          },
          "prematch_odds": {
            "home_probability": 0.61,
            "away_probability": 0.39,
            "home_rendered_percent": 61,
            "away_rendered_percent": 39,
            "source": "blend"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.60, "observed_at": "2026-10-16T00:05:00Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.62, "count": 5, "observed_at": "2026-10-16T00:05:00Z" }
            ]
          }
        }
        """)
    }

    private func soccerDuringFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127053,
          "sport": "soccer_uefa_champs_league",
          "sport_name": "Champions League",
          "home_team": "VfB Stuttgart",
          "away_team": "Olympique Marseille",
          "commence_time": "2026-11-14T06:45:00Z",
          "status": "live",
          "home_score": 1,
          "away_score": 0,
          "home_team_data": {
            "abbreviation": "STU",
            "primary_color": "#E32219",
            "record": "2-1-1"
          },
          "away_team_data": {
            "abbreviation": "OM",
            "primary_color": "#009FE3",
            "record": "2-0-2"
          },
          "current_odds": {
            "home_probability": 0.514,
            "draw_probability": 0.278,
            "away_probability": 0.208,
            "updated_at": "2026-11-14T07:59:40Z"
          },
          "prematch_odds": {
            "home_probability": 0.31,
            "draw_probability": 0.27,
            "away_probability": 0.42,
            "source": "blend"
          },
          "hero_probability": 0.514,
          "hero_probability_away": 0.208,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T07:59:40Z",
          "espn": {
            "period": "2nd Half",
            "game_clock": "64'"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.51, "observed_at": "2026-11-14T07:59:40Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.52, "observed_at": "2026-11-14T07:59:35Z" }
            ]
          }
        }
        """)
    }

    private func mmaBeforeFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127054,
          "sport": "mma_mixed_martial_arts",
          "home_team": "Alexander Volkanovski",
          "away_team": "Ilia Topuria",
          "commence_time": "2026-11-15T05:00:00Z",
          "status": "scheduled",
          "home_team_data": {
            "primary_color": "#1D4ED8",
            "record": "26-4"
          },
          "away_team_data": {
            "primary_color": "#DC2626",
            "record": "15-0"
          },
          "current_odds": {
            "home_probability": 0.39,
            "away_probability": 0.61,
            "home_rendered_percent": 39,
            "away_rendered_percent": 61,
            "updated_at": "2026-11-14T07:58:00Z"
          },
          "hero_probability": 0.39,
          "hero_probability_away": 0.61,
          "hero_probability_source": "blend",
          "espn": {
            "broadcast": "PPV"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.39, "observed_at": "2026-11-14T07:58:00Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.39, "count": 4, "observed_at": "2026-11-14T07:57:00Z" }
            ]
          }
        }
        """)
    }

    private func mmaDuringFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127055,
          "sport": "mma_mixed_martial_arts",
          "home_team": "Alexander Volkanovski",
          "away_team": "Ilia Topuria",
          "commence_time": "2026-11-14T07:45:00Z",
          "status": "live",
          "home_team_data": {
            "primary_color": "#1D4ED8",
            "record": "26-4"
          },
          "away_team_data": {
            "primary_color": "#DC2626",
            "record": "15-0"
          },
          "current_odds": {
            "home_probability": 0.284,
            "away_probability": 0.716,
            "updated_at": "2026-11-14T07:59:50Z"
          },
          "prematch_odds": {
            "home_probability": 0.39,
            "away_probability": 0.61,
            "home_rendered_percent": 39,
            "away_rendered_percent": 61,
            "source": "blend"
          },
          "hero_probability": 0.284,
          "hero_probability_away": 0.716,
          "hero_probability_source": "blend",
          "espn": {
            "period": "R2",
            "game_clock": "3:12"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.28, "observed_at": "2026-11-14T07:59:50Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.29, "observed_at": "2026-11-14T07:59:45Z" }
            ]
          }
        }
        """)
    }

    private func mmaAfterFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127056,
          "sport": "mma_mixed_martial_arts",
          "home_team": "Alexander Volkanovski",
          "away_team": "Ilia Topuria",
          "commence_time": "2026-11-09T05:00:00Z",
          "completed_at": "2026-11-09T05:18:00Z",
          "status": "completed",
          "hero_settled_result": "away",
          "home_team_data": {
            "primary_color": "#1D4ED8",
            "record": "26-5"
          },
          "away_team_data": {
            "primary_color": "#DC2626",
            "record": "16-0"
          },
          "prematch_odds": {
            "home_probability": 0.39,
            "away_probability": 0.61,
            "home_rendered_percent": 39,
            "away_rendered_percent": 61,
            "source": "blend"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.39, "observed_at": "2026-11-09T04:58:00Z" }
            ]
          }
        }
        """)
    }

    private func tennisDuringFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127057,
          "sport": "tennis_atp_paris_masters",
          "sport_name": "ATP Tour",
          "home_team": "Alex Michelsen",
          "away_team": "Francisco Cerundolo",
          "commence_time": "2026-11-14T06:30:00Z",
          "status": "live",
          "home_score": 0,
          "away_score": 1,
          "home_team_data": {
            "primary_color": "#1D4ED8"
          },
          "away_team_data": {
            "primary_color": "#C2410C"
          },
          "current_odds": {
            "home_probability": 0.316,
            "away_probability": 0.684,
            "updated_at": "2026-11-14T07:59:50Z"
          },
          "prematch_odds": {
            "home_probability": 0.45,
            "away_probability": 0.55,
            "home_rendered_percent": 45,
            "away_rendered_percent": 55,
            "source": "blend"
          },
          "hero_probability": 0.316,
          "hero_probability_away": 0.684,
          "hero_probability_source": "blend",
          "espn": {
            "period": "2nd Set",
            "game_clock": "0:00"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.32, "observed_at": "2026-11-14T07:59:50Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.31, "observed_at": "2026-11-14T07:59:45Z" }
            ]
          }
        }
        """)
    }

    private func makeHistory(event: EventDetail, homeProb: Double) throws -> EventHistoryResponse {
        let awayProb = max(0.0, min(1.0, 1.0 - homeProb))
        return try decodeHistory("""
        {
          "event_id": \(event.id),
          "home_team": "\(event.homeTeam)",
          "away_team": "\(event.awayTeam)",
          "history": [
            { "timestamp": "2026-11-14T06:30:00Z", "home_probability": 0.50, "away_probability": 0.50, "source": "aggregate" },
            { "timestamp": "2026-11-14T07:15:00Z", "home_probability": \((homeProb + 0.50) / 2.0), "away_probability": \((awayProb + 0.50) / 2.0), "source": "aggregate" },
            { "timestamp": "2026-11-14T07:59:00Z", "home_probability": \(homeProb), "away_probability": \(awayProb), "source": "aggregate" }
          ]
        }
        """)
    }

    // MARK: - Unit Tests

    func testNFLAfterHeadlineAlignsPregameChancesAndFinalScoresInTwoRows() throws {
        let event = try nflAfterFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: event, now: fixedNow), .nflAfterGame)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: nil,
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.finalColumnHeaders?.pregame, "Pregame")
        XCTAssertEqual(model.finalColumnHeaders?.finalLabel, "Final")
        XCTAssertEqual(model.away.shortName, "Packers")
        XCTAssertEqual(model.away.won, true)
        XCTAssertEqual(model.away.pregameChanceText, "38%")
        XCTAssertEqual(model.away.finalResultText, "45")
        XCTAssertEqual(model.away.secondarySublineText, "11-6 · Proj. 21")
        XCTAssertEqual(model.home.shortName, "Patriots")
        XCTAssertEqual(model.home.won, false)
        XCTAssertEqual(model.home.pregameChanceText, "62%")
        XCTAssertEqual(model.home.finalResultText, "27")
        XCTAssertEqual(model.home.secondarySublineText, "5-12 · Proj. 25")
        XCTAssertFalse(model.showsBottomBar)
        XCTAssertFalse(model.showsEkg)
        XCTAssertFalse(model.plainMetaText?.lowercased().contains("settled") ?? false)
    }

    func testMLBAfterHeadlineUsesInningsCountAndPregameFinalColumns() throws {
        let event = try mlbAfterFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: event, now: fixedNow), .mlbAfterGame)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: nil,
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.plainMetaText, "MLB · Final · 9 Innings")
        XCTAssertEqual(model.finalColumnHeaders?.pregame, "Pregame")
        XCTAssertEqual(model.finalColumnHeaders?.finalLabel, "Final")
        XCTAssertEqual(model.away.shortName, "Brewers")
        XCTAssertEqual(model.away.won, false)
        XCTAssertEqual(model.away.pregameChanceText, "39%")
        XCTAssertEqual(model.away.finalResultText, "2")
        XCTAssertEqual(model.away.secondarySublineText, "93-69 · NLCS Game 3")
        XCTAssertEqual(model.home.shortName, "Dodgers")
        XCTAssertEqual(model.home.won, true)
        XCTAssertEqual(model.home.pregameChanceText, "61%")
        XCTAssertEqual(model.home.finalResultText, "5")
        XCTAssertTrue(model.showsRowDivider)
        XCTAssertFalse(model.showsBottomBar)
    }

    func testSoccerDuringHeadlineShowsLiveScorePillThreeWayTenthsAndSinglePregameHeader() throws {
        let event = try soccerDuringFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: event, now: fixedNow), .soccerDuringGame)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: "64'",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.liveBadgeText, "LIVE · 64'")
        XCTAssertEqual(model.leagueLabel, "Champions League")
        XCTAssertTrue(model.showsEkg)
        let threeWay = try XCTUnwrap(model.soccerThreeWay)
        XCTAssertEqual(threeWay.centerTagText, "1 \u{2013} 0")
        XCTAssertTrue(threeWay.isScorePill)
        XCTAssertEqual(threeWay.homeBox.mainText, "51.4%")
        XCTAssertEqual(threeWay.drawBox.mainText, "27.8%")
        XCTAssertEqual(threeWay.awayBox.mainText, "20.8%")
        XCTAssertEqual(threeWay.pregameHeader, "Pregame")
        XCTAssertEqual(threeWay.homeBox.pregameChanceText, "31%")
        XCTAssertEqual(threeWay.drawBox.pregameChanceText, "27%")
        XCTAssertEqual(threeWay.awayBox.pregameChanceText, "42%")
        XCTAssertTrue(threeWay.showsBottomBar)
    }

    func testMMAHeadlinesCoverBeforeDuringAfterWithoutCornerLabels() throws {
        let before = try mmaBeforeFixture()
        let during = try mmaDuringFixture()
        let after = try mmaAfterFixture()

        XCTAssertEqual(EventSportHeadlines12472.kind(for: before, now: fixedNow), .mmaBeforeGame)
        XCTAssertEqual(EventSportHeadlines12472.kind(for: during, now: fixedNow), .mmaDuringGame)
        XCTAssertEqual(EventSportHeadlines12472.kind(for: after, now: fixedNow), .mmaAfterGame)

        let beforeModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: before,
                awayFullName: before.awayTeam,
                homeFullName: before.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(beforeModel.away.shortName, "Topuria")
        XCTAssertEqual(beforeModel.home.shortName, "Volkanovski")
        XCTAssertEqual(beforeModel.away.winChanceText, "61%")
        XCTAssertEqual(beforeModel.home.winChanceText, "39%")

        let duringModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: during,
                awayFullName: during.awayTeam,
                homeFullName: during.homeTeam,
                liveStatusText: "R2 3:12",
                hasScore: false,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(duringModel.liveBadgeText, "LIVE · R2 3:12")
        XCTAssertEqual(duringModel.liveColumnHeaders?.pregame, "Pregame")
        XCTAssertEqual(duringModel.liveColumnHeaders?.now, "Now")
        XCTAssertNil(duringModel.liveColumnHeaders?.score)
        XCTAssertEqual(duringModel.away.winChanceText, "71.6%")
        XCTAssertEqual(duringModel.home.winChanceText, "28.4%")

        let afterModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: after,
                awayFullName: after.awayTeam,
                homeFullName: after.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(afterModel.finalColumnHeaders?.pregame, "Pregame")
        XCTAssertEqual(afterModel.finalColumnHeaders?.finalLabel, "Result")
        XCTAssertEqual(afterModel.away.won, true)
        XCTAssertEqual(afterModel.away.finalResultText, "Won")
        XCTAssertEqual(afterModel.home.won, false)
        XCTAssertEqual(afterModel.home.finalResultText, "Lost")
        XCTAssertFalse(afterModel.showsBottomBar)
    }

    func testTennisDuringHeadlineIsScoreFirstWithSetColumnsAndClockParsedPoints() throws {
        let event = try tennisDuringFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: event, now: fixedNow), .tennisDuringGame)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: "Set 2",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.liveBadgeText, "LIVE · Set 2")
        XCTAssertEqual(model.leagueLabel, "ATP")
        XCTAssertEqual(model.away.shortName, "Cerundolo")
        XCTAssertEqual(model.home.shortName, "Michelsen")

        let scoreFirst = try XCTUnwrap(model.tennisScoreFirst)
        XCTAssertEqual(scoreFirst.setColumns.map(\.header), ["Sets"])
        XCTAssertEqual(scoreFirst.setColumns.map(\.awayValue), ["1"])
        XCTAssertEqual(scoreFirst.setColumns.map(\.homeValue), ["0"])
        XCTAssertNil(scoreFirst.pointsColumn)
        XCTAssertEqual(scoreFirst.pregameHeader, "Pregame")
        XCTAssertEqual(scoreFirst.nowHeader, "Now")
        XCTAssertEqual(model.away.pregameChanceText, "55%")
        XCTAssertEqual(model.home.pregameChanceText, "45%")
        XCTAssertEqual(model.away.winChanceText, "68.4%")
        XCTAssertEqual(model.home.winChanceText, "31.6%")

        // When box_score_data period scores and a tennis point-pair game_clock are served,
        // S1 / S2 columns and clock-parsed Pts render in place of Sets.
        let perSetAndPtsEvent = try decodeEvent("""
        {
          "id": 9127059,
          "sport": "tennis_atp_paris_masters",
          "sport_name": "ATP Tour",
          "home_team": "Alex Michelsen",
          "away_team": "Francisco Cerundolo",
          "commence_time": "2026-11-14T06:30:00Z",
          "status": "live",
          "home_score": 0,
          "away_score": 1,
          "box_score_data": {
            "away_period_scores": [6, 3],
            "home_period_scores": [4, 4]
          },
          "current_odds": {
            "home_probability": 0.316,
            "away_probability": 0.684,
            "updated_at": "2026-11-14T07:59:50Z"
          },
          "espn": {
            "period": "2nd Set",
            "game_clock": "30-40"
          }
        }
        """)
        let perSetModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: perSetAndPtsEvent,
                awayFullName: perSetAndPtsEvent.awayTeam,
                homeFullName: perSetAndPtsEvent.homeTeam,
                liveStatusText: "Set 2",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        let perSetScoreFirst = try XCTUnwrap(perSetModel.tennisScoreFirst)
        XCTAssertEqual(perSetScoreFirst.setColumns.map(\.header), ["S1", "S2"])
        XCTAssertEqual(perSetScoreFirst.setColumns.map(\.awayValue), ["6", "3"])
        XCTAssertEqual(perSetScoreFirst.setColumns.map(\.homeValue), ["4", "4"])
        XCTAssertEqual(perSetScoreFirst.pointsColumn?.away, "30")
        XCTAssertEqual(perSetScoreFirst.pointsColumn?.home, "40")
    }

    // MARK: - Hosted Layout & 390 px Render Export

    func testAllOvernight5HeadlinesFitAt390AndAccessibility2AndExportRenders() async throws {
        let nflAfter = try nflAfterFixture()
        let mlbAfter = try mlbAfterFixture()
        let soccerDuring = try soccerDuringFixture()
        let mmaBefore = try mmaBeforeFixture()
        let mmaDuring = try mmaDuringFixture()
        let mmaAfter = try mmaAfterFixture()
        let tennisDuring = try tennisDuringFixture()

        func makeCard(
            _ event: EventDetail,
            liveStatus: String?,
            hasScore: Bool,
            streams: Bool
        ) throws -> EventSportHeadlineCard12472 {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: liveStatus,
                    hasScore: hasScore,
                    numberStreams: streams,
                    now: fixedNow
                )
            )
            let pairColors = TeamTextContrast.cardColors(
                awayHex: event.awayTeamData?.primaryColor,
                homeHex: event.homeTeamData?.primaryColor
            )
            return EventSportHeadlineCard12472(
                model: model,
                colors: pairColors,
                ekgTracker: .empty,
                liveUpdateStatus: event.status == "live" ? .live : .awaitingUpdate,
                displayAsOf: fixedNow,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: event.status == "live",
                lastReceivedAt: fixedNow,
                confirmedAt: fixedNow,
                revealForecast: nil
            )
        }

        let nflCard = try makeCard(nflAfter, liveStatus: nil, hasScore: true, streams: false)
        let mlbCard = try makeCard(mlbAfter, liveStatus: nil, hasScore: true, streams: false)
        let socCard = try makeCard(soccerDuring, liveStatus: "64'", hasScore: true, streams: true)
        let mmaBCard = try makeCard(mmaBefore, liveStatus: nil, hasScore: false, streams: false)
        let mmaDCard = try makeCard(mmaDuring, liveStatus: "R2 3:12", hasScore: false, streams: true)
        let mmaACard = try makeCard(mmaAfter, liveStatus: nil, hasScore: false, streams: false)
        let tenCard = try makeCard(tennisDuring, liveStatus: "Set 2", hasScore: true, streams: true)

        for card in [nflCard, mlbCard, socCard, mmaBCard, mmaDCard, mmaACard, tenCard] {
            for dt in [DynamicTypeSize.large, .accessibility2] {
                let host = hostForMeasurement(card.frame(width: 358), at: dt)
                let fitted = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
                XCTAssertLessThanOrEqual(fitted.width, 358.5)
                XCTAssertGreaterThan(fitted.height, 80)
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_OVERNIGHT5_RENDERS_DIR"],
           !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            func writeHostedPNG<V: View>(
                _ view: V,
                size: CGSize,
                at dt: DynamicTypeSize = .large,
                to url: URL
            ) async throws {
                let host = hostForMeasurement(view.environment(\.colorScheme, .light), at: dt)
                host.overrideUserInterfaceStyle = .light
                host.view.frame = CGRect(origin: .zero, size: size)
                let window: UIWindow
                if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                    window = UIWindow(windowScene: scene)
                } else {
                    window = UIWindow(frame: host.view.frame)
                }
                window.frame = host.view.frame
                window.overrideUserInterfaceStyle = .light
                window.rootViewController = host
                window.isHidden = false
                defer {
                    window.isHidden = true
                    window.rootViewController = nil
                }
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                try await Task.sleep(nanoseconds: 250_000_000)
                let until = Date().addingTimeInterval(0.30)
                repeat {
                    host.view.setNeedsLayout()
                    host.view.layoutIfNeeded()
                    RunLoop.current.run(until: Date().addingTimeInterval(0.015))
                } while Date() < until
                let fmt = UIGraphicsImageRendererFormat()
                fmt.scale = 3.0
                let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                    _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
                }
                if let png = img.pngData() {
                    try png.write(to: url)
                }
            }

            func makeFullPage(_ event: EventDetail, homeProb: Double) async throws -> AnyView {
                let hist = try makeHistory(event: event, homeProb: homeProb)
                let vm = EventDetailViewModel(
                    eventId: event.id,
                    client: StubEventDetailProvider(detail: event, history: hist)
                )
                await vm.load()
                vm.stopRefresh()
                return AnyView(
                    NavigationStack {
                        EventDetailView(eventId: event.id)
                            .withLoadedEventForTest12278(event, viewModel: vm)
                    }
                    .environmentObject(PinManager())
                    .environmentObject(NavigationCoordinator())
                    .frame(width: 390, height: 852)
                    .background(Color(uiColor: .systemGroupedBackground))
                )
            }

            try await writeHostedPNG(
                try await makeFullPage(nflAfter, homeProb: 0.12),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("overnight5-nfl-after-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(soccerDuring, homeProb: 0.514),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("overnight5-soccer-during-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(mlbAfter, homeProb: 0.88),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("overnight5-mlb-after-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(tennisDuring, homeProb: 0.316),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("overnight5-tennis-during-score-first-390x852.png")
            )

            let mmaSheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("MMA · Before a Fight")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    mmaBCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("MMA · During a Fight ('Pregame' + 'Now' Headers)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    mmaDCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("MMA · After a Fight ('Pregame' + 'Result' Headers)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    mmaACard
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let mmaHost = hostForMeasurement(mmaSheet.environment(\.colorScheme, .light), at: .large)
            let mmaHeight = ceil(mmaHost.sizeThatFits(in: CGSize(width: 390, height: 2000)).height)
            try await writeHostedPNG(
                mmaSheet,
                size: CGSize(width: 390, height: mmaHeight),
                to: dirURL.appendingPathComponent("overnight5-mma-states-390.png")
            )

            let overviewSheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("NFL After · Two Rows, Pregame & Final Aligned")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    nflCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("Soccer During · Live Score Pill + 3-Way Tenths + 'Pregame'")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    socCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("MLB After · 9 Innings + Pregame & Final Aligned")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    mlbCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("Tennis During · Score-First (Sets Before Chances)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    tenCard
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let ovHost = hostForMeasurement(overviewSheet.environment(\.colorScheme, .light), at: .large)
            let ovHeight = ceil(ovHost.sizeThatFits(in: CGSize(width: 390, height: 2400)).height)
            try await writeHostedPNG(
                overviewSheet,
                size: CGSize(width: 390, height: ovHeight),
                to: dirURL.appendingPathComponent("overnight5-comparison-sheet-390.png")
            )
        }
    }

    func testLiveSoccerQualifyingViaGameMarketsSuppressesGameInfoOpenedRow() async throws {
        let liveSoccerWithoutOddsDraw = try decodeEvent("""
        {
          "id": 9127599,
          "sport": "soccer_france_ligue_one",
          "sport_name": "Ligue 1",
          "home_team": "Strasbourg",
          "away_team": "Marseille",
          "commence_time": "2026-11-14T06:45:00Z",
          "status": "live",
          "home_score": 1,
          "away_score": 0,
          "current_odds": {
            "home_probability": 0.514,
            "away_probability": 0.208,
            "updated_at": "2026-11-14T07:59:50Z"
          },
          "opening_odds": {
            "home_probability": 0.31,
            "away_probability": 0.42
          },
          "espn": {
            "period": "2nd Half",
            "game_clock": "64'"
          }
        }
        """)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let liveThreeWayGM = try decoder.decode(GameMarketsResponse.self, from: Data("""
        {
          "event_id": 9127599,
          "player_props": [],
          "period_markets": [],
          "other": [
            { "_market_id": 901, "market_name": "Match Winner", "outcome_name": "Strasbourg", "probability": 0.514, "pregame_mark": 0.31, "source": "blend", "observed_at": "2026-11-14T07:59:50Z" },
            { "_market_id": 901, "market_name": "Match Winner", "outcome_name": "Draw", "probability": 0.278, "pregame_mark": 0.27, "source": "blend", "observed_at": "2026-11-14T07:59:50Z" },
            { "_market_id": 901, "market_name": "Match Winner", "outcome_name": "Marseille", "probability": 0.208, "pregame_mark": 0.42, "source": "blend", "observed_at": "2026-11-14T07:59:50Z" }
          ]
        }
        """.utf8))

        XCTAssertFalse(EventSportHeadlines12472.applies(to: liveSoccerWithoutOddsDraw, now: fixedNow))
        XCTAssertTrue(EventSportHeadlines12472.applies(to: liveSoccerWithoutOddsDraw, gameMarkets: liveThreeWayGM, now: fixedNow))

        let hist = try makeHistory(event: liveSoccerWithoutOddsDraw, homeProb: 0.514)
        let vm = EventDetailViewModel(
            eventId: liveSoccerWithoutOddsDraw.id,
            client: StubEventDetailProvider(detail: liveSoccerWithoutOddsDraw, history: hist, markets: liveThreeWayGM)
        )
        await vm.load()
        vm.stopRefresh()

        let page = NavigationStack {
            EventDetailView(eventId: liveSoccerWithoutOddsDraw.id)
                .withLoadedEventForTest12278(liveSoccerWithoutOddsDraw, viewModel: vm)
        }
        .environmentObject(PinManager())
        .environmentObject(NavigationCoordinator())
        .frame(width: 390, height: 2200)

        let host = hostForMeasurement(page.environment(\.colorScheme, .light), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 2200)
        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        try await Task.sleep(nanoseconds: 100_000_000)
        host.view.layoutIfNeeded()

        func collectStrings(from view: UIView) -> [String] {
            var out: [String] = []
            if let label = view.accessibilityLabel, !label.isEmpty { out.append(label) }
            if let value = view.accessibilityValue, !value.isEmpty { out.append(value) }
            if let uil = view as? UILabel, let t = uil.text, !t.isEmpty { out.append(t) }
            for sub in view.subviews { out.append(contentsOf: collectStrings(from: sub)) }
            return out
        }

        let strings = collectStrings(from: host.view)
        XCTAssertFalse(
            strings.contains(where: { $0.localizedCaseInsensitiveContains("opened") }),
            "live soccer page qualifying via gameMarkets must suppress Opened in Game Info: \(strings)"
        )
    }
}
