import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13689:
/// 1. On a long-horizon ("All") finished game chart, the trailing `Final` period chip
///    flips left of the terminal line/dot instead of clipping against the right edge (`"Fina"`).
/// 2. X-axis date ticks never emit a closing date past the last drawn data point
///    (e.g., `"Nov 26"` for a game whose last observation was Nov 22 PT / Nov 23 UTC).
@MainActor
final class OddsChartAllRangeEndMarkerAndAxis13689Tests: XCTestCase {
    private static let scratchDir = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch"
    private static let outputDir = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/13689-renders"

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    func testAllRangeLastAxisDateNeverExceedsLastPointDate() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let firstPoint = ISO8601DateFormatter().date(from: "2026-05-13T14:21:00Z")!
        let lastPoint = ISO8601DateFormatter().date(from: "2026-11-23T04:26:00Z")! // Nov 22, 8:26 PM PST

        let paddedDomain = OddsChartView.naturalDomain(of: [firstPoint, lastPoint])!
        XCTAssertGreaterThan(paddedDomain.upperBound, lastPoint)

        let dataRange = OddsChartView.dataDateRange(of: [firstPoint, lastPoint])!
        XCTAssertEqual(dataRange.lowerBound, firstPoint)
        XCTAssertEqual(dataRange.upperBound, lastPoint)

