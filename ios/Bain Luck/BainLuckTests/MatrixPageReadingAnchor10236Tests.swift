import Combine
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10236 — the page half of "Close returns the reader to the same visible
/// player question while scores and prices keep updating".
///
/// The specimen is the retained failing live pass: while the sheet was open a
/// section above the matrix changed height and the header and every row moved
/// together by −22.333 pt. These tests host a REAL SwiftUI `ScrollView` (the
/// marker must find SwiftUI's own backing scroll through its superview chain,
/// not a window scan), shrink a header above the marker by exactly that much,
/// and read where the marker sits on screen.
///
/// Every restore case first proves its own strawman: with no anchor the same
/// change does move the marker by −22.333, so a pass is not a page that never
/// moved.
@MainActor
final class MatrixPageReadingAnchor10236Tests: XCTestCase {
    fileprivate static let shift: CGFloat = -22.333
    private let eventID = 4242

    @MainActor private final class Page: ObservableObject {
        @Published var headerHeight: CGFloat = 600
    }

    private struct PageView: View {
        @ObservedObject var page: Page
        let anchor: MatrixPageReadingAnchor10236?

        var body: some View {
            ScrollView {
                VStack(spacing: 0) {
                    Color.red.frame(height: page.headerHeight)
                    matrix
                    Color.blue.frame(height: 2000)
                }
            }
        }

        @ViewBuilder private var matrix: some View {
            // A horizontal scroll INSIDE the matrix, as in the real one: the
            // marker on the matrix root must skip past it to the page.
            let content = ScrollView(.horizontal) { Color.green.frame(width: 900, height: 200) }
                .frame(height: 200)
            if let anchor {
                content.background(MatrixPageReadingAnchorMarker10236(anchor: anchor))
            } else {
                content.background(ProbeMarker())
            }
        }
    }

    /// The strawman's marker: the same view type with no anchor behind it.
    private struct ProbeMarker: UIViewRepresentable {
        func makeUIView(context: Context) -> MatrixPageReadingAnchorMarkerView10236 { .init() }
        func updateUIView(_ uiView: MatrixPageReadingAnchorMarkerView10236, context: Context) {}
    }

    @MainActor private final class Hosted {
        let window: UIWindow
        let previousKeyWindow: UIWindow?
        let host: UIViewController

        init<V: View>(_ view: V) async throws {
            let deadline = CACurrentMediaTime() + 10
            func activeScene() -> UIWindowScene? {
                UIApplication.shared.connectedScenes
                    .compactMap { $0 as? UIWindowScene }
                    .first { $0.activationState == .foregroundActive }
            }
            while activeScene() == nil && CACurrentMediaTime() < deadline {
                try await Task.sleep(nanoseconds: 50_000_000)
            }
            let scene = try XCTUnwrap(activeScene(), "The anchor tests need a foreground-active window scene")
            previousKeyWindow = scene.windows.first { $0.isKeyWindow }
            host = hostForMeasurement(view)
            window = UIWindow(windowScene: scene)
            window.frame = CGRect(x: 0, y: 0, width: 390, height: 800)
            window.rootViewController = host
            window.makeKeyAndVisible()
            layout()
        }

        func layout() {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
        }

        func close() {
            window.isHidden = true
            previousKeyWindow?.makeKey()
        }

        var marker: MatrixPageReadingAnchorMarkerView10236? {
            func find(_ view: UIView) -> MatrixPageReadingAnchorMarkerView10236? {
                if let marker = view as? MatrixPageReadingAnchorMarkerView10236 { return marker }
                for child in view.subviews { if let hit = find(child) { return hit } }
                return nil
            }
            return find(window)
        }
    }

    private func viewportY(_ marker: UIView, _ scroll: UIScrollView) -> CGFloat {
        marker.convert(CGPoint.zero, to: scroll).y - scroll.bounds.minY
    }

