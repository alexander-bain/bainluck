import Charts
import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13773 & #13778 part 1:
/// 1. Suppress small Discover card charts whose series moves less than 2 pp.
/// 2. Always label dates/times beneath every small card chart that is drawn.
@MainActor
final class DiscoverCardChartsFlatAndDates13773Tests: XCTestCase {

    private func decodeJSON<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(T.self, from: Data(json.utf8))
    }

    private func recognizeText(in image: UIImage) -> String {
        guard let cg = image.cgImage else { return "" }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
    }

    // MARK: - Unit Rules

    func testFlatAndMovingThresholdsAcrossTwoWayThreeWayAndKitLines() {
        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingSpread([]))
        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingSpread([0.50]))
        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingSpread([0.50, 0.50]))
        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingSpread([0.50, 0.519]))
        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingSpread([.nan, 0.50, 0.51]))
        XCTAssertTrue(DiscoverCardChartRules13773.hasMovingSpread([0.50, 0.52]))
        XCTAssertTrue(DiscoverCardChartRules13773.hasMovingSpread([0.85, 0.14]))

        let t0 = Date(timeIntervalSince1970: 1_795_000_000)
        let flatThreeWay: [SoccerThreeLineChart211A.Point] = [
            .init(id: 0, date: t0, home: 0.45, draw: 0.25, away: 0.30, isLiveEdge: false, isOpening: true, isSolidMark: false, isEndpoint: false),
            .init(id: 1, date: t0.addingTimeInterval(600), home: 0.46, draw: 0.24, away: 0.30, isLiveEdge: true, isOpening: false, isSolidMark: true, isEndpoint: true),
        ]
        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingThreeWaySpread(flatThreeWay))

        let movingThreeWay: [SoccerThreeLineChart211A.Point] = [
            .init(id: 0, date: t0, home: 0.45, draw: 0.25, away: 0.30, isLiveEdge: false, isOpening: true, isSolidMark: false, isEndpoint: false),
            .init(id: 1, date: t0.addingTimeInterval(600), home: 0.48, draw: 0.24, away: 0.28, isLiveEdge: true, isOpening: false, isSolidMark: true, isEndpoint: true),
        ]
        XCTAssertTrue(DiscoverCardChartRules13773.hasMovingThreeWaySpread(movingThreeWay))

        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingKitLine([
            KitV1LinePoint(x: 0, y: 0.50, label: "Nov 1"),
            KitV1LinePoint(x: 1, y: 0.51, label: "Nov 25"),
        ]))
        XCTAssertTrue(DiscoverCardChartRules13773.hasMovingKitLine([
            KitV1LinePoint(x: 0, y: 0.50, label: "Nov 1"),
            KitV1LinePoint(x: 1, y: 0.55, label: "Nov 25"),
        ]))
        XCTAssertFalse(DiscoverCardChartRules13773.hasMovingKitLine([
            KitV1LinePoint(x: 0, y: 50, label: "Nov 1"),
            KitV1LinePoint(x: 1, y: 51, label: "Nov 25"),
        ]))
        XCTAssertTrue(DiscoverCardChartRules13773.hasMovingKitLine([
            KitV1LinePoint(x: 0, y: 40, label: "Nov 1"),
            KitV1LinePoint(x: 1, y: 63, label: "Nov 25"),
        ]))
    }

    func testAxisEndLabelsFormatSameDayOvernightMultiDayAndCrossYear() {
        let est = TimeZone(identifier: "America/New_York")!
        let sameDay = DiscoverCardChartRules13773.axisEndLabels(
            startIso: "2026-11-19T18:00:00Z",
            endIso: "2026-11-19T20:30:00Z",
            timeZone: est
        )
        XCTAssertEqual(sameDay?.start, "Nov 19, 1:00 PM")
        XCTAssertEqual(sameDay?.end, "3:30 PM")

        let overnight = DiscoverCardChartRules13773.axisEndLabels(
            startIso: "2026-11-19T03:30:00Z",
            endIso: "2026-11-19T06:15:00Z",
            timeZone: est
        )
        XCTAssertEqual(overnight?.start, "Nov 18, 10:30 PM")
        XCTAssertEqual(overnight?.end, "Nov 19, 1:15 AM")

        let multiDay = DiscoverCardChartRules13773.axisEndLabels(
            startIso: "2026-10-28T00:00:00Z",
            endIso: "2026-11-25T18:00:00Z",
            timeZone: est
        )
        XCTAssertEqual(multiDay?.start, "Oct 27")
        XCTAssertEqual(multiDay?.end, "Nov 25")

        let crossYear = DiscoverCardChartRules13773.axisEndLabels(
            startIso: "2026-12-20T12:00:00Z",
            endIso: "2027-01-15T12:00:00Z",
            timeZone: est
        )
        XCTAssertEqual(crossYear?.start, "Dec 20, 2026")
        XCTAssertEqual(crossYear?.end, "Jan 15, 2027")
    }

    // MARK: - View Suppression, X-Axis Dates & iPad Renders

    func testFlatChartsSuppressCompletelyAndMovingChartsDrawXAxisDatesAtIPadWidth() throws {
        let flatEvent = try decodeJSON(FeedEventData.self, """
        {
          "id": 1377301,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Atlanta Hawks",
          "home_team": "Boston Celtics",
          "commence_time": "2026-11-25T18:00:00Z",
          "status": "live",
          "away_score": 14,
          "home_score": 16,
          "away_team_data": {"primary_color": "#E03A3E", "abbreviation": "ATL"},
          "home_team_data": {"primary_color": "#007A33", "abbreviation": "BOS"},
          "current_odds": {"away_probability": 0.25, "home_probability": 0.75},
          "prematch_odds": {"away_probability": 0.25, "home_probability": 0.75}
        }
        """)
        let flatHistory = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 1377301,
          "home_team": "Boston Celtics",
          "away_team": "Atlanta Hawks",
          "status": "live",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-25T18:00:00Z", "home_probability": 0.750},
              {"timestamp": "2026-11-25T18:20:00Z", "home_probability": 0.758}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-25T18:00:00Z", "home_probability": 0.750},
            {"timestamp": "2026-11-25T18:10:00Z", "home_probability": 0.755},
            {"timestamp": "2026-11-25T18:20:00Z", "home_probability": 0.758}
          ]
        }
        """)

        let movingEvent = try decodeJSON(FeedEventData.self, """
        {
          "id": 1377302,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Denver Nuggets",
          "commence_time": "2026-11-19T18:00:00Z",
          "status": "completed",
          "away_score": 101,
          "home_score": 105,
          "away_team_data": {"primary_color": "#007A33", "abbreviation": "BOS"},
          "home_team_data": {"primary_color": "#0E2240", "secondary_color": "#FEC524", "abbreviation": "DEN"},
          "prematch_odds": {"away_probability": 0.52, "home_probability": 0.48, "source": "kalshi"},
          "pregame_projection": {"projected_away_score": 111.0, "projected_home_score": 109.0, "source": "sportsbooks", "unit": "points", "period": "full_game"}
        }
        """)
        let movingHistory = try decodeJSON(EventHistoryResponse.self, """
        {
          "event_id": 1377302,
          "home_team": "Denver Nuggets",
          "away_team": "Boston Celtics",
          "status": "completed",
          "completed_at": "2026-11-19T20:32:00Z",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-19T18:00:00Z", "home_probability": 0.48},
              {"timestamp": "2026-11-19T20:30:00Z", "home_probability": 1.0}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-19T18:00:00Z", "home_probability": 0.48},
            {"timestamp": "2026-11-19T18:45:00Z", "home_probability": 0.24},
            {"timestamp": "2026-11-19T19:35:00Z", "home_probability": 0.41},
            {"timestamp": "2026-11-19T20:30:00Z", "home_probability": 1.0}
          ]
        }
        """)

        let nyTZ = TimeZone(identifier: "America/New_York")!
        let flatPrematch = PrematchReading.resolve(prematch: flatEvent.prematchOdds, opening: flatEvent.openingOdds)
        let movingPrematch = PrematchReading.resolve(prematch: movingEvent.prematchOdds, opening: movingEvent.openingOdds)

        // 1. DiscoverPictureChartPanel191AView: flat suppresses to 0 height, moving preserves loading-height parity
        let flatPanel = DiscoverPictureChartPanel191AView(
            event: flatEvent,
            prematch: flatPrematch,
            awayColor: Color(hex: "#E03A3E"),
            homeColor: Color(hex: "#007A33"),
            preloadedHistory: flatHistory
        )
        .frame(width: 360)
        let flatSize = hostForMeasurement(flatPanel, at: .large).sizeThatFits(in: CGSize(width: 360, height: 500))
        XCTAssertLessThanOrEqual(flatSize.height, 1.0, "Flat < 2 pp game chart must not render")

        let movingLoadingPanel = DiscoverPictureChartPanel191AView(
            event: movingEvent,
            prematch: movingPrematch,
            awayColor: Color(hex: "#007A33"),
            homeColor: Color(hex: "#0E2240"),
            preloadedHistory: nil,
            isLoadingOverrideForTesting: true
        )
        .environment(\.timeZone, nyTZ)
        .frame(width: 360)
        let movingLoadedPanel = DiscoverPictureChartPanel191AView(
            event: movingEvent,
            prematch: movingPrematch,
            awayColor: Color(hex: "#007A33"),
            homeColor: Color(hex: "#0E2240"),
            preloadedHistory: movingHistory
        )
        .environment(\.timeZone, nyTZ)
        .frame(width: 360)
        let loadingSize = hostForMeasurement(movingLoadingPanel, at: .large).sizeThatFits(in: CGSize(width: 360, height: 600))
        let loadedSize = hostForMeasurement(movingLoadedPanel, at: .large).sizeThatFits(in: CGSize(width: 360, height: 600))
        XCTAssertGreaterThan(loadedSize.height, 120)
        XCTAssertEqual(loadingSize.height, loadedSize.height, accuracy: 4.0)

        let moving191Renderer = rendererForMeasurement(
            movingLoadedPanel.padding(12).background(Color.white),
            at: .large
        )
        moving191Renderer.scale = 2.0
        let moving191OCR = recognizeText(in: try XCTUnwrap(moving191Renderer.uiImage))
        XCTAssertTrue(moving191OCR.contains("Nov 19"), "Expected Nov 19 date on 191-A chart x-axis: \(moving191OCR)")
        XCTAssertTrue(moving191OCR.contains("PM"), "Expected start/end time on intraday 191-A chart x-axis: \(moving191OCR)")

        // 2. MachineryHistoryChartCardView: flat suppresses to 0 height, moving renders dates beneath plot
        let flatMachinery = MachineryHistoryChartItem(
            marketId: 7001,
            title: "Grammys Pop Vocal Album",
            startIso: "2026-11-01T12:00:00Z",
            endIso: "2026-11-25T12:00:00Z",
            yMin: 0,
            yMax: 100,
            moved: true,
            series: [
                MachineryHistorySeries(
                    outcomeId: 1,
                    name: "Choosin' Texas",
                    currentPct: 50,
                    color: "#2563EB",
                    points: [
                        MachineryHistorySeriesPoint(t: "2026-11-01T12:00:00Z", pct: 50),
                        MachineryHistorySeriesPoint(t: "2026-11-25T12:00:00Z", pct: 51),
                    ]
                )
            ]
        )
        let flatMachSize = hostForMeasurement(
            MachineryHistoryChartCardView(chart: flatMachinery, compact: true).frame(width: 360),
            at: .large
        ).sizeThatFits(in: CGSize(width: 360, height: 500))
        XCTAssertLessThanOrEqual(flatMachSize.height, 1.0, "Flat < 2 pp machinery chart must suppress cleanly")

        let movingMachinery = MachineryHistoryChartItem(
            marketId: 7002,
            title: "Odds - Tech & AI",
            startIso: "2026-11-01T12:00:00Z",
            endIso: "2026-11-25T12:00:00Z",
            yMin: 0,
            yMax: 40,
            moved: true,
            series: [
                MachineryHistorySeries(
                    outcomeId: 2,
                    name: "CoreWeave",
                    currentPct: 18,
                    color: "#2563EB",
                    points: [
                        MachineryHistorySeriesPoint(t: "2026-11-01T12:00:00Z", pct: 32),
                        MachineryHistorySeriesPoint(t: "2026-11-12T12:00:00Z", pct: 24),
                        MachineryHistorySeriesPoint(t: "2026-11-25T12:00:00Z", pct: 18),
                    ]
                ),
                MachineryHistorySeries(
                    outcomeId: 3,
                    name: "Anthropic",
                    currentPct: 9,
                    color: "#059669",
                    points: [
                        MachineryHistorySeriesPoint(t: "2026-11-01T12:00:00Z", pct: 5),
                        MachineryHistorySeriesPoint(t: "2026-11-12T12:00:00Z", pct: 7),
                        MachineryHistorySeriesPoint(t: "2026-11-25T12:00:00Z", pct: 9),
                    ]
                ),
            ]
        )
        let movingMachView = MachineryHistoryChartCardView(chart: movingMachinery, compact: true)
            .environment(\.timeZone, nyTZ)
            .frame(width: 360)
        let movingMachSize = hostForMeasurement(movingMachView, at: .large).sizeThatFits(in: CGSize(width: 360, height: 500))
        XCTAssertGreaterThan(movingMachSize.height, 120)
        let movingMachRenderer = rendererForMeasurement(movingMachView.padding(12).background(Color.white), at: .large)
        movingMachRenderer.scale = 2.0
        let movingMachOCR = recognizeText(in: try XCTUnwrap(movingMachRenderer.uiImage))
        XCTAssertTrue(movingMachOCR.contains("Nov 1"), "Expected start date Nov 1 beneath machinery chart: \(movingMachOCR)")
        XCTAssertTrue(movingMachOCR.contains("Nov 25"), "Expected end date Nov 25 beneath machinery chart: \(movingMachOCR)")

        // 3. KitLineMarkView366B & KitCardView366B: flat suppresses, moving draws with date ticks
        let flatKitLine = KitV1LineMark(
            points: [
                KitV1LinePoint(x: 0, y: 0.42, label: "Nov 1"),
                KitV1LinePoint(x: 1, y: 0.428, label: "Nov 25"),
            ],
            dashed: false,
            color: KitV1AdaptiveHex(light: "#2563EB", dark: "#60A5FA"),
            colorDark: nil,
            threshold: nil
        )
        let flatKitSize = hostForMeasurement(
            KitLineMarkView366B(mark: flatKitLine).frame(width: 360),
            at: .large
        ).sizeThatFits(in: CGSize(width: 360, height: 200))
        XCTAssertLessThanOrEqual(flatKitSize.height, 1.0, "Flat < 2 pp KitLineMark must suppress")

        let movingKitLine = KitV1LineMark(
            points: [
                KitV1LinePoint(x: 0, y: 0.12, label: "Nov 1"),
                KitV1LinePoint(x: 1, y: 0.34, label: "Nov 25"),
            ],
            dashed: false,
            color: KitV1AdaptiveHex(light: "#2563EB", dark: "#60A5FA"),
            colorDark: nil,
            threshold: nil
        )
        let movingKitSize = hostForMeasurement(
            KitLineMarkView366B(mark: movingKitLine).frame(width: 360),
            at: .large
        ).sizeThatFits(in: CGSize(width: 360, height: 200))
        XCTAssertGreaterThanOrEqual(movingKitSize.height, 30)

        let kitMovingSpec = try XCTUnwrap(KitV1CardSpec.parse(from: Data("""
        {
          "kit_version": 1,
          "id": "kit-moving-line-13773",
          "layout": "axis",
          "kicker": "Economics",
          "common_headline": "Federal Reserve Rate Cut by Dec 2026?",
          "body": {
            "scale": {
              "scale_kind": "time",
              "unit": "",
              "min": 0.0,
              "max": 1.0,
              "ticks": [
                {"x": 0.0, "label": "Nov 1"},
                {"x": 0.5, "label": "Nov 13"},
                {"x": 1.0, "label": "Nov 25"}
              ]
            },
            "marks": [
              {
                "mark": "line",
                "points": [
                  {"x": 0.0, "y": 0.12, "label": "Nov 1"},
                  {"x": 0.5, "y": 0.21, "label": "Nov 13"},
                  {"x": 1.0, "y": 0.34, "label": "Nov 25"}
                ],
                "dashed": false,
                "color": {"light": "#2563EB", "dark": "#60A5FA"}
              }
            ]
          }
        }
        """.utf8)))

        // Optional iPad-width Light & Dark captures when env var is set
        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13773_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

            for (schemeName, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
                let surfaceBg = scheme == .dark ? Color(white: 0.08) : Color(white: 0.955)
                let cardBg = scheme == .dark ? Color(hex: "#1C1C1E") : Color.white
                let colWidth: CGFloat = 385

                let grid = VStack(alignment: .leading, spacing: 14) {
                    Text("iPad 834 pt (\(schemeName.capitalized)) — #13773 & #13778 Part 1")
                        .font(.headline.bold())
                        .foregroundStyle(scheme == .dark ? Color.white : Color.black)

                    HStack(alignment: .top, spacing: 16) {
                        // Col 1: Flat charts suppressed
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Flat (< 2 pp) small card charts suppressed")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Hawks vs Celtics · Live (75% flat)")
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(scheme == .dark ? Color.white : Color.black)
                                DiscoverPictureChartPanel191AView(
                                    event: flatEvent,
                                    prematch: flatPrematch,
                                    awayColor: Color(hex: "#E03A3E"),
                                    homeColor: Color(hex: "#007A33"),
                                    preloadedHistory: flatHistory
                                )
                                Text("Chart suppressed because spread < 2 pp.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(14)
                            .frame(width: colWidth, alignment: .leading)
                            .background(cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Grammys Pop Vocal Album (50%–51% flat)")
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(scheme == .dark ? Color.white : Color.black)
                                MachineryHistoryChartCardView(chart: flatMachinery, compact: true)
                                Text("Mini-chart suppressed because spread < 2 pp.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .padding(14)
                            .frame(width: colWidth, alignment: .leading)
                            .background(cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        }

                        // Col 2: Moving charts drawn WITH x-axis dates
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Moving (>= 2 pp) charts with x-axis dates")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Celtics 101 at Nuggets 105 · Final")
                                    .font(.subheadline.weight(.bold))
                                    .foregroundStyle(scheme == .dark ? Color.white : Color.black)
                                DiscoverPictureChartPanel191AView(
                                    event: movingEvent,
                                    prematch: movingPrematch,
                                    awayColor: Color(hex: "#007A33"),
                                    homeColor: Color(hex: scheme == .dark ? "#FEC524" : "#0E2240"),
                                    preloadedHistory: movingHistory
                                )
                            }
                            .padding(14)
                            .frame(width: colWidth, alignment: .leading)
                            .background(cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))

                            VStack(alignment: .leading, spacing: 8) {
                                MachineryHistoryChartCardView(chart: movingMachinery, compact: true)
                            }
                            .frame(width: colWidth, alignment: .leading)

                            if let kitCard = KitCardView366B(spec: kitMovingSpec) {
                                kitCard
                                    .frame(width: colWidth, alignment: .leading)
                            }
                        }
                    }
                }
                .padding(24)
                .frame(width: 834, alignment: .leading)
                .background(surfaceBg)
                .environment(\.colorScheme, scheme)
                .environment(\.timeZone, nyTZ)
                .environment(\.horizontalSizeClass, .regular)

                let renderer = rendererForMeasurement(grid, at: .large)
                renderer.scale = 2.0
                let img = try XCTUnwrap(renderer.uiImage)
                try XCTUnwrap(img.pngData()).write(
                    to: URL(fileURLWithPath: outDir).appendingPathComponent("ipad-834-\(schemeName).png")
                )
            }
        }
    }
}
