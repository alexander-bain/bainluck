import SwiftUI
import XCTest
@testable import Bain_Luck

/// The only camera that reaches the score chart (#3269).
///
/// It sits below the fold on the event page, `simctl` has no scroll, and no
/// scroll rig exists (checked again 2026-09-05: no idb, no cliclick, no pyobjc
/// Quartz — the same finding native/023 recorded for the race board). So the
/// chart that #3237's corrections were never applied to could not be
/// photographed at all, and "fixed by construction, same shared functions as the
/// chart above it" is not evidence. This renders the real view from a real
/// payload through `ImageRenderer` instead.
///
/// The fixture is 15302914 (Arizona @ Houston, 2026-09-04, 155 minutes) reduced
/// to its shape: a projection point every five minutes, ESPN innings, and the
/// two scoring moments. Reduced fixtures back SHAPE, not counts — nothing here
/// asserts a census.
@MainActor
final class ScoreDifferentialChartRenderSmokeTests: XCTestCase {

    private static let commence = "2026-09-05T00:10:00Z"
    private static let completed = "2026-09-05T02:45:00Z"

    /// The domain `EventDetailView` hands BOTH charts, so the axis this renders
    /// is the axis the win-probability chart above it renders.
    private var sharedDomain: ClosedRange<Date> {
        Self.commence.asDate!...Self.completed.asDate!
    }

    private func fixture() throws -> EventHistoryResponse {
        let start = Self.commence.asDate!
        let iso = ISO8601DateFormatter()

        var odds: [String] = []
        var espn: [String] = []
        for step in 0...31 {
            let at = iso.string(from: start.addingTimeInterval(Double(step) * 300))
            // A projected margin that drifts from +0.5 to +3.
            let projHome = 4.5 + Double(step) * 0.08
            odds.append("""
                {"timestamp": "\(at)", "home_probability": 0.55,
                 "projected_home_score": \(projHome), "projected_away_score": 4.0}
                """)
            // Nine innings over the 155 minutes, ~17 minutes each.
            let inning = min(9, step / 3 + 1)
            let half = step % 3 == 0 ? "Top" : "Bottom"
            let homeScore = step >= 12 ? 3 : 0
            let awayScore = step >= 21 ? 1 : 0
            espn.append("""
                {"timestamp": "\(at)", "period": "\(half) \(inning)",
                 "home_score": \(homeScore), "away_score": \(awayScore)}
                """)
        }

        let json = """
        {"event_id": 15302914, "home_team": "Houston Astros",
         "away_team": "Arizona Diamondbacks",
         "completed_at": "\(Self.completed)", "status": "completed",
         "history": [\(odds.joined(separator: ","))],
         "espn_history": [\(espn.joined(separator: ","))]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func render(_ name: String, forcedDomain: ClosedRange<Date>?) throws -> Data {
        let view = ScoreDifferentialChartView(
            history: try fixture(),
            homeTeam: "Houston Astros",
            awayTeam: "Arizona Diamondbacks",
            sportKey: "baseball_mlb",
            commenceTime: Self.commence,
            eventStatus: "completed",
            homeTeamColor: .blue,
            awayTeamColor: .gray,
            homeTeamAbbrev: "HOU",
            awayTeamAbbrev: "ARI",
            forcedDomain: forcedDomain
        )
        .padding(16)
        .frame(width: 390)

        let renderer = ImageRenderer(content: view)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("score-diff-\(name).png")
        try? png.write(to: url)
        print("Score chart render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    /// The chart draws, from a payload the app actually receives. A raster is
    /// the only thing that can show a chip sitting on the wrong gridline, which
    /// is what #3237 fixed above and what was left here.
    func testTheScoreChartRasterisesFromARealPayload() throws {
        let png = try render("shared-domain", forcedDomain: sharedDomain)
        XCTAssertGreaterThan(png.count, 5_000, "the score chart render is suspiciously empty")
    }

    /// Nothing in the view reads a clock, a network or ambient state, so the
    /// same payload rasterises identically. Without this the render above proves
    /// only that something was drawn once.
    func testRenderingIsDeterministic() throws {
        XCTAssertEqual(
            try render("determinism-a", forcedDomain: sharedDomain),
            try render("determinism-b", forcedDomain: sharedDomain))
    }

    /// The chart is handed `forcedDomain` precisely so it agrees with the
    /// win-probability chart above it, and the two now derive their ticks from
    /// one function. Pinned on the fixture's own domain: 155 minutes at phone
    /// width takes the 45-minute rung, in minutes, not hours.
    func testItsAxisIsTheMatchChartsAxis() {
        let plan = OddsChartView.xAxisPlan(for: sharedDomain, plotWidth: 293)
        XCTAssertEqual(plan.component, .minute)
        XCTAssertEqual(plan.count, 45)
        XCTAssertEqual(plan.labelStyle, .timeOfDay)
    }
}