    /// A hosted page scrolled so the matrix sits mid-screen.
    private func hostedPage(anchor: MatrixPageReadingAnchor10236?) async throws
        -> (Hosted, Page, MatrixPageReadingAnchorMarkerView10236, UIScrollView) {
        let page = Page()
        let hosted = try await Hosted(PageView(page: page, anchor: anchor))
        let marker = try XCTUnwrap(hosted.marker, "the marker never reached UIKit")
        let scroll = try XCTUnwrap(marker.enclosingPageScroll(), "the marker found no enclosing scroll")
        hosted.layout()
        scroll.setContentOffset(CGPoint(x: scroll.contentOffset.x, y: 300), animated: false)
        hosted.layout()
        return (hosted, page, marker, scroll)
    }

    private func shrinkHeader(_ page: Page, _ hosted: Hosted) async throws {
        page.headerHeight += Self.shift
        try await Task.sleep(nanoseconds: 50_000_000)
        hosted.layout()
    }

    // MARK: - Finding the page

    func testTheMarkerResolvesTheVerticalPageNotTheMatrixsHorizontalScroll() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let (hosted, _, marker, scroll) = try await hostedPage(anchor: anchor)
        defer { hosted.close() }
        XCTAssertGreaterThan(scroll.contentSize.height, scroll.bounds.height,
                             "the resolved scroll must be the tall vertical page")
        XCTAssertLessThanOrEqual(scroll.contentSize.width, scroll.bounds.width + 1,
                                 "the matrix's own 900pt horizontal scroll must be skipped")
        XCTAssertGreaterThan(viewportY(marker, scroll), 0)
    }

    // MARK: - Restore

    func testWithoutAnAnchorTheSameChangeMovesTheMatrixByTheSpecimensShift() async throws {
        let (hosted, page, marker, scroll) = try await hostedPage(anchor: nil)
        defer { hosted.close() }
        let before = viewportY(marker, scroll)
        try await shrinkHeader(page, hosted)
        XCTAssertEqual(viewportY(marker, scroll) - before, Self.shift, accuracy: 0.01)
    }

    func testAHeldAnchorPutsTheMatrixBackWhereTheReaderTappedAndKeepsTheSidewaysOffset() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let (hosted, page, marker, scroll) = try await hostedPage(anchor: anchor)
        defer { hosted.close(); anchor.cancel() }
        let before = viewportY(marker, scroll)
        let offsetBefore = scroll.contentOffset
        anchor.capture(eventID: eventID)
        XCTAssertEqual(anchor.token?.viewportY ?? .nan, Double(before), accuracy: 0.001,
                       "the token holds the on-screen position, not the content position")
        try await shrinkHeader(page, hosted)
        // The held display link may already have corrected during the layout
        // wait; either way one reconcile leaves the page restored.
        anchor.reconcile()
        hosted.layout()
        XCTAssertEqual(scroll.contentOffset.y, offsetBefore.y + Self.shift, accuracy: 0.01,
                       "the page moves by the shift from where it is, not to an old offset")
        XCTAssertEqual(viewportY(marker, scroll), before, accuracy: 0.5)
        XCTAssertEqual(scroll.contentOffset.x, offsetBefore.x)
        XCTAssertEqual(anchor.reconcile(), .hold(.restored), "a restored page must not be moved again")
    }

    func testTheHeldDisplayLinkCorrectsWithoutAnyCallFromThePage() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let (hosted, page, marker, scroll) = try await hostedPage(anchor: anchor)
        defer { hosted.close(); anchor.cancel() }
        let before = viewportY(marker, scroll)
        anchor.capture(eventID: eventID)
        try await shrinkHeader(page, hosted)
        try await Task.sleep(nanoseconds: 400_000_000)
        hosted.layout()
        XCTAssertEqual(viewportY(marker, scroll), before, accuracy: 0.5)
        XCTAssertNotNil(anchor.token, "a held anchor stays until the sheet's onDismiss")
    }

    func testCloseRestoresTheDismissalsOwnLayoutThenLetsThePageGo() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .after)
        let (hosted, page, marker, scroll) = try await hostedPage(anchor: anchor)
        defer { hosted.close(); anchor.cancel() }
        let before = viewportY(marker, scroll)
        anchor.capture(eventID: eventID)
        anchor.finish(eventID: eventID)
        // The dismissal's layout lands after onDismiss.
        try await shrinkHeader(page, hosted)
        try await Task.sleep(nanoseconds: 100_000_000)
        hosted.layout()
        XCTAssertEqual(viewportY(marker, scroll), before, accuracy: 0.5)

        try await Task.sleep(nanoseconds: UInt64((MatrixPageReadingAnchor10236.settleSeconds + 0.2) * 1e9))
        XCTAssertNil(anchor.token, "the page is never pinned after Close")
        let settled = viewportY(marker, scroll)
        try await shrinkHeader(page, hosted)
        try await Task.sleep(nanoseconds: 200_000_000)
        hosted.layout()
        XCTAssertEqual(viewportY(marker, scroll) - settled, Self.shift, accuracy: 0.01,
                       "after the settle a later change scrolls the page like any page")
    }

    // MARK: - Ends without scrolling

    func testTheUnavailableCancelBeforeTheDeferredFalseNeverScrolls() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let (hosted, page, _, scroll) = try await hostedPage(anchor: anchor)
        defer { hosted.close() }
        anchor.capture(eventID: eventID)
        anchor.cancel()
        try await shrinkHeader(page, hosted)
        let offset = scroll.contentOffset
        anchor.finish(eventID: eventID)
        try await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(scroll.contentOffset, offset)
        XCTAssertNil(anchor.token)
    }

    func testCloseForADifferentEventNeverScrolls() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let (hosted, page, _, scroll) = try await hostedPage(anchor: anchor)
        defer { hosted.close() }
        anchor.capture(eventID: eventID)
        try await shrinkHeader(page, hosted)
        let offset = scroll.contentOffset
        anchor.finish(eventID: eventID + 1)
        XCTAssertEqual(scroll.contentOffset, offset)
        XCTAssertNil(anchor.token)
    }

    func testAReplacedMarkerEndsTheTokenWithoutScrolling() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let (hosted, page, marker, scroll) = try await hostedPage(anchor: anchor)
        defer { hosted.close() }
        anchor.capture(eventID: eventID)
        let replacement = MatrixPageReadingAnchorMarkerView10236()
        marker.superview?.addSubview(replacement)
        defer { replacement.removeFromSuperview() }
        anchor.attachForTesting(replacement)
        try await shrinkHeader(page, hosted)
        let offset = scroll.contentOffset
        // The held display link may have ended it during the layout wait.
        if case .invalidate(let why) = anchor.reconcile() {
            XCTAssertTrue([.markerMismatch, .noToken].contains(why), "\(why)")
        } else {
            XCTFail("a token captured on the old marker must never act for the new one")
        }
        XCTAssertEqual(scroll.contentOffset, offset)
        XCTAssertNil(anchor.token)
    }

    // MARK: - A reader's own drag (UIKit rig)
    //
    // The held link samples `isDragging` at 10 Hz, so a short drag can begin and
    // end between two ticks. These pages are plain UIKit so the rig can stand in
    // for the page's pan recognizer and deliver `.began` / `.ended` exactly as
    // UIKit does — set the state, send the actions to every target — between two
    // reconciles, with `isDragging` false throughout.

    /// The page's pan recognizer, delivering to whatever targets were added to it.
    private final class RecordingPan: UIPanGestureRecognizer {
        private(set) var targets: [(target: AnyObject, action: Selector)] = []
        private var delivered: UIGestureRecognizer.State = .possible
        override var state: UIGestureRecognizer.State {
            get { delivered }
            set { delivered = newValue }
        }

        override func addTarget(_ target: Any, action: Selector) {
            super.addTarget(target, action: action)
            targets.append((target as AnyObject, action))
        }

        override func removeTarget(_ target: Any?, action: Selector?) {
            super.removeTarget(target, action: action)
            targets.removeAll { entry in
                (target == nil || entry.target === (target as AnyObject)) && (action == nil || entry.action == action)
            }
        }

        func deliver(_ state: UIGestureRecognizer.State) {
            delivered = state
            for entry in targets { _ = (entry.target as? NSObject)?.perform(entry.action, with: self) }
        }
    }

    private final class OtherTarget: NSObject {
        @objc func panned(_ recognizer: UIGestureRecognizer) {}
    }

    private final class RigScroll: UIScrollView {
        let pan = RecordingPan()
        var coasting = false
        override var panGestureRecognizer: UIPanGestureRecognizer { pan }
        override var isDecelerating: Bool { coasting }
    }

    @MainActor private final class UIKitPage {
        let window: UIWindow
        let previousKeyWindow: UIWindow?
        let scroll = RigScroll(frame: CGRect(x: 0, y: 0, width: 390, height: 800))
        let header = UIView(frame: CGRect(x: 0, y: 0, width: 390, height: 600))
        let marker = MatrixPageReadingAnchorMarkerView10236(frame: CGRect(x: 0, y: 600, width: 390, height: 200))

        init() async throws {
            let deadline = CACurrentMediaTime() + 10
            func activeScene() -> UIWindowScene? {
                UIApplication.shared.connectedScenes
                    .compactMap { $0 as? UIWindowScene }
                    .first { $0.activationState == .foregroundActive }
            }
            while activeScene() == nil && CACurrentMediaTime() < deadline {
                try await Task.sleep(nanoseconds: 50_000_000)
            }
            let scene = try XCTUnwrap(activeScene(), "The anchor tests need a foreground-active window scene")
            previousKeyWindow = scene.windows.first { $0.isKeyWindow }
            let host = UIViewController()
            host.view.addSubview(scroll)
            scroll.addSubview(header)
            scroll.addSubview(marker)
            scroll.contentSize = CGSize(width: 390, height: 2800)
            window = UIWindow(windowScene: scene)
            window.frame = CGRect(x: 0, y: 0, width: 390, height: 800)
            window.rootViewController = host
            window.makeKeyAndVisible()
            scroll.contentInsetAdjustmentBehavior = .never
            scroll.contentInset = .zero
            scroll.setContentOffset(CGPoint(x: 0, y: 300), animated: false)
        }

        /// A section above the matrix changes height by the specimen's shift.
        func shrinkHeader() {
            header.frame.size.height += MatrixPageReadingAnchor10236Tests.shift
            marker.frame.origin.y += MatrixPageReadingAnchor10236Tests.shift
            scroll.contentSize.height += MatrixPageReadingAnchor10236Tests.shift
        }

        func close() {
            window.isHidden = true
            previousKeyWindow?.makeKey()
        }
    }

    private func uikitPage(_ anchor: MatrixPageReadingAnchor10236) async throws -> UIKitPage {
        let page = try await UIKitPage()
        anchor.attachForTesting(page.marker)
        XCTAssertTrue(page.marker.enclosingPageScroll() === page.scroll)
        return page
    }

    /// The reader's drag lands the page here, between two ticks.
    private let draggedTo: CGFloat = 520

    func testWithoutThePanSignalADragLandedBetweenTicksReadsAsLayoutDrift() async throws {
        // The strawman for the guard below: `isDragging` is false at every tick,
        // so polling alone cannot tell the reader's drag from a reflow and puts
        // the page back where the reader left it.
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let page = try await uikitPage(anchor)
        defer { page.close(); anchor.cancel() }
        anchor.capture(eventID: eventID)
        XCTAssertNotNil(anchor.token)
        XCTAssertFalse(page.scroll.isDragging)
        page.scroll.setContentOffset(CGPoint(x: 0, y: draggedTo), animated: false)
        page.shrinkHeader()
        anchor.reconcile()
        XCTAssertNotEqual(page.scroll.contentOffset.y, draggedTo, accuracy: 1,
                          "without the pan signal the drag is undone — the gap this guards")
    }

    func testAShortDragBetweenTicksEndsTheAnchorAtBeganAndIsNeverUndone() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let page = try await uikitPage(anchor)
        defer { page.close(); anchor.cancel() }
        anchor.capture(eventID: eventID)
        XCTAssertNotNil(anchor.token)

        page.scroll.pan.deliver(.began)
        XCTAssertNil(anchor.token, "the drag ends the anchor synchronously at .began, not at the next tick")
        page.scroll.setContentOffset(CGPoint(x: 0, y: draggedTo), animated: false)
        page.scroll.pan.deliver(.ended)
        XCTAssertFalse(page.scroll.isDragging)

        page.shrinkHeader()
        XCTAssertEqual(anchor.reconcile(), .invalidate(.noToken))
        anchor.finish(eventID: eventID)
        try await Task.sleep(nanoseconds: UInt64((MatrixPageReadingAnchor10236.settleSeconds + 0.1) * 1e9))
        XCTAssertEqual(page.scroll.contentOffset.y, draggedTo, "the reader's drag is never scrolled back")
        XCTAssertNil(anchor.token)
    }

    func testAShortDragDuringThePostCloseSettleIsNeverUndone() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .after)
        let page = try await uikitPage(anchor)
        defer { page.close(); anchor.cancel() }
        anchor.capture(eventID: eventID)
        anchor.finish(eventID: eventID)
        XCTAssertNotNil(anchor.token, "the settle is running")

        page.scroll.pan.deliver(.began)
        XCTAssertNil(anchor.token)
        page.scroll.setContentOffset(CGPoint(x: 0, y: draggedTo), animated: false)
        page.scroll.pan.deliver(.ended)
        page.shrinkHeader()
        try await Task.sleep(nanoseconds: UInt64((MatrixPageReadingAnchor10236.settleSeconds + 0.1) * 1e9))
        XCTAssertEqual(page.scroll.contentOffset.y, draggedTo)
    }

    func testTheAnchorAddsAndRemovesOnlyItsOwnPanTarget() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let page = try await uikitPage(anchor)
        defer { page.close(); anchor.cancel() }
        let other = OtherTarget()
        page.scroll.pan.addTarget(other, action: #selector(OtherTarget.panned(_:)))
        XCTAssertEqual(page.scroll.pan.targets.count, 1)

        anchor.capture(eventID: eventID)
        XCTAssertEqual(page.scroll.pan.targets.count, 2, "capture listens on the page's own pan recognizer")
        anchor.cancel()
        XCTAssertEqual(page.scroll.pan.targets.count, 1)
        XCTAssertTrue(page.scroll.pan.targets.first?.target === other, "someone else's target is never removed")

        anchor.capture(eventID: eventID)
        anchor.finish(eventID: eventID)
        try await Task.sleep(nanoseconds: UInt64((MatrixPageReadingAnchor10236.settleSeconds + 0.2) * 1e9))
        XCTAssertNil(anchor.token)
        XCTAssertEqual(page.scroll.pan.targets.count, 1, "the settle's end stops listening too")
    }

    func testAnInertialPageIsNeverCaptured() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let page = try await uikitPage(anchor)
        defer { page.close(); anchor.cancel() }
        page.scroll.coasting = true
        anchor.capture(eventID: eventID)
        XCTAssertNil(anchor.token, "a page still coasting from a flick is the reader moving, not a place to hold")
        XCTAssertTrue(page.scroll.pan.targets.isEmpty)
    }

    func testDecelerationWhileHeldEndsTheAnchorWithoutScrolling() async throws {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let page = try await uikitPage(anchor)
        defer { page.close(); anchor.cancel() }
        anchor.capture(eventID: eventID)
        page.scroll.coasting = true
        page.scroll.setContentOffset(CGPoint(x: 0, y: draggedTo), animated: false)
        page.shrinkHeader()
        XCTAssertEqual(anchor.reconcile(), .invalidate(.verticalDrag))
        XCTAssertEqual(page.scroll.contentOffset.y, draggedTo)
        XCTAssertNil(anchor.token)
    }

    func testAMarkerOutsideAnyWindowCapturesNothing() {
        let anchor = MatrixPageReadingAnchor10236(host: .during)
        let scroll = UIScrollView(frame: CGRect(x: 0, y: 0, width: 390, height: 800))
        let marker = MatrixPageReadingAnchorMarkerView10236(frame: CGRect(x: 0, y: 900, width: 390, height: 200))
        scroll.addSubview(marker)
        anchor.attachForTesting(marker)
        anchor.capture(eventID: eventID)
        XCTAssertNil(anchor.token)
    }
}
