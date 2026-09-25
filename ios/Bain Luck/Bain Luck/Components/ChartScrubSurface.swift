import SwiftUI

/// A transparent touch surface that reports pan updates **without taking the
/// touch away from an enclosing scroll view** (#6705).
///
/// ## Why this is UIKit and not a `DragGesture`
///
/// Any SwiftUI `DragGesture` attached inside `FuturesDetailView`'s `ScrollView`
/// starves that scroll view's pan. Four compositions were measured on a real
/// simulator by `AReaderCanScrollPastTheChartTests`, against a control swipe of
/// the same length started a few points away:
///
/// * `.gesture(DragGesture(minimumDistance: 0))`                 — 0.0pt travel
/// * `.simultaneousGesture(DragGesture(minimumDistance: 0))`     — 0.0pt travel
/// * `.gesture(LongPress.sequenced(before: Drag))`               — 0.0pt travel
/// * `.simultaneousGesture(LongPress.sequenced(before: Drag))`   — 0.0pt travel
/// * no gesture at all                                            — scrolls
///
/// `simultaneousGesture` composes a gesture with other SwiftUI gestures. The
/// recognizer being starved here is `UIScrollView`'s own pan, which is not in
/// that graph, so the modifier that reads like the fix is not one. Sequencing
/// behind a long press does not help either: the recognizer is installed, and
/// installed is enough.
///
/// `UIGestureRecognizerDelegate` is the layer where "these two may both
/// recognize" can actually be said, and this is the smallest thing that says
/// it. The coordinator answers `gestureRecognizer(_:shouldRecognizeSimultaneouslyWith:)`
/// with `sharesTheTouchWithTheScrollView` — unconditionally true — so the page
/// scrolls no matter what this surface decides to do with the same touch.
///
/// ## The cost that buys, and who pays it
///
/// Both recognizers now fire, so a vertical scroll that begins on the chart
/// produces pan callbacks here too. Left alone that would drag a crosshair down
/// the page with the reader's thumb — which is why `ChartScrubState` exists and
/// why this view reports translation as well as location. This type is the
/// plumbing; the axis decision is that type's, pure and unit-tested.
///
/// ## macOS
///
/// `UIViewRepresentable` is iOS-only, and the conflict it solves is a
/// `UIScrollView` one. On macOS the chart keeps an ordinary `DragGesture`:
/// scrolling there is a trackpad/wheel event that never contended for the
/// touch in the first place. Guarded rather than ported, because a macOS
/// `NSViewRepresentable` written blind is a thing nobody on this lane can
/// photograph.
/// #925 — whether a chart installs its UIKit touch surface. True everywhere a
/// finger can reach; false only for rasters. `ImageRenderer` cannot draw a
/// UIKit-backed view and paints an opaque placeholder in its place — measured:
/// it covered the game chart's time labels in
/// `OneControlOneWindowReadableClock8481Tests` (0 labels found, 47,652 coloured
/// pixels where the plot should be empty). A picture has no finger, so the
/// measurement helper turns this off; nothing in the app does.
private struct ChartScrubSurfacesKey: EnvironmentKey {
    static let defaultValue = true
}

extension EnvironmentValues {
    var chartScrubSurfaces: Bool {
        get { self[ChartScrubSurfacesKey.self] }
        set { self[ChartScrubSurfacesKey.self] = newValue }
    }
}

#if os(iOS)
struct ChartScrubSurface: UIViewRepresentable {
    /// Whether this surface's pan lets the enclosing scroll view recognize the
    /// same touch. **This is the fix**; everything else in this file is
    /// plumbing around it.
    ///
    /// A constant and not a bare `true` in the delegate body so that the fast
    /// test suite can assert the ANSWER and not merely the presence of the
    /// method — see the delegate below for what that cost before it existed.
    static let sharesTheTouchWithTheScrollView = true

