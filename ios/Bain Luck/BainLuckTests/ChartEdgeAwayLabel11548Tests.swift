import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #11548 — pregame headline keeps the win-probability chart above the fold on
/// a 393 pt screen, and the live edge label on a two-outcome tug-of-war chart
/// names the away team (`NCSU 73%`) when home probability sits below 50% so
/// the endpoint label matches the away-side gridlines beside it.
@MainActor
final class ChartEdgeAwayLabel11548Tests: XCTestCase {

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

    func testEndpointLabelMatchesTugOfWarPoleBelow50Percent() {
        let reading27 = LiveEdgeReading(
            homeProbability: 0.27,
            homeLabel: "27%",
            awayLabel: "73%",
            source: "blend"
        )
        XCTAssertEqual(
            LiveChartEdgeMarkerPlan.endpointLabel(
                homeShort: "STAN",
                awayShort: "NCSU",
                reading: reading27,
                sides: .homeAndAway
            ),
            "NCSU 73%"
        )
        XCTAssertEqual(
            LiveChartEdgeMarkerPlan.endpointLabel(
                homeShort: "STAN",
                awayShort: "NCSU",
                reading: reading27,
                sides: .homeOnly
            ),
            "STAN 27%"
        )

        let reading50 = LiveEdgeReading(
            homeProbability: 0.50,
            homeLabel: "50%",
            awayLabel: "50%",
            source: "blend"
        )
        XCTAssertEqual(
            LiveChartEdgeMarkerPlan.endpointLabel(
                homeShort: "STAN",
                awayShort: "NCSU",
                reading: reading50,
                sides: .homeAndAway
            ),
            "STAN 50%"
        )

        let reading73 = LiveEdgeReading(
            homeProbability: 0.73,
            homeLabel: "73%",
            awayLabel: "27%",
            source: "blend"
        )
        XCTAssertEqual(
            LiveChartEdgeMarkerPlan.endpointLabel(
                homeShort: "STAN",
                awayShort: "NCSU",
                reading: reading73,
                sides: .homeAndAway
            ),
            "STAN 73%"
        )
    }

    func testEndpointLabelFallsBackToPairedAwayLabelWhenReadingOmitsAwayLabel() {
        let legacyReading = LiveEdgeReading(
            homeProbability: 0.27,
            homeLabel: "27%",
            source: "blend"
        )
        XCTAssertEqual(
            LiveChartEdgeMarkerPlan.endpointLabel(
                homeShort: "STAN",
                awayShort: "NCSU",
                reading: legacyReading,
                sides: .homeAndAway,
                fallbackAwayLabel: "73%"
            ),
            "NCSU 73%"
        )
        XCTAssertEqual(
            LiveChartEdgeMarkerPlan.endpointLabel(
                homeShort: "STAN",
                awayShort: "NCSU",
                reading: legacyReading,
                sides: .homeAndAway,
                fallbackAwayLabel: nil
            ),
            "STAN 27%"
        )
    }

    func testLiveEdgeCurrentCapturesServedHomeAndAwayLabels() throws {
        let event = try decodeEvent("""
        {
          "id": 15332072,
          "sport": "americanfootball_ncaaf",
          "home_team": "Stanford Cardinal",
          "away_team": "NC State Wolfpack",
          "commence_time": "2026-10-24T02:30:00Z",
          "status": "scheduled",
          "hero_probability": 0.27,
          "hero_probability_away": 0.73,
          "hero_probability_source": "blend",
          "current_odds": {
            "home_probability": 0.27,
            "away_probability": 0.73,
            "home_rendered_percent": 27,
            "away_rendered_percent": 73,
            "updated_at": "2026-10-23T20:42:00Z"
          }
        }
        """)
        let reading = try XCTUnwrap(LiveEdgeReading.current(in: event))
        let pair = LivePriceActivity.displayedLabels(in: event)
        XCTAssertEqual(reading.homeLabel, pair.home)
        XCTAssertEqual(reading.awayLabel, pair.away)
        XCTAssertEqual(reading.homeLabel, "27.0%")
        XCTAssertEqual(reading.awayLabel, "73.0%")
    }

