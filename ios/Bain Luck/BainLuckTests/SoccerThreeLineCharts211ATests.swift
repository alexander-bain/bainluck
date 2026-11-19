import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Ruling 211-A (Mon Nov 16, 2026):
/// Soccer charts draw all three lines — Home, Draw, and Away — on `0` to `100`,
/// with `Draw` drawn as the lighter grey line (`HeadlineStyleTable199.drawInk`).
@MainActor
final class SoccerThreeLineCharts211ATests: XCTestCase {

    private func decodeJSON<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(type, from: Data(json.utf8))
    }

    // MARK: - 1. 3-Way Decoding, Extraction, Terminal Safety & #5271/#5363 Two-Way Refusal

    func testThreeWaySoccerSeriesExtractsAllThreeOutcomesAndRefusesTwoWayComplement() throws {
        // A. Explicit 3-way venue series (`kalshi`) + synthetic `game_state.final` row (`0.5 / 0.5 / null`)
        //    on a 1–1 finished draw: real 3-way readings are preserved and the legacy 2-way `0.5`
        //    terminal row is excluded so `Draw` never drops from 92% to 50%!
        let finishedDrawHistory = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 601001,
          "home_team": "Arsenal",
          "away_team": "Chelsea",
          "status": "completed",
          "completed_at": "2026-11-16T19:55:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-16T17:55:00Z", "home_probability": 0.48, "draw_probability": 0.26, "away_probability": 0.26},
              {"timestamp": "2026-11-16T18:30:00Z", "home_probability": 0.62, "draw_probability": 0.22, "away_probability": 0.16},
              {"timestamp": "2026-11-16T19:15:00Z", "home_probability": 0.28, "draw_probability": 0.49, "away_probability": 0.23},
              {"timestamp": "2026-11-16T19:50:00Z", "home_probability": 0.05, "draw_probability": 0.91, "away_probability": 0.04},
              {"timestamp": "2026-11-16T19:55:00Z", "home_probability": 0.50, "draw_probability": null, "away_probability": 0.50, "game_state": {"final": true}}
            ]
          }
        }
        """)

        let series = try XCTUnwrap(
            SoccerThreeLineChart211A.build(
                history: finishedDrawHistory,
                sportKey: "soccer_epl",
                status: "completed",
                commenceTime: "2026-11-16T18:00:00Z",
                selectedRange: .sinceStart,
                homeLabel: "Arsenal",
                awayLabel: "Chelsea"
            )
        )
        XCTAssertEqual(series.source, "kalshi")
        XCTAssertEqual(series.homeLabel, "Arsenal")
        XCTAssertEqual(series.awayLabel, "Chelsea")
        XCTAssertEqual(series.points.count, 4, "Pregame anchor + 3 in-play readings; synthetic 0.5/0.5/null final row excluded")
        XCTAssertEqual(series.points.first?.home ?? 0, 0.48, accuracy: 0.001)
        XCTAssertEqual(series.points.first?.draw ?? 0, 0.26, accuracy: 0.001)
        XCTAssertEqual(series.points.first?.away ?? 0, 0.26, accuracy: 0.001)
        XCTAssertEqual(series.points.last?.draw ?? 0, 0.91, accuracy: 0.001)
        let resting = try XCTUnwrap(series.reading(at: nil))
        let formatted = series.formattedTriple(for: resting.point)
        XCTAssertEqual(formatted.home, "5%")
        XCTAssertEqual(formatted.draw, "91%")
        XCTAssertEqual(formatted.away, "4%")

        // B. 3-way sportsbook `history` consensus (`h2h_pair_on_the_full_board`: `home + away < 1.0`)
        let booksThreeWay = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 601002,
          "home_team": "Liverpool",
          "away_team": "Manchester City",
          "status": "scheduled",
          "history": [
            {"timestamp": "2026-11-16T14:00:00Z", "home_probability": 0.42, "away_probability": 0.32, "bookmaker_count": 8},
            {"timestamp": "2026-11-16T16:00:00Z", "home_probability": 0.45, "away_probability": 0.30, "bookmaker_count": 9}
          ]
        }
        """)
        let booksSeries = try XCTUnwrap(
            SoccerThreeLineChart211A.build(
                history: booksThreeWay,
                sportKey: "soccer_epl",
                status: "scheduled",
                commenceTime: "2026-11-16T20:00:00Z",
                selectedRange: .all,
                homeLabel: "Liverpool",
                awayLabel: "Man City"
            )
        )
        XCTAssertEqual(booksSeries.points.last?.home ?? 0, 0.45, accuracy: 0.001)
        XCTAssertEqual(booksSeries.points.last?.draw ?? 0, 0.25, accuracy: 0.001)
        XCTAssertEqual(booksSeries.points.last?.away ?? 0, 0.30, accuracy: 0.001)

        // C. Two-way complement-only soccer (#5271 / #5363): `home + away == 1.0` with no `draw_probability`
        //    must return `nil` rather than inventing `0%` draw or `1 - home` away!
        let twoWayOnly = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 601003,
          "home_team": "Everton",
          "away_team": "Fulham",
          "status": "live",
          "history": [
            {"timestamp": "2026-11-16T18:05:00Z", "home_probability": 0.58, "away_probability": 0.42, "bookmaker_count": 4},
            {"timestamp": "2026-11-16T18:25:00Z", "home_probability": 0.64, "away_probability": 0.36, "bookmaker_count": 4}
          ]
        }
        """)
        XCTAssertNil(
            SoccerThreeLineChart211A.build(
                history: twoWayOnly,
                sportKey: "soccer_epl",
                status: "live",
                commenceTime: "2026-11-16T18:00:00Z",
                selectedRange: .sinceStart,
                homeLabel: "Everton",
                awayLabel: "Fulham"
            ),
            "2-way complement-only soccer must never invent a 3-line chart"
        )

        // D. Non-soccer sport (`basketball_nba`) always returns `nil`
        XCTAssertNil(
            SoccerThreeLineChart211A.build(
                history: finishedDrawHistory,
                sportKey: "basketball_nba",
                status: "completed",
                commenceTime: "2026-11-16T18:00:00Z",
                selectedRange: .sinceStart,
                homeLabel: "Celtics",
                awayLabel: "Lakers"
            )
        )
    }

    // MARK: - 2. 390 px Render Sheet (Game Page Before / During / After + Discover Card)

    private func renderHostedSheet<V: View>(_ view: V, width: CGFloat = 390) -> UIImage {
        let wrapped = view
            .frame(width: width)
            .background(Color(UIColor.systemGroupedBackground))
            .environmentObject(PinManager(
                defaults: UserDefaults(suiteName: "SoccerThreeLineCharts211ATests")!,
                serverLoad: { PinsResponse(events: [], futures: []) },
                serverSync: { _, _, _ in }
            ))
            .environmentObject(NavigationCoordinator())
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
        let until = Date().addingTimeInterval(0.3)
        repeat {
            let nextH = max(host.sizeThatFits(in: CGSize(width: width, height: 12_000)).height, 400)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: width, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.04))
        } while Date() < until

        let format = UIGraphicsImageRendererFormat()
        format.scale = 3.0
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: host.view.bounds.size, format: format)
        return renderer.image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    func testExportRuling211ASoccerThreeLineChartSheetAt390px() throws {
        let beforeHistory = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 602001,
          "home_team": "Arsenal",
          "away_team": "Chelsea",
          "status": "scheduled",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-15T12:00:00Z", "home_probability": 0.46, "draw_probability": 0.27, "away_probability": 0.27},
              {"timestamp": "2026-11-15T20:00:00Z", "home_probability": 0.49, "draw_probability": 0.26, "away_probability": 0.25},
              {"timestamp": "2026-11-16T08:00:00Z", "home_probability": 0.52, "draw_probability": 0.25, "away_probability": 0.23},
              {"timestamp": "2026-11-16T16:00:00Z", "home_probability": 0.54, "draw_probability": 0.24, "away_probability": 0.22}
            ]
          }
        }
        """)

        let liveHistory = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 602002,
          "home_team": "Chelsea",
          "away_team": "Arsenal",
          "status": "live",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-16T17:25:00Z", "home_probability": 0.34, "draw_probability": 0.25, "away_probability": 0.41},
              {"timestamp": "2026-11-16T17:48:00Z", "home_probability": 0.31, "draw_probability": 0.30, "away_probability": 0.39},
              {"timestamp": "2026-11-16T18:10:00Z", "home_probability": 0.58, "draw_probability": 0.24, "away_probability": 0.18},
              {"timestamp": "2026-11-16T18:35:00Z", "home_probability": 0.524, "draw_probability": 0.235, "away_probability": 0.241}
            ]
          }
        }
        """)

        let afterDrawHistory = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 602003,
          "home_team": "Liverpool",
          "away_team": "Arsenal",
          "status": "completed",
          "completed_at": "2026-11-16T19:52:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-16T17:55:00Z", "home_probability": 0.44, "draw_probability": 0.26, "away_probability": 0.30},
              {"timestamp": "2026-11-16T18:22:00Z", "home_probability": 0.65, "draw_probability": 0.20, "away_probability": 0.15},
              {"timestamp": "2026-11-16T19:12:00Z", "home_probability": 0.31, "draw_probability": 0.46, "away_probability": 0.23},
              {"timestamp": "2026-11-16T19:49:00Z", "home_probability": 0.06, "draw_probability": 0.89, "away_probability": 0.05}
            ]
          }
        }
        """)

        let liveSoccerFeed = try decodeJSON(FeedEventData.self, """
        {
          "id": 602002,
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "home_team": "Chelsea",
          "away_team": "Arsenal",
          "commence_time": "2026-11-16T17:30:00Z",
          "status": "live",
          "home_score": 1,
          "away_score": 0,
          "home_team_data": { "abbreviation": "CHE", "primary_color": "#034694" },
          "away_team_data": { "abbreviation": "ARS", "primary_color": "#EF0107" },
          "current_odds": {
            "away_probability": 0.241,
            "draw_probability": 0.235,
            "home_probability": 0.524,
            "live_projection": {
              "projected_away_score": 1.0,
              "projected_home_score": 1.6,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T17:30:00Z",
              "earliest_confirmed_at": "2026-11-16T18:30:00Z",
              "latest_captured_at": "2026-11-16T18:35:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 3,
              "unit": "goals",
              "period": "regulation"
            }
          },
          "prematch_odds": {
            "away_probability": 0.41,
            "draw_probability": 0.25,
            "home_probability": 0.34,
            "source": "kalshi"
          },
          "espn": { "period": "67'" }
        }
        """)

        let arsenalChelseaColors = TeamTextContrast.cardColors(awayHex: "#034694", homeHex: "#EF0107")
        let chelseaArsenalColors = TeamTextContrast.cardColors(awayHex: "#EF0107", homeHex: "#034694")
        // Ruling 197 red-vs-red clash (`Liverpool #C8102E` home vs `Arsenal #EF0107` away + `#063672` navy secondary)!
        let liverpoolArsenalColors = TeamTextContrast.cardColors(
            awayHex: "#EF0107",
            homeHex: "#C8102E",
            awaySecondaryHex: "#063672"
        )

        let sheet = VStack(alignment: .leading, spacing: 14) {
            Text("Ruling 211-A — Three-Line Soccer Charts (Home · Draw · Away on 0–100 · 390 px)")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(.primary)

            chartSection("1 · Game Page Before Kickoff (Arsenal · Draw · Chelsea, 0–100)") {
                OddsChartView(
                    eventId: 602001,
                    teamColors: arsenalChelseaColors,
                    commenceTime: "2026-11-16T20:00:00Z",
                    status: "scheduled",
                    homeTeamName: "Arsenal",
                    awayTeamName: "Chelsea",
                    homeTeamAbbrev: "ARS",
                    awayTeamAbbrev: "CHE",
                    sportKey: "soccer_epl",
                    selectedRange: .constant(.all),
                    preloadedHistory: beforeHistory
                )
            }

            chartSection("2 · Game Page Live 67' (Chelsea · Draw · Arsenal, 0–100)") {
                OddsChartView(
                    eventId: 602002,
                    teamColors: chelseaArsenalColors,
                    commenceTime: "2026-11-16T17:30:00Z",
                    status: "live",
                    homeTeamName: "Chelsea",
                    awayTeamName: "Arsenal",
                    homeTeamAbbrev: "CHE",
                    awayTeamAbbrev: "ARS",
                    sportKey: "soccer_epl",
                    homeScore: 1,
                    awayScore: 0,
                    preloadedHistory: liveHistory
                )
            }

            chartSection("3 · Game Page Finished 1–1 Draw + Ruling 197 Clash (Liverpool Red · Draw Grey · Arsenal Navy)") {
                OddsChartView(
                    eventId: 602003,
                    teamColors: liverpoolArsenalColors,
                    commenceTime: "2026-11-16T18:00:00Z",
                    status: "completed",
                    homeTeamName: "Liverpool",
                    awayTeamName: "Arsenal",
                    homeTeamAbbrev: "LIV",
                    awayTeamAbbrev: "ARS",
                    sportKey: "soccer_epl",
                    homeScore: 1,
                    awayScore: 1,
                    preloadedHistory: afterDrawHistory
                )
            }

            chartSection("4 · Discover Live Soccer Card (191-A 3-Line Chart Panel on 0–100)") {
                NativeEventDiscoverCard(
                    event: liveSoccerFeed,
                    feedContext: nil,
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: liveHistory
                )
            }
        }
        .padding(16)

        let img = renderHostedSheet(sheet, width: 390)
        XCTAssertEqual(img.size.width, 390, accuracy: 0.5)

        if let dir = ProcessInfo.processInfo.environment["EXPORT_211A_SOCCER_DIR"], !dir.isEmpty {
            let outURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)
            try XCTUnwrap(img.pngData()).write(to: outURL.appendingPathComponent("211a-soccer-three-line-charts-390.png"))
        }
    }

    private func chartSection<V: View>(_ title: String, @ViewBuilder content: () -> V) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            content()
                .padding(12)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
                )
        }
    }
}
