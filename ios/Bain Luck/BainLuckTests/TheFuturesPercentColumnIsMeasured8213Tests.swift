import XCTest
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

/// #8213 — the Discover FUTURES card's outcome row drew its percentage at
/// `.frame(width: 34)` in `.caption.weight(.bold).monospacedDigit()`, a text
/// style that scales, so at a11y5 `63%` broke into `6` / `3` / `%`, one glyph
/// per line, beside a name truncated to `Demo-`/`cratic…`.
///
/// Half of this file is SOURCE GUARDS on the call site, and that is deliberate:
/// `FuturesOutcomeRowColumns.layout` takes `availableWidth` and `typeSize` as
/// parameters, so **the defect being repaired — hardcoded point widths at the
/// CALL SITE — cannot be written inside the model at all.** No test of the model
/// alone could fail on the old behaviour. Sever any one wire and the model stays
/// perfectly correct and completely inert.
final class TheFuturesPercentColumnIsMeasured8213Tests: XCTestCase {

    // MARK: - The measurement tracks the text size

    /// The whole defect in one assertion: the percentage's ink outgrows the 34pt
    /// box that used to hold it. If this ever fails, the fix is unnecessary.
    func testThePercentOutgrowsTheOldThirtyFourPointBox() {
        let atLarge = FuturesOutcomeRowColumns.percentWidth("63%", typeSize: .large)
        let atA11y5 = FuturesOutcomeRowColumns.percentWidth("63%", typeSize: .accessibility5)

        XCTAssertLessThan(atLarge, 34, "at the default size 63% did fit — the literal was not absurd")
        XCTAssertGreaterThan(
            atA11y5, 34,
            "the photographed defect: at a11y5 63% needs more than the 34pt it was given")
        XCTAssertGreaterThan(atA11y5, atLarge * 2, "the caption style ramps steeply by a11y5")
    }

    /// Monotonic across every shipped size — a column that is measured cannot be
    /// correct at one setting and wrong at the next, which is what 34 was.
    func testTheMeasurementRisesWithEveryStepOfDynamicType() {
        let sizes: [DynamicTypeSize] = [
            .xSmall, .small, .medium, .large, .xLarge, .xxLarge, .xxxLarge,
            .accessibility1, .accessibility2, .accessibility3, .accessibility4, .accessibility5,
        ]
        let widths = sizes.map { FuturesOutcomeRowColumns.percentWidth("100%", typeSize: $0) }
        for (smaller, larger) in zip(widths, widths.dropFirst()) {
            XCTAssertLessThanOrEqual(smaller, larger, "the ramp must never go backwards")
        }
        XCTAssertLessThan(widths.first!, widths.last!, "and it must actually move")
    }

    /// `100%` is the widest string this row can ever print, and it is the one the
    /// column has to be able to hold. `discoverFuturesCardPercentLabel` is the
    /// producer, so the bound is read from it rather than assumed.
    func testTheWidestStringTheRowCanPrintIsOneHundredPercent() {
        let everyLabel = (0...100).map { discoverFuturesCardPercentLabel($0) }
            + [discoverFuturesCardPercentLabel(nil)]
        let widest = everyLabel
            .map { FuturesOutcomeRowColumns.percentWidth($0, typeSize: .accessibility5) }
            .max()!
        let hundred = FuturesOutcomeRowColumns.percentWidth("100%", typeSize: .accessibility5)
        XCTAssertEqual(widest, hundred, accuracy: 0.01,
                       "nothing this row prints is wider than 100%")
    }

    // MARK: - The column is shared, which is what the literal got right

    /// The three rows must share a right edge or the bars beside them ragged.
    /// Measuring each row on its own ink would do exactly that.
    func testEveryRowOnACardGetsTheSamePercentColumn() {
        let layout = FuturesOutcomeRowColumns.layout(
            percentLabels: ["63%", "37%", "1%"], availableWidth: 315, typeSize: .large)
        let widest = FuturesOutcomeRowColumns.percentWidth("63%", typeSize: .large)
            + FuturesOutcomeRowColumns.inkSlack

        XCTAssertEqual(layout.percentWidth, widest, accuracy: 0.01,
                       "the column is the WIDEST label on the card, not the first or the last")
    }

    /// Order must not decide the width — a guard that only ever sees the widest
    /// label first would pass on a `first` where a `max` was meant.
    func testTheColumnIsTheWidestLabelWhicheverOrderTheyArrive() {
        let ascending = FuturesOutcomeRowColumns.layout(
            percentLabels: ["1%", "37%", "100%"], availableWidth: 315, typeSize: .large)
        let descending = FuturesOutcomeRowColumns.layout(
            percentLabels: ["100%", "37%", "1%"], availableWidth: 315, typeSize: .large)

        XCTAssertEqual(ascending.percentWidth, descending.percentWidth, accuracy: 0.01)
        XCTAssertEqual(
            ascending.percentWidth,
            FuturesOutcomeRowColumns.percentWidth("100%", typeSize: .large)
                + FuturesOutcomeRowColumns.inkSlack,
            accuracy: 0.01)
    }

