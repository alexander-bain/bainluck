import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #10868 — VISUAL QUALIFICATION HARNESS for the hockey journey screen
/// (`nhl-journey`), not a unit test and not production integration.
///
/// It builds the screen from FULL retained `/api/events/{id}`, `/history` and
/// `/game-markets` bodies through the host glue's own pure build
/// (`HockeyJourneyEventPageHost10868.build`, which runs parts one to five) and
/// rasterises it:
///   - the page in a real `UIWindow` the size of the simulator's own screen,
///     inside tab-bar and navigation chrome, so safe areas and the tab bar take
///     their real space (`drawHierarchy`, the first screen a reader sees);
///   - the whole page, and each other mode the presentation offers (full-size
///     history, points and assists, the All props catalogue, one selected
///     original's Details, About), at the screen's width
///     (`rendererForMeasurement`), for review.
/// Each image is named event · box · phase · mode · screen points · text size ·
/// appearance.
///
/// Inputs come from disk, never from the network: `CLI_FIXTURE_DIR` holds
/// `<case>-detail.json`, `<case>-history.json`, `<case>-game-markets.json`, and
/// images go to `CLI_RENDER_DIR` (pass both as `TEST_RUNNER_CLI_FIXTURE_DIR` /
/// `TEST_RUNNER_CLI_RENDER_DIR`). Without them the harness skips.
///
/// BOX COUNTS — TEST-ONLY DECODING. The app's box (`/related-futures`
/// `box_score`) was not retained; the server fills it from the same
/// `box_score_data.players` the detail body serves, so `box: detail-copy`
/// cases decode that copy here into the host's `boxScore` contract. That is a
/// harness envelope, not the app's binding: the related-futures caller is
/// unproven. `box: missing` cases pass nil, as a page before that payload.
///
/// HARNESS CALLBACKS. Every callback is a no-op closure so the controls
/// render in their live state; tapping them in an image proves nothing. The
/// selected original is the catalogue's first, chosen here. The chrome is a
/// harness, not the app's host: mounting, real navigation, sheets, Back/Done,
/// paging and held updates remain Native's to integrate.
@MainActor
final class HockeyJourneyRenderHarness10868Tests: XCTestCase {
    private typealias Host = HockeyJourneyEventPageHost10868

    private enum Box: String {
        case detailCopy = "detail-copy"
        case missing
    }

    private struct Case {
        let name: String
        /// The capture instant the page is read at.
        let now: String
        let box: Box
    }

    private static let cases = [
        Case(name: "nhl-15169793", now: "2026-10-11T04:56:41Z", box: .detailCopy),
        Case(name: "nhl-15169793", now: "2026-10-11T04:56:41Z", box: .missing),
        Case(name: "nhl-15338034", now: "2026-10-30T20:13:55Z", box: .detailCopy),
        Case(name: "nhl-15338496", now: "2026-10-30T20:13:55Z", box: .missing),
    ]

    private static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()
    private static let locale = Locale(identifier: "en_US")

    private nonisolated struct BoxBody: Decodable {
        nonisolated struct Players: Decodable { let players: [String: [String: Double]]? }
        let boxScoreData: Players?
    }

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

    /// The page exactly as the host glue builds it from these bodies.
    private func built(_ c: Case, fixtures: URL,
                       reading: Host.Reading = .init()) throws -> Host.Built {
        let detailURL = fixtures.appendingPathComponent("\(c.name)-detail.json")
        let event = try decode(EventDetail.self, detailURL)
        let history = try decode(EventHistoryResponse.self, fixtures.appendingPathComponent("\(c.name)-history.json"))
        let markets = try decode(GameMarketsResponse.self, fixtures.appendingPathComponent("\(c.name)-game-markets.json"))
        let box = c.box == .detailCopy ? try decode(BoxBody.self, detailURL).boxScoreData?.players : nil
        return try XCTUnwrap(Host.build(
            event: event, history: history, markets: markets, boxScore: box,
            probabilityObservedAt: event.heroProbabilityObservedAt?.asDate,
            now: try XCTUnwrap(c.now.asDate), reading: reading,
            calendar: Self.pacific, locale: Self.locale))
    }

    /// The presentation with harness no-op callbacks, so offered controls are live.
    private func page(_ built: Host.Built, mode: HockeyJourneyPageMode10868) -> HockeyJourneyEventPagePresentation10868 {
        HockeyJourneyEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAbout: {}, onAllProps: {}, onOriginalSelect: { _ in }, onOriginalHistory: { _ in },
            onStoryIntent: { _ in }, onOpenStory: { _ in }, onHistoryAction: { _ in },
            onHistoryInspectionChoice: nil, onHistoryPlotPosition: nil,
            onPointsSelect: { _ in }, onPointsChoosePlayer: { _ in }, onPointsDetails: { _ in },
            onAssistsSelect: { _ in }, onAssistsChoosePlayer: { _ in }, onAssistsDetails: { _ in },
            pointsChoicesExpanded: .constant(false), pointsTimingExpanded: .constant(false),
            assistsChoicesExpanded: .constant(false), assistsTimingExpanded: .constant(false))
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

