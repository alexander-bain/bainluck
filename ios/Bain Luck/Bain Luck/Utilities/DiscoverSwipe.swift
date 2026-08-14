import Foundation

/// What a completed horizontal drag on a Discover card resolved to.
enum DiscoverSwipeOutcome: Equatable, Sendable {
    case none
    case left
    case right
}

/// Pure, testable state machine behind `SwipeToDismiss` (#1773).
///
/// Extracted from the view so the two defects it carried are provable without a
/// device — the sandbox cannot compile Swift, so the logic that can be unit
/// tested must not live inside a `View` body.
///
///  1. **The axis latch keyed on `offset == 0`.** The old guard decided "is this
///     drag horizontal?" only while `offset` was exactly zero:
///     `if !isHorizontalDrag && offset == 0 { … }`. A card whose `offset` was
///     non-zero could therefore never latch horizontal, so `offset = v.translation.width`
///     never ran and the card ignored every subsequent swipe — silently, with no
///     visual feedback at all. That is exactly the state a card is LEFT IN by (2).
///
///  2. **No reset after a commit.** The commit branch set `offset = 400` and
///     `removing = true` and never cleared them, on the assumption that the row
///     always disappears. It does not. `DiscoverView.filteredItems` BACKFILLS the
///     least-recently-dismissed cards whenever dismissal would drop the feed below
///     `feedFloor` (8), and pull-to-refresh clears the dismiss store outright — both
///     re-present the same `gi.id`, and `ForEach(id:)` + `.id(gi.id)` mean SwiftUI
///     reuses that row's `@State` rather than rebuilding it. The card came back with
///     `opacity(0)` AND an un-latchable axis: an invisible, permanently dead grid
///     slot that still consumed a full card's height.
///
/// Together those two make "swipe is dead" self-reinforcing: the first successful
/// swipe on a short feed is also the last one that card will ever accept.
struct DiscoverSwipeState: Equatable, Sendable {
    /// Drag distance before the gesture recognizer engages at all.
    static let minimumDistance: CGFloat = 20
    /// Horizontal distance a drag must cover to commit to like/unlike.
    static let commitDistance: CGFloat = 120
    /// Where a committed card flies out to.
    static let exitOffset: CGFloat = 400
    /// Denominator for the drag-out fade.
    static let fadeDistance: CGFloat = 300
    /// Offset past which the "More/Less like this" affordance appears.
    static let overlayRevealDistance: CGFloat = 20

    private(set) var offset: CGFloat = 0
    private(set) var removing = false
    /// True once THIS gesture has decided its axis. Reset in `end`, so it can
    /// never be decided by — or blocked by — a value that outlives the gesture.
    private(set) var axisLatched = false
    private(set) var isHorizontal = false

    /// Card opacity. Clamped at 0: `1 - 400/300` is negative at full exit.
    var opacity: Double {
        removing ? 0 : max(0, 1.0 - Double(abs(offset)) / Double(Self.fadeDistance))
    }

    var overlayOpacity: Double {
        min(Double(abs(offset)) / 150, 1.0)
    }

    var showsOverlay: Bool {
        isHorizontal && abs(offset) > Self.overlayRevealDistance
    }

    /// Leading affordance for a right (like) drag, trailing for a left (unlike).
    var overlayIsLeading: Bool { offset > 0 }

    mutating func change(width: CGFloat, height: CGFloat) {
        if !axisLatched {
            axisLatched = true
            isHorizontal = abs(width) > abs(height)
        }
        if isHorizontal {
            offset = width
        }
    }

    /// Whether a drag ending at `width` would commit. Exposed so the view can
    /// pick its animation curve (fly-out vs spring-back) from the SAME predicate
    /// `end` uses, rather than re-deriving it and drifting.
    func commits(width: CGFloat) -> Bool {
        isHorizontal && abs(width) > Self.commitDistance
    }

    /// Resolve the gesture. Always clears the per-gesture axis latch, whether the
    /// drag committed or sprang back.
    mutating func end(width: CGFloat) -> DiscoverSwipeOutcome {
        let outcome: DiscoverSwipeOutcome
        if commits(width: width) {
            outcome = width > 0 ? .right : .left
            offset = width > 0 ? Self.exitOffset : -Self.exitOffset
            removing = true
        } else {
            outcome = .none
            offset = 0
        }
        axisLatched = false
        isHorizontal = false
        return outcome
    }

    /// Clear the fly-out presentation once the commit callback has run.
    ///
    /// Called unconditionally after the callback, NOT only when the row survives:
    /// if the row really did leave the feed the view is gone and this is a no-op,
    /// and if it did not — backfill or pull-to-refresh — this is the only thing
    /// that makes it visible and swipeable again.
    mutating func settleAfterCommit() {
        offset = 0
        removing = false
        axisLatched = false
        isHorizontal = false
    }
}
