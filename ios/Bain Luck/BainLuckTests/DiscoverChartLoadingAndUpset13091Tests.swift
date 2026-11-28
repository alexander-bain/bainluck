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
///    pregame-to-final outcome (`"Upset · 15% pregame"`, `"Rallied from 14%"`,
///    `"64% pregame · Won"`) with zero model-written text and zero `"…"`.
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
        XCTAssertEqual(jazzChartModel.finishedSummaryLabel, "Upset · 15% pregame")

        // 3. Favorite win with no deep dip -> "<N>% pregame · Won" (never "Opened at")
        let favEvent = try decodeEvent(#"""
        {
          "id": 15350800,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Miami Heat",
          "home_team": "Boston Celtics",
          "commence_time": "2026-11-19T00:30:00Z",
          "status": "completed",
          "away_score": 98,
          "home_score": 112,
          "prematch_odds": {"away_probability": 0.36, "home_probability": 0.64, "away_rendered_percent": 36, "home_rendered_percent": 64, "source": "kalshi"}
        }
        """#)
        let favHistory = try decodeHistory(#"""
        {
          "event_id": 15350800,
          "home_team": "Boston Celtics",
          "away_team": "Miami Heat",
          "status": "completed",
          "completed_at": "2026-11-19T02:55:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T00:28:00Z", "home_probability": 0.64},
              {"timestamp": "2026-11-19T02:52:00Z", "home_probability": 1.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T00:28:00Z", "home_probability": 0.64},
            {"timestamp": "2026-11-19T01:15:00Z", "home_probability": 0.72},
            {"timestamp": "2026-11-19T02:52:00Z", "home_probability": 1.0}
          ]
        }
        """#)
        let favPrematch = PrematchReading.resolve(prematch: favEvent.prematchOdds, opening: favEvent.openingOdds)
        let favModel = DiscoverPictureChart191A.build(
            event: favEvent,
            prematch: favPrematch,
            history: favHistory
        )
        XCTAssertEqual(favModel.finishedSummaryLabel, "64% pregame · Won")
    }

    func testLiveJazz13092RowAndChartBadgeAgreeWhenServerRoundsHalfDown() throws {
        // Live #13092 payload shape: Jazz 109 @ Lakers 97 where server paired rounding
        // gives 0.175 -> 17% and 0.825 -> 83%. Chart header and leftEndLabel must match
        // the card row's 17% instead of independently rounding 0.175 to 18%.
        let liveJazzEvent = try decodeEvent(#"""
        {
          "id": 15350792,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Utah Jazz",
          "home_team": "Los Angeles Lakers",
          "commence_time": "2026-11-19T03:00:00Z",
          "status": "completed",
          "away_score": 109,
          "home_score": 97,
          "away_team_data": {"primary_color": "#002B5C", "secondary_color": "#F9A01B", "abbreviation": "UTA"},
          "home_team_data": {"primary_color": "#552583", "secondary_color": "#FDB927", "abbreviation": "LAL"},
          "prematch_odds": {
            "away_probability": 0.175,
            "home_probability": 0.825,
            "away_rendered_percent": 17,
            "home_rendered_percent": 83,
            "source": "kalshi"
          },
          "pregame_projection": {
            "projected_away_score": 109.0,
            "projected_home_score": 121.0,
            "source": "sportsbooks",
            "unit": "points",
            "period": "full_game"
          }
        }
        """#)
        let liveJazzHistory = try decodeHistory(#"""
        {
          "event_id": 15350792,
          "home_team": "Los Angeles Lakers",
          "away_team": "Utah Jazz",
          "status": "completed",
          "completed_at": "2026-11-19T05:35:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T02:58:00Z", "home_probability": 0.825},
              {"timestamp": "2026-11-19T05:32:00Z", "home_probability": 0.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T02:58:00Z", "home_probability": 0.825},
            {"timestamp": "2026-11-19T04:00:00Z", "home_probability": 0.70},
            {"timestamp": "2026-11-19T05:32:00Z", "home_probability": 0.0}
          ]
        }
        """#)
        let prematch = try XCTUnwrap(PrematchReading.resolve(prematch: liveJazzEvent.prematchOdds, opening: liveJazzEvent.openingOdds))
        let cardModel = DiscoverSingleGameCard190C.build(
            event: liveJazzEvent,
            prematch: prematch,
            showsInlinePregame: true,
            usesPictureLayout: true
        )
        XCTAssertEqual(cardModel.rows.map(\.pregameText), ["17%", "83%"])

        let chartModel = DiscoverPictureChart191A.build(
            event: liveJazzEvent,
            prematch: prematch,
            history: liveJazzHistory
        )
        XCTAssertEqual(chartModel.leftEndLabel, "Pregame 17% UTA")
        XCTAssertEqual(chartModel.finishedSummaryLabel, "Upset · 17% pregame")

        // Sub-1% upset & rally never print 0%
        let subOneEvent = try decodeEvent(#"""
        {
          "id": 15350999,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Utah Jazz",
          "home_team": "Los Angeles Lakers",
          "away_team_data": {"abbreviation": "UTA"},
          "commence_time": "2026-11-19T03:00:00Z",
          "status": "completed",
          "away_score": 109,
          "home_score": 97,
          "prematch_odds": {
            "away_probability": 0.004,
            "home_probability": 0.996,
            "away_rendered_percent": 0,
            "home_rendered_percent": 100,
            "source": "kalshi"
          }
        }
        """#)
        let subOnePrematch = try XCTUnwrap(PrematchReading.resolve(prematch: subOneEvent.prematchOdds, opening: nil))
        let subOneChart = DiscoverPictureChart191A.build(event: subOneEvent, prematch: subOnePrematch, history: liveJazzHistory)
        XCTAssertEqual(subOneChart.leftEndLabel, "Pregame <1% UTA")
        XCTAssertEqual(subOneChart.finishedSummaryLabel, "Upset · <1% pregame")

        let deepRallyEvent = try decodeEvent(#"""
        {
          "id": 15351000,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Denver Nuggets",
          "commence_time": "2026-11-19T02:00:00Z",
          "status": "completed",
          "away_score": 101,
          "home_score": 105,
          "prematch_odds": {
            "away_probability": 0.45,
            "home_probability": 0.55,
            "away_rendered_percent": 45,
            "home_rendered_percent": 55,
            "source": "kalshi"
          }
        }
        """#)
        let deepRallyHistory = try decodeHistory(#"""
        {
          "event_id": 15351000,
          "home_team": "Denver Nuggets",
          "away_team": "Boston Celtics",
          "status": "completed",
          "completed_at": "2026-11-19T04:32:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T02:00:00Z", "home_probability": 0.55},
              {"timestamp": "2026-11-19T04:30:00Z", "home_probability": 1.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T02:00:00Z", "home_probability": 0.55},
            {"timestamp": "2026-11-19T03:55:00Z", "home_probability": 0.004},
            {"timestamp": "2026-11-19T04:30:00Z", "home_probability": 1.0}
          ]
        }
        """#)
        let rallyPrematch = try XCTUnwrap(PrematchReading.resolve(prematch: deepRallyEvent.prematchOdds, opening: nil))
        let rallyChart = DiscoverPictureChart191A.build(event: deepRallyEvent, prematch: rallyPrematch, history: deepRallyHistory)
        XCTAssertEqual(rallyChart.finishedSummaryLabel, "Rallied from <1%")
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

                    // 3. Loaded #13092 Jazz upset card (`prematch_odds` recovered from history -> `15%` / `85%` + `Upset · 15% pregame`)
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
                XCTAssertTrue(spaceJoined.contains("15% pregame"), "Expected Upset · 15% pregame summary (\(typeTag), \(scheme)); got: \(joined)")
                XCTAssertFalse(spaceJoined.contains("Opened at"), "Discover summary must never use 'Opened at' (\(typeTag), \(scheme)); got: \(joined)")
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

    func testLiveJazz13092RenderParity390LightAndDark() throws {
        let liveJazzEvent = try decodeEvent(#"""
        {
          "id": 15350792,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Utah Jazz",
          "home_team": "Los Angeles Lakers",
          "commence_time": "2026-11-19T03:00:00Z",
          "status": "completed",
          "away_score": 109,
          "home_score": 97,
          "away_team_data": {"primary_color": "#0e2240", "secondary_color": "#fec524", "abbreviation": "UTA"},
          "home_team_data": {"primary_color": "#552583", "secondary_color": "#FDB927", "abbreviation": "LAL"},
          "prematch_odds": {
            "away_probability": 0.175,
            "home_probability": 0.825,
            "away_rendered_percent": 17,
            "home_rendered_percent": 83,
            "source": "kalshi"
          },
          "pregame_projection": {
            "projected_away_score": 109.0,
            "projected_home_score": 121.0,
            "source": "sportsbooks",
            "unit": "points",
            "period": "full_game"
          }
        }
        """#)
        let liveJazzHistory = try decodeHistory(#"""
        {
          "event_id": 15350792,
          "home_team": "Los Angeles Lakers",
          "away_team": "Utah Jazz",
          "status": "completed",
          "completed_at": "2026-11-19T05:35:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T02:58:00Z", "home_probability": 0.825},
              {"timestamp": "2026-11-19T05:32:00Z", "home_probability": 0.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T03:00:00Z", "home_probability": 0.812},
            {"timestamp": "2026-11-19T03:16:00Z", "home_probability": 0.7354},
            {"timestamp": "2026-11-19T03:40:00Z", "home_probability": 0.8530},
            {"timestamp": "2026-11-19T03:48:00Z", "home_probability": 0.8771},
            {"timestamp": "2026-11-19T04:12:00Z", "home_probability": 0.7198},
            {"timestamp": "2026-11-19T04:37:00Z", "home_probability": 0.6330},
            {"timestamp": "2026-11-19T04:45:00Z", "home_probability": 0.7927},
            {"timestamp": "2026-11-19T05:09:00Z", "home_probability": 0.4816},
            {"timestamp": "2026-11-19T05:17:00Z", "home_probability": 0.2333},
            {"timestamp": "2026-11-19T05:25:00Z", "home_probability": 0.0255},
            {"timestamp": "2026-11-19T05:32:00Z", "home_probability": 0.0}
          ]
        }
        """#)

        let pinDefaults = UserDefaults(suiteName: "test.13092.parity.\(UUID().uuidString)")!
        let pinManager = PinManager(defaults: pinDefaults, allowLegacyGuestPins: false)

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let surface = scheme == .dark ? Color.black : Color(white: 0.955)
            let sheet = NativeEventDiscoverCard(
                event: liveJazzEvent,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: liveJazzHistory
            )
            .environment(\.discoverCardLikeAction420D, DiscoverCardLikeAction420D(
                itemKey: "event-15350792",
                isLiked: false,
                pinType: "event",
                pinId: 15350792,
                shareURL: URL(string: "https://bainluck.com/discover"),
                shareTitle: "Utah Jazz at Los Angeles Lakers",
                onToggle: {},
                onShare: {}
            ))
            .padding(16)
            .fixedSize(horizontal: false, vertical: true)
            .frame(width: 422, alignment: .topLeading)
            .background(surface)
            .environmentObject(pinManager)
            .environment(\.colorScheme, scheme)

            let host = hostForMeasurement(sheet, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let fitting = host.sizeThatFits(in: CGSize(width: 422, height: 1400))
            let bounds = CGRect(origin: .zero, size: CGSize(width: 422, height: ceil(fitting.height) + 4))
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

            for _ in 0..<4 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.02))
            }

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            let img = UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
                if !host.view.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                    host.view.layer.render(in: ctx.cgContext)
                }
            }

            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
            let spaceJoined = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")

            XCTAssertTrue(spaceJoined.contains("17%"), "Expected 17% pregame row in \(scheme); got: \(spaceJoined)")
            XCTAssertTrue(spaceJoined.contains("83%"), "Expected 83% pregame row in \(scheme); got: \(spaceJoined)")
            XCTAssertTrue(spaceJoined.contains("17% pregame"), "Expected Upset · 17% pregame pill in \(scheme); got: \(spaceJoined)")
            XCTAssertFalse(spaceJoined.contains("18% pregame"), "Must not show 18% pregame mismatch in \(scheme); got: \(spaceJoined)")

            if let outDir = ProcessInfo.processInfo.environment["BAINLUCK_13092_FIX_RENDER_DIR"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let schemeTag = scheme == .dark ? "dark" : "light"
                try XCTUnwrap(img.pngData()).write(
                    to: dirURL.appendingPathComponent("13092-after-\(schemeTag).png"),
                    options: .atomic
                )
            }
        }
    }
    #endif
}
