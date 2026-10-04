import Combine
import Foundation
import XCTest
@testable import Bain_Luck

final class GameContinuationTests: XCTestCase {
    func testCanonicalURLRoundTripsOnlyPositiveExactEventIdentity() throws {
        let canonicalID = 15323927
        let url = try XCTUnwrap(GameContinuation.url(eventID: canonicalID))
        XCTAssertEqual(url.absoluteString, "https://bainluck.com/events/15323927")
        XCTAssertEqual(GameContinuation.eventID(from: url), canonicalID)
        XCTAssertNil(GameContinuation.url(eventID: 0))
        XCTAssertNil(GameContinuation.url(eventID: -1))
        XCTAssertNil(GameContinuation.eventID(from: nil))
        for literal in invalidURLs {
            XCTAssertNil(GameContinuation.eventID(from: try XCTUnwrap(URL(string: literal))), literal)
        }
    }

    @MainActor
    func testConfiguredActivityCarriesOnlyPublicCanonicalIdentity() throws {
        let activity = NSUserActivity(activityType: GameContinuation.activityType)
        activity.userInfo = ["token": "test-only", "score": 4]
        activity.isEligibleForSearch = true
        activity.isEligibleForPublicIndexing = true
        #if os(iOS) || os(watchOS)
        activity.isEligibleForPrediction = true
        #endif
        GameContinuation.configure(activity, eventID: 15323927)
        XCTAssertEqual(activity.webpageURL, GameContinuation.url(eventID: 15323927))
        XCTAssertTrue(activity.userInfo?.isEmpty != false)
        XCTAssertTrue(activity.isEligibleForHandoff)
        XCTAssertFalse(activity.isEligibleForSearch)
        XCTAssertFalse(activity.isEligibleForPublicIndexing)
        #if os(iOS) || os(watchOS)
        XCTAssertFalse(activity.isEligibleForPrediction)
        #endif
        GameContinuation.configure(activity, eventID: 0)
        XCTAssertNil(activity.webpageURL)
        XCTAssertFalse(activity.isEligibleForHandoff)
    }

    @MainActor
    func testReceiverPublishesTheSameCanonicalEventAfterTabTransition() async throws {
        let coordinator = NavigationCoordinator()
        let canonicalID = 15323927
        let route = Route.eventDetail(id: canonicalID)
        let published = expectation(description: "Canonical continuation route published")
        let subscription = coordinator.$pendingRoute
            .first(where: { $0 == route })
            .sink { _ in published.fulfill() }
        defer { subscription.cancel() }
        let activity = NSUserActivity(activityType: GameContinuation.activityType)
        GameContinuation.configure(activity, eventID: canonicalID)
        XCTAssertTrue(coordinator.handleGameContinuation(activity))
        XCTAssertEqual(coordinator.selectedTab, .feed)
        await fulfillment(of: [published], timeout: 2)
        XCTAssertEqual(coordinator.pendingRoute, route)
        XCTAssertEqual(coordinator.consumeRoute(), route)
        XCTAssertNil(coordinator.pendingRoute)
    }

    @MainActor
    func testReceiverRejectsInvalidActivitiesWithoutImmediateOrDelayedNavigation() async throws {
        let coordinator = NavigationCoordinator()
        coordinator.selectedTab = .myStuff
        let notPublished = expectation(description: "Invalid continuation never publishes a route")
        notPublished.isInverted = true
        let subscription = coordinator.$pendingRoute.compactMap { $0 }
            .sink { _ in notPublished.fulfill() }
        defer { subscription.cancel() }

        let wrongType = NSUserActivity(activityType: "com.bainluck.unrelated")
        wrongType.webpageURL = GameContinuation.url(eventID: 15323927)
        XCTAssertFalse(coordinator.handleGameContinuation(wrongType))
        let missingURL = NSUserActivity(activityType: GameContinuation.activityType)
        XCTAssertFalse(coordinator.handleGameContinuation(missingURL))
        // Foundation permits only HTTP(S) webpageURL values; the pure parser also tests custom schemes.
        for literal in invalidURLs where literal.hasPrefix("http") {
            let activity = NSUserActivity(activityType: GameContinuation.activityType)
            activity.webpageURL = try XCTUnwrap(URL(string: literal))
            XCTAssertFalse(coordinator.handleGameContinuation(activity), literal)
        }
        await fulfillment(of: [notPublished], timeout: 0.25)
        XCTAssertEqual(coordinator.selectedTab, .myStuff)
        XCTAssertNil(coordinator.pendingRoute)
        XCTAssertNil(coordinator.pendingSearchQuery)
    }

    private var invalidURLs: [String] {
        [
            "http://bainluck.com/events/15323927",
            "https://www.bainluck.com/events/15323927",
            "https://example.com/events/15323927",
            "bainluck://events/15323927",
            "https://bainluck.com/futures/15323927",
            "https://bainluck.com/events/0",
            "https://bainluck.com/events/-1",
            "https://bainluck.com/events/015323927",
            "https://bainluck.com/events/15323927/",
            "https://bainluck.com/events/15323927/extra",
            "https://bainluck.com/events/15323927?source=watch",
            "https://bainluck.com/events/15323927#score",
            "https://bainluck.com/events/not-an-id",
            "https://bainluck.com/events"
        ]
    }
}
