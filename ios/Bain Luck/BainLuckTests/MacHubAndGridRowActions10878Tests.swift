import XCTest
import SwiftUI
#if canImport(AppKit)
import AppKit
#endif
#if canImport(ImageIO)
import ImageIO
import UniformTypeIdentifiers
#endif
#if canImport(Bain_Luck)
@testable import Bain_Luck
#endif

/// #10878 / #4942 / #5400 / #4931 — right-clicking a game, match, bout, mover,
/// or market row on Mac Explore (`FuturesListView`), Championship Grids
/// (`LeagueGridView`), Featured Tournament Hubs (`TournamentHubView`), or
/// Fight Cards (`ConceptCardView`) offers `Pin`/`Unpin` (when `PinManager` is
/// supplied), `Copy Link`, `Share`, and (for event-backed games/matches/bouts
/// only) `Open in New Window`.
@MainActor
final class MacHubAndGridRowActions10878Tests: XCTestCase {

    // MARK: - Rule: Game / Match / Bout (.eventDetail)

    func testGameMatchOrBoutWithoutPinManagerOffersCopyLinkShareAndOpenInNewWindow() throws {
        let actions = MacHubAndGridRowAction10878.actions(for: .eventDetail(id: 9812))

        XCTAssertEqual(
            actions,
            [
                .copyLink("https://bainluck.com/events/9812"),
                .share(try XCTUnwrap(URL(string: "https://bainluck.com/events/9812"))),
                .openInNewWindow(eventID: 9812),
            ]
        )
        XCTAssertEqual(actions.map(\.title), ["Copy Link", "Share", "Open in New Window"])
        XCTAssertEqual(
            actions.map(\.systemImage),
            ["link", "square.and.arrow.up", "macwindow.badge.plus"]
        )
    }

    func testGameMatchOrBoutWithPinManagerOffersPinOrUnpinBeforeCopyLinkShareAndOpenInNewWindow() throws {
        let unpinned = MacHubAndGridRowAction10878.actions(for: .eventDetail(id: 9812), isPinned: false)
        XCTAssertEqual(
            unpinned,
            [
                .togglePin(isPinned: false, type: "event", id: 9812),
                .copyLink("https://bainluck.com/events/9812"),
                .share(try XCTUnwrap(URL(string: "https://bainluck.com/events/9812"))),
                .openInNewWindow(eventID: 9812),
            ]
        )
        XCTAssertEqual(unpinned.map(\.title), ["Pin", "Copy Link", "Share", "Open in New Window"])
        XCTAssertEqual(unpinned.first?.systemImage, "bookmark")

        let pinned = MacHubAndGridRowAction10878.actions(for: .eventDetail(id: 9812), isPinned: true)
        XCTAssertEqual(pinned.first, .togglePin(isPinned: true, type: "event", id: 9812))
        XCTAssertEqual(pinned.first?.title, "Unpin")
        XCTAssertEqual(pinned.first?.systemImage, "bookmark.slash")
    }

    // MARK: - Rule: Market / Mover (.futuresDetail)

    func testMarketOrMoverOffersCopyLinkAndShareWithOptionalPinAndNeverOpenInNewWindow() throws {
        let unpinned = MacHubAndGridRowAction10878.actions(for: .futuresDetail(id: 7741))
        XCTAssertEqual(
            unpinned,
            [
                .copyLink("https://bainluck.com/futures/7741"),
                .share(try XCTUnwrap(URL(string: "https://bainluck.com/futures/7741"))),
            ]
        )
        XCTAssertEqual(unpinned.map(\.title), ["Copy Link", "Share"])
        XCTAssertFalse(
            unpinned.contains { if case .openInNewWindow = $0 { return true } else { return false } },
            "No WindowGroup exists for a market id — offering Open in New Window on a market would do nothing"
        )

        let withPin = MacHubAndGridRowAction10878.actions(for: .futuresDetail(id: 7741), isPinned: false)
        XCTAssertEqual(
            withPin,
            [
                .togglePin(isPinned: false, type: "future", id: 7741),
                .copyLink("https://bainluck.com/futures/7741"),
                .share(try XCTUnwrap(URL(string: "https://bainluck.com/futures/7741"))),
            ]
        )
        XCTAssertEqual(withPin.map(\.title), ["Pin", "Copy Link", "Share"])

        let pinned = MacHubAndGridRowAction10878.actions(for: .futuresDetail(id: 7741), isPinned: true)
        XCTAssertEqual(pinned.first, .togglePin(isPinned: true, type: "future", id: 7741))
        XCTAssertEqual(pinned.first?.title, "Unpin")
        XCTAssertEqual(pinned.first?.systemImage, "bookmark.slash")
    }

    // MARK: - Plain canonical URLs & unsupported routes / sentinel IDs