    /// The slack is real and is the difference between a column and a clipped
    /// glyph — `NSString.size` is fractional and SwiftUI truncates on the
    /// fractional overflow.
    func testTheColumnIsWiderThanTheBareInk() {
        let layout = FuturesOutcomeRowColumns.layout(
            percentLabels: ["63%"], availableWidth: 315, typeSize: .accessibility5)
        XCTAssertGreaterThan(
            layout.percentWidth,
            FuturesOutcomeRowColumns.percentWidth("63%", typeSize: .accessibility5))
    }

    // MARK: - The name cap, which was the row's other literal

    /// The cap moves in BOTH directions against the 140 it replaces, and each
    /// direction has a reason: at the default size the percentage is small, so
    /// the name may have more than 140; at a11y5 the percentage needs ~80pt, so
    /// the name must accept less. A literal can do neither.
    func testTheNameCapGrowsAtDefaultSizeAndShrinksAtAccessibilitySizes() {
        let atLarge = FuturesOutcomeRowColumns.layout(
            percentLabels: ["63%"], availableWidth: 315, typeSize: .large).nameMaximum
        let atA11y5 = FuturesOutcomeRowColumns.layout(
            percentLabels: ["63%"], availableWidth: 315, typeSize: .accessibility5).nameMaximum

        XCTAssertGreaterThan(atLarge, 140, "at .large the old cap was needlessly tight")
        XCTAssertLessThan(atA11y5, 140, "at a11y5 the old cap starved the percentage")
        XCTAssertLessThan(atA11y5, atLarge, "and the two move in the right order")
    }

    /// The bar keeps its third whatever the name wants — it is the only column
    /// that cannot truncate its way out of being too small.
    func testTheBarKeepsAThirdOfTheRow() {
        let available: Double = 315
        let layout = FuturesOutcomeRowColumns.layout(
            percentLabels: ["100%"], availableWidth: available, typeSize: .accessibility5)
        let leftForBar = available
            - layout.nameMaximum
            - layout.percentWidth
            - FuturesOutcomeRowColumns.interColumnSpacing * 2

        XCTAssertGreaterThanOrEqual(
            leftForBar, available * FuturesOutcomeRowColumns.barMinimumShare - 0.01,
            "with the name at its cap the bar still has its share")
    }

    /// The cap is a proportion, so it must track the card's width rather than a
    /// phone this file has heard of.
    func testTheCapTracksTheCardWidthNotTheDevice() {
        let narrow = FuturesOutcomeRowColumns.layout(
            percentLabels: ["63%"], availableWidth: 280, typeSize: .large).nameMaximum
        let wide = FuturesOutcomeRowColumns.layout(
            percentLabels: ["63%"], availableWidth: 400, typeSize: .large).nameMaximum
        XCTAssertGreaterThan(wide, narrow)
    }

    /// The floor holds even when the arithmetic would go under it, so a one-word
    /// outcome never collapses its column on a very narrow card.
    func testTheNameNeverFallsBelowItsFloor() {
        let layout = FuturesOutcomeRowColumns.layout(
            percentLabels: ["100%"], availableWidth: 120, typeSize: .accessibility5)
        XCTAssertEqual(layout.nameMaximum, FuturesOutcomeRowColumns.nameMinimum, accuracy: 0.01)
    }

    /// Before the first `GeometryReader` pass there is no width. The percentage
    /// does not depend on one, so it is still measured; the name keeps its floor.
    func testAnUnmeasuredFirstFrameStillSizesThePercentage() {
        let layout = FuturesOutcomeRowColumns.layout(
            percentLabels: ["63%"], availableWidth: 0, typeSize: .accessibility5)
        XCTAssertEqual(
            layout.percentWidth,
            FuturesOutcomeRowColumns.percentWidth("63%", typeSize: .accessibility5)
                + FuturesOutcomeRowColumns.inkSlack,
            accuracy: 0.01,
            "the percentage is measured from the string, not from the row's width")
        XCTAssertEqual(layout.nameMaximum, FuturesOutcomeRowColumns.nameMinimum, accuracy: 0.01)
    }

    /// An empty card cannot ask for a negative column.
    func testACardWithNoRowsAsksForNoPercentColumn() {
        let layout = FuturesOutcomeRowColumns.layout(
            percentLabels: [], availableWidth: 315, typeSize: .large)
        XCTAssertEqual(layout.percentWidth, FuturesOutcomeRowColumns.inkSlack, accuracy: 0.01)
    }

    // MARK: - The wiring, which no test of the model can see

