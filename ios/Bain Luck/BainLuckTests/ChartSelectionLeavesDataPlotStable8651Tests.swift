import XCTest
import SwiftUI
import UIKit
import Vision
@testable import Bain_Luck

@MainActor
final class ChartSelectionLeavesDataPlotStable8651Tests: XCTestCase {
    private let start = Date(timeIntervalSince1970: 1_790_500_000)

    private final class LiveInput: ObservableObject {
        @Published var frames: [LiveBlendPoint] = []
    }

    private struct LiveFixture: View {
        @ObservedObject var input: LiveInput
        let payload: EventHistoryResponse
        let model: OddsChartViewModel
        let selection: OddsChartSelection
        var body: some View {
            OddsChartView(eventId: 1, status: "live", homeTeamName: "Home", awayTeamName: "Away",
                          preloadedHistory: payload, liveFrames: input.frames,
                          readout: GamePlayCardView(homeTeam: "Home", awayTeam: "Away", lastPoint: nil),
                          model: model, selection: selection)
        }
    }

    private func history(final: Double = 0.6) throws -> EventHistoryResponse {
        var points: [[String: Any]] = []
        for index in 0..<1_200 {
            let timestamp = start.addingTimeInterval(Double(index)).ISO8601Format()
            let probability: Double = index == 1_199 ? final : 0.4 + Double(index % 10) / 100.0
            points.append(["timestamp": timestamp, "home_probability": probability])
        }
        let data = try JSONSerialization.data(withJSONObject: [
            "event_id": 1, "home_team": "Home", "away_team": "Away", "status": "live",
            "history": [], "win_prob_history": ["polymarket": points], "aggregate_line": points
        ])
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: data)
    }

    private func pump(_ host: UIViewController, times: Int = 5) {
        for _ in 0..<times {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
    }

    private func visibleText(_ host: UIViewController, name: String) throws -> String {
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("8651-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("#8651 rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    func testActualHostedChartDoesNotRebuildMarksWhenOnlyTheFingerMoves() throws {
        let payload = try history()
        let model = OddsChartViewModel(eventId: 1, preloaded: payload)
        let selection = OddsChartSelection()
        var plotBuilds = 0
        model.onPlotBuild = { plotBuilds += 1 }
        let input = LiveInput()
        let chart = LiveFixture(input: input, payload: payload, model: model, selection: selection)
        let host = hostForMeasurement(chart.frame(width: 390), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true; model.onPlotBuild = nil }
        pump(host, times: 12)
        XCTAssertGreaterThan(plotBuilds, 0, "the real data plot must render for this test to mean anything")
        let before = plotBuilds
        let enrichments = model.enrichmentBuildCount
        for step in 0..<20 {
            selection.change(date: start.addingTimeInterval(Double(step * 40)),
                             translation: CGSize(width: 30 + step, height: 2))
            pump(host, times: 1)
        }
        XCTAssertNotNil(selection.date)
        XCTAssertEqual(plotBuilds, before, "selection re-evaluated the expensive Chart marks")
        XCTAssertEqual(model.enrichmentBuildCount, enrichments)
        selection.end()
        pump(host)
        XCTAssertNil(selection.date)
        XCTAssertEqual(plotBuilds, before, "releasing selection rebuilt the data plot")

        // A genuinely new served payload MUST rebuild the plot; the repair is
        // isolation from finger movement, never freezing the live series.
        model.history = try history(final: 0.77)
        pump(host)
        XCTAssertGreaterThan(plotBuilds, before)
        XCTAssertEqual(model.enrichmentBuildCount, enrichments + 1)
        XCTAssertEqual(model.enrichedChartPoints(liveFrames: []).last?.probability, 0.77)
        let afterHistory = plotBuilds
        input.frames = [LiveBlendPoint(date: start.addingTimeInterval(1_201), homeProbability: 0.73)]
        pump(host)
        XCTAssertGreaterThan(plotBuilds, afterHistory, "a pushed live edge must still reach the mounted plot")
        XCTAssertEqual(model.enrichmentBuildCount, enrichments + 2)
        XCTAssertTrue(model.enrichedChartPoints(liveFrames: input.frames).contains {
            $0.date == start.addingTimeInterval(1_201) && $0.probability == 0.73
        })
        print("#8651 render counts: selection=0, release=0, initial=\(before), after-history=\(afterHistory), after-push=\(plotBuilds); enrichment \(enrichments)->\(model.enrichmentBuildCount)")
    }

    /// Snapshotting explicitly redraws the hierarchy, so visual correctness is
    /// tested separately from the live body's no-rebuild assertion above.
    func testMountedReadoutChangesWithSelectionAndReturnsToTheLiveEdge() throws {
        let payload = try history()
        let selection = OddsChartSelection()
        let chart = OddsChartView(eventId: 1, status: "live", homeTeamName: "Home", awayTeamName: "Away",
                                  preloadedHistory: payload,
                                  readout: GamePlayCardView(homeTeam: "Home", awayTeam: "Away", lastPoint: nil),
                                  selection: selection)
        let host = hostForMeasurement(chart.frame(width: 390), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        pump(host, times: 12)
        selection.select(start.addingTimeInterval(3))
        pump(host)
        let selectedText = try visibleText(host, name: "selected")
        XCTAssertTrue(selectedText.contains("43%"), "the mounted readout did not follow selection: \(selectedText)")
        selection.end()
        pump(host)
        let restingText = try visibleText(host, name: "released")
        XCTAssertTrue(restingText.contains("60%"), restingText)
        XCTAssertFalse(restingText.contains("43%"), "the readout did not return to the live edge")
    }

    func testEnrichmentMemoInvalidatesOnHistoryAndAcceptedLiveFrames() throws {
        let model = OddsChartViewModel(eventId: 1, preloaded: try history())
        let before = model.enrichedChartPoints(liveFrames: [])
        XCTAssertEqual(before.count, 2_400)
        let builds = model.enrichmentBuildCount
        XCTAssertEqual(model.enrichedChartPoints(liveFrames: []).map(\.id), before.map(\.id))
        XCTAssertEqual(model.enrichmentBuildCount, builds)
        let live = LiveBlendPoint(date: start.addingTimeInterval(1_201), homeProbability: 0.73)
        let after = model.enrichedChartPoints(liveFrames: [live])
        XCTAssertEqual(model.enrichmentBuildCount, builds + 1)
        XCTAssertTrue(after.contains { $0.date == live.date && $0.probability == 0.73 })
        model.history = nil
        XCTAssertTrue(model.enrichedChartPoints(liveFrames: [live]).isEmpty)
    }

    func testVerticalSwipesNeverSelectAndHeldScrubsStillRelease() {
        let selection = OddsChartSelection()
        selection.change(date: start, translation: CGSize(width: 2, height: 30))
        XCTAssertNil(selection.date)
        XCTAssertFalse(selection.holdsTheScrollStill)
        selection.end()
        selection.hold(date: start)
        XCTAssertEqual(selection.date, start)
        XCTAssertTrue(selection.holdsTheScrollStill)
        selection.end()
        XCTAssertNil(selection.date)
        XCTAssertFalse(selection.holdsTheScrollStill)
    }
}
