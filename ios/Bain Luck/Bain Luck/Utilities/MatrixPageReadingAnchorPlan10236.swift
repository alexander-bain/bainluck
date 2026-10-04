import Foundation

/// Which matrix the opened question came from.
nonisolated enum MatrixPageReadingAnchorHost10236: String, Equatable, Sendable {
    case during
    case after
}

/// Where the token is in the sheet's lifecycle. Both phases may reconcile; a
/// cleared or cancelled token is `nil`, not a third phase.
nonisolated enum MatrixPageReadingAnchorPhase10236: Equatable, Sendable {
    /// Captured synchronously before the sheet opened.
    case held
    /// The sheet's actual `onDismiss` has fired.
    case postDismissal
}

/// The marker's position, both values in the vertical page scroll's content
/// coordinate space.
nonisolated struct MatrixPageReadingAnchorMarkerGeometry10236: Equatable, Sendable {
    /// The marker's minY in the page scroll's content coordinates.
    let contentY: Double
    /// The page scroll's `bounds.minY` at the same instant.
    let boundsMinY: Double

    init(contentY: Double, boundsMinY: Double) {
        self.contentY = contentY
        self.boundsMinY = boundsMinY
    }

    /// Distance from the top of the visible page to the marker.
    var viewportY: Double { contentY - boundsMinY }

    var isFinite: Bool { contentY.isFinite && boundsMinY.isFinite }
}

/// The page scroll's state at reconcile time.
nonisolated struct MatrixPageReadingAnchorScrollGeometry10236: Equatable, Sendable {
    let offsetX: Double
    let offsetY: Double
    let contentHeight: Double
    let viewportHeight: Double
    let adjustedTopInset: Double
    let adjustedBottomInset: Double
    /// Physical pixels per point, supplied by Native's bridge; one pixel is
    /// `1 / screenScale` points.
    let screenScale: Double

    init(offsetX: Double, offsetY: Double, contentHeight: Double, viewportHeight: Double,
         adjustedTopInset: Double, adjustedBottomInset: Double, screenScale: Double) {
        self.offsetX = offsetX
        self.offsetY = offsetY
        self.contentHeight = contentHeight
        self.viewportHeight = viewportHeight
        self.adjustedTopInset = adjustedTopInset
        self.adjustedBottomInset = adjustedBottomInset
        self.screenScale = screenScale
    }

    /// Every input finite, a positive scale, and physical heights: a page with
    /// no visible height or negative content has no position to restore.
    var isUsable: Bool {
        [offsetX, offsetY, contentHeight, viewportHeight, adjustedTopInset, adjustedBottomInset, screenScale]
            .allSatisfy(\.isFinite) && screenScale > 0 && viewportHeight > 0 && contentHeight >= 0
    }

    var minOffsetY: Double { -adjustedTopInset }
    /// The deepest offset the content reaches before `maxOffsetY` floors it at
    /// `minOffsetY`. Finite inputs can still overflow here, and the floor would
    /// hide a `-infinity`, so the planner checks this value itself.
    var contentExtentY: Double { contentHeight - viewportHeight + adjustedBottomInset }
    var maxOffsetY: Double { max(minOffsetY, contentExtentY) }
}

/// What the page looked like when the reader opened the question.
nonisolated struct MatrixPageReadingAnchorToken10236: Equatable, Sendable {
    let eventID: Int
    let host: MatrixPageReadingAnchorHost10236
    let markerInstanceID: UUID
    let presentationGeneration: Int
    let viewportY: Double
    let phase: MatrixPageReadingAnchorPhase10236

    /// The same token after the sheet's actual `onDismiss`. Identity and
    /// `viewportY` are carried over unchanged.
    func dismissed() -> MatrixPageReadingAnchorToken10236 {
        MatrixPageReadingAnchorToken10236(
            eventID: eventID, host: host, markerInstanceID: markerInstanceID,
            presentationGeneration: presentationGeneration, viewportY: viewportY,
            phase: .postDismissal)
    }
}

