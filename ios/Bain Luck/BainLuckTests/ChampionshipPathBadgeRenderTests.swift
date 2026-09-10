import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4757: the Championship Path's no-logo crest placeholder draws the SHARED
/// badge, not two hand-taken characters.
///
/// Why this file rasterises instead of asserting on a string: the badge lives
/// inline in `ChampionshipPathView`'s `AsyncImage` fallback, and there is no
/// function to call. The two sites are reachable only when a team has no logo
/// (the `else` branch, exercised here) or while its image is still loading (the
/// `default:` branch of the `phase` switch) — states that production teams in
/// MLB/NFL/NBA/NHL almost never sit in, so a simulator screenshot of a real
/// fixture cannot be relied on to contain them. Rendering the view with a
/// fixture that FORCES the branch produces the exact pixels a reader would get,
/// which is a stronger artifact than a screenshot of a state we cannot summon.
/// Same technique `NumericSuffixRenderTests` uses on this very view.
///
/// The defect: the placeholder took `String((team.shortName ?? team.name).prefix(2))`.
/// For a club whose designator LEADS the name that is the designator itself —
/// "FC Schalke 04" drew `FC`, "1. FC Heidenheim 1846" drew `1.`. `abbreviation`
/// returns `SCH` and `HEI`, which is what every other badge in the app draws.
/// `@MainActor` on the class, matching `NumericSuffixRenderTests`: `ImageRenderer`
/// is main-actor-isolated, so a rasterising suite has no nonisolated half to keep.
@MainActor
final class ChampionshipPathBadgeRenderTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    /// A progression whose teams carry NO `logo_url`, which is the whole point:
    /// it is the only payload shape that reaches the placeholder.
    private func progression(homeName: String, awayName: String) throws -> TeamProgressionResponse {
        let json = #"""
        {"event_id": 4757, "league": "soccer", "league_name": "Bundesliga",
         "home_team": {"name": "\#(homeName)", "record": "12-6",
                       "stages": [
                         {"key": "title", "label": "Win Title", "probability": 0.22},
                         {"key": "top4", "label": "Top Four", "probability": 0.58}
                       ]},
         "away_team": {"name": "\#(awayName)", "record": "9-9",
                       "stages": [
                         {"key": "title", "label": "Win Title", "probability": 0.08},
                         {"key": "top4", "label": "Top Four", "probability": 0.31}
                       ]}}
        """#
        return try decoder().decode(TeamProgressionResponse.self, from: Data(json.utf8))
    }

    @discardableResult
    private func rasterize<V: View>(_ view: V, name: String) throws -> Data {
        let renderer = rendererForMeasurement(view.frame(width: 360))
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("n097-\(name).png")
        try? png.write(to: url)
        print("#4757 render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        XCTAssertGreaterThan(png.count, 1_000, "\(name) render is suspiciously empty")
        return png
    }

    /// The precondition the whole file rests on. If the fixture ever grows a
    /// logo URL the placeholder stops rendering and every raster below would be
    /// photographing the wrong branch while still passing.
    func testFixtureReachesThePlaceholderBranch() throws {
        let p = try progression(homeName: "FC Schalke 04", awayName: "1. FC Heidenheim 1846")
        XCTAssertNil(p.homeTeam?.logoUrl, "precondition: no logo, or the placeholder never draws")
        XCTAssertNil(p.awayTeam?.logoUrl)
        XCTAssertNil(p.homeTeam?.shortName, "precondition: the badge must fall through to `name`")
    }

    /// The badge values the placeholder is now wired to. These are the strings
    /// `TeamShortName` already pins; asserting them here records what the raster
    /// below should be showing, so a reader of the artifact knows what to look for.
    func testTheSharedRuleNamesTheClubNotItsDesignator() {
        XCTAssertEqual(TeamShortName.abbreviation("FC Schalke 04"), "SCH")
        XCTAssertEqual(TeamShortName.abbreviation("1. FC Heidenheim 1846"), "HEI")
        XCTAssertEqual(TeamShortName.abbreviation("AD Ceuta FC"), "CEU")

        // What the placeholder used to draw, kept as the contrast: two characters
        // off the raw name is the designator, every time the designator leads.
        for name in ["FC Schalke 04", "1. FC Heidenheim 1846", "AD Ceuta FC"] {
            let old = String(name.prefix(2))
            XCTAssertNotEqual(
                old, TeamShortName.abbreviation(name),
                "if these ever agree this test has stopped discriminating")
        }
    }

    /// Renders the real view through the real branch and writes the PNG. The
    /// artifact is the point — it is read by hand as the LOOK for this change,
    /// because the branch cannot be summoned on a production screenshot.
    func testPlaceholderRasterisesForDesignatorLeadingClubs() throws {
        let p = try progression(homeName: "FC Schalke 04", awayName: "1. FC Heidenheim 1846")
        try rasterize(ChampionshipPathView(progression: p), name: "champpath-designator-clubs")
    }

    /// A club whose badge does NOT change must still render, so the change is
    /// shown to be scoped to the names it was for rather than to every card.
    func testPlaceholderStillRendersForAnOrdinaryClub() throws {
        let p = try progression(homeName: "Borussia Dortmund", awayName: "Bayer Leverkusen")
        try rasterize(ChampionshipPathView(progression: p), name: "champpath-ordinary-clubs")
    }
}
