import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4107 — the event page's Sources label column.
///
/// The guards below are written against the thing that actually broke: a width
/// that was correct at one text size and wrong at every other. So most of them
/// assert a RELATIONSHIP (the column holds the label it will draw; it grows with
/// Dynamic Type; it never starves the bar) rather than a point count — a test
/// that pins `101` is the 118pt literal again, one layer down.
final class EventSourceLabelColumnTests: XCTestCase {

    /// The five labels a real MLB event draws, from `GET /api/events/15307197`
    /// plus the `betting` row that a pre-game event carries.
    private let productionLabels = [
        "Sportsbooks (19)", "Bain Luck Model", "MLB Model", "Kalshi", "Polymarket",
    ]

    /// A 375pt phone — the narrowest we ship — and a 402pt one.
    private let narrowPhone: Double = 375
    private let widePhone: Double = 402

    // MARK: - The regression itself

    /// The defect, stated as a test: at every text size up to the clamp, the
    /// column is wide enough for the widest label it will draw.
    ///
    /// This is the assertion the 118pt literal failed from xxxLarge on.
    func testTheColumnHoldsItsWidestLabelAtEveryTypeSizeItCanAfford() {
        for typeSize in Self.everyTypeSize {
            let width = EventSourceLabelColumn.width(
                for: productionLabels, availableWidth: narrowPhone, typeSize: typeSize)
            let ceiling = EventSourceLabelColumn.maximumLabelWidth(
                availableWidth: narrowPhone)
            guard width < ceiling else { continue }  // clamped; wrapping takes over

            let widestInk = productionLabels
                .map { EventSourceLabelColumn.textWidth($0, typeSize: typeSize) }
                .max() ?? 0
            XCTAssertGreaterThanOrEqual(
                width, widestInk,
                "at \(typeSize) the column is \(width)pt but the widest label needs \(widestInk)pt")
        }
    }

    /// The old literal, measured — so this file records WHY 118 was wrong and
    /// fails if someone ever reinstates it.
    ///
    /// Deliberately asserts both directions: 118 was genuinely fine at default
    /// (which is why the issue's "it grew from (10) to (14)" story was wrong),
    /// and genuinely too small higher up.
    func testTheOldOneHundredEighteenPointLiteralFitsAtDefaultAndFailsAbove() {
        let atDefault = EventSourceLabelColumn.textWidth(
            "Sportsbooks (14)", typeSize: .large)
        XCTAssertLessThan(
            atDefault, 118,
            "the report blamed the label's length, but at default type size it fit")

        let atXXXLarge = EventSourceLabelColumn.textWidth(
            "Sportsbooks (14)", typeSize: .xxxLarge)
        XCTAssertGreaterThan(
            atXXXLarge, 118 / 0.85,
            "xxxLarge is where it truncated, even with the old 0.85 scale floor")
    }

    /// `Bain Luck Model` is the second casualty the issue never mentioned: it
    /// clears 118 too, one step later. A fix special-cased to `Sportsbooks (N)`
    /// would re-break here.
    func testTheSportsbooksRowIsNotTheOnlyLabelThatOutgrewTheOldColumn() {
        XCTAssertGreaterThan(
            EventSourceLabelColumn.textWidth("Bain Luck Model", typeSize: .accessibility1),
            118)
        let width = EventSourceLabelColumn.width(
            for: ["Bain Luck Model"], availableWidth: widePhone, typeSize: .accessibility1)
        XCTAssertGreaterThanOrEqual(
            width, EventSourceLabelColumn.textWidth("Bain Luck Model", typeSize: .accessibility1))
    }

    // MARK: - Tracking Dynamic Type

    func testTheColumnGrowsWithDynamicTypeUntilItIsClamped() {
        var previous: Double = 0
        for typeSize in Self.everyTypeSize {
            let width = EventSourceLabelColumn.width(
                for: productionLabels, availableWidth: widePhone, typeSize: typeSize)
            XCTAssertGreaterThanOrEqual(
                width, previous, "the column shrank going up to \(typeSize)")
            previous = width
        }
    }

    /// Sized against ink, the column is NARROWER than the old literal at default
    /// — the bar gets that room back on every phone. Worth pinning, because a
    /// future "just make it wider to be safe" change would silently undo it.
    func testAtDefaultTypeSizeTheColumnIsNarrowerThanTheLiteralItReplaced() {
        let width = EventSourceLabelColumn.width(
            for: productionLabels, availableWidth: narrowPhone, typeSize: .large)
        XCTAssertLessThan(width, 118)
        XCTAssertGreaterThan(width, 90, "…but not so narrow it re-breaks the 90pt case")
    }

