import XCTest
@testable import Bain_Luck

/// Guards Deliverable 5 (Fri Nov 13): tapping "Start exploring" (`/discover`) at the
/// bottom of the native About screen opens the app's Discover tab directly instead of
/// leaving the app for the website, while `/calibration`, `/privacy`, and `mailto:`
/// continue handing off to Safari and Mail (#5914).
final class AboutStartExploringOpensDiscoverTests: XCTestCase {

    func testOpensDiscoverInAppMatchesWwwAndApexDiscoverURLs() {
        XCTAssertTrue(
            InAppWebViewNavigation.opensDiscoverInApp(
                URL(string: "https://www.bainluck.com/discover")!
            )
        )
        XCTAssertTrue(
            InAppWebViewNavigation.opensDiscoverInApp(
                URL(string: "https://bainluck.com/discover")!
            )
        )
        XCTAssertTrue(
            InAppWebViewNavigation.opensDiscoverInApp(
                URL(string: "https://www.bainluck.com/discover/")!
            )
        )
        XCTAssertTrue(
            InAppWebViewNavigation.opensDiscoverInApp(
                URL(string: "https://www.bainluck.com/discover?source=about#top")!
            )
        )
    }

    func testOpensDiscoverInAppRejectsNonDiscoverAndExternalLinks() {
        for raw in [
            "https://www.bainluck.com/about?embed=1",
            "https://www.bainluck.com/calibration",
            "https://www.bainluck.com/privacy",
            "https://www.bainluck.com/",
            "mailto:bugs@bainluck.com",
            "https://kalshi.com/discover",
            "bainluck://www.bainluck.com/discover",
        ] {
            XCTAssertFalse(
                InAppWebViewNavigation.opensDiscoverInApp(URL(string: raw)!),
                "\(raw) should not intercept into the native Discover tab"
            )
        }
    }

    @MainActor
    func testHandleOutgoingLinkSwitchesToDiscoverAndDismissesAboutScreen() {
        let navigation = NavigationCoordinator()
        navigation.selectedTab = .myStuff
        var didDismiss = false

        let handled = AboutView.handleOutgoingLink(
            URL(string: "https://www.bainluck.com/discover")!,
            navigation: navigation,
            dismiss: { didDismiss = true }
        )

        XCTAssertTrue(handled, "Start exploring (/discover) must be handled inside the app")
        XCTAssertTrue(didDismiss, "AboutView must dismiss itself when switching to Discover")
        XCTAssertEqual(navigation.selectedTab, .discover, "Selected tab must switch to Discover")
    }

    @MainActor
    func testHandleOutgoingLinkLeavesCalibrationPrivacyAndMailtoToSystem() {
        for raw in [
            "https://www.bainluck.com/calibration",
            "https://www.bainluck.com/privacy",
            "mailto:bugs@bainluck.com",
        ] {
            let navigation = NavigationCoordinator()
            navigation.selectedTab = .myStuff
            var didDismiss = false

            let handled = AboutView.handleOutgoingLink(
                URL(string: raw)!,
                navigation: navigation,
                dismiss: { didDismiss = true }
            )

            XCTAssertFalse(handled, "\(raw) must still hand off to Safari/Mail")
            XCTAssertFalse(didDismiss)
            XCTAssertEqual(navigation.selectedTab, .myStuff)
        }
    }

    func testAboutViewWiresInterceptHandOffToHandleOutgoingLink() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent("AboutView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("interceptHandOff:"))
        XCTAssertTrue(source.contains("Self.handleOutgoingLink("))
    }
}
