import SwiftUI
import XCTest
@testable import Bain_Luck

@MainActor
final class SavedGameWidgetAndWristTileSat5Tests: XCTestCase {

    private let pacific = TimeZone(identifier: "America/Los_Angeles")!
    // Sat Nov 14, 2026 11:00 AM PT -> 2026-11-14T19:00:00Z
    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T19:00:00Z")!
    private let freshStamp = "2026-11-14T18:58:00Z"

    private func decodeWidgetEvent(_ json: String) throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(json.utf8)
        )
    }

    // MARK: - Home Screen Saved-Game Widget Model Tests

    func testHomeWidgetBeforeDuringAfterColumnsAndFooters() throws {
        // 1. Before: Steelers at Bengals, Sun 10:00 AM PT (2026-11-15T18:00:00Z)
        let beforeEvent = try decodeWidgetEvent("""
        {
          "id": 91001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-15T18:00:00Z",
          "away_team": "Pittsburgh Steelers",
          "home_team": "Cincinnati Bengals",
          "away_team_data": {"abbreviation": "PIT", "primary_color": "#FFB612", "secondary_color": "#101820"},
          "home_team_data": {"abbreviation": "CIN", "primary_color": "#FB4F14", "secondary_color": "#000000"},
          "current_odds": {
            "away_probability": 0.34,
            "home_probability": 0.66,
            "away_rendered_percent": 34,
            "home_rendered_percent": 66,
            "projected_away_score": 20.0,
            "projected_home_score": 24.5
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let beforeReading = SavedWidgetReadingRules10875.game(beforeEvent, side: nil, now: fixedNow)
        let beforeArt = SavedWidgetArt12466.game(beforeEvent)
        let beforeModel = SavedGameHeadlineWidgetModel12616.build(
            reading: beforeReading,
            art: beforeArt,
            clockFooter: "As of 10:58 AM",
            isOffline: false,
            clearsRefreshTrailing: true,
            now: fixedNow,
            timeZone: pacific
        )

        XCTAssertEqual(beforeModel.stage, .before)
        XCTAssertEqual(beforeModel.headers, .init(leading: "Proj.", pregame: nil, primary: "Chance"))
        XCTAssertEqual(beforeModel.away.shortName, "Steelers")
        XCTAssertEqual(beforeModel.home.shortName, "Bengals")
        XCTAssertEqual(beforeModel.away.projectedText, "20")
        XCTAssertEqual(beforeModel.home.projectedText, "25")
        XCTAssertEqual(beforeModel.away.figure, "34%")
        XCTAssertEqual(beforeModel.home.figure, "66%")
        XCTAssertEqual(beforeModel.smallFooter, "Proj. 25–20")
        XCTAssertEqual(beforeModel.mediumFooter, "")
        XCTAssertTrue(TeamTextContrast.readableOnCard(beforeModel.away.teamInkHex))
        XCTAssertTrue(TeamTextContrast.readableOnCard(beforeModel.home.teamInkHex))

        // 2. During: Celtics at 76ers, live Q4 02:14 (213-A + 214-A1: Score · Proj. · Now + grey pregame line)
        let duringEvent = try decodeWidgetEvent("""
        {
          "id": 91002,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "status": "live",
          "commence_time": "2026-11-14T17:30:00Z",
          "away_team": "Boston Celtics",
          "home_team": "Philadelphia 76ers",
          "away_score": 98,
          "home_score": 100,
          "espn": {"period": "Q4", "game_clock": "02:14"},
          "away_team_data": {"abbreviation": "BOS", "primary_color": "#007A33", "secondary_color": "#BA9653"},
          "home_team_data": {"abbreviation": "PHI", "primary_color": "#006BB6", "secondary_color": "#ED174C"},
          "prematch_odds": {"away_probability": 0.49, "home_probability": 0.51},
          "pregame_projection": {
            "projected_away_score": 108.0,
            "projected_home_score": 111.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-14T17:30:00Z",
            "earliest_captured_at": "2026-11-14T16:30:00Z",
            "latest_captured_at": "2026-11-14T17:28:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.412,
            "home_probability": 0.588,
            "away_rendered_percent": 41,
            "home_rendered_percent": 59,
            "live_projection": {
              "projected_away_score": 106.0,
              "projected_home_score": 109.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-14T17:30:00Z",
              "earliest_confirmed_at": "2026-11-14T18:55:00Z",
              "latest_captured_at": "\(freshStamp)",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 5,
              "unit": "points",
              "period": "full_game"
            }
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let duringReading = SavedWidgetReadingRules10875.game(duringEvent, side: nil, now: fixedNow)
        let duringArt = SavedWidgetArt12466.game(duringEvent)
        let duringModel = SavedGameHeadlineWidgetModel12616.build(
            reading: duringReading,
            art: duringArt,
            clockFooter: "As of 10:58 AM",
            isOffline: false,
            clearsRefreshTrailing: true,
            now: fixedNow,
            timeZone: pacific
        )

        XCTAssertEqual(duringModel.stage, .during)
        XCTAssertEqual(duringModel.headers, .init(leading: "Score", pregame: "Proj.", primary: "Now"))
        XCTAssertEqual(duringModel.liveBadgeText, "Q4 02:14")
        XCTAssertEqual(duringModel.away.liveScoreText, "98")
        XCTAssertEqual(duringModel.home.liveScoreText, "100")
        XCTAssertEqual(duringModel.away.liveProjectedText, "106")
        XCTAssertEqual(duringModel.home.liveProjectedText, "109")
        XCTAssertEqual(duringModel.away.figure, "41%")
        XCTAssertEqual(duringModel.home.figure, "59%")
        XCTAssertEqual(duringModel.pregameAwayBarShare ?? 0, 0.49, accuracy: 0.001)
        XCTAssertEqual(duringModel.smallFooter, "Pregame PHI 51%")
        XCTAssertEqual(duringModel.mediumFooter, "Pregame  76ers 51% · projected 111–108")

        // 3. After: Patriots at Packers upset win (Packers 38% pregame, won 45–27)
        let afterEvent = try decodeWidgetEvent("""
        {
          "id": 91003,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-14T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Green Bay Packers",
          "away_score": 27,
          "home_score": 45,
          "hero_settled_result": "home",
          "away_team_data": {"abbreviation": "NE", "primary_color": "#002244", "secondary_color": "#C60C30"},
          "home_team_data": {"abbreviation": "GB", "primary_color": "#203731", "secondary_color": "#FFB612"},
          "prematch_odds": {"away_probability": 0.62, "home_probability": 0.38},
          "current_odds": {"away_probability": 0.0, "home_probability": 1.0}
        }
        """)
        let afterReading = SavedWidgetReadingRules10875.game(afterEvent, side: nil, now: fixedNow)
        XCTAssertNil(afterReading.shares, "Settled game never gets a probability bar")
        let afterArt = SavedWidgetArt12466.game(afterEvent)
        let afterModel = SavedGameHeadlineWidgetModel12616.build(
            reading: afterReading,
            art: afterArt,
            clockFooter: "Final",
            isOffline: false,
            clearsRefreshTrailing: true,
            now: fixedNow,
            timeZone: pacific
        )

        XCTAssertEqual(afterModel.stage, .after)
        XCTAssertEqual(afterModel.headers, .init(leading: nil, pregame: "Pregame", primary: "Final"))
        XCTAssertTrue(afterModel.home.isWinner)
        XCTAssertTrue(afterModel.away.isLoser)
        XCTAssertEqual(afterModel.smallTopTrailing, "Pregame 38%")
        XCTAssertEqual(afterModel.smallFooter, "Won from 38% pregame")
        XCTAssertEqual(afterModel.mediumFooter, "Packers won from a 38% pregame chance")
        XCTAssertTrue(afterModel.footerIsEmeraldCallout)

        // Offline reading preserves the truth caption rather than overriding it.
        let offlineModel = SavedGameHeadlineWidgetModel12616.build(
            reading: duringReading,
            art: duringArt,
            clockFooter: "Offline · 10:58 AM",
            isOffline: true,
            clearsRefreshTrailing: true,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(offlineModel.smallFooter, "Offline · 10:58 AM")
        XCTAssertEqual(offlineModel.mediumFooter, "Offline · 10:58 AM")
    }

    // MARK: - Apple Watch Wrist Tile Model Tests

    func testWatchWristTileSaysOneThingWellAndWithholdsComplementOnSoccer() {
        let sundayMorning = ISO8601DateFormatter().date(from: "2026-11-15T18:00:00Z")!

        // 1. Before (Home leader)
        let beforeHome = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Cincinnati Bengals",
                awayTeam: "Pittsburgh Steelers",
                homeServedAbbreviation: "CIN",
                awayServedAbbreviation: "PIT",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.66,
                awayProbability: 0.34,
                projectedHomeScore: 24.5,
                projectedAwayScore: 20.0,
                homePrimaryColor: "#FB4F14",
                awayPrimaryColor: "#FFB612",
                commenceTime: sundayMorning
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(beforeHome.stage, .before)
        XCTAssertEqual(beforeHome.topMetaText, "SUN 10:00 AM · VS PIT")
        XCTAssertEqual(beforeHome.leaderName, "Bengals")
        XCTAssertEqual(beforeHome.heroFigureText, "66%")
        XCTAssertEqual(beforeHome.supportingLine, "Favored · Proj. 25–20")

        // 2. Before (Away leader + dark navy primary uses contrast-safe gold secondary)
        let beforeAway = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Cincinnati Bengals",
                awayTeam: "Pittsburgh Steelers",
                homeServedAbbreviation: "CIN",
                awayServedAbbreviation: "PIT",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.38,
                awayProbability: 0.62,
                projectedHomeScore: 20.0,
                projectedAwayScore: 24.0,
                homePrimaryColor: "#FB4F14",
                awayPrimaryColor: "#002A5C",
                awaySecondaryColor: "#FFB612",
                commenceTime: sundayMorning
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(beforeAway.topMetaText, "SUN 10:00 AM · AT CIN")
        XCTAssertEqual(beforeAway.leaderName, "Steelers")
        XCTAssertEqual(beforeAway.heroFigureText, "62%")
        XCTAssertEqual(beforeAway.heroInkHex, "#FFB612")
        XCTAssertEqual(beforeAway.supportingLine, "Favored · Proj. 24–20")

        // 3. During (Live edge + score + pregame delta)
        let duringLive = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Philadelphia 76ers",
                awayTeam: "Boston Celtics",
                homeServedAbbreviation: "PHI",
                awayServedAbbreviation: "BOS",
                sportKey: "basketball_nba",
                isLive: true,
                homeScore: 100,
                awayScore: 98,
                homeProbability: 0.588,
                awayProbability: 0.412,
                prematchHomeProbability: 0.51,
                prematchAwayProbability: 0.49,
                homePrimaryColor: "#006BB6",
                homeSecondaryColor: "#60A5FA",
                awayPrimaryColor: "#007A33",
                liveClockText: "Q4 02:14",
                probabilityObservedAt: fixedNow.addingTimeInterval(-45)
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(duringLive.stage, .during)
        XCTAssertEqual(duringLive.liveCapsuleText, "Q4 02:14")
        XCTAssertEqual(duringLive.topMetaText, "PHI 100–98 BOS")
        XCTAssertEqual(duringLive.leaderName, "76ers")
        XCTAssertEqual(duringLive.heroFigureText, "59%")
        XCTAssertEqual(duringLive.supportingLine, "Up 8 points from 51%")

        // 4. After (Upset win: winner's score first + pregame improbability)
        let afterUpset = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Green Bay Packers",
                awayTeam: "New England Patriots",
                homeServedAbbreviation: "GB",
                awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                isFinal: true,
                homeScore: 45,
                awayScore: 27,
                prematchHomeProbability: 0.38,
                prematchAwayProbability: 0.62,
                homePrimaryColor: "#203731",
                awayPrimaryColor: "#002244"
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(afterUpset.stage, .after)
        XCTAssertTrue(afterUpset.showsFinalCheckmark)
        XCTAssertEqual(afterUpset.topMetaText, "FINAL · VS PATRIOTS")
        XCTAssertEqual(afterUpset.leaderName, "Packers")
        XCTAssertEqual(afterUpset.heroFigureText, "45–27")
        XCTAssertEqual(afterUpset.supportingLine, "Won from 38% pregame chance")

        // 5. Draw-priced soccer without draw odds: away is 1 - home complement, so ALWAYS names home!
        let soccerWithheld = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Arsenal FC",
                awayTeam: "Liverpool FC",
                homeServedAbbreviation: "ARS",
                awayServedAbbreviation: "LIV",
                sportKey: "soccer_epl",
                homeProbability: 0.34,
                awayProbability: 0.66, // complement (away + draw) — must NOT be printed as LIV 66%!
                homePrimaryColor: "#EF0107",
                awayPrimaryColor: "#C8102E",
                commenceTime: sundayMorning
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(soccerWithheld.leaderName, "Arsenal")
        XCTAssertEqual(soccerWithheld.heroFigureText, "34%")
        XCTAssertEqual(soccerWithheld.supportingLine, "Home win chance")

        // Women's / reserve designators and leading prefixes stay intact.
        let womensClub = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Arsenal WFC",
                awayTeam: "Chelsea FC Women",
                sportKey: "soccer_england_wsl",
                homeProbability: 0.55,
                commenceTime: sundayMorning
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(womensClub.leaderName, "Arsenal WFC")
        XCTAssertEqual(womensClub.supportingLine, "Favored")

        for copy in [
            beforeHome.supportingLine,
            duringLive.supportingLine,
            afterUpset.supportingLine,
            soccerWithheld.supportingLine
        ] {
            for forbidden in ["opened", "stale", "settled", "venues", "favoured"] {
                XCTAssertFalse(copy.localizedCaseInsensitiveContains(forbidden), copy)
            }
        }
    }

    // MARK: - 390 px Visual Render Export

    func testExportSat5WidgetAndWatchRenders390() throws {
        let env = ProcessInfo.processInfo.environment
        guard let dirPath = env["TEST_RUNNER_BUILDER_C_RENDER_DIR_SAT5"] ?? env["BUILDER_C_RENDER_DIR_SAT5"],
              !dirPath.isEmpty else {
            return
        }
        let outDir = URL(fileURLWithPath: dirPath, isDirectory: true)
        try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

        let sundayMorning = ISO8601DateFormatter().date(from: "2026-11-15T18:00:00Z")!

        let beforeEvent = try decodeWidgetEvent("""
        {
          "id": 91001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-15T18:00:00Z",
          "away_team": "Pittsburgh Steelers",
          "home_team": "Cincinnati Bengals",
          "away_team_data": {"abbreviation": "PIT", "primary_color": "#FFB612", "secondary_color": "#101820"},
          "home_team_data": {"abbreviation": "CIN", "primary_color": "#FB4F14", "secondary_color": "#000000"},
          "current_odds": {
            "away_probability": 0.34,
            "home_probability": 0.66,
            "away_rendered_percent": 34,
            "home_rendered_percent": 66,
            "projected_away_score": 20.0,
            "projected_home_score": 24.5
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let duringEvent = try decodeWidgetEvent("""
        {
          "id": 91002,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "status": "live",
          "commence_time": "2026-11-14T17:30:00Z",
          "away_team": "Boston Celtics",
          "home_team": "Philadelphia 76ers",
          "away_score": 98,
          "home_score": 100,
          "espn": {"period": "Q4", "game_clock": "02:14"},
          "away_team_data": {"abbreviation": "BOS", "primary_color": "#007A33", "secondary_color": "#BA9653"},
          "home_team_data": {"abbreviation": "PHI", "primary_color": "#006BB6", "secondary_color": "#ED174C"},
          "prematch_odds": {"away_probability": 0.49, "home_probability": 0.51},
          "current_odds": {
            "away_probability": 0.412,
            "home_probability": 0.588,
            "away_rendered_percent": 41,
            "home_rendered_percent": 59
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let afterEvent = try decodeWidgetEvent("""
        {
          "id": 91003,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-14T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Green Bay Packers",
          "away_score": 27,
          "home_score": 45,
          "hero_settled_result": "home",
          "away_team_data": {"abbreviation": "NE", "primary_color": "#002244", "secondary_color": "#C60C30"},
          "home_team_data": {"abbreviation": "GB", "primary_color": "#203731", "secondary_color": "#FFB612"},
          "prematch_odds": {"away_probability": 0.62, "home_probability": 0.38},
          "current_odds": {"away_probability": 0.0, "home_probability": 1.0}
        }
        """)

        func makeWidgetModel(_ event: SavedWidgetEventDetail10875, clock: String) -> (SavedGameHeadlineWidgetModel12616, SavedWidgetReading10875, SavedWidgetArt12466) {
            let r = SavedWidgetReadingRules10875.game(event, side: nil, now: fixedNow)
            let a = SavedWidgetArt12466.game(event)
            let m = SavedGameHeadlineWidgetModel12616.build(
                reading: r,
                art: a,
                clockFooter: clock,
                isOffline: false,
                clearsRefreshTrailing: true,
                now: fixedNow,
                timeZone: pacific
            )
            return (m, r, a)
        }

        let (beforeM, beforeR, beforeA) = makeWidgetModel(beforeEvent, clock: "As of 10:58 AM")
        let (duringM, duringR, duringA) = makeWidgetModel(duringEvent, clock: "As of 10:58 AM")
        let (afterM, afterR, afterA) = makeWidgetModel(afterEvent, clock: "Final")

        @ViewBuilder
        func sampleBar(reading: SavedWidgetReading10875, art: SavedWidgetArt12466) -> some View {
            if let shares = reading.shares {
                let hexes = art.barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)
                GeometryReader { geo in
                    let widths = SavedWidgetArt12466.barWidths(shares, total: geo.size.width)
                    HStack(spacing: 2) {
                        Capsule().fill(Color(hex: hexes.away)).frame(width: widths.first)
                        Capsule().fill(Color(hex: hexes.home)).frame(width: widths.second)
                    }
                }
                .frame(height: 5)
            }
        }

        @ViewBuilder
        func widgetFrame(
            model: SavedGameHeadlineWidgetModel12616,
            reading: SavedWidgetReading10875,
            art: SavedWidgetArt12466,
            size: SavedGameWidgetSize12616
        ) -> some View {
            let width: CGFloat = size == .small ? 158 : 338
            SavedGameHeadlineWidgetView12616(
                model: model,
                size: size,
                awayLogo: nil,
                homeLogo: nil,
                fullColor: true
            ) {
                sampleBar(reading: reading, art: art)
            }
            .padding(13)
            .frame(width: width, height: 158)
            .background(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .fill(Color.white)
                    .shadow(color: .black.opacity(0.08), radius: 8, x: 0, y: 3)
            )
            .overlay(alignment: .bottomTrailing) {
                Image(systemName: "arrow.clockwise")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(Color(hex: "#6B7280"))
                    .padding(12)
            }
        }

        func renderPNG<V: View>(_ content: V, fileName: String, dark: Bool = false) throws {
            let canvas = content
                .padding(16)
                .frame(width: 390)
                .background(dark ? Color(hex: "#090A0F") : Color(hex: "#F1F5F9"))
                .environment(\.colorScheme, dark ? .dark : .light)
            let renderer = rendererForMeasurement(canvas)
            renderer.scale = 3.0
            renderer.proposedSize = ProposedViewSize(width: 390, height: nil)
            let image = try XCTUnwrap(renderer.uiImage)
            try XCTUnwrap(image.pngData()).write(to: outDir.appendingPathComponent(fileName))
        }

        try renderPNG(
            VStack(alignment: .leading, spacing: 18) {
                Text("HOME SCREEN SAVED-GAME WIDGETS · SMALL (158×158) & MEDIUM (338×158)")
                    .font(.system(size: 10.5, weight: .bold))
                    .foregroundStyle(Color(hex: "#475569"))

                Text("BEFORE · PROJ. · CHANCE")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Color(hex: "#64748B"))
                widgetFrame(model: beforeM, reading: beforeR, art: beforeA, size: .small)
                widgetFrame(model: beforeM, reading: beforeR, art: beforeA, size: .medium)

                Text("DURING · LIVE SCORE + PREGAME + NOW")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Color(hex: "#64748B"))
                widgetFrame(model: duringM, reading: duringR, art: duringA, size: .small)
                widgetFrame(model: duringM, reading: duringR, art: duringA, size: .medium)

                Text("AFTER · WINNER ✓ + PREGAME + FINAL")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(Color(hex: "#64748B"))
                widgetFrame(model: afterM, reading: afterR, art: afterA, size: .small)
                widgetFrame(model: afterM, reading: afterR, art: afterA, size: .medium)
            },
            fileName: "sat5-home-widgets-small-and-medium-390.png"
        )

        let watchBefore = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Cincinnati Bengals",
                awayTeam: "Pittsburgh Steelers",
                homeServedAbbreviation: "CIN",
                awayServedAbbreviation: "PIT",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.66,
                awayProbability: 0.34,
                projectedHomeScore: 24.5,
                projectedAwayScore: 20.0,
                homePrimaryColor: "#FB4F14",
                awayPrimaryColor: "#FFB612",
                commenceTime: sundayMorning
            ),
            now: fixedNow,
            timeZone: pacific
        )
        let watchDuring = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Philadelphia 76ers",
                awayTeam: "Boston Celtics",
                homeServedAbbreviation: "PHI",
                awayServedAbbreviation: "BOS",
                sportKey: "basketball_nba",
                isLive: true,
                homeScore: 100,
                awayScore: 98,
                homeProbability: 0.588,
                awayProbability: 0.412,
                prematchHomeProbability: 0.51,
                prematchAwayProbability: 0.49,
                homePrimaryColor: "#006BB6",
                homeSecondaryColor: "#60A5FA",
                awayPrimaryColor: "#007A33",
                liveClockText: "Q4 02:14",
                probabilityObservedAt: fixedNow.addingTimeInterval(-45)
            ),
            now: fixedNow,
            timeZone: pacific
        )
        let watchAfter = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Green Bay Packers",
                awayTeam: "New England Patriots",
                homeServedAbbreviation: "GB",
                awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                isFinal: true,
                homeScore: 45,
                awayScore: 27,
                prematchHomeProbability: 0.38,
                prematchAwayProbability: 0.62,
                homePrimaryColor: "#203731",
                awayPrimaryColor: "#002244"
            ),
            now: fixedNow,
            timeZone: pacific
        )
        let watchSoccer = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Arsenal FC",
                awayTeam: "Liverpool FC",
                homeServedAbbreviation: "ARS",
                awayServedAbbreviation: "LIV",
                sportKey: "soccer_epl",
                homeProbability: 0.34,
                awayProbability: 0.66,
                homePrimaryColor: "#EF0107",
                awayPrimaryColor: "#C8102E",
                commenceTime: sundayMorning
            ),
            now: fixedNow,
            timeZone: pacific
        )

        try renderPNG(
            VStack(alignment: .leading, spacing: 14) {
                Text("APPLE WATCH WRIST TILES (41MM · 184 PT) · SAYS ONE THING WELL")
                    .font(.system(size: 10.5, weight: .bold))
                    .foregroundStyle(Color.white.opacity(0.65))

                VStack(alignment: .leading, spacing: 6) {
                    Text("BEFORE · WHO IS FAVORED")
                        .font(.system(size: 9.5, weight: .bold))
                        .foregroundStyle(Color.white.opacity(0.5))
                    WatchWristTileView12616(model: watchBefore) {
                        Image(systemName: "bookmark.fill")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(.orange)
                    }
                    .frame(width: 204)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("DURING · LIVE EDGE + SCORE")
                        .font(.system(size: 9.5, weight: .bold))
                        .foregroundStyle(Color.white.opacity(0.5))
                    WatchWristTileView12616(model: watchDuring) {
                        EmptyView()
                    }
                    .frame(width: 204)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("AFTER · WINNER + UPSET")
                        .font(.system(size: 9.5, weight: .bold))
                        .foregroundStyle(Color.white.opacity(0.5))
                    WatchWristTileView12616(model: watchAfter) {
                        EmptyView()
                    }
                    .frame(width: 204)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("SOCCER · HOME ONLY (41MM · 184 PT)")
                        .font(.system(size: 9.5, weight: .bold))
                        .foregroundStyle(Color.white.opacity(0.5))
                    WatchWristTileView12616(model: watchSoccer) {
                        EmptyView()
                    }
                    .frame(width: 184)
                }
            },
            fileName: "sat5-watch-wrist-tiles-390.png",
            dark: true
        )
    }
}
