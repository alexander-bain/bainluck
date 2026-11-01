#if os(iOS)
import SwiftUI
import UIKit

/// #11703 — closes a page's freshness details the moment UIKit takes the page
/// off its window.
///
/// A link that pushes another game covers the page, but SwiftUI presents the
/// page's popover from the window's root controller, above the whole stack,
/// and the page's `onDisappear` — where it closed them — runs seconds late:
/// on hosted iOS 27 (draft PR #11784, master 12c0237e) the page was off its
/// window at 0.18 s and the details were still up over the next game at
/// 1.5 s. A probe at the page's root hears the page leave its window 0.1–0.2 s
/// after the push (draft PRs #11788, #11791). In that turn it turns the page's
/// state off, so SwiftUI has nothing to present again — while the state still
/// read open, SwiftUI presented a closed popover again (#11791). The state
/// alone reaches SwiftUI late, and the popover was still up at 2 s (#11790,
/// a7e27b92), so one turn later it also closes that same popover the way a tap
/// outside would: the popover goes, then its delegate hears the dismissal so
/// SwiftUI knows it is gone. Not inside the push: UIKit held a dismissal
/// started there until +5.27 s, and the details stayed up over the next game
/// until then (9cccdaed, diag 944e5ee3). It never tries a second
/// time: on #11791 a retry's extra dismissal reached the root and closed the
/// next game's details.
struct PageDetailsCloser: UIViewRepresentable {
    /// The page's details state.
    @Binding var detailsOpen: Bool

    func makeUIView(context: Context) -> Probe {
        let probe = Probe()
        probe.detailsOpen = $detailsOpen
        probe.isUserInteractionEnabled = false
        return probe
    }

    func updateUIView(_ probe: Probe, context: Context) { probe.detailsOpen = $detailsOpen }

    final class Probe: UIView {
        var detailsOpen: Binding<Bool>?

        override func willMove(toWindow newWindow: UIWindow?) {
            super.willMove(toWindow: newWindow)
            guard newWindow == nil, let detailsOpen, detailsOpen.wrappedValue else { return }
            let details = window.flatMap { PageDetailsCloser.detailsPopover(in: $0) }
            detailsOpen.wrappedValue = false
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
