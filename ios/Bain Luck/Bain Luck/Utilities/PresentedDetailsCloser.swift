#if os(iOS)
import SwiftUI
import UIKit

/// #11703 — closes a page's popover from UIKit, the moment the page leaves
/// its window.
///
/// A link that pushes another game covers the page, but the page's popover is
/// presented above the whole stack. SwiftUI hears about the cover late: on
/// hosted iOS 27 (draft PR #11784, master 12c0237e) the page was off its
/// window at 0.32 s, its `onDisappear` ran at 5.02 s, and the details stayed
/// up over the next game until 6.31 s. So the popover's content records the
/// controller that presents it (`PresentedDetailsAnchor`), and a view at the
/// page's root dismisses that one when UIKit takes the page off its window
/// (`PageWindowAnchor`).
final class PresentedDetailsCloser {
    private weak var presented: UIViewController?

    fileprivate func adopt(_ controller: UIViewController) { presented = controller }

    /// The page at `pageView` is leaving `window`. Dismisses the recorded
    /// popover, or failing that a popover anchored inside this page. It never
    /// touches another page's presentation.
    fileprivate func pageLeaving(_ pageView: UIView, window: UIWindow) {
        var targets: [UIViewController] = []
        if let presented { targets.append(presented) }
        var next = window.rootViewController?.presentedViewController
        while let controller = next {
            if controller.modalPresentationStyle == .popover,
               let source = controller.popoverPresentationController?.sourceView,
               source.isDescendant(of: pageView) {
                targets.append(controller)
            }
            next = controller.presentedViewController
        }
        guard !targets.isEmpty else { return }
        // One turn later: this runs inside the push's own completion, and a
        // dismissal started there can be dropped.
        DispatchQueue.main.async {
            for controller in targets where controller.presentingViewController != nil
                && !controller.isBeingDismissed {
                controller.dismiss(animated: false)
            }
        }
    }
}

/// Placed inside the popover's content. It records the presented controller
/// that holds it, once it is on a window.
struct PresentedDetailsAnchor: UIViewRepresentable {
    let closer: PresentedDetailsCloser

    func makeUIView(context: Context) -> Probe {
        let probe = Probe()
        probe.closer = closer
        probe.isUserInteractionEnabled = false
        return probe
    }

    func updateUIView(_ probe: Probe, context: Context) { probe.closer = closer }

    final class Probe: UIView {
        var closer: PresentedDetailsCloser?

        override func didMoveToWindow() {
            super.didMoveToWindow()
            guard window != nil else { return }
            // The root of a presentation has no parent and a presenter. A
            // child controller also reports its ancestor's presenter, so the
            // parent check keeps that child from being recorded.
            var responder: UIResponder? = next
            while let current = responder {
                if let controller = current as? UIViewController,
                   controller.parent == nil, controller.presentingViewController != nil {
                    closer?.adopt(controller)
                    return
                }
                responder = current.next
            }
        }
    }
}

/// Placed at the page's root, outside any lazy stack. When UIKit takes the
/// page off its window, it closes the page's popover.
struct PageWindowAnchor: UIViewRepresentable {
    let closer: PresentedDetailsCloser

    func makeUIView(context: Context) -> Probe {
        let probe = Probe()
        probe.closer = closer
        probe.isUserInteractionEnabled = false
        return probe
    }

    func updateUIView(_ probe: Probe, context: Context) { probe.closer = closer }

    final class Probe: UIView {
        var closer: PresentedDetailsCloser?

        override func willMove(toWindow newWindow: UIWindow?) {
            super.willMove(toWindow: newWindow)
            guard newWindow == nil, let window else { return }
            closer?.pageLeaving(pageView ?? self, window: window)
        }

        /// The root view of the controller hosting this page.
        private var pageView: UIView? {
            var view: UIView? = self
            while let current = view {
                if current.next is UIViewController { return current }
                view = current.superview
            }
            return nil
        }
    }
}
#endif
