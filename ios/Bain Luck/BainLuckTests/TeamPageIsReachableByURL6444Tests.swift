import XCTest
@testable import Bain_Luck

/// #6444 — THE TEAM PAGE HAD NO URL.
///
/// `TeamDetailView` has shipped for as long as search could push it, and
/// `NavigationCoordinator.handleURL` had no `team` case — so
/// `bainluck://team/boston-red-sox-mlb` returned false and a team link shared out
/// of the web app (`/sport/<sport>/<league>/team/<slug>`) opened the default tab.
///
/// It is also why this fix arrived without a photograph of the screen it fixes:
/// the LOOK rig drives the app through `-launch_route`, one router, this switch.
/// **A surface with no route cannot be shown to anybody** — not to a reader with
/// a link, and not to Alex in a before/after. That is a launch-week defect in its
/// own right, so it is tested as one rather than as rig plumbing.
@MainActor
final class TeamPageIsReachableByURL6444Tests: XCTestCase {

    private func route(for url: String, file: StaticString = #filePath, line: UInt = #line) async -> Route? {
        let coordinator = NavigationCoordinator()
        let handled = coordinator.handleURL(URL(string: url)!)
        guard handled else { return nil }
        // `navigate(to:tab:)` publishes the route one main-queue hop later, so the
        // tab transition can begin first. Wait for the hop rather than asserting
        // into the gap.
        try? await Task.sleep(nanoseconds: 400_000_000)
        return coordinator.pendingRoute
    }

    func testCustomSchemeOpensTheTeamPage() async {
        let route = await route(for: "bainluck://team/boston-red-sox-mlb")
        XCTAssertEqual(route, .teamDetail(slug: "boston-red-sox-mlb"))
    }

    /// The plural spelling too: the API path is `/api/teams/{slug}`, and a link
    /// built from it is the likeliest near-miss.
    func testPluralSpellingAlsoOpensTheTeamPage() async {
        let route = await route(for: "bainluck://teams/arsenal-epl")
        XCTAssertEqual(route, .teamDetail(slug: "arsenal-epl"))
    }

    /// The web's own URL, which is what a shared link actually looks like.
    func testUniversalLinkFromTheWebTeamPageOpensIt() async {
        let route = await route(for: "https://bainluck.com/sport/baseball/mlb/team/boston-red-sox")
        XCTAssertEqual(route, .teamDetail(slug: "boston-red-sox"))
    }

    /// The slug travels whole. Web resolves it server-side and so do we — a
    /// client-side sport check here would be a second, stricter rule about a
    /// string this app does not own.
    func testSlugIsPassedThroughUnparsed() async {
        let route = await route(for: "https://bainluck.com/sport/football/ncaaf/team/clemson-tigers-ncaaf")
        XCTAssertEqual(route, .teamDetail(slug: "clemson-tigers-ncaaf"))
    }

    func testTabIsSports() {
        let coordinator = NavigationCoordinator()
        XCTAssertTrue(coordinator.handleURL(URL(string: "bainluck://team/boston-red-sox-mlb")!))
        XCTAssertEqual(coordinator.selectedTab, .feed)
    }

    // MARK: - What must still be refused

    /// A bare `bainluck://team` names no team. Returning false hands the URL back
    /// to the caller instead of opening a page about nobody.
    func testBareTeamURLIsRefused() {
        let coordinator = NavigationCoordinator()
        XCTAssertFalse(coordinator.handleURL(URL(string: "bainluck://team")!))
        XCTAssertNil(coordinator.pendingRoute)
    }

    /// `/sport/...` paths that are not team links are refused exactly as they
    /// were before this case existed — the new arm widens one URL, not a family.
    func testOtherSportPathsAreStillRefused() {
        let coordinator = NavigationCoordinator()
        for url in [
            "https://bainluck.com/sport/baseball/mlb",
            "https://bainluck.com/sport/baseball/mlb/team",
            "https://bainluck.com/sport",
        ] {
            XCTAssertFalse(
                coordinator.handleURL(URL(string: url)!),
                "\(url) is not a screen this app has"
            )
        }
        XCTAssertNil(coordinator.pendingRoute)
    }

    /// Another host is not ours, however its path is spelled.
    func testForeignHostIsRefused() {
        let coordinator = NavigationCoordinator()
        XCTAssertFalse(
            coordinator.handleURL(URL(string: "https://example.com/sport/baseball/mlb/team/boston-red-sox")!)
        )
    }
}
