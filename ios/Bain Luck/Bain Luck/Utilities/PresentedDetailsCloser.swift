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

    fileprivate func adopt(_ controller: UIViewController) {
        presented = controller
        print("DIAG11703 adopt t=\(CACurrentMediaTime()) type=\(type(of: controller)) style=\(controller.modalPresentationStyle.rawValue) presenter=\(controller.presentingViewController.map { String(describing: type(of: $0)) } ?? "nil")")
    }

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
        var chain: [String] = []
        var walk = window.rootViewController?.presentedViewController
        while let c = walk {
            let src = c.popoverPresentationController?.sourceView
            chain.append("\(type(of: c))/style=\(c.modalPresentationStyle.rawValue)/src=\(src.map { String(describing: type(of: $0)) } ?? "nil")/inPage=\(src?.isDescendant(of: pageView) ?? false)")
            walk = c.presentedViewController
        }
        print("DIAG11703 pageLeaving t=\(CACurrentMediaTime()) page=\(type(of: pageView)) pageVC=\(pageView.next.map { String(describing: type(of: $0)) } ?? "nil") recorded=\(presented.map { String(describing: type(of: $0)) } ?? "nil") targets=\(targets.count) chain=\(chain)")
        guard !targets.isEmpty else { return }
        // One turn later: this runs inside the push's own completion, and a
        // dismissal started there can be dropped.
        DispatchQueue.main.async {
            for controller in targets where controller.presentingViewController != nil
                && !controller.isBeingDismissed {
                controller.dismiss(animated: false)
            }
            print("DIAG11703 dismissed t=\(CACurrentMediaTime()) stillPresented=\(window.rootViewController?.presentedViewController.map { String(describing: type(of: $0)) } ?? "nil") states=\(targets.map { "\($0.presentingViewController != nil)/\($0.isBeingDismissed)" })")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                print("DIAG11703 after0.3 t=\(CACurrentMediaTime()) stillPresented=\(window.rootViewController?.presentedViewController.map { String(describing: type(of: $0)) } ?? "nil")")
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
            print("DIAG11703 contentDidMove t=\(CACurrentMediaTime()) window=\(window != nil)")
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
            print("DIAG11703 pageWillMove t=\(CACurrentMediaTime()) toWindow=\(newWindow != nil) hadWindow=\(window != nil) closer=\(closer != nil)")
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
