import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #12616 (Ruling 190-C, 182-A, 187-A, 161-B) — Behavioral and 390px visual proof
/// for the compact Discover single-game card (`NativeEventDiscoverCard` / `DiscoverSingleGameCard190C`).
@MainActor
final class DiscoverSingleGameCard190CTests: XCTestCase {

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func prematch(_ event: FeedEventData) -> PrematchReading? {
        PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)
    }

    // MARK: - 1. 190-C Picture Eligibility & Variant 191 Hold

    func testPictureEligibilityRequiresLiveOrFivePointMoveAndWaitsOn191() throws {
        // Scheduled with 4-point move (45% -> 41% / 55% -> 59%): stays compact (< 5 pts).
        let fourPointMove = try decodeEvent("""
        {"id": 14969886, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "Minnesota Vikings", "home_team": "Green Bay Packers",
         "commence_time": "2026-11-15T18:00:00Z", "status": "scheduled",
         "prematch_odds": {"away_probability": 0.45, "home_probability": 0.55,
                           "away_rendered_percent": 45, "home_rendered_percent": 55, "source": "kalshi"},
         "current_odds": {"away_probability": 0.41, "home_probability": 0.59,
                          "away_rendered_percent": 41, "home_rendered_percent": 59}}
        """)
        XCTAssertEqual(
            DiscoverSingleGameCard190C.swingPoints(event: fourPointMove, prematch: prematch(fourPointMove)) ?? -1,
            4.0,
            accuracy: 0.001
        )
        XCTAssertFalse(DiscoverSingleGameCard190C.qualifiesForPicture190C(event: fourPointMove, prematch: prematch(fourPointMove)))
        XCTAssertFalse(DiscoverSingleGameCard190C.usesPictureLayout(event: fourPointMove, prematch: prematch(fourPointMove), pictureVariant191Adopted: true))

        // Scheduled with >= 5.0-point move (45% -> 39.5% / 55% -> 60.5%): qualifies for picture once 191 is chosen,
        // but defaults to compact (`false`) while 191 is pending.
        let fiveHalfMove = try decodeEvent("""
        {"id": 14969887, "sport": "americanfootball_nfl", "sport_name": "NFL",
         "away_team": "Minnesota Vikings", "home_team": "Green Bay Packers",
         "commence_time": "2026-11-15T18:00:00Z", "status": "scheduled",
         "prematch_odds": {"away_probability": 0.45, "home_probability": 0.55,
                           "away_rendered_percent": 45, "home_rendered_percent": 55, "source": "kalshi"},
         "current_odds": {"away_probability": 0.395, "home_probability": 0.605,
                          "away_rendered_percent": 40, "home_rendered_percent": 60}}
        """)
        XCTAssertTrue(DiscoverSingleGameCard190C.qualifiesForPicture190C(event: fiveHalfMove, prematch: prematch(fiveHalfMove)))
        XCTAssertFalse(DiscoverSingleGameCard190C.usesPictureLayout(event: fiveHalfMove, prematch: prematch(fiveHalfMove)))
        XCTAssertTrue(DiscoverSingleGameCard190C.usesPictureLayout(event: fiveHalfMove, prematch: prematch(fiveHalfMove), pictureVariant191Adopted: true))

        // Live game: always qualifies for picture under 190-C even with 0-point move, held until 191.
        let liveFlat = try decodeEvent("""
        {"id": 15346136, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 54, "home_score": 61,
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.64, "home_probability": 0.36}}
        """)
        XCTAssertTrue(DiscoverSingleGameCard190C.qualifiesForPicture190C(event: liveFlat, prematch: prematch(liveFlat)))
        XCTAssertFalse(DiscoverSingleGameCard190C.usesPictureLayout(event: liveFlat, prematch: prematch(liveFlat)))
        XCTAssertTrue(DiscoverSingleGameCard190C.usesPictureLayout(event: liveFlat, prematch: prematch(liveFlat), pictureVariant191Adopted: true))

        // Finished game: never uses picture layout under 190-C even if current_odds differed by 20 points.
        let finishedBigSwing = try decodeEvent("""
        {"id": 15346137, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-12T18:00:00Z", "status": "completed",
         "away_score": 98, "home_score": 93,
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.90, "home_probability": 0.10}}
        """)
        XCTAssertFalse(DiscoverSingleGameCard190C.qualifiesForPicture190C(event: finishedBigSwing, prematch: prematch(finishedBigSwing)))
        XCTAssertFalse(DiscoverSingleGameCard190C.usesPictureLayout(event: finishedBigSwing, prematch: prematch(finishedBigSwing), pictureVariant191Adopted: true))
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
        let liveModel = DiscoverSingleGameCard190C.build(event: liveNBA, prematch: prematch(liveNBA))
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
        XCTAssertNil(afterModel.bar, "Finished compact Discover card draws no settled probability bar")

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

    // MARK: - 3. 390px Visual Render Export (Atlas Sheet `(a)` States + `.accessibility2`)

    func testExportDiscoverCompact190CRendersAt390px() throws {
        guard let dirPath = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_190C"],
              !dirPath.isEmpty else {
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

        let beforeSoccer3Way = try decodeEvent("""
        {"id": 15333846, "sport": "soccer_uefa_nations_league", "sport_name": "UEFA",
         "away_team": "Greece", "home_team": "Netherlands",
         "commence_time": "2026-11-14T19:45:00Z", "status": "scheduled",
         "away_team_data": {"primary_color": "#0D5EAF"}, "home_team_data": {"primary_color": "#F36C21"},
         "prematch_odds": {"away_probability": 0.19, "home_probability": 0.60, "draw_probability": 0.21, "source": "kalshi"},
         "current_odds": {"away_probability": 0.17, "home_probability": 0.63, "draw_probability": 0.20}}
        """)

        let liveNBA = try decodeEvent("""
        {"id": 15346136, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 54, "home_score": 61,
         "espn": {"period": "Halftime"},
         "away_team_data": {"primary_color": "#007A33"}, "home_team_data": {"primary_color": "#CE1141"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.429, "home_probability": 0.571,
                          "live_projection": {
                              "projected_away_score": 104.5, "projected_home_score": 110.7,
                              "kind": "in_play", "boundary": "commence_time",
                              "boundary_at": "2026-11-13T18:00:00Z",
                              "earliest_confirmed_at": "2026-11-13T18:50:00Z",
                              "latest_captured_at": "2026-11-13T18:51:00Z",
                              "source": "sportsbooks", "basis": "consensus_spread_total",
                              "bookmaker_count": 4, "unit": "points", "period": "full_game"
                          }}}
        """)

        let afterNBA = try decodeEvent("""
        {"id": 15346137, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Boston Celtics", "home_team": "Toronto Raptors",
         "commence_time": "2026-11-12T18:00:00Z", "status": "completed",
         "away_score": 98, "home_score": 93,
         "away_team_data": {"primary_color": "#007A33"}, "home_team_data": {"primary_color": "#CE1141"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"}}
        """)

        let longLiveNBA = try decodeEvent("""
        {"id": 15346199, "sport": "basketball_nba", "sport_name": "NBA",
         "away_team": "Minnesota Timberwolves", "home_team": "Portland Trail Blazers",
         "commence_time": "2026-11-13T18:00:00Z", "status": "live",
         "away_score": 104, "home_score": 98,
         "espn": {"period": "Q4", "game_clock": "6:40"},
         "away_team_data": {"primary_color": "#0C2340"}, "home_team_data": {"primary_color": "#E03A3E"},
         "prematch_odds": {"away_probability": 0.64, "home_probability": 0.36,
                           "away_rendered_percent": 64, "home_rendered_percent": 36, "source": "kalshi"},
         "current_odds": {"away_probability": 0.784, "home_probability": 0.216}}
        """)

        func renderSheet<V: View>(_ content: V, fileName: String, typeSize: DynamicTypeSize) throws {
            let canvas = content
                .padding(16)
                .frame(width: 390)
                .background(Color(white: 0.965))
                .environment(\.colorScheme, .light)
            let host = hostForMeasurement(canvas, at: typeSize)
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 3500))
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
                    feedContext: "Packers moved 4 points from pregame",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                NativeEventDiscoverCard(
                    event: beforeSoccer3Way,
                    feedContext: "Group B top-table decider in Amsterdam",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                NativeEventDiscoverCard(
                    event: liveNBA,
                    feedContext: "Raptors up 7 at halftime from 36% pregame",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                NativeEventDiscoverCard(
                    event: afterNBA,
                    feedContext: "Celtics rallied after trailing 54\u{2013}61 at halftime",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            },
            fileName: "12616-discover-compact-190c-states-390.png",
            typeSize: .large
        )

        try renderSheet(
            VStack(spacing: 14) {
                NativeEventDiscoverCard(
                    event: longLiveNBA,
                    feedContext: "Close fourth-quarter pace",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
                NativeEventDiscoverCard(
                    event: afterNBA,
                    feedContext: "Celtics rallied after trailing 54\u{2013}61 at halftime",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            },
            fileName: "12616-discover-compact-190c-a11y2-390.png",
            typeSize: .accessibility2
        )
    }
}