    /// #925 — seconds a STILL finger must rest before `onHold` fires. `nil`
    /// (the futures chart) installs no hold recognizer at all.
    ///
    /// Alex's build-20 recording on the game chart: a press-and-drag drew a
    /// crosshair for a moment and then the page moved under his thumb. A thumb
    /// never drags level, and any vertical drift let the page's scroll take the
    /// touch. A press that has rested this long cannot be the start of a
    /// scroll — a scroll moves before it is this old — so from here on the
    /// finger may wander in any direction and stay on the chart.
    static let gameChartHold: TimeInterval = 0.25

    var holdToScrub: TimeInterval? = nil
    /// Called for every pan update with the touch location in this view's own
    /// coordinate space, and the translation since the gesture began.
    let onChange: (_ location: CGPoint, _ translation: CGSize) -> Void
    /// Called when a held press begins and for every move after it (#925),
    /// with the touch location in this view's own coordinate space.
    var onHold: ((_ location: CGPoint) -> Void)? = nil
    /// #925 — asked after every callback: while it answers true the nearest
    /// enclosing scroll view is held still, and it is released the moment it
    /// answers false or the gesture ends. The futures chart never asks (it
    /// defaults false), which keeps #6705's simultaneous scroll exactly as it
    /// was measured.
    var holdsTheScrollStill: () -> Bool = { false }
    /// Called when the gesture ends, cancels, or fails.
    let onEnd: () -> Void

