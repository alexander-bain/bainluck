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
/// after the push (draft PRs #11788, #11791) and, in that same turn, does two
/// things. Either alone fails: a dismissal from UIKit closes the popover, but
/// while the state still reads open SwiftUI presents it again (#11791); the
/// state alone reaches SwiftUI late, and the popover was still up at 2 s
/// (#11790, a7e27b92). So it closes the popover the way a tap outside would —
/// the popover goes, then its delegate hears the dismissal so SwiftUI knows it
/// is gone — and turns the page's state off, so SwiftUI has nothing to present
/// again. It never tries a second time: on #11791 a retry's extra dismissal
/// reached the root and closed the next game's details.
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
            print("DIAG11703S pageWillMove t=\(CACurrentMediaTime()) toWindow=\(newWindow != nil) open=\(detailsOpen?.wrappedValue ?? false) rootPresented=\(window?.rootViewController?.presentedViewController.map { String(describing: ObjectIdentifier($0)) } ?? "nil") found=\(window.flatMap { PageDetailsCloser.detailsPopover(in: $0) }.map { String(describing: ObjectIdentifier($0)) } ?? "nil")")
            guard newWindow == nil, let detailsOpen, detailsOpen.wrappedValue else { return }
            if let window, let details = PageDetailsCloser.detailsPopover(in: window) {
                PageDetailsCloser.close(details)
                print("DIAG11703L afterSyncClose t=\(CACurrentMediaTime()) beingDismissed=\(details.isBeingDismissed) presenter=\(details.presentingViewController != nil)")
            }
            detailsOpen.wrappedValue = false
            print("DIAG11703S flipped t=\(CACurrentMediaTime()) open=\(detailsOpen.wrappedValue)")
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
        print("DIAG11703L dismiss t=\(CACurrentMediaTime()) popover=\(String(describing: ObjectIdentifier(popover))) delegate=\(presentation?.delegate.map { String(describing: type(of: $0)) } ?? "nil")")
        popover.dismiss(animated: false) {
            if let presentation {
                presentation.delegate?.presentationControllerDidDismiss?(presentation)
            }
            print("DIAG11703L dismissed t=\(CACurrentMediaTime())")
        }
    }
}
#endif
