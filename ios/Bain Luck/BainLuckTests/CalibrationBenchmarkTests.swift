import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #7536 — the Accuracy screen's "How We Compare" card, pinned.
///
/// THE BUG THIS PINS. Web repaired this card three times (CAL-P1261 / #6278,
/// then #7524). The Swift twin took none of the three, because the four rows
/// were four literal argument lists passed to a private `@ViewBuilder` helper:
/// no test in `ios/**` named `3.5`, `1.5`, `2.5` or `"Bain Luck"`, and the
/// cross-surface parity hooks cover the hero and the source table, not this
/// card. So the app spent three ships drawing a 2–5pp range as a solid bar at
/// its invented midpoint, grading Metaculus and two 2008 papers green on OUR
/// thresholds, plotting a vote-share error as a calibration benchmark, and
/// labelling the one cohort-scoped row as if it were not.
///
/// THE SHAPE OF THESE TESTS. Each assertion names the value the defect had, not
/// only the value the fix has — `3.5` and a bar starting at zero are the things
/// that must never come back, and a test that only asserts the new number keeps
/// passing when a later edit reverts to a midpoint by a different route. The
/// rows are pinned as values AND the card is rasterised, because "a range draws
/// as a band" is a claim about ink.
@MainActor
final class CalibrationBenchmarkTests: XCTestCase {

    /// `loadedStack`'s `.padding(.horizontal)` inside the narrowest phone.
    private static let cardWidth: CGFloat = 390 - 32

