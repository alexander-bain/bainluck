import XCTest
@testable import Bain_Luck

final class ContainerHubNavigationTests: XCTestCase {
    @MainActor
    func testNFLNativeLinkOpensHubOnTheReceivingBrowseTab() throws {
        let coordinator = NavigationCoordinator()
        let url = try XCTUnwrap(URL(string: "bainluck://containers/nfl-2026-week-5?name=NFL%20Week%205"))
        XCTAssertTrue(coordinator.handleURL(url))
        XCTAssertEqual(coordinator.selectedTab, .leagues)
        XCTAssertEqual(coordinator.pendingRoute, .containerHub(slug: "nfl-2026-week-5", name: "NFL Week 5"))
    }

    @MainActor
    func testMLBNativeLinkUsesRealSlugWithoutInferringMembership() throws {
        let coordinator = NavigationCoordinator()
        XCTAssertTrue(coordinator.handleURL(try XCTUnwrap(URL(string: "bainluck://containers/mlb-2026-postseason"))))
        XCTAssertEqual(coordinator.pendingRoute, .containerHub(slug: "mlb-2026-postseason", name: "Collection"))
    }

    @MainActor
    func testNoNonexistentWebHubPageIsClaimed() throws {
        let coordinator = NavigationCoordinator()
        XCTAssertFalse(coordinator.handleURL(try XCTUnwrap(URL(string: "https://bainluck.com/containers/nfl-2026-week-5"))))
        XCTAssertNil(coordinator.pendingRoute)
    }

    @MainActor
    func testMemberDestinationsKeepTheExistingEventAndFuturesRoutes() throws {
        let coordinator = NavigationCoordinator()
        XCTAssertTrue(coordinator.handleURL(try XCTUnwrap(URL(string: "bainluck://events/501"))))
        XCTAssertEqual(coordinator.pendingRoute, .eventDetail(id: 501))
        XCTAssertTrue(coordinator.handleURL(try XCTUnwrap(URL(string: "bainluck://futures/9103"))))
        XCTAssertEqual(coordinator.pendingRoute, .futuresDetail(id: 9103))
    }
}
