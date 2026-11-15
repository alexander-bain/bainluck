import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Item 5 — Ruling 201 Chart Scale & Header Cleanup:
/// 1. Two teams or two players with no draw: keep the fitted vertical scale (`probabilityWindow9483` / `ChartProbabilityAxis9483.window`).
/// 2. Use `0` to `100` (`ChartProbabilityAxis9483.full`) only for soccer and anything with a draw, and for fields of more than two (golf, futures, multi-outcome props).
/// 3. Remove the legend line (`"Recorded reading"`, `"Change"`, etc.) and the `"Tap any reading for exact time (PT)"` line; keep one title row with the `All` / `Since Start` control (while preserving active scrub selection readout when `selection.date != nil`).
@MainActor
final class Ruling201ChartScaleAndHeaderTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T19:15:00Z")!

    private func makeDate(_ iso: String) -> Date {
        ISO8601DateFormatter().date(from: iso)!
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func collectTexts(in view: UIView) -> [String] {
        var found: [String] = []
        if let label = view as? UILabel, let text = label.text, !text.isEmpty, !label.isHidden, label.alpha > 0.01 {
            found.append(text)
        }
        for sub in view.subviews {
            found.append(contentsOf: collectTexts(in: sub))
        }
        return found
    }

    // MARK: - 1. Ruling 201 Sport & Field Scale Rule

    func testRuling201ScaleUsesFittedForTwoWayNonDrawAndZeroToHundredForDrawOrFieldOverTwo() throws {
        // Two-way non-draw sports keep fitted vertical scale
        for twoWaySport in [
            "americanfootball_nfl",
            "americanfootball_ncaaf",
            "basketball_nba",
            "basketball_ncaab",
            "baseball_mlb",
            "icehockey_nhl",
            "tennis_atp_us_open",
            "tennis_wta_australian_open",
            "mma_mixed_martial_arts",
        ] {
            XCTAssertFalse(
                OddsChartView.usesZeroToHundredVerticalScale201(sportKey: twoWaySport),
                "\(twoWaySport) has two sides and no draw -> must keep fitted vertical scale"
            )
        }

        // Soccer / draw-priced sports use 0 to 100
        for drawSport in [
            "soccer_epl",
            "soccer_uefa_champs_league",
            "soccer_usa_mls",
            "soccer_spain_la_liga",
        ] {
            XCTAssertTrue(
                OddsChartView.usesZeroToHundredVerticalScale201(sportKey: drawSport),
                "\(drawSport) prices a draw -> must use 0 to 100 scale"
            )
        }

        // Discover 191-A picture chart panel follows the exact same rule
        let t0 = makeDate("2026-11-15T18:00:00Z")
        let twoWayPoints: [DiscoverPictureChart191A.Point] = (0..<14).map { idx in
            DiscoverPictureChart191A.Point(
                id: idx,
                date: t0.addingTimeInterval(Double(idx) * 300),
                probability: 0.52 + Double(idx) * 0.01,
                isOpening: idx == 0,
                isSolidMark: true,
                isEndpoint: idx == 13
            )
        }
        let fittedDiscover = DiscoverPictureChartPanel191AView.verticalWindow201(
            sportKey: "americanfootball_nfl",
            points: twoWayPoints
        )
        XCTAssertNotEqual(fittedDiscover, ChartProbabilityAxis9483.full, "14-point live NFL trajectory uses fitted window")
        XCTAssertGreaterThan(fittedDiscover.lowerPercent, 0)
        XCTAssertLessThan(fittedDiscover.upperPercent, 100)

        let drawDiscover = DiscoverPictureChartPanel191AView.verticalWindow201(
            sportKey: "soccer_epl",
            points: twoWayPoints
        )
        XCTAssertEqual(drawDiscover, ChartProbabilityAxis9483.full, "Soccer uses 0 to 100 full window")

        // Fields of more than two (EvolutionChartView + Golf) use 0 to 100
        let sampleEntries: [EvolutionPoint] = [
            EvolutionPoint(date: t0, name: "Scheffler", probability: 24, isCombined: false, archive: nil),
            EvolutionPoint(date: t0.addingTimeInterval(3600), name: "Scheffler", probability: 28, isCombined: false, archive: nil),
        ]
        XCTAssertEqual(
            EvolutionChartView.yCeilingPercent192A(entries: sampleEntries, outcomeCount: 4),
            100.0,
            "Fields of more than two (outcomeCount = 4) must use 0 to 100"
        )
        XCTAssertEqual(
            EvolutionChartView.yCeilingPercent192A(entries: sampleEntries, outcomeCount: 2),
            50.0,
            "Two-outcome non-draw market keeps fitted ceiling"
        )
    }

    // MARK: - 2. Header At Rest Has Zero Legend & Zero Tap-Hint Lines; Scrub Still Works

    func testHeaderRemovesLegendAndTapHintAtRestWhileKeepingScrubReadoutAnd390Renders() async throws {
        let kickoff = makeDate("2026-11-15T18:00:00Z")
        let points: [ChartDataPoint] = (0..<14).map { idx in
            ChartDataPoint(
                date: kickoff.addingTimeInterval(Double(idx - 1) * 300),
                probability: 0.49 + Double(idx) * 0.013,
                source: "aggregate"
            )
        }

        // 1. Header view at rest has height 0 and emits no legend / tap-hint strings
        let restSelection = OddsChartSelection()
        let headerAtRest = EventAtlasChartHeaderView11666(
            selection: restSelection,
            dataPoints: points,
            checkpoints: nil,
            history: nil,
            status: "live",
            sides: .homeAndAway,
            includesOpening: true,
            homeName: "Lions",
            primaryColor: .blue,
            gameStart: kickoff
        )
        let restHost = hostForMeasurement(headerAtRest.frame(width: 358))
        let restFitted = restHost.sizeThatFits(in: CGSize(width: 358, height: 400))
        XCTAssertEqual(restFitted.height, 0, accuracy: 0.5, "EventAtlasChartHeaderView11666 must collapse to 0pt at rest")

        let sourceURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/EventAtlasChartMarks11666.swift")
        let marksSource = try String(contentsOf: sourceURL, encoding: .utf8)
        XCTAssertFalse(marksSource.contains("event.atlas.chartMarkKey"), "Legend mark-key row removed from view")
        XCTAssertFalse(marksSource.contains("event.atlas.selectedReadingPrompt"), "Tap-hint prompt row removed from view")

        // 2. Active scrub selection still renders exact PT timestamp readout
        let activeSelection = OddsChartSelection()
        activeSelection.hold(date: points[5].date)
        let headerScrubbing = EventAtlasChartHeaderView11666(
            selection: activeSelection,
            dataPoints: points,
            checkpoints: nil,
            history: nil,
            status: "live",
            sides: .homeAndAway,
            includesOpening: true,
            homeName: "Lions",
            primaryColor: .blue,
            gameStart: kickoff
        )
        let activeHost = hostForMeasurement(headerScrubbing.frame(width: 358))
        let activeFitted = activeHost.sizeThatFits(in: CGSize(width: 358, height: 400))
        XCTAssertGreaterThan(activeFitted.height, 24, "Active scrub selection readout remains visible when scrubbing")

        // 3. Full OddsChartView renders for NFL (fitted scale, 1 title row) vs Soccer (0-100% scale, 1 title row)
        let nflHistoryJSON = """
        {
          "event_id": 919901,
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "live",
          "win_prob_sources": {
            "aggregate": { "label": "Blended", "weight": 1.0 },
            "consensus": { "label": "Sportsbooks", "weight": 3.0 },
            "kalshi": { "label": "Kalshi", "weight": 0.8 }
          },
          "history": [
            { "timestamp": "2026-11-15T17:50:00Z", "home_probability": 0.580, "away_probability": 0.420 },
            { "timestamp": "2026-11-15T18:00:00Z", "home_probability": 0.565, "away_probability": 0.435 },
            { "timestamp": "2026-11-15T18:06:00Z", "home_probability": 0.530, "away_probability": 0.470 },
            { "timestamp": "2026-11-15T18:12:00Z", "home_probability": 0.492, "away_probability": 0.508 },
            { "timestamp": "2026-11-15T18:18:00Z", "home_probability": 0.515, "away_probability": 0.485 },
            { "timestamp": "2026-11-15T18:24:00Z", "home_probability": 0.548, "away_probability": 0.452 },
            { "timestamp": "2026-11-15T18:30:00Z", "home_probability": 0.575, "away_probability": 0.425 },
            { "timestamp": "2026-11-15T18:36:00Z", "home_probability": 0.605, "away_probability": 0.395 },
            { "timestamp": "2026-11-15T18:42:00Z", "home_probability": 0.590, "away_probability": 0.410 },
            { "timestamp": "2026-11-15T18:48:00Z", "home_probability": 0.618, "away_probability": 0.382 },
            { "timestamp": "2026-11-15T18:54:00Z", "home_probability": 0.635, "away_probability": 0.365 },
            { "timestamp": "2026-11-15T19:00:00Z", "home_probability": 0.648, "away_probability": 0.352 },
            { "timestamp": "2026-11-15T19:08:00Z", "home_probability": 0.654, "away_probability": 0.346 },
            { "timestamp": "2026-11-15T19:14:00Z", "home_probability": 0.662, "away_probability": 0.338 }
          ],
          "aggregate_line": [
            { "timestamp": "2026-11-15T17:50:00Z", "home_probability": 0.580, "away_probability": 0.420 },
            { "timestamp": "2026-11-15T18:00:00Z", "home_probability": 0.565, "away_probability": 0.435 },
            { "timestamp": "2026-11-15T18:06:00Z", "home_probability": 0.530, "away_probability": 0.470 },
            { "timestamp": "2026-11-15T18:12:00Z", "home_probability": 0.492, "away_probability": 0.508 },
            { "timestamp": "2026-11-15T18:18:00Z", "home_probability": 0.515, "away_probability": 0.485 },
            { "timestamp": "2026-11-15T18:24:00Z", "home_probability": 0.548, "away_probability": 0.452 },
            { "timestamp": "2026-11-15T18:30:00Z", "home_probability": 0.575, "away_probability": 0.425 },
            { "timestamp": "2026-11-15T18:36:00Z", "home_probability": 0.605, "away_probability": 0.395 },
            { "timestamp": "2026-11-15T18:42:00Z", "home_probability": 0.590, "away_probability": 0.410 },
            { "timestamp": "2026-11-15T18:48:00Z", "home_probability": 0.618, "away_probability": 0.382 },
            { "timestamp": "2026-11-15T18:54:00Z", "home_probability": 0.635, "away_probability": 0.365 },
            { "timestamp": "2026-11-15T19:00:00Z", "home_probability": 0.648, "away_probability": 0.352 },
            { "timestamp": "2026-11-15T19:08:00Z", "home_probability": 0.654, "away_probability": 0.346 },
            { "timestamp": "2026-11-15T19:14:00Z", "home_probability": 0.662, "away_probability": 0.338 }
          ]
        }
        """
        let nflHistory = try decodeHistory(nflHistoryJSON)
        let nflChart = OddsChartView(
            eventId: 919901,
            teamColors: (away: Color(hex: "#C60C30"), home: Color(hex: "#0076B6")),
            commenceTime: "2026-11-15T18:00:00Z",
            status: "live",
            homeTeamName: "Detroit Lions",
            awayTeamName: "New England Patriots",
            homeTeamAbbrev: "DET",
            awayTeamAbbrev: "NE",
            sportKey: "americanfootball_nfl",
            servedHomeProbability: 0.662,
            servedAwayProbability: 0.338,
            selectedRange: .constant(.sinceStart),
            preloadedHistory: nflHistory,
            preloadedHistoryGeneration: 1,
            selection: restSelection
        )
        let nflScrubbingSelection = OddsChartSelection()
        nflScrubbingSelection.hold(date: makeDate("2026-11-15T18:30:00Z"))
        let nflScrubbingChart = OddsChartView(
            eventId: 919901,
            teamColors: (away: Color(hex: "#C60C30"), home: Color(hex: "#0076B6")),
            commenceTime: "2026-11-15T18:00:00Z",
            status: "live",
            homeTeamName: "Detroit Lions",
            awayTeamName: "New England Patriots",
            homeTeamAbbrev: "DET",
            awayTeamAbbrev: "NE",
            sportKey: "americanfootball_nfl",
            servedHomeProbability: 0.662,
            servedAwayProbability: 0.338,
            selectedRange: .constant(.sinceStart),
            preloadedHistory: nflHistory,
            preloadedHistoryGeneration: 1,
            selection: nflScrubbingSelection
        )
        let nflAtRestHost = hostForMeasurement(nflChart.frame(width: 358))
        let nflScrubbingHost = hostForMeasurement(nflScrubbingChart.frame(width: 358))
        let nflAtRestFitted = nflAtRestHost.sizeThatFits(in: CGSize(width: 358, height: 800))
        let nflScrubbingFitted = nflScrubbingHost.sizeThatFits(in: CGSize(width: 358, height: 800))
        XCTAssertEqual(
            nflAtRestFitted.height,
            nflScrubbingFitted.height,
            accuracy: 0.5,
            "Scrubbing readout overlays the chart plot without shifting the plot vertically"
        )

        let soccerHistoryJSON = """
        {
          "event_id": 919902,
          "home_team": "Arsenal",
          "away_team": "Liverpool",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "live",
          "win_prob_sources": {
            "aggregate": { "label": "Blended", "weight": 1.0 }
          },
          "history": [
            { "timestamp": "2026-11-15T17:50:00Z", "home_probability": 0.440, "away_probability": 0.300 },
            { "timestamp": "2026-11-15T18:00:00Z", "home_probability": 0.450, "away_probability": 0.290 },
            { "timestamp": "2026-11-15T18:06:00Z", "home_probability": 0.460, "away_probability": 0.285 },
            { "timestamp": "2026-11-15T18:12:00Z", "home_probability": 0.475, "away_probability": 0.275 },
            { "timestamp": "2026-11-15T18:18:00Z", "home_probability": 0.490, "away_probability": 0.265 },
            { "timestamp": "2026-11-15T18:24:00Z", "home_probability": 0.510, "away_probability": 0.250 },
            { "timestamp": "2026-11-15T18:30:00Z", "home_probability": 0.525, "away_probability": 0.240 },
            { "timestamp": "2026-11-15T18:36:00Z", "home_probability": 0.540, "away_probability": 0.230 },
            { "timestamp": "2026-11-15T18:42:00Z", "home_probability": 0.535, "away_probability": 0.235 },
            { "timestamp": "2026-11-15T18:48:00Z", "home_probability": 0.550, "away_probability": 0.225 },
            { "timestamp": "2026-11-15T18:54:00Z", "home_probability": 0.565, "away_probability": 0.215 },
            { "timestamp": "2026-11-15T19:00:00Z", "home_probability": 0.580, "away_probability": 0.205 },
            { "timestamp": "2026-11-15T19:08:00Z", "home_probability": 0.590, "away_probability": 0.200 },
            { "timestamp": "2026-11-15T19:14:00Z", "home_probability": 0.605, "away_probability": 0.195 }
          ],
          "aggregate_line": [
            { "timestamp": "2026-11-15T17:50:00Z", "home_probability": 0.440 },
            { "timestamp": "2026-11-15T18:00:00Z", "home_probability": 0.450 },
            { "timestamp": "2026-11-15T18:06:00Z", "home_probability": 0.460 },
            { "timestamp": "2026-11-15T18:12:00Z", "home_probability": 0.475 },
            { "timestamp": "2026-11-15T18:18:00Z", "home_probability": 0.490 },
            { "timestamp": "2026-11-15T18:24:00Z", "home_probability": 0.510 },
            { "timestamp": "2026-11-15T18:30:00Z", "home_probability": 0.525 },
            { "timestamp": "2026-11-15T18:36:00Z", "home_probability": 0.540 },
            { "timestamp": "2026-11-15T18:42:00Z", "home_probability": 0.535 },
            { "timestamp": "2026-11-15T18:48:00Z", "home_probability": 0.550 },
            { "timestamp": "2026-11-15T18:54:00Z", "home_probability": 0.565 },
            { "timestamp": "2026-11-15T19:00:00Z", "home_probability": 0.580 },
            { "timestamp": "2026-11-15T19:08:00Z", "home_probability": 0.590 },
            { "timestamp": "2026-11-15T19:14:00Z", "home_probability": 0.605 }
          ]
        }
        """
        let soccerHistory = try decodeHistory(soccerHistoryJSON)
        let soccerChart = OddsChartView(
            eventId: 919902,
            teamColors: (away: Color(hex: "#00B2A9"), home: Color(hex: "#EF0107")),
            commenceTime: "2026-11-15T18:00:00Z",
            status: "live",
            homeTeamName: "Arsenal",
            awayTeamName: "Liverpool",
            homeTeamAbbrev: "ARS",
            awayTeamAbbrev: "LIV",
            sportKey: "soccer_epl",
            servedHomeProbability: 0.605,
            servedAwayProbability: nil,
            selectedRange: .constant(.sinceStart),
            preloadedHistory: soccerHistory,
            preloadedHistoryGeneration: 1
        )

        let sheet = VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text("NFL Live (2-Team, No Draw) · Fitted Scale")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                nflChart
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .padding(.horizontal, 16)
            }
            VStack(alignment: .leading, spacing: 4) {
                Text("Soccer Live (Draw Sport) · 0%–100% Scale")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 16)
                soccerChart
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .padding(.horizontal, 16)
            }
        }
        .padding(.vertical, 16)
        .frame(width: 390)
        .background(Color(uiColor: .systemGroupedBackground))
        .ignoresSafeArea()

        let host = hostForMeasurement(sheet.environment(\.colorScheme, .light), at: .large)
        host.additionalSafeAreaInsets = .zero
        host.overrideUserInterfaceStyle = .light
        let sheetHeight = ceil(host.sizeThatFits(in: CGSize(width: 390, height: 2200)).height)
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: sheetHeight))

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

        try await Task.sleep(nanoseconds: 350_000_000)
        let until = Date().addingTimeInterval(0.35)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until

        let renderedTexts = collectTexts(in: host.view).joined(separator: " | ")
        XCTAssertFalse(renderedTexts.contains("Recorded reading"), "Legend 'Recorded reading' must not render")
        XCTAssertFalse(renderedTexts.contains("Tap any reading"), "Tap hint must not render")

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_201_CHART_RENDERS_DIR"],
           !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            if let png = img.pngData() {
                try png.write(to: dirURL.appendingPathComponent("201-chart-fitted-nfl-vs-full-soccer-390.png"))
            }
        }
    }
}
