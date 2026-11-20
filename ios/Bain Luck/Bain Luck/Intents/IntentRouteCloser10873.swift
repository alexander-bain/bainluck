#if os(iOS)
import UIKit

/// #10873 — a Siri, Shortcuts or Control Center "open" lands in front of the
/// reader, not behind whatever they left open.
///
/// The router changes the tab and pushes the page; it never closed anything.
/// A sheet or full-screen view — the chart's Full Screen, a card reader, a share
/// sheet — is presented from the window's root controller, above every tab, so
/// it stayed up and the destination opened out of sight behind it. Measured on
/// the iOS 27 simulator (master `e948d55104`): with the win-probability chart in
/// Full Screen, Spotlight's "Open My Stuff" ran, the link was handed over and
/// the tab switched to My Stuff (`selectedTab` 0 → 4), and the reader still saw
/// the chart.
///
/// So before an intent's link is routed, what is presented on each foreground
/// window is closed the way a swipe down closes it: dismissed, then each
/// presentation's delegate hears the dismissal, so SwiftUI knows it is gone and
/// does not present it again (`PageDetailsCloser`, #11703, learned that SwiftUI
/// re-presents what it still thinks is open). With nothing presented, the link
/// routes in the same turn, exactly as before — a cold launch never waits.
///
/// What a swipe could not close is left alone, with everything under it: an
/// alert, or a sheet that refuses a swipe down (`interactiveDismissDisabled`,
/// such as the telemetry consent ask). Each is a decision the reader has not
/// made yet. The link then routes behind it, as it always did.
///
/// The link routes exactly once: when the dismissals finish, or after
/// `fallbackDelay` if UIKit holds one (#11703 saw a dismissal held for 5 s).
@MainActor
enum IntentRouteCloser10873 {
    /// How long a held dismissal may delay the link before it routes anyway.
    static var fallbackDelay: TimeInterval = 1.0

    /// Closes what is presented over each of `roots`, then calls `route`.
    static func closePresentations(over roots: [UIViewController], then route: @escaping @MainActor () -> Void) {
        let chains = roots.map(presentedChain(over:)).filter { chain in
            !chain.isEmpty && !chain.contains { $0 is UIAlertController || $0.isModalInPresentation }
        }
        guard !chains.isEmpty else {
            route()
            return
        }

        let routing = PendingRoute(closing: chains.count, route: route)
        for chain in chains {
            // Top first, the order a reader would close them in.
            let presentations = chain.reversed().compactMap(\.presentationController)
            let closed = {
                for presentation in presentations {
                    presentation.delegate?.presentationControllerDidDismiss?(presentation)
                }
                routing.closedOne()
            }
            if let presenter = chain[0].presentingViewController {
                presenter.dismiss(animated: false, completion: closed)
            } else {
                closed()
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + fallbackDelay) { routing.routeOnce() }
    }

    /// Routes once every window has closed, or when the fallback fires first.
    private final class PendingRoute {
        private var closing: Int
        private var route: (@MainActor () -> Void)?

        init(closing: Int, route: @escaping @MainActor () -> Void) {
            self.closing = closing
            self.route = route
        }

        func closedOne() {
            closing -= 1
            if closing == 0 { routeOnce() }
        }

        func routeOnce() {
            guard let route else { return }
            self.route = nil
            route()
        }
    }

    /// The root controller of every window the reader can see.
    static func foregroundRoots() -> [UIViewController] {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .filter { $0.activationState == .foregroundActive || $0.activationState == .foregroundInactive }
            .compactMap { scene in
                (scene.keyWindow ?? scene.windows.first { !$0.isHidden && $0.rootViewController != nil })?
                    .rootViewController
            }
    }

    /// What is presented over `root`, bottom first.
    static func presentedChain(over root: UIViewController) -> [UIViewController] {
        var chain: [UIViewController] = []
        var next = root.presentedViewController
        while let presented = next {
            chain.append(presented)
            next = presented.presentedViewController
        }
        return chain
    }
}
#endif
