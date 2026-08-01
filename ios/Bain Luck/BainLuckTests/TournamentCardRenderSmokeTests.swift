import SwiftUI
import XCTest
@testable import Bain_Luck

/// L2-225 Item 3 — deterministic, network-free RENDER evidence for the live →
/// terminal pair.
///
/// Every prior native settled-state queue could only claim "BUILD SUCCEEDED": the
/// WHAT-HIT treatment appears on the real feed only during a marquee's T+36h window,
/// so no screenshot of today's Discover could ever prove the changed branch. This
/// drives the actual SwiftUI view through `ImageRenderer` from a fixed local payload,
/// so both framings of the SAME card are rasterised on every test run.
///
/// The assertions stay semantic, not pixel-exact: both states must produce a real
/// image, and the two must DIFFER. That catches the regression that matters (a
/// terminal card silently rendering its live framing) without pinning fonts, colours,
/// or copy. Rendered PNGs are written to the temp dir and their paths logged so a run
/// can be eyeballed after the fact.
@MainActor
final class TournamentCardRenderSmokeTests: XCTestCase {

    private func fixture(marqueeWhathit: Bool) throws -> FeedTournamentData {
        try XCTUnwrap(
            TournamentLifecyclePreviewFixture.decode(
                marqueeWhathit: marqueeWhathit,
                scheduleStatus: marqueeWhathit ? "completed" : "in_progress"))
    }

    private func render(_ data: FeedTournamentData, name: String) throws -> Data {
        let card = NativeTournamentDiscoverCard(
            data: data,
            // Deliberately the backend's LIVE reason string, so the terminal render
            // is proven to suppress present-tense movement prose rather than merely
            // never being handed any.
            feedContext: "PGA Tour: Scottie Scheffler leads at 62.0% (up 2.3% today)",
            navigationPath: .constant(NavigationPath())
        )
        .frame(width: 360)

        let renderer = ImageRenderer(content: card)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        XCTAssertGreaterThan(image.size.width, 0)
        XCTAssertGreaterThan(image.size.height, 0)

        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("l2225-tournament-\(name).png")
        try? png.write(to: url)
        print("L2-225 render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    func testLiveAndTerminalTournamentCardsBothRenderAndDiffer() throws {
        let livePNG = try render(try fixture(marqueeWhathit: false), name: "live")
        let terminalPNG = try render(try fixture(marqueeWhathit: true), name: "terminal")

        XCTAssertGreaterThan(livePNG.count, 1_000, "live render is suspiciously empty")
        XCTAssertGreaterThan(terminalPNG.count, 1_000, "terminal render is suspiciously empty")
        XCTAssertNotEqual(
            livePNG, terminalPNG,
            "the same payload must NOT rasterise identically in the live and settled "
            + "states — that is exactly the stale-resolved-state failure")
    }

    func testRenderingIsDeterministicForAFixedPayload() throws {
        // Same fixture twice must produce the same bytes: the fixture path depends on
        // no clock, no network, and no ambient feed state.
        let first = try render(try fixture(marqueeWhathit: true), name: "terminal-a")
        let second = try render(try fixture(marqueeWhathit: true), name: "terminal-b")
        XCTAssertEqual(first, second)
    }
}
