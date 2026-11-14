import SwiftUI
import UIKit
import WebKit
import XCTest
@testable import Bain_Luck

/// Ruling 195-A (#12659) — About screen carries a "Picture credits" link that opens
/// the website's `/picture-credits` page in the system browser rather than inside the
/// confined About web view.
@MainActor
final class AboutPictureCredits195ATests: XCTestCase {

    func testPictureCreditsURLPointsToCanonicalSiteRouteAndHandsOffToSystem() throws {
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
        XCTAssertFalse(
            nav.handleURL(AboutView.pictureCreditsURL),
            "NavigationCoordinator must let /picture-credits open in Safari"
        )
    }

    func testAboutViewExposesPictureCreditsLinkAndExports390pxRender() async throws {
        var heights: [DynamicTypeSize: CGFloat] = [:]
        for dt in [DynamicTypeSize.large, .accessibility5] {
            let footer = AboutView.pictureCreditsFooter
            let host = hostForMeasurement(footer, at: dt)
            let fitted = host.sizeThatFits(
                in: CGSize(width: 390, height: UIView.layoutFittingCompressedSize.height)
            )
            XCTAssertEqual(fitted.width, 390, accuracy: 0.5)
            XCTAssertGreaterThan(fitted.height, 40)
            XCTAssertLessThan(fitted.height, 220, "Footer link must fit cleanly at \(dt)")
            heights[dt] = fitted.height
        }
        XCTAssertGreaterThan(
            try XCTUnwrap(heights[.accessibility5]),
            try XCTUnwrap(heights[.large]),
            "AX5 footer row must grow natively rather than clamping to a fixed height"
        )

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_195A_RENDERS_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            let screen = NavigationStack {
                AboutView()
            }
            .environmentObject(NavigationCoordinator())
            .environment(\.colorScheme, .light)
            .frame(width: 390, height: 852)

            let host = hostForMeasurement(screen, at: .large)
            host.overrideUserInterfaceStyle = .light
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 852)
            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = .light
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            func findWebView(in root: UIView) -> WKWebView? {
                if let wv = root as? WKWebView { return wv }
                for sub in root.subviews {
                    if let found = findWebView(in: sub) { return found }
                }
                return nil
            }
            let deadline = Date().addingTimeInterval(10.0)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.05))
                try await Task.sleep(nanoseconds: 100_000_000)
                if let wv = findWebView(in: host.view), !wv.isLoading, wv.estimatedProgress >= 0.99 {
                    break
                }
            } while Date() < deadline
            try await Task.sleep(nanoseconds: 500_000_000)
            RunLoop.current.run(until: Date().addingTimeInterval(0.1))

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            if let png = img.pngData() {
                try png.write(to: dirURL.appendingPathComponent("about-picture-credits-195a-390x852.png"))
            }
        }
    }
}
