import CoreGraphics
import XCTest
@testable import Bain_Luck

/// #10830 — a map's axis labels never print over each other, at any text size.
///
/// THE PHOTOGRAPH. NFL 14782161 (LV vs NE), AX3 (accessibility extra large),
/// 390 pt iPhone, taken by native while gating #10796 —
/// `artifacts/native-10796-composed-6a4b/margin-map-ax3-collision.png`. The
/// Margin map's axis reads `LV by 18+Tie NE by 23.5+`: the `+` of the left label
/// runs into `Tie`, and `Tie` butts into `NE`.
///
/// THE MEASUREMENT, in points off that frame (@3x): the rail spans
/// x = 29.7 … 372.0, so the row is **342 pt** wide. `LV by 18+` takes ~130 pt,
/// `Tie` ~40 pt, `NE by 23.5+` ~168 pt. The rail is `[-18, 23.5]`, so zero is
/// at 43.4%, i.e. 148 pt. `Tie` centred there spans 128–168 pt. It overlaps the
/// left label (which ends at 130) and leaves no gap before the right one
/// (which starts at 174).
///
/// THE MECHANISM. The mid label was an overlay positioned by a percentage of
/// the rail. `endLabelBandPercent` (20%) only keeps it clear of the ends at
/// the text size that band was measured at.
final class MarketMapAxisLabelFrames10830Tests: XCTestCase {

    private func zeroFraction(min: Double, max: Double) -> CGFloat {
        CGFloat((0 - min) / (max - min))
    }

    private func assertApart(
        _ frames: MarketMapRail.AxisLabelFrames, width: CGFloat,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        var all = [frames.left, frames.right]
        if let mid = frames.mid { all.append(mid) }
        for frame in all {
            XCTAssertGreaterThanOrEqual(frame.minX, 0, "a label starts before the row", file: file, line: line)
            XCTAssertLessThanOrEqual(frame.maxX, width + 0.001, "a label runs past the row", file: file, line: line)
        }
        for i in all.indices {
            for j in all.indices where j > i {
                XCTAssertFalse(
                    all[i].intersects(all[j]),
                    "labels overprint: \(all[i]) and \(all[j])", file: file, line: line
                )
            }
        }
    }

    // MARK: - The photographed card

    func testTheAX3MarginMapMovesTieToItsOwnRowUnderTheTie() {
        let width: CGFloat = 342
        let centre = width * zeroFraction(min: -18, max: 23.5)
        let frames = MarketMapRail.axisLabelFrames(
            width: width,
            left: CGSize(width: 130, height: 24),
            mid: CGSize(width: 40, height: 24),
            right: CGSize(width: 168, height: 24),
            midCentreX: centre
        )
        XCTAssertEqual(frames.left.minY, 0, "the left label keeps the first row")
        XCTAssertEqual(frames.right.minY, 0, "both end labels fit on the first row, so the right one stays")
        XCTAssertEqual(frames.right.maxX, width, "the right label is flush with the rail's end")
        guard let mid = frames.mid else { return XCTFail("Tie is drawn on this rail") }
        XCTAssertGreaterThan(mid.minY, frames.left.maxY, "Tie moves below the end labels instead of printing over them")
        XCTAssertEqual(mid.midX, centre, accuracy: 0.001, "Tie stays under the rail's zero")
        assertApart(frames, width: width)
    }

    // MARK: - Default text: nothing moves

    func testAtDefaultTextAllThreeLabelsShareOneRow() {
        // The same card at default size: about 52 / 18 / 70 pt.
        let width: CGFloat = 342
        let centre = width * zeroFraction(min: -18, max: 23.5)
        let frames = MarketMapRail.axisLabelFrames(
            width: width,
            left: CGSize(width: 52, height: 13),
            mid: CGSize(width: 18, height: 13),
            right: CGSize(width: 70, height: 13),
            midCentreX: centre
        )
        XCTAssertEqual(frames.left.origin, .zero)
        XCTAssertEqual(frames.right, CGRect(x: width - 70, y: 0, width: 70, height: 13))
        XCTAssertEqual(frames.mid, CGRect(x: centre - 9, y: 0, width: 18, height: 13))
        XCTAssertEqual(frames.height, 13, "the row is no taller than before")
    }

    func testAWithheldMidLabelDrawsOnlyTheEnds() {
        let frames = MarketMapRail.axisLabelFrames(
            width: 342,
            left: CGSize(width: 52, height: 13), mid: nil,
            right: CGSize(width: 70, height: 13), midCentreX: nil
        )
        XCTAssertNil(frames.mid)
        XCTAssertEqual(frames.height, 13)
    }

    // MARK: - Ends that cannot share a row

    func testEndLabelsTooWideForOneRowStackWithTheRightOneTrailing() {
        // AX5-sized ends: together they are wider than the row.
        let width: CGFloat = 342
        let frames = MarketMapRail.axisLabelFrames(
            width: width,
            left: CGSize(width: 200, height: 34),
            mid: CGSize(width: 56, height: 34),
            right: CGSize(width: 250, height: 34),
            midCentreX: width / 2
        )
        XCTAssertEqual(frames.right.minY, frames.left.maxY + 2, "the right label takes the next row")
        XCTAssertEqual(frames.right.maxX, width, "and stays on the right")
        assertApart(frames, width: width)
    }

    func testAMidLabelNearAnEndIsKeptInsideTheRow() {
        let frames = MarketMapRail.axisLabelFrames(
            width: 342,
            left: CGSize(width: 130, height: 24),
            mid: CGSize(width: 40, height: 24),
            right: CGSize(width: 168, height: 24),
            midCentreX: 5
        )
        XCTAssertEqual(frames.mid?.minX, 0)
        assertApart(frames, width: 342)
    }

    // MARK: - Every size, every zero

    /// The rule's whole promise, swept: no overlaps and nothing outside the row,
    /// across every label width from default text to AX5 and every zero
    /// position the mid-label rule draws.
    func testNoLabelsOverprintAcrossTextSizesAndZeroPositions() {
        let width: CGFloat = 342
        for scale in stride(from: 1.0, through: 3.6, by: 0.2) {
            let left = CGSize(width: Swift.min(width, 52 * scale), height: 13 * scale)
            let mid = CGSize(width: 18 * scale, height: 13 * scale)
            let right = CGSize(width: Swift.min(width, 70 * scale), height: 13 * scale)
            for percent in stride(from: 20.5, through: 79.5, by: 1.5) {
                let frames = MarketMapRail.axisLabelFrames(
                    width: width, left: left, mid: mid, right: right,
                    midCentreX: width * CGFloat(percent) / 100
                )
                assertApart(frames, width: width)
            }
        }
    }
}