    private func whole(_ view: HockeyJourneyEventPagePresentation10868, width: CGFloat,
                       size: DynamicTypeSize, style: UIUserInterfaceStyle) throws -> UIImage {
        let renderer = rendererForMeasurement(
            view.padding(.horizontal, 16).frame(width: width)
                .background(Color(uiColor: .systemBackground))
                .environment(\.colorScheme, style == .dark ? .dark : .light),
            at: size)
        renderer.scale = UIScreen.main.scale
        let image = try XCTUnwrap(renderer.uiImage, "whole page produced no raster")
        XCTAssertGreaterThan(image.size.height, 0)
        return image
    }

    private static func modeName(_ mode: HockeyJourneyPageMode10868) -> String {
        switch mode {
        case .page: "page"
        case .reader(let card): "reader-\(card.rawValue)"
        case .catalogue: "catalogue"
        case .original: "original"
        case .about: "about"
        }
    }

    func testTheHockeyJourneyScreenRendersFromRetainedProductionBodiesInRealChrome() throws {
        let dirs = try directories()
        let screen = UIScreen.main.bounds.size
        let points = "\(Int(screen.width))x\(Int(screen.height))"
        var manifest: [[String: String]] = []
        for c in Self.cases {
            let plain = try built(c, fixtures: dirs.fixtures)
            // The catalogue's first original, selected here, for its Details.
            let first = plain.originals.catalogue.flatMap { catalogue in
                catalogue.originals.first.map { OriginalMarketDetails9483.Selection(scope: catalogue.scope,
                                                                                   identity: $0.identity) }
            }
            let chosen = try built(c, fixtures: dirs.fixtures, reading: Host.Reading(selection: first))
            var modes: [HockeyJourneyPageMode10868] = [.page, .reader(.history), .about]
            if plain.input.points != nil { modes.append(.reader(.points)) }
            if plain.input.assists != nil { modes.append(.reader(.assists)) }
            if plain.originals.catalogue != nil { modes.append(.catalogue) }
            if first != nil { modes.append(.original) }
            let stem = "\(c.name)-box-\(c.box.rawValue)-\(plain.input.phase)"

            for (sizeName, size) in [("default", DynamicTypeSize.large), ("ax3", DynamicTypeSize.accessibility3)] {
                for (styleName, style) in [("light", UIUserInterfaceStyle.light), ("dark", UIUserInterfaceStyle.dark)] {
                    let variant = "\(points)-\(sizeName)-\(styleName)"

                    // First screen inside real chrome.
                    let window = UIWindow(frame: CGRect(origin: .zero, size: screen))
                    window.overrideUserInterfaceStyle = style
                    let host = UIHostingController(rootView: chrome(page(plain, mode: .page))
                        .environment(\.dynamicTypeSize, size))
                    window.rootViewController = host
                    window.makeKeyAndVisible()
                    host.view.setNeedsLayout()
                    host.view.layoutIfNeeded()
                    RunLoop.main.run(until: Date().addingTimeInterval(0.4))
                    let firstScreen = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                        window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
                    }
                    let screenURL = try write(firstScreen, "\(stem)-page-\(variant)-screen", to: dirs.renders)
                    window.isHidden = true
                    manifest.append(["case": c.name, "box": c.box.rawValue, "phase": "\(plain.input.phase)",
                                     "mode": "page-first-screen", "screen_points": points, "text_size": sizeName,
                                     "appearance": styleName, "png": screenURL.lastPathComponent,
                                     "height_pt": "\(Int(firstScreen.size.height))"])

                    for mode in modes {
                        let source = mode == .original ? chosen : plain
                        let image = try whole(page(source, mode: mode), width: screen.width, size: size, style: style)
                        let url = try write(image, "\(stem)-\(Self.modeName(mode))-\(variant)", to: dirs.renders)
                        manifest.append(["case": c.name, "box": c.box.rawValue, "phase": "\(plain.input.phase)",
                                         "mode": Self.modeName(mode), "screen_points": points,
                                         "text_size": sizeName, "appearance": styleName,
                                         "png": url.lastPathComponent, "height_pt": "\(Int(image.size.height))"])
                    }
                }
            }
        }
        let data = try JSONSerialization.data(withJSONObject: manifest, options: [.prettyPrinted, .sortedKeys])
        try data.write(to: dirs.renders.appendingPathComponent("manifest-\(points).json"))
    }
}
