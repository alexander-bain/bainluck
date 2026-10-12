import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10878 — the Mac main window.
///
/// `MainTabView` used to pick its root from the size class alone, so a Mac window
/// got the phone tab bar or the iPad split depending on what the environment
/// reported. It now asks `MacMainWindow10878.root`, which gives the Mac its own
/// sidebar window and leaves iPhone and iPad on exactly the rule they had.
///
/// This target runs on iOS, so the macOS view itself cannot be mounted here.
/// What runs here is every rule that view is built from — the root choice, the
/// sidebar's places, selection against the real `NavigationCoordinator`, and the
/// window/column sizes — plus one read of `MainTabView` proving the shipping
/// body routes through that rule. Mac renders, keyboard/VoiceOver and the
/// second-window check are separate acceptance on a real Mac.
///
/// Recorded window sizes (sidebar at its ideal 220pt):
/// - narrow 800 × 600 (minimum): detail 580pt; with the widest sidebar 520pt
/// - normal 1200 × 800 (the app's default): detail 980pt, uncapped
/// - wide 1680 × 1000: detail 1460pt, centred column capped at 1100pt
@MainActor
final class MacMainWindow10878Tests: XCTestCase {

    // MARK: - Root choice

    func testPhoneAndIPadKeepTheirSizeClassRule() {
        XCTAssertEqual(MacMainWindow10878.root(isMac: false, sizeClass: .regular), .iPadSplit)
        XCTAssertEqual(MacMainWindow10878.root(isMac: false, sizeClass: .compact), .phoneTabs)
        XCTAssertEqual(MacMainWindow10878.root(isMac: false, sizeClass: nil), .phoneTabs)
    }

    func testTheMacGetsItsOwnWindowWhateverSizeClassItReports() {
        for sizeClass: UserInterfaceSizeClass? in [.regular, .compact, nil] {
            XCTAssertEqual(MacMainWindow10878.root(isMac: true, sizeClass: sizeClass), .macWindow)
        }
    }

    /// The iOS app is never routed to the Mac window: on this host the rule's
    /// platform input is false, so the two assertions above are the whole
    /// iPhone/iPad behaviour.
    func testThisIOSHostIsNotTreatedAsAMac() {
        XCTAssertFalse(MacMainWindow10878.runsOnMac)
    }

    /// The runtime checks above only protect the app if `MainTabView` asks the
    /// rule. Its body must route through it, mount the Mac window on the Mac
    /// arm, and keep both existing layouts on theirs.
    func testMainTabViewRoutesThroughTheRule() throws {
        let source = try Self.appSource("Views/MainTabView.swift")
        let body = try XCTUnwrap(Self.slice(source, from: "var body: some View {", to: "// MARK: - iPhone"))

        XCTAssertTrue(body.contains(
            "switch MacMainWindow10878.root(isMac: MacMainWindow10878.runsOnMac, sizeClass: sizeClass)"
        ), "MainTabView no longer chooses its root through MacMainWindow10878.root")
        let macArm = try XCTUnwrap(Self.slice(body, from: "case .macWindow:", to: "case .iPadSplit:"))
        XCTAssertTrue(macArm.contains("MacMainWindowView()"), "the Mac arm does not mount the Mac window")
        XCTAssertTrue(body.contains("case .iPadSplit:\n            iPadLayout"))
        XCTAssertTrue(body.contains("case .phoneTabs:\n            iPhoneLayout"))
        // The old direct size-class branch is gone, so nothing bypasses the rule.
        XCTAssertFalse(body.contains("if sizeClass == .regular"))
    }

    // MARK: - Sidebar

    func testTheSidebarHasThePhonesFivePlacesInOrder() {
        XCTAssertEqual(
            MacMainWindow10878.destinations.map(\.tab),
            [.discover, .feed, .leagues, .search, .myStuff]
        )
        XCTAssertEqual(
            MacMainWindow10878.destinations.map(\.title),
            ["Discover", "Sports", "Browse", "Search", "My Stuff"]
        )
        XCTAssertEqual(MacMainWindow10878.quickLinks.map(\.tab), [.preferences, .calibration])
        XCTAssertEqual(MacMainWindow10878.quickLinks.map(\.title), ["Preferences", CalibrationView.readerTitle])
    }

    /// #10877: no sidebar label calls content a "question".
    func testNoSidebarLabelSaysQuestion() {
        for item in MacMainWindow10878.destinations + MacMainWindow10878.quickLinks {
            XCTAssertFalse(item.title.lowercased().contains("question"), item.title)
        }
    }

    /// Every tab the app has is either a sidebar place or a declared
    /// detail-only destination — a new `AppTab` fails here until someone
    /// decides where the Mac shows it.
    func testEveryTabIsPlacedOrDeclaredDetailOnly() {
        let all = Set((0..<64).compactMap(AppTab.init(rawValue:)))
        XCTAssertEqual(all.count, 12, "AppTab gained or lost a case; place it in the Mac sidebar or detailOnlyTabs")

        let sidebar = (MacMainWindow10878.destinations + MacMainWindow10878.quickLinks).map(\.tab)
        XCTAssertEqual(Set(sidebar).count, sidebar.count, "a tab appears twice in the sidebar")
        XCTAssertTrue(Set(sidebar).isDisjoint(with: MacMainWindow10878.detailOnlyTabs))
        XCTAssertEqual(Set(sidebar).union(MacMainWindow10878.detailOnlyTabs), all)
    }