    func testLinksAreCanonicalPlainShareURLsWithoutTrackingQuery() {
        for route in [Route.eventDetail(id: 19), .futuresDetail(id: 23)] {
            for action in MacHubAndGridRowAction10878.actions(for: route, isPinned: false) {
                switch action {
                case .togglePin:
                    break
                case .copyLink(let link):
                    XCTAssertEqual(link, route == .eventDetail(id: 19) ? eventShareURL(19) : futuresShareURL(23))
                    XCTAssertFalse(link.contains("utm_"), "\(link) must not append Discover card tracking params")
                case .share(let url):
                    XCTAssertEqual(
                        url.absoluteString,
                        route == .eventDetail(id: 19) ? eventShareURL(19) : futuresShareURL(23)
                    )
                case .openInNewWindow(let id):
                    XCTAssertEqual(id, 19)
                }
            }
        }
    }

    func testEveryOtherRouteAndNonPositiveSentinelIdsGetNoActionsAndNoPinTarget() {
        let unsupported: [Route] = [
            .eventDetail(id: 0),
            .eventDetail(id: -1),
            .futuresDetail(id: 0),
            .futuresDetail(id: -5),
            .eventModels(id: 1),
            .sportCategory(key: "mma_mixed_martial_arts", name: "UFC"),
            .leagueGrid(slug: "nba"),
            .teamDetail(slug: "bos"),
            .tournamentHub(slug: "us-open", name: "US Open"),
            .containerHub(slug: "ai-race", name: "AI Race"),
            .conceptCard(key: "ufc-331", name: "UFC 331"),
            .golfCategory,
            .golfLeaderboard,
            .golfTournament(slug: "masters", name: "The Masters"),
            .futuresList,
            .calibration,
            .dailyChallenge,
            .predictionStats,
            .preferences,
            .about,
            .weather,
            .economics,
            .politics,
            .entertainment,
            .discoverLabeling,
        ]
        for route in unsupported {
            XCTAssertEqual(
                MacHubAndGridRowAction10878.actions(for: route),
                [],
                "\(route) must not attach a context menu"
            )
            XCTAssertEqual(
                MacHubAndGridRowAction10878.actions(for: route, isPinned: true),
                [],
                "\(route) must not attach a context menu even when isPinned is supplied"
            )
            XCTAssertNil(
                MacHubAndGridRowAction10878.pinTarget(for: route),
                "\(route) has no PinManager target"
            )
        }
    }

    // MARK: - Parity with CardContextMenu

    func testLabelsAndSymbolsMatchCardContextMenu() throws {
        let cardMenu = try Self.appSource("Components/CardContextMenu.swift")
        for action in MacHubAndGridRowAction10878.actions(for: .eventDetail(id: 1), isPinned: false) {
            XCTAssertTrue(
                cardMenu.contains("Label(\"\(action.title)\", systemImage: \"\(action.systemImage)\")")
                    || cardMenu.contains("\"\(action.title)\"") && cardMenu.contains("\"\(action.systemImage)\""),
                "CardContextMenu and MacHubAndGridRowAction10878 disagree on \(action.title) / \(action.systemImage)"
            )
        }
        let unpinAction = MacHubAndGridRowAction10878.togglePin(isPinned: true, type: "event", id: 1)
        XCTAssertTrue(cardMenu.contains("\"\(unpinAction.title)\""))
        XCTAssertTrue(cardMenu.contains("\"\(unpinAction.systemImage)\""))
        XCTAssertFalse(
            MacHubAndGridRowAction10878.actions(for: .eventDetail(id: 1), isPinned: false)
                .map(\.title)
                .contains("Copy Probability"),
            "Hub, grid, explore, and fight card rows include settled results and multi-outcome boards — Copy Probability is deliberately omitted"
        )
    }

    // MARK: - Source Wiring: FuturesListView, LeagueGridView, TournamentHubView, ConceptCardView

    func testFuturesListViewMarksMoverCardsAndMarketRows() throws {
        let source = try Self.appSource("Views/FuturesListView.swift")
        let lines = source.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }

        var navLinks: [String] = []
        var menus: [String] = []
        for line in lines {
            if let route = Self.argument(of: "NavigationLink(value: Route.", in: line, closingBefore: ") {") {
                navLinks.append("." + route)
            }
            if let menu = Self.argument(of: ".macHubAndGridRowMenu(", in: line, closingBefore: ", pinManager: macPinManager)") {
                menus.append(menu)
            }
        }

