import Combine
import Foundation
import XCTest
@testable import Bain_Luck

/// Transition guards; primary-window reopening and focus remain Mac runtime gates.
final class MacNotificationDelivery10878Tests: XCTestCase {
    @MainActor
    func testIneligibleBindClearsOldTargetAndPendingFlushesOnlyToNewMain() throws {
        let delivery = MacNotificationDelivery10878()
        let oldMain = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        let game = MacSceneCommands10878.makeNavigation(initialTab: .feed)
        let newMain = MacSceneCommands10878.makeNavigation()
        delivery.bind(oldMain, permitsBrowsing: true)
        delivery.bind(game, permitsBrowsing: false)
        delivery.receive(.url(try XCTUnwrap(URL(string: "bainluck://search?q=Oscars"))))
        XCTAssertEqual(oldMain.selectedTab, .myStuff)
        XCTAssertNil(oldMain.pendingSearchQuery)
        XCTAssertEqual(game.selectedTab, .feed)
        XCTAssertNil(game.pendingSearchQuery)
        delivery.bind(newMain, permitsBrowsing: true)
        XCTAssertEqual(newMain.selectedTab, .search)
        XCTAssertEqual(newMain.consumeSearchQuery(), "Oscars")
        delivery.bind(oldMain, permitsBrowsing: true)
        XCTAssertEqual(oldMain.selectedTab, .myStuff)
        XCTAssertNil(oldMain.pendingSearchQuery)
    }

    @MainActor
    func testLatestPendingTapWinsAndNoneDoesNotEraseIt() throws {
        let delivery = MacNotificationDelivery10878()
        let main = MacSceneCommands10878.makeNavigation()
        delivery.receive(.url(try XCTUnwrap(URL(string: "bainluck://search?q=old"))))
        delivery.receive(.url(try XCTUnwrap(URL(string: "bainluck://search?q=new"))))
        delivery.receive(.none)
        delivery.bind(main, permitsBrowsing: true)
        XCTAssertEqual(main.consumeSearchQuery(), "new")
        XCTAssertNil(main.pendingRoute)
    }

    @MainActor
    func testInstallingWindowRequestFlushesThroughSynchronousBindExactlyOnce() throws {
        let delivery = MacNotificationDelivery10878()
        let main = MacSceneCommands10878.makeNavigation()
        let second = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        var requests = 0
        delivery.receive(.url(try XCTUnwrap(URL(string: "bainluck://search?q=queued"))))
        delivery.installWindowRequest {
            requests += 1
            delivery.bind(main, permitsBrowsing: true)
            delivery.bind(second, permitsBrowsing: true)
        }
        XCTAssertEqual(requests, 1)
        XCTAssertEqual(main.consumeSearchQuery(), "queued")
        XCTAssertEqual(second.selectedTab, .myStuff)
        XCTAssertNil(second.pendingSearchQuery)
        delivery.installWindowRequest { requests += 1 }
        XCTAssertEqual(requests, 1)
    }

    @MainActor
    func testMissingTargetRequestsWindowAndNoneDoesNotRequestOne() throws {
        let delivery = MacNotificationDelivery10878()
        var requests = 0
        delivery.installWindowRequest { requests += 1 }
        delivery.receive(.none)
        XCTAssertEqual(requests, 0)
        delivery.receive(.url(try XCTUnwrap(URL(string: "bainluck://my-stuff"))))
        XCTAssertEqual(requests, 1)
        let main = MacSceneCommands10878.makeNavigation()
        delivery.bind(main, permitsBrowsing: true)
        XCTAssertEqual(main.selectedTab, .myStuff)
        delivery.bind(nil, permitsBrowsing: true)
        delivery.receive(.url(try XCTUnwrap(URL(string: "bainluck://search?q=next"))))
        XCTAssertEqual(requests, 2)
        XCTAssertEqual(main.selectedTab, .myStuff)
        XCTAssertNil(main.pendingSearchQuery)
    }

    @MainActor
    func testDispatchClearsPendingBeforeReentrantBind() throws {
        let delivery = MacNotificationDelivery10878()
        let main = MacSceneCommands10878.makeNavigation()
        let second = MacSceneCommands10878.makeNavigation(initialTab: .myStuff)
        var rebindings = 0
        let subscription = main.$selectedTab.dropFirst().sink { _ in
            rebindings += 1
            delivery.bind(second, permitsBrowsing: true)
        }
        defer { subscription.cancel() }
        delivery.bind(main, permitsBrowsing: true)
        delivery.receive(.url(try XCTUnwrap(URL(string: "bainluck://search?q=single"))))
        XCTAssertEqual(rebindings, 1)
        XCTAssertEqual(main.consumeSearchQuery(), "single")
        XCTAssertEqual(second.selectedTab, .myStuff)
        XCTAssertNil(second.pendingSearchQuery)
    }
}
