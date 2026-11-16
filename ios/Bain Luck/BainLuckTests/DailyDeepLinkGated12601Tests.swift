import XCTest
@testable import Bain_Luck

/// #12601 — while `ReleaseSurfaces.predictionsExperienceEnabled` is `false`,
/// `bainluck://daily`, `bainluck://challenge/<code>`, and their `bainluck.com`
/// / `www.bainluck.com` counterparts land on Discover without pushing the
/// Daily Challenge or Friend Challenge screens; flipping the switch back on
/// restores both routes.
@MainActor
final class DailyDeepLinkGated12601Tests: XCTestCase {

    func testShippingSwitchDefaultsToOff() {
        let nav = NavigationCoordinator()
        XCTAssertFalse(ReleaseSurfaces.predictionsExperienceEnabled)
        XCTAssertFalse(nav.predictionsExperienceEnabled)
    }

    func testDailyLinksLandOnDiscoverWithoutPushingChallengeWhenOff() throws {
        for raw in [
            "bainluck://daily",
            "https://bainluck.com/daily",
            "https://www.bainluck.com/daily",
        ] {
            let nav = NavigationCoordinator()
            nav.selectedTab = .leagues
            nav.pendingRoute = .calibration

            XCTAssertTrue(
                nav.handleURL(try XCTUnwrap(URL(string: raw))),
                "\(raw) should still be accepted so an old link lands on Discover"
            )
            XCTAssertEqual(nav.selectedTab, .discover, "\(raw) should switch to Discover")
            XCTAssertNil(nav.pendingRoute, "\(raw) should clear any queued route immediately")

            let settled = expectation(description: "runloop hop settled for \(raw)")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { settled.fulfill() }
            wait(for: [settled], timeout: 1.0)

            XCTAssertNil(
                nav.consumeRoute(),
                "\(raw) must not push .dailyChallenge while predictionsExperienceEnabled is false"
            )
        }
    }

    func testFriendChallengeLinksLandOnDiscoverWithoutPushingChallengeWhenOff() throws {
        for raw in [
            "bainluck://challenge/abc123",
            "https://bainluck.com/challenge/abc123",
            "https://www.bainluck.com/challenge/abc123",
        ] {
            let nav = NavigationCoordinator()
            nav.selectedTab = .myStuff
            nav.pendingRoute = .about

            XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: raw))))
            XCTAssertEqual(nav.selectedTab, .discover)
            XCTAssertNil(nav.pendingRoute)

            let settled = expectation(description: "runloop hop settled for \(raw)")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { settled.fulfill() }
            wait(for: [settled], timeout: 1.0)

            XCTAssertNil(
                nav.consumeRoute(),
                "\(raw) must not push .friendChallenge while predictionsExperienceEnabled is false"
            )
        }

        let nav = NavigationCoordinator()
        XCTAssertFalse(
            nav.handleURL(try XCTUnwrap(URL(string: "bainluck://challenge"))),
            "a bare challenge URL without a code remains unclaimed"
        )
    }

    func testFlippingSwitchBackOnRestoresDailyAndFriendChallengeRoutes() throws {
        let dailyNav = NavigationCoordinator()
        dailyNav.predictionsExperienceEnabled = true
        dailyNav.selectedTab = .leagues

        XCTAssertTrue(dailyNav.handleURL(try XCTUnwrap(URL(string: "bainluck://daily"))))
        XCTAssertEqual(dailyNav.selectedTab, .discover)
        let dailyPushed = expectation(description: "daily route published")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { dailyPushed.fulfill() }
        wait(for: [dailyPushed], timeout: 1.0)
        XCTAssertEqual(dailyNav.consumeRoute(), .dailyChallenge)

        let challengeNav = NavigationCoordinator()
        challengeNav.predictionsExperienceEnabled = true
        challengeNav.selectedTab = .leagues

        XCTAssertTrue(challengeNav.handleURL(try XCTUnwrap(URL(string: "bainluck://challenge/xyz789"))))
        XCTAssertEqual(challengeNav.selectedTab, .discover)
        let challengePushed = expectation(description: "challenge route published")
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { challengePushed.fulfill() }
        wait(for: [challengePushed], timeout: 1.0)
        XCTAssertEqual(challengeNav.consumeRoute(), .friendChallenge(code: "xyz789"))
    }
}
