import Combine
import XCTest
@testable import Bain_Luck

final class ContainerHubNavigationTests: XCTestCase {
    /// The real router deliberately publishes after its tab transition. Observe
    /// that publication before asserting, rather than guessing a sleep duration.
    @MainActor
    private func assertPublishes(_ route: Route, from coordinator: NavigationCoordinator, opening url: URL) async {
        let published = expectation(description: "Route published: \(route)")
        let subscription = coordinator.$pendingRoute
            .first(where: { $0 == route })
            .sink { _ in published.fulfill() }
        defer { subscription.cancel() }
        XCTAssertTrue(coordinator.handleURL(url))
        await fulfillment(of: [published], timeout: 2)
        XCTAssertEqual(coordinator.pendingRoute, route)
    }

    @MainActor
    func testNFLNativeLinkOpensHubOnTheReceivingBrowseTab() async throws {
        let coordinator = NavigationCoordinator()
        let url = try XCTUnwrap(URL(string: "bainluck://containers/nfl-2026-week-5?name=NFL%20Week%205"))
        await assertPublishes(.containerHub(slug: "nfl-2026-week-5", name: "NFL Week 5"), from: coordinator, opening: url)
        XCTAssertEqual(coordinator.selectedTab, .leagues)
    }

    @MainActor
    func testMLBNativeLinkUsesRealSlugWithoutInferringMembership() async throws {
        let coordinator = NavigationCoordinator()
        let url = try XCTUnwrap(URL(string: "bainluck://containers/mlb-2026-postseason"))
        await assertPublishes(.containerHub(slug: "mlb-2026-postseason", name: "Collection"), from: coordinator, opening: url)
    }

    @MainActor
    func testNoNonexistentWebHubPageIsClaimed() async throws {
        let coordinator = NavigationCoordinator()
        let notPublished = expectation(description: "Unsupported web URL never publishes a route")
        notPublished.isInverted = true
        let subscription = coordinator.$pendingRoute.compactMap { $0 }.sink { _ in notPublished.fulfill() }
        defer { subscription.cancel() }
        XCTAssertFalse(coordinator.handleURL(try XCTUnwrap(URL(string: "https://bainluck.com/containers/nfl-2026-week-5"))))
        // Also covers the router's delayed path, so an accidental deferred push
        // cannot make this negative assertion pass before publication occurs.
        await fulfillment(of: [notPublished], timeout: 0.25)
        XCTAssertNil(coordinator.pendingRoute)
    }

    @MainActor
    func testMemberDestinationsKeepTheExistingEventAndFuturesRoutes() async throws {
        let coordinator = NavigationCoordinator()
        await assertPublishes(.eventDetail(id: 501), from: coordinator, opening: try XCTUnwrap(URL(string: "bainluck://events/501")))
        await assertPublishes(.futuresDetail(id: 9103), from: coordinator, opening: try XCTUnwrap(URL(string: "bainluck://futures/9103")))
    }
}
