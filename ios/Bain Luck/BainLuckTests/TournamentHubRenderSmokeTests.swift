import SwiftUI
import XCTest
@testable import Bain_Luck

/// Deterministic, network-free RENDER evidence for the US Open hub (G2).
///
/// `TournamentHubSurface` exists as a separate view from `TournamentHubView`
/// precisely so this can run: a screen that owns its own `.task` rasterises its
/// loading skeleton and the resulting PNG proves nothing about the rows.
///
/// The assertion that matters is the D27 one — **the honest-empty screen must
/// not be a blank page.** A tournament that returns nothing renders sentences,
/// so its raster is substantial and differs from the populated one. That is the
/// failure a screenshot of a good day can never catch.
///
/// Two traps this file is shaped around, both measured before:
/// a tall page returns `nil` from `pngData()` rather than a truncated image, so
/// the sections are rendered from small payloads rather than all at once; and a
/// `nil` unwrap inside an assertion kills the whole test host, so every render
/// goes through `XCTUnwrap` with a message.
@MainActor
final class TournamentHubRenderSmokeTests: XCTestCase {

    private func render(
        _ presentation: TournamentHubPresentation,
        name: String,
        scale: CGFloat = 2
    ) throws -> Data {
        let surface = TournamentHubSurface(presentation: presentation)
            .padding(16)
            .frame(width: 390)

        let renderer = ImageRenderer(content: surface)
        renderer.scale = scale
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        XCTAssertGreaterThan(image.size.width, 0)
        XCTAssertGreaterThan(image.size.height, 0)

        let png = try XCTUnwrap(
            image.pngData(),
            "\(name) produced no PNG data — usually means the render was too tall, "
            + "which reads as 'no evidence' rather than as a failure")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("tournament-hub-\(name).png")
        try? png.write(to: url)
        print("Tournament hub render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    private func presentation(_ json: String) -> TournamentHubPresentation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return TournamentHubPresentation(
            response: try! decoder.decode(TournamentHubResponse.self, from: Data(json.utf8)))
    }

    func testTheRealPayloadRasterises() throws {
        let png = try render(
            TournamentHubPresentation(response: try TournamentHubProdFixture.decode()),
            name: "us-open-live",
            // Scale 1: the full page at scale 2 is over the height at which
            // `pngData()` starts returning nil.
            scale: 1)
        XCTAssertGreaterThan(png.count, 5_000, "the live hub render is suspiciously empty")
    }

    func testAnEmptyTournamentRendersSentencesRatherThanABlankPage() throws {
        let empty = try render(presentation(Self.emptyJSON), name: "empty")
        XCTAssertGreaterThan(
            empty.count, 3_000,
            "a tournament with no matches, no results and no board must still "
            + "render its honest-empty sentences — a near-blank raster here is "
            + "the exact D27 failure this screen exists to avoid")

        let populated = try render(
            TournamentHubPresentation(response: try TournamentHubProdFixture.decode()),
            name: "us-open-live-scale2-compare",
            scale: 1)
        XCTAssertNotEqual(
            empty, populated,
            "the empty and populated states must not rasterise identically")
    }

    /// #3043. The presentation tests prove the five questions REDUCE correctly;
    /// this proves the surface actually draws them. A section wired into the
    /// value type and left out of the view passes every one of those tests and
    /// is invisible on the phone — which is exactly how the web's own props
    /// section spent a release rendering an empty state nobody could see
    /// (UX-P139, "the section was INVISIBLE in the artifact Alex viewed").
    func testTheCuratedQuestionsAreDrawnAndNotJustComputed() throws {
        let withProps = try render(
            try TournamentHubPropsFixture.presentation(), name: "props", scale: 1)
        let withoutProps = try render(presentation(Self.emptyJSON), name: "props-none", scale: 1)
        XCTAssertGreaterThan(
            withProps.count, withoutProps.count,
            "five questions must make the page taller than the sentence that "
            + "stands in for them")
    }

    func testRenderingIsDeterministicForAFixedPayload() throws {
        let first = try render(presentation(Self.emptyJSON), name: "empty-a")
        let second = try render(presentation(Self.emptyJSON), name: "empty-b")
        XCTAssertEqual(
            first, second,
            "the surface depends on no clock, no network and no ambient state")
    }

    private static let emptyJSON = """
    {"slug": "us-open", "title": "US Open 2026", "subtitle": "Flushing Meadows",
     "slate": {"matches": [], "count": 0},
     "results": {"matches": [], "count": 0},
     "boards": [], "bracket": {}, "event_links": {"by_espn": {}}, "broadcasts": []}
    """
}
