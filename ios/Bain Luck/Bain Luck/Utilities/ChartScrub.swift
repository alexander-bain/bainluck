import CoreGraphics
import Foundation

/// Which drags on a chart are a crosshair scrub, and which belong to the page's
/// scroll (#6705).
///
/// ## Why this type exists, stated from measurement rather than from taste
///
/// `EvolutionChartView` drew its crosshair from a full-bleed `Color.clear`
/// overlay carrying `.gesture(DragGesture(minimumDistance: 0))`. That gesture
/// starved the enclosing `ScrollView` in `FuturesDetailView`: measured by
/// `AReaderCanScrollPastTheChartTests`, an identical 160pt swipe travelled
/// ~330pt started off the chart and **0.0pt** started on it. The chart is 280pt
/// tall at full width, mid-page — about a third of the viewport on a 390×844
/// phone was a region where the page did not scroll.
///
/// **Four SwiftUI compositions were measured and all four failed:**
///
/// | attachment                                          | travel |
/// |-----------------------------------------------------|--------|
/// | `.gesture(DragGesture(minimumDistance: 0))`          | 0.0pt  |
/// | `.simultaneousGesture(DragGesture(minimumDistance: 0))` | 0.0pt |
/// | `.gesture(LongPress.sequenced(before: Drag))`        | 0.0pt  |
/// | `.simultaneousGesture(LongPress.sequenced(before: Drag))` | 0.0pt |
/// | *no gesture at all*                                  | passes |
///
/// `simultaneousGesture` composes a gesture with other SwiftUI gestures; the
/// recognizer being starved is `UIScrollView`'s own pan, which is not in that
/// graph. Sequencing behind a long press does not help either — the recognizer
/// is installed, and installed is enough. Only removing the gesture restored
/// the scroll, and removing it deletes the interaction.
///
/// So the scrub is driven by a UIKit pan recognizer whose delegate answers
/// `shouldRecognizeSimultaneouslyWith: true` (`ChartScrubSurface`). That hands
/// the scroll back unconditionally — and it is precisely what makes THIS type
/// necessary, because now both recognizers fire: without an axis decision a
/// vertical scroll would drag a crosshair down the page with it.
///
/// ## Why the axis is latched and not re-read every frame
///
/// `DiscoverSwipeState` learned this the hard way (#1773): a per-frame axis
/// decision flips mid-gesture, because a drag 30pt across and 28pt down crosses
/// the diagonal repeatedly on the way. One decision per gesture, cleared in
/// `end`, is the only shape that cannot flicker.
///
/// ## Why a stationary touch still tracks
///
/// The crosshair is press-and-hold-to-inspect — the view clears it when the
/// gesture ends, so it only ever exists while a finger is down. If tracking
/// waited for a horizontal latch a reader who pressed and held would get
/// nothing, and that is the chart's primary interaction. A touch that has not
/// moved cannot be a scroll yet, so `tracks` is true while the axis is
/// undecided and goes false the instant the gesture commits to vertical.
struct ChartScrubState: Equatable, Sendable {
    /// Movement, in points, after which a drag's axis is decided.
    ///
    /// Not zero: the first callback of a pan arrives at translation `(0, 0)`,
    /// where `abs(0) > abs(0)` is false, so a zero threshold would latch
    /// VERTICAL on a touch that has not moved — killing press-and-hold inspect
    /// outright. The threshold is what makes the latch a statement about
    /// direction rather than about arrival order.
    ///
    /// 12pt is under `DiscoverSwipeState.minimumDistance` (20) on purpose: the
    /// card swipe can afford to wait because nothing else wants those points,
    /// whereas here every point spent undecided is a point the crosshair may
    /// draw during what turns out to be a scroll.
    static let axisThreshold: CGFloat = 12

    /// True once THIS gesture has decided its axis. Reset in `end`, so it can
    /// never be decided by — or blocked by — a value that outlives the gesture.
    private(set) var axisLatched = false
    private(set) var isHorizontal = false

    /// Whether the crosshair should follow the touch at its current location.
    ///
    /// Undecided counts as tracking (see the type's doc comment): a finger that
    /// has not moved is a press-and-hold inspect, not a scroll.
    var tracks: Bool { !axisLatched || isHorizontal }

    /// Feed one pan update. Returns `tracks` so the caller reads the decision
    /// from the SAME evaluation that made it and cannot drift from it.
    @discardableResult
    mutating func change(width: CGFloat, height: CGFloat) -> Bool {
        if !axisLatched, max(abs(width), abs(height)) >= Self.axisThreshold {
            axisLatched = true
            // Ties go to vertical: on a scrolling page the scroll is the
            // behaviour a reader is entitled to, and a perfectly diagonal drag
            // is far likelier to be a sloppy scroll than a deliberate scrub.
            isHorizontal = abs(width) > abs(height)
        }
        return tracks
    }

    /// Resolve the gesture, clearing the per-gesture latch so the next drag on
    /// the same chart decides its own axis from scratch.
    mutating func end() {
        axisLatched = false
        isHorizontal = false
    }
}
