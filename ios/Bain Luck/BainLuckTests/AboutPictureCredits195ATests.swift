import SwiftUI
import UIKit
import WebKit
import XCTest
@testable import Bain_Luck

/// Ruling 195-A (#12659) — About screen carries a "Picture credits" link as the last row
/// of the page's own scrollable content (never pinned over the text), opening
/// `https://www.bainluck.com/picture-credits` in the system browser.
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

    func testPictureCreditsFooterScrollsWithPageContentBelowDocumentAndGrowsAtAX5() async throws {
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

        // Verify deterministically with local HTML that the footer lives inside WKWebView.scrollView
        // at y == contentSize.height (never pinned over the viewport).
        let localTestURL = URL(string: "http://127.0.0.1:1/about")!
        let testWebView = InAppWebView(
            url: localTestURL,
            linkPolicy: .handOffToTheSystem,
            scrollFooter: AnyView(AboutView.pictureCreditsFooter)
        )
        .frame(width: 390, height: 600)

        let localHost = hostForMeasurement(testWebView, at: .large)
        localHost.view.frame = CGRect(x: 0, y: 0, width: 390, height: 600)
        let localWindow: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: localHost.view.frame)
        localWindow.frame = localHost.view.frame
        localWindow.rootViewController = localHost
        localWindow.isHidden = false
        defer {
            localWindow.isHidden = true
            localWindow.rootViewController = nil
            previousKey?.makeKeyAndVisible()
        }

        localHost.view.setNeedsLayout()
        localHost.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.05))

        let wk = try XCTUnwrap(findWebView(in: localHost.view))
        wk.stopLoading()
        // WKWebView fills the entire container height (nothing is pinned below it stealing viewport height).
        XCTAssertEqual(wk.frame.height, 600, accuracy: 1.0)

        let tallHTML = """
        <!doctype html><html><body style="margin:0;padding:0;">
        <div style="height:1600px;background:#f8fafc;">Tall About copy</div>
        </body></html>
        """
        wk.loadHTMLString(tallHTML, baseURL: localTestURL)

        let loadDeadline = Date().addingTimeInterval(4.0)
        repeat {
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))
            try await Task.sleep(nanoseconds: 50_000_000)
            if !wk.isLoading, wk.scrollView.contentSize.height >= 1500 {
                break
            }
        } while Date() < loadDeadline

        let scrollFooterView = try XCTUnwrap(
            findView(withIdentifier: "in-app-webview-scroll-footer", in: wk.scrollView),
            "Picture credits row must be a child of WKWebView.scrollView so it scrolls with the page"
        )
        XCTAssertFalse(scrollFooterView.isHidden)
        XCTAssertGreaterThanOrEqual(wk.scrollView.contentInset.bottom, 44)
        XCTAssertEqual(
            scrollFooterView.frame.minY,
            wk.scrollView.contentSize.height,
            accuracy: 1.0,
            "Picture credits row must start at the exact bottom of the web document, covering zero copy"
        )
        // At the top of the page (offset 0), the footer is far below the 600pt viewport.
        XCTAssertGreaterThan(scrollFooterView.frame.minY - wk.scrollView.contentOffset.y, wk.bounds.height)

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

            let deadline = Date().addingTimeInterval(12.0)
            repeat {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.05))
                try await Task.sleep(nanoseconds: 100_000_000)
                if let wv = findWebView(in: host.view), !wv.isLoading, wv.estimatedProgress >= 0.99, wv.scrollView.contentSize.height > 900 {
                    break
                }
            } while Date() < deadline

            if let wv = findWebView(in: host.view) {
                // Step down the scrollView so IntersectionObserver reveals every section cleanly,
                // then settle at the exact bottom so the last row ("Picture credits") is visible.
                let totalHeight = wv.scrollView.contentSize.height + wv.scrollView.adjustedContentInset.bottom
                let maxOffset = max(0, totalHeight - wv.scrollView.bounds.height)
                let steps = 6
                for i in 1...steps {
                    let y = maxOffset * CGFloat(i) / CGFloat(steps)
                    wv.scrollView.setContentOffset(CGPoint(x: 0, y: y), animated: false)
                    wv.setNeedsLayout()
                    wv.layoutIfNeeded()
                    RunLoop.current.run(until: Date().addingTimeInterval(0.05))
                    try await Task.sleep(nanoseconds: 150_000_000)
                }
                // Recompute bottom offset after any final layout adjustments and wait for CSS reveal transition (700ms).
                let finalTotal = wv.scrollView.contentSize.height + wv.scrollView.adjustedContentInset.bottom
                let finalBottomOffset = max(0, finalTotal - wv.scrollView.bounds.height)
                wv.scrollView.setContentOffset(CGPoint(x: 0, y: finalBottomOffset), animated: false)
                try await Task.sleep(nanoseconds: 900_000_000)
                RunLoop.current.run(until: Date().addingTimeInterval(0.1))
            }

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
