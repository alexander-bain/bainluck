import Combine
import Foundation
import XCTest
@testable import Bain_Luck

/// Model routing guards only. Mounted StateObject lifetime, active-window
/// focus, screenshots, and real Mac commands still require Native runtime proof.
final class MacSceneCommands10878Tests: XCTestCase {
    @MainActor
    func testNewScenesOwnIndependentCoordinatorsAndInitialTabs() {
        let main = MacSceneCommands10878.makeNavigation()
        let anotherMain = MacSceneCommands10878.makeNavigation()
        let game = MacSceneCommands10878.makeNavigation(initialTab: .feed)
        XCTAssertFalse(main === anotherMain)
        XCTAssertFalse(main === game)
        XCTAssertEqual(main.selectedTab, .discover)
        XCTAssertEqual(anotherMain.selectedTab, .discover)
        XCTAssertEqual(game.selectedTab, .feed)

        main.liveGameCount = 3
        main.liveGameTitle = "3 live games"
        XCTAssertEqual(game.liveGameCount, 0)
        XCTAssertEqual(game.liveGameTitle, "Bain Luck")
    }

    @MainActor
    func testBrowseCommandChangesOnlyItsEligibleTargetAndKeepsRouteContext() {
        let first = MacSceneCommands10878.makeNavigation()
        let second = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        first.pendingSearchQuery = "Oscars"
        first.pendingRoute = .eventDetail(id: 123)
        second.pendingSearchQuery = "AI"
        second.pendingRoute = .futuresDetail(id: 456)

        XCTAssertTrue(MacSceneCommands10878.selectTab(.search, target: first, permitsBrowsing: true))
        XCTAssertEqual(first.selectedTab, .search)
        XCTAssertEqual(first.pendingSearchQuery, "Oscars")
        XCTAssertEqual(first.pendingRoute, .eventDetail(id: 123))
        XCTAssertEqual(second.selectedTab, .myStuff)
        XCTAssertEqual(second.pendingSearchQuery, "AI")
        XCTAssertEqual(second.pendingRoute, .futuresDetail(id: 456))
    }

    @MainActor
    func testMissingAndIneligibleTargetsNeverRedirectOtherScenes() {
        let main = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        let game = MacSceneCommands10878.makeNavigation(initialTab: .feed)
        game.pendingRoute = .eventDetail(id: 123)
        XCTAssertFalse(MacSceneCommands10878.selectTab(.search, target: nil, permitsBrowsing: true))
        XCTAssertFalse(MacSceneCommands10878.selectTab(.discover, target: game, permitsBrowsing: false))
        XCTAssertFalse(MacSceneCommands10878.selectTab(.search, target: main, permitsBrowsing: false))
        XCTAssertEqual(main.selectedTab, .myStuff)
        XCTAssertEqual(game.selectedTab, .feed)
        XCTAssertEqual(game.pendingRoute, .eventDetail(id: 123))
    }

    /// #4940: cold Command-K. Arriving at Search from another tab is not by
    /// itself a focus ask, so Quick Search asks explicitly — only when its
    /// selection succeeded, and only on the window it selected.
    @MainActor
    func testQuickSearchAsksForFocusOnlyOnItsEligibleTarget() {
        let main = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        let other = MacSceneCommands10878.makeNavigation(initialTab: .feed)

        XCTAssertFalse(MacSceneCommands10878.quickSearch(target: nil, permitsBrowsing: true))
        XCTAssertFalse(MacSceneCommands10878.quickSearch(target: main, permitsBrowsing: false))
        XCTAssertEqual(main.selectedTab, .myStuff)
        XCTAssertFalse(main.consumeSearchFocusRequest())
        XCTAssertFalse(other.consumeSearchFocusRequest())

        // A plain arrival is no ask; Quick Search from the same tab is one.
        XCTAssertTrue(MacSceneCommands10878.selectTab(.search, target: other, permitsBrowsing: true))
        XCTAssertFalse(other.consumeSearchFocusRequest())
        other.selectedTab = .feed

        XCTAssertTrue(MacSceneCommands10878.quickSearch(target: main, permitsBrowsing: true))
        XCTAssertEqual(main.selectedTab, .search)
        XCTAssertTrue(main.consumeSearchFocusRequest())
        XCTAssertFalse(main.consumeSearchFocusRequest())
        XCTAssertEqual(other.selectedTab, .feed)
        XCTAssertFalse(other.consumeSearchFocusRequest())

        // Warm: already on Search, still exactly one focus per press.
        XCTAssertTrue(MacSceneCommands10878.quickSearch(target: main, permitsBrowsing: true))
        XCTAssertTrue(main.consumeSearchFocusRequest())
        XCTAssertFalse(main.consumeSearchFocusRequest())
        XCTAssertFalse(other.consumeSearchFocusRequest())
    }

    @MainActor
    func testReportActionIsLocalAndDoesNotNavigate() {
        let main = MacSceneCommands10878.makeNavigation(initialTab: .search)
        let game = MacSceneCommands10878.makeNavigation(initialTab: .feed)
        XCTAssertFalse(MacSceneCommands10878.reportBug(target: nil))
        XCTAssertFalse(main.showBugReport)
        XCTAssertFalse(game.showBugReport)
        XCTAssertTrue(MacSceneCommands10878.reportBug(target: game))
        XCTAssertTrue(game.showBugReport)
        XCTAssertFalse(main.showBugReport)
        XCTAssertEqual(game.selectedTab, .feed)
        XCTAssertEqual(main.selectedTab, .search)
    }

    @MainActor
    func testSearchURLQueuesOnlyTheReceivingScenesQuery() throws {
        let receiving = MacSceneCommands10878.makeNavigation()
        let other = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        XCTAssertTrue(receiving.handleURL(try XCTUnwrap(URL(string: "bainluck://search?q=Oscars"))))
        XCTAssertEqual(receiving.selectedTab, .search)
        XCTAssertEqual(receiving.consumeSearchQuery(), "Oscars")
        XCTAssertNil(receiving.pendingSearchQuery)
        XCTAssertEqual(other.selectedTab, .myStuff)
        XCTAssertNil(other.pendingSearchQuery)
        XCTAssertNil(other.pendingRoute)
    }

    @MainActor
    func testDelayedEventURLRouteCannotLeakIntoAnotherScene() async throws {
        let receiving = MacSceneCommands10878.makeNavigation()
        let other = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        let published = expectation(description: "Receiving scene publishes event route")
        let noOtherRoute = expectation(description: "Other scene receives no route")
        noOtherRoute.isInverted = true
        let firstSubscription = receiving.$pendingRoute
            .first(where: { $0 == .eventDetail(id: 123) })
            .sink { _ in published.fulfill() }
        let secondSubscription = other.$pendingRoute.compactMap { $0 }
            .sink { _ in noOtherRoute.fulfill() }
        defer {
            firstSubscription.cancel()
            secondSubscription.cancel()
        }
        XCTAssertTrue(receiving.handleURL(try XCTUnwrap(URL(string: "bainluck://events/123"))))
        await fulfillment(of: [published, noOtherRoute], timeout: 0.5)
        XCTAssertEqual(receiving.selectedTab, .feed)
        XCTAssertEqual(receiving.consumeRoute(), .eventDetail(id: 123))
        XCTAssertNil(receiving.pendingRoute)
        XCTAssertEqual(other.selectedTab, .myStuff)
        XCTAssertNil(other.pendingRoute)
    }
}