        for scaled: CGFloat in [12, 16] {
            let scale = EventChartTypography.labelSize(scaled: scaled) / 9
            let plan = OddsChartView.xAxisPlan(
                for: paddedDomain,
                plotWidth: 306,
                calendar: calendar,
                labelScale: scale
            )
            let ticks = OddsChartView.xAxisContextTicks(
                for: paddedDomain,
                plan: plan,
                plotWidth: 306,
                labelScale: scale,
                calendar: calendar,
                dataRange: dataRange
            )
            XCTAssertFalse(ticks.isEmpty)
            XCTAssertLessThanOrEqual(ticks.last!, lastPoint)
            XCTAssertEqual(ticks.last, lastPoint)

            var formatter = plan.format(in: calendar.timeZone)
            formatter.calendar = calendar
            let lastFormatted = formatter.format(ticks.last!)
            let expectedLast = plan.labelStyle == .monthAndYear ? "Nov 2026" : "Nov 22"
            XCTAssertEqual(lastFormatted, expectedLast)
            XCTAssertNotEqual(lastFormatted, "Nov 26")
            XCTAssertNotEqual(lastFormatted, "Nov 27")

            let totalDur = paddedDomain.upperBound.timeIntervalSince(paddedDomain.lowerBound)
            let positions = ticks.map { CGFloat($0.timeIntervalSince(paddedDomain.lowerBound) / totalDur) * 306 }
            let width = OddsChartView.xAxisLabelWidth(for: plan.labelStyle) * scale
            let centers = OddsChartView.xAxisLabelCenters(tickPositions: positions, plotWidth: 306, labelWidth: width)
            XCTAssertTrue(OddsChartView.xAxisLabelsClear(centers: centers, labelWidth: width))
        }
    }

    func testTrailingFinalChipFlipsLeftOfEndLineInsidePlot() {
        let plotWidth = 306.0
        let endLineX = 300.0 // 2% right padding from naturalDomain puts last data at ~300pt of 306pt
        let requests = [
            PeriodChipGeometry.ChipRequest(key: 0, label: "Q4", rawX: 299.0),
            PeriodChipGeometry.ChipRequest(key: 1, label: "Final", rawX: endLineX),
        ]
        let placements = PeriodChipGeometry.place(
            requests,
            plotWidth: plotWidth,
            clearTrailingBoundary: true
        )
        XCTAssertEqual(placements.map(\.key), [1], "Tight Q4+Final should drop Q4 and preserve Final")
        let finalPlacement = placements[0]
        let half = PeriodChipGeometry.chipWidth(for: "Final") / 2
        XCTAssertGreaterThanOrEqual(finalPlacement.centerX - half, 0)
        XCTAssertLessThanOrEqual(finalPlacement.centerX + half, endLineX - 6 + 0.01)
    }

    func testFinishedGameAllChartFinalMarkerAndAxisDatesAt390LightDarkRegularAndLargest() throws {
        let event: EventDetail
        let allHistory: EventHistoryResponse

        let eventPath = "\(Self.scratchDir)/13606-event-14639207.json"
        let allPath = "\(Self.scratchDir)/13606-history-all.json"
        if FileManager.default.fileExists(atPath: eventPath),
           FileManager.default.fileExists(atPath: allPath) {
            let d = Self.decoder()
            event = try d.decode(EventDetail.self, from: Data(contentsOf: URL(fileURLWithPath: eventPath)))
            allHistory = try d.decode(EventHistoryResponse.self, from: Data(contentsOf: URL(fileURLWithPath: allPath)))
        } else {
            (event, allHistory) = try makeSyntheticLongHorizonFinishedGame()
        }

        let cases: [(name: String, scheme: ColorScheme, textSize: DynamicTypeSize)] = [
            ("reg-light", .light, .large),
            ("reg-dark", .dark, .large),
            ("ax5-light", .light, .accessibility5),
            ("ax5-dark", .dark, .accessibility5),
        ]
        var rendered: [String: UIImage] = [:]

        for c in cases {
            let panelHeight: CGFloat = c.textSize == .accessibility5 ? 640 : 470
            let img = renderSlice(width: 390, height: panelHeight, scheme: c.scheme, textSize: c.textSize) {
                OddsChartView(
                    eventId: event.id,
                    commenceTime: event.commenceTime,
                    status: event.status,
                    homeTeamName: event.homeTeam,
                    awayTeamName: event.awayTeam,
                    homeTeamLogo: event.homeTeamData?.logoSmall,
                    awayTeamLogo: event.awayTeamData?.logoSmall,
                    homeTeamAbbrev: event.homeTeamData?.abbreviation,
                    awayTeamAbbrev: event.awayTeamData?.abbreviation,
                    sportKey: event.sport,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    servedHomeProbability: event.heroProbabilitySource == OpeningLineHero.openingSource ? nil : event.currentOdds?.homeProbability,
                    servedAwayProbability: event.heroProbabilitySource == OpeningLineHero.openingSource ? nil : event.currentOdds?.awayProbability,
                    selectedRange: .constant(.all),
                    preloadedHistory: allHistory
                )
                .padding(12)
                .frame(width: 390, height: panelHeight, alignment: .topLeading)
                .background(Color(.systemGroupedBackground))
            }
            rendered[c.name] = img

            let lines = try recognizeLines(in: img)
            let joined = lines.joined(separator: " ")
            XCTAssertTrue(lines.contains { $0 == "Final" } || joined.contains("Final"), "Missing full 'Final' badge in \(c.name): \(lines)")
            XCTAssertFalse(lines.contains { $0 == "Fina" }, "Clipped 'Fina' badge present in \(c.name): \(lines)")
            XCTAssertFalse(joined.contains("Nov 26"), "Post-game future date 'Nov 26' leaked in \(c.name): \(joined)")
            XCTAssertFalse(joined.contains("Nov 27"), "Post-game future date 'Nov 27' leaked in \(c.name): \(joined)")
            XCTAssertTrue(
                joined.contains("Nov 22") || joined.contains("Nov 23") || joined.contains("Nov 2026"),
                "Expected closing game date Nov 22/23 or Nov 2026 in \(c.name): \(joined)"
            )
        }

        if let outEnv = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13689_DIR"], !outEnv.isEmpty {
            try FileManager.default.createDirectory(atPath: outEnv, withIntermediateDirectories: true)
            for (name, img) in rendered {
                if let data = img.pngData() {
                    try data.write(to: URL(fileURLWithPath: "\(outEnv)/13689-\(name).png"), options: .atomic)
                }
            }
        }
    }

    private func makeSyntheticLongHorizonFinishedGame() throws -> (EventDetail, EventHistoryResponse) {
        let d = Self.decoder()
        let event = try d.decode(EventDetail.self, from: Data("""
        {
          "id": 14639207,
          "home_team": "San Francisco 49ers",
          "away_team": "Minnesota Vikings",
          "home_team_data": {"team_id": 25, "abbreviation": "SF"},
          "away_team_data": {"team_id": 16, "abbreviation": "MIN"},
          "status": "completed",
          "sport": "americanfootball_nfl",
          "commence_time": "2026-11-23T01:20:00Z",
          "completed_at": "2026-11-23T04:26:00Z",
          "home_score": 24,
          "away_score": 17,
          "current_odds": {"home_probability": 0.99, "away_probability": 0.01}
        }
        """.utf8))
        let history = try d.decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 14639207,
          "home_team": "San Francisco 49ers",
          "away_team": "Minnesota Vikings",
          "status": "completed",
          "commence_time": "2026-11-23T01:20:00Z",
          "completed_at": "2026-11-23T04:26:00Z",
          "pre_window_omitted": false,
          "commence_time_is_kickoff": true,
          "history": [
            {"timestamp": "2026-05-13T14:21:00Z", "home_probability": 0.64, "away_probability": 0.36},
            {"timestamp": "2026-08-08T12:00:00Z", "home_probability": 0.65, "away_probability": 0.35},
            {"timestamp": "2026-11-23T01:25:00Z", "home_probability": 0.68, "away_probability": 0.32},
            {"timestamp": "2026-11-23T04:26:00Z", "home_probability": 0.99, "away_probability": 0.01}
          ],
          "espn_history": [
            {"timestamp": "2026-11-23T01:25:00Z", "home_probability": 0.68, "away_probability": 0.32, "period": "1st", "clock": "14:00"},
            {"timestamp": "2026-11-23T03:50:00Z", "home_probability": 0.92, "away_probability": 0.08, "period": "4th", "clock": "05:00"},
            {"timestamp": "2026-11-23T04:26:00Z", "home_probability": 0.99, "away_probability": 0.01, "period": "Final", "clock": "0:00"}
          ],
          "period_markers": [
            {"timestamp": "2026-11-23T01:20:00Z", "label": "Q1", "period": "1"},
            {"timestamp": "2026-11-23T03:45:00Z", "label": "Q4", "period": "4"},
            {"timestamp": "2026-11-23T04:26:00Z", "label": "Final", "period": "Final"}
          ]
        }
        """.utf8))
        return (event, history)
    }

    private func renderSlice<Content: View>(
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme,
        textSize: DynamicTypeSize,
        @ViewBuilder content: () -> Content
    ) -> UIImage {
        let host = UIHostingController(
            rootView: content()
                .environment(\.colorScheme, scheme)
                .environment(\.dynamicTypeSize, textSize)
        )
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        host.view.backgroundColor = scheme == .dark ? .black : .white
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<5 {
            host.view.frame = bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.04))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        let img = UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        window.rootViewController = nil
        return img
    }

    private func recognizeLines(in image: UIImage) throws -> [String] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }
}
