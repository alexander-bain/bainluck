import Combine
import Foundation
import XCTest
@testable import Bain_Luck

final class StoryContinuationTests: XCTestCase {
    func testCanonicalDestinationsPreserveEntityKindAndIdentity() throws {
        for destination in [StoryContinuationDestination.event(15323927), .futures(4935)] {
            let url = try XCTUnwrap(StoryContinuation.url(for: destination))
            XCTAssertEqual(StoryContinuation.destination(from: url), destination)
        }
        XCTAssertEqual(StoryContinuation.url(for: .event(4935))?.absoluteString, "https://bainluck.com/events/4935")
        XCTAssertEqual(StoryContinuation.url(for: .futures(4935))?.absoluteString, "https://bainluck.com/futures/4935")
        for destination in [StoryContinuationDestination.event(0), .event(-1), .futures(0), .futures(-1)] {
            XCTAssertNil(StoryContinuation.url(for: destination))
        }
        XCTAssertNil(StoryContinuation.destination(from: nil))
        for literal in invalidURLs {
            XCTAssertNil(StoryContinuation.destination(from: try XCTUnwrap(URL(string: literal))), literal)
        }
    }

    @MainActor
    func testActivityCarriesOnlyCanonicalPublicIdentityAndClearsInvalidDestination() throws {
        let activity = NSUserActivity(activityType: StoryContinuation.activityType)
        activity.userInfo = ["token": "test-only", "probability": 0.64]
        activity.isEligibleForSearch = true
        activity.isEligibleForPublicIndexing = true
        #if os(iOS) || os(watchOS)
        activity.isEligibleForPrediction = true
        #endif
        StoryContinuation.configure(activity, destination: .futures(4935))
        XCTAssertEqual(activity.webpageURL?.absoluteString, "https://bainluck.com/futures/4935")
        XCTAssertTrue(activity.userInfo?.isEmpty != false)
        XCTAssertTrue(activity.isEligibleForHandoff)
        XCTAssertFalse(activity.isEligibleForSearch)
        XCTAssertFalse(activity.isEligibleForPublicIndexing)
        #if os(iOS) || os(watchOS)
        XCTAssertFalse(activity.isEligibleForPrediction)
        #endif
        StoryContinuation.configure(activity, destination: .futures(0))
        XCTAssertNil(activity.webpageURL)
        XCTAssertFalse(activity.isEligibleForHandoff)

        let wrongType = NSUserActivity(activityType: GameContinuation.activityType)
        StoryContinuation.configure(wrongType, destination: .futures(4935))
        XCTAssertFalse(wrongType.isEligibleForHandoff)
    }

    @MainActor
    func testReceiverPublishesExactEventAndFuturesRoutesAfterTabTransition() async throws {
        let cases: [(StoryContinuationDestination, Route)] = [
            (.event(15323927), .eventDetail(id: 15323927)),
            (.futures(4935), .futuresDetail(id: 4935))
        ]
        for (destination, route) in cases {
            let coordinator = NavigationCoordinator()
            coordinator.selectedTab = .myStuff
            let published = expectation(description: "Exact story route published: \(destination)")
            let subscription = coordinator.$pendingRoute.first(where: { $0 == route })
                .sink { _ in published.fulfill() }
            defer { subscription.cancel() }
            let activity = NSUserActivity(activityType: StoryContinuation.activityType)
            StoryContinuation.configure(activity, destination: destination)
            XCTAssertTrue(coordinator.handleStoryContinuation(activity))
            XCTAssertEqual(coordinator.selectedTab, .feed)
            await fulfillment(of: [published], timeout: 2)
            XCTAssertEqual(coordinator.consumeRoute(), route)
            XCTAssertNil(coordinator.pendingRoute)
        }
    }

    @MainActor
    func testInvalidActivitiesNeverNavigateAndLegacyGameStillRoutes() async throws {
        let coordinator = NavigationCoordinator()
        coordinator.selectedTab = .myStuff
        let noRoute = expectation(description: "Invalid story activity never publishes a route")
        noRoute.isInverted = true
        let subscription = coordinator.$pendingRoute.compactMap { $0 }
            .sink { _ in noRoute.fulfill() }
        let wrongType = NSUserActivity(activityType: GameContinuation.activityType)
        wrongType.webpageURL = StoryContinuation.url(for: .futures(4935))
        XCTAssertFalse(coordinator.handleStoryContinuation(wrongType))
        XCTAssertFalse(coordinator.handleStoryContinuation(NSUserActivity(activityType: StoryContinuation.activityType)))
        for literal in invalidURLs where literal.hasPrefix("http") {
            let activity = NSUserActivity(activityType: StoryContinuation.activityType)
            activity.webpageURL = try XCTUnwrap(URL(string: literal))
            XCTAssertFalse(coordinator.handleStoryContinuation(activity), literal)
        }
        await fulfillment(of: [noRoute], timeout: 0.25)
        subscription.cancel()
        XCTAssertEqual(coordinator.selectedTab, .myStuff)
        XCTAssertNil(coordinator.pendingRoute)
        XCTAssertNil(coordinator.pendingSearchQuery)

        let legacyRoute = Route.eventDetail(id: 15323927)
        let legacyPublished = expectation(description: "Legacy game route preserved")
        let legacySubscription = coordinator.$pendingRoute.first(where: { $0 == legacyRoute })
            .sink { _ in legacyPublished.fulfill() }
        defer { legacySubscription.cancel() }
        let legacy = NSUserActivity(activityType: GameContinuation.activityType)
        GameContinuation.configure(legacy, eventID: 15323927)
        XCTAssertTrue(coordinator.handleGameContinuation(legacy))
        await fulfillment(of: [legacyPublished], timeout: 2)
        XCTAssertEqual(coordinator.consumeRoute(), legacyRoute)
    }

    private var invalidURLs: [String] {
        [
            "http://bainluck.com/futures/4935",
            "https://www.bainluck.com/futures/4935",
            "https://example.com/futures/4935",
            "bainluck://futures/4935",
            "https://bainluck.com/futures/0",
            "https://bainluck.com/futures/-1",
            "https://bainluck.com/futures/04935",
            "https://bainluck.com/futures/4935/",
            "https://bainluck.com/futures/4935/extra",
            "https://bainluck.com/futures/4935?source=watch",
            "https://bainluck.com/futures/4935#outcome",
            "https://bainluck.com/futures/not-an-id",
            "https://bainluck.com/futures",
            "https://bainluck.com/events/0",
            "https://bainluck.com/events/015323927",
            "https://bainluck.com/events/15323927?source=watch",
            "https://bainluck.com/story/4935"
        ]
    }
}
