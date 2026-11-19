import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Ruling 221 (`#12538#issuecomment-6934721648`, Fable `#12779#issuecomment-6934722042`):
/// When a team's primary colour fails the 3:1 contrast floor on a dark background
/// (widgets in dark mode, Watch faces, dark-mode surfaces), `TeamTextContrast` uses:
/// 1. the team's secondary colour if present and readable (`>= 3.0:1`),
/// 2. otherwise a lightened version of its primary colour (preserving hue),
/// 3. falling back to the slot default ONLY when no valid colour exists (or under Ruling 197
///    when two teams in the same hue family clash with no usable secondary).
@MainActor
final class Ruling221DarkTeamContrastTests: XCTestCase {

    private let darkLum = TeamTextContrast.darkSurfaceLuminance
    private let pacific = TimeZone(identifier: "America/Los_Angeles")!
    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-16T19:15:00Z")!
    private let freshStamp = "2026-11-16T19:14:00Z"

    private func decodeWidgetEvent(_ json: String) throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(json.utf8)
        )
    }

    // MARK: - 1. Core Ruling 221 Solver in TeamTextContrast

    func testRavensAndDarkPrimariesUseReadableSecondaryElseLightenedPrimary() {
        // Baltimore Ravens (#241773 purple fails 3:1 on dark; #9E7C0C gold clears 3:1) -> gold #9E7C0C
        XCTAssertFalse(TeamTextContrast.readableOnSurface("#241773", surfaceLuminance: darkLum))
        XCTAssertTrue(TeamTextContrast.readableOnSurface("#9E7C0C", surfaceLuminance: darkLum))
        XCTAssertEqual(
            TeamTextContrast.usableOnDarkSurface(primaryHex: "#241773", secondaryHex: "#9E7C0C", surfaceLuminance: darkLum),
            "#9E7C0C"
        )

        // Ravens without a readable secondary (nil or #000000 black) -> lightened purple (#6450DC), NEVER grey!
        for unreadableSecondary in [nil, "", "#000000", "#101820"] {
            let resolved = TeamTextContrast.usableOnDarkSurface(
                primaryHex: "#241773",
                secondaryHex: unreadableSecondary,
                surfaceLuminance: darkLum
            )
            XCTAssertNotNil(resolved)
            XCTAssertNotEqual(resolved, ProbabilityBarPalette.awayDefault)
            XCTAssertTrue(
                TeamTextContrast.readableOnSurface(resolved, surfaceLuminance: darkLum),
                "Lightened Ravens purple \(String(describing: resolved)) must clear 3.0:1 on dark"
            )
            XCTAssertEqual(
                ProbabilityBarPalette.colorHueFamily(resolved),
                .purple,
                "Lightened Ravens primary \(String(describing: resolved)) must preserve purple hue family"
            )
        }

        // Already-readable primaries on dark (Chiefs #E31837, Lions #0076B6, Steelers #FFB612) stay untouched
        for bright in ["#E31837", "#0076B6", "#FFB612", "#FB4F14"] {
            XCTAssertEqual(
                TeamTextContrast.usableOnDarkSurface(primaryHex: bright, secondaryHex: "#FFFFFF", surfaceLuminance: darkLum),
                bright
            )
        }

        // Absent / malformed primary with no readable secondary -> nil (so palette slot default applies)
        for absent in [nil, "", "not-a-color", "#FFF"] {
            XCTAssertNil(
                TeamTextContrast.usableOnDarkSurface(primaryHex: absent, secondaryHex: nil, surfaceLuminance: darkLum)
            )
        }
    }

    func testDarkSurfacePairCombinesRuling221WithRuling197ClashSeparation() {
        // 1. Ravens (#241773 + gold #9E7C0C) at Chiefs (#E31837): gold vs red -> (#9E7C0C, #E31837)
        let ravensChiefs = TeamTextContrast.darkSurfaceColorHexes(
            awayHex: "#241773",
            homeHex: "#E31837",
            awaySecondaryHex: "#9E7C0C",
            surfaceLuminance: darkLum
        )
        XCTAssertEqual(ravensChiefs.away, "#9E7C0C")
        XCTAssertEqual(ravensChiefs.home, "#E31837")

        // 2. Ravens (#241773 + gold #9E7C0C) at Steelers (#FFB612 gold):
        // Ravens' gold secondary clashes with Steelers' gold -> Ravens uses lightened purple instead of grey!
        let ravensSteelers = TeamTextContrast.darkSurfaceColorHexes(
            awayHex: "#241773",
            homeHex: "#FFB612",
            awaySecondaryHex: "#9E7C0C",
            surfaceLuminance: darkLum
        )
        XCTAssertEqual(ravensSteelers.home, "#FFB612")
        XCTAssertEqual(ProbabilityBarPalette.colorHueFamily(ravensSteelers.away), .purple)
        XCTAssertTrue(TeamTextContrast.readableOnSurface(ravensSteelers.away, surfaceLuminance: darkLum))

        // 3. Gonzaga (#041E42, no secondary) at Duke (#003087, no secondary):
        // Both lighten into .blue -> Ruling 197 keeps Duke's lightened blue and moves Gonzaga to slate #64748B,
        // with quietDarkLineSlateFallbackHex (#94A3B8) clearing 3:1 on the pregame line.
        let gonzagaDuke = TeamTextContrast.darkSurfaceColorHexes(
            awayHex: "#041E42",
            homeHex: "#003087",
            surfaceLuminance: darkLum
        )
        XCTAssertEqual(gonzagaDuke.away, ProbabilityBarPalette.awayDefault)
        XCTAssertEqual(ProbabilityBarPalette.colorHueFamily(gonzagaDuke.home), .blue)
        XCTAssertTrue(TeamTextContrast.readableOnSurface(gonzagaDuke.home, surfaceLuminance: darkLum))
        let darkQuietSlate = TeamTextContrast.quietLineHex(gonzagaDuke.away, surfaceLuminance: darkLum)
        XCTAssertEqual(darkQuietSlate, "#94A3B8")
        XCTAssertTrue(TeamTextContrast.readableOnSurface(darkQuietSlate, surfaceLuminance: darkLum))

        // 4. Exhaustive property across dark/bright/achromatic inputs: every dark-surface pair clears 3:1 and reads apart
        let samples: [(String?, String?)] = [
            (nil, nil), ("#000000", nil), ("#000000", "#A5ACAF"),
            ("#241773", "#9E7C0C"), ("#241773", "#000000"), ("#241773", nil),
            ("#041E42", nil), ("#003087", nil), ("#203731", "#FFB612"), ("#203731", nil),
            ("#E31837", "#FFB81C"), ("#0076B6", "#B0B7BC"), ("#FFFFFF", nil)
        ]
        for (aPri, aSec) in samples {
            for (hPri, hSec) in samples {
                let pair = TeamTextContrast.darkSurfaceColorHexes(
                    awayHex: aPri,
                    homeHex: hPri,
                    awaySecondaryHex: aSec,
                    homeSecondaryHex: hSec,
                    surfaceLuminance: darkLum
                )
                XCTAssertTrue(
                    TeamTextContrast.readableOnSurface(pair.away, surfaceLuminance: darkLum),
                    "Away \(pair.away) failed 3:1 for (\(String(describing: aPri)), \(String(describing: hPri)))"
                )
                XCTAssertTrue(
                    TeamTextContrast.readableOnSurface(pair.home, surfaceLuminance: darkLum),
                    "Home \(pair.home) failed 3:1 for (\(String(describing: aPri)), \(String(describing: hPri)))"
                )
                XCTAssertTrue(
                    ProbabilityBarPalette.distinguishable(pair.away, pair.home),
                    "Pair \(pair) not distinguishable"
                )
            }
        }
    }

    func testColorSchemeRoutingMatchesLightAndDarkContracts() {
        // Light scheme preserves exact cardColorHexes behaviour (#241773 is 12.1:1 on white -> stays #241773)
        let lightPair = TeamTextContrast.surfaceColorHexes(
            awayHex: "#241773",
            homeHex: "#E31837",
            awaySecondaryHex: "#9E7C0C",
            colorScheme: .light
        )
        XCTAssertEqual(lightPair.away, "#241773")
        XCTAssertEqual(lightPair.home, "#E31837")

        // Dark scheme switches #241773 -> #9E7C0C (or lightened purple without secondary)
        let darkPair = TeamTextContrast.surfaceColorHexes(
            awayHex: "#241773",
            homeHex: "#E31837",
            awaySecondaryHex: "#9E7C0C",
            colorScheme: .dark
        )
        XCTAssertEqual(darkPair.away, "#9E7C0C")
        XCTAssertEqual(darkPair.home, "#E31837")

        XCTAssertEqual(
            TeamTextContrast.textHexOnSurface("#241773", secondaryHex: "#9E7C0C", fallback: "#64748B", colorScheme: .light),
            "#241773"
        )
        XCTAssertEqual(
            TeamTextContrast.textHexOnSurface("#241773", secondaryHex: "#9E7C0C", fallback: "#64748B", colorScheme: .dark),
            "#9E7C0C"
        )
        let lightenedNoSec = TeamTextContrast.textHexOnSurface("#241773", secondaryHex: nil, fallback: "#64748B", colorScheme: .dark)
        XCTAssertEqual(ProbabilityBarPalette.colorHueFamily(lightenedNoSec), .purple)
    }

    // MARK: - 2. Widgets & Watch Wrist Tile Wiring

    func testWidgetsAndWatchWristTileApplyRuling221OnDarkSurfaces() throws {
        // 1. SavedGameHeadlineWidgetModel12616 in dark mode: Ravens (#241773 + #9E7C0C) vs Ravens (#241773, no sec)
        let ravensGoldDetail = try decodeWidgetEvent("""
        {
          "id": 822101,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Baltimore Ravens",
          "home_team": "Kansas City Chiefs",
          "away_score": 21,
          "home_score": 17,
          "espn": { "period": "Q3", "game_clock": "06:42" },
          "away_team_data": { "abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#9E7C0C" },
          "home_team_data": { "abbreviation": "KC", "primary_color": "#E31837", "secondary_color": "#FFB81C" },
          "prematch_odds": { "away_probability": 0.54, "home_probability": 0.46 },
          "pregame_projection": {
            "projected_away_score": 27.0,
            "projected_home_score": 24.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T18:00:00Z",
            "earliest_captured_at": "2026-11-16T17:30:00Z",
            "latest_captured_at": "2026-11-16T17:58:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.638,
            "home_probability": 0.362,
            "away_rendered_percent": 64,
            "home_rendered_percent": 36,
            "live_projection": {
              "projected_away_score": 28.0,
              "projected_home_score": 24.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:10:00Z",
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
        let ravensGoldArt = SavedWidgetArt12466.game(ravensGoldDetail)
        let ravensGoldReading = SavedWidgetReadingRules10875.game(ravensGoldDetail, side: nil, now: fixedNow)
        let darkGoldModel = SavedGameHeadlineWidgetModel12616.build(
            reading: ravensGoldReading,
            art: ravensGoldArt,
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            surfaceLuminance: SavedWidgetArt12466.darkSurfaceLuminance,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(darkGoldModel.away.teamInkHex.uppercased(), "#9E7C0C")
        XCTAssertEqual(darkGoldModel.quietAwayInkHex.uppercased(), "#9E7C0C")
        XCTAssertEqual(darkGoldModel.home.teamInkHex.uppercased(), "#E31837")

        let ravensNoSecDetail = try decodeWidgetEvent("""
        {
          "id": 822102,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Baltimore Ravens",
          "home_team": "Detroit Lions",
          "away_score": 20,
          "home_score": 14,
          "espn": { "period": "Q3", "game_clock": "04:10" },
          "away_team_data": { "abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#000000" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.52, "home_probability": 0.48 },
          "current_odds": {
            "away_probability": 0.67,
            "home_probability": 0.33,
            "away_rendered_percent": 67,
            "home_rendered_percent": 33
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let darkLightenedModel = SavedGameHeadlineWidgetModel12616.build(
            reading: SavedWidgetReadingRules10875.game(ravensNoSecDetail, side: nil, now: fixedNow),
            art: SavedWidgetArt12466.game(ravensNoSecDetail),
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            surfaceLuminance: SavedWidgetArt12466.darkSurfaceLuminance,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(ProbabilityBarPalette.colorHueFamily(darkLightenedModel.away.teamInkHex), .purple)
        XCTAssertTrue(
            TeamTextContrast.readableOnSurface(
                darkLightenedModel.away.teamInkHex,
                surfaceLuminance: SavedWidgetArt12466.darkSurfaceLuminance
            )
        )
        XCTAssertEqual(darkLightenedModel.home.teamInkHex.uppercased(), "#0076B6")

        // 2. WatchWristTileModel12616: Ravens with gold -> #9E7C0C; Ravens without readable secondary -> lightened purple
        let kickoff = ISO8601DateFormatter().date(from: "2026-11-17T01:15:00Z")!
        let watchRavensGold = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Baltimore Ravens",
                awayTeam: "Kansas City Chiefs",
                homeServedAbbreviation: "BAL",
                awayServedAbbreviation: "KC",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.58,
                awayProbability: 0.42,
                projectedHomeScore: 27.0,
                projectedAwayScore: 24.0,
                homePrimaryColor: "#241773",
                homeSecondaryColor: "#9E7C0C",
                awayPrimaryColor: "#E31837",
                commenceTime: kickoff
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(watchRavensGold.heroInkHex, "#9E7C0C")

        let watchRavensLightened = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Baltimore Ravens",
                awayTeam: "Detroit Lions",
                homeServedAbbreviation: "BAL",
                awayServedAbbreviation: "DET",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.58,
                awayProbability: 0.42,
                projectedHomeScore: 27.0,
                projectedAwayScore: 23.0,
                homePrimaryColor: "#241773",
                homeSecondaryColor: "#000000",
                awayPrimaryColor: "#0076B6",
                commenceTime: kickoff
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(ProbabilityBarPalette.colorHueFamily(watchRavensLightened.heroInkHex), .purple)
        XCTAssertTrue(
            TeamTextContrast.readableOnSurface(
                watchRavensLightened.heroInkHex,
                surfaceLuminance: WatchWristTileModel12616.watchSurfaceLuminance
            )
        )
    }

    // MARK: - 3. 390 px Contact Sheet (Dark Mode Widgets + Watch + Light Control)

    private func renderHostedSheet<V: View>(_ view: V, width: CGFloat = 390) -> UIImage {
        let wrapped = view
            .frame(width: width)
            .background(Color(hex: "#0F1115"))

        let host = hostForMeasurement(wrapped, at: .large)
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: 6_000))
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: min(max(fitting.height, 400), 2_500))
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.25)
        repeat {
            let nextH = min(max(host.sizeThatFits(in: CGSize(width: width, height: 6_000)).height, 400), 2_500)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: width, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        } while Date() < until

        let format = UIGraphicsImageRendererFormat()
        format.scale = 3.0
        format.opaque = true
        return UIGraphicsImageRenderer(size: host.view.bounds.size, format: format).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    func testExportRuling221DarkModeWidgetsSheet390() throws {
        let kickoff = ISO8601DateFormatter().date(from: "2026-11-17T01:15:00Z")!

        func buildWidget(json: String, scheme: ColorScheme) throws -> (SavedGameHeadlineWidgetModel12616, SavedWidgetReading10875, SavedWidgetArt12466) {
            let detail = try decodeWidgetEvent(json)
            let reading = SavedWidgetReadingRules10875.game(detail, side: nil, now: fixedNow)
            let art = SavedWidgetArt12466.game(detail)
            let lum = scheme == .dark
                ? SavedWidgetArt12466.darkSurfaceLuminance
                : SavedWidgetArt12466.lightSurfaceLuminance
            let model = SavedGameHeadlineWidgetModel12616.build(
                reading: reading,
                art: art,
                clockFooter: "As of 11:14 AM",
                isOffline: false,
                clearsRefreshTrailing: false,
                surfaceLuminance: lum,
                now: fixedNow,
                timeZone: pacific
            )
            return (model, reading, art)
        }

        let ravensChiefsJSON = """
        {
          "id": 822201,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Baltimore Ravens",
          "home_team": "Kansas City Chiefs",
          "away_score": 21,
          "home_score": 17,
          "espn": { "period": "Q3", "game_clock": "06:42" },
          "away_team_data": { "abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#9E7C0C" },
          "home_team_data": { "abbreviation": "KC", "primary_color": "#E31837", "secondary_color": "#FFB81C" },
          "prematch_odds": { "away_probability": 0.54, "home_probability": 0.46 },
          "pregame_projection": {
            "projected_away_score": 27.0,
            "projected_home_score": 24.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T18:00:00Z",
            "earliest_captured_at": "2026-11-16T17:30:00Z",
            "latest_captured_at": "2026-11-16T17:58:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.638,
            "home_probability": 0.362,
            "away_rendered_percent": 64,
            "home_rendered_percent": 36,
            "live_projection": {
              "projected_away_score": 28.0,
              "projected_home_score": 24.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:10:00Z",
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
        """

        let ravensNoSecJSON = """
        {
          "id": 822202,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Baltimore Ravens",
          "home_team": "Detroit Lions",
          "away_score": 20,
          "home_score": 14,
          "espn": { "period": "Q3", "game_clock": "04:10" },
          "away_team_data": { "abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#000000" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.56, "home_probability": 0.44 },
          "pregame_projection": {
            "projected_away_score": 26.0,
            "projected_home_score": 23.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T18:00:00Z",
            "earliest_captured_at": "2026-11-16T17:30:00Z",
            "latest_captured_at": "2026-11-16T17:58:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.672,
            "home_probability": 0.328,
            "away_rendered_percent": 67,
            "home_rendered_percent": 33,
            "live_projection": {
              "projected_away_score": 27.0,
              "projected_home_score": 21.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:10:00Z",
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
        """

        let ravensSteelersSmallJSON = """
        {
          "id": 822203,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-17T01:15:00Z",
          "away_team": "Baltimore Ravens",
          "home_team": "Pittsburgh Steelers",
          "away_team_data": { "abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#9E7C0C" },
          "home_team_data": { "abbreviation": "PIT", "primary_color": "#FFB612" },
          "current_odds": {
            "away_probability": 0.58,
            "home_probability": 0.42,
            "away_rendered_percent": 58,
            "home_rendered_percent": 42,
            "projected_away_score": 24.0,
            "projected_home_score": 20.0
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """

        let (darkGoldM, darkGoldR, darkGoldA) = try buildWidget(json: ravensChiefsJSON, scheme: .dark)
        let (darkLightM, darkLightR, darkLightA) = try buildWidget(json: ravensNoSecJSON, scheme: .dark)
        let (darkSmallM, darkSmallR, darkSmallA) = try buildWidget(json: ravensSteelersSmallJSON, scheme: .dark)
        let (lightCtrlM, lightCtrlR, lightCtrlA) = try buildWidget(json: ravensChiefsJSON, scheme: .light)

        let watchLightened = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Baltimore Ravens",
                awayTeam: "Detroit Lions",
                homeServedAbbreviation: "BAL",
                awayServedAbbreviation: "DET",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.58,
                awayProbability: 0.42,
                projectedHomeScore: 26.0,
                projectedAwayScore: 23.0,
                homePrimaryColor: "#241773",
                homeSecondaryColor: "#000000",
                awayPrimaryColor: "#0076B6",
                commenceTime: kickoff
            ),
            now: fixedNow,
            timeZone: pacific
        )

        @ViewBuilder
        func widgetCard(
            model: SavedGameHeadlineWidgetModel12616,
            reading: SavedWidgetReading10875,
            art: SavedWidgetArt12466,
            size: SavedGameWidgetSize12616,
            scheme: ColorScheme
        ) -> some View {
            let w: CGFloat = size == .small ? 158 : 338
            let lum = scheme == .dark ? SavedWidgetArt12466.darkSurfaceLuminance : SavedWidgetArt12466.lightSurfaceLuminance
            let hexes = art.barHexes(surfaceLuminance: lum)
            let bg = scheme == .dark ? Color(hex: "#1C1C1E") : Color.white
            let border = scheme == .dark ? Color.white.opacity(0.12) : HeadlineStyleTable199.cardBorderInk
            SavedGameHeadlineWidgetView12616(
                model: model,
                size: size,
                awayLogo: nil,
                homeLogo: nil,
                fullColor: true
            ) {
                if let shares = reading.shares {
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
            .padding(14)
            .frame(width: w, height: 158)
            .background(bg, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(border, lineWidth: 1)
            )
            .environment(\.colorScheme, scheme)
        }

        func sectionLabel(_ text: String) -> some View {
            Text(text)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(Color(hex: "#9CA3AF"))
                .fixedSize(horizontal: false, vertical: true)
        }

        let sheet = VStack(alignment: .leading, spacing: 14) {
            Text("Ruling 221 — Dark-Mode Widgets & TeamTextContrast (390 px)")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(Color.white)
                .fixedSize(horizontal: false, vertical: true)

            sectionLabel("1 · Dark Mode Medium: Ravens (#241773) + Readable Gold Secondary (#9E7C0C) @ Chiefs (#E31837)")
            widgetCard(model: darkGoldM, reading: darkGoldR, art: darkGoldA, size: .medium, scheme: .dark)

            sectionLabel("2 · Dark Mode Medium: Ravens (#241773, No Readable Secondary) -> Lightened Purple (#6450DC) @ Lions")
            widgetCard(model: darkLightM, reading: darkLightR, art: darkLightA, size: .medium, scheme: .dark)

            sectionLabel("3 · Dark Small (Ravens @ Steelers Gold -> Lightened Purple) & Watch Tile (Ravens Lightened Purple)")
            HStack(alignment: .center, spacing: 12) {
                widgetCard(model: darkSmallM, reading: darkSmallR, art: darkSmallA, size: .small, scheme: .dark)
                WatchWristTileView12616(model: watchLightened) { EmptyView() }
                    .frame(width: 188)
            }

            sectionLabel("4 · Light Mode Control: Ravens (#241773 Primary Clears 3:1 on White) @ Chiefs (#E31837)")
            widgetCard(model: lightCtrlM, reading: lightCtrlR, art: lightCtrlA, size: .medium, scheme: .light)
        }
        .padding(16)

        let img = renderHostedSheet(sheet, width: 390)
        XCTAssertEqual(img.size.width, 390, accuracy: 0.5)

        if let dir = ProcessInfo.processInfo.environment["EXPORT_RULING_221_DIR"], !dir.isEmpty {
            let outURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)
            try XCTUnwrap(img.pngData()).write(to: outURL.appendingPathComponent("ruling-221-dark-team-contrast-390.png"))
        }
    }
}