    // MARK: - The clamp, and what it protects

    /// THE FLOOR IS PINNED TO A LITERAL, AND THAT IS DELIBERATE.
    ///
    /// This test used to assert `barLeft >= EventSourceLabelColumn.minimumBarWidth`
    /// and it could never fail. `width` is clamped by `maximumLabelWidth`, which is
    /// itself `availableWidth - fixedRowCost - minimumBarWidth`, so on the clamped
    /// path `barLeft` EQUALS `minimumBarWidth` by construction — the mutation
    /// moved both sides of the comparison at once. native/079's harness caught it:
    /// `minimumBarWidth 72 -> 0` was the one mutant of fifteen that SURVIVED, and a
    /// zero floor is precisely the regression this test is named for, because it
    /// lets the label consume the whole row and leave the bar nothing.
    ///
    /// So the floor is asserted as a NUMBER. 72pt is a claim about what a reader
    /// can see — below it a two-segment 6pt bar cannot show a split anyone can
    /// read — and a claim about pixels cannot be checked against the variable that
    /// is supposed to encode it. Changing the floor should mean changing this line
    /// and saying why.
    func testTheBarKeepsItsFloorEvenAtTheLargestAccessibilitySize() {
        let width = EventSourceLabelColumn.width(
            for: ["Sportsbooks (100)"], availableWidth: narrowPhone,
            typeSize: .accessibility5)
        let barLeft = narrowPhone - EventSourceLabelColumn.fixedRowCost - width
        XCTAssertGreaterThanOrEqual(barLeft, 72, "the label ate the probability bar")
    }

    /// And the constant itself, so the floor cannot be lowered anywhere else
    /// either. Paired with the test above: that one proves the clamp DELIVERS 72pt
    /// of bar on the worst real row, this one proves 72 is still what the module
    /// promises. Both are needed — the first alone passes if the clamp is removed
    /// and the row happens to be roomy, the second alone passes if the constant is
    /// right but nothing reads it.
    func testTheAdvertisedBarFloorIsStillSeventyTwoPoints() {
        XCTAssertEqual(EventSourceLabelColumn.minimumBarWidth, 72)
    }

    /// The clamp has to actually engage somewhere, or the previous test passes
    /// vacuously on a column that is simply never wide enough to threaten the
    /// bar. This asserts the ELIGIBLE case exists.
    func testTheClampGenuinelyEngagesAtAccessibilitySizesOnANarrowPhone() {
        let ink = EventSourceLabelColumn.textWidth(
            "Sportsbooks (100)", typeSize: .accessibility5)
        let ceiling = EventSourceLabelColumn.maximumLabelWidth(availableWidth: narrowPhone)
        XCTAssertGreaterThan(
            ink, ceiling,
            "no accessibility size on a 375pt phone outgrows the row — the clamp is untested")

        let width = EventSourceLabelColumn.width(
            for: ["Sportsbooks (100)"], availableWidth: narrowPhone,
            typeSize: .accessibility5)
        XCTAssertEqual(width, ceiling, accuracy: 0.001)
    }

    func testAShortLabelSetStillGetsAReadableFloor() {
        let width = EventSourceLabelColumn.width(
            for: ["Kalshi"], availableWidth: narrowPhone, typeSize: .xSmall)
        XCTAssertGreaterThanOrEqual(width, EventSourceLabelColumn.minimumLabelWidth)
    }

    func testAnEmptyTableFallsBackToTheFloorRatherThanZero() {
        let width = EventSourceLabelColumn.width(
            for: [], availableWidth: narrowPhone, typeSize: .large)
        XCTAssertEqual(width, EventSourceLabelColumn.minimumLabelWidth, accuracy: 0.001)
    }

    // MARK: - Before the first layout pass

    /// `availableWidth == 0` is the frame before the `GeometryReader` reports.
    /// The column must use its ink there, not collapse to the floor and snap
    /// wider a frame later.
    func testAnUnmeasuredRowUsesInkRatherThanCollapsingToTheFloor() {
        let width = EventSourceLabelColumn.width(
            for: productionLabels, availableWidth: 0, typeSize: .large)
        let widestInk = productionLabels
            .map { EventSourceLabelColumn.textWidth($0, typeSize: .large) }
            .max() ?? 0
        XCTAssertGreaterThanOrEqual(width, widestInk)
        XCTAssertGreaterThan(width, EventSourceLabelColumn.minimumLabelWidth)
    }

