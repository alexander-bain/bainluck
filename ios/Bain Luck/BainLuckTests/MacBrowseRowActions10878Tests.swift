import XCTest
#if os(macOS)
import AppKit
import SwiftUI
#endif
#if canImport(Bain_Luck)
@testable import Bain_Luck
#endif

/// #10878 / #4942 / #5400 — right-click actions on Mac League (`SportCategoryView`)
/// and Team (`TeamDetailView`) browse rows.
///
/// Verifies the pure route-to-actions rule (`MacBrowseRowAction10878`), pin/unpin
/// state transitions, plain share URLs, label/icon parity with `CardContextMenu`,
/// `#if os(macOS)` isolation, and exact source wiring across `SportCategoryView`
/// and `TeamDetailView`.
@MainActor
final class MacBrowseRowActions10878Tests: XCTestCase {

    // MARK: - 1. Route Action Rules

    func testGameRowWithoutPinManagerOffersCopyLinkShareAndOpenInNewWindow() {
        XCTAssertEqual(
            MacBrowseRowAction10878.actions(for: .eventDetail(id: 15330459)),
            [
                .copyLink("https://bainluck.com/events/15330459"),
                .share(URL(string: "https://bainluck.com/events/15330459")!),
                .openInNewWindow(eventID: 15330459),
            ]
        )
    }

    func testGameRowWithPinManagerOffersPinOrUnpinBeforeCopyLinkShareAndOpenInNewWindow() {
        let unpinned = MacBrowseRowAction10878.actions(for: .eventDetail(id: 15330459), isPinned: false)
        XCTAssertEqual(
            unpinned,
            [
                .togglePin(isPinned: false, type: "event", id: 15330459),
                .copyLink("https://bainluck.com/events/15330459"),
                .share(URL(string: "https://bainluck.com/events/15330459")!),
                .openInNewWindow(eventID: 15330459),
            ]
        )
        XCTAssertEqual(unpinned.first?.title, "Pin")
        XCTAssertEqual(unpinned.first?.systemImage, "bookmark")

        let pinned = MacBrowseRowAction10878.actions(for: .eventDetail(id: 15330459), isPinned: true)
        XCTAssertEqual(
            pinned,
            [
                .togglePin(isPinned: true, type: "event", id: 15330459),
                .copyLink("https://bainluck.com/events/15330459"),
                .share(URL(string: "https://bainluck.com/events/15330459")!),
                .openInNewWindow(eventID: 15330459),
            ]
        )
        XCTAssertEqual(pinned.first?.title, "Unpin")
        XCTAssertEqual(pinned.first?.systemImage, "bookmark.slash")
    }

    func testMarketRowOffersCopyLinkAndShareWithOptionalPinAndNeverOpenInNewWindow() {
        let teamFuture = MacBrowseRowAction10878.actions(for: .futuresDetail(id: 6173044))
        XCTAssertEqual(
            teamFuture,
            [
                .copyLink("https://bainluck.com/futures/6173044"),
                .share(URL(string: "https://bainluck.com/futures/6173044")!),
            ]
        )

        let categoryFuture = MacBrowseRowAction10878.actions(for: .futuresDetail(id: 6173044), isPinned: false)
        XCTAssertEqual(
            categoryFuture,
            [
                .togglePin(isPinned: false, type: "future", id: 6173044),
                .copyLink("https://bainluck.com/futures/6173044"),
                .share(URL(string: "https://bainluck.com/futures/6173044")!),
            ]
        )
        for action in teamFuture + categoryFuture {
            if case .openInNewWindow = action {
                XCTFail("A market row must never offer Open in New Window")
            }
        }
    }

    func testLinksAreCanonicalPlainShareURLsWithoutTrackingQuery() {
        let game = MacBrowseRowAction10878.actions(for: .eventDetail(id: 42), isPinned: false)
        let market = MacBrowseRowAction10878.actions(for: .futuresDetail(id: 99), isPinned: true)
        XCTAssertTrue(game.contains(.copyLink(eventShareURL(42, style: .plain))))
        XCTAssertTrue(market.contains(.copyLink(futuresShareURL(99, style: .plain))))

        for action in game + market {
            switch action {
            case .copyLink(let link):
                XCTAssertFalse(link.contains("?"), "Copied link must not include tracking parameters: \(link)")
            case .share(let url):
                XCTAssertNil(url.query, "Shared URL must not include tracking parameters: \(url)")
            case .togglePin, .openInNewWindow:
                break
            }
        }
    }

