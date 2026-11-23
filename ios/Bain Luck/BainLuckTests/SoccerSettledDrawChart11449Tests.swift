import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #11449 — A finished soccer match settled as a draw (`EventOutcome.resolve == .draw`)
/// must not stamp a single team's last pre-whistle win probability (such as `NAP 67%`
/// and legend `last NAP 67%`) onto a home-only fallback chart.
@MainActor
final class SoccerSettledDrawChart11449Tests: XCTestCase {

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func ocrStrings(in image: UIImage) throws -> [String] {
        guard let cgImage = image.cgImage else { return [] }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func samplePoints() -> [ChartDataPoint] {
        let t0 = Date(timeIntervalSince1970: 1_763_145_000)
        let t1 = t0.addingTimeInterval(3_600)
        let t2 = t1.addingTimeInterval(3_300)
        return [
            ChartDataPoint(date: t0, probability: 0.44, source: "aggregate"),
            ChartDataPoint(date: t1, probability: 0.55, source: "aggregate"),
            ChartDataPoint(date: t2, probability: 0.67, source: "aggregate"),
        ]
    }

    func testSettledDrawSuppressesFinishedEndWhileDecisiveWinsAndLiveTiesDoNot() {
        let points = samplePoints()

        XCTAssertTrue(
            OddsChartView.isSettledDraw9483(
                status: "completed", homeScore: 3, awayScore: 3, servedSettledResult: nil
            )
        )
        XCTAssertNil(
            OddsChartView.finishedEnd9483(
                dataPoints: points, checkpoints: nil, finished: true, settledDraw: true
            ),
            "Settled draw by equal final score must not stamp a team's endpoint label"
        )

        XCTAssertTrue(
            OddsChartView.isSettledDraw9483(
                status: "closed", homeScore: nil, awayScore: nil, servedSettledResult: "draw"
            )
        )

        XCTAssertFalse(
            OddsChartView.isSettledDraw9483(
                status: "completed", homeScore: 2, awayScore: 1, servedSettledResult: "home"
            )
        )
        XCTAssertFalse(
            OddsChartView.isSettledDraw9483(
                status: "completed", homeScore: 21, awayScore: 30, servedSettledResult: "away"
            )
        )
        XCTAssertEqual(
            OddsChartView.finishedEnd9483(
                dataPoints: points, checkpoints: nil, finished: true, settledDraw: false
            )?.probability,
            0.67
        )

        XCTAssertFalse(
            OddsChartView.isSettledDraw9483(
                status: "live", homeScore: 1, awayScore: 1, servedSettledResult: nil
            ),
            "A live match that happens to be tied is not a settled draw"
        )
        XCTAssertFalse(
            OddsChartView.isSettledDraw9483(
                status: "completed", homeScore: nil, awayScore: nil, servedSettledResult: nil
            ),
            "An unresolved final without scores or served result is not assumed to be a draw"
        )
    }

    func testNapoliRomaSettledDrawHomeOnlyChartRendersWithoutTeamEndpointBadge() async throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-14T22:00:00Z")!
        let event = try decodeEvent("""
        {
          "id": 15328786,
          "sport": "soccer_italy_serie_a",
          "home_team": "Napoli",
          "away_team": "AS Roma",
          "commence_time": "2026-11-14T18:30:00Z",
          "status": "completed",
          "home_score": 3,
          "away_score": 3,
          "hero_settled_result": "draw",
          "home_team_data": {"abbreviation": "NAP"},
          "away_team_data": {"abbreviation": "ROM"}
        }
        """)
        let history = try decodeHistory("""
        {
          "event_id": 15328786,
          "home_team": "Napoli",
          "away_team": "AS Roma",
          "status": "completed",
          "history": [
            {"timestamp": "2026-11-14T18:30:00Z", "home_probability": 0.44},
            {"timestamp": "2026-11-14T19:30:00Z", "home_probability": 0.55},
            {"timestamp": "2026-11-14T20:25:00Z", "home_probability": 0.67}
          ],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-14T18:30:00Z", "home_probability": 0.44},
              {"timestamp": "2026-11-14T19:30:00Z", "home_probability": 0.55},
              {"timestamp": "2026-11-14T20:25:00Z", "home_probability": 0.67}
            ]
          },
          "period_markers": []
        }
        """)

        let headlineModel = EventSportHeadlines12472.resolve(
            event: event,
            awayFullName: event.awayTeam,
            homeFullName: event.homeTeam,
            liveStatusText: nil,
            hasScore: true,
            numberStreams: false,
            now: now
        )
        let colors = TeamTextContrast.cardColors(awayHex: nil, homeHex: nil, checkHueFamily: true)

        for (scheme, suffix) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let view = VStack(alignment: .leading, spacing: 14) {
                EventSportHeadlineCard12472(
                    model: headlineModel,
                    colors: colors,
                    ekgTracker: EkgTracker(),
                    liveUpdateStatus: .hidden,
                    displayAsOf: nil,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                OddsChartView(
                    eventId: event.id,
                    teamColors: colors,
                    commenceTime: event.commenceTime,
                    status: event.status,
                    homeTeamName: event.homeTeam,
                    awayTeamName: event.awayTeam,
                    homeTeamAbbrev: "NAP",
                    awayTeamAbbrev: "ROM",
                    sportKey: event.sport,
                    homeScore: 3,
                    awayScore: 3,
                    servedSettledResult: "draw",
                    selectedRange: .constant(.all),
                    preloadedHistory: history
                )
            }
            .padding(14)
            .background(Color.pageBackground)
            .frame(width: 390, alignment: .topLeading)
            .environment(\.colorScheme, scheme)
            .environment(\.scenePhase, .active)
            .environment(\.horizontalSizeClass, .compact)
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())

            let host = hostForMeasurement(view, at: .large)
            host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
            let scene = try XCTUnwrap(
                UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
            )
            let existing = scene.windows
            existing.forEach { $0.isHidden = true }
            let window = UIWindow(windowScene: scene)
            window.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
            window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
            window.rootViewController = host
            window.makeKeyAndVisible()
            defer {
                window.isHidden = true
                window.rootViewController = nil
                existing.forEach { $0.isHidden = false }
            }

            host.view.frame = window.bounds
            for _ in 0..<8 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                await Task.yield()
                try await Task.sleep(for: .milliseconds(30))
            }

