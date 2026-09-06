#if os(iOS)
import UIKit

/// The UIKit half of ``LaunchRig``'s `-launch_scroll`: put the page at an
/// offset so the camera can photograph what is below the fold.
///
/// Deliberately generic rather than per-screen. The alternative — a
/// `ScrollViewReader` and a named anchor on each surface we want to shoot — is
/// product code added to a shipping view for a photograph, once per view,
/// forever, and every one of them is a thing that can rot without anybody
/// noticing. Walking for the page's own scroll view costs the app nothing when
/// the argument is absent, and reaches every screen the router can already
/// reach (`LaunchRig.route`) without those screens knowing the rig exists.
///
/// Everything here is `#if os(iOS)`: macOS uses `NSScrollView`, has a resizable
/// window, and can simply be made tall enough to photograph.
enum LaunchRigScroll {

    /// Scroll the page's own scroll view to `points` from the top.
    ///
    /// Returns the offset actually applied, or `nil` where there was no page to
    /// scroll — a screen with no scroll view, or one whose content is shorter
    /// than the screen. Nil is returned rather than silently doing nothing so
    /// the caller can log it: a shoot that scrolled nothing and a shoot that
    /// scrolled to the top produce the same PNG, and only one of them is a bug.
    @MainActor
    @discardableResult
    static func scrollPage(to points: Double) -> Double? {
        guard let scrollView = pageScrollView() else { return nil }

        let contentHeight = Double(
            scrollView.contentSize.height + scrollView.adjustedContentInset.bottom
        )
        let viewportHeight = Double(scrollView.bounds.height)
        let offset = LaunchRig.clampedScrollOffset(
            requested: points,
            contentHeight: contentHeight,
            viewportHeight: viewportHeight
        )
        guard offset > 0 else { return nil }

        // Not animated: the camera fires on a fixed delay, and an in-flight
        // scroll animation photographs a page mid-flight at an offset nobody
        // asked for. #3336's blank-chart lesson in another costume — a shot
        // taken during a transition is evidence of the transition, not the page.
        scrollView.setContentOffset(
            CGPoint(x: scrollView.contentOffset.x, y: CGFloat(offset) - scrollView.adjustedContentInset.top),
            animated: false
        )
        return offset
    }

    /// The scroll view that IS the page.
    ///
    /// An event detail screen holds several: the vertical page plus a
    /// horizontal strip per carousel, and on iOS 18 the `TabView` itself. The
    /// page is the one with the most VERTICAL room left to travel, which is a
    /// property of the thing we want rather than of where it happens to sit in
    /// the hierarchy — so it survives the next view being wrapped in one more
    /// container. A carousel scores ~0 here (it is as tall as its content) and
    /// can never win.
    @MainActor
    private static func pageScrollView() -> UIScrollView? {
        guard let window = keyWindow() else { return nil }
        var best: (view: UIScrollView, travel: CGFloat)?
        for scrollView in descendantScrollViews(of: window) {
            let travel = scrollView.contentSize.height - scrollView.bounds.height
            guard travel > 1 else { continue }
            if best == nil || travel > best!.travel {
                best = (scrollView, travel)
            }
        }
        return best?.view
    }

    @MainActor
    private static func descendantScrollViews(of view: UIView) -> [UIScrollView] {
        var found: [UIScrollView] = []
        if let scrollView = view as? UIScrollView { found.append(scrollView) }
        for subview in view.subviews {
            found.append(contentsOf: descendantScrollViews(of: subview))
        }
        return found
    }

    /// Gotcha #27 — Stage Manager can hand back a background scene, so the
    /// window has to be filtered for a foreground-active one rather than taken
    /// from `windows.first`.
    @MainActor
    private static func keyWindow() -> UIWindow? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .filter { $0.activationState == .foregroundActive }
            .flatMap(\.windows)
            .first(where: \.isKeyWindow)
    }
}
#endif
