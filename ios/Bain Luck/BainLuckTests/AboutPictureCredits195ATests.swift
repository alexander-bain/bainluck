import SwiftUI
import UIKit
import WebKit
import XCTest
@testable import Bain_Luck

/// Ruling 195-A (#12659) — About screen keeps the fine-print "Picture credits" link
/// (`https://www.bainluck.com/picture-credits`, handed off to the system browser) without
/// adding a duplicate separate row under "Start Exploring", while "Start Exploring" (`/discover`)
/// switches natively to the Discover tab.
@MainActor
final class AboutPictureCredits195ATests: XCTestCase {

    func testPictureCreditsFinePrintHandsOffToSystemWhileDiscoverOpensInApp() throws {
        XCTAssertEqual(
            AboutView.pictureCreditsURL.absoluteString,
            "https://www.bainluck.com/picture-credits"
        )
        XCTAssertFalse(
            InAppWebViewNavigation.rendersInPlace(
                AboutView.pictureCreditsURL,
                embedding: AboutView.aboutURL,
                under: .handOffToTheSystem
            ),
            "/picture-credits must open in the system browser, never inside the About web view"
        )
        XCTAssertFalse(
            InAppWebViewNavigation.rendersInPlace(
                try XCTUnwrap(URL(string: "https://bainluck.com/picture-credits")),
                embedding: AboutView.aboutURL,
                under: .handOffToTheSystem
            )
        )

        let nav = NavigationCoordinator()
        nav.selectedTab = .feed
        var didDismiss = false
        XCTAssertFalse(
            AboutView.handleOutgoingLink(
                AboutView.pictureCreditsURL,
                navigation: nav,
                dismiss: { didDismiss = true }
            ),
            "/picture-credits must not be intercepted into the Discover tab"
        )
        XCTAssertFalse(didDismiss)
        XCTAssertEqual(nav.selectedTab, .feed)
        XCTAssertFalse(
            nav.handleURL(AboutView.pictureCreditsURL),
            "NavigationCoordinator must let /picture-credits open in Safari"
        )

        let discoverURL = try XCTUnwrap(URL(string: "https://www.bainluck.com/discover"))
        XCTAssertTrue(InAppWebViewNavigation.opensDiscoverInApp(discoverURL))
        XCTAssertTrue(
            AboutView.handleOutgoingLink(
                discoverURL,
                navigation: nav,
                dismiss: { didDismiss = true }
            ),
            "/discover CTA must dismiss About and switch natively to Discover"
        )
        XCTAssertTrue(didDismiss)
        XCTAssertEqual(nav.selectedTab, .discover)
    }

    func testAboutScreenMountsNoDuplicateSeparatePictureCreditsRowAndExports390pxRender() async throws {
        func findWebView(in root: UIView) -> WKWebView? {
            if let wv = root as? WKWebView { return wv }
            for sub in root.subviews {
                if let found = findWebView(in: sub) { return found }
            }
            return nil
        }

        func findView(withIdentifier id: String, in root: UIView) -> UIView? {
            if root.accessibilityIdentifier == id { return root }
            for sub in root.subviews {
                if let found = findView(withIdentifier: id, in: sub) { return found }
            }
            return nil
        }

        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let previousKey = scene?.windows.first(where: \.isKeyWindow)

        let screen = NavigationStack {
            AboutView()
        }
        .environmentObject(NavigationCoordinator())
        .environment(\.colorScheme, .light)
        .frame(width: 390, height: 852)

        let host = hostForMeasurement(screen, at: .large)
        host.overrideUserInterfaceStyle = .light
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 852)
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
            previousKey?.makeKeyAndVisible()
        }

        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))

        XCTAssertNil(
            findWebView(in: host.view),
            "Native #12672 AboutView renders directly in SwiftUI"
        )
        XCTAssertNil(
            findView(withIdentifier: "in-app-webview-scroll-footer", in: host.view),
            "Separate duplicate Picture credits row must not be mounted below Start Exploring"
        )
        XCTAssertNil(
            findView(withIdentifier: "about-picture-credits-link", in: host.view),
            "AboutView must not mount a second duplicate Picture credits row alongside the bottom fine-print row"
        )
    }
}
