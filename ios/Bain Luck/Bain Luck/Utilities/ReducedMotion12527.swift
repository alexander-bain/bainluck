import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

/// #12527 — what an animation becomes when the reader turns on Reduce Motion.
///
/// Apple's rule for the setting: no sliding, springing, scaling or repeating
/// motion; a change may still show as a fade or happen at once. So here a
/// motion animation becomes no animation (the change lands instantly) and a
/// moving transition becomes a fade. With the setting off, every call returns
/// exactly what it was given, so nothing changes for anyone else.
///
/// Three doors, one rule:
/// - `withMotion12527` replaces `withAnimation` in event handlers;
/// - `.motionAnimation12527(_:value:)` replaces `.animation(_:value:)` and reads
///   the view's own `accessibilityReduceMotion`;
/// - `ReducedMotion12527.transition(_:)` wraps a moving transition.
enum ReducedMotion12527 {
    /// The setting as the system holds it right now. Read at the moment of each
    /// change, so flipping it in Settings applies to the next one.
    static var isOn: Bool {
        #if canImport(UIKit)
        UIAccessibility.isReduceMotionEnabled
        #elseif canImport(AppKit)
        NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
        #else
        false
        #endif
    }

    /// The animation to run: `animation` itself, or none when motion is reduced.
    nonisolated static func motion(_ animation: Animation?, reduced: Bool) -> Animation? {
        reduced ? nil : animation
    }

    /// The transition to run: `transition` itself, or a fade when motion is reduced.
    nonisolated static func transition(_ transition: AnyTransition, reduced: Bool) -> AnyTransition {
        reduced ? .opacity : transition
    }

    static func transition(_ transition: AnyTransition) -> AnyTransition {
        Self.transition(transition, reduced: isOn)
    }
}

/// `withAnimation` that honours Reduce Motion: with the setting on, `body`
/// runs without an animation.
@discardableResult
func withMotion12527<Result>(_ animation: Animation? = .default,
                             _ body: () throws -> Result) rethrows -> Result {
    try withAnimation(ReducedMotion12527.motion(animation, reduced: ReducedMotion12527.isOn), body)
}

private struct MotionAnimation12527<Value: Equatable>: ViewModifier {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let animation: Animation?
    let value: Value

    func body(content: Content) -> some View {
        content.animation(ReducedMotion12527.motion(animation, reduced: reduceMotion), value: value)
    }
}

extension View {
    /// `.animation(_:value:)` that honours Reduce Motion.
    func motionAnimation12527<Value: Equatable>(_ animation: Animation?, value: Value) -> some View {
        modifier(MotionAnimation12527(animation: animation, value: value))
    }
}
