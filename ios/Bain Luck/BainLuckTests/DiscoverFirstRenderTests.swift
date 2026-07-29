import XCTest
@testable import Bain_Luck

/// L2-206 / #1472 Item 3 — the on-screen first-render milestone is emitted once
/// per load, only after a load has started, and is a real elapsed measurement —
/// never a stand-in for model assignment (data-ready). Testing the pure decision
/// core proves the once-only + ordering contract without a running SwiftUI view.
final class DiscoverFirstRenderTests: XCTestCase {

    private let start = ISO8601DateFormatter().date(from: "2026-07-28T12:00:00Z")!

    func testEmitsElapsedMsOnFirstEligibleRender() {
        let now = start.addingTimeInterval(0.25) // 250ms after load start
        let ms = DiscoverFirstRender.elapsedMsIfShouldEmit(emitted: false, loadStartedAt: start, now: now)
        XCTAssertEqual(try XCTUnwrap(ms), 250, accuracy: 0.001, "first render reports the real elapsed time")
    }

    func testDoesNotEmitTwiceForTheSameLoad() {
        // Already emitted → nil, so the view never double-counts a first render.
        XCTAssertNil(DiscoverFirstRender.elapsedMsIfShouldEmit(
            emitted: true, loadStartedAt: start, now: start.addingTimeInterval(1)))
    }

    func testDoesNotEmitWithoutALoadStart() {
        // No load-start anchor → nil. This is the guard that prevents a "first
        // render" from being reported at model assignment (there is no window open).
        XCTAssertNil(DiscoverFirstRender.elapsedMsIfShouldEmit(
            emitted: false, loadStartedAt: nil, now: start))
    }

    func testClampsNegativeElapsedToZero() {
        // Defensive against clock skew: a render "before" the stamped start reports
        // 0, never a negative latency.
        let ms = DiscoverFirstRender.elapsedMsIfShouldEmit(
            emitted: false, loadStartedAt: start, now: start.addingTimeInterval(-5))
        XCTAssertEqual(try XCTUnwrap(ms), 0)
    }
}