    func testEveryOtherRouteGetsNoActionsAndNoPinTarget() {
        let unsupportedRoutes: [Route] = [
            .golfTournament(slug: "masters", name: "Masters"),
            .tournamentHub(slug: "us-open", name: "US Open"),
            .teamDetail(slug: "boston-celtics"),
            .containerHub(slug: "nba-playoffs", name: "NBA Playoffs"),
            .conceptCard(key: "event:ufc:ufc-310", name: "UFC 310"),
            .sportCategory(key: "basketball", name: "Basketball"),
            .leagueGrid(slug: "nba"),
            .futuresList,
            .eventModels(id: 15330459),
            .calibration,
        ]
        for route in unsupportedRoutes {
            XCTAssertNil(MacBrowseRowAction10878.pinTarget(for: route), "\(route)")
            XCTAssertEqual(MacBrowseRowAction10878.actions(for: route, isPinned: false), [], "\(route)")
            XCTAssertEqual(MacBrowseRowAction10878.actions(for: route, isPinned: nil), [], "\(route)")
        }
    }

    func testLabelsAndSymbolsMatchCardContextMenu() throws {
        let unpinnedGame = MacBrowseRowAction10878.actions(for: .eventDetail(id: 1), isPinned: false)
        XCTAssertEqual(
            unpinnedGame.map(\.title),
            ["Pin", "Copy Link", "Share", "Open in New Window"]
        )
        XCTAssertEqual(
            unpinnedGame.map(\.systemImage),
            ["bookmark", "link", "square.and.arrow.up", "macwindow.badge.plus"]
        )

        let sharedMenu = try Self.appSource("Components/CardContextMenu.swift")
        for item in unpinnedGame.dropFirst() {
            XCTAssertTrue(
                sharedMenu.contains("Label(\"\(item.title)\", systemImage: \"\(item.systemImage)\")"),
                "CardContextMenu no longer carries \(item.title) (\(item.systemImage))"
            )
        }
        XCTAssertTrue(
            sharedMenu.contains("Label(pin.isPinned ? \"Unpin\" : \"Pin\", systemImage: pin.isPinned ? \"bookmark.slash\" : \"bookmark\")")
        )
    }

    // MARK: - 2. SportCategoryView & TeamDetailView Source Wiring

    func testSportCategoryViewMarksEveryGameAndMarketLinkAndLeavesGolfTournamentsUnmarked() throws {
        let source = try Self.appSource("Views/SportCategoryView.swift")
        let lines = source.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }

        var navRoutes: [String] = []
        var menuAttaches: [String] = []

        for line in lines {
            if let route = Self.argument(of: "NavigationLink(value: Route.", in: line, closingBefore: ") {") {
                navRoutes.append(route)
            }
            if let menu = Self.argument(of: ".macBrowseRowMenu(", in: line, closingBefore: ")") {
                menuAttaches.append(menu)
            }
        }

