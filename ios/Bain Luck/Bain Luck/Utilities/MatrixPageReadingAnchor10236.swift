import SwiftUI
#if os(iOS)
import UIKit
#endif

/// #10236 — Close puts the reader back on the same visible player question
/// while scores and prices keep updating above it.
///
/// The matrix already keeps its statistic, question and sideways offset across
/// a detail sheet. What moved in the failing live pass was the PAGE: the header
/// and every row shifted together by −22.333 pt while the sheet was open,
/// because a section above the matrix changed height. This holds the matrix at
/// the distance from the top of the visible page it had when the reader tapped,
/// by moving the page's vertical scroll — never by freezing the model, the score
/// or a price.
///
/// One per matrix host, owned by `EventDetailView`, driven by the matrix's own
/// `onDetailPresentationChanged` callbacks:
///
/// - `capture` on `true`, which fires synchronously BEFORE the sheet opens;
/// - `finish` on `false`, which fires inside the sheet's actual `onDismiss`;
/// - `cancel` from the unavailable callback (which runs before that `false`),
///   on disappear, and when the scene leaves `.active`.
///
/// While held, a low-rate display link re-measures the marker and applies
/// `MatrixPageReadingAnchorPlan10236`'s decision. After `finish` it runs at full
/// rate for `settleSeconds` so the dismissal's own layout is caught, then lets go:
/// the page is never pinned after Close. A vertical drag, a detached or replaced
/// marker, or a different page scroll ends the token without scrolling.
///
/// The marker (`MatrixPageReadingAnchorMarker10236`) sits on the matrix root,
/// outside its horizontal scrolls, and resolves only the first `UIScrollView` in
/// its own superview chain — no window scan, no "largest scroll" pick.
final class MatrixPageReadingAnchor10236 {
    let host: MatrixPageReadingAnchorHost10236
    private(set) var token: MatrixPageReadingAnchorToken10236?
    private var generation = 0

    /// How long after the sheet's `onDismiss` the page keeps reconciling. One
    /// main-queue turn can run before the dismissal's layout commits; a quarter
    /// second covers that commit at any refresh rate and is not a hold.
    static let settleSeconds: CFTimeInterval = 0.25

    init(host: MatrixPageReadingAnchorHost10236) {
        self.host = host
    }

    #if os(iOS)
    fileprivate weak var marker: MatrixPageReadingAnchorMarkerView10236?
    private weak var pageScroll: UIScrollView?
    private var displayLink: CADisplayLink?
    private var settleDeadline: CFTimeInterval?

    fileprivate func attach(_ view: MatrixPageReadingAnchorMarkerView10236) {
        marker = view
    }

    /// Synchronously, before the sheet opens.
    func capture(eventID: Int) {
        cancel()
        generation += 1
        guard let marker, marker.window != nil, let scroll = marker.enclosingPageScroll() else { return }
        token = MatrixPageReadingAnchorPlan10236.capture(
            eventID: eventID, host: host, markerInstanceID: marker.instanceID,
            presentationGeneration: generation, marker: Self.markerGeometry(marker, in: scroll))
        guard token != nil else { return }
        pageScroll = scroll
        startLink(heldRate: true)
    }

    /// The sheet's actual `onDismiss`. A no-op after `cancel`.
    func finish(eventID: Int) {
        guard let held = token, held.eventID == eventID, held.phase == .held else {
            cancel()
            return
        }
        token = held.dismissed()
        reconcile()
        guard token != nil else { return }
        settleDeadline = CACurrentMediaTime() + Self.settleSeconds
        startLink(heldRate: false)
    }

    func cancel() {
        token = nil
        pageScroll = nil
        settleDeadline = nil
        displayLink?.invalidate()
        displayLink = nil
    }

    /// One measurement and, at most, one offset change.
    @discardableResult
    func reconcile() -> MatrixPageReadingAnchorDecision10236 {
        let decision = MatrixPageReadingAnchorPlan10236.reconcile(token, measurement())
        switch decision {
        case .move(let to):
            pageScroll?.setContentOffset(CGPoint(x: to.x, y: to.y), animated: false)
        case .hold:
            break
        case .invalidate:
            cancel()
        }
        return decision
    }

    fileprivate func tick(_ link: CADisplayLink) {
        reconcile()
        if let deadline = settleDeadline, link.timestamp >= deadline { cancel() }
    }

