import SwiftUI
import XCTest
@testable import Bain_Luck

/// A camera on #3313, because the defect only ever existed as a raster.
///
/// "A 19-point swing renders as noise" is a LAYOUT claim, and no assertion about
/// domains can see what a reader sees. This renders the real `LiveSparklineChart`
/// through `ImageRenderer` (the camera native/025 built) and MEASURES THE INK —
/// the bounding box of the pixels actually drawn — rather than a PNG byte count.
///
/// native/026's lesson, applied: a byte count is a tripwire, not evidence. Ink
/// extent is the thing the bug is about, so it is asserted directly and the
/// artifact paths are printed for a human read on top.
///
/// THE CONTROL IS THE OLD RULE ITSELF. `minimumSpan: 1.0` reproduces master's
/// full-0-100 axis exactly — any range under 1.0 slides to 0...1 — so BEFORE and
/// AFTER come from one code path, one fixture, one renderer. Nothing about the
/// comparison depends on when it was taken or on a hand-built stand-in.
@MainActor
final class LiveSparklineRenderSmokeTests: XCTestCase {

    /// The old behaviour, expressed in the new code's own vocabulary.
    private static let fullRangeAxis: Double = 1.0

    private static let width: CGFloat = 96
    private static let height: CGFloat = 24
    private static let scale: CGFloat = 3

    /// Event 15296785, Cubs at Marlins, measured on production 2026-09-05 14:05 PT:
    /// 19 points of travel inside the ten-minute window, the most dramatic thing on
    /// its page.
    private func cubsMarlinsSwing(now: Date) -> [ChartDataPoint] {
        series([0.35, 0.34, 0.31, 0.27, 0.22, 0.16, 0.19, 0.22], now: now)
    }

    /// Event 15304503, Gauff–Bucsa, same sweep: essentially still. It must STAY
    /// still — a fix that made everything dramatic would be the mountain the
    /// original full-range rule was written to prevent.
    private func flatMarket(now: Date) -> [ChartDataPoint] {
        series([0.062, 0.063, 0.062, 0.064, 0.063, 0.064, 0.063, 0.064], now: now)
    }

    private func series(_ values: [Double], now: Date) -> [ChartDataPoint] {
        values.enumerated().map { index, value in
            ChartDataPoint(
                date: now.addingTimeInterval(-Double(values.count - index) * 70),
                probability: value,
                source: "aggregate")
        }
    }

    // MARK: - The camera

    private func render(_ name: String,
                        _ points: [ChartDataPoint],
                        minimumSpan: Double) throws -> (png: Data, inkHeight: Int) {
        let view = LiveSparklineChart(
            points: points,
            width: Self.width,
            height: Self.height,
            minimumSpan: minimumSpan,
            now: Date())

        let renderer = ImageRenderer(content: view)
        renderer.scale = Self.scale
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("live-sparkline-\(name).png")
        try? png.write(to: url)
        let ink = try Self.inkHeight(of: image)
        print("Sparkline render [\(name)]: \(url.path) "
              + "(\(png.count) bytes, ink \(ink)px of \(Int(Self.height * Self.scale)))")
        return (png, ink)
    }

    /// Whether the glyph draws nothing at all.
    ///
    /// Two shapes both count as "nothing", and the test must accept either or it
    /// pins an implementation detail: today a non-drawable window produces no view,
    /// so `ImageRenderer` returns NO RASTER; a later version that returns a
    /// zero-size transparent box would be equally honest. What must never happen is
    /// ink.
    private func drawsNothing(_ name: String, _ points: [ChartDataPoint]) throws -> Bool {
        let view = LiveSparklineChart(
            points: points,
            width: Self.width,
            height: Self.height,
            minimumSpan: LiveSparklineChart.minimumSpan,
            now: Date())
        let renderer = ImageRenderer(content: view)
        renderer.scale = Self.scale
        guard let image = renderer.uiImage else {
            print("Sparkline render [\(name)]: no raster — the glyph drew nothing")
            return true
        }
        let ink = try Self.inkHeight(of: image)
        print("Sparkline render [\(name)]: raster produced, ink \(ink)px")
        return ink == 0
    }

