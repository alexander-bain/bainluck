import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// #13091 (report 232 — Celtics 101 at Nuggets ✓ 105) & #13092 (report 233 — Jazz ✓ 109 at Lakers 97):
/// 1. `DiscoverPictureChartPanel191AView` renders a same-height chart-shaped loading state
///    (`"Loading win-chance chart"`) instead of a blank box while history loads.
/// 2. Two-way Discover game charts label whose win chance the curve represents
///    (`"Nuggets win chance"`, `"Jazz win chance"`) and state the deterministic
///    pregame-to-final outcome (`"Upset · Opened at 15%"`, `"Rallied from 14%"`,
///    `"Opened at 64% · Won"`) with zero model-written text and zero `"…"`.
/// 3. Finished two-way Discover cards whose `/api/feed` payload omitted `prematch_odds`
///    recover the `Pregame` column (`15%` / `85%`) from `EventHistoryResponse`.
@MainActor
final class DiscoverChartLoadingAndUpset13091Tests: XCTestCase {

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    func testNuggetsRally13091AndJazzUpset13092ModelsAndPrematchFallback() throws {
        // 1. #13091: Celtics 101 at Nuggets ✓ 105 (Nuggets opened 48%, dipped to 14%, rallied to win)
        let nuggetsEvent = try decodeEvent(#"""
        {
          "id": 15350575,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Denver Nuggets",
          "commence_time": "2026-11-19T02:00:00Z",
          "status": "completed",
          "away_score": 101,
          "home_score": 105,
          "away_team_data": {"primary_color": "#007A33", "abbreviation": "BOS"},
          "home_team_data": {"primary_color": "#0E2240", "secondary_color": "#FEC524", "abbreviation": "DEN"},
          "prematch_odds": {"away_probability": 0.52, "home_probability": 0.48, "away_rendered_percent": 52, "home_rendered_percent": 48, "source": "kalshi"},
          "pregame_projection": {
            "projected_away_score": 111.0,
            "projected_home_score": 109.0,
            "source": "sportsbooks",
            "unit": "points",
            "period": "full_game"
          }
        }
        """#)
        let nuggetsHistory = try decodeHistory(#"""
        {
          "event_id": 15350575,
          "home_team": "Denver Nuggets",
          "away_team": "Boston Celtics",
          "status": "completed",
          "completed_at": "2026-11-19T04:32:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T02:00:00Z", "home_probability": 0.48},
              {"timestamp": "2026-11-19T04:30:00Z", "home_probability": 1.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T02:00:00Z", "home_probability": 0.48},
            {"timestamp": "2026-11-19T02:35:00Z", "home_probability": 0.31},
            {"timestamp": "2026-11-19T03:15:00Z", "home_probability": 0.19},
            {"timestamp": "2026-11-19T03:55:00Z", "home_probability": 0.14},
            {"timestamp": "2026-11-19T04:18:00Z", "home_probability": 0.42},
            {"timestamp": "2026-11-19T04:30:00Z", "home_probability": 1.0}
          ]
        }
        """#)
        let nuggetsPrematch = PrematchReading.resolve(prematch: nuggetsEvent.prematchOdds, opening: nuggetsEvent.openingOdds)
        let nuggetsModel = DiscoverPictureChart191A.build(
            event: nuggetsEvent,
            prematch: nuggetsPrematch,
            history: nuggetsHistory
        )
        XCTAssertEqual(nuggetsModel.perspective, .home)
        XCTAssertEqual(nuggetsModel.chartHeaderTitle, "Nuggets win chance")
        XCTAssertEqual(nuggetsModel.finishedSummaryLabel, "Rallied from 14%")

        // 2. #13092: Jazz ✓ 109 at Lakers 97 (`prematch_odds` omitted on feed payload; history starts at 15% Jazz / 85% Lakers)
        let jazzEvent = try decodeEvent(#"""
        {
          "id": 15350792,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Utah Jazz",
          "home_team": "Los Angeles Lakers",
          "commence_time": "2026-11-19T03:30:00Z",
          "status": "completed",
          "away_score": 109,
          "home_score": 97,
          "away_team_data": {"primary_color": "#002B5C", "secondary_color": "#F9A01B", "abbreviation": "UTA"},
          "home_team_data": {"primary_color": "#552583", "secondary_color": "#FDB927", "abbreviation": "LAL"},
          "pregame_projection": {
            "projected_away_score": 109.0,
            "projected_home_score": 121.0,
            "source": "sportsbooks",
            "unit": "points",
            "period": "full_game"
          }
        }
        """#)
        let jazzHistory = try decodeHistory(#"""
        {
          "event_id": 15350792,
          "home_team": "Los Angeles Lakers",
          "away_team": "Utah Jazz",
          "status": "completed",
          "completed_at": "2026-11-19T05:55:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T03:28:00Z", "home_probability": 0.85},
              {"timestamp": "2026-11-19T05:52:00Z", "home_probability": 0.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T03:28:00Z", "home_probability": 0.85},
            {"timestamp": "2026-11-19T04:05:00Z", "home_probability": 0.72},
            {"timestamp": "2026-11-19T04:45:00Z", "home_probability": 0.58},
            {"timestamp": "2026-11-19T05:20:00Z", "home_probability": 0.31},
            {"timestamp": "2026-11-19T05:52:00Z", "home_probability": 0.0}
          ]
        }
        """#)
        XCTAssertTrue(
            DiscoverSingleGameCard190C.qualifiesForPicture191A(event: jazzEvent),
            "Finished Discover card with pregame_projection stays eligible for 191-A chart"
        )
        let recoveredPrematch = try XCTUnwrap(
            DiscoverPictureChart191A.fallbackPrematchReading(event: jazzEvent, history: jazzHistory)
        )
        XCTAssertEqual(recoveredPrematch.awayProbability, 0.15, accuracy: 0.001)
        XCTAssertEqual(recoveredPrematch.homeProbability, 0.85, accuracy: 0.001)

        let jazzCardModel = DiscoverSingleGameCard190C.build(
            event: jazzEvent,
            prematch: recoveredPrematch,
            showsInlinePregame: true,
            usesPictureLayout: true
        )
        XCTAssertEqual(jazzCardModel.headers, .init(score: nil, pregame: "Pregame", primary: "Final"))
        XCTAssertEqual(jazzCardModel.rows.map(\.pregameText), ["15%", "85%"])

        let jazzChartModel = DiscoverPictureChart191A.build(
            event: jazzEvent,
            prematch: recoveredPrematch,
            history: jazzHistory
        )
        XCTAssertEqual(jazzChartModel.perspective, .away)
        XCTAssertEqual(jazzChartModel.chartHeaderTitle, "Jazz win chance")
        XCTAssertEqual(jazzChartModel.finishedSummaryLabel, "Upset · Opened at 15%")
    }

    #if canImport(UIKit)
    func testLoadingStateHoldsSameHeightAndCardsRenderWithoutEllipsisAt390DefaultAndAX3() throws {
        let nuggetsEvent = try decodeEvent(#"""
        {
          "id": 15350575,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Denver Nuggets",
          "commence_time": "2026-11-19T02:00:00Z",
          "status": "completed",
          "away_score": 101,
          "home_score": 105,
          "away_team_data": {"primary_color": "#007A33", "abbreviation": "BOS"},
          "home_team_data": {"primary_color": "#0E2240", "secondary_color": "#FEC524", "abbreviation": "DEN"},
          "prematch_odds": {"away_probability": 0.52, "home_probability": 0.48, "away_rendered_percent": 52, "home_rendered_percent": 48, "source": "kalshi"},
          "pregame_projection": {
            "projected_away_score": 111.0,
            "projected_home_score": 109.0,
            "source": "sportsbooks",
            "unit": "points",
            "period": "full_game"
          }
        }
        """#)
        let nuggetsHistory = try decodeHistory(#"""
        {
          "event_id": 15350575,
          "home_team": "Denver Nuggets",
          "away_team": "Boston Celtics",
          "status": "completed",
          "completed_at": "2026-11-19T04:32:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T02:00:00Z", "home_probability": 0.48},
              {"timestamp": "2026-11-19T04:30:00Z", "home_probability": 1.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T02:00:00Z", "home_probability": 0.48},
            {"timestamp": "2026-11-19T02:35:00Z", "home_probability": 0.31},
            {"timestamp": "2026-11-19T03:15:00Z", "home_probability": 0.19},
            {"timestamp": "2026-11-19T03:55:00Z", "home_probability": 0.14},
            {"timestamp": "2026-11-19T04:18:00Z", "home_probability": 0.42},
            {"timestamp": "2026-11-19T04:30:00Z", "home_probability": 1.0}
          ]
        }
        """#)
        let jazzEvent = try decodeEvent(#"""
        {
          "id": 15350792,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Utah Jazz",
          "home_team": "Los Angeles Lakers",
          "commence_time": "2026-11-19T03:30:00Z",
          "status": "completed",
          "away_score": 109,
          "home_score": 97,
          "away_team_data": {"primary_color": "#002B5C", "secondary_color": "#F9A01B", "abbreviation": "UTA"},
          "home_team_data": {"primary_color": "#552583", "secondary_color": "#FDB927", "abbreviation": "LAL"},
          "pregame_projection": {
            "projected_away_score": 109.0,
            "projected_home_score": 121.0,
            "source": "sportsbooks",
            "unit": "points",
            "period": "full_game"
          }
        }
        """#)
        let jazzHistory = try decodeHistory(#"""
        {
          "event_id": 15350792,
          "home_team": "Los Angeles Lakers",
          "away_team": "Utah Jazz",
          "status": "completed",
          "completed_at": "2026-11-19T05:55:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T03:28:00Z", "home_probability": 0.85},
              {"timestamp": "2026-11-19T05:52:00Z", "home_probability": 0.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T03:28:00Z", "home_probability": 0.85},
            {"timestamp": "2026-11-19T04:05:00Z", "home_probability": 0.72},
            {"timestamp": "2026-11-19T04:45:00Z", "home_probability": 0.58},
            {"timestamp": "2026-11-19T05:20:00Z", "home_probability": 0.31},
            {"timestamp": "2026-11-19T05:52:00Z", "home_probability": 0.0}
          ]
        }
        """#)

        let nuggetsPrematch = PrematchReading.resolve(prematch: nuggetsEvent.prematchOdds, opening: nuggetsEvent.openingOdds)
        let loadingPanel = DiscoverPictureChartPanel191AView(
            event: nuggetsEvent,
            prematch: nuggetsPrematch,
            awayColor: Color(hex: "#007A33"),
            homeColor: Color(hex: "#0E2240"),
            preloadedHistory: nil,
            isLoadingOverrideForTesting: true
        )
        .frame(width: 334)
        let loadedPanel = DiscoverPictureChartPanel191AView(
            event: nuggetsEvent,
            prematch: nuggetsPrematch,
            awayColor: Color(hex: "#007A33"),
            homeColor: Color(hex: "#0E2240"),
            preloadedHistory: nuggetsHistory
        )
        .frame(width: 334)

        let loadingHost = hostForMeasurement(loadingPanel, at: .large)
        let loadedHost = hostForMeasurement(loadedPanel, at: .large)
        let loadingSize = loadingHost.sizeThatFits(in: CGSize(width: 334, height: 600))
        let loadedSize = loadedHost.sizeThatFits(in: CGSize(width: 334, height: 600))
        XCTAssertEqual(loadingSize.height, loadedSize.height, accuracy: 4.0, "Loading chart placeholder reserves the loaded chart height so the card does not jump")

        let pinDefaults = UserDefaults(suiteName: "test.13091.\(UUID().uuidString)")!
        let pinManager = PinManager(defaults: pinDefaults, allowLegacyGuestPins: false)

        for (typeSize, typeTag) in [(DynamicTypeSize.large, "default"), (.accessibility3, "ax3")] {
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
                let surface = scheme == .dark ? Color.black : Color(white: 0.955)
                let cardBg = scheme == .dark ? Color(hex: "#1C1C1E") : Color.white
                let nuggetsColors = scheme == .dark
                    ? TeamTextContrast.darkSurfaceColorHexes(awayHex: "#007A33", homeHex: "#0E2240", homeSecondaryHex: "#FEC524")
                    : TeamTextContrast.cardColorHexes(awayHex: "#007A33", homeHex: "#0E2240")

                let sheet = VStack(alignment: .leading, spacing: 14) {
                    // 1. Loading placeholder panel (#13091)
                    VStack(alignment: .leading, spacing: 8) {
                        DiscoverPictureChartPanel191AView(
                            event: nuggetsEvent,
                            prematch: nuggetsPrematch,
                            awayColor: Color(hex: nuggetsColors.away),
                            homeColor: Color(hex: nuggetsColors.home),
                            preloadedHistory: nil,
                            isLoadingOverrideForTesting: true
                        )
                    }
                    .padding(14)
                    .background(cardBg)
                    .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))

                    // 2. Loaded #13091 Nuggets rally card
                    NativeEventDiscoverCard(
                        event: nuggetsEvent,
                        feedContext: nil,
                        expandedContext: nil,
                        navigationPath: .constant(NavigationPath()),
                        chartHistory: nuggetsHistory
                    )

                    // 3. Loaded #13092 Jazz upset card (`prematch_odds` recovered from history -> `15%` / `85%` + `Upset · Opened at 15%`)
                    NativeEventDiscoverCard(
                        event: jazzEvent,
                        feedContext: nil,
                        expandedContext: nil,
                        navigationPath: .constant(NavigationPath()),
                        chartHistory: jazzHistory
                    )
                }
                .padding(16)
                .frame(width: 390, alignment: .topLeading)
                .background(surface)
                .environmentObject(pinManager)
                .environment(\.colorScheme, scheme)

                let host = hostForMeasurement(sheet, at: typeSize)
                host.overrideUserInterfaceStyle = uiStyle
                let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 4200))
                let bounds = CGRect(origin: .zero, size: CGSize(width: 390, height: max(900, ceil(fitting.height) + 12)))
                host.view.frame = bounds

                let window: UIWindow
                if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                    window = UIWindow(windowScene: scene)
                } else {
                    window = UIWindow(frame: bounds)
                }
                window.frame = bounds
                window.overrideUserInterfaceStyle = uiStyle
                window.rootViewController = host
                window.isHidden = false
                defer {
                    window.isHidden = true
                    window.rootViewController = nil
                }

                let until = Date().addingTimeInterval(0.20)
                repeat {
                    host.view.setNeedsLayout()
                    host.view.layoutIfNeeded()
                    RunLoop.current.run(until: Date().addingTimeInterval(0.015))
                } while Date() < until

                let fmt = UIGraphicsImageRendererFormat()
                fmt.scale = 3.0
                let img = UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
                    if !host.view.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                        host.view.layer.render(in: ctx.cgContext)
                    }
                }

                let req = VNRecognizeTextRequest()
                req.recognitionLevel = .accurate
                try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
                let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
                let joined = lines.joined(separator: " | ")
                let spaceJoined = lines.joined(separator: " ")

                XCTAssertTrue(spaceJoined.contains("Loading win chance"), "Expected loading label (\(typeTag), \(scheme)); got: \(joined)")
                XCTAssertTrue(spaceJoined.contains("Nuggets win chance"), "Expected Nuggets win chance header (\(typeTag), \(scheme)); got: \(joined)")
                XCTAssertTrue(spaceJoined.contains("Rallied from 14%"), "Expected Rallied from 14% summary (\(typeTag), \(scheme)); got: \(joined)")
                XCTAssertTrue(spaceJoined.contains("Jazz win chance"), "Expected Jazz win chance header (\(typeTag), \(scheme)); got: \(joined)")
                XCTAssertTrue(spaceJoined.contains("Opened at 15%"), "Expected Upset · Opened at 15% summary (\(typeTag), \(scheme)); got: \(joined)")
                XCTAssertFalse(
                    lines.contains(where: { $0.contains("…") || $0.contains("...") }),
                    "Discover cards (\(typeTag), \(scheme)) must have zero ellipsis; got: \(joined)"
                )

                if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_13091"], !outDir.isEmpty {
                    let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                    try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                    let schemeTag = scheme == .dark ? "dark" : "light"
                    if let png = img.pngData() {
                        try png.write(to: dirURL.appendingPathComponent("13091-13092-discover-chart-\(typeTag)-\(schemeTag)-390.png"))
                    }
                }
            }
        }
    }
    #endif
}
