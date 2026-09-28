import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Controlled input, actual mounted production event page. This deliberately
/// holds the .445 tie so a moving real market cannot make the regression vacuous.
@MainActor
final class ComplementDisplayRender9321Tests: XCTestCase {
    private final class Client: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        let history: EventHistoryResponse
        init() throws {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            let now = Date(), start = now.addingTimeInterval(-600)
            event = try decoder.decode(EventDetail.self, from: Data("""
            {"id":4242,"home_team":"Home","away_team":"Away","sport":"baseball_mlb","status":"live",
             "commence_time":"\(start.ISO8601Format())","home_score":2,"away_score":3,
             "current_odds":{"home_probability":0.445,"away_probability":0.555,"home_rendered_percent":44,"away_rendered_percent":56},
             "hero_probability":0.445,"hero_probability_source":"blend","hero_probability_observed_at":"\(now.ISO8601Format())",
             "win_probability_sources":{"polymarket":{"value":0.445,"updated_at":"\(now.ISO8601Format())"}}}
            """.utf8))
            let points = (0...10).map { index in
                "{\"timestamp\":\"\(start.addingTimeInterval(Double(index)*60).ISO8601Format())\",\"home_probability\":0.445}"
            }.joined(separator: ",")
            history = try decoder.decode(EventHistoryResponse.self, from: Data("""
            {"event_id":4242,"home_team":"Home","away_team":"Away","status":"live","history":[],
             "aggregate_line":[\(points)],"win_prob_history":{"polymarket":[\(points)]}}
            """.utf8))
        }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }
    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() { isClosed = true }
    }
    func testActualPagePrintsTheSameTieAtDefaultAndXXXL() async throws {
        let prior = UserDefaults.standard.object(forKey: LaunchRig.expandSectionsKey)
        UserDefaults.standard.set(true, forKey: LaunchRig.expandSectionsKey)
        defer { UserDefaults.standard.set(prior, forKey: LaunchRig.expandSectionsKey) }
        for (name, size) in [("default", DynamicTypeSize.large), ("xxxl", .xxxLarge)] {
            let client = try Client(), handle = Handle()
            let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle })
            await vm.load()
            let page = NavigationStack { EventDetailView(eventId: 4242, viewModel: vm) }
                .environmentObject(PinManager())
                .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
            let host = hostForMeasurement(page, at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 1800)
            let window = UIWindow(frame: host.view.frame); window.rootViewController = host; window.isHidden = false
            defer { vm.stopRefresh(); window.isHidden = true }
            for _ in 0..<40 {
                host.view.setNeedsLayout(); host.view.layoutIfNeeded()
                try await Task.sleep(nanoseconds: 25_000_000)
            }
            let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
                host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent("complement9321")
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try XCTUnwrap(image.pngData()).write(to: dir.appendingPathComponent(name + ".png"))
            let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
            let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
            try text.write(to: dir.appendingPathComponent(name + ".txt"), atomically: true, encoding: .utf8)
            print("COMPLEMENT9321 controlled production page \(name): \(dir.path) text=\(text)")
            XCTAssertTrue(text.contains("44%"), text)
            XCTAssertTrue(text.contains("56%"), text)
            XCTAssertFalse(text.contains("45%"), text)
            XCTAssertFalse(text.contains("55%"), text)
            XCTAssertTrue(text.contains("Polymarket"), "Source row must actually be on screen: \(text)")

            // Exercise the production chart's own readout with the same tie.
            // The full page may omit a resting play card when no play is served.
            let point = ChartDataPoint(date: Date(), probability: 0.445, source: "aggregate")
            let readout = GamePlayCardView(homeTeam: "Home", awayTeam: "Away",
                lastPoint: OddsChartView.playPoint(for: point, sportKey: "baseball_mlb"))
            let chart = OddsChartView(eventId: 4242, status: "live", homeTeamName: "Home", awayTeamName: "Away",
                sportKey: "baseball_mlb", preloadedHistory: client.history, readout: readout)
                .environment(\.colorScheme, .light)
            let chartHost = hostForMeasurement(chart, at: size)
            chartHost.view.frame = CGRect(x: 0, y: 0, width: 390, height: 600)
            let chartWindow = UIWindow(frame: chartHost.view.frame)
            chartWindow.rootViewController = chartHost; chartWindow.isHidden = false
            defer { chartWindow.isHidden = true }
            for _ in 0..<20 {
                chartHost.view.setNeedsLayout(); chartHost.view.layoutIfNeeded()
                try await Task.sleep(nanoseconds: 25_000_000)
            }
            let chartImage = UIGraphicsImageRenderer(bounds: chartHost.view.bounds).image { _ in
                chartHost.view.drawHierarchy(in: chartHost.view.bounds, afterScreenUpdates: true)
            }
            try XCTUnwrap(chartImage.pngData()).write(to: dir.appendingPathComponent(name + "-chart.png"))
            let chartRequest = VNRecognizeTextRequest(); chartRequest.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: XCTUnwrap(chartImage.cgImage)).perform([chartRequest])
            let chartText = (chartRequest.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
            print("COMPLEMENT9321 controlled chart \(name): \(chartText)")
            XCTAssertTrue(chartText.contains("44%"), chartText)
            XCTAssertTrue(chartText.contains("56%"), chartText)
            XCTAssertFalse(chartText.contains("45%"), chartText)
            XCTAssertFalse(chartText.contains("55%"), chartText)
        }
    }
}