    // MARK: - The row model matches the row

    /// `fixedRowCost` is a claim about `sourceContent`'s modifiers. If someone
    /// changes a padding in the view and not here, the clamp silently starts
    /// protecting the wrong amount of space.
    func testFixedRowCostIsTheSumOfTheRowsOwnConstants() {
        let padding: Double = 16 * 2
        let gaps: Double = 6 * 3
        let numbers: Double = 36 * 2
        XCTAssertEqual(
            EventSourceLabelColumn.fixedRowCost, padding + gaps + numbers, accuracy: 0.001)
    }

    // MARK: - The second list: individual sportsbooks

    /// The books rows draw a plain `.caption` while the source rows draw
    /// `.caption.weight(.medium)`, and the model's contract is that a label is
    /// measured in the face it is drawn in. If `weight:` stopped being honoured
    /// the books column would be measured as medium — wider than it needs to be,
    /// invisibly, in the one direction a width bug never announces itself.
    func testTheRegularFaceMeasuresNarrowerThanTheMediumOne() {
        let label = "betanysportsbook"
        let medium = EventSourceLabelColumn.textWidth(
            label, typeSize: .xxxLarge, weight: .medium)
        let regular = EventSourceLabelColumn.textWidth(
            label, typeSize: .xxxLarge, weight: .regular)
        XCTAssertLessThan(regular, medium)
    }

    /// AN UNMEASURED ROW IS UNCLAMPED, WHICH IS WHY THE PUBLISH SITE MATTERS.
    ///
    /// `maximumLabelWidth` returns `.infinity` for `availableWidth == 0` by
    /// design, so the first layout pass sizes on ink instead of snapping wider a
    /// frame later. The cost of that choice is that a list which NEVER receives a
    /// measurement is not just unstyled — it has lost `minimumBarWidth` entirely.
    ///
    /// The books list shipped in exactly that state: the `GeometryReader` sat
    /// behind the sources list, and the two render under independent conditions,
    /// so an event with sportsbook odds and no aggregate sources (the disclosure
    /// labels it "Individual Sportsbooks") measured 0 forever. This pins the
    /// contract that made it invisible.
    func testAnUnmeasuredRowIsUnclampedSoBothListsMustPublishAWidth() {
        let label = "betanysportsbook"
        let unmeasured = EventSourceLabelColumn.width(
            for: [label], availableWidth: 0, typeSize: .accessibility5, weight: .regular)
        let measured = EventSourceLabelColumn.width(
            for: [label], availableWidth: narrowPhone, typeSize: .accessibility5,
            weight: .regular)
        // Unmeasured takes the whole of the ink; measured yields to the bar.
        XCTAssertGreaterThan(
            unmeasured, measured,
            "an unmeasured row is supposed to be the UNCLAMPED one")
        XCTAssertEqual(
            measured, EventSourceLabelColumn.maximumLabelWidth(availableWidth: narrowPhone),
            accuracy: 0.001, "the measured row should be sitting on the clamp here")
        // And the thing the clamp is for: on the unmeasured row the bar is gone.
        XCTAssertLessThan(
            narrowPhone - EventSourceLabelColumn.fixedRowCost - unmeasured, 72)
    }

    /// The longest real bookmaker name this list draws, at the size that cut it on
    /// a 375pt phone. #4107 shipped its first half with this row still truncating.
    func testTheLongestBookmakerNameFitsTheColumnItIsGiven() {
        let books = ["ballybet", "betanysportsbook", "betmgm", "betonlineag",
                     "betparx", "betrivers", "betus", "bovada", "draftkings", "espnbet"]
        let width = EventSourceLabelColumn.width(
            for: books, availableWidth: narrowPhone, typeSize: .xxxLarge, weight: .regular)
        let widest = books
            .map { EventSourceLabelColumn.textWidth($0, typeSize: .xxxLarge, weight: .regular) }
            .max() ?? 0
        // Not clamped at this size, so the column holds the whole string.
        XCTAssertGreaterThanOrEqual(width, widest)
        XCTAssertLessThanOrEqual(
            width, EventSourceLabelColumn.maximumLabelWidth(availableWidth: narrowPhone))
    }

    // MARK: -

    private static let everyTypeSize: [DynamicTypeSize] = [
        .xSmall, .small, .medium, .large, .xLarge, .xxLarge, .xxxLarge,
        .accessibility1, .accessibility2, .accessibility3, .accessibility4,
        .accessibility5,
    ]
}
