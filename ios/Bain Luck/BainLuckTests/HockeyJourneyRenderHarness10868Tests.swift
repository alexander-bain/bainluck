import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #10868 — VISUAL QUALIFICATION HARNESS for the hockey journey screen
/// (`nhl-journey`), not a unit test and not production integration.
///
/// It builds the accepted screen from FULL retained `/api/events/{id}`,
/// `/history` and `/game-markets` bodies through the production adapters (parts
/// one, two, three and five) and rasterises it two ways:
///   - in a real `UIWindow` the size of the simulator's own screen, inside tab-bar
///     and navigation chrome, so safe areas and the tab bar take their real space
///     (`drawHierarchy`, the first screen a reader sees);
///   - the whole page at the screen's width (`rendererForMeasurement`), for review.
/// Each image is named event · phase · screen points · text size · appearance.
///
/// Inputs come from disk, never from the network: `CLI_FIXTURE_DIR` holds
/// `<case>-detail.json`, `<case>-history.json`, `<case>-game-markets.json`, and
/// images go to `CLI_RENDER_DIR` (pass both as `TEST_RUNNER_CLI_FIXTURE_DIR` /
/// `TEST_RUNNER_CLI_RENDER_DIR`). Without them the harness skips. The page-level
/// box score (`/related-futures`) was not retained, so player counts render as
/// their absence words — recorded, not filled.
///
/// The chrome here is a harness, not the app's host: mounting, real navigation,
/// sheets, Back/Done, paging and held updates remain Native's to integrate.
@MainActor
final class HockeyJourneyRenderHarness10868Tests: XCTestCase {

    private struct Case {
        let name: String
        /// The capture instant the page is read at.
        let now: String
    }

    private static let cases = [
        Case(name: "nhl-15169793", now: "2026-10-11T04:56:41Z"),
        Case(name: "nhl-15338034", now: "2026-10-30T20:13:55Z"),
        Case(name: "nhl-15338496", now: "2026-10-30T20:13:55Z"),
    ]

    private static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()
    private static let locale = Locale(identifier: "en_US")

    private func directories() throws -> (fixtures: URL, renders: URL) {
        let env = ProcessInfo.processInfo.environment
        guard let fixtures = env["CLI_FIXTURE_DIR"], let renders = env["CLI_RENDER_DIR"] else {
            throw XCTSkip("visual harness: CLI_FIXTURE_DIR / CLI_RENDER_DIR not set")
        }
        let out = URL(fileURLWithPath: renders, isDirectory: true)
        try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
        return (URL(fileURLWithPath: fixtures, isDirectory: true), out)
    }

    private func decode<T: Decodable>(_ type: T.Type, _ url: URL) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(contentsOf: url))
    }

    /// The page input exactly as a host would build it from these bodies.
    private func input(_ c: Case, fixtures: URL) throws -> HockeyJourneyPageInput10868 {
        let event = try decode(EventDetail.self, fixtures.appendingPathComponent("\(c.name)-detail.json"))
        let history = try decode(EventHistoryResponse.self, fixtures.appendingPathComponent("\(c.name)-history.json"))
        let markets = try decode(GameMarketsResponse.self, fixtures.appendingPathComponent("\(c.name)-game-markets.json"))
        let now = try XCTUnwrap(c.now.asDate)
        let host = HockeyJourneyPageAdapter10868.Host(
            probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, now: now,
            calendar: Self.pacific, locale: Self.locale)
        let phase = HockeyJourneyPageAdapter10868.phase(event, now: now)
        let historyInput = HockeyJourneyHistoryAdapter10868.history(
            history, event: event, phase: phase,
            host: HockeyJourneyHistoryAdapter10868.Host(now: now, calendar: Self.pacific, locale: Self.locale))
        let contributions = HockeyJourneyContributionAdapter10868.Host(
            boxScore: nil, now: now, calendar: Self.pacific, locale: Self.locale)
        return HockeyJourneyPageInputAdapter10868.input(
            event, history: historyInput,
            points: HockeyJourneyContributionAdapter10868.points(event, markets: markets, host: contributions),
            assists: HockeyJourneyContributionAdapter10868.assists(event, markets: markets, host: contributions),
            originalsCount: QuestionCatalog9483.sourceOutcomeCount(markets),
            stream: .init(), host: host)
    }

    /// Tab bar + navigation chrome around the page, as a phone shows an event.
    private func chrome(_ page: HockeyJourneyEventPagePresentation10868) -> some View {
        TabView {
            NavigationStack {
                ScrollView { page.padding(.horizontal, 16) }
                    .navigationTitle("Event")
                    .navigationBarTitleDisplayMode(.inline)
            }
            .tabItem { Label("Discover", systemImage: "sparkles") }
        }
    }

    private func write(_ image: UIImage, _ name: String, to dir: URL) throws -> URL {
        let url = dir.appendingPathComponent("\(name).png")
        try XCTUnwrap(image.pngData(), "\(name): no PNG").write(to: url)
        print("CLI-10868 RENDER \(url.path) \(Int(image.size.width))x\(Int(image.size.height))")
        return url
    }

    func testTheHockeyJourneyScreenRendersFromRetainedProductionBodiesInRealChrome() throws {
        let dirs = try directories()
        let screen = UIScreen.main.bounds.size
        let points = "\(Int(screen.width))x\(Int(screen.height))"
        var manifest: [[String: String]] = []
        for c in Self.cases {
            let input = try input(c, fixtures: dirs.fixtures)
            for (sizeName, size) in [("default", DynamicTypeSize.large), ("ax3", DynamicTypeSize.accessibility3)] {
                for (styleName, style) in [("light", UIUserInterfaceStyle.light), ("dark", UIUserInterfaceStyle.dark)] {
                    let page = HockeyJourneyEventPagePresentation10868(input: input)
                    let name = "\(c.name)-\(input.phase)-\(points)-\(sizeName)-\(styleName)"

                    // First screen inside real chrome.
                    let window = UIWindow(frame: CGRect(origin: .zero, size: screen))
                    window.overrideUserInterfaceStyle = style
                    let host = UIHostingController(rootView: chrome(page).environment(\.dynamicTypeSize, size))
                    window.rootViewController = host
                    window.makeKeyAndVisible()
                    host.view.setNeedsLayout()
                    host.view.layoutIfNeeded()
                    RunLoop.main.run(until: Date().addingTimeInterval(0.4))
                    let first = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                        window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
                    }
                    let firstURL = try write(first, "\(name)-screen", to: dirs.renders)
                    window.isHidden = true

                    // The whole page at the screen's width.
                    let whole = rendererForMeasurement(
                        page.padding(.horizontal, 16).frame(width: screen.width)
                            .background(Color(uiColor: .systemBackground))
                            .environment(\.colorScheme, style == .dark ? .dark : .light),
                        at: size)
                    whole.scale = UIScreen.main.scale
                    let full = try XCTUnwrap(whole.uiImage, "\(name): whole page produced no raster")
                    XCTAssertGreaterThan(full.size.height, 0)
                    let fullURL = try write(full, "\(name)-page", to: dirs.renders)
                    manifest.append(["case": c.name, "phase": "\(input.phase)", "screen_points": points,
                                     "text_size": sizeName, "appearance": styleName,
                                     "screen_png": firstURL.lastPathComponent, "page_png": fullURL.lastPathComponent,
                                     "page_height_pt": "\(Int(full.size.height))"])
                }
            }
        }
        let data = try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: dirs.renders.appendingPathComponent("manifest-\(points).json"))
    }
}
