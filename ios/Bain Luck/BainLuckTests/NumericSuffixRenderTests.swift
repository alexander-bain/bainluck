import SwiftUI
import XCTest
@testable import Bain_Luck

/// L2-226 Item 2 — deterministic, network-free proof that a repaired `…24h`
/// value reaches PIXELS, not just a property.
///
/// A decode test proves the number is in the model. It does not prove the number
/// is on screen — and "the field decodes now" was never the user-visible claim.
/// This drives two real, already-shipped consumers through `ImageRenderer` from
/// fixed local payloads (the L2-225 pattern) and asserts the render with the
/// movement value DIFFERS from the render without it. Before this queue both
/// renders were byte-identical, because the value was always `nil`.
///
/// No new rendered treatment is introduced: both movement rows already existed
/// and were simply unreachable.
@MainActor
final class NumericSuffixRenderTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func rasterize<V: View>(_ view: V, name: String) throws -> Data {
        let renderer = ImageRenderer(content: view.frame(width: 360))
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        XCTAssertGreaterThan(image.size.width, 0)
        XCTAssertGreaterThan(image.size.height, 0)
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("l2226-\(name).png")
        try? png.write(to: url)
        print("L2-226 render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        XCTAssertGreaterThan(png.count, 1_000, "\(name) render is suspiciously empty")
        return png
    }

    // MARK: - GolfModels family → TournamentHeroCard

    private func tournament(withMovement: Bool) throws -> GolfTournamentData {
        let movement = withMovement ? #", "movement_24h": 0.023"# : ""
        let json = #"""
        {"key": "the_open_championship", "name": "The Open Championship",
         "slug": "the-open", "is_major": true, "tour": "pga",
         "venue": "Royal Portrush", "location": "Northern Ireland",
         "golfers": [
           {"name": "Scottie Scheffler", "probability": 0.62, "rank": 1\#(movement)},
           {"name": "Rory McIlroy", "probability": 0.145, "rank": 2}
         ]}
        """#
        return try decoder().decode(GolfTournamentData.self, from: Data(json.utf8))
    }

    func testGolferMovementReachesTheTournamentHeroCard() throws {
        let withMovement = try tournament(withMovement: true)
        XCTAssertEqual(
            withMovement.golfers.first?.movement24h, 0.023,
            "precondition: the fixture must actually carry the movement")
        XCTAssertNil(try tournament(withMovement: false).golfers.first?.movement24h)

        let withPNG = try rasterize(
            TournamentHeroCard(tournament: withMovement), name: "golf-with-movement")
        let withoutPNG = try rasterize(
            TournamentHeroCard(tournament: try tournament(withMovement: false)),
            name: "golf-no-movement")

        XCTAssertNotEqual(
            withPNG, withoutPNG,
            "movement_24h must change what the hero card draws — identical rasters "
            + "are exactly the silent-nil failure this queue repairs")
    }

    // MARK: - FuturesModels family → ChampionshipPathView

    private func progression(withTrend: Bool) throws -> TeamProgressionResponse {
        let trend = withTrend ? #", "trend_24h": -0.031"# : ""
        let json = #"""
        {"event_id": 4242, "league": "mlb", "league_name": "MLB",
         "home_team": {"name": "Los Angeles Dodgers", "short_name": "Dodgers",
                       "record": "62-40",
                       "stages": [
                         {"key": "division", "label": "Win Division", "probability": 0.71\#(trend)},
                         {"key": "pennant", "label": "Win Pennant", "probability": 0.34}
                       ]}}
        """#
        return try decoder().decode(TeamProgressionResponse.self, from: Data(json.utf8))
    }

    func testStageTrendReachesTheChampionshipPath() throws {
        let withTrend = try progression(withTrend: true)
        XCTAssertEqual(
            withTrend.homeTeam?.stages.first?.trend24h, -0.031,
            "precondition: the fixture must actually carry the trend")
        XCTAssertNil(try progression(withTrend: false).homeTeam?.stages.first?.trend24h)

        let withPNG = try rasterize(
            ChampionshipPathView(progression: withTrend), name: "path-with-trend")
        let withoutPNG = try rasterize(
            ChampionshipPathView(progression: try progression(withTrend: false)),
            name: "path-no-trend")

        XCTAssertNotEqual(
            withPNG, withoutPNG,
            "trend_24h must change what the championship path draws")
    }

    // MARK: - Determinism

    /// The fixtures depend on no clock, no network, and no ambient state, so the
    /// same payload must rasterise to the same bytes every run. Without this a
    /// "the rasters differ" assertion could pass on noise.
    func testRendersAreDeterministicForAFixedPayload() throws {
        let a = try rasterize(
            TournamentHeroCard(tournament: try tournament(withMovement: true)),
            name: "golf-determinism-a")
        let b = try rasterize(
            TournamentHeroCard(tournament: try tournament(withMovement: true)),
            name: "golf-determinism-b")
        XCTAssertEqual(a, b)
    }
}