    /// Vertical extent, in device pixels, of everything actually drawn.
    ///
    /// The glyph has no axis, no legend and no background, so the only ink is the
    /// line — which makes this a direct measurement of "how much did the reader
    /// see it move", the exact quantity #3313 is about.
    private static func inkHeight(of image: UIImage) throws -> Int {
        let cg = try XCTUnwrap(image.cgImage, "no CGImage")
        let w = cg.width, h = cg.height
        var buffer = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = try XCTUnwrap(CGContext(
            data: &buffer, width: w, height: h,
            bitsPerComponent: 8, bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue), "no CGContext")
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))

        var top: Int?
        var bottom: Int?
        for y in 0..<h {
            var rowHasInk = false
            for x in 0..<w {
                let i = (y * w + x) * 4
                let r = Int(buffer[i]), g = Int(buffer[i + 1])
                let b = Int(buffer[i + 2]), a = Int(buffer[i + 3])
                // The stroke is #10B981 or #EF4444 on nothing. Antialiasing fades
                // alpha, so a modest threshold, plus a colour test so a stray
                // neutral pixel cannot widen the box.
                let coloured = (g > r + 20 && g > b + 20) || (r > g + 20 && r > b + 20)
                if a > 60 && coloured {
                    rowHasInk = true
                    break
                }
            }
            if rowHasInk {
                if top == nil { top = y }
                bottom = y
            }
        }
        guard let t = top, let b = bottom else { return 0 }
        return b - t + 1
    }

    // MARK: - The claim

    /// The whole ship, as one measurement: the same swing, the same fixture, the
    /// same renderer, one number changed.
    func testARealSwingIsResolvedWhereTheOldAxisFlattenedIt() throws {
        let now = Date()
        let before = try render("before-full-range-swing",
                                cubsMarlinsSwing(now: now),
                                minimumSpan: Self.fullRangeAxis)
        let after = try render("after-swing",
                               cubsMarlinsSwing(now: now),
                               minimumSpan: LiveSparklineChart.minimumSpan)

        XCTAssertGreaterThan(before.inkHeight, 0, "the BEFORE control drew nothing — camera is dead")
        XCTAssertGreaterThan(
            after.inkHeight, before.inkHeight * 3,
            "a 19-point swing must draw far more travel than the full-range axis gave it "
            + "(before \(before.inkHeight)px, after \(after.inkHeight)px)")
        // And it must genuinely use the box, not merely beat a low bar.
        XCTAssertGreaterThan(
            after.inkHeight, Int(Self.height * Self.scale) / 2,
            "the swing should fill most of the glyph")
    }

    /// The partner assertion, and the one that stops this fix from being "make
    /// everything dramatic". A still market must still LOOK still.
    func testAFlatMarketStaysFlat() throws {
        let now = Date()
        let flat = try render("after-flat", flatMarket(now: now), minimumSpan: LiveSparklineChart.minimumSpan)
        let swing = try render("after-swing-control", cubsMarlinsSwing(now: now),
                               minimumSpan: LiveSparklineChart.minimumSpan)
        // 0.002 of a 0.2 span in a 72px raster is about 1px, plus stroke width.
        XCTAssertLessThan(
            flat.inkHeight, 12,
            "a market that moved a fifth of a point drew \(flat.inkHeight)px — "
            + "that is the auto-scaled mountain the span floor exists to prevent")
        XCTAssertGreaterThan(swing.inkHeight, flat.inkHeight * 3,
                             "flat and dramatic must not look alike")
    }

    /// Without this, both halves above pass just as well if the glyph renders
    /// nothing at all.
    func testTheGlyphActuallyDrawsSomething() throws {
        let now = Date()
        let drawn = try render("control-draws", cubsMarlinsSwing(now: now),
                               minimumSpan: LiveSparklineChart.minimumSpan)
        XCTAssertGreaterThan(drawn.png.count, 300, "raster is suspiciously empty")
        XCTAssertGreaterThan(drawn.inkHeight, 0, "no ink found — the line was not drawn")
    }

    /// #3278 one size down: a non-drawable window renders NOTHING — not a frame,
    /// not a flat line. The glyph's honest-empty is absence.
    func testANonDrawableWindowRendersNoInk() throws {
        let now = Date()
        let twoPoints = series([0.4, 0.5], now: now)
        XCTAssertFalse(LiveSparklineChart.isDrawable(
            LiveSparklineChart.windowed(twoPoints, minutes: 10, now: now)))
        XCTAssertTrue(try drawsNothing("empty-two-points", twoPoints),
                      "a non-drawable window drew a line anyway")
        // The control: one more reading and the same path DOES draw. Without it
        // this test passes for a glyph that never renders under any input.
        XCTAssertFalse(try drawsNothing("empty-control-three-points",
                                        series([0.4, 0.45, 0.5], now: now)))
    }

    /// A stale series is not a live one. Nothing inside the window means no glyph.
    func testAStaleSeriesRendersNoInk() throws {
        let now = Date()
        let stale = (0..<8).map { index in
            ChartDataPoint(
                date: now.addingTimeInterval(-3600 - Double(index) * 60),
                probability: 0.3 + Double(index) * 0.02,
                source: "aggregate")
        }
        XCTAssertTrue(try drawsNothing("empty-stale", stale), "an hour-old series drew a glyph")
    }
}