/// Why the page is NOT the one that was captured. Each of these ends the token;
/// none of them produces a scroll.
nonisolated enum MatrixPageReadingAnchorPageCondition10236: Equatable, Sendable {
    case intact
    case detached
    case inactive
    case routeChanged
    /// The reader dragged the page vertically after capture.
    case verticalDrag
}

/// One reconcile-time reading, supplied by Native.
nonisolated struct MatrixPageReadingAnchorMeasurement10236: Equatable, Sendable {
    let eventID: Int
    let host: MatrixPageReadingAnchorHost10236
    let markerInstanceID: UUID
    let presentationGeneration: Int
    let condition: MatrixPageReadingAnchorPageCondition10236
    let marker: MatrixPageReadingAnchorMarkerGeometry10236
    let scroll: MatrixPageReadingAnchorScrollGeometry10236

    init(eventID: Int, host: MatrixPageReadingAnchorHost10236, markerInstanceID: UUID,
         presentationGeneration: Int, condition: MatrixPageReadingAnchorPageCondition10236 = .intact,
         marker: MatrixPageReadingAnchorMarkerGeometry10236,
         scroll: MatrixPageReadingAnchorScrollGeometry10236) {
        self.eventID = eventID
        self.host = host
        self.markerInstanceID = markerInstanceID
        self.presentationGeneration = presentationGeneration
        self.condition = condition
        self.marker = marker
        self.scroll = scroll
    }
}

nonisolated struct MatrixPageReadingAnchorOffset10236: Equatable, Sendable {
    let x: Double
    let y: Double
}

nonisolated enum MatrixPageReadingAnchorInvalidation10236: Equatable, Sendable {
    case noToken
    case unavailable
    case detached
    case inactive
    case routeChanged
    case verticalDrag
    case eventMismatch
    case hostMismatch
    case markerMismatch
    case staleGeneration
    case nonFiniteGeometry
}

nonisolated enum MatrixPageReadingAnchorHold10236: Equatable, Sendable {
    /// The marker is back where it was, to within one physical pixel.
    case restored
    /// The page is already at the limit the restore needs to pass; stop.
    case clampedAtLimit
}

nonisolated enum MatrixPageReadingAnchorDecision10236: Equatable, Sendable {
    case move(to: MatrixPageReadingAnchorOffset10236)
    case hold(MatrixPageReadingAnchorHold10236)
    case invalidate(MatrixPageReadingAnchorInvalidation10236)
}

