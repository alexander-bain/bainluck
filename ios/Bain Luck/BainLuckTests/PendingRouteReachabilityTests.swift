import XCTest
@testable import Bain_Luck

/// #2998 — `navigate(to:tab:)` selects a tab and then publishes `pendingRoute`,
/// but only the views that OBSERVE `pendingRoute` ever consume it. Browse did not,
/// so every deep link routed to `.leagues` switched to Browse and dropped its
/// route: `bainluck://playoffs/<slug>` and `bainluck://calibration` both landed on
/// the Browse index with no error and no spinner.
///
/// The per-view push is not reachable from a unit test — SwiftUI's `onChange` needs
/// a render host. What IS reachable is the pairing that the defect broke: a tab
/// that can be navigated TO must be a tab that can RECEIVE. This file reads the
/// shipping sources and asserts that, so the next tab wired up with a destination
/// it cannot reach fails here instead of in someone's hands.
final class PendingRouteReachabilityTests: XCTestCase {

    /// Every app source file, walked from this test's own location so the census
    /// reads the shipping tree rather than a copy that can drift.
    private func appSources() throws -> [(path: String, text: String)] {
        let here = URL(fileURLWithPath: #filePath)
        let appRoot = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")

        guard let walker = FileManager.default.enumerator(
            at: appRoot,
            includingPropertiesForKeys: nil
        ) else {
            return []
        }

        var found: [(String, String)] = []
        for case let url as URL in walker where url.pathExtension == "swift" {
            let text = try String(contentsOf: url, encoding: .utf8)
            found.append((url.lastPathComponent, text))
        }
        return found
    }

    /// Tab names appearing as `tab: .<name>` in `NavigationCoordinator.swift` —
    /// every tab a deep link can be sent to with a route attached.
    private func navigatedTabs() throws -> Set<String> {
        guard let coordinator = try appSources().first(where: { $0.path == "NavigationCoordinator.swift" }) else {
            XCTFail("NavigationCoordinator.swift not found — the census is not running")
            return []
        }
        return Set(matches(of: #"tab:\s*\.([A-Za-z]+)"#, in: coordinator.text))
    }

    /// Tab names a view actually consumes a route for: a file that calls
    /// `consumeRoute()` and guards it on `selectedTab == .<name>`.
    ///
    /// Keyed on `consumeRoute()` and not on the `onChange` alone, because
    /// `SearchView` observes `pendingRoute` and deliberately does nothing with it —
    /// observing without consuming is not receiving.
    private func receivingTabs() throws -> Set<String> {
        var tabs: Set<String> = []
        for source in try appSources() where source.text.contains("consumeRoute()") {
            tabs.formUnion(matches(of: #"selectedTab\s*==\s*\.([A-Za-z]+)"#, in: source.text))
        }
        return tabs
    }

    private func matches(of pattern: String, in text: String) -> [String] {
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return regex.matches(in: text, range: range).compactMap { match in
            guard let captured = Range(match.range(at: 1), in: text) else { return nil }
            return String(text[captured])
        }
    }

    // MARK: - The census must be running

    func testTheSourceWalkReachesTheShippingTree() throws {
        // A census whose pass and fail look identical is not a check: if the walk
        // finds nothing, the assertion below passes vacuously forever.
        let sources = try appSources()
        XCTAssertGreaterThan(sources.count, 100, "the source walk found almost nothing")
        XCTAssertTrue(sources.contains { $0.path == "NavigationCoordinator.swift" })
        XCTAssertTrue(sources.contains { $0.path == "LeaguesView.swift" })
    }

    func testTheTwoSetsAreBothNonEmpty() throws {
        // Either regex silently matching nothing would make the real assertion
        // trivially true, in the direction that hides the defect.
        XCTAssertFalse(try navigatedTabs().isEmpty, "no `tab: .x` call sites found — the pattern has rotted")
        XCTAssertFalse(try receivingTabs().isEmpty, "no route-consuming views found — the pattern has rotted")
    }

    // MARK: - The invariant

    func testEveryTabADeepLinkTargetsCanReceiveTheRoute() throws {
        let navigated = try navigatedTabs()
        let receiving = try receivingTabs()
        let unreachable = navigated.subtracting(receiving).sorted()

        XCTAssertTrue(
            unreachable.isEmpty,
            """
            `navigate(to:tab:)` sends a route to a tab whose view never consumes it \
            (#2998). The tab switches, the route sits unread in `pendingRoute`, and \
            the person lands on that tab's index with no error. Give the tab's view \
            the observer that Feed, Browse and My Stuff have:

                .onChange(of: navCoordinator.pendingRoute) { _, _ in
                    if navCoordinator.selectedTab == .<tab>,
                       let route = navCoordinator.consumeRoute() {
                        path.append(route)
                    }
                }

            Tabs that can be navigated to but cannot receive: \(unreachable.joined(separator: ", "))
            """
        )
    }

    func testBrowseIsAmongTheReceivingTabs() throws {
        // The specific regression. `.leagues` is what #2998 was about, and it is
        // the tab `playoffs` and `calibration` both target.
        XCTAssertTrue(
            try receivingTabs().contains("leagues"),
            "LeaguesView must consume pendingRoute — this is #2998 itself"
        )
    }

    func testTheTabsADeepLinkTargetsStillIncludeBrowse() throws {
        // Guards the guard from the other side: if `playoffs` and `calibration`
        // stopped targeting `.leagues`, the test above would keep passing while
        // proving nothing about a live route.
        XCTAssertTrue(
            try navigatedTabs().contains("leagues"),
            "no deep link routes to Browse any more — re-point this guard or delete it"
        )
    }
}