        XCTAssertEqual(
            navRoutes,
            [
                "futuresDetail(id: market.id)",
                "eventDetail(id: event.id)",
                "futuresDetail(id: futures.id)",
                "golfTournament(slug: slug, name: tournament.name)",
            ],
            "SportCategoryView NavigationLink destinations changed"
        )
        XCTAssertEqual(
            menuAttaches,
            [
                ".futuresDetail(id: market.id), pinManager: pinManager",
                ".eventDetail(id: event.id), pinManager: pinManager",
                ".futuresDetail(id: futures.id), pinManager: pinManager",
            ],
            "Every event and futures NavigationLink in SportCategoryView must attach macBrowseRowMenu with pinManager"
        )
    }

    func testTeamDetailViewMarksEveryGameAndMarketLink() throws {
        let source = try Self.appSource("Views/TeamDetailView.swift")
        let lines = source.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }

        var navRoutes: [String] = []
        var menuAttaches: [String] = []

        for line in lines {
            if let route = Self.argument(of: "NavigationLink(value: Route.", in: line, closingBefore: ") {") {
                navRoutes.append(route)
            }
            if let menu = Self.argument(of: ".macBrowseRowMenu(", in: line, closingBefore: ")") {
                menuAttaches.append(menu)
            }
        }

        XCTAssertEqual(
            navRoutes,
            [
                "futuresDetail(id: entry.marketId)",
                "eventDetail(id: event.id)",
                "eventDetail(id: event.id)",
                "futuresDetail(id: future.marketId)",
            ],
            "TeamDetailView NavigationLink destinations changed"
        )
        XCTAssertEqual(
            menuAttaches,
            [
                ".futuresDetail(id: entry.marketId), pinManager: pinManager",
                ".eventDetail(id: event.id), pinManager: pinManager",
                ".eventDetail(id: event.id), pinManager: pinManager",
                ".futuresDetail(id: future.marketId), pinManager: pinManager",
            ],
            "Every Championship Path, Upcoming, Recent, and Season Futures link in TeamDetailView must attach macBrowseRowMenu with pinManager"
        )
    }

    func testModifierIsMacOnlyAndDrawsActionsFromRuleWithoutNavigating() throws {
        let source = try Self.appSource("Utilities/MacBrowseRowActions10878.swift")
        var platform: [String] = []
        var contextMenus = 0
        var windowOpeners = 0

        for line in source.components(separatedBy: "\n") {
            let text = line.trimmingCharacters(in: .whitespaces)
            if text.hasPrefix("#if ") { platform.append(text) }
            if text == "#else" { platform.append("#else of \(platform.popLast() ?? "")") }
            if text == "#endif" { _ = platform.popLast() }
            if text.contains(".contextMenu") {
                contextMenus += 1
                XCTAssertEqual(platform.last, "#if os(macOS)", ".contextMenu must be compiled only on macOS")
            }
            if text.contains("openWindow") {
                windowOpeners += 1
                XCTAssertTrue(platform.contains("#if os(macOS)"), "openWindow must be compiled only on macOS")
            }
        }
        XCTAssertEqual(contextMenus, 1)
        XCTAssertGreaterThan(windowOpeners, 0)

        let modifier = try XCTUnwrap(
            Self.slice(
                source,
                from: "func macBrowseRowMenu(_ route: Route, pinManager: PinManager? = nil) -> some View {",
                to: "\n    }\n"
            ),
            "macBrowseRowMenu signature changed"
        )
        let statements = modifier.components(separatedBy: "\n").dropFirst()
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        XCTAssertEqual(
            statements,
            [
                "#if os(macOS)",
                "modifier(MacBrowseRowMenu10878(route: route, pinManager: pinManager))",
                "#else",
                "self",
                "#endif",
            ]
        )

        let menuStruct = try XCTUnwrap(
            Self.slice(source, from: "private struct MacBrowseRowMenu10878: ViewModifier {", to: "\n#endif"),
            "MacBrowseRowMenu10878 moved"
        )
        XCTAssertTrue(menuStruct.contains("let actions = MacBrowseRowAction10878.actions(for: route, isPinned: isPinned)"))
        XCTAssertTrue(menuStruct.contains("if actions.isEmpty {\n            content\n"))
        XCTAssertTrue(menuStruct.contains("pinManager?.togglePin(type: type, id: id)"))
        XCTAssertTrue(menuStruct.contains("copyToClipboard(link)"))
        XCTAssertTrue(menuStruct.contains("ShareLink(item: url)"))
        XCTAssertTrue(menuStruct.contains("openWindow(value: eventID)"))
        for forbidden in ["navCoordinator", "NavigationLink", "path.append", "Copy Probability"] {
            XCTAssertFalse(menuStruct.contains(forbidden), "Menu modifier must not reference \(forbidden)")
        }
    }

    #if os(macOS)
    func testOffscreenRenderedMenuPreviewProducesNonEmptyBitmaps() throws {
        struct Scenario {
            let name: String
            let subtitle: String
            let rowHeadline: String
            let rowSubline: String
            let rowTrailing: String
            let route: Route
            let isPinned: Bool
        }
        let scenarios: [Scenario] = [
            Scenario(
                name: "01-sport-category-live-event-menu",
                subtitle: "SportCategoryView · Live Event Card Right-Click",
                rowHeadline: "Celtics @ Knicks",
                rowSubline: "NBA · Q3 4:12 · 81–77",
                rowTrailing: "BOS 62% · NYK 38%",
                route: .eventDetail(id: 15330459),
                isPinned: false
            ),
            Scenario(
                name: "02-sport-category-pinned-market-menu",
                subtitle: "SportCategoryView · League Market Row Right-Click (Pinned)",
                rowHeadline: "2026 NBA Champion",
                rowSubline: "Kalshi · +29 more",
                rowTrailing: "Celtics 24%",
                route: .futuresDetail(id: 6173044),
                isPinned: true
            ),
            Scenario(
                name: "03-team-detail-game-menu",
                subtitle: "TeamDetailView · Upcoming / Recent Game Row Right-Click (Pinned)",
                rowHeadline: "@ Knicks",
                rowSubline: "Oct 24 · 7:30 PM",
                rowTrailing: "62%",
                route: .eventDetail(id: 15330459),
                isPinned: true
            ),
            Scenario(
                name: "04-team-detail-future-menu",
                subtitle: "TeamDetailView · Championship Path / Season Futures Right-Click",
                rowHeadline: "Win Finals",
                rowSubline: "NBA Championship · #1",
                rowTrailing: "24%",
                route: .futuresDetail(id: 6173044),
                isPinned: false
            ),
        ]

        let outputDir = ProcessInfo.processInfo.environment["MAC_BROWSE_10878_SNAPSHOT_DIR"]
        if let outputDir {
            try FileManager.default.createDirectory(
                at: URL(fileURLWithPath: outputDir),
                withIntermediateDirectories: true
            )
        }

        for scenario in scenarios {
            let pm = PinManager()
            if scenario.isPinned, let target = MacBrowseRowAction10878.pinTarget(for: scenario.route) {
                pm.togglePin(type: target.type, id: target.id)
            }
            let actions = MacBrowseRowAction10878.actions(
                for: scenario.route,
                isPinned: scenario.isPinned
            )

            let preview = VStack(alignment: .leading, spacing: 8) {
                Text(scenario.subtitle)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)

                // Simulated browse row with real .macBrowseRowMenu attached
                HStack(alignment: .center, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(scenario.rowHeadline)
                            .font(.system(size: 13, weight: .semibold))
                        Text(scenario.rowSubline)
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(scenario.rowTrailing)
                        .font(.system(size: 12, weight: .bold).monospacedDigit())
                        .fixedSize(horizontal: true, vertical: false)
                }
                .padding(10)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color(nsColor: .controlBackgroundColor))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.accentColor.opacity(0.35), lineWidth: 1)
                )
                .macBrowseRowMenu(scenario.route, pinManager: pm)

                // Rendered right-click context menu items produced by MacBrowseRowAction10878
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(actions.enumerated()), id: \.offset) { idx, action in
                        HStack(spacing: 8) {
                            Image(systemName: action.systemImage)
                                .font(.system(size: 12, weight: .medium))
                                .frame(width: 16, alignment: .center)
                            Text(action.title)
                                .font(.system(size: 13))
                            Spacer()
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        if case .togglePin = action {
                            Divider().padding(.vertical, 2)
                        } else if idx < actions.count - 1 {
                            Divider().opacity(0.35)
                        }
                    }
                }
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color(nsColor: .controlBackgroundColor))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.primary.opacity(0.12), lineWidth: 1)
                )
            }
            .padding(12)
            .frame(width: 300)
            .background(Color(nsColor: .windowBackgroundColor))
            .environment(\.colorScheme, .light)

            let renderer = rendererForMeasurement(preview)
            renderer.scale = 2.0
            let cgImage = try XCTUnwrap(renderer.cgImage, "Failed to render \(scenario.name)")
            XCTAssertEqual(cgImage.width, 600)
            XCTAssertGreaterThan(cgImage.height, 200)

            if let outputDir {
                let rep = NSBitmapImageRep(cgImage: cgImage)
                let png = try XCTUnwrap(rep.representation(using: .png, properties: [:]))
                try png.write(to: URL(fileURLWithPath: outputDir).appendingPathComponent("\(scenario.name).png"))
            }
        }
    }
    #endif

    // MARK: - Helpers

    private static func appSource(_ relativePath: String, file: StaticString = #filePath) throws -> String {
        let appRoot = URL(fileURLWithPath: "\(file)")
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        return try String(contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    private static func slice(_ text: String, from start: String, to end: String) -> String? {
        guard let lower = text.range(of: start),
              let upper = text.range(of: end, range: lower.upperBound..<text.endIndex) else { return nil }
        return String(text[lower.lowerBound..<upper.lowerBound])
    }

    private static func argument(of prefix: String, in line: String, closingBefore suffix: String) -> String? {
        guard line.hasPrefix(prefix), line.hasSuffix(suffix) else { return nil }
        return String(line.dropFirst(prefix.count).dropLast(suffix.count))
    }
}
