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

    /// Called for every pan update with the touch location in this view's own
    /// coordinate space, and the translation since the gesture began.
    let onChange: (_ location: CGPoint, _ translation: CGSize) -> Void
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
        return view
    }

    func updateUIView(_ uiView: UIView, context: Context) {
        // The closures are recreated on every SwiftUI update and the
        // coordinator is not, so it has to be re-pointed at the live ones or it
        // keeps calling into the first render's captured state.
        context.coordinator.onChange = onChange
        context.coordinator.onEnd = onEnd
    }

    func makeCoordinator() -> Coordinator { Coordinator(onChange: onChange, onEnd: onEnd) }

    final class Coordinator: NSObject, UIGestureRecognizerDelegate {
        var onChange: (_ location: CGPoint, _ translation: CGSize) -> Void
        var onEnd: () -> Void

        init(
            onChange: @escaping (_ location: CGPoint, _ translation: CGSize) -> Void,
            onEnd: @escaping () -> Void
        ) {
            self.onChange = onChange
            self.onEnd = onEnd
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
            case .ended, .cancelled, .failed:
                onEnd()
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
