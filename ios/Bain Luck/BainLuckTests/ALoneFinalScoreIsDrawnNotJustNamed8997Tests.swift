import SwiftUI
import XCTest
@testable import Bain_Luck

/// #8997 — a Score Differential whose only captured score is the final draws
/// it, rather than naming "Actual Score Diff" in the legend over an empty plot.
///
/// `/events/15292394` (Dubai Basketball 78–77 Real Madrid, FINAL) serves one
/// `score_history` row, stamped at `completed_at`, and no ESPN scores. The
/// actual series was drawn only as a `LineMark`, which draws nothing through a
/// single point, while the legend advertised it on any point at all.
///
/// FIXTURE: `Fixtures/event-15292394-history-8997-lone-final.20260927.json`, the
/// served `/history` reduced to shape (see its `_fixture_note`).
///
/// Teal is counted in the PLOT only — the legend's own teal swatch sits in the
/// bottom band and is excluded, because the defect was exactly a swatch with no
/// mark above it.
@MainActor
final class ALoneFinalScoreIsDrawnNotJustNamed8997Tests: XCTestCase {

    private static var fixtureURL: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("event-15292394-history-8997-lone-final.20260927.json")
    }

    private static let commence = "2026-09-24T16:00:00+00:00"

    private enum Scores { case served, twoRows, none }

    private func specimen(_ scores: Scores) throws -> EventHistoryResponse {
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
        switch scores {
        case .served:
            break
        case .none:
            object.removeValue(forKey: "score_history")
        case .twoRows:
            // The control: one more observed score mid-game makes the series a
            // line, which must keep drawing exactly as it did before #8997.
            var rows = try XCTUnwrap(object["score_history"] as? [[String: Any]])
            rows.insert(["timestamp": "2026-09-24T19:30:00+00:00",
                         "home_score": 50, "away_score": 44], at: 0)
            object["score_history"] = rows
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    /// Teal pixels above the legend band, at 3x.
    private func plotTeal(_ scores: Scores, name: String) throws -> Int {
        let view = ScoreDifferentialChartView(
            history: try specimen(scores), homeTeam: "Dubai Basketball", awayTeam: "Real Madrid",
            sportKey: "basketball_euroleague", commenceTime: Self.commence, eventStatus: "completed",
            homeTeamColor: .red, awayTeamColor: .blue,
            homeTeamAbbrev: "DUB", awayTeamAbbrev: "RMA")
            .padding(16)
            .frame(width: 390)
            .background(Color.white)
        let renderer = rendererForMeasurement(view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.cgImage)

        let dir = URL(fileURLWithPath: ProcessInfo.processInfo.environment["BL_ARTIFACTS"]
            ?? FileManager.default.temporaryDirectory.path)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("8997-\(name).png")
        try? UIImage(cgImage: image).pngData()?.write(to: url)
        print("8997 render artifact [\(name)]: \(url.path)")

        let w = image.width, h = image.height
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = try XCTUnwrap(CGContext(
            data: &bytes, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        ctx.draw(image, in: CGRect(x: 0, y: 0, width: w, height: h))
        // The legend row and the paddings below it: 16 + 16 + one caption2 line.
        let legendBand = 50 * 3
        var teal = 0
        for y in 0..<max(0, h - legendBand) {
            for x in 0..<w {
                let i = (y * w + x) * 4
                let r = Int(bytes[i]), g = Int(bytes[i + 1]), b = Int(bytes[i + 2])
                // The actual series is #0d9488 (13, 148, 136). `abs(g - b)`
                // keeps the away gutter's system blue (0, 122, 255) out.
                if r < 70, g > 110, b > 100, g - r > 60, abs(g - b) < 40 { teal += 1 }
            }
        }
        return teal
    }

    func testTheLoneServedFinalIsDrawnInThePlot() throws {
        let teal = try plotTeal(.served, name: "specimen")
        XCTAssertGreaterThan(teal, 150, "the legend names an actual series the plot does not draw (#8997)")
    }

    /// Two rows are a line and keep drawing as one — the change is confined to
    /// the one-point case.
    func testTwoScoresStillDrawTheLine() throws {
        XCTAssertGreaterThan(try plotTeal(.twoRows, name: "two-rows-control"), 300)
    }

    /// No score at all draws no teal: the counter is not reading the orange
    /// projection or the gutter as the actual series.
    func testNoScoresDrawNoTeal() throws {
        XCTAssertEqual(try plotTeal(.none, name: "no-scores-control"), 0)
    }

    func testTheLonePointPredicate() {
        XCTAssertTrue(ScoreDifferentialChartView.actualIsALonePoint([nil, 1, nil]))
        XCTAssertFalse(ScoreDifferentialChartView.actualIsALonePoint([nil, nil]))
        XCTAssertFalse(ScoreDifferentialChartView.actualIsALonePoint([2, nil, 1]))
        XCTAssertFalse(ScoreDifferentialChartView.actualIsALonePoint([]))
    }
}