    func makeUIView(context: Context) -> UIView {
        let view = PassthroughView()
        let pan = UIPanGestureRecognizer(
            target: context.coordinator,
            action: #selector(Coordinator.handlePan(_:)))
        pan.delegate = context.coordinator
        // A single finger: a two-finger gesture on this page belongs to the
        // system (zoom, scroll) and is never a scrub.
        pan.minimumNumberOfTouches = 1
        pan.maximumNumberOfTouches = 1
        view.addGestureRecognizer(pan)
        if let holdToScrub {
            context.coordinator.holdsOffTheContentBackSwipe = true
            let hold = UILongPressGestureRecognizer(
                target: context.coordinator,
                action: #selector(Coordinator.handleHold(_:)))
            hold.delegate = context.coordinator
            hold.minimumPressDuration = holdToScrub
            // UIKit's default 10pt: a finger that travels further than this
            // before the hold matures is a drag, and the pan above decides its
            // axis. After it matures the recognizer tracks any distance.
            hold.allowableMovement = 10
            view.addGestureRecognizer(hold)
        }
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        // The closures are recreated on every SwiftUI update and the
        // coordinator is not, so it has to be re-pointed at the live ones or it
        // keeps calling into the first render's captured state.
        context.coordinator.onChange = onChange
        context.coordinator.onHold = onHold
        context.coordinator.holdsTheScrollStill = holdsTheScrollStill
        context.coordinator.onEnd = onEnd
    }

    static func dismantleUIView(_ uiView: UIView, coordinator: Coordinator) {
        // A page popped mid-scrub must not leave its scroll view frozen.
        coordinator.releaseTheScroll()
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(onChange: onChange, onHold: onHold,
                    holdsTheScrollStill: holdsTheScrollStill, onEnd: onEnd)
    }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var onChange: (_ location: CGPoint, _ translation: CGSize) -> Void
        var onHold: ((_ location: CGPoint) -> Void)?
        var holdsTheScrollStill: () -> Bool
        var onEnd: () -> Void
        /// The scroll view this surface is holding still, and what its
        /// `isScrollEnabled` was before — restored, never assumed `true`.
        private weak var frozen: UIScrollView?
        private var frozenWasEnabled = true

        init(
            onChange: @escaping (_ location: CGPoint, _ translation: CGSize) -> Void,
            onHold: ((_ location: CGPoint) -> Void)?,
            holdsTheScrollStill: @escaping () -> Bool,
            onEnd: @escaping () -> Void
        ) {
            self.onChange = onChange
            self.onHold = onHold
            self.holdsTheScrollStill = holdsTheScrollStill
            self.onEnd = onEnd
        }

        /// Freeze or release the enclosing scroll view to match the view's
        /// answer. Disabling a scroll view mid-drag cancels its pan where it
        /// stands; the page does not jump back.
        func syncTheScroll(from view: UIView) {
            if holdsTheScrollStill() {
                guard frozen == nil, let scroll = Self.enclosingScrollView(of: view) else { return }
                frozen = scroll
                frozenWasEnabled = scroll.isScrollEnabled
                scroll.isScrollEnabled = false
            } else {
                releaseTheScroll()
            }
        }

        func releaseTheScroll() {
            frozen?.isScrollEnabled = frozenWasEnabled
            frozen = nil
        }

        static func enclosingScrollView(of view: UIView) -> UIScrollView? {
            var next = view.superview
            while let candidate = next {
                if let scroll = candidate as? UIScrollView { return scroll }
                next = candidate.superview
            }
            return nil
        }

        private func endGesture() {
            releaseTheScroll()
            onEnd()
        }

        /// #925 — set for the game chart (it installs the hold). iOS 26 added a
        /// full-width swipe-back (`interactiveContentPopGestureRecognizer`), and
        /// a quick rightward scrub on the chart started leaving the page —
        /// measured on the simulator, before and after this fix's other half.
        /// A sideways drag that begins on a scrubbable chart is the chart's; the
        /// screen-EDGE back swipe is a different recognizer and is untouched.
        var holdsOffTheContentBackSwipe = false

        func gestureRecognizer(
            _ gestureRecognizer: UIGestureRecognizer,
            shouldBeRequiredToFailBy other: UIGestureRecognizer
        ) -> Bool {
            guard holdsOffTheContentBackSwipe, let view = gestureRecognizer.view else { return false }
            return Self.isContentBackSwipe(other, near: view)
        }

        static func isContentBackSwipe(_ recognizer: UIGestureRecognizer, near view: UIView) -> Bool {
            guard #available(iOS 26.0, *) else { return false }
            var responder: UIResponder? = view
            while let next = responder {
                if let nav = next as? UINavigationController {
                    return recognizer === nav.interactiveContentPopGestureRecognizer
                }
                responder = next.next
            }
            return false
        }

        @objc func handleHold(_ hold: UILongPressGestureRecognizer) {
            guard let view = hold.view else { return }
            switch hold.state {
            case .began, .changed:
                onHold?(hold.location(in: view))
                syncTheScroll(from: view)
            case .ended, .cancelled, .failed:
                endGesture()
            default:
                break
            }
        }

        /// **The whole point of this file.** Without this the pan added above
        /// behaves exactly like the `DragGesture` it replaced.
        ///
        /// Answered from a named constant rather than a bare `true` because a
        /// mutation battery caught this exact line as the one hole in the
        /// guard: a scan can see that `shouldRecognizeSimultaneouslyWith` is
        /// implemented, but not what it answers, so flipping the literal to
        /// `false` reinstated #6705 with every unit test still green. The
        /// constant gives the fast suite something to assert and the scan
        /// something to anchor on.
        func gestureRecognizer(
            _ gestureRecognizer: UIGestureRecognizer,
            shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool {
            ChartScrubSurface.sharesTheTouchWithTheScrollView
        }

        @objc func handlePan(_ pan: UIPanGestureRecognizer) {
            guard let view = pan.view else { return }
            switch pan.state {
            case .began, .changed:
                let translation = pan.translation(in: view)
                onChange(
                    pan.location(in: view),
                    CGSize(width: translation.x, height: translation.y))
                syncTheScroll(from: view)
            case .ended, .cancelled, .failed:
                endGesture()
            default:
                break
            }
        }
    }

    /// Transparent to everything except the pan added above.
    ///
    /// `hitTest` returning the view itself for any point inside it is what
    /// `.contentShape(Rectangle())` did for the SwiftUI overlay — without it a
    /// zero-subview `UIView` with a clear background is still hit-tested, but
    /// this states it rather than relying on it, and it keeps the surface from
    /// swallowing anything it was not asked to handle (it has no other
    /// recognizers and no subviews, so there is nothing to swallow).
    private final class PassthroughView: UIView {
        override init(frame: CGRect) {
            super.init(frame: frame)
            backgroundColor = .clear
            isMultipleTouchEnabled = false
        }

        @available(*, unavailable)
        required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }
    }
}
#endif
