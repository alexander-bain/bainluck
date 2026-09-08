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
    private func marker(width: CGFloat, height: CGFloat) -> some View {
        Color(red: 1, green: 0, blue: 0).frame(width: width, height: height)
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
    /// The tempting one-liner for the test above is `.frame(height:)` instead
    /// of `.frame(minHeight:)`. It centres the short case identically and
    /// clips the tall case into a box that cannot be scrolled — so a phone at
    /// large Dynamic Type would lose the answer buttons off the bottom while
    /// the screenshot of the ordinary case looked perfect.
    func testTallContentStartsAtTheTopAndIsNotCentredIntoAClip() {
        let image = render(
            CenteredPageContent { marker(width: 200, height: 900) },
            width: 402, height: 600
        )
        guard let ink = inkBounds(in: image) else {
            return XCTFail("the marker did not render at all")
        }
        XCTAssertLessThan(
            ink.minY, 4,
            "900pt of content in a 600pt viewport must begin at the top "
            + "(measured \(Int(ink.minY))pt down); anything else means it was "
            + "centred, and centring tall content scrolls its head off screen"
        )
        XCTAssertGreaterThan(
            ink.maxY, 590,
            "the content must fill the viewport and continue past it"
        )
    }

    // MARK: - The width cap

    /// The cap binds, and what it caps stays horizontally centred.
    func testWideContentIsCappedAndCentred() {
        let image = render(
            CenteredPageContent(maxContentWidth: 560) {
                marker(width: 200, height: 100).frame(maxWidth: .infinity)
            },
            width: 834, height: 600
        )
        guard let ink = inkBounds(in: image) else {
            return XCTFail("the marker did not render at all")
        }
        XCTAssertEqual(
            ink.midX, 417, accuracy: 3,
            "the capped column must sit in the middle of the 834pt page"
        )
        XCTAssertLessThan(
            ink.maxX - ink.minX, 570,
            "the marker expanded past the 560pt cap"
        )
    }

    /// With no cap the content still fills the width — the default must not
    /// quietly narrow a caller that did not ask for a column.
    func testTheDefaultAppliesNoWidthCap() {
        let image = render(
            CenteredPageContent {
                marker(width: 200, height: 100).frame(maxWidth: .infinity)
            },
            width: 834, height: 600
        )
        guard let ink = inkBounds(in: image) else {
            return XCTFail("the marker did not render at all")
        }
        XCTAssertGreaterThan(ink.maxX - ink.minX, 800)
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
