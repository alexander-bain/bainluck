import XCTest
@testable import Bain_Luck

/// #10878 — right-click on a Mac Search result: a game offers Copy Link, Share
/// and Open in New Window, a market offers Copy Link and Share, and every other
/// row offers nothing.
///
/// This target runs on iOS, so no Mac menu can be mounted here, and nothing
/// below claims a right-click reached a row, the pasteboard took the link, the
/// sharing picker opened or a second window appeared. What runs here is the
/// rule each row's menu is built from — route in, items and links out — and
/// three reads of `SearchView` proving every game and market row carries that
/// menu, that it is the Mac's alone, and that it neither navigates nor moves
/// the keyboard pick. The mounted menu (paste, share picker, independent game
/// window, kept query/scroll/pick, VoiceOver, iPhone regression) is acceptance
/// on a real Mac.
@MainActor
final class MacSearchResultActions10878Tests: XCTestCase {

    // MARK: - What each row offers

    /// "dodgers" → Brewers vs Dodgers, event 15330459.
    func testAGameOffersCopyLinkShareAndOpenInNewWindow() {
        XCTAssertEqual(
            MacSearchResultAction10878.actions(for: .eventDetail(id: 15330459)),
            [
                .copyLink("https://bainluck.com/events/15330459"),
                .share(URL(string: "https://bainluck.com/events/15330459")!),
                .openInNewWindow(eventID: 15330459),
            ]
        )
    }

    /// "best picture" → Oscar Winner: Best Picture (6173044) and the Polymarket
    /// nominations market (27988771). A market has no typed window, so no
    /// Open in New Window.
    func testAMarketOffersCopyLinkAndShareOnly() {
        for id in [6173044, 27988771] {
            XCTAssertEqual(
                MacSearchResultAction10878.actions(for: .futuresDetail(id: id)),
                [
                    .copyLink("https://bainluck.com/futures/\(id)"),
                    .share(URL(string: "https://bainluck.com/futures/\(id)")!),
                ]
            )
        }
    }

    /// The links are the app's own share URLs, in the `.plain` style Sports and
    /// My Stuff copy — no tracking query on a link a reader pastes.
    func testTheLinksAreTheSharedPlainURLs() {
        let game = MacSearchResultAction10878.actions(for: .eventDetail(id: 7))
        XCTAssertEqual(game.first, .copyLink(eventShareURL(7, style: .plain)))
        XCTAssertEqual(game.dropFirst().first, .share(URL(string: eventShareURL(7, style: .plain))!))
        let market = MacSearchResultAction10878.actions(for: .futuresDetail(id: 7))
        XCTAssertEqual(market.first, .copyLink(futuresShareURL(7, style: .plain)))
        XCTAssertEqual(market.dropFirst().first, .share(URL(string: futuresShareURL(7, style: .plain))!))
        for action in game + market {
            switch action {
            case .copyLink(let link): XCTAssertFalse(link.contains("?"), link)
            case .share(let url): XCTAssertNil(url.query, url.absoluteString)
            case .openInNewWindow: break
            }
        }
    }

    /// A team, collection, tournament or any other destination has no native
    /// share URL, so its row gets no menu at all.
    func testEveryOtherDestinationGetsNoMenu() {
        let others: [Route] = [
            .teamDetail(slug: "los-angeles-dodgers"),
            .tournamentHub(slug: "us-open", name: "US Open"),
            .containerHub(slug: "mlb-postseason-2026", name: "MLB Postseason"),
            .golfTournament(slug: "masters", name: "Masters"),
            .conceptCard(key: "event:ufc:ufc-310", name: "UFC 310"),
            .sportCategory(key: "baseball", name: "Baseball"),
            .leagueGrid(slug: "mlb"),
            .futuresList,
            .eventModels(id: 15330459),
            .calibration,
        ]
        for route in others {
            XCTAssertEqual(MacSearchResultAction10878.actions(for: route), [], "\(route)")
        }
    }

    /// Same words and symbols as the right-click on Sports and My Stuff.
    func testLabelsAndSymbolsAreTheSharedMenus() throws {
        let items = MacSearchResultAction10878.actions(for: .eventDetail(id: 1))
        XCTAssertEqual(items.map(\.title), ["Copy Link", "Share", "Open in New Window"])
        XCTAssertEqual(items.map(\.systemImage), ["link", "square.and.arrow.up", "macwindow.badge.plus"])
        let shared = try Self.appSource("Components/CardContextMenu.swift")
        for item in items {
            XCTAssertTrue(
                shared.contains("Label(\"\(item.title)\", systemImage: \"\(item.systemImage)\")"),
                "CardContextMenu no longer says \(item.title) with \(item.systemImage)"
            )
        }
    }

