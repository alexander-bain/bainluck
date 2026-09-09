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

    /// The probability strings a real five-source row prints. Passed explicitly
    /// everywhere rather than defaulted, because #4208 was exactly the bug of a
    /// numeric width that nobody at a call site had to think about.
    private let productionValues = ["43%", "57%", "44%", "56%", "41%", "59%"]

    /// The widest pair `formatProbability` can return — its `<1%` / `>99%`
    /// guards, not a hypothetical `100%`.
    private let widestValues = [">99%", "<1%"]

    /// The numeric width for a given render, so tests can state the coupling
    /// instead of re-deriving it.
    private func numeric(_ values: [String], _ typeSize: DynamicTypeSize) -> Double {
        EventSourceLabelColumn.numericColumnWidth(for: values, typeSize: typeSize)
    }

    // MARK: - The regression itself

    /// The defect, stated as a test: at every text size up to the clamp, the
    /// column is wide enough for the widest label it will draw.
    ///
    /// This is the assertion the 118pt literal failed from xxxLarge on.
    func testTheColumnHoldsItsWidestLabelAtEveryTypeSizeItCanAfford() {
        for typeSize in Self.everyTypeSize {
            let width = EventSourceLabelColumn.columns(
                labels: productionLabels, values: productionValues,
                availableWidth: narrowPhone, typeSize: typeSize).label
            let ceiling = EventSourceLabelColumn.maximumLabelWidth(
                availableWidth: narrowPhone,
                numericWidth: numeric(productionValues, typeSize))
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
        let width = EventSourceLabelColumn.columns(
            labels: ["Bain Luck Model"], values: productionValues,
            availableWidth: widePhone, typeSize: .accessibility1).label
        XCTAssertGreaterThanOrEqual(
            width, EventSourceLabelColumn.textWidth("Bain Luck Model", typeSize: .accessibility1))
    }

    // MARK: - Tracking Dynamic Type

    /// THE DEMAND grows with Dynamic Type — the label column tracking text size,
    /// which is #4107's whole property, stated on the unclamped value.
    ///
    /// It is asserted on `availableWidth: 0` (the unmeasured, unclamped path)
    /// deliberately. The CLAMPED width is no longer monotonic and must not be
    /// asserted to be — see the test below, which pins the reason.
    func testTheColumnsInkDemandGrowsWithDynamicType() {
        var previous: Double = 0
        for typeSize in Self.everyTypeSize {
            let width = EventSourceLabelColumn.columns(
                labels: productionLabels, values: productionValues,
                availableWidth: 0, typeSize: typeSize).label
            XCTAssertGreaterThanOrEqual(
                width, previous, "the column's demand shrank going up to \(typeSize)")
            previous = width
        }
    }

    /// #4208 CHANGED THIS, AND THE CHANGE IS THE POINT.
    ///
    /// The clamped label column used to grow monotonically with text size. It no
    /// longer does, because the numbers beside it now grow too and they are part
    /// of the cost the label clamps against. Going from a11y4 to a11y5 on a 402pt
    /// phone the numeric columns take ~26pt more and the label's ceiling drops by
    /// exactly that, so a label already sitting on the clamp gets NARROWER.
    ///
    /// That is the declared priority order working (numbers never clamp, the
    /// label yields), not a regression — but it is surprising enough that it is
    /// written down as a test rather than left for someone to rediscover as a
    /// bug. If a future change makes the clamped width monotonic again it has
    /// almost certainly stopped charging for the numbers.
    func testTheClampedColumnYieldsToTheNumbersAtTheTopOfTheScale() {
        let long = ["Sportsbooks (100)"]
        let atFour = EventSourceLabelColumn.columns(
            labels: long, values: productionValues,
            availableWidth: widePhone, typeSize: .accessibility4)
        let atFive = EventSourceLabelColumn.columns(
            labels: long, values: productionValues,
            availableWidth: widePhone, typeSize: .accessibility5)

        XCTAssertGreaterThan(
            atFive.numeric, atFour.numeric,
            "the numbers must be the thing that grew")
        XCTAssertLessThan(
            atFive.label, atFour.label,
            "a clamped label is supposed to yield the room the numbers took")
    }

    /// Sized against ink, the column is NARROWER than the old literal at default
    /// — the bar gets that room back on every phone. Worth pinning, because a
    /// future "just make it wider to be safe" change would silently undo it.
    func testAtDefaultTypeSizeTheColumnIsNarrowerThanTheLiteralItReplaced() {
        let width = EventSourceLabelColumn.columns(
            labels: productionLabels, values: productionValues,
            availableWidth: narrowPhone, typeSize: .large).label
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
        let columns = EventSourceLabelColumn.columns(
            labels: ["Sportsbooks (100)"], values: productionValues,
            availableWidth: narrowPhone, typeSize: .accessibility5)
        XCTAssertGreaterThanOrEqual(
            columns.barWidth(availableWidth: narrowPhone), 72,
            "the label ate the probability bar")
    }

    /// #4208 — AND HERE IS WHERE THAT FLOOR IS GIVEN UP, MEASURED AND ON PURPOSE.
    ///
    /// `>99%` / `<1%` is the widest pair `formatProbability` can return. At a11y5
    /// on a 375pt phone the two numeric columns take 108pt each, which is more
    /// than the row has to give: the label goes to its 60pt floor and the bar is
    /// left with 49pt rather than 72pt.
    ///
    /// The alternative was clamping the numbers, and a clamped number does not
    /// degrade — it wraps to `4` / `9` / `%`, which is the defect, or truncates
    /// to `4…`, which is a DIFFERENT number. So the bar yields last and yields
    /// least often (this pair needs a near-certain game at the largest
    /// accessibility size on the smallest phone). Pinned so the trade is a
    /// decision on record rather than a surprise, and so anyone who widens the
    /// numbers further has to come back here and re-justify the number.
    func testTheWidestPossiblePairCostsTheBarItsFloorAndThatIsTheTrade() {
        let columns = EventSourceLabelColumn.columns(
            labels: ["Sportsbooks (100)"], values: widestValues,
            availableWidth: narrowPhone, typeSize: .accessibility5)
        let bar = columns.barWidth(availableWidth: narrowPhone)

        XCTAssertLessThan(bar, EventSourceLabelColumn.minimumBarWidth)
        XCTAssertGreaterThan(bar, 40, "a bar this short stops reading as a split at all")
        XCTAssertEqual(
            columns.label, EventSourceLabelColumn.minimumLabelWidth, accuracy: 0.001,
            "the label is supposed to have yielded everything first")
    }

    /// AND THE BAR NEVER GOES NEGATIVE, which is the failure the test above is
    /// one step away from: a row whose fixed costs exceed its width does not
    /// report anything, it silently overflows the HStack on a real phone.
    ///
    /// Swept over every text size, both lists' faces, and the widest strings
    /// either column can hold, at the narrowest width we ship.
    func testTheBarSurvivesEveryTypeSizeOnTheNarrowestPhone() {
        let longestBookmaker = ["betanysportsbook"]
        for typeSize in Self.everyTypeSize {
            for (labels, weight) in [
                (["Sportsbooks (100)"], Font.Weight.medium),
                (longestBookmaker, Font.Weight.regular),
            ] {
                let columns = EventSourceLabelColumn.columns(
                    labels: labels, values: widestValues, availableWidth: narrowPhone,
                    typeSize: typeSize, weight: weight)
                XCTAssertGreaterThan(
                    columns.barWidth(availableWidth: narrowPhone), 0,
                    "the row over-subscribes at \(typeSize) for \(labels)")
            }
        }
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
        let ceiling = EventSourceLabelColumn.maximumLabelWidth(
            availableWidth: narrowPhone,
            numericWidth: numeric(productionValues, .accessibility5))
        XCTAssertGreaterThan(
            ink, ceiling,
            "no accessibility size on a 375pt phone outgrows the row — the clamp is untested")

        let width = EventSourceLabelColumn.columns(
            labels: ["Sportsbooks (100)"], values: productionValues,
            availableWidth: narrowPhone, typeSize: .accessibility5).label
        XCTAssertEqual(width, ceiling, accuracy: 0.001)
    }

    func testAShortLabelSetStillGetsAReadableFloor() {
        let width = EventSourceLabelColumn.columns(
            labels: ["Kalshi"], values: productionValues,
            availableWidth: narrowPhone, typeSize: .xSmall).label
        XCTAssertGreaterThanOrEqual(width, EventSourceLabelColumn.minimumLabelWidth)
    }

    func testAnEmptyTableFallsBackToTheFloorRatherThanZero() {
        let width = EventSourceLabelColumn.columns(
            labels: [], values: productionValues,
            availableWidth: narrowPhone, typeSize: .large).label
        XCTAssertEqual(width, EventSourceLabelColumn.minimumLabelWidth, accuracy: 0.001)
    }

    // MARK: - Before the first layout pass

    /// `availableWidth == 0` is the frame before the `GeometryReader` reports.
    /// The column must use its ink there, not collapse to the floor and snap
    /// wider a frame later.
    func testAnUnmeasuredRowUsesInkRatherThanCollapsingToTheFloor() {
        let width = EventSourceLabelColumn.columns(
            labels: productionLabels, values: productionValues,
            availableWidth: 0, typeSize: .large).label
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
    /// The padding and gaps are still literals here — they are literals in the
    /// view too, and this test is what ties the two together. The numeric width
    /// is NOT: #4208 is the discovery that `36 * 2` was the same kind of stale
    /// claim, so it is passed in and the sum is checked against whatever the
    /// model measured.
    func testFixedRowCostIsTheSumOfTheRowsOwnConstants() {
        let padding: Double = 16 * 2
        let gaps: Double = 6 * 3
        let numericWidth = numeric(productionValues, .large)
        XCTAssertEqual(
            EventSourceLabelColumn.fixedRowCost(numericWidth: numericWidth),
            padding + gaps + numericWidth * 2, accuracy: 0.001)
    }

    // MARK: - #4208: the probability columns

    /// THE DEFECT ITSELF: at accessibility sizes a `49%` did not fit its 36pt box
    /// and stacked one glyph per line.
    ///
    /// Asserted against the OLD literal so this file records why 36 was wrong,
    /// and in both directions — 36 was genuinely roomy at default size, which is
    /// why nobody saw this until Alex turned the text up.
    func testTheOldThirtySixPointLiteralFitsAtDefaultAndFailsAtAccessibilitySizes() {
        XCTAssertLessThan(
            EventSourceLabelColumn.numericTextWidth(">99%", typeSize: .large), 36,
            "even the widest string fit the old box at default size")
        XCTAssertGreaterThan(
            EventSourceLabelColumn.numericTextWidth("49%", typeSize: .accessibility1), 36,
            "a plain two-digit percentage already overflows 36pt at a11y1")
        XCTAssertGreaterThan(
            EventSourceLabelColumn.numericTextWidth("49%", typeSize: .accessibility5), 72,
            "at a11y5 it needs more than twice the old box")
    }

    /// The fix, stated: the column holds every number it will draw, at every
    /// text size. This is the assertion the 36pt literal failed from a11y1 on.
    func testTheNumericColumnHoldsEveryNumberItWillDrawAtEveryTypeSize() {
        for typeSize in Self.everyTypeSize {
            for values in [productionValues, widestValues, ["7%", "93%"]] {
                let width = numeric(values, typeSize)
                for value in values {
                    XCTAssertGreaterThanOrEqual(
                        width,
                        EventSourceLabelColumn.numericTextWidth(value, typeSize: typeSize),
                        "at \(typeSize) the column is \(width)pt but \(value) needs more")
                }
            }
        }
    }

    /// Measured in the WRONG face, the column is too narrow — which is how a
    /// width bug hides. `.caption2` is a different text style from the label's
    /// `.caption`/caption1, and reusing `textWidth` here would under-charge every
    /// row at every size.
    func testTheNumbersAreMeasuredInCaptionTwoNotTheLabelsFace() {
        for typeSize in [DynamicTypeSize.large, .accessibility3, .accessibility5] {
            XCTAssertLessThan(
                EventSourceLabelColumn.numericTextWidth("49%", typeSize: typeSize),
                EventSourceLabelColumn.textWidth("49%", typeSize: typeSize, weight: .regular),
                "caption2 must measure narrower than caption1 at \(typeSize)")
        }
    }

    /// Sized to ink the numbers are NARROWER than the old literal at default
    /// size, which hands the bar back ~10pt per row on the phone most people
    /// use. The bug reads as an accessibility-only one and is not.
    func testAtDefaultSizeTheNumbersGiveTheBarRoomBack() {
        let width = numeric(productionValues, .large)
        XCTAssertLessThan(width, 36)
        let reclaimed = (36 - width) * EventSourceLabelColumn.numericColumnCount
        XCTAssertGreaterThan(reclaimed, 10, "the pair should return real room, not a rounding")
    }

    /// A degenerate list draws no numbers at all, and the column must not
    /// collapse to zero: a zero-width numeric column understates `fixedRowCost`
    /// and hands the label a wider clamp than the row actually has, which is the
    /// bar-starving failure one level up.
    func testAListThatDrawsNoNumbersStillReservesATwoDigitColumn() {
        for typeSize in Self.everyTypeSize {
            XCTAssertEqual(
                numeric([], typeSize),
                numeric(["00%"], typeSize), accuracy: 0.001,
                "an empty list should fall back to the two-digit template at \(typeSize)")
            XCTAssertGreaterThan(numeric([], typeSize), 0)
        }
    }

    /// The floor tracks Dynamic Type like everything else here. A literal floor
    /// would be this file's own defect reintroduced one constant over, so the
    /// guard is that it MOVES, not that it equals some number.
    func testTheNumericFloorTracksDynamicTypeRatherThanBeingALiteral() {
        XCTAssertGreaterThan(numeric([], .accessibility5), numeric([], .large) * 2)
    }

    /// Both columns share one width, so the widest string on EITHER side binds
    /// both. A per-column implementation would pass every test above and still
    /// draw two differently-sized boxes for one away–home pair.
    ///
    /// BOTH ORDERINGS, and that is not padding. The first version of this test
    /// listed `>99%` first and a mutation that took `.first` instead of `.max()`
    /// SURVIVED it — the widest string happened to be the one it read. The other
    /// values in this file could not catch it either, because the `00%` floor is
    /// as wide as a three-character percentage and quietly covered the gap. A
    /// test whose worst case is in position zero is testing the position.
    func testOneWidthCoversBothColumnsSoTheWidestSideBindsThePair() {
        for lopsided in [[">99%", "<1%"], ["<1%", ">99%"]] {
            for typeSize in [DynamicTypeSize.large, .accessibility5] {
                let width = numeric(lopsided, typeSize)
                for value in lopsided {
                    XCTAssertGreaterThanOrEqual(
                        width,
                        EventSourceLabelColumn.numericTextWidth(value, typeSize: typeSize),
                        "\(value) did not bind the column in \(lopsided) at \(typeSize)")
                }
            }
        }
    }

    /// THE COLUMN IS STRICTLY WIDER THAN ITS INK, NOT EQUAL TO IT.
    ///
    /// `inkSlack` is what makes that true, and without this test nothing checked
    /// it: every other assertion here is `>=`, which `.rounded(.up)` alone
    /// satisfies. Deleting the slack survived the mutation pass.
    ///
    /// It is load-bearing for the reason written on the constant — `NSString.size`
    /// returns a fractional width and SwiftUI truncates on the fractional
    /// overflow, so a column sized to exactly its measurement can still clip its
    /// own last glyph. A column that merely equals its ink is the bug with a
    /// rounding error in front of it.
    func testTheNumericColumnIsStrictlyWiderThanTheInkItHolds() {
        for typeSize in Self.everyTypeSize {
            for values in [productionValues, widestValues] {
                let width = numeric(values, typeSize)
                let widest = values
                    .map { EventSourceLabelColumn.numericTextWidth($0, typeSize: typeSize) }
                    .max() ?? 0
                XCTAssertGreaterThan(
                    width, widest,
                    "at \(typeSize) the column exactly equals its ink and may clip")
            }
        }
    }

    /// `columns` is the only entry point the view uses, and the coupling it
    /// exists for: the numeric width it returns is the one its own
    /// `fixedRowCost` charged for. If the two ever came from different renders
    /// the clamp would protect the wrong amount of space — silently, since both
    /// numbers would still look plausible.
    func testTheColumnsPairIsInternallyConsistent() {
        for typeSize in Self.everyTypeSize {
            let columns = EventSourceLabelColumn.columns(
                labels: productionLabels, values: productionValues,
                availableWidth: narrowPhone, typeSize: typeSize)
            XCTAssertEqual(
                columns.fixedRowCost,
                EventSourceLabelColumn.fixedRowCost(numericWidth: columns.numeric),
                accuracy: 0.001)
            XCTAssertEqual(
                columns.numeric, numeric(productionValues, typeSize), accuracy: 0.001)
            XCTAssertEqual(
                columns.barWidth(availableWidth: narrowPhone),
                narrowPhone - columns.fixedRowCost - columns.label, accuracy: 0.001)
        }
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
        let unmeasured = EventSourceLabelColumn.columns(
            labels: [label], values: productionValues, availableWidth: 0,
            typeSize: .accessibility5, weight: .regular)
        let measured = EventSourceLabelColumn.columns(
            labels: [label], values: productionValues, availableWidth: narrowPhone,
            typeSize: .accessibility5, weight: .regular)
        // Unmeasured takes the whole of the ink; measured yields to the bar.
        XCTAssertGreaterThan(
            unmeasured.label, measured.label,
            "an unmeasured row is supposed to be the UNCLAMPED one")
        XCTAssertEqual(
            measured.label,
            EventSourceLabelColumn.maximumLabelWidth(
                availableWidth: narrowPhone, numericWidth: measured.numeric),
            accuracy: 0.001, "the measured row should be sitting on the clamp here")
        // And the thing the clamp is for: on the unmeasured row the bar is gone.
        XCTAssertLessThan(unmeasured.barWidth(availableWidth: narrowPhone), 72)
    }

    /// The longest real bookmaker name this list draws, at the size that cut it on
    /// a 375pt phone. #4107 shipped its first half with this row still truncating.
    func testTheLongestBookmakerNameFitsTheColumnItIsGiven() {
        let books = ["ballybet", "betanysportsbook", "betmgm", "betonlineag",
                     "betparx", "betrivers", "betus", "bovada", "draftkings", "espnbet"]
        let columns = EventSourceLabelColumn.columns(
            labels: books, values: productionValues, availableWidth: narrowPhone,
            typeSize: .xxxLarge, weight: .regular)
        let widest = books
            .map { EventSourceLabelColumn.textWidth($0, typeSize: .xxxLarge, weight: .regular) }
            .max() ?? 0
        // Not clamped at this size, so the column holds the whole string.
        XCTAssertGreaterThanOrEqual(columns.label, widest)
        XCTAssertLessThanOrEqual(
            columns.label,
            EventSourceLabelColumn.maximumLabelWidth(
                availableWidth: narrowPhone, numericWidth: columns.numeric))
    }

    // MARK: -

    private static let everyTypeSize: [DynamicTypeSize] = [
        .xSmall, .small, .medium, .large, .xLarge, .xxLarge, .xxxLarge,
        .accessibility1, .accessibility2, .accessibility3, .accessibility4,
        .accessibility5,
    ]
}
