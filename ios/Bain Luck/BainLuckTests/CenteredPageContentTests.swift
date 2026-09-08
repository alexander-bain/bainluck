import XCTest
import SwiftUI
@testable import Bain_Luck

/// #3865 — renders ``CenteredPageContent`` and measures where the ink lands.
///
/// The arithmetic in ``DailyChallengeLayoutTests`` can only guard the widths.
/// The vertical half of this fix is a `minHeight` + `alignment` on a frame,
/// which no pure function models, so it is measured off a raster the way
/// `ChampionshipRowLayoutTests` measures its bars.
@MainActor
final class CenteredPageContentTests: XCTestCase {

    /// Nothing else in these renders is this colour, so any of it is the marker.
    ///
    /// A marker with a fixed `width`, for the VERTICAL tests. Do not use it to
    /// measure a width cap: a fixed-width `Color` inside `.frame(maxWidth:)`
    /// leaves the *container* expanding and the ink 200pt wide either way, so
    /// both cap assertions would pass whatever the cap did. Use
    /// ``expandingMarker(height:)`` there.
    private func marker(width: CGFloat, height: CGFloat) -> some View {
        Color(red: 1, green: 0, blue: 0).frame(width: width, height: height)
    }

    /// A marker that takes every point of width it is offered, so the ink
    /// bounds ARE the width the cap resolved to.
    private func expandingMarker(height: CGFloat) -> some View {
        Color(red: 1, green: 0, blue: 0)
            .frame(height: height)
            .frame(maxWidth: .infinity)
    }

    // MARK: - The defect

    /// Content shorter than the viewport is CENTRED, not pinned to the top.
    ///
    /// This is the bug as photographed: a 100pt block in a 600pt viewport used
    /// to sit at y=0 with 500pt of white under it. It must now sit with the
    /// white split evenly above and below.
    func testShortContentIsCentredRatherThanPinnedToTheTop() {
        let image = render(
            CenteredPageContent { marker(width: 200, height: 100) },
            width: 402, height: 600
        )
        guard let ink = inkBounds(in: image) else {
            return XCTFail("the marker did not render at all")
        }
        let above = ink.minY
        let below = 600 - ink.maxY

        XCTAssertEqual(ink.height, 100, accuracy: 2)
        XCTAssertGreaterThan(
            above, 200,
            "content sat \(Int(above))pt from the top of a 600pt viewport — "
            + "that is the top-pinned layout #3865 is about, not a centred one"
        )
        XCTAssertEqual(
            above, below, accuracy: 2,
            "the leftover space must be split evenly: measured \(Int(above))pt "
            + "above and \(Int(below))pt below"
        )
    }

    // MARK: - The way centring goes wrong

    /// Content TALLER than the viewport must start at the top and scroll.
    ///
    /// The tempting spelling is `.frame(height:)` instead of
    /// `.frame(minHeight:)`. It centres the short case identically, so it
    /// passes the test above; on tall content it centres a 900pt child in a
    /// 600pt box and pushes the child's HEAD 150pt above the viewport, where
    /// the scroll view cannot reach it — a phone at large Dynamic Type would
    /// silently lose the top of the question while the ordinary screenshot
    /// looked perfect.
    ///
    /// A full-height marker cannot see that: both spellings paint red from the
    /// top edge to the bottom edge of the frame, and this test passed against
    /// the broken one until the mutation run caught it. So the marker is only
    /// the top **20pt** of the content, and the assertion is that the head is
    /// still on screen.
    func testTallContentKeepsItsHeadOnScreenRatherThanCentringItOutOfReach() {
        let image = render(
            CenteredPageContent {
                VStack(spacing: 0) {
                    marker(width: 200, height: 20)
                    // Not red, so `inkBounds` ignores it — it is only here to
                    // make the content 900pt tall in a 600pt viewport.
                    Color(red: 0, green: 0, blue: 1).frame(width: 200, height: 880)
                }
            },
            width: 402, height: 600
        )
        guard let ink = inkBounds(in: image) else {
            return XCTFail(
                "the head of the content did not render at all — 900pt of "
                + "content was centred in the 600pt viewport, so its top 150pt "
                + "sits above the scroll view and cannot be reached"
            )
        }
        XCTAssertLessThan(
            ink.minY, 4,
            "the head of 900pt of content in a 600pt viewport must sit at the "
            + "top (measured \(Int(ink.minY))pt down)"
        )
        XCTAssertEqual(
            ink.height, 20, accuracy: 2,
            "the whole 20pt head must be visible, not part of it"
        )
    }

    // MARK: - The width cap

    /// The cap binds, and what it caps stays horizontally centred.
    func testWideContentIsCappedAndCentred() {
        let image = render(
            CenteredPageContent(maxContentWidth: 560) { expandingMarker(height: 100) },
            width: 834, height: 600
        )
        guard let ink = inkBounds(in: image) else {
            return XCTFail("the marker did not render at all")
        }
        XCTAssertEqual(
            ink.width, 560, accuracy: 2,
            "an expanding marker in a 560-capped column drew \(Int(ink.width))pt "
            + "inside an 834pt page — the cap did not bind"
        )
        XCTAssertEqual(
            ink.midX, 417, accuracy: 3,
            "the capped column must sit in the middle of the 834pt page"
        )
    }

    /// With no cap the content still fills the width — the default must not
    /// quietly narrow a caller that did not ask for a column.
    func testTheDefaultAppliesNoWidthCap() {
        let image = render(
            CenteredPageContent { expandingMarker(height: 100) },
            width: 834, height: 600
        )
        guard let ink = inkBounds(in: image) else {
            return XCTFail("the marker did not render at all")
        }
        XCTAssertEqual(
            ink.width, 834, accuracy: 2,
            "the default cap is `.infinity`, so an expanding marker must draw "
            + "the whole 834pt page; it drew \(Int(ink.width))pt"
        )
    }

    // MARK: - Raster helpers

    /// The bounding box of the red marker, in POINTS.
    private func inkBounds(in image: UIImage) -> CGRect? {
        guard let cg = image.cgImage else { return nil }
        let width = cg.width, height = cg.height
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        guard let ctx = CGContext(
            data: &pixels, width: width, height: height, bitsPerComponent: 8,
            bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))

        var minX = width, maxX = -1, minY = height, maxY = -1
        for y in 0..<height {
            for x in 0..<width {
                let i = (y * width + x) * 4
                guard pixels[i] > 180, pixels[i + 1] < 90, pixels[i + 2] < 90 else { continue }
                minX = min(minX, x); maxX = max(maxX, x)
                minY = min(minY, y); maxY = max(maxY, y)
            }
        }
        guard maxY >= 0 else { return nil }
        let s = image.scale
        return CGRect(
            x: CGFloat(minX) / s, y: CGFloat(minY) / s,
            width: CGFloat(maxX - minX + 1) / s, height: CGFloat(maxY - minY + 1) / s
        )
    }

    private func render<V: View>(_ view: V, width: CGFloat, height: CGFloat) -> UIImage {
        let host = UIHostingController(rootView: view.frame(width: width, height: height))
        // The window inherits an ambient safe area from the simulator's screen,
        // and a `ScrollView` turns that into a content inset — measured at 31pt
        // here, which shifted every vertical reading below by the same 31pt and
        // is a fact about this harness, not about the layout under test. The
        // viewport these tests talk about is exactly `width` × `height`.
        host.safeAreaRegions = []
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: height))
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        let bounds = host.view.bounds
        return UIGraphicsImageRenderer(bounds: bounds).image { _ in
            host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }
}