    // MARK: - SearchView reads

    /// Every game and market row carries the menu for the route it opens, on
    /// the line after its keyboard mark; no other row carries one.
    func testEveryGameAndMarketRowCarriesItsMenu() throws {
        let source = try Self.appSource("Views/SearchView.swift")
        let results = try XCTUnwrap(
            Self.slice(source, from: "private func searchResults(", to: "// MARK: - Tournament Row"),
            "searchResults moved"
        )
        let lines = results.components(separatedBy: "\n").map { $0.trimmingCharacters(in: .whitespaces) }
        var menus: [String] = []
        for (index, text) in lines.enumerated() {
            if let route = Self.argument(of: ".macKeyboardRow(", in: text, closingBefore: ", in: keyboardSelection)") {
                let next = index + 1 < lines.count ? lines[index + 1] : ""
                let menu = Self.argument(of: ".macResultMenu(", in: next, closingBefore: ")")
                if route.hasPrefix(".eventDetail(") || route.hasPrefix(".futuresDetail(") {
                    XCTAssertEqual(menu, route, "the \(route) row has no right-click menu")
                } else {
                    XCTAssertNil(menu, "the \(route) row offers a menu with no share URL behind it")
                }
            }
            if let menu = Self.argument(of: ".macResultMenu(", in: text, closingBefore: ")") {
                menus.append(menu)
                let previous = index > 0 ? lines[index - 1] : ""
                XCTAssertEqual(
                    Self.argument(of: ".macKeyboardRow(", in: previous, closingBefore: ", in: keyboardSelection)"),
                    menu,
                    "a menu must sit on the row its keyboard mark names"
                )
            }
        }
        XCTAssertEqual(menus.count, 7, "two game sites, five market sites — mark any new one")
        XCTAssertEqual(menus.filter { $0.hasPrefix(".eventDetail(") }.count, 2)
    }

    /// The menu is the Mac's alone: the modifier hands iPhone and iPad their row
    /// back, and the only context menu and window opener in the file sit inside
    /// `#if os(macOS)`.
    func testTheMenuIsMacOnly() throws {
        let source = try Self.appSource("Views/SearchView.swift")
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
                XCTAssertEqual(platform.last, "#if os(macOS)", "\(text) runs outside the Mac")
            }
            if text.contains("openWindow") {
                windowOpeners += 1
                XCTAssertTrue(platform.contains("#if os(macOS)"), "\(text) runs outside the Mac")
            }
        }
        XCTAssertEqual(contextMenus, 1)
        XCTAssertGreaterThan(windowOpeners, 0)
        let modifier = try XCTUnwrap(
            Self.slice(source, from: "func macResultMenu(_ route: Route) -> some View {", to: "\n    }\n"),
            "macResultMenu moved"
        )
        let statements = modifier.components(separatedBy: "\n").dropFirst()
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        XCTAssertEqual(
            statements,
            ["#if os(macOS)", "modifier(MacSearchResultMenu(route: route))", "#else", "self", "#endif"]
        )
    }

    /// The menu draws every item from `actions(for:)` and does nothing but copy,
    /// share or open a window: it never navigates this window and never touches
    /// the keyboard pick.
    func testTheMenuDrawsTheRuleAndNeverNavigates() throws {
        let source = try Self.appSource("Views/SearchView.swift")
        let menu = try XCTUnwrap(
            Self.slice(source, from: "private struct MacSearchResultMenu: ViewModifier {", to: "\n#endif"),
            "MacSearchResultMenu moved"
        )
        XCTAssertTrue(menu.contains("let actions = MacSearchResultAction10878.actions(for: route)"))
        XCTAssertTrue(menu.contains("if actions.isEmpty {\n            content\n"), "no actions must mean no menu")
        XCTAssertTrue(menu.contains("ForEach(actions, id: \\.self)"))
        XCTAssertTrue(menu.contains("copyToClipboard(link)"))
        XCTAssertTrue(menu.contains("ShareLink(item: url)"))
        XCTAssertTrue(menu.contains("openWindow(value: eventID)"))
        for forbidden in ["keyboardSelection", "path", "navCoordinator", "NavigationLink", "eventShareURL", "futuresShareURL"] {
            XCTAssertFalse(menu.contains(forbidden), "the menu reaches for \(forbidden)")
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
