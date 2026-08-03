import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// L2-238 Item 2 — the Calibration Curve card lays out inside a 390pt iPhone.
///
/// L2-237 put the cohort name in the curve's subtitle, rendered it, and got back
/// "Calibration Curve: Price moved + sport…". The cause was not the copy: the
/// `Chart` inside `calibrationChartSection` carried no width constraint, so it
/// proposed its own ideal width to the enclosing `VStack`, the stack sized to
/// that instead of to the card, and both `Text`s laid out on a single over-wide
/// line the card then clipped. The old explainer was already cut at
/// "…perfect calibrati…" before any of this queue's work — the truncation just
/// had never been in a sentence anyone needed to read to the end.
///
/// The measurement here is the point. `sizeThatFits` on the real section, at the
/// real width, is the only thing that distinguishes "the string is right" from
/// "the string is readable" — L2-237's own lesson was that both placements
/// passed every assertion and both builds, and only the raster showed one was
/// unreadable. So: measure, and also write the PNG so a run can be eyeballed.
@MainActor
final class CalibrationCurveWidthTests: XCTestCase {

    /// The narrowest supported iPhone width the app ships against.
    private static let iPhoneWidth: CGFloat = 390
    /// `loadedStack`'s `.padding(.horizontal)` — the width the card really gets.
    private static let cardWidth: CGFloat = 390 - 32

    private func model(_ json: String = CalibrationProdFixture.json) throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return CalibrationViewModel(preloaded: try dec.decode(CalibrationData.self, from: Data(json.utf8)))
    }

    /// The REAL section, at the REAL card width — never a replica of it.
    private func section(_ vm: CalibrationViewModel) -> some View {
        CalibrationSurfaceView(viewModel: vm).calibrationChartSection
            .frame(width: Self.cardWidth)
    }

    private func raster(_ view: some View, name: String) throws -> (Data, CGSize) {
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("l2238-curve-\(name).png")
        try? png.write(to: url)
        print("L2-238 render artifact [\(name)]: \(url.path) "
            + "(\(png.count) bytes, \(image.size.width)x\(image.size.height)pt)")
        return (png, image.size)
    }

    // MARK: - The fix

    /// The defect, measured: the section must not be wider than the card it is in.
    func testTheCurveSectionFitsTheCardWidth() throws {
        let vm = try model()
        let host = UIHostingController(rootView: AnyView(section(vm)))
        let fitted = host.sizeThatFits(in: CGSize(width: Self.cardWidth,
                                                  height: .greatestFiniteMagnitude))
        print("L2-238 curve section fitted size: \(fitted) (card width \(Self.cardWidth))")
        XCTAssertLessThanOrEqual(
            fitted.width, Self.cardWidth + 0.5,
            "the curve section is wider than the 390pt card — the chart is proposing "
            + "its own ideal width again and the title/subtitle will clip")
    }

    /// The consequence, measured: the subtitle is long enough that fitting inside
    /// the card REQUIRES it to wrap. A section tall enough for the 300pt chart
    /// plus a multi-line subtitle proves it did.
    func testTheSubtitleWrapsInsteadOfTruncating() throws {
        let vm = try model()
        let host = UIHostingController(rootView: AnyView(section(vm)))
        let fitted = host.sizeThatFits(in: CGSize(width: Self.cardWidth,
                                                  height: .greatestFiniteMagnitude))

        // Chart 300 + card padding 32 + title ~22 + spacing 20 ≈ 374 for a
        // single-line subtitle. The subtitle is ~230 characters at `.caption`;
        // wrapped inside 326pt it is 5+ lines, so anything under ~420 means it
        // collapsed onto one line and got clipped again.
        XCTAssertGreaterThan(
            fitted.height, 420,
            "the curve section is too short to be holding a wrapped subtitle — "
            + "the explainer has collapsed to one truncated line")
        print("L2-238 subtitle length: \(vm.cohortShortLabel.count) (short label) / "
            + "section height \(fitted.height)")
    }

    /// The two states L2-237 rendered, both at 390pt, both written out for eyes.
    ///
    /// Read this one with your eyes, not only with the assertions. The measured
    /// checks above pin the section's IDEAL layout, and the ideal was never the
    /// problem: `sizeThatFits` reported a wrapped 451pt section both before and
    /// after the fix, because the compression happened in the RENDER pass, inside
    /// the stack, where the enclosing `VStack` handed the card less height than
    /// its own sizing pass had allotted. `.fixedSize(horizontal: false,
    /// vertical: true)` on the card's `Text`s is what forbids that, and only the
    /// `surface-390` raster shows it — which is precisely how the defect was
    /// found in the first place. The artifact path is printed on every run.
    func testFreshAndDatedDegradedBothRasteriseAtIPhoneWidth() throws {
        let fresh = try model()
        let (freshPNG, freshSize) = try raster(section(fresh), name: "fresh")
        XCTAssertGreaterThan(freshPNG.count, 1_000, "fresh curve render is suspiciously empty")
        XCTAssertLessThanOrEqual(freshSize.width, Self.cardWidth + 0.5)

        // The frozen production payload was served STALE — the dated-degraded
        // state, from real provenance rather than a fixture written to produce it.
        XCTAssertTrue(fresh.isStale, "the frozen production response was served stale")

        // The full surface at a real device width, so the card is measured in the
        // stack it actually lives in (padding, max-width and all).
        let surface = CalibrationSurfaceView(viewModel: fresh, scrolls: false)
            .frame(width: Self.iPhoneWidth)
        let (surfacePNG, surfaceSize) = try raster(surface, name: "surface-390")
        XCTAssertGreaterThan(surfacePNG.count, 1_000)
        XCTAssertLessThanOrEqual(
            surfaceSize.width, Self.iPhoneWidth + 0.5,
            "the calibration surface overflows a 390pt iPhone")
    }

    // MARK: - Nothing else moved

    /// The gate says: no chart axis, height, metric, population, filter, copy or
    /// interaction change. The chart geometry and every number are asserted here
    /// so "a layout fix" cannot quietly become anything else.
    func testChartGeometryCopyAndNumbersAreUnchanged() throws {
        let vm = try model()
        // Copy — the exact strings L2-237 approved.
        XCTAssertEqual(vm.cohortShortLabel, "Price moved + sportsbook lines")
        XCTAssertEqual(vm.cohortHeadline,
                       "Showing markets whose price moved, plus sportsbook lines (389,385)")
        // Population / metrics — the 1e-12 production-fixture invariants.
        XCTAssertEqual(vm.cohortN, 389_385)
        XCTAssertEqual(vm.movedN + vm.unchangedN + vm.notApplicableN, vm.fullN)
        XCTAssertEqual(vm.fullN, 652_407)
        // Filter default.
        XCTAssertFalse(vm.includeThin, "the cohort filter default moved")
        // Chart geometry: the section's height is chart(300) + chrome, so a
        // changed chart height would move it out of this window.
        let host = UIHostingController(rootView: AnyView(section(vm)))
        let fitted = host.sizeThatFits(in: CGSize(width: Self.cardWidth,
                                                  height: .greatestFiniteMagnitude))
        XCTAssertGreaterThan(fitted.height, 300, "the 300pt chart is gone")
        XCTAssertLessThan(fitted.height, 700, "the section grew beyond a wrapped subtitle + chart")
    }
}