    private static func source(_ relativePath: String) throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let appRoot = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        return try String(
            contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// Comments are where this file's own subject is DESCRIBED, at length. A
    /// guard that scanned them would pass on a card whose code had been reverted
    /// and whose comments still explained the fix.
    private static func strippedSource(_ relativePath: String) throws -> String {
        try source(relativePath)
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// Anti-vacuity: the strip has to remove the prose AND leave the code. A
    /// stripper that returned "" would make every guard below pass.
    func testTheCommentStripLeavesRealCodeStanding() throws {
        let stripped = try Self.strippedSource("Components/DiscoverFuturesCard.swift")
        XCTAssertTrue(
            stripped.contains("struct NativeFuturesDiscoverCard: View {"),
            "the strip ate the code; every needle below would then be vacuous")
        XCTAssertFalse(
            stripped.contains("#8213 — the column widths are measured from the strings"),
            "the strip left doc comments in, so a needle could match prose about the fix")
    }

    /// The defect itself, in the only place it can be written.
    func testNeitherLiteralSurvivesAtTheCallSite() throws {
        let stripped = try Self.strippedSource("Components/DiscoverFuturesCard.swift")
        XCTAssertFalse(
            stripped.contains(".frame(width: 34, alignment: .trailing)"),
            "the 34pt percent column is back — this is #8213")
        XCTAssertFalse(
            stripped.contains("maxWidth: 140"),
            "the 140pt name cap is back — the row's other literal")
    }

    /// The model is called, and called with the two inputs that make it a
    /// measurement rather than a constant.
    func testTheCardMeasuresItselfAndItsOwnTextSize() throws {
        let stripped = try Self.strippedSource("Components/DiscoverFuturesCard.swift")
        XCTAssertTrue(
            stripped.contains("FuturesOutcomeRowColumns.layout("),
            "the column model is not called at all")
        XCTAssertTrue(
            stripped.contains("availableWidth: outcomeRowWidth"),
            "the row stopped publishing its own width; the model always sees 0")
        XCTAssertTrue(
            stripped.contains("typeSize: dynamicTypeSize"),
            "the card stopped reading its own text size")
        XCTAssertTrue(
            stripped.contains("@Environment(\\.dynamicTypeSize) private var dynamicTypeSize"),
            "there is no text size to read")
        XCTAssertTrue(
            stripped.contains("FuturesOutcomeRowWidthKey.self"),
            "the GeometryReader that publishes the width is gone")
    }

    /// Both measured values must actually reach the row, not merely be computed.
    func testBothMeasurementsAreAppliedToTheRow() throws {
        let stripped = try Self.strippedSource("Components/DiscoverFuturesCard.swift")
        XCTAssertTrue(
            stripped.contains("width: columns.percentWidth"),
            "the percentage is not drawn at the measured width")
        XCTAssertTrue(
            stripped.contains("maxWidth: columns.nameMaximum"),
            "the name is not capped at the measured maximum")
        XCTAssertTrue(
            stripped.contains("minWidth: FuturesOutcomeRowColumns.nameMinimum"),
            "the name floor stopped coming from the model")
    }

    /// The spacing the model subtracts must be the spacing the row is built
    /// with, or the arithmetic describes a row that does not exist.
    func testTheRowIsBuiltWithTheSpacingTheModelSubtracts() throws {
        let stripped = try Self.strippedSource("Components/DiscoverFuturesCard.swift")
        XCTAssertTrue(
            stripped.contains("HStack(spacing: FuturesOutcomeRowColumns.interColumnSpacing)"),
            "the row's spacing and the model's are two numbers that can drift apart")
    }

    /// The percentage is measured as ONE line, so it must be drawn as one — a
    /// column sized to unwrapped ink under a view that may wrap is the same
    /// shred in a different box.
    func testThePercentageIsDrawnOnOneLine() throws {
        let stripped = try Self.strippedSource("Components/DiscoverFuturesCard.swift")
        let percentBlock = stripped
            .components(separatedBy: "Text(discoverFuturesCardPercentLabel(percent))")
        XCTAssertEqual(percentBlock.count, 2, "the percentage is printed in exactly one place")
        XCTAssertTrue(
            percentBlock[1].prefix(220).contains(".lineLimit(1)"),
            "the percentage may wrap, which is the defect measured ink cannot prevent")
    }

    /// The measuring font must be the drawn font. Measuring `.caption2` while
    /// drawing `.caption` is how a column ends up narrower than its string.
    func testTheMeasuringFontIsTheFontTheRowDraws() throws {
        let stripped = try Self.strippedSource("Components/DiscoverFuturesCard.swift")
        XCTAssertTrue(
            stripped.contains(".font(.caption.weight(.bold).monospacedDigit())"),
            "the row's percentage font changed; the model still measures .caption1 bold")
        #if canImport(UIKit)
        let traits = UITraitCollection(preferredContentSizeCategory: .large)
        let drawn = UIFont.preferredFont(forTextStyle: .caption1, compatibleWith: traits)
        XCTAssertEqual(
            FuturesOutcomeRowColumns.percentFont(at: .large).pointSize,
            drawn.pointSize, accuracy: 0.01)
        #endif
    }
}