    private func measurement() -> MatrixPageReadingAnchorMeasurement10236? {
        guard let token else { return nil }
        guard let marker, let scroll = pageScroll, marker.window != nil,
              marker.enclosingPageScroll() === scroll else {
            return detached(token)
        }
        let condition: MatrixPageReadingAnchorPageCondition10236
        if scroll.isDragging {
            condition = .verticalDrag
        } else if let scene = marker.window?.windowScene, scene.activationState != .foregroundActive {
            condition = .inactive
        } else {
            condition = .intact
        }
        return MatrixPageReadingAnchorMeasurement10236(
            eventID: token.eventID, host: host, markerInstanceID: marker.instanceID,
            presentationGeneration: generation, condition: condition,
            marker: Self.markerGeometry(marker, in: scroll),
            scroll: MatrixPageReadingAnchorScrollGeometry10236(
                offsetX: scroll.contentOffset.x, offsetY: scroll.contentOffset.y,
                contentHeight: scroll.contentSize.height, viewportHeight: scroll.bounds.height,
                adjustedTopInset: scroll.adjustedContentInset.top,
                adjustedBottomInset: scroll.adjustedContentInset.bottom,
                screenScale: marker.traitCollection.displayScale))
    }

    private func detached(_ token: MatrixPageReadingAnchorToken10236) -> MatrixPageReadingAnchorMeasurement10236 {
        MatrixPageReadingAnchorMeasurement10236(
            eventID: token.eventID, host: host, markerInstanceID: token.markerInstanceID,
            presentationGeneration: generation, condition: .detached,
            marker: .init(contentY: 0, boundsMinY: 0),
            scroll: .init(offsetX: 0, offsetY: 0, contentHeight: 0, viewportHeight: 0,
                          adjustedTopInset: 0, adjustedBottomInset: 0, screenScale: 1))
    }

    /// Content-space Y and the page's `bounds.minY` together: the planner takes
    /// the difference, so the token holds a VIEWPORT position, not a content one.
    private static func markerGeometry(_ marker: UIView, in scroll: UIScrollView) -> MatrixPageReadingAnchorMarkerGeometry10236 {
        MatrixPageReadingAnchorMarkerGeometry10236(
            contentY: marker.convert(CGPoint.zero, to: scroll).y, boundsMinY: scroll.bounds.minY)
    }

    /// Low rate while the sheet covers the page; full rate for the short settle.
    private func startLink(heldRate: Bool) {
        displayLink?.invalidate()
        let link = CADisplayLink(target: DisplayLinkProxy(self), selector: #selector(DisplayLinkProxy.tick(_:)))
        if heldRate {
            link.preferredFrameRateRange = CAFrameRateRange(minimum: 8, maximum: 15, preferred: 10)
        }
        link.add(to: .main, forMode: .common)
        displayLink = link
    }

    /// The link retains its target; the target must not retain the anchor.
    private final class DisplayLinkProxy: NSObject {
        weak var owner: MatrixPageReadingAnchor10236?
        init(_ owner: MatrixPageReadingAnchor10236) { self.owner = owner }
        @objc func tick(_ link: CADisplayLink) {
            guard let owner else { link.invalidate(); return }
            owner.tick(link)
        }
    }

    deinit {
        displayLink?.invalidate()
    }
    #else
    func capture(eventID: Int) {}
    func finish(eventID: Int) {}
    func cancel() {}
    #endif
}

/// Put on a matrix root with `.background`, outside its horizontal scrolls.
struct MatrixPageReadingAnchorMarker10236: View {
    let anchor: MatrixPageReadingAnchor10236

    var body: some View {
        #if os(iOS)
        MarkerRepresentable(anchor: anchor)
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        #else
        Color.clear
        #endif
    }
}

#if os(iOS)
private struct MarkerRepresentable: UIViewRepresentable {
    let anchor: MatrixPageReadingAnchor10236

    func makeUIView(context: Context) -> MatrixPageReadingAnchorMarkerView10236 {
        let view = MatrixPageReadingAnchorMarkerView10236()
        anchor.attach(view)
        return view
    }

    func updateUIView(_ uiView: MatrixPageReadingAnchorMarkerView10236, context: Context) {
        anchor.attach(uiView)
    }
}

/// A transparent view whose only job is to be measured. A new instance is a new
/// marker: a token captured against the old one never scrolls for the new one.
final class MatrixPageReadingAnchorMarkerView10236: UIView {
    let instanceID = UUID()

    override init(frame: CGRect) {
        super.init(frame: frame)
        isUserInteractionEnabled = false
        isAccessibilityElement = false
        backgroundColor = .clear
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { fatalError("init(coder:) is not supported") }

    /// The first `UIScrollView` in this view's own superview chain.
    func enclosingPageScroll() -> UIScrollView? {
        var view = superview
        while let current = view {
            if let scroll = current as? UIScrollView { return scroll }
            view = current.superview
        }
        return nil
    }
}

extension MatrixPageReadingAnchor10236 {
    /// Tests only: attach a marker built outside SwiftUI.
    func attachForTesting(_ view: MatrixPageReadingAnchorMarkerView10236) { attach(view) }
}
#endif
