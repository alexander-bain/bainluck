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
/// after the push (draft PRs #11788, #11791) and turns the page's own state
/// off then. Dismissing from UIKit instead is not enough: a dismissal started
/// there waits behind the push, and while the state still reads open SwiftUI
/// presents the popover again (#11791).
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
            print("DIAG11703S pageWillMove t=\(CACurrentMediaTime()) toWindow=\(newWindow != nil) open=\(detailsOpen?.wrappedValue ?? false) rootPresented=\(window?.rootViewController?.presentedViewController.map { String(describing: ObjectIdentifier($0)) } ?? "nil")")
            guard newWindow == nil, let detailsOpen, detailsOpen.wrappedValue else { return }
            detailsOpen.wrappedValue = false
            print("DIAG11703S flipped t=\(CACurrentMediaTime()) open=\(detailsOpen.wrappedValue)")
        }
    }
}
#endif
