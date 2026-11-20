#if os(iOS)
import UIKit
import XCTest
@testable import Bain_Luck

/// #10873 — a Siri, Shortcuts or Control Center "open" closes what the reader
/// left open, then routes (`IntentRouteCloser10873`).
///
/// Measured before this rule (iOS 27 simulator, master `e948d55104`): with the
/// chart in Full Screen, "Open My Stuff" switched the tab to My Stuff behind
/// the chart and the reader still saw the chart.
///
/// These present real UIKit controllers in a real window of the test host, so
/// the dismissals are UIKit's own. They do not show a SwiftUI sheet hearing its
/// dismissal, Siri, or a real iPhone: the simulator walk on the PR shows the
/// app, and a device check owns the phone.
@MainActor
final class IntentRouteCloser10873Tests: XCTestCase {

    private final class HearsDismissal: NSObject, UIAdaptivePresentationControllerDelegate {
        let name: String
        let log: (String) -> Void

        init(_ name: String, log: @escaping (String) -> Void) {
            self.name = name
            self.log = log
        }

        func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
            log("heard \(name)")
        }
    }

    /// A root whose dismissal UIKit holds: it keeps the completion and never
    /// calls it unless the test does.
    private final class HoldingRoot: UIViewController {
        var shown: UIViewController?
        var heldCompletion: (() -> Void)?
        override var presentedViewController: UIViewController? { shown }
        override func dismiss(animated flag: Bool, completion: (() -> Void)? = nil) {
            heldCompletion = completion
        }
    }

    private final class ShownBy: UIViewController {
        weak var presenter: UIViewController?
        override var presentingViewController: UIViewController? { presenter }
    }

    private var events: [String] = []
    private var spies: [HearsDismissal] = []

    private func window() throws -> UIViewController {
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first)
        let window = UIWindow(windowScene: scene)
        let root = UIViewController()
        window.rootViewController = root
        window.makeKeyAndVisible()
        addTeardownBlock { @MainActor in
            window.rootViewController?.dismiss(animated: false)
            window.isHidden = true
        }
        return root
    }

    /// `heard` names the spy that listens for the dismissal; nil listens for none
    /// (an alert's presentation is UIKit's own).
    private func present(_ shown: UIViewController, from presenter: UIViewController, heard name: String?) {
        if let name {
            let spy = HearsDismissal(name) { [weak self] in self?.events.append($0) }
            spies.append(spy)
            shown.presentationController?.delegate = spy
        }
        let done = expectation(description: "presented \(name ?? "alert")")
        presenter.present(shown, animated: false) { done.fulfill() }
        wait(for: [done], timeout: 2)
    }

    private func sheet(_ style: UIModalPresentationStyle = .pageSheet) -> UIViewController {
        let controller = UIViewController()
        controller.modalPresentationStyle = style
        return controller
    }

    private func close(_ roots: [UIViewController]) -> XCTestExpectation {
        let routed = expectation(description: "routed")
        IntentRouteCloser10873.closePresentations(over: roots) { [weak self] in
            self?.events.append("routed with \(roots.map { IntentRouteCloser10873.presentedChain(over: $0).count })")
            routed.fulfill()
        }
        return routed
    }

    func testWithNothingOpenTheLinkRoutesInTheSameTurn() throws {
        let root = try window()
        let routed = close([root])
        XCTAssertEqual(events, ["routed with [0]"], "a cold launch must never wait")
        wait(for: [routed], timeout: 0)
    }

    func testAFullScreenViewIsClosedAndHeardBeforeTheLinkRoutes() throws {
        let root = try window()
        present(sheet(.fullScreen), from: root, heard: "chart")
        wait(for: [close([root])], timeout: 2)
        XCTAssertEqual(events, ["heard chart", "routed with [0]"])
        XCTAssertNil(root.presentedViewController)
    }

    func testStackedSheetsAllCloseTopFirst() throws {
        let root = try window()
        let lower = sheet()
        present(lower, from: root, heard: "lower")
        present(sheet(), from: lower, heard: "upper")
        wait(for: [close([root])], timeout: 2)
        XCTAssertEqual(events, ["heard upper", "heard lower", "routed with [0]"])
    }

    func testAnAlertIsLeftUpAndTheLinkRoutesBehindIt() throws {
        let root = try window()
        let lower = sheet()
        present(lower, from: root, heard: "sheet")
        present(UIAlertController(title: "Sign out?", message: nil, preferredStyle: .alert), from: lower, heard: nil)
        let routed = close([root])
        XCTAssertEqual(events, ["routed with [2]"])
        wait(for: [routed], timeout: 0)
    }

    func testASheetThatRefusesASwipeIsLeftUp() throws {
        let root = try window()
        let consent = sheet()
        consent.isModalInPresentation = true
        present(consent, from: root, heard: "consent")
        let routed = close([root])
        XCTAssertEqual(events, ["routed with [1]"])
        wait(for: [routed], timeout: 0)
    }

    func testEveryForegroundWindowClosesBeforeTheLinkRoutesOnce() throws {
        let first = try window()
        let second = try window()
        let untouched = try window()
        present(sheet(), from: first, heard: "first")
        present(sheet(.fullScreen), from: second, heard: "second")
        wait(for: [close([first, second, untouched])], timeout: 2)
        XCTAssertEqual(events.filter { $0.hasPrefix("routed") }, ["routed with [0, 0, 0]"])
        XCTAssertEqual(Set(events.filter { $0.hasPrefix("heard") }), ["heard first", "heard second"])
    }

    func testAHeldDismissalStillRoutesExactlyOnce() {
        let previous = IntentRouteCloser10873.fallbackDelay
        IntentRouteCloser10873.fallbackDelay = 0.05
        addTeardownBlock { @MainActor in IntentRouteCloser10873.fallbackDelay = previous }

        let root = HoldingRoot()
        let shown = ShownBy()
        shown.presenter = root
        root.shown = shown
        var routes = 0
        let routed = expectation(description: "routed by the fallback")
        IntentRouteCloser10873.closePresentations(over: [root]) {
            routes += 1
            routed.fulfill()
        }
        XCTAssertNotNil(root.heldCompletion, "the dismissal was asked for")
        XCTAssertEqual(routes, 0, "the link waits for the dismissal")
        wait(for: [routed], timeout: 2)

        root.heldCompletion?()  // UIKit finally lets it go
        RunLoop.main.run(until: Date().addingTimeInterval(0.1))
        XCTAssertEqual(routes, 1)
    }
}
#endif