            let fitted = host.sizeThatFits(in: CGSize(width: 390, height: 1200))
            let bounds = CGRect(x: 0, y: 0, width: 390, height: min(844, ceil(fitted.height)))
            window.frame = bounds
            host.view.frame = bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            await Task.yield()
            try await Task.sleep(for: .milliseconds(30))

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let image = UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
                if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                    window.layer.render(in: ctx.cgContext)
                }
            }

            if let dir = ProcessInfo.processInfo.environment["RENDER_11449_DIR"], !dir.isEmpty {
                try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                let url = URL(fileURLWithPath: dir)
                    .appendingPathComponent("11449-settled-draw-fixed-\(suffix)-390.png")
                try XCTUnwrap(image.pngData()).write(to: url)
            }

            let ocr = try ocrStrings(in: image).joined(separator: " | ")
            XCTAssertTrue(ocr.contains("Napoli"), "Expected Napoli in rendered headline: \(ocr)")
            XCTAssertTrue(ocr.contains("AS Roma"), "Expected AS Roma in rendered headline: \(ocr)")
            XCTAssertTrue(ocr.contains("Draw"), "Expected Draw verdict in rendered headline: \(ocr)")
            XCTAssertFalse(ocr.contains("NAP 67%"), "Settled draw chart must not print NAP 67%: \(ocr)")
            XCTAssertFalse(ocr.contains("last NAP 67%"), "Settled draw legend must not print last NAP 67%: \(ocr)")
        }
    }
}
