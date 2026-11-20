import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Item 7 Surface #2 (#12959 / #12581) — Team Championship Path `source_mark`
/// served on `GET /api/teams/{slug}` (`championship_path[].source_mark`).
/// - Active steps pass `entry.probability` to `SourceMarkButton` (`compactRow: true`).
/// - Grid-verdict steps (`Won` / `Out`) pass `number: nil` so the sheet prints
///   the settled `"Official result"` row (`Won` / `Eliminated`) with no residual percentage.
/// - `state == "none"` or absent `source_mark` draws nothing (137-A: zero client inference).
@MainActor
final class TeamChampionshipPathSourceMarks12959Tests: XCTestCase {

    private func decodeEntry(_ json: String) throws -> ChampionshipPathEntry {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(ChampionshipPathEntry.self, from: Data(json.utf8))
    }

    func testActiveStepDecodesBlendMarkAndBuildsSourceMarkButtonWithProbability() throws {
        let entry = try decodeEntry("""
        {
          "tier": 2,
          "label": "Conference",
          "market_name": "Eastern Conference Champion",
          "market_id": 60120,
          "probability": 0.2075,
          "rank": 2,
          "movement": 0.012,
          "source_mark": {
            "state": "blend",
            "sources": [
              {"key": "kalshi", "name": "Kalshi", "probability": 0.20, "observed_at": null},
              {"key": "polymarket", "name": "Polymarket", "probability": 0.215, "observed_at": null}
            ],
            "method": "Bain Luck blend · average of 2 prices before rounding"
          }
        }
        """)
        XCTAssertEqual(entry.sourceMark?.state, SourceMark.State.blend)
        XCTAssertEqual(entry.sourceMark?.sources.count, 2)
        XCTAssertNil(entry.gridVerdict)

        let btn = try XCTUnwrap(
            SourceMarkButton(entry.sourceMark, number: entry.probability, numberSize: 15, compactRow: true)
        )
        XCTAssertEqual(try XCTUnwrap(btn.number), 0.2075, accuracy: 0.0001)
        XCTAssertEqual(SourceMarkSheet.headline(btn.number), "21%")
        XCTAssertEqual(
            SourceMarkSheet.method(try XCTUnwrap(entry.sourceMark)),
            "Bain Luck blend · average of 2 prices before rounding"
        )
    }

    func testSettledGridStepUsesSettledVerdictMarkWithNilNumberAndNoneDrawsNothing() throws {
        let eliminated = try decodeEntry("""
        {
          "tier": 2,
          "label": "Conference",
          "market_name": "Western Conference Champion",
          "market_id": 60199,
          "probability": 0.001,
          "rank": 15,
          "movement": null,
          "state": "eliminated",
          "source_mark": {
            "state": "settled",
            "sources": [],
            "settled": {"source": null, "result": "Eliminated", "at": null}
          }
        }
        """)
        XCTAssertEqual(eliminated.gridVerdict, .eliminated)
        let mark = try XCTUnwrap(eliminated.sourceMark)
        XCTAssertEqual(mark.state, SourceMark.State.settled)
        XCTAssertTrue(mark.draws)
        // TeamDetailView passes `number: nil` on `.out` / `.won` so residual 0.1% is never printed.
        let btn = try XCTUnwrap(SourceMarkButton(mark, number: nil, numberSize: 15, compactRow: true))
        XCTAssertNil(btn.number)
        XCTAssertEqual(
            SourceMarkSheet.settledLine(mark),
            .init(name: "Official result", price: "Eliminated", age: nil)
        )

        let noneEntry = try decodeEntry("""
        {
          "tier": 3,
          "label": "Division",
          "market_name": "Atlantic Division Winner",
          "market_id": 60200,
          "probability": 0.45,
          "rank": 1,
          "movement": null,
          "source_mark": {"state": "none", "sources": []}
        }
        """)
        XCTAssertNil(SourceMarkButton(noneEntry.sourceMark, number: noneEntry.probability, numberSize: 15, compactRow: true))
    }

    // MARK: - Live 390 pt Light & Dark Render Export

    private func captureWindowSnapshot<V: View>(
        _ content: V,
        scheme: ColorScheme,
        width: CGFloat = 390,
        fixedHeight: CGFloat
    ) async throws -> UIImage {
        let host = hostForMeasurement(content.environment(\.colorScheme, scheme), at: .large)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = .large

        let bounds = CGRect(x: 0, y: 0, width: width, height: fixedHeight)
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = .large
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = bounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        try await Task.sleep(nanoseconds: 700_000_000)
        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    func testRenderLiveTeamChampionshipPathSourceMarks390() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let outDir = env["RENDER_12959_DIR"], !outDir.isEmpty,
              let jsonPath = env["RENDER_12959_JSON"], !jsonPath.isEmpty else {
            return
        }
        try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

        let rawData = try Data(contentsOf: URL(fileURLWithPath: jsonPath))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let page = try decoder.decode(TeamPageResponse.self, from: rawData)

        let stepWithMark = try XCTUnwrap(
            page.championshipPath.first(where: { $0.sourceMark?.draws == true }),
            "Live team payload must carry at least one championship_path step with a drawable source_mark"
        )
        let mark = try XCTUnwrap(stepWithMark.sourceMark)

        var preloadedLogos: [URL: Image] = [:]
        if let logoStr = page.team.logoLarge ?? page.team.logoSmall,
           let url = URL(string: logoStr),
           let (imgData, _) = try? await URLSession.shared.data(from: url),
           let uiImg = UIImage(data: imgData) {
            preloadedLogos[url] = Image(uiImage: uiImg)
        }

        let suiteName = "Render12959.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        for (tag, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
            let pageView = NavigationStack {
                TeamDetailView(
                    slug: page.team.slug,
                    loadedPageForTest: page,
                    preloadedAvatarImagesForTest: preloadedLogos
                )
            }
            .environmentObject(pinManager)

            let cardImg = try await captureWindowSnapshot(pageView, scheme: scheme, width: 390, fixedHeight: 460)
            try XCTUnwrap(cardImg.pngData()).write(
                to: URL(fileURLWithPath: "\(outDir)/12959-championship-path-\(tag)-390.png")
            )

            let sheetView = SourceMarkSheet(
                mark: mark,
                number: stepWithMark.gridVerdict == nil ? stepWithMark.probability : nil
            )
            let sheetImg = try await captureWindowSnapshot(sheetView, scheme: scheme, width: 390, fixedHeight: 430)
            try XCTUnwrap(sheetImg.pngData()).write(
                to: URL(fileURLWithPath: "\(outDir)/12959-championship-path-sheet-\(tag)-390.png")
            )
        }
    }
}
