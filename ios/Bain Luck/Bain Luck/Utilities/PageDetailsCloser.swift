#if os(iOS)
import SwiftUI
import UIKit

/// #11703 — closes a page's freshness details from UIKit the moment the page
/// leaves its window.
///
/// A link that pushes another game covers the page, but SwiftUI presents the
/// page's popover from the window's root controller, above the whole stack,
/// and hears about the cover late. On hosted iOS 27 (draft PR #11784, master
/// 12c0237e) the page was off its window at 0.18 s and the details were still
/// up over the next game at 1.5 s. The popover is anchored to the root
/// hosting view, not to anything inside the page, and its own content can
/// reach its window after the push (draft PR #11788), so neither can say
/// whose it is. The page can: a probe at its root hears UIKit take it off its
/// window (0.2 s after the push on #11788) and, if this page's details are
/// open, closes them the way a tap outside would — the popover goes, then
/// its delegate hears the dismissal so SwiftUI's `isPresented` reads false
/// and SwiftUI has nothing left to close later.
struct PageDetailsCloser: UIViewRepresentable {
    /// This page's details are open, as the page last rendered.
    let detailsOpen: Bool

    func makeUIView(context: Context) -> Probe {
        let probe = Probe()
        probe.detailsOpen = detailsOpen
        probe.isUserInteractionEnabled = false
        return probe
    }

    func updateUIView(_ probe: Probe, context: Context) { probe.detailsOpen = detailsOpen }

    final class Probe: UIView {
        var detailsOpen = false

        override func willMove(toWindow newWindow: UIWindow?) {
            super.willMove(toWindow: newWindow)
            guard newWindow == nil, detailsOpen, let window,
                  let details = PageDetailsCloser.detailsPopover(in: window) else { return }
            // At once: a turn later the main thread is building the page that
            // covered this one, and the close waited 1.4 s on hosted iOS 27
            // (#11791). If UIKit drops a dismissal started inside the push,
            // the next turn tries again — the same popover, never another.
            PageDetailsCloser.close(details)
            DispatchQueue.main.async { [weak details] in
                if let details { PageDetailsCloser.close(details) }
            }
        }
    }

    /// The details are the popover on top of the window's presentations.
    /// Anything else on top (a sheet, an alert) is left alone.
    static func detailsPopover(in window: UIWindow) -> UIViewController? {
        var top = window.rootViewController?.presentedViewController
        while let next = top?.presentedViewController { top = next }
        guard let top, top.modalPresentationStyle == .popover, !top.isBeingDismissed else { return nil }
        return top
    }

    static func close(_ popover: UIViewController) {
        guard popover.presentingViewController != nil, !popover.isBeingDismissed else { return }
        let presentation = popover.presentationController
        popover.dismiss(animated: false) {
            if let presentation {
                presentation.delegate?.presentationControllerDidDismiss?(presentation)
            }
        }
    }
}
#endif
