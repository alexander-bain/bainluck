import XCTest
@testable import Bain_Luck

/// #12028 — Universal links open the app from both `bainluck.com` and
/// `www.bainluck.com`, and both entitlements files declare both hosts.
final class UniversalLinks12028Tests: XCTestCase {

    private func source(_ relativePath: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent(relativePath), encoding: .utf8)
    }

    func testBothEntitlementsDeclareApexAndWwwAssociatedDomains() throws {
        for path in [
            "Bain Luck/Bain Luck.entitlements",
            "Bain Luck/Bain Luck-macOS.entitlements",
        ] {
            let plist = try XCTUnwrap(
                PropertyListSerialization.propertyList(
                    from: Data(try source(path).utf8),
                    format: nil
                ) as? [String: Any],
                "\(path) is not a valid plist"
            )
            let domains = try XCTUnwrap(
                plist["com.apple.developer.associated-domains"] as? [String],
                "\(path) is missing com.apple.developer.associated-domains"
            )
            XCTAssertTrue(
                domains.contains("applinks:bainluck.com"),
                "\(path) must claim applinks:bainluck.com"
            )
            XCTAssertTrue(
                domains.contains("applinks:www.bainluck.com"),
                "\(path) must claim applinks:www.bainluck.com so canonical www links open the app"
            )
        }
    }

    @MainActor
    func testBothApexAndWwwUniversalLinksOpenEventAndFuturesDetail() throws {
        for host in ["bainluck.com", "www.bainluck.com"] {
            let eventNav = NavigationCoordinator()
            XCTAssertTrue(
                eventNav.handleURL(try XCTUnwrap(URL(string: "https://\(host)/events/15304209"))),
                "\(host) event universal link was refused"
            )
            XCTAssertEqual(eventNav.selectedTab, .feed)
            let eventPushed = expectation(description: "event route published for \(host)")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { eventPushed.fulfill() }
            wait(for: [eventPushed], timeout: 1.0)
            XCTAssertEqual(eventNav.consumeRoute(), .eventDetail(id: 15304209))

            let futuresNav = NavigationCoordinator()
            XCTAssertTrue(
                futuresNav.handleURL(try XCTUnwrap(URL(string: "https://\(host)/futures/109085"))),
                "\(host) futures universal link was refused"
            )
            XCTAssertEqual(futuresNav.selectedTab, .feed)
            let futuresPushed = expectation(description: "futures route published for \(host)")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { futuresPushed.fulfill() }
            wait(for: [futuresPushed], timeout: 1.0)
            XCTAssertEqual(futuresNav.consumeRoute(), .futuresDetail(id: 109085))
        }
    }

    @MainActor
    func testBothApexAndWwwUniversalLinksOpenAasaRoutes() throws {
        for host in ["bainluck.com", "www.bainluck.com"] {
            let nav = NavigationCoordinator()
            nav.selectedTab = .leagues

            XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "https://\(host)/my-stuff"))))
            XCTAssertEqual(nav.selectedTab, .myStuff)

            XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "https://\(host)/search?q=lakers"))))
            XCTAssertEqual(nav.selectedTab, .search)
            XCTAssertEqual(nav.consumeSearchQuery(), "lakers")

            XCTAssertTrue(nav.handleURL(try XCTUnwrap(URL(string: "https://\(host)/ei/hall-of-fame"))))
            XCTAssertEqual(nav.selectedTab, .feed)
        }
    }
}