/// #10236 — Close puts the reader back on the same visible player question
/// while scores and prices keep updating above it.
///
/// This file holds only the restore decision and the rules for when a captured
/// position is still valid. It is pure value logic over `Double` geometry: no
/// UIKit, no SwiftUI, no clock, no observed state. It does not choose the scroll
/// container, schedule anything, read a date, watch a model, scroll a view, or
/// touch a source, price or focus. Native's bridge supplies the geometry of the
/// nearest enclosing VERTICAL page scroll, measured from a local marker that
/// sits outside the matrix's horizontal scrolls, and applies whatever offset this
/// returns.
///
/// ## What is remembered
///
/// The marker's distance from the top of the visible page, `viewportY =
/// contentY - boundsMinY` — where it sat on screen when the reader tapped. Not
/// the absolute content offset (a header that grows while the sheet is open
/// makes the old offset show different rows), not the content position alone
/// (that moves with the header and carries no information about the screen), and
/// not a row index, question key or price (the matrix can reorder or reprice
/// underneath).
///
/// ## Why the captured value never moves
///
/// `viewportY` is fixed at capture. A reconcile measures where the marker sits
/// NOW and proposes moving the page by the difference. Once the page has actually
/// moved, the next measurement equals the captured value and the answer is "hold".
/// If a clamp stops the page short, the answer is also "hold" — the token is
/// never rebased to the drift it observed, and the planner never chases a
/// position the page cannot reach.
///
/// ## Adoption (Native owns the call sites)
///
/// ```swift
/// // synchronously, before the sheet opens
/// anchor = MatrixPageReadingAnchorPlan10236.capture(
///     eventID: eventId, host: .during, markerInstanceID: markerID,
///     presentationGeneration: generation,
///     marker: .init(contentY: markerMinYInContent, boundsMinY: scroll.bounds.minY))
/// // the sheet's actual onDismiss
/// anchor = anchor?.dismissed()
/// // the unavailable callback: cancel before the deferred false
/// anchor = nil
/// // ONE generation-guarded reconcile after dismissal, then clear
/// switch MatrixPageReadingAnchorPlan10236.reconcile(anchor, measurement) {
/// case .move(let to): scroll.setContentOffset(CGPoint(x: to.x, y: to.y), animated: false)
/// case .hold, .invalidate: break
/// }
/// anchor = nil
/// ```
nonisolated enum MatrixPageReadingAnchorPlan10236 {
    /// A held token, or `nil` when the marker geometry is not finite.
    static func capture(eventID: Int, host: MatrixPageReadingAnchorHost10236, markerInstanceID: UUID,
                        presentationGeneration: Int,
                        marker: MatrixPageReadingAnchorMarkerGeometry10236) -> MatrixPageReadingAnchorToken10236? {
        guard marker.isFinite, marker.viewportY.isFinite else { return nil }
        return MatrixPageReadingAnchorToken10236(
            eventID: eventID, host: host, markerInstanceID: markerInstanceID,
            presentationGeneration: presentationGeneration, viewportY: marker.viewportY, phase: .held)
    }

    /// `measurement == nil` is the unavailable callback: no page to measure.
    static func reconcile(_ token: MatrixPageReadingAnchorToken10236?,
                          _ measurement: MatrixPageReadingAnchorMeasurement10236?) -> MatrixPageReadingAnchorDecision10236 {
        guard let token else { return .invalidate(.noToken) }
        guard let measurement else { return .invalidate(.unavailable) }
        switch measurement.condition {
        case .intact: break
        case .detached: return .invalidate(.detached)
        case .inactive: return .invalidate(.inactive)
        case .routeChanged: return .invalidate(.routeChanged)
        case .verticalDrag: return .invalidate(.verticalDrag)
        }
        guard measurement.eventID == token.eventID else { return .invalidate(.eventMismatch) }
        guard measurement.host == token.host else { return .invalidate(.hostMismatch) }
        guard measurement.markerInstanceID == token.markerInstanceID else { return .invalidate(.markerMismatch) }
        guard measurement.presentationGeneration == token.presentationGeneration else {
            return .invalidate(.staleGeneration)
        }
        let scroll = measurement.scroll
        let delta = measurement.marker.viewportY - token.viewportY
        guard measurement.marker.isFinite, scroll.isUsable, token.viewportY.isFinite, delta.isFinite else {
            return .invalidate(.nonFiniteGeometry)
        }

        // Finite inputs do not make finite derived values: the bounds, the
        // proposed offset and the pixel can each overflow. Refuse before any
        // hold, clamp or move reads them.
        let pixel = 1 / scroll.screenScale
        let lowerY = scroll.minOffsetY
        let upperY = scroll.maxOffsetY
        let proposedY = scroll.offsetY + delta
        guard pixel.isFinite, lowerY.isFinite, scroll.contentExtentY.isFinite, upperY.isFinite,
              proposedY.isFinite else {
            return .invalidate(.nonFiniteGeometry)
        }

        if abs(delta) < pixel { return .hold(.restored) }
        let destinationY = min(max(proposedY, lowerY), upperY)
        let travelY = destinationY - scroll.offsetY
        guard destinationY.isFinite, travelY.isFinite else { return .invalidate(.nonFiniteGeometry) }
        if abs(travelY) < pixel { return .hold(.clampedAtLimit) }
        return .move(to: MatrixPageReadingAnchorOffset10236(x: scroll.offsetX, y: destinationY))
    }
}