    func testNCStateAtStanfordCompactHeadlineAndAwayChartEndpointAboveFold() async throws {
        let now = ISO8601DateFormatter().date(from: "2026-10-23T20:42:00Z")!
        let event = try decodeEvent("""
        {
          "id": 15332072,
          "sport": "americanfootball_ncaaf",
          "home_team": "Stanford Cardinal",
          "away_team": "NC State Wolfpack",
          "commence_time": "2026-10-24T02:30:00Z",
          "status": "scheduled",
          "home_team_data": {"abbreviation": "STAN", "primary_color": "#8C1515", "record": "3-4"},
          "away_team_data": {"abbreviation": "NCSU", "primary_color": "#CC0000", "record": "5-2"},
          "espn": {"broadcast": "ESPN"},
          "hero_probability": 0.27,
          "hero_probability_away": 0.73,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-10-23T20:42:00Z",
          "current_odds": {
            "home_probability": 0.27,
            "away_probability": 0.73,
            "home_rendered_percent": 27,
            "away_rendered_percent": 73,
            "projected_home_score": 21.0,
            "projected_away_score": 28.0,
            "updated_at": "2026-10-23T20:42:00Z"
          }
        }
        """)
        let history = try decodeHistory("""
        {
          "event_id": 15332072,
          "home_team": "Stanford Cardinal",
          "away_team": "NC State Wolfpack",
          "status": "scheduled",
          "history": [],
          "aggregate_line": [
            {"timestamp": "2026-10-23T12:00:00Z", "home_probability": 0.34},
            {"timestamp": "2026-10-23T16:00:00Z", "home_probability": 0.30},
            {"timestamp": "2026-10-23T20:42:00Z", "home_probability": 0.27}
          ],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-10-23T12:00:00Z", "home_probability": 0.34},
              {"timestamp": "2026-10-23T16:00:00Z", "home_probability": 0.30},
              {"timestamp": "2026-10-23T20:42:00Z", "home_probability": 0.27}
            ]
          },
          "period_markers": []
        }
        """)

        let colors = TeamTextContrast.cardColors(awayHex: "#CC0000", homeHex: "#8C1515", checkHueFamily: true)
        let headlineModel = EventSportHeadlines12472.resolve(
            event: event,
            awayFullName: event.awayTeam,
            homeFullName: event.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: now
        )
        let liveEdge = try XCTUnwrap(LiveEdgeReading.current(in: event))

        let headlineCard = EventSportHeadlineCard12472(
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
        let headlineHeight = hostForMeasurement(
            headlineCard
                .padding(.horizontal, 14)
                .frame(width: 393, alignment: .topLeading),
            at: .large
        ).sizeThatFits(in: CGSize(width: 393, height: 1200)).height
        XCTAssertLessThan(headlineHeight, 220, "Compact pregame headline should fit below 220 pt at default text")

        for (scheme, suffix) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let view = VStack(alignment: .leading, spacing: 14) {
                headlineCard
                OddsChartView(
                    eventId: event.id,
                    teamColors: colors,
                    commenceTime: event.commenceTime,
                    status: event.status,
                    homeTeamName: event.homeTeam,
                    awayTeamName: event.awayTeam,
                    homeTeamAbbrev: "STAN",
                    awayTeamAbbrev: "NCSU",
                    sportKey: event.sport,
                    liveEdge: liveEdge,
                    quoteIsCurrent: true,
                    pairedAwayLabel9483: liveEdge.awayLabel,
                    servedHomeProbability: 0.27,
                    servedAwayProbability: 0.73,
                    selectedRange: .constant(.all),
                    preloadedHistory: history
                )
            }
            .padding(14)
            .background(Color.pageBackground)
            .frame(width: 393, alignment: .topLeading)
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
            window.frame = CGRect(x: 0, y: 0, width: 393, height: 852)
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

            let fitted = host.sizeThatFits(in: CGSize(width: 393, height: 1200))
            XCTAssertLessThan(fitted.height, 852, "Headline + chart should fit above the 852 pt fold")

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let bounds = CGRect(x: 0, y: 0, width: 393, height: min(852, ceil(fitted.height)))
            window.frame = bounds
            host.view.frame = bounds
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            await Task.yield()
            try await Task.sleep(for: .milliseconds(30))

            let image = UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
                if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                    window.layer.render(in: ctx.cgContext)
                }
            }

            if let dir = ProcessInfo.processInfo.environment["RENDER_11548_DIR"], !dir.isEmpty {
                try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                let url = URL(fileURLWithPath: dir).appendingPathComponent("11548-ncsu-stanford-\(suffix)-393.png")
                try XCTUnwrap(image.pngData()).write(to: url)
            }

            let ocr = try ocrStrings(in: image).joined(separator: " | ")
            XCTAssertTrue(ocr.contains("NCSU 73.0%"),
                          "Chart endpoint should label away favorite NCSU 73.0% below 50%: \(ocr)")
            XCTAssertFalse(ocr.contains("STAN 27.0%"),
                           "Chart endpoint must not print STAN 27.0% beside the 73% gridline: \(ocr)")
            XCTAssertFalse(ocr.contains("STAN 27%"),
                           "Chart endpoint must not print STAN 27% beside the 73% gridline: \(ocr)")
        }
    }
}