        XCTAssertEqual(
            navLinks,
            [
                ".futuresDetail(id: mover.marketId)",
                ".futuresDetail(id: market.id)",
            ],
            "FuturesListView NavigationLink set changed — verify Mac context menu coverage"
        )
        XCTAssertEqual(
            menus,
            [
                ".futuresDetail(id: mover.marketId)",
                ".futuresDetail(id: market.id)",
            ],
            "FuturesListView must attach .macHubAndGridRowMenu with macPinManager to both Biggest Movers and market rows"
        )
    }

    func testLeagueGridViewMarksLeagueMarketRows() throws {
        let source = try Self.appSource("Views/LeagueGridView.swift")
        let lines = source.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }

        var navLinks: [String] = []
        var menus: [String] = []
        for line in lines {
            if let route = Self.argument(of: "NavigationLink(value: Route.", in: line, closingBefore: ") {") {
                navLinks.append("." + route)
            }
            if let menu = Self.argument(of: ".macHubAndGridRowMenu(", in: line, closingBefore: ", pinManager: macPinManager)") {
                menus.append(menu)
            }
        }

        XCTAssertEqual(navLinks, [".futuresDetail(id: market.id)"])
        XCTAssertEqual(menus, [".futuresDetail(id: market.id)"])
    }

    func testTournamentHubViewMarksLiveUpcomingAndResultMatchLinks() throws {
        let source = try Self.appSource("Views/TournamentHubView.swift")
        let lines = source.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }

        var navLinks: [String] = []
        var menus: [String] = []
        for line in lines {
            if let route = Self.argument(of: "NavigationLink(value: Route.", in: line, closingBefore: ") {") {
                navLinks.append("." + route)
            }
            if let menu = Self.argument(of: ".macHubAndGridRowMenu(", in: line, closingBefore: ", pinManager: pinManager)") {
                menus.append(menu)
            }
        }

        XCTAssertEqual(
            navLinks,
            [
                ".eventDetail(id: eventId)",
                ".eventDetail(id: eventId)",
            ]
        )
        XCTAssertEqual(
            menus,
            [
                ".eventDetail(id: eventId)",
                ".eventDetail(id: eventId)",
            ],
            "Both TournamentHubMatchCard and TournamentHubResultCard must attach .macHubAndGridRowMenu when eventId is non-nil"
        )
        XCTAssertTrue(
            source.contains("TournamentHubSurface(presentation: presentation, pinManager: macPinManager)"),
            "TournamentHubView must forward macPinManager into TournamentHubSurface"
        )
    }

    func testConceptCardViewMarksResolvedBoutLinksAndLeavesUnavailableSportLinkUnmarked() throws {
        let source = try Self.appSource("Views/ConceptCardView.swift")
        let lines = source.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }

        var menus: [String] = []
        for line in lines {
            if let menu = Self.argument(of: ".macHubAndGridRowMenu(", in: line, closingBefore: ", pinManager: macPinManager)") {
                menus.append(menu)
            }
        }

        XCTAssertEqual(
            menus,
            ["route"],
            "ConceptCardView must attach .macHubAndGridRowMenu(route, pinManager: macPinManager) to resolved bout links and leave the unavailable sport fallback link unmarked"
        )
    }

    // MARK: - Platform Isolation & Modifier Safety

    func testModifierIsMacOnlyAndDrawsActionsFromRuleWithoutNavigating() throws {
        let utility = try Self.appSource("Utilities/MacHubAndGridRowActions10878.swift")

        let modifierFn = try XCTUnwrap(
            Self.slice(
                utility,
                from: "func macHubAndGridRowMenu(_ route: Route, pinManager: PinManager? = nil) -> some View {",
                to: "\n    }\n"
            ),
            "macHubAndGridRowMenu signature changed"
        )
        let statements = modifierFn.components(separatedBy: "\n").dropFirst()
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        XCTAssertEqual(
            statements,
            [
                "#if os(macOS)",
                "modifier(MacHubAndGridRowMenu10878(route: route, pinManager: pinManager))",
                "#else",
                "self",
                "#endif",
            ]
        )

        let modifierBody = try XCTUnwrap(
            Self.slice(
                utility,
                from: "private struct MacHubAndGridRowMenu10878: ViewModifier {",
                to: "\n#endif"
            ),
            "MacHubAndGridRowMenu10878 struct missing"
        )
        XCTAssertTrue(modifierBody.contains("MacHubAndGridRowAction10878.actions(for: route, isPinned: isPinned)"))
        XCTAssertTrue(modifierBody.contains("if actions.isEmpty {\n            content\n"))
        XCTAssertTrue(modifierBody.contains("ForEach(actions, id: \\.self)"))
        XCTAssertTrue(modifierBody.contains("pinManager?.togglePin(type: type, id: id)"))
        XCTAssertTrue(modifierBody.contains("copyToClipboard(link)"))
        XCTAssertTrue(modifierBody.contains("ShareLink(item: url)"))
        XCTAssertTrue(modifierBody.contains("openWindow(value: eventID)"))
        for forbidden in ["NavigationLink", "navCoordinator", "selectedTab", "path.append"] {
            XCTAssertFalse(modifierBody.contains(forbidden), "Menu modifier must not touch \(forbidden)")
        }
    }

    // MARK: - Reader-Visible Offscreen Render Verification

    func testOffscreenRenderedHubAndGridMenuPreviewProducesNonEmptyBitmaps() throws {
        let scenarios: [(
            slug: String,
            header: String,
            rowTitle: String,
            rowSubtitle: String,
            rowProb: String,
            route: Route,
            isPinned: Bool?
        )] = [
            (
                "01-futures-list-mover-and-market-menu",
                "FuturesListView · Explore Market Row Right-Click",
                "2026 NBA Champion",
                "Sports · 30 outcomes · Kalshi + Polymarket",
                "Boston Celtics  28%",
                .futuresDetail(id: 7741),
                false
            ),
            (
                "02-league-grid-market-menu",
                "LeagueGridView · Championship Grid Market Right-Click",
                "NBA Eastern Conference Winner",
                "Conference Finals · Pinned Market",
                "Celtics 46% · Knicks 24%",
                .futuresDetail(id: 7788),
                true
            ),
            (
                "03-tournament-hub-match-menu",
                "TournamentHubView · US Open Match Card Right-Click",
                "Men's Singles · Semifinal",
                "Jannik Sinner vs Carlos Alcaraz",
                "54% · 46%",
                .eventDetail(id: 9812),
                false
            ),
            (
                "04-concept-card-bout-menu",
                "ConceptCardView · UFC 331 Main Event Right-Click",
                "MAIN EVENT · 331: Van vs Pantoja",
                "UFC · 5 fights · Pinned Bout",
                "Pantoja 64% · Van 36%",
                .eventDetail(id: 9901),
                true
            ),
        ]

        let snapshotDir = ProcessInfo.processInfo.environment["MAC_HUB_GRID_SNAPSHOT_DIR"]

        for scenario in scenarios {
            let actions = MacHubAndGridRowAction10878.actions(for: scenario.route, isPinned: scenario.isPinned)
            XCTAssertFalse(actions.isEmpty)

            let preview = VStack(alignment: .leading, spacing: 10) {
                Text(scenario.header)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)

                // Simulated Hub / Grid / Explore / Fight Card row with the real .macHubAndGridRowMenu modifier attached
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(scenario.rowTitle)
                            .font(.system(size: 14, weight: .bold))
                            .foregroundStyle(.primary)
                        Text(scenario.rowSubtitle)
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Text(scenario.rowProb)
                        .font(.system(size: 13, weight: .bold, design: .monospaced))
                        .foregroundStyle(.primary)
                }
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .fill(Color.secondary.opacity(0.08))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(Color.accentColor.opacity(0.45), lineWidth: 1)
                )
                .macHubAndGridRowMenu(scenario.route)

                // Rendered representation of the right-click context menu items produced by MacHubAndGridRowAction10878
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Array(actions.enumerated()), id: \.offset) { idx, action in
                        HStack(spacing: 10) {
                            Image(systemName: action.systemImage)
                                .font(.system(size: 13, weight: .medium))
                                .frame(width: 18)
                            Text(action.title)
                                .font(.system(size: 13, weight: .regular))
                            Spacer()
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 7)

                        if idx < actions.count - 1 {
                            Divider()
                        }
                    }
                }
                .background(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .fill(Color.secondary.opacity(0.10))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8, style: .continuous)
                        .strokeBorder(Color.secondary.opacity(0.25), lineWidth: 0.5)
                )
            }
            .padding(14)
            .frame(width: 340)
            .background(Color.white)
            .environment(\.colorScheme, .light)

            let renderer = rendererForMeasurement(preview)
            renderer.scale = 2.0
            let cgImage = try XCTUnwrap(renderer.cgImage, "Expected non-nil CGImage for \(scenario.slug)")
            XCTAssertEqual(cgImage.width, 680)
            XCTAssertGreaterThan(cgImage.height, 260)

            #if canImport(ImageIO)
            if let snapshotDir {
                let dirURL = URL(fileURLWithPath: snapshotDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let fileURL = dirURL.appendingPathComponent("\(scenario.slug).png")
                if let dest = CGImageDestinationCreateWithURL(
                    fileURL as CFURL,
                    UTType.png.identifier as CFString,
                    1,
                    nil
                ) {
                    CGImageDestinationAddImage(dest, cgImage, nil)
                    XCTAssertTrue(CGImageDestinationFinalize(dest))
                }
            }
            #endif
        }
    }

    // MARK: - Helpers

    private static func appSource(_ relativePath: String) throws -> String {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
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
