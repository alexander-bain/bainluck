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
/// page's root dismisses exactly that one when UIKit takes the page off its
/// window (`PageWindowAnchor`).
final class PresentedDetailsCloser {
    private weak var presented: UIViewController?

    fileprivate func adopt(_ controller: UIViewController) { presented = controller }

    /// Dismisses the recorded popover if it is still up. It never touches
    /// any other presentation.
    fileprivate func close() {
        guard let presented, presented.presentingViewController != nil,
              !presented.isBeingDismissed else { return }
        presented.dismiss(animated: false)
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
/// page off its window, it closes the page's recorded popover.
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

        override func didMoveToWindow() {
            super.didMoveToWindow()
            if window == nil { closer?.close() }
        }
    }
}
#endif
