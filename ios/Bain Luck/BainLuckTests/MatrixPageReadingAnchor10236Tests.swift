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
    private static let shift: CGFloat = -22.333
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
            host = UIHostingController(rootView: view)
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
