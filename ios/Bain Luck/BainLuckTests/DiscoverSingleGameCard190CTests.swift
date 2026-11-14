import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #12616 (Rulings 190-C, 191-A, 182-A, 187-A, 161-B) — Behavioral and 390px visual proof
/// for the Discover single-game card: compact before kickoff (`190-C`) and chart panel
/// under the rows (`191-A`: win-chance line, 50% reference line, labelled ends) during
/// and after a game.
@MainActor
final class DiscoverSingleGameCard190CTests: XCTestCase {

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func prematch(_ event: FeedEventData) -> PrematchReading? {
        PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)
    }

    // MARK: - 1. 191-A Eligibility (Compact Before Kickoff; Picture During & After)

    func testPictureEligibility191ALiveAndFinishedOnly() throws {
        XCTAssertTrue(DiscoverSingleGameCard190C.defaultPictureVariant191Adopted)

        // Scheduled pregame (even with >= 5pt move): stays compact under 191-A.
        let scheduledBigMove = try decodeEvent("""
        {"id": 14969887, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "Minnesota Vikings", "home_team": "Green Bay Packers",
         "commence_time": "2026-11-15T18:00:00Z", "status": "scheduled",
         "prematch_odds": {"away_probability": 0.45, "home_probability": 0.55,
                           "away_rendered_percent": 45, "home_rendered_percent": 55, "source": "kalshi"},
         "current_odds": {"away_probability": 0.33, "home_probability": 0.67,
                          "away_rendered_percent": 33, "home_rendered_percent": 67}}
        """)
        XCTAssertFalse(DiscoverSingleGameCard190C.qualifiesForPicture191A(event: scheduledBigMove))
        XCTAssertFalse(DiscoverSingleGameCard190C.usesPictureLayout(event: scheduledBigMove, prematch: prematch(scheduledBigMove)))

        // Live game: carries the 191-A chart panel under the rows and swaps out the 5pt bar.
        let liveGame = try decodeEvent("""
        {"id": 15346136, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 54, "home_score": 61,
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.429, "home_probability": 0.571}}
        """)
        XCTAssertTrue(DiscoverSingleGameCard190C.qualifiesForPicture191A(event: liveGame))
        XCTAssertTrue(DiscoverSingleGameCard190C.usesPictureLayout(event: liveGame, prematch: prematch(liveGame)))
        let livePictureModel = DiscoverSingleGameCard190C.build(
            event: liveGame,
            prematch: prematch(liveGame),
            usesPictureLayout: true
        )
        XCTAssertNil(livePictureModel.bar, "191-A chart panel replaces the 5pt bar on live games")

        // Finished game: carries the 191-A chart panel under the rows.
        let finishedGame = try decodeEvent("""
        {"id": 15346137, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-12T18:00:00Z", "status": "completed",
         "away_score": 98, "home_score": 93,
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36, "source": "kalshi"}}
        """)
        XCTAssertTrue(DiscoverSingleGameCard190C.qualifiesForPicture191A(event: finishedGame))
        XCTAssertTrue(DiscoverSingleGameCard190C.usesPictureLayout(event: finishedGame, prematch: prematch(finishedGame)))

        // Suspended-and-started & venue-closed-no-winner: stay compact (no chart panel).
        let suspendedGame = try decodeEvent("""
        {"id": 15297959, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Miami Heat", "home_team": "Orlando Magic",
         "commence_time": "2026-11-10T00:00:00Z", "status": "suspended",
         "away_score": 41, "home_score": 39}
        """)
        XCTAssertFalse(DiscoverSingleGameCard190C.qualifiesForPicture191A(event: suspendedGame))
        XCTAssertFalse(DiscoverSingleGameCard190C.usesPictureLayout(event: suspendedGame, prematch: prematch(suspendedGame)))

        let closedNoWinner = try decodeEvent("""
        {"id": 15297960, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Miami Heat", "home_team": "Orlando Magic",
         "commence_time": "2026-11-10T00:00:00Z", "status": "suspended",
         "venue_closed_no_winner": true,
         "prematch_odds": {"away_probability": 0.44, "home_probability": 0.56, "source": "kalshi"}}
        """)
        XCTAssertFalse(DiscoverSingleGameCard190C.qualifiesForPicture191A(event: closedNoWinner))

        // Finished game with zero win-probability data: stays compact (never draws an empty chart box).
        let finishedWithoutOdds = try decodeEvent("""
        {"id": 14780563, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "Washington Commanders", "home_team": "San Francisco 49ers",
         "commence_time": "2026-10-20T00:15:00Z", "status": "completed",
         "away_score": 17, "home_score": 23}
        """)
        XCTAssertFalse(DiscoverSingleGameCard190C.qualifiesForPicture191A(event: finishedWithoutOdds))
    }

    // MARK: - 2. Compact Card Columns, 187-A Middle Soccer Draw, #5363 & Settled Bar Omission

    func testCompactModelAcrossBeforeThreeWayLiveAfterAndSuspended() throws {
        // 1. Before (Two-Way NFL)
        let beforeNFL = try decodeEvent("""
        {"id": 14969886, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "Minnesota Vikings", "home_team": "Green Bay Packers",
         "commence_time": "2026-11-15T18:00:00Z", "status": "scheduled",
         "prematch_odds": {"away_probability": 0.45, "home_probability": 0.55,
                           "away_rendered_percent": 45, "home_rendered_percent": 55, "source": "kalshi"},
         "current_odds": {"away_probability": 0.41, "home_probability": 0.59,
                          "away_rendered_percent": 41, "home_rendered_percent": 59,
                          "projected_away_score": 19.6, "projected_home_score": 22.6}}
        """)
        let nflModel = DiscoverSingleGameCard190C.build(event: beforeNFL, prematch: prematch(beforeNFL))
        XCTAssertEqual(nflModel.headers, .init(score: nil, pregame: nil, primary: "Now"), "Before kickoff, show Now only (no Pregame column)")
        XCTAssertEqual(nflModel.rows.map(\.shortName), ["Vikings", "Packers"])
        XCTAssertEqual(nflModel.rows.map(\.pregameText), [nil, nil])
        XCTAssertEqual(nflModel.rows.map(\.primaryCell), [.probability("41%"), .probability("59%")])
        XCTAssertNotNil(nflModel.bar)
        XCTAssertEqual(nflModel.scheduledProjectedLine, "Projected: VIK 20 \u{2013} GBP 23")

        // 2. Before (187-A Three-Way Soccer: Draw in the middle of both rows and bar, Now only before kickoff!)
        let soccerThreeWay = try decodeEvent("""
        {"id": 15333846, "sport": "soccer_uefa_nations_league", "sport_name": "UEFA",
         "away_team": "Greece", "home_team": "Netherlands",
         "commence_time": "2026-11-13T22:45:00Z", "status": "scheduled",
         "prematch_odds": {"away_probability": 0.19, "home_probability": 0.60, "draw_probability": 0.21, "source": "kalshi"},
         "current_odds": {"away_probability": 0.17, "home_probability": 0.63, "draw_probability": 0.20}}
        """)
        let soccerModel = DiscoverSingleGameCard190C.build(event: soccerThreeWay, prematch: prematch(soccerThreeWay))
        XCTAssertEqual(soccerModel.headers, .init(score: nil, pregame: nil, primary: "Now"))
        XCTAssertEqual(soccerModel.rows.map(\.kind), [.away, .draw, .home], "187-A puts Draw in the middle")
        XCTAssertEqual(soccerModel.rows.map(\.shortName), ["Greece", "Draw", "Netherlands"])
        XCTAssertEqual(soccerModel.rows.map(\.pregameText), [nil, nil, nil])
        XCTAssertEqual(soccerModel.rows.map(\.primaryCell), [.probability("17%"), .probability("20%"), .probability("63%")])
        XCTAssertEqual(soccerModel.bar?.drawShare ?? 0, 0.20, accuracy: 0.001)

        // #5363: Two-way complement soccer without explicit drawProbability withholds away (`—`), never `1 - home`.
        let soccerComplementOnly = try decodeEvent("""
        {"id": 15333847, "sport": "soccer_epl", "sport_name": "Premier League",
         "away_team": "Everton", "home_team": "Arsenal",
         "commence_time": "2026-11-15T15:00:00Z", "status": "scheduled",
         "current_odds": {"away_probability": 0.32, "home_probability": 0.68}}
        """)
        let complementModel = DiscoverSingleGameCard190C.build(event: soccerComplementOnly, prematch: prematch(soccerComplementOnly))
        XCTAssertEqual(complementModel.rows.count, 2)
        XCTAssertEqual(complementModel.rows[0].primaryCell, .settledDash, "Away complement is withheld on two-way soccer")
        XCTAssertEqual(complementModel.rows[1].primaryCell, .probability("68%"))
        XCTAssertEqual(complementModel.bar?.awayIsWithheld, true)

        // 3. During (Live NBA: Score | Pregame | Now, streaming tenths summing to 100.0%)
        let liveNBA = try decodeEvent("""
        {"id": 15346136, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 54, "home_score": 61,
         "espn": {"period": "Halftime"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.429, "home_probability": 0.571}}
        """)
        let liveModel = DiscoverSingleGameCard190C.build(
            event: liveNBA,
            prematch: prematch(liveNBA),
            usesPictureLayout: false
        )
        XCTAssertEqual(liveModel.headers, .init(score: "Score", pregame: "Pregame", primary: "Now"))
        XCTAssertEqual(liveModel.rows.map(\.scoreText), ["54", "61"])
        XCTAssertEqual(liveModel.rows.map(\.pregameText), ["64%", "36%"])
        XCTAssertEqual(liveModel.rows.map(\.primaryCell), [.probability("42.9%"), .probability("57.1%")])
        XCTAssertNotNil(liveModel.bar)

        // 4. After (Finished NBA: Score | Pregame | Result, Won ✓ on winner, — on loser, NO bar)
        let afterNBA = try decodeEvent("""
        {"id": 15346137, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-12T18:00:00Z", "status": "completed",
         "away_score": 98, "home_score": 93,
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"}}
        """)
        let afterModel = DiscoverSingleGameCard190C.build(event: afterNBA, prematch: prematch(afterNBA))
        XCTAssertEqual(afterModel.headers, .init(score: "Score", pregame: "Pregame", primary: "Result"))
        XCTAssertEqual(afterModel.rows.map(\.scoreText), ["98", "93"])
        XCTAssertEqual(afterModel.rows.map(\.pregameText), ["64%", "36%"])
        XCTAssertEqual(afterModel.rows.map(\.primaryCell), [.won("Won \u{2713}"), .settledDash])
        XCTAssertNil(afterModel.bar, "Finished Discover card draws no settled probability bar")

        // 5. Suspended-and-started (#6010): withholds `Now` and bar even if stale `current_odds` exist.
        let suspendedMatch = try decodeEvent("""
        {"id": 15297959, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Miami Heat", "home_team": "Orlando Magic",
         "commence_time": "2026-11-10T00:00:00Z", "status": "suspended",
         "away_score": 41, "home_score": 39,
         "prematch_odds": {"away_probability": 0.52, "home_probability": 0.48,
                           "away_rendered_percent": 52, "home_rendered_percent": 48, "source": "kalshi"},
         "current_odds": {"away_probability": 0.85, "home_probability": 0.15}}
        """)
        let suspendedModel = DiscoverSingleGameCard190C.build(event: suspendedMatch, prematch: prematch(suspendedMatch))
        XCTAssertNil(suspendedModel.headers.primary, "Suspended game never prints stale live current_odds")
        XCTAssertNil(suspendedModel.bar)
    }

    // MARK: - 3. 191-A Chart Panel Trajectory, Labelled Ends, #5363 & Drift Clipping

    func testPictureChartPanel191ATrajectoryAndLabelledEnds() throws {
        // A. Live NBA (Celtics at Raptors, Raptors 36% pregame -> 57.1% now, +21.1 pts)
        let liveNBA = try decodeEvent("""
        {"id": 15346136, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "away_team_data": {"abbreviation": "BOS"}, "home_team_data": {"abbreviation": "TOR"},
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 54, "home_score": 61,
         "espn": {"period": "Halftime"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.429, "home_probability": 0.571}}
        """)
        let liveHistory = try decodeHistory("""
        {"event_id": 15346136, "home_team": "Toronto Raptors", "away_team": "Boston Celtics",
         "status": "live",
         "history": [],
         "win_prob_history": {
             "kalshi": [
                 {"timestamp": "2026-11-13T18:05:00Z", "home_probability": 0.41},
                 {"timestamp": "2026-11-13T18:25:00Z", "home_probability": 0.49},
                 {"timestamp": "2026-11-13T18:50:00Z", "home_probability": 0.571}
             ]
         },
         "aggregate_line": [
             {"timestamp": "2026-11-12T12:00:00Z", "home_probability": 0.35},
             {"timestamp": "2026-11-13T18:05:00Z", "home_probability": 0.41},
             {"timestamp": "2026-11-13T18:25:00Z", "home_probability": 0.49},
             {"timestamp": "2026-11-13T18:50:00Z", "home_probability": 0.571}
         ]}
        """)
        let liveChart = DiscoverPictureChart191A.build(
            event: liveNBA,
            prematch: prematch(liveNBA),
            history: liveHistory
        )
        XCTAssertEqual(liveChart.perspective, .home)
        XCTAssertEqual(liveChart.plottedTeamShortName, "Raptors")
        XCTAssertEqual(liveChart.plottedTeamCode, "TOR")
        XCTAssertEqual(liveChart.leftEndLabel, "Pregame 36% TOR")
        XCTAssertEqual(liveChart.rightEndLabel, "Now 57.1% TOR (+21.1 pts)")
        XCTAssertEqual(liveChart.points.count, 4, "Multi-day pregame trimmed; kickoff pregame anchor carried onto start edge")
        XCTAssertEqual(liveChart.points.first?.probability ?? -1, 0.36, accuracy: 0.001)
        XCTAssertTrue(liveChart.points.first?.isOpening == true)
        XCTAssertEqual(liveChart.points.last?.probability ?? -1, 0.571, accuracy: 0.001)
        XCTAssertTrue(liveChart.points.last?.isEndpoint == true)

        // B. Finished NBA Road Winner (Celtics 98, Raptors 93: 64% -> 38% -> 100%, clipping post-game drift)
        let afterNBA = try decodeEvent("""
        {"id": 15346137, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "away_team_data": {"abbreviation": "BOS"}, "home_team_data": {"abbreviation": "TOR"},
         "commence_time": "2026-11-12T18:00:00Z", "status": "completed",
         "away_score": 98, "home_score": 93,
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36, "source": "kalshi"}}
        """)
        let afterHistory = try decodeHistory("""
        {"event_id": 15346137, "home_team": "Toronto Raptors", "away_team": "Boston Celtics",
         "status": "completed", "completed_at": "2026-11-12T20:30:00Z",
         "history": [],
         "win_prob_history": {"kalshi": [{"timestamp": "2026-11-12T18:10:00Z", "home_probability": 0.42}]},
         "aggregate_line": [
             {"timestamp": "2026-11-12T18:10:00Z", "home_probability": 0.42},
             {"timestamp": "2026-11-12T19:15:00Z", "home_probability": 0.62},
             {"timestamp": "2026-11-12T20:29:00Z", "home_probability": 0.0},
             {"timestamp": "2026-11-12T22:00:00Z", "home_probability": 0.50}
         ]}
        """)
        let afterChart = DiscoverPictureChart191A.build(
            event: afterNBA,
            prematch: prematch(afterNBA),
            history: afterHistory
        )
        XCTAssertEqual(afterChart.perspective, .away, "Road winner is plotted on two-way finished card")
        XCTAssertEqual(afterChart.leftEndLabel, "Pregame 64% BOS")
        XCTAssertEqual(afterChart.rightEndLabel, "Final \u{00B7} BOS won 98\u{2013}93")
        XCTAssertEqual(afterChart.points.first?.probability ?? -1, 0.64, accuracy: 0.001)
        XCTAssertEqual(afterChart.points[2].probability, 0.38, accuracy: 0.001, "Halftime dip to 38% preserved")
        XCTAssertEqual(afterChart.points.last?.probability ?? -1, 1.0, accuracy: 0.001, "Post-game 22:00Z 50% drift clipped")

        // C. #5271 / #5363 Three-Way Live Soccer: never complements `1 - home` even when away leads!
        let liveSoccer = try decodeEvent("""
        {"id": 15333846, "sport": "soccer_uefa_nations_league", "sport_name": "UEFA",
         "away_team": "Greece", "home_team": "Netherlands",
         "away_team_data": {"abbreviation": "GRE"}, "home_team_data": {"abbreviation": "NED"},
         "commence_time": "2026-11-13T19:45:00Z", "status": "live",
         "away_score": 1, "home_score": 0,
         "espn": {"period": "62'"},
         "prematch_odds": {"away_probability": 0.19, "home_probability": 0.60, "draw_probability": 0.21, "source": "kalshi"},
         "current_odds": {"away_probability": 0.52, "home_probability": 0.22, "draw_probability": 0.26}}
        """)
        let soccerChart = DiscoverPictureChart191A.build(
            event: liveSoccer,
            prematch: prematch(liveSoccer),
            history: nil
        )
        XCTAssertEqual(soccerChart.perspective, .home, "#5363: draw-priced sports always plot home rather than `1 - home`")
        XCTAssertEqual(soccerChart.leftEndLabel, "Pregame 60% NED")
        XCTAssertEqual(soccerChart.rightEndLabel, "Now 22.0% NED (-38.0 pts)")

        // D. Live near-certain cap: never prints `100.0%` on a live card.
        let liveNearCertain = try decodeEvent("""
        {"id": 15346999, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 88, "home_score": 112,
         "prematch_odds": {"away_probability": 0.50, "home_probability": 0.50, "source": "kalshi"},
         "current_odds": {"away_probability": 0.002, "home_probability": 0.998}}
        """)
        let nearCertainChart = DiscoverPictureChart191A.build(
            event: liveNearCertain,
            prematch: prematch(liveNearCertain),
            history: nil
        )
        XCTAssertTrue(nearCertainChart.rightEndLabel.contains(">99%"))
        XCTAssertFalse(nearCertainChart.rightEndLabel.contains("100"))
    }

    // MARK: - 4. 390px Visual Render Export (191-A Picture States + Compact Before + Soccer + `.accessibility2`)

    func testExportDiscoverPicture191ARendersAt390px() throws {
        let dirPath = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_191A"]
            ?? ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_190C"]
        guard let dirPath, !dirPath.isEmpty else {
            return
        }
        let outDir = URL(fileURLWithPath: dirPath, isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let beforeNFL = try decodeEvent("""
        {"id": 14969886, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "Minnesota Vikings", "home_team": "Green Bay Packers",
         "commence_time": "2026-11-15T18:00:00Z", "status": "scheduled",
         "away_team_data": {"primary_color": "#4F2683"}, "home_team_data": {"primary_color": "#203731"},
         "prematch_odds": {"away_probability": 0.45, "home_probability": 0.55,
                           "away_rendered_percent": 45, "home_rendered_percent": 55, "source": "kalshi"},
         "current_odds": {"away_probability": 0.41, "home_probability": 0.59,
                          "away_rendered_percent": 41, "home_rendered_percent": 59,
                          "projected_away_score": 19.6, "projected_home_score": 22.6}}
        """)

        let liveNBA = try decodeEvent("""
        {"id": 15346136, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 41, "home_score": 54,
         "espn": {"period": "Q2", "game_clock": "2:18"},
         "away_team_data": {"primary_color": "#007A33", "abbreviation": "BOS"}, "home_team_data": {"primary_color": "#CE1141", "abbreviation": "TOR"},
         "prematch_odds": {"away_probability": 0.65, "home_probability": 0.35,
                           "away_rendered_percent": 65, "home_rendered_percent": 35, "source": "kalshi"},
         "current_odds": {"away_probability": 0.158, "home_probability": 0.842,
                          "live_projection": {
                              "projected_away_score": 101.5, "projected_home_score": 114.2,
                              "kind": "in_play", "boundary": "commence_time",
                              "boundary_at": "2026-11-13T18:00:00Z",
                              "earliest_confirmed_at": "2026-11-13T18:50:00Z",
                              "latest_captured_at": "2026-11-13T18:51:00Z",
                              "source": "sportsbooks", "basis": "consensus_spread_total",
                              "bookmaker_count": 4, "unit": "points", "period": "full_game"
                          }}}
        """)
        let liveNBAHistory = try decodeHistory("""
        {"event_id": 15346136, "home_team": "Toronto Raptors", "away_team": "Boston Celtics",
         "status": "live", "history": [],
         "win_prob_history": {"kalshi": [{"timestamp": "2026-11-13T18:05:00Z", "home_probability": 0.39}]},
         "aggregate_line": [
             {"timestamp": "2026-11-13T18:04:00Z", "home_probability": 0.39},
             {"timestamp": "2026-11-13T18:12:00Z", "home_probability": 0.46},
             {"timestamp": "2026-11-13T18:20:00Z", "home_probability": 0.43},
             {"timestamp": "2026-11-13T18:30:00Z", "home_probability": 0.58},
             {"timestamp": "2026-11-13T18:40:00Z", "home_probability": 0.73},
             {"timestamp": "2026-11-13T18:50:00Z", "home_probability": 0.842}
         ]}
        """)

        let afterNBAComeback = try decodeEvent("""
        {"id": 15346137, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-12T18:00:00Z", "status": "completed",
         "away_score": 98, "home_score": 93,
         "away_team_data": {"primary_color": "#007A33", "abbreviation": "BOS"}, "home_team_data": {"primary_color": "#CE1141", "abbreviation": "TOR"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"}}
        """)
        let afterNBAComebackHistory = try decodeHistory("""
        {"event_id": 15346137, "home_team": "Toronto Raptors", "away_team": "Boston Celtics",
         "status": "completed", "completed_at": "2026-11-12T20:32:00Z", "history": [],
         "win_prob_history": {"kalshi": [{"timestamp": "2026-11-12T18:08:00Z", "home_probability": 0.44}]},
         "aggregate_line": [
             {"timestamp": "2026-11-12T18:08:00Z", "home_probability": 0.44},
             {"timestamp": "2026-11-12T18:32:00Z", "home_probability": 0.53},
             {"timestamp": "2026-11-12T19:05:00Z", "home_probability": 0.62},
             {"timestamp": "2026-11-12T19:35:00Z", "home_probability": 0.48},
             {"timestamp": "2026-11-12T20:05:00Z", "home_probability": 0.26},
             {"timestamp": "2026-11-12T20:20:00Z", "home_probability": 0.14},
             {"timestamp": "2026-11-12T20:30:00Z", "home_probability": 0.0}
         ]}
        """)

        let afterNBAUpset = try decodeEvent("""
        {"id": 15346115, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Cleveland Cavaliers", "home_team": "New York Knicks",
         "commence_time": "2026-11-12T18:00:00Z", "status": "completed",
         "away_score": 115, "home_score": 107,
         "away_team_data": {"primary_color": "#860038", "abbreviation": "CLE"}, "home_team_data": {"primary_color": "#006BB6", "abbreviation": "NYK"},
         "prematch_odds": {"away_probability": 0.35, "home_probability": 0.65,
                           "away_rendered_percent": 35, "home_rendered_percent": 65, "source": "kalshi"}}
        """)
        let afterNBAUpsetHistory = try decodeHistory("""
        {"event_id": 15346115, "home_team": "New York Knicks", "away_team": "Cleveland Cavaliers",
         "status": "completed", "completed_at": "2026-11-12T20:35:00Z", "history": [],
         "win_prob_history": {"kalshi": [{"timestamp": "2026-11-12T18:10:00Z", "home_probability": 0.64}]},
         "aggregate_line": [
             {"timestamp": "2026-11-12T18:10:00Z", "home_probability": 0.64},
             {"timestamp": "2026-11-12T18:35:00Z", "home_probability": 0.44},
             {"timestamp": "2026-11-12T19:00:00Z", "home_probability": 0.59},
             {"timestamp": "2026-11-12T19:30:00Z", "home_probability": 0.47},
             {"timestamp": "2026-11-12T20:00:00Z", "home_probability": 0.38},
             {"timestamp": "2026-11-12T20:20:00Z", "home_probability": 0.22},
             {"timestamp": "2026-11-12T20:33:00Z", "home_probability": 0.0}
         ]}
        """)

        let liveSoccer3Way = try decodeEvent("""
        {"id": 15333846, "sport": "soccer_uefa_nations_league", "sport_name": "UEFA",
         "away_team": "Greece", "home_team": "Netherlands",
         "commence_time": "2026-11-13T19:45:00Z", "status": "live",
         "away_score": 0, "home_score": 1,
         "espn": {"period": "64'"},
         "away_team_data": {"primary_color": "#0D5EAF", "abbreviation": "GRE"}, "home_team_data": {"primary_color": "#F36C21", "abbreviation": "NED"},
         "prematch_odds": {"away_probability": 0.19, "home_probability": 0.60, "draw_probability": 0.21, "source": "kalshi"},
         "current_odds": {"away_probability": 0.092, "home_probability": 0.768, "draw_probability": 0.14}}
        """)
        let liveSoccerHistory = try decodeHistory("""
        {"event_id": 15333846, "home_team": "Netherlands", "away_team": "Greece",
         "status": "live", "history": [],
         "win_prob_history": {"kalshi": [{"timestamp": "2026-11-13T19:55:00Z", "home_probability": 0.58}]},
         "aggregate_line": [
             {"timestamp": "2026-11-13T19:55:00Z", "home_probability": 0.58},
             {"timestamp": "2026-11-13T20:15:00Z", "home_probability": 0.54},
             {"timestamp": "2026-11-13T20:35:00Z", "home_probability": 0.51},
             {"timestamp": "2026-11-13T20:52:00Z", "home_probability": 0.74},
             {"timestamp": "2026-11-13T21:04:00Z", "home_probability": 0.768}
         ]}
        """)

        let longLiveNBA = try decodeEvent("""
        {"id": 15346199, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Minnesota Timberwolves", "home_team": "Portland Trail Blazers",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 104, "home_score": 98,
         "espn": {"period": "Q4", "game_clock": "6:40"},
         "away_team_data": {"primary_color": "#0C2340", "abbreviation": "MIN"}, "home_team_data": {"primary_color": "#E03A3E", "abbreviation": "POR"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.784, "home_probability": 0.216}}
        """)
        let longLiveHistory = try decodeHistory("""
        {"event_id": 15346199, "home_team": "Portland Trail Blazers", "away_team": "Minnesota Timberwolves",
         "status": "live", "history": [],
         "win_prob_history": {"kalshi": [{"timestamp": "2026-11-13T18:10:00Z", "home_probability": 0.40}]},
         "aggregate_line": [
             {"timestamp": "2026-11-13T18:10:00Z", "home_probability": 0.40},
             {"timestamp": "2026-11-13T18:45:00Z", "home_probability": 0.52},
             {"timestamp": "2026-11-13T19:20:00Z", "home_probability": 0.34},
             {"timestamp": "2026-11-13T19:55:00Z", "home_probability": 0.216}
         ]}
        """)

        func renderSheet<V: View>(_ content: V, fileName: String, typeSize: DynamicTypeSize) throws {
            let canvas = content
                .padding(16)
                .frame(width: 390)
                .background(Color(white: 0.965))
                .environmentObject(PinManager())
                .environment(\.colorScheme, .light)
            let host = hostForMeasurement(canvas, at: typeSize)
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 4500))
            let bounds = CGRect(x: 0, y: 0, width: 390, height: ceil(fitting.height))
            let window = UIWindow(frame: bounds)
            window.rootViewController = host
            host.view.frame = bounds
            window.isHidden = false
            for _ in 0..<8 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.03))
            }
            let format = UIGraphicsImageRendererFormat()
            format.scale = 3.0
            let image = UIGraphicsImageRenderer(bounds: bounds, format: format).image { _ in
                host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
            }
            window.isHidden = true
            try XCTUnwrap(image.pngData()).write(to: outDir.appendingPathComponent(fileName))
        }

        try renderSheet(
            VStack(spacing: 14) {
                NativeEventDiscoverCard(
                    event: beforeNFL,
                    feedContext: "One game, winner-take-all division tiebreaker at Lambeau",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                NativeEventDiscoverCard(
                    event: liveNBA,
                    feedContext: "Toronto has jumped 49 points since tipoff after holding Boston to 14 points this quarter",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: liveNBAHistory
                )
                NativeEventDiscoverCard(
                    event: afterNBAComeback,
                    feedContext: "Celtics rallied after trailing 54\u{2013}61 at halftime",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: afterNBAComebackHistory
                )
                NativeEventDiscoverCard(
                    event: afterNBAUpset,
                    feedContext: "Cleveland won on the road from 35% pregame and gained 4 points in the Central race",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: afterNBAUpsetHistory
                )
            },
            fileName: "12616-discover-191a-states-390.png",
            typeSize: .large
        )

        try renderSheet(
            VStack(spacing: 14) {
                NativeEventDiscoverCard(
                    event: liveSoccer3Way,
                    feedContext: "Netherlands jumped 17 points after opening the scoring in the 58th minute",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: liveSoccerHistory
                )
                NativeEventDiscoverCard(
                    event: longLiveNBA,
                    feedContext: "Close fourth-quarter pace",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: longLiveHistory
                )
            },
            fileName: "12616-discover-191a-soccer-and-a11y2-390.png",
            typeSize: .accessibility2
        )
    }
}
