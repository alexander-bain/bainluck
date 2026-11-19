import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Fable 3:08 PM PT follow-ups (`#12779#issuecomment-6932124371` + `#12808` `#475569` note):
/// 1. Medium widget during a game follows `213-A` and `214-A1`: `Score · Proj. · Now`,
///    the bar with its pregame tick, and the grey line with team-coloured numbers
///    (`#475569` when Ruling 197 falls back to slate `#64748B`).
/// 2. Projections on the small widget and Watch tile follow `214-A1`: `"Proj. 27–21"`
///    with each number in its team's colour, the favourite's first, and no `"DET"` after it.
/// 3. After a game, the small widget's `"Pregame 58%"` prints in the colour of the
///    team it belongs to.
/// 4. On the calibration screen, `"The curve rebuilds hourly."` and the two
///    `"hourly rebuilds"` sentences become daily (`CalibrationStaleness.swift`), and
///    `"Updated hourly"` is dropped when `generated_at` is missing (`#7612`).
@MainActor
final class WidgetsWatchCalibration214A1Tests: XCTestCase {

    private let pacific = TimeZone(identifier: "America/Los_Angeles")!
    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-16T19:15:00Z")!
    private let freshStamp = "2026-11-16T19:14:00Z"

    private func decodeWidgetEvent(_ json: String) throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(json.utf8)
        )
    }

    private func decodeJSON<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(type, from: Data(json.utf8))
    }

    // MARK: - 1. Medium Widget During (`213-A` + `214-A1` + `#475569` Slate Fallback)

    func testMediumWidgetDuringUsesScoreProjNowPregameTickAndTeamColouredSummary() throws {
        // Distinct pair: Patriots at Lions (`Lions` pregame 58% fav, projected 27–21)
        let distinctDetail = try decodeWidgetEvent("""
        {
          "id": 701001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 17,
          "home_score": 24,
          "espn": { "period": "Q3", "game_clock": "08:14" },
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "pregame_projection": {
            "projected_away_score": 21.0,
            "projected_home_score": 27.0,
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
            "away_probability": 0.338,
            "home_probability": 0.662,
            "away_rendered_percent": 34,
            "home_rendered_percent": 66,
            "live_projection": {
              "projected_away_score": 23.0,
              "projected_home_score": 30.0,
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
        let distinctArt = SavedWidgetArt12466.game(distinctDetail)
        let distinctReading = SavedWidgetReadingRules10875.game(distinctDetail, side: nil, now: fixedNow)
        let distinctModel = SavedGameHeadlineWidgetModel12616.build(
            reading: distinctReading,
            art: distinctArt,
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(distinctModel.headers, .init(leading: "Score", pregame: "Proj.", primary: "Now"))
        XCTAssertEqual(distinctModel.away.liveScoreText, "17")
        XCTAssertEqual(distinctModel.home.liveScoreText, "24")
        XCTAssertEqual(distinctModel.away.liveProjectedText, "23")
        XCTAssertEqual(distinctModel.home.liveProjectedText, "30")
        XCTAssertEqual(distinctModel.pregameAwayBarShare ?? 0, 0.42, accuracy: 0.001)
        XCTAssertEqual(distinctModel.mediumFooter, "Pregame  Lions 58% · projected 27–21")
        XCTAssertEqual(distinctModel.mediumFooterSegments, [
            .init(text: "Pregame", ink: .quietLead),
            .init(text: "  ", ink: .quiet),
            .init(text: "Lions 58%", ink: .homeTeam),
            .init(text: " · projected ", ink: .quiet),
            .init(text: "27", ink: .homeTeam),
            .init(text: "\u{2013}", ink: .quiet),
            .init(text: "21", ink: .awayTeam),
        ])

        // Ruling 197 grey-fallback pair (`Gonzaga @ Duke`, both navy, no secondary):
        // Bar/headline away hex is `#64748B`, while `quietAwayInkHex` darkens to `#475569`!
        let greyFallbackDetail = try decodeWidgetEvent("""
        {
          "id": 701002,
          "sport": "basketball_ncaab",
          "sport_name": "NCAAB",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Gonzaga Bulldogs",
          "home_team": "Duke Blue Devils",
          "away_score": 41,
          "home_score": 38,
          "espn": { "period": "2nd Half", "game_clock": "14:20" },
          "away_team_data": { "abbreviation": "GONZ", "primary_color": "#041E42" },
          "home_team_data": { "abbreviation": "DUKE", "primary_color": "#003087" },
          "prematch_odds": { "away_probability": 0.56, "home_probability": 0.44 },
          "pregame_projection": {
            "projected_away_score": 76.0,
            "projected_home_score": 73.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T18:00:00Z",
            "earliest_captured_at": "2026-11-16T17:30:00Z",
            "latest_captured_at": "2026-11-16T17:58:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 4,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.618,
            "home_probability": 0.382,
            "away_rendered_percent": 62,
            "home_rendered_percent": 38,
            "live_projection": {
              "projected_away_score": 79.0,
              "projected_home_score": 74.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:10:00Z",
              "latest_captured_at": "\(freshStamp)",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 4,
              "unit": "points",
              "period": "full_game"
            }
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let greyArt = SavedWidgetArt12466.game(greyFallbackDetail)
        let greyReading = SavedWidgetReadingRules10875.game(greyFallbackDetail, side: nil, now: fixedNow)
        let greyModel = SavedGameHeadlineWidgetModel12616.build(
            reading: greyReading,
            art: greyArt,
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(greyModel.away.teamInkHex.uppercased(), "#64748B")
        XCTAssertEqual(greyModel.quietAwayInkHex.uppercased(), "#475569", "Pregame line slate fallback darkens to #475569")
        XCTAssertEqual(greyModel.mediumFooter, "Pregame  Gonzaga 56% · projected 76–73")
        XCTAssertEqual(greyModel.mediumFooterSegments[2], .init(text: "Gonzaga 56%", ink: .awayTeam))
        XCTAssertEqual(greyModel.mediumFooterSegments[4], .init(text: "76", ink: .awayTeam))
        XCTAssertEqual(greyModel.mediumFooterSegments[6], .init(text: "73", ink: .homeTeam))
    }

    // MARK: - 2 & 3. Small Widget + Watch Tile Projections (`214-A1`) & Small Widget After `"Pregame 58%"`

    func testSmallWidgetAndWatchProjectionsAndFinishedSmallPregameColour() throws {
        // Before: Lions 58% home favourite -> `"Proj. 27–21"` (no `"DET"`, 27 in Lions blue, 21 in Patriots red)
        let beforeDetail = try decodeWidgetEvent("""
        {
          "id": 702001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-17T01:15:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "current_odds": {
            "away_probability": 0.42,
            "home_probability": 0.58,
            "away_rendered_percent": 42,
            "home_rendered_percent": 58,
            "projected_away_score": 21.0,
            "projected_home_score": 27.0
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let beforeArt = SavedWidgetArt12466.game(beforeDetail)
        let beforeReading = SavedWidgetReadingRules10875.game(beforeDetail, side: nil, now: fixedNow)
        let beforeModel = SavedGameHeadlineWidgetModel12616.build(
            reading: beforeReading,
            art: beforeArt,
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(beforeModel.smallFooter, "Proj. 27–21")
        XCTAssertFalse(beforeModel.smallFooter.contains("DET"))
        XCTAssertEqual(beforeModel.smallFooterSegments, [
            .init(text: "Proj. ", ink: .quiet),
            .init(text: "27", ink: .homeTeam),
            .init(text: "\u{2013}", ink: .quiet),
            .init(text: "21", ink: .awayTeam),
        ])

        // Watch tile before: `"Favored · Proj. 27–21"` with 27 in Lions colour & 21 in Patriots colour
        let kickoff = ISO8601DateFormatter().date(from: "2026-11-17T01:15:00Z")!
        let watchBefore = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Detroit Lions",
                awayTeam: "New England Patriots",
                homeServedAbbreviation: "DET",
                awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.58,
                awayProbability: 0.42,
                projectedHomeScore: 27.0,
                projectedAwayScore: 21.0,
                homePrimaryColor: "#0076B6",
                awayPrimaryColor: "#C60C30",
                commenceTime: kickoff
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(watchBefore.supportingLine, "Favored · Proj. 27–21")
        XCTAssertEqual(watchBefore.supportingSegments.count, 4)
        XCTAssertEqual(watchBefore.supportingSegments[0], .init(text: "Favored · Proj. ", hex: nil))
        XCTAssertEqual(watchBefore.supportingSegments[1].text, "27")
        XCTAssertNotNil(watchBefore.supportingSegments[1].hex)
        XCTAssertEqual(watchBefore.supportingSegments[2], .init(text: "\u{2013}", hex: nil))
        XCTAssertEqual(watchBefore.supportingSegments[3].text, "21")
        XCTAssertNotNil(watchBefore.supportingSegments[3].hex)
        XCTAssertNotEqual(watchBefore.supportingSegments[1].hex, watchBefore.supportingSegments[3].hex)

        // After: Small widget `"Pregame 58%"` prints in Lions blue (`#0076B6`)
        let afterDetail = try decodeWidgetEvent("""
        {
          "id": 702003,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-16T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 20,
          "home_score": 31,
          "hero_settled_result": "home",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "current_odds": { "away_probability": 0.0, "home_probability": 1.0 }
        }
        """)
        let afterArt = SavedWidgetArt12466.game(afterDetail)
        let afterReading = SavedWidgetReadingRules10875.game(afterDetail, side: nil, now: fixedNow)
        let afterModel = SavedGameHeadlineWidgetModel12616.build(
            reading: afterReading,
            art: afterArt,
            clockFooter: "Final",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(afterModel.smallTopTrailing, "Pregame 58%")
        XCTAssertEqual(afterModel.smallTopTrailingInkHex?.uppercased(), "#0076B6")
        XCTAssertEqual(afterModel.smallFooter, "")

        // Upset small widget: keeps `"Pregame 42%"` in winner's red (`#C60C30`) in the header
        // and drops the duplicate `"Won from 42% pregame"` footer (Fable look 5:12 PM PT).
        let afterUpsetDetail = try decodeWidgetEvent("""
        {
          "id": 702006,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-16T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 28,
          "home_score": 24,
          "hero_settled_result": "away",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "current_odds": { "away_probability": 1.0, "home_probability": 0.0 }
        }
        """)
        let afterUpsetModel = SavedGameHeadlineWidgetModel12616.build(
            reading: SavedWidgetReadingRules10875.game(afterUpsetDetail, side: nil, now: fixedNow),
            art: SavedWidgetArt12466.game(afterUpsetDetail),
            clockFooter: "Final",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(afterUpsetModel.smallTopTrailing, "Pregame 42%")
        XCTAssertEqual(afterUpsetModel.smallTopTrailingInkHex?.uppercased(), "#C60C30")
        XCTAssertEqual(afterUpsetModel.smallFooter, "")
        XCTAssertTrue(afterUpsetModel.smallFooterSegments.isEmpty)
        XCTAssertEqual(afterUpsetModel.mediumFooter, "Patriots won from a 42% pregame chance")

        // Live soccer Medium widget: prints rounded whole-number goals (matching LiveProjectedFinalAdmission2920),
        // never decimals, and withholds outside regulation.
        let soccerRegDetail = try decodeWidgetEvent("""
        {
          "id": 702004,
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Chelsea",
          "home_team": "Arsenal",
          "away_score": 0,
          "home_score": 1,
          "away_team_data": { "abbreviation": "CHE", "primary_color": "#034694" },
          "home_team_data": { "abbreviation": "ARS", "primary_color": "#EF0107" },
          "espn": { "period": "62'" },
          "prematch_odds": { "away_probability": 0.25, "home_probability": 0.50, "draw_probability": 0.25 },
          "current_odds": {
            "away_probability": 0.14,
            "home_probability": 0.68,
            "draw_probability": 0.18,
            "away_rendered_percent": 14,
            "home_rendered_percent": 68,
            "live_projection": {
              "projected_away_score": 0.8,
              "projected_home_score": 1.6,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:02:00Z",
              "latest_captured_at": "\(freshStamp)",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 6,
              "unit": "goals",
              "period": "regulation"
            }
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let soccerRegModel = SavedGameHeadlineWidgetModel12616.build(
            reading: SavedWidgetReadingRules10875.game(soccerRegDetail, side: nil, now: fixedNow),
            art: SavedWidgetArt12466.game(soccerRegDetail),
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(soccerRegModel.headers, .init(leading: "Score", pregame: "Proj.", primary: "Now"))
        XCTAssertEqual(soccerRegModel.away.liveProjectedText, "1")
        XCTAssertEqual(soccerRegModel.home.liveProjectedText, "2")

        // Extra time withholds soccer 90-min regulation projection
        let soccerETDetail = try decodeWidgetEvent("""
        {
          "id": 702005,
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Chelsea",
          "home_team": "Arsenal",
          "away_score": 1,
          "home_score": 1,
          "espn": { "period": "95'" },
          "current_odds": {
            "away_probability": 0.30,
            "home_probability": 0.40,
            "draw_probability": 0.30,
            "away_rendered_percent": 30,
            "home_rendered_percent": 40,
            "live_projection": {
              "projected_away_score": 1.4,
              "projected_home_score": 1.6,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:35:00Z",
              "latest_captured_at": "\(freshStamp)",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 6,
              "unit": "goals",
              "period": "regulation"
            }
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let soccerETModel = SavedGameHeadlineWidgetModel12616.build(
            reading: SavedWidgetReadingRules10875.game(soccerETDetail, side: nil, now: fixedNow),
            art: SavedWidgetArt12466.game(soccerETDetail),
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertNil(soccerETModel.headers.pregame)
        XCTAssertNil(soccerETModel.away.liveProjectedText)
        XCTAssertNil(soccerETModel.home.liveProjectedText)

        // Parity guard: PeriodLabel.isSoccerRegulationPeriod matches LiveProjectedFinalAdmission2920.soccerPhase
        let samplePeriods: [String?] = [
            nil, "", "  ", "1st Half", "2nd half", "first half", "second half",
            "1H", "2H", "HT", "Halftime", "half time", "half-time",
            "0", "1'", "45'", "45+2", "45' + 3'", "62'", "90", "90+4'",
            "30+2", "91'", "105+1", "ET", "Pen.", "FT", "4 5", "90+100", "Q1", "١٢"
        ]
        for raw in samplePeriods {
            let expectedReg = LiveProjectedFinalAdmission2920.soccerPhase(servedPeriod: raw) == .regulation
            XCTAssertEqual(
                PeriodLabel.isSoccerRegulationPeriod(raw),
                expectedReg,
                "Soccer regulation parity mismatch for \(String(describing: raw))"
            )
        }
    }

    // MARK: - 4. 390 px Render Sheet Across All Four Items

    private func renderHostedSheet<V: View>(_ view: V, width: CGFloat = 390) -> UIImage {
        let wrapped = view
            .frame(width: width)
            .background(Color(UIColor.systemGroupedBackground))
            .environment(\.colorScheme, .light)

        let host = hostForMeasurement(wrapped, at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: 12_000))
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: max(fitting.height, 400))
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.25)
        repeat {
            let nextH = max(host.sizeThatFits(in: CGSize(width: width, height: 12_000)).height, 400)
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

    func testExportWidgetsWatchAndCalibration214A1Sheet390() throws {
        let kickoff = ISO8601DateFormatter().date(from: "2026-11-17T01:15:00Z")!

        func buildWidget(json: String, clock: String = "As of 11:14 AM") throws -> (SavedGameHeadlineWidgetModel12616, SavedWidgetReading10875, SavedWidgetArt12466) {
            let detail = try decodeWidgetEvent(json)
            let reading = SavedWidgetReadingRules10875.game(detail, side: nil, now: fixedNow)
            let art = SavedWidgetArt12466.game(detail)
            let model = SavedGameHeadlineWidgetModel12616.build(
                reading: reading,
                art: art,
                clockFooter: clock,
                isOffline: false,
                clearsRefreshTrailing: false,
                now: fixedNow,
                timeZone: pacific
            )
            return (model, reading, art)
        }

        let (liveDistinctM, liveDistinctR, liveDistinctA) = try buildWidget(json: """
        {
          "id": 703001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 17,
          "home_score": 24,
          "espn": { "period": "Q3", "game_clock": "08:14" },
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "pregame_projection": {
            "projected_away_score": 21.0,
            "projected_home_score": 27.0,
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
            "away_probability": 0.338,
            "home_probability": 0.662,
            "away_rendered_percent": 34,
            "home_rendered_percent": 66,
            "live_projection": {
              "projected_away_score": 23.0,
              "projected_home_score": 30.0,
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

        let (liveClashM, liveClashR, liveClashA) = try buildWidget(json: """
        {
          "id": 703002,
          "sport": "basketball_ncaab",
          "sport_name": "NCAAB",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "Gonzaga Bulldogs",
          "home_team": "Duke Blue Devils",
          "away_score": 41,
          "home_score": 38,
          "espn": { "period": "2nd Half", "game_clock": "14:20" },
          "away_team_data": { "abbreviation": "GONZ", "primary_color": "#041E42" },
          "home_team_data": { "abbreviation": "DUKE", "primary_color": "#003087" },
          "prematch_odds": { "away_probability": 0.56, "home_probability": 0.44 },
          "pregame_projection": {
            "projected_away_score": 76.0,
            "projected_home_score": 73.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T18:00:00Z",
            "earliest_captured_at": "2026-11-16T17:30:00Z",
            "latest_captured_at": "2026-11-16T17:58:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 4,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.618,
            "home_probability": 0.382,
            "away_rendered_percent": 62,
            "home_rendered_percent": 38,
            "live_projection": {
              "projected_away_score": 79.0,
              "projected_home_score": 74.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:10:00Z",
              "latest_captured_at": "\(freshStamp)",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 4,
              "unit": "points",
              "period": "full_game"
            }
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)

        let (beforeM, beforeR, beforeA) = try buildWidget(json: """
        {
          "id": 703003,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-17T01:15:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "current_odds": {
            "away_probability": 0.42,
            "home_probability": 0.58,
            "away_rendered_percent": 42,
            "home_rendered_percent": 58,
            "projected_away_score": 21.0,
            "projected_home_score": 27.0
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)

        let (afterM, afterR, afterA) = try buildWidget(json: """
        {
          "id": 703004,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-16T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 20,
          "home_score": 31,
          "hero_settled_result": "home",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "current_odds": { "away_probability": 0.0, "home_probability": 1.0 }
        }
        """, clock: "Final")

        let (afterUpsetM, afterUpsetR, afterUpsetA) = try buildWidget(json: """
        {
          "id": 703005,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-16T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 28,
          "home_score": 24,
          "hero_settled_result": "away",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "current_odds": { "away_probability": 1.0, "home_probability": 0.0 }
        }
        """, clock: "Final")

        let watchBefore = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Detroit Lions",
                awayTeam: "New England Patriots",
                homeServedAbbreviation: "DET",
                awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.58,
                awayProbability: 0.42,
                projectedHomeScore: 27.0,
                projectedAwayScore: 21.0,
                homePrimaryColor: "#0076B6",
                homeSecondaryColor: "#38BDF8",
                awayPrimaryColor: "#C60C30",
                awaySecondaryColor: "#F87171",
                commenceTime: kickoff
            ),
            now: fixedNow,
            timeZone: pacific
        )

        // Calibration undated + daily staleness banner
        let calData = try decodeJSON(CalibrationData.self, """
        {
          "availability": "stale",
          "producer": {"task": "precompute_calibration_main", "interval_s": 86400, "stall_after_s": 259200, "age_s": 3600, "beats_missed": 0, "stalled": false},
          "staged": {"measured": false, "reason": "served_bank_empty"},
          "population_version": "\(CalibrationRenderSmokeTests.renderableVersion)",
          "date_range": {"start": "2024-09-01", "end": "2026-11-16"},
          "buckets": [
            {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
            {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": false, "n": 100, "winners": 55, "avg_prob": 0.55, "sum_prob": 55.0, "sum_sq_err": 24.0, "ci_lower": 0.45, "ci_upper": 0.64}
          ],
          "total_markets": 12, "total_outcomes": 300, "total_winners": 115,
          "min_category_outcomes": 1000
        }
        """)
        let calVM = CalibrationViewModel(preloaded: calData)
        let calRenderer = rendererForMeasurement(
            CalibrationSurfaceView(viewModel: calVM, scrolls: false)
                .frame(width: 390)
                .background(Color.white)
                .environment(\.colorScheme, .light)
        )
        calRenderer.scale = 3.0
        let fullCalImg = try XCTUnwrap(calRenderer.uiImage)
        let cropH = min(fullCalImg.size.height, 360)
        let calFmt = UIGraphicsImageRendererFormat()
        calFmt.scale = 3.0
        calFmt.opaque = true
        let calCropImg = UIGraphicsImageRenderer(size: CGSize(width: 390, height: cropH), format: calFmt).image { ctx in
            UIColor.white.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 390, height: cropH))
            fullCalImg.draw(at: .zero)
        }

        @ViewBuilder
        func widgetCard(
            model: SavedGameHeadlineWidgetModel12616,
            reading: SavedWidgetReading10875,
            art: SavedWidgetArt12466,
            size: SavedGameWidgetSize12616
        ) -> some View {
            let w: CGFloat = size == .small ? 158 : 338
            let hexes = art.barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)
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
            .background(Color.white, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
            )
        }

        let sheet = VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 14) {
                Text("Widgets, Watch & Calibration — Rulings 213-A · 214-A1 · 215-B (390 px)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.primary)
                    .fixedSize(horizontal: false, vertical: true)

                sectionLabel("1A · Medium Widget During (Patriots @ Lions: Score · Proj. · Now + Tick + Pregame Line)")
                widgetCard(model: liveDistinctM, reading: liveDistinctR, art: liveDistinctA, size: .medium)

                sectionLabel("1B · Medium Widget During — Ruling 197 Grey Fallback (Gonzaga #475569 @ Duke)")
                widgetCard(model: liveClashM, reading: liveClashR, art: liveClashA, size: .medium)

                sectionLabel("2 · Small Widget & Watch Tile Before (Proj. 27–21 in Team Colours, Fav First, No DET)")
                HStack(alignment: .center, spacing: 12) {
                    widgetCard(model: beforeM, reading: beforeR, art: beforeA, size: .small)
                    WatchWristTileView12616(model: watchBefore) { EmptyView() }
                        .frame(width: 188)
                }

                sectionLabel("3 · Small Widget After (Pregame 58% in Lions Blue & Pregame 42% in Patriots Red)")
                HStack(alignment: .center, spacing: 12) {
                    widgetCard(model: afterM, reading: afterR, art: afterA, size: .small)
                    widgetCard(model: afterUpsetM, reading: afterUpsetR, art: afterUpsetA, size: .small)
                }
            }
            .padding(.horizontal, 16)

            sectionLabel("4 · Calibration Screen (Daily Cadence in Banner + No 'Updated hourly' When Undated)")
                .padding(.horizontal, 16)
            Image(uiImage: calCropImg)
                .resizable()
                .frame(width: 390, height: calCropImg.size.height)
        }
        .padding(.vertical, 16)

        let img = renderHostedSheet(sheet, width: 390)
        XCTAssertEqual(img.size.width, 390, accuracy: 0.5)

        let afterSheet = VStack(alignment: .leading, spacing: 14) {
            Text("After-Game Widgets — Upset Small Widget Header Only (390 px)")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)

            sectionLabel("Small Widget After: Favourite Won (Pregame 58%) · Upset Won (Pregame 42%, No Duplicate Footer)")
            HStack(alignment: .center, spacing: 12) {
                widgetCard(model: afterM, reading: afterR, art: afterA, size: .small)
                widgetCard(model: afterUpsetM, reading: afterUpsetR, art: afterUpsetA, size: .small)
            }

            sectionLabel("Medium Widget After: Upset Won (Patriots @ Lions)")
            widgetCard(model: afterUpsetM, reading: afterUpsetR, art: afterUpsetA, size: .medium)
        }
        .padding(16)

        let afterImg = renderHostedSheet(afterSheet, width: 390)
        XCTAssertEqual(afterImg.size.width, 390, accuracy: 0.5)

        if let dir = ProcessInfo.processInfo.environment["EXPORT_WIDGETS_214A1_DIR"], !dir.isEmpty {
            let outURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)
            try XCTUnwrap(img.pngData()).write(to: outURL.appendingPathComponent("widgets-watch-calibration-214a1-390.png"))
            try XCTUnwrap(afterImg.pngData()).write(to: outURL.appendingPathComponent("widgets-214a1-after-sheet-390.png"))
        }
    }

    private func sectionLabel(_ title: String) -> some View {
        Text(title)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }
}