    private func model(_ json: String = CalibrationProdFixture.json) throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return CalibrationViewModel(preloaded: try dec.decode(CalibrationData.self, from: Data(json.utf8)))
    }

    private func rows(
        mce: Double = 1.0, outcomes: String = "449,027", cohort: String = "Price moved"
    ) -> [CalibrationBenchmarks.Row] {
        CalibrationBenchmarks.rows(ourMCE: mce, ourOutcomes: outcomes, cohort: cohort)
    }

    private func row(_ label: String) throws -> CalibrationBenchmarks.Row {
        try XCTUnwrap(rows().first { $0.label == label }, "no row labelled \(label)")
    }

    // MARK: - #7524 — the row that was not a calibration figure

    func testTheIowaElectronicMarketsRowIsGone() {
        for r in rows() {
            let text = "\(r.label) \(r.detail) \(r.cohortTag ?? "")"
            XCTAssertFalse(text.localizedCaseInsensitiveContains("Iowa"),
                           "#7524: \(text) — Berg et al.'s 1.5pp is an absolute error on "
                           + "predicted vote SHARE, not a per-bucket calibration error")
            XCTAssertFalse(text.localizedCaseInsensitiveContains("Berg"), text)
            XCTAssertNotEqual(r.value, 1.5, "#7524: the IEM figure is back on \(r.label)")
        }
        XCTAssertEqual(rows().count, 3, "our row, Metaculus, and the Arrow range")
    }

    // MARK: - #6278 item 3 — a range is a band, never a midpoint

    func testTheAcademicConsensusRangeIsPublishedAsARangeAndHasNoPointValue() throws {
        let arrow = try row("Academic consensus")
        XCTAssertTrue(arrow.isRange)
        XCTAssertNil(arrow.value,
                     "a benchmark published as a RANGE has no point value; inventing one "
                     + "to draw a bar with is the whole defect")
        XCTAssertEqual(arrow.rangeLow, 2)
        XCTAssertEqual(arrow.rangeHigh, 5)
        XCTAssertEqual(arrow.figureText, "2\u{2013}5pp")
        // The caption used to carry "(2–5pp)" beside a bar drawn at 3.5, which is
        // how the row contradicted itself in place. The figure says the range now,
        // so the caption must not say it twice.
        XCTAssertFalse(arrow.detail.contains("pp"), "duplicated figure in the caption: \(arrow.detail)")
    }

    func testTheRangeIsDrawnAsABandBetweenItsEndsAndNotFromZeroToItsMidpoint() throws {
        let arrow = try row("Academic consensus")
        XCTAssertEqual(arrow.barLeadingFraction, 0.2, accuracy: 1e-9,
                       "a 2–5pp band on a 0–10pp axis starts a fifth of the way along")
        XCTAssertEqual(arrow.barWidthFraction, 0.3, accuracy: 1e-9)

        // The defect, named: a solid bar from the leading edge at the midpoint.
        XCTAssertNotEqual(arrow.barLeadingFraction, 0, accuracy: 1e-9,
                          "#6278 item 3: the band starts at its LOW end, not at zero")
        XCTAssertNotEqual(arrow.barWidthFraction, 0.35, accuracy: 1e-9,
                          "#6278 item 3: 3.5 is the midpoint of 2–5 and appears nowhere "
                          + "the reader can see")
        XCTAssertFalse(arrow.figureText.contains("3.5"))
    }

    // MARK: - #6278 item 2 — only our own measured row is graded

    func testOnlyOurOwnMeasuredRowMayBeColouredOnOurThresholds() {
        let graded = rows().filter(\.isGraded)
        XCTAssertEqual(graded.count, 1, "graded: \(graded.map(\.label))")
        XCTAssertEqual(graded.first?.label, "Bain Luck")
        for r in rows() where r.label != "Bain Luck" {
            XCTAssertFalse(r.isGraded,
                           "\(r.label) is somebody else's figure measured somebody else's "
                           + "way; our green/blue/orange is a verdict we cannot support")
        }
    }

    /// The defect was invisible precisely because every value cleared the green
    /// threshold, so the grading bug and a correctly-graded card looked identical.
    /// This pins the property that hid it: ungraded means ungraded whatever the
    /// number would have scored.
    func testABenchmarkUnderOurGreenThresholdIsStillNotGraded() throws {
        let metaculus = try row("Metaculus")
        XCTAssertEqual(metaculus.value, 2.5)
        XCTAssertLessThan(try XCTUnwrap(metaculus.value), 4,
                          "the figure that used to print green")
        XCTAssertFalse(metaculus.isGraded)
    }

    // MARK: - #6278 item 1 — our row names the cohort it moves with

    func testOurRowCarriesTheActiveCohortAndTheBenchmarksDoNot() {
        let ours = rows(cohort: "Price moved + sportsbook lines").first { $0.isOurs }
        XCTAssertEqual(ours?.cohortTag, "Price moved + sportsbook lines")
        for r in rows() where !r.isOurs {
            XCTAssertNil(r.cohortTag,
                         "\(r.label) is not cohort-scoped at all — tagging it would claim "
                         + "the toggle above moves it")
        }
        XCTAssertEqual(rows().filter(\.isOurs).count, 1)
    }

    /// The tag comes from the view model, so it cannot drift from the banner that
    /// sets it — and it MOVES, which is the whole reason the row needs one.
    func testTheCohortTagTracksTheToggleOnTheRealPayload() throws {
        let vm = try model()
        func ourRow() -> CalibrationBenchmarks.Row? {
            CalibrationBenchmarks.rows(
                ourMCE: vm.cohortMCE,
                ourOutcomes: vm.formattedCohortOutcomes,
                cohort: vm.cohortShortLabel).first { $0.isOurs }
        }
        vm.includeThin = false
        let traded = try XCTUnwrap(ourRow())
        vm.includeThin = true
        let all = try XCTUnwrap(ourRow())

        XCTAssertEqual(traded.cohortTag, "Price moved + sportsbook lines")
        XCTAssertEqual(all.cohortTag, "All markets")
        XCTAssertNotEqual(traded.detail, all.detail, "the outcome count moves with it")
        XCTAssertNotEqual(traded.value, all.value, "so does the figure")
        print("#7536 prod row: \(traded.label) [\(traded.cohortTag ?? "nil")] "
            + "\(traded.figureText) · \(traded.detail) → toggled: "
            + "[\(all.cohortTag ?? "nil")] \(all.figureText) · \(all.detail)")
    }

    func testOurFigureIsTheCohortPerBucketErrorTheViewModelPublishes() throws {
        let vm = try model()
        let ours = try XCTUnwrap(CalibrationBenchmarks.rows(
            ourMCE: vm.cohortMCE,
            ourOutcomes: vm.formattedCohortOutcomes,
            cohort: vm.cohortShortLabel).first { $0.isOurs })
        XCTAssertEqual(try XCTUnwrap(ours.value), vm.cohortMCE, accuracy: 1e-9)
        XCTAssertEqual(ours.figureText, String(format: "%.1fpp", vm.cohortMCE))
        XCTAssertEqual(ours.detail, "\(vm.formattedCohortOutcomes) outcomes")
    }

    // MARK: - #7225 — the figure says which statistic it is

    func testOurFigureNamesItsStatisticAndTheBenchmarksDoNot() throws {
        let vm = try model()
        let rows = CalibrationBenchmarks.rows(
            ourMCE: vm.cohortMCE, ourOutcomes: vm.formattedCohortOutcomes,
            cohort: vm.cohortShortLabel)
        XCTAssertEqual(rows.first { $0.isOurs }?.figureQualifier, "per-bucket",
                       "our figure is the equal-weighted per-bucket error while the hero "
                       + "and the source table's Combined row are n-weighted ECE — on the "
                       + "same payload they read \(String(format: "%.1f", vm.cohortMCE))pp "
                       + "and \(String(format: "%.1f", vm.cohortECE))pp with nothing to "
                       + "tell them apart")
        for r in rows where !r.isOurs {
            XCTAssertNil(r.figureQualifier,
                         "\(r.label) is somebody else's figure and we cannot say how it "
                         + "was averaged")
        }
        // The qualifier is a separate fragment, never welded into the figure:
        // the figure has to stay one unbreakable token.
        XCTAssertFalse(try XCTUnwrap(rows.first { $0.isOurs }).figureText.contains("per-bucket"))
    }

    // MARK: - The axis

    func testAPointRowStartsAtTheLeadingEdgeAndScalesOnTheSharedAxis() {
        let point = CalibrationBenchmarks.Row.point("X", 2.5, detail: "")
        XCTAssertEqual(point.barLeadingFraction, 0, accuracy: 1e-9)
        XCTAssertEqual(point.barWidthFraction, 0.25, accuracy: 1e-9)
        XCTAssertEqual(point.figureText, "2.5pp")
        XCTAssertNil(point.rangeLow)
        XCTAssertNil(point.rangeHigh)
        XCTAssertEqual(CalibrationBenchmarks.axisMaxPP, 10)
    }

    func testTheBarNeverRunsPastTheTrackWhateverTheFigure() {
        // A cohort that is badly calibrated is a number we still have to draw.
        XCTAssertEqual(CalibrationBenchmarks.Row.point("X", 36.49, detail: "").barWidthFraction,
                       1, accuracy: 1e-9)
        XCTAssertEqual(CalibrationBenchmarks.Row.point("X", -1, detail: "").barWidthFraction,
                       0, accuracy: 1e-9)
        XCTAssertEqual(CalibrationBenchmarks.Row.point("X", .nan, detail: "").barWidthFraction,
                       0, accuracy: 1e-9)
        let overhang = CalibrationBenchmarks.Row.range("X", low: 8, high: 20, detail: "")
        XCTAssertEqual(overhang.barLeadingFraction, 0.8, accuracy: 1e-9)
        XCTAssertEqual(overhang.barWidthFraction, 0.2, accuracy: 1e-9,
                       "a band that starts inside the track must end inside it")
    }

    func testARangeRowIsNeverAlsoAPointRow() {
        for r in rows() {
            XCTAssertFalse(r.isRange && r.value != nil,
                           "\(r.label) holds both a range and a point value")
            XCTAssertFalse(!r.isRange && r.value == nil,
                           "\(r.label) holds neither")
        }
    }

    // MARK: - The drawn card

    /// The values above are the rule; this is the ink. Rasterises the REAL
    /// section at the REAL card width so a run can be eyeballed, and measures
    /// that it fits — the row grew a second label line for the cohort tag.
    func testTheCardRendersInsideThePhoneCard() throws {
        let vm = try model()
        let section = CalibrationSurfaceView(viewModel: vm).benchmarkSection
            .frame(width: Self.cardWidth)
        let host = hostForMeasurement(AnyView(section))
        let fitted = host.sizeThatFits(in: CGSize(width: Self.cardWidth,
                                                  height: .greatestFiniteMagnitude))
        XCTAssertLessThanOrEqual(fitted.width, Self.cardWidth + 0.5,
                                 "the benchmark card is wider than the 390pt card")

        let renderer = rendererForMeasurement(section)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage)
        let png = try XCTUnwrap(image.pngData())
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("7536-how-we-compare.png")
        try? png.write(to: url)
        print("#7536 render artifact: \(url.path) "
            + "(\(png.count) bytes, \(image.size.width)x\(image.size.height)pt, "
            + "fitted \(fitted))")
        XCTAssertGreaterThan(png.count, 1_000)
    }
}
