import SwiftUI
import XCTest
@testable import Bain_Luck

/// The camera for #920, because "the chart's right edge reaches the same moment
/// the hero does" is a claim about a picture.
///
/// The BEFORE arm here is not a strawman or a reconstruction: pre-fix, the chart
/// drew the payload it was handed and ignored every pushed frame, which is
/// exactly what `liveFrames: []` draws today. Same specimen, same size, same
/// payload — the only difference between the two rasters is the frames the page
/// was actually given. What a raster cannot show is the OTHER half of this ship
/// (the chart refusing every fresher payload for the life of the view); that is
/// a lifecycle claim and `LiveChartEdgeTests920` carries it.
///
/// Byte counts are the tripwire, not the evidence. The artifact paths are
/// printed so a human reads the actual picture, which is the judgement that
/// counts (notice 4 / D48).
@MainActor
final class LiveChartEdgeRenderSmokeTests920: XCTestCase {

    private static let commence = "2026-09-21T11:55:00Z"

    private func history(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// A live match whose published blend stops at 12:10 — and which DRAWS on its
    /// own, so the before arm is a real chart and not an empty-state frame. A
    /// before/after pair is worthless if one arm never cleared the render gate.
    private func published() throws -> EventHistoryResponse {
        try history("""
        {
          "event_id": 15302923, "home_team": "Red Sox", "away_team": "Yankees",
          "status": "live",
          "history": [
            {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.40},
            {"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.44}
          ],
          "win_prob_history": {
            "espn": [
              {"timestamp": "2026-09-21T12:02:00Z", "home_probability": 0.43},
              {"timestamp": "2026-09-21T12:06:00Z", "home_probability": 0.47}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-09-21T12:00:00Z", "home_probability": 0.41},
            {"timestamp": "2026-09-21T12:05:00Z", "home_probability": 0.43},
            {"timestamp": "2026-09-21T12:10:00Z", "home_probability": 0.46}
          ]
        }
        """)
    }

    /// Eight minutes of pushed frames past the published edge, ending in the
    /// swing a reader would be staring at: 46% → 78%.
    private func pushed() -> [LiveBlendPoint] {
        let stamps: [(String, Double)] = [
            ("2026-09-21T12:11:00Z", 0.49), ("2026-09-21T12:12:00Z", 0.55),
            ("2026-09-21T12:13:00Z", 0.58), ("2026-09-21T12:14:00Z", 0.64),
            ("2026-09-21T12:15:00Z", 0.62), ("2026-09-21T12:16:00Z", 0.70),
            ("2026-09-21T12:17:00Z", 0.74), ("2026-09-21T12:18:00Z", 0.78),
        ]
        return stamps.compactMap { iso, p in
            iso.asDate.map { LiveBlendPoint(date: $0, homeProbability: p) }
        }
    }

    @discardableResult
    private func render(
        _ name: String, _ payload: EventHistoryResponse, _ frames: [LiveBlendPoint]
    ) throws -> Data {
        let view = OddsChartView(
            eventId: 15302923,
            commenceTime: Self.commence,
            status: "live",
            homeTeamName: "Red Sox",
            awayTeamName: "Yankees",
            homeTeamAbbrev: "BOS",
            awayTeamAbbrev: "NYY",
            refreshStreaming: true,
            preloadedHistory: payload,
            liveFrames: frames
        )
        .frame(width: 390)

        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")

        // Written where the lane keeps its evidence, not to a temp dir that the
        // next reboot eats — a frame nobody can open later is not evidence.
        let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BL_ARTIFACTS"]
            ?? FileManager.default.temporaryDirectory.path)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("920-\(name).png")
        try png.write(to: url)
        print("#920 render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    /// BEFORE and AFTER, one specimen. The before arm must itself be a drawn
    /// chart (its own control, below), or "after has more ink" would be the
    /// difference between a chart and an empty frame rather than the difference
    /// this ship makes.
    func testThePushedFramesAddInkPastThePublishedEdge() throws {
        let before = try render("before-published-only", try published(), [])
        let after = try render("after-live-edge", try published(), pushed())

        XCTAssertGreaterThan(
            after.count, before.count,
            "the pushed frames drew nothing — the chart is still stopping at the served edge"
        )
    }

    /// The control. Without it the comparison above is equally happy when the
    /// before arm collapsed to an empty frame, which is the failure mode every
    /// two-arm raster test has.
    func testTheBeforeArmIsItselfADrawnChart() throws {
        let points = OddsChartView.chartPoints(from: try published())
        XCTAssertTrue(
            OddsChartView.hasDrawableLine(in: points),
            "the before arm must be a real chart, or this pair proves nothing"
        )
        XCTAssertGreaterThan(try render("control-before-drawable", try published(), []).count, 20_000)
    }

    /// And the frames really are past the edge, so the pair is about the live
    /// edge and not about eight arbitrary extra points.
    func testTheRenderedFramesAreAllPastThePublishedEdge() throws {
        let published = try published()
        let edge = try XCTUnwrap(
            OddsChartView.chartPoints(from: published)
                .filter { $0.source == "aggregate" }.map(\.date).max()
        )
        let frames = pushed()
        XCTAssertEqual(frames.count, 8)
        for frame in frames { XCTAssertGreaterThan(frame.date, edge) }
    }
}
