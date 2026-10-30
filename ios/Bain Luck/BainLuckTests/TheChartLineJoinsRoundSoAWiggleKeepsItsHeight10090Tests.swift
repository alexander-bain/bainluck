import XCTest
import SwiftUI
@testable import Bain_Luck

/// #10090 / #11105 — **the held iPhone chart draws a tiny real reversal at its
/// true height, not as a tall needle.**
///
/// Specimen: build 91's held live tail (latency 2329Z,
/// `artifacts/latency-10090-b91-chart-ticks-20261029/`). The Bain Luck line was
/// `StrokeStyle(lineWidth: 3.0)` — the default MITER join, limit 10. A 0.1–0.6 pt
/// reversal inside 0.4–2 s sits on two vertices a fraction of a point apart, and
/// the miter at that sharp angle points far past the vertex: a spike several
/// times taller than the move. The live tail (`LiveChartEdgeMarker`) already
/// joins round; the plot's own line now does too.
final class TheChartLineJoinsRoundSoAWiggleKeepsItsHeight10090Tests: XCTestCase {

    private func style(_ source: String, isModel: Bool = false, hasAggregate: Bool = true) -> StrokeStyle {
        OddsChartView.strokeStyle(source: source, isModel: isModel, hasAggregate: hasAggregate)
    }

    // MARK: - The pinned styles

    func testTheBainLuckLineJoinsAndCapsRound() {
        let s = style("aggregate")
        XCTAssertEqual(s.lineWidth, 3.0)
        XCTAssertEqual(s.lineJoin, .round, "a miter join draws a small reversal as a needle")
        XCTAssertEqual(s.lineCap, .round, "the line meets the round live tail without a square shoulder")
        XCTAssertTrue(s.dash.isEmpty)
    }

    func testEverySolidLineJoinsAndCapsRound() {
        for (source, width, hasAggregate) in [("consensus", 1.5, true), ("consensus", 2.5, false),
                                              ("kalshi", 1.5, true), ("polymarket", 1.5, true)] {
            let s = style(source, hasAggregate: hasAggregate)
            XCTAssertEqual(s.lineWidth, CGFloat(width), source)
            XCTAssertEqual(s.lineJoin, .round, source)
            XCTAssertEqual(s.lineCap, .round, source)
            XCTAssertTrue(s.dash.isEmpty, source)
        }
    }

    /// A round cap would lengthen every 5 pt dash by the line's width and close
    /// the 3 pt gaps the legend swatch (butt caps) still draws.
    func testAModelLineJoinsRoundButKeepsItsDashRhythm() {
        let s = style("espn", isModel: true)
        XCTAssertEqual(s.lineWidth, 1.5)
        XCTAssertEqual(s.lineJoin, .round)
        XCTAssertEqual(s.lineCap, .butt)
        XCTAssertEqual(s.dash, [5, 3])
    }

    // MARK: - The picture

    /// The specimen's shape: a 0.3 pt reversal over two vertices 0.05 pt apart
    /// on the time axis. Stroked with the Bain Luck line's style, nothing may
    /// rise above the peak by more than half the line's width; the same path
    /// with the old miter join rises ~9 pt — 30× the move.
    func testATinyReversalStrokesAtItsTrueHeight() {
        let peakY: CGFloat = 9.7
        let path = CGMutablePath()
        path.move(to: CGPoint(x: 0, y: 10))
        path.addLine(to: CGPoint(x: 0.05, y: peakY))
        path.addLine(to: CGPoint(x: 0.1, y: 10))

        func top(_ s: StrokeStyle) -> CGFloat {
            path.copy(strokingWithWidth: s.lineWidth, lineCap: s.lineCap, lineJoin: s.lineJoin,
                      miterLimit: s.miterLimit).boundingBoxOfPath.minY
        }

        let drawn = style("aggregate")
        let overshoot = peakY - top(drawn)
        XCTAssertLessThanOrEqual(overshoot, drawn.lineWidth / 2 + 0.01,
                                 "the line rose \(overshoot) pt above a 0.3 pt wiggle")

        // Control: the pre-fix style on the same path is the needle.
        let miter = StrokeStyle(lineWidth: 3.0)
        XCTAssertGreaterThan(peakY - top(miter), 5, "the control must reproduce the needle")
    }
}
