#if os(iOS)
import SwiftUI
import UIKit

/// #11703 — closes a page's popover from UIKit, where the page's own state
/// cannot reach it in time.
///
/// A link that pushes another game covers the page before its `onDisappear`
/// runs. By then the page is off its window, and SwiftUI does not apply that
/// page's `isPresented = false` to the popover until something redraws it.
/// Hosted iOS 27 (draft PR #11784, master 12c0237e): the page was off its
/// window at 0.18 s and the details were still up over the next game at
/// 1.5 s. The popover's own content is still on screen, so it records the
/// controller that presents it, and the page dismisses exactly that one.
final class PresentedDetailsCloser {
    private weak var presented: UIViewController?

    fileprivate func adopt(_ controller: UIViewController) { presented = controller }

    /// Dismisses the recorded popover if it is still up. It never touches
    /// any other presentation.
    func close() {
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
#endif