    /// Every supported link lands on a sidebar place, so the Mac sidebar always
    /// highlights where the link took the reader.
    func testEveryDeepLinkLandsOnAPlaceTheSidebarHighlights() throws {
        let links = [
            "bainluck://events/15327331", "bainluck://events", "bainluck://futures/9413479",
            "bainluck://futures", "bainluck://search?q=red%20sox", "bainluck://tournaments/us-open",
            "bainluck://golf/the-masters", "bainluck://playoffs/wnba", "bainluck://team/boston-red-sox-mlb",
            "bainluck://my-stuff", "bainluck://preferences", "bainluck://weather",
            "bainluck://calibration", "bainluck://about", "https://bainluck.com/events/15327331",
        ]
        let places = Set(MacMainWindow10878.destinations.map(\.tab))
        for link in links {
            let coordinator = NavigationCoordinator()
            coordinator.selectedTab = .myStuff
            XCTAssertTrue(coordinator.handleURL(try XCTUnwrap(URL(string: link))), "\(link) is not routed")
            XCTAssertTrue(places.contains(coordinator.selectedTab), "\(link) selected \(coordinator.selectedTab)")
        }
    }

    func testSelectingASidebarRowMovesTheWindow() async {
        let coordinator = NavigationCoordinator()
        coordinator.selectedTab = .discover

        MacMainWindow10878.applySelection(.search, to: coordinator)
        await Self.drainMainQueue()
        XCTAssertEqual(coordinator.selectedTab, .search)

        MacMainWindow10878.applySelection(.calibration, to: coordinator)
        await Self.drainMainQueue()
        XCTAssertEqual(coordinator.selectedTab, .calibration)
    }

    /// Clicking empty sidebar space deselects the list; the reader stays put.
    func testDeselectingKeepsTheReaderWhereTheyAre() async {
        let coordinator = NavigationCoordinator()
        coordinator.selectedTab = .myStuff

        MacMainWindow10878.applySelection(nil, to: coordinator)
        await Self.drainMainQueue()
        XCTAssertEqual(coordinator.selectedTab, .myStuff)
    }

    func testTheLiveBadgeUsesThePhonesWords() throws {
        XCTAssertNil(MacMainWindow10878.liveBadge(count: 0))
        XCTAssertNil(MacMainWindow10878.liveBadge(count: -1))
        XCTAssertEqual(MacMainWindow10878.liveBadge(count: 3), "3 live")
        // The phone tab bar's own string, so the two cannot drift.
        let tabView = try Self.appSource("Views/MainTabView.swift")
        XCTAssertTrue(tabView.contains("\"\\(navCoordinator.liveGameCount) live\""))
    }

    // MARK: - Window and column sizes

    func testSidebarWidthsAreOrdered() {
        XCTAssertLessThanOrEqual(MacMainWindow10878.sidebarMinWidth, MacMainWindow10878.sidebarIdealWidth)
        XCTAssertLessThanOrEqual(MacMainWindow10878.sidebarIdealWidth, MacMainWindow10878.sidebarMaxWidth)
    }

    /// At the narrowest window with the widest sidebar, the detail column is
    /// still a width the iPad's wide layouts already serve — the window stops
    /// shrinking before text has to.
    func testTheNarrowestWindowStillFitsTheWideLayouts() {
        let detail = MacMainWindow10878.minimumWindowSize.width - MacMainWindow10878.sidebarMaxWidth
        XCTAssertGreaterThanOrEqual(detail, MacMainWindow10878.narrowestRegularDetailWidth)
    }

    /// A normal laptop window is untouched by the cap; a wide desktop window
    /// gets a centred column; Discover's own 800pt Mac cap is never squeezed.
    func testTheReadableCapOnlyBitesOnWideWindows() {
        let cap = MacMainWindow10878.readableContentWidth
        let ideal = MacMainWindow10878.sidebarIdealWidth
        XCTAssertLessThanOrEqual(1200 - ideal, cap, "a normal 1200pt window would be capped")
        XCTAssertGreaterThan(1680 - ideal, cap, "a wide 1680pt window would stretch edge to edge")
        XCTAssertGreaterThanOrEqual(cap, 800, "the column would squeeze Discover's own Mac width")
    }

    /// The app opens its main window at 1200 × 800; that must not be smaller
    /// than the minimum this window declares.
    func testTheDefaultWindowIsAtLeastTheMinimum() throws {
        let app = try Self.appSource("Bain_LuckApp.swift")
        XCTAssertTrue(app.contains(".defaultSize(width: 1200, height: 800)"), "the main window's default size moved")
        XCTAssertLessThanOrEqual(MacMainWindow10878.minimumWindowSize.width, 1200)
        XCTAssertLessThanOrEqual(MacMainWindow10878.minimumWindowSize.height, 800)
    }

    func testTheDetailUsesTheWideLayoutFamily() {
        XCTAssertEqual(MacMainWindow10878.detailSizeClass, .regular)
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

    /// `applySelection` defers its write with `DispatchQueue.main.async`; a
    /// block enqueued after it runs after it.
    private static func drainMainQueue() async {
        await withCheckedContinuation { continuation in
            DispatchQueue.main.async { continuation.resume() }
        }
    }
}
