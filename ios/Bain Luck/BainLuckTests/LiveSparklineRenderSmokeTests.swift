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
                        minimumSpan: Double) throws -> (png: Data, inkHeight: Int, image: UIImage) {
        let view = LiveSparklineChart(
            points: points,
            width: Self.width,
            height: Self.height,
            minimumSpan: minimumSpan,
            now: Date())

        let renderer = rendererForMeasurement(view)
        renderer.scale = Self.scale
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("live-sparkline-\(name).png")
        try? png.write(to: url)
        let ink = try Self.inkHeight(of: image)
        print("Sparkline render [\(name)]: \(url.path) "
              + "(\(png.count) bytes, ink \(ink)px of \(Int(Self.height * Self.scale)))")
        return (png, ink, image)
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
        let renderer = rendererForMeasurement(view)
        renderer.scale = Self.scale
        guard let image = renderer.uiImage else {
            print("Sparkline render [\(name)]: no raster — the glyph drew nothing")
            return true
        }
        let ink = try Self.inkHeight(of: image)
        print("Sparkline render [\(name)]: raster produced, ink \(ink)px")
        return ink == 0
    }

    // MARK: - Reading the raster

    /// An RGB triple parsed from one of the component's OWN stroke constants, so
    /// the camera cannot drift from the colours production actually draws.
    private static func rgb(_ hex: String) -> (r: Int, g: Int, b: Int) {
        var value: UInt64 = 0
        Scanner(string: hex.replacingOccurrences(of: "#", with: "")).scanHexInt64(&value)
        return (Int((value >> 16) & 0xFF), Int((value >> 8) & 0xFF), Int(value & 0xFF))
    }

    private static var up: (r: Int, g: Int, b: Int) { rgb(LiveSparklineChart.strokeUp) }
    private static var down: (r: Int, g: Int, b: Int) { rgb(LiveSparklineChart.strokeDown) }
    private static var flat: (r: Int, g: Int, b: Int) { rgb(LiveSparklineChart.strokeFlat) }

    /// How far a pixel may sit from a stroke colour and still be counted as it.
    ///
    /// The three strokes are far apart in RGB — the closest pair, flat grey and
    /// down red, differ by 83 in the red channel alone — so this cannot confuse
    /// one for another; it exists to absorb antialiasing and colour-space drift.
    private static let colourTolerance = 40

    /// Vertical extent, in device pixels, of everything drawn IN A GIVEN COLOUR —
    /// or in any of the glyph's three stroke colours when `matching` is nil.
    ///
    /// #7794 WIDENED THIS, AND THAT WAS HALF THE SHIP. The predicate used to be
    /// `(g > r + 20 && g > b + 20) || (r > g + 20 && r > b + 20)` — green-dominant
    /// or red-dominant, the only two colours the glyph could draw at the time.
    /// The moment a flat window started drawing `#9CA3AF`, which is dominant in
    /// nothing, every grey pixel read as background: `testAFlatMarketStaysFlat`
    /// would have kept passing its `inkHeight < 12` assertion **against an ink
    /// height of zero**, measuring an empty image and calling it a still market.
    /// A measuring instrument keyed to the values it has seen so far fails toward
    /// "nothing is there", which is the shape of every vacuous guard. The tests
    /// below therefore assert a POSITIVE ink height everywhere they assert a small
    /// one.
    ///
    /// Channels are un-premultiplied before comparison: the buffer is
    /// `premultipliedLast`, so an antialiased edge at half alpha carries half of
    /// each colour channel and would miss an exact-colour test entirely.
    private static func ink(
        of image: UIImage,
        matching target: (r: Int, g: Int, b: Int)? = nil
    ) throws -> (height: Int, pixels: Int) {
        let cg = try XCTUnwrap(image.cgImage, "no CGImage")
        let w = cg.width, h = cg.height
        var buffer = [UInt8](repeating: 0, count: w * h * 4)
        let ctx = try XCTUnwrap(CGContext(
            data: &buffer, width: w, height: h,
            bitsPerComponent: 8, bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue), "no CGContext")
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))

        let candidates = target.map { [$0] } ?? [Self.up, Self.down, Self.flat]

        var top: Int?
        var bottom: Int?
        var pixels = 0
        for y in 0..<h {
            var rowHasInk = false
            for x in 0..<w {
                let i = (y * w + x) * 4
                let a = Int(buffer[i + 3])
                // Antialiasing fades alpha, so a modest threshold; below it the
                // un-premultiplied colour is too noisy to attribute anyway.
                guard a > 60 else { continue }
                let r = min(255, Int(buffer[i]) * 255 / a)
                let g = min(255, Int(buffer[i + 1]) * 255 / a)
                let b = min(255, Int(buffer[i + 2]) * 255 / a)
                let matches = candidates.contains { c in
                    abs(r - c.r) <= Self.colourTolerance
                        && abs(g - c.g) <= Self.colourTolerance
                        && abs(b - c.b) <= Self.colourTolerance
                }
                if matches {
                    rowHasInk = true
                    pixels += 1
                }
            }
            if rowHasInk {
                if top == nil { top = y }
                bottom = y
            }
        }
        guard let t = top, let b = bottom else { return (0, pixels) }
        return (b - t + 1, pixels)
    }

    private static func inkHeight(of image: UIImage) throws -> Int {
        try ink(of: image).height
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
        // Without this the assertion below is satisfied by an EMPTY IMAGE, and
        // #7794 made that a live risk rather than a theoretical one: this fixture
        // now draws flat grey, which the pre-#7794 ink predicate scored as zero.
        // Every "small" claim in this file is paired with a "present" one.
        XCTAssertGreaterThan(
            flat.inkHeight, 0,
            "the flat fixture drew no measurable ink — the camera is colour-blind "
            + "to this glyph's stroke, so `< 12` below is measuring nothing")
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

    // MARK: - #7794, as a raster

    /// The filed specimen: a 99% favourite whose line was painted the colour for
    /// *fell* because it gave up one ten-thousandth of a point.
    ///
    /// Asserted as INK PER COLOUR rather than by reading the `Direction` back,
    /// because `direction` returning `.flat` and the reader seeing grey are two
    /// different claims — the second one is the defect. `LiveSparklineDirectionTests`
    /// owns the arithmetic; this owns what is on the screen.
    func testTheNinetyNinePercentFavouriteDrawsGreyAndNoRed() throws {
        let now = Date()
        let specimen = series([0.9901, 0.9902, 0.99], now: now)

        // THE BEFORE, stated as arithmetic because the old rule no longer exists
        // to render: `last >= first` on the raw probabilities called this a fall,
        // so the fixture is a genuine before/after pair and not a case that was
        // already grey. Without this line the test below passes just as well on a
        // specimen the bug never touched.
        XCTAssertLessThan(0.99, 0.9901, "the specimen must be a RAW fall, or it proves nothing")

        let shot = try render("after-7794-99pct-favourite", specimen,
                              minimumSpan: LiveSparklineChart.minimumSpan)
        let grey = try Self.ink(of: shot.image, matching: Self.flat)
        let red = try Self.ink(of: shot.image, matching: Self.down)
        let green = try Self.ink(of: shot.image, matching: Self.up)

        XCTAssertGreaterThan(grey.pixels, 0,
                             "the flat glyph drew no grey — it drew nothing, or another colour")
        XCTAssertEqual(red.pixels, 0,
                       "a 99% favourite still paints \(red.pixels) red pixels for a "
                       + "ten-thousandth of a point — this is #7794")
        XCTAssertEqual(green.pixels, 0, "a flat window must not claim a rise either")

        // And the label the colour is now derived from says the same thing, in the
        // same render. One pair of numbers, one answer.
        XCTAssertEqual(
            LiveSparklineChart.accessibilityLabel(for: specimen, minutes: 10),
            "Last 10 minutes: 99% to 99%")
    }

    /// The partner, and the reason the test above is not satisfied by a glyph that
    /// paints everything grey: a real move must still carry its colour, and the
    /// colour matcher must be able to tell the three apart on a real raster.
    func testARealMoveStillPaintsItsOwnColour() throws {
        let now = Date()

        let fell = try render("after-7794-real-fall", cubsMarlinsSwing(now: now),
                              minimumSpan: LiveSparklineChart.minimumSpan)
        XCTAssertGreaterThan(try Self.ink(of: fell.image, matching: Self.down).pixels, 0,
                             "a 13-point fall must still be red")
        XCTAssertEqual(try Self.ink(of: fell.image, matching: Self.flat).pixels, 0,
                       "a 13-point fall was painted flat grey")

        let rose = try render("after-7794-real-rise", series([0.40, 0.50, 0.62], now: now),
                              minimumSpan: LiveSparklineChart.minimumSpan)
        XCTAssertGreaterThan(try Self.ink(of: rose.image, matching: Self.up).pixels, 0,
                             "a 22-point rise must still be green")
        XCTAssertEqual(try Self.ink(of: rose.image, matching: Self.flat).pixels, 0,
                       "a 22-point rise was painted flat grey")
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
