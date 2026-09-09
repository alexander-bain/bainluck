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

    /// THE WIDTH THE PANEL ACTUALLY PUBLISHES — MEASURED, NOT THE SCREEN.
    ///
    /// #4233 — this used to read `375` and `402`, the two phones' screen widths,
    /// and it was wrong in the direction that flatters the code: the Sources
    /// panel is inset inside the event card, so the row it measures is smaller
    /// than the phone. Instrumented at the publish site (`SOURCEROWWIDTH=…` from
    /// `onPreferenceChange`) on event 14780138 at a11y3:
    ///
    ///   - 375pt SE    → **348** (27pt of inset)
    ///   - 402pt phone → **370** (32pt — and note it is NOT the same inset, which
    ///     is why both are measured rather than one derived from the other)
    ///
    /// Every sweep in this file therefore used to test a roomier row than ships,
    /// which is how #4233's first trigger passed its own tests and still left the
    /// real books table truncating at a11y3. A width model checked against a
    /// width nobody renders is the defect this file exists to prevent, one level
    /// up.
    ///
    /// The transient first pass publishes 420 before layout settles; the clamp
    /// simply runs roomy for that frame, which is the same behaviour
    /// `maximumLabelWidth` already documents for an unmeasured row.
    private let narrowRow: Double = 348
    private let wideRow: Double = 370

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

    /// #4233 — the width the INLINE clamp gives, whether or not the model then
    /// reflows the row.
    ///
    /// Several guards below are about the clamp's arithmetic — that it charges
    /// for the numbers, that it engages, that it yields to the bar — and not
    /// about which layout ships. `columns(...)` now answers both questions in one
    /// call, so at the top of the scale it returns a full-width stacked label and
    /// those guards stop describing anything. Asking the clamp directly keeps
    /// each test on its own subject; the layout choice has its own guards below.
    private func inlineLabel(
        _ labels: [String], _ values: [String], _ availableWidth: Double,
        _ typeSize: DynamicTypeSize, _ weight: Font.Weight = .medium
    ) -> Double {
        EventSourceLabelColumn.width(
            for: labels, availableWidth: availableWidth,
            numericWidth: numeric(values, typeSize),
            typeSize: typeSize, weight: weight)
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
                availableWidth: narrowRow, typeSize: typeSize).label
            let ceiling = EventSourceLabelColumn.maximumLabelWidth(
                availableWidth: narrowRow,
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
            availableWidth: wideRow, typeSize: .accessibility1).label
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

        XCTAssertGreaterThan(
            numeric(productionValues, .accessibility5),
            numeric(productionValues, .accessibility4),
            "the numbers must be the thing that grew")
        XCTAssertLessThan(
            inlineLabel(long, productionValues, wideRow, .accessibility5),
            inlineLabel(long, productionValues, wideRow, .accessibility4),
            "a clamped label is supposed to yield the room the numbers took")
    }

    /// Sized against ink, the column is NARROWER than the old literal at default
    /// — the bar gets that room back on every phone. Worth pinning, because a
    /// future "just make it wider to be safe" change would silently undo it.
    func testAtDefaultTypeSizeTheColumnIsNarrowerThanTheLiteralItReplaced() {
        let width = EventSourceLabelColumn.columns(
            labels: productionLabels, values: productionValues,
            availableWidth: narrowRow, typeSize: .large).label
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
            availableWidth: narrowRow, typeSize: .accessibility5)
        XCTAssertGreaterThanOrEqual(
            columns.barWidth(availableWidth: narrowRow), 72,
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
    ///
    /// **#4233 — AND THIS IS WHY THE READER NO LONGER SEES IT.** The trade below
    /// is still exactly what the inline row would make; it is now the evidence
    /// that the inline row is the wrong shape here rather than a description of
    /// what ships. Kept, and asserted against the clamp directly, because the
    /// reflow's whole justification is that this is what it replaces — a later
    /// change that made the inline clamp roomy again should have to come back and
    /// read this.
    func testTheWidestPossiblePairCostsTheBarItsFloorAndThatIsTheTrade() {
        let labels = ["Sportsbooks (100)"]
        let label = inlineLabel(labels, widestValues, narrowRow, .accessibility5)
        let bar = narrowRow
            - EventSourceLabelColumn.fixedRowCost(
                numericWidth: numeric(widestValues, .accessibility5))
            - label

        XCTAssertLessThan(bar, EventSourceLabelColumn.minimumBarWidth)
        // #4233 — this used to assert `bar > 40`, on the reasoning that 49pt
        // still reads as a split. Measured against the row the panel actually
        // publishes (348pt, not the 375pt screen this file used to sweep) the
        // inline bar here is 22pt, not 49. So the trade #4208 recorded was worse
        // than #4208 could see, and the floor that matters is only that the
        // arithmetic stays positive — a NEGATIVE bar is a silent overflow, which
        // is the failure `testTheBarNeverGoesNegative…` below owns.
        XCTAssertGreaterThan(bar, 0, "the inline row over-subscribes outright")
        XCTAssertLessThan(
            bar, 40,
            "22pt of bar is the measured cost of staying inline here — if this row "
                + "has become roomy, re-read whether the reflow is still earning its place")
        XCTAssertEqual(
            label, EventSourceLabelColumn.minimumLabelWidth, accuracy: 0.001,
            "the label is supposed to have yielded everything first")
    }

    /// #4233 — SO THE ROW STACKS, AND BOTH SIDES OF THAT TRADE COME BACK.
    ///
    /// The pair to the test above, on the identical render: the model reflows,
    /// the label goes from its 60pt floor to the full 343pt line, and the bar
    /// goes from 49pt — under the floor — to 115pt, comfortably over it. This is
    /// the assertion that the reflow was worth making; the previous test is the
    /// assertion that it was necessary.
    func testTheReflowGivesBackBothSidesOfThatTrade() {
        let columns = EventSourceLabelColumn.columns(
            labels: ["Sportsbooks (100)"], values: widestValues,
            availableWidth: narrowRow, typeSize: .accessibility5)

        XCTAssertEqual(columns.layout, .stacked)
        XCTAssertGreaterThan(
            columns.barWidth(availableWidth: narrowRow),
            EventSourceLabelColumn.minimumBarWidth,
            "the reflow is supposed to lift the bar back over its floor, not just move it")
        XCTAssertGreaterThan(
            columns.label,
            inlineLabel(["Sportsbooks (100)"], widestValues, narrowRow, .accessibility5),
            "and the label is supposed to be wider than the clamp it escaped")
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
                    labels: labels, values: widestValues, availableWidth: narrowRow,
                    typeSize: typeSize, weight: weight)
                XCTAssertGreaterThan(
                    columns.barWidth(availableWidth: narrowRow), 0,
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
            availableWidth: narrowRow,
            numericWidth: numeric(productionValues, .accessibility5))
        XCTAssertGreaterThan(
            ink, ceiling,
            "no accessibility size on a 375pt phone outgrows the row — the clamp is untested")

        XCTAssertEqual(
            inlineLabel(["Sportsbooks (100)"], productionValues, narrowRow, .accessibility5),
            ceiling, accuracy: 0.001)
    }

    func testAShortLabelSetStillGetsAReadableFloor() {
        let width = EventSourceLabelColumn.columns(
            labels: ["Kalshi"], values: productionValues,
            availableWidth: narrowRow, typeSize: .xSmall).label
        XCTAssertGreaterThanOrEqual(width, EventSourceLabelColumn.minimumLabelWidth)
    }

    func testAnEmptyTableFallsBackToTheFloorRatherThanZero() {
        let width = EventSourceLabelColumn.columns(
            labels: [], values: productionValues,
            availableWidth: narrowRow, typeSize: .large).label
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
    ///
    /// #4233 — both branches are asserted, and the sweep is checked to visit
    /// both. A version of this test that only knew about `.inline` would pass on
    /// a build where the reflow never engages, which is the one regression it is
    /// worth having.
    func testTheColumnsPairIsInternallyConsistent() {
        var seen = Set<EventSourceLabelColumn.RowLayout>()
        for typeSize in Self.everyTypeSize {
            let columns = EventSourceLabelColumn.columns(
                labels: productionLabels, values: productionValues,
                availableWidth: narrowRow, typeSize: typeSize)
            seen.insert(columns.layout)
            XCTAssertEqual(
                columns.numeric, numeric(productionValues, typeSize), accuracy: 0.001)

            switch columns.layout {
            case .inline:
                XCTAssertEqual(
                    columns.fixedRowCost,
                    EventSourceLabelColumn.fixedRowCost(numericWidth: columns.numeric),
                    accuracy: 0.001)
                XCTAssertEqual(
                    columns.barWidth(availableWidth: narrowRow),
                    narrowRow - columns.fixedRowCost - columns.label, accuracy: 0.001)
            case .stacked:
                // One gap fewer, and the label is on the line above rather than
                // subtracted from this one.
                XCTAssertEqual(
                    columns.fixedRowCost,
                    EventSourceLabelColumn.stackedFixedRowCost(numericWidth: columns.numeric),
                    accuracy: 0.001)
                XCTAssertEqual(
                    columns.barWidth(availableWidth: narrowRow),
                    narrowRow - columns.fixedRowCost, accuracy: 0.001)
            }
        }
        XCTAssertEqual(
            seen, [.inline, .stacked],
            "the five-source table on a 375pt phone is supposed to use BOTH layouts "
                + "across the type scale — this sweep asserted only \(seen)")
    }

    // MARK: - #4233 — the reflow

    /// The ten rows `bookmakerContent` draws on event 14780138 (NE vs SEA), in
    /// the order it draws them.
    ///
    /// Captured from the frame rather than invented, because the first version of
    /// this sweep used a six-name subset that happened to exclude
    /// `betanysportsbook` and `betonlineag` — the two longest — and therefore
    /// exercised a roomier table than the one that ships.
    /// `betanysports`, not `betanysportsbook`: the stacked frame prints it in
    /// full and there is no ellipsis on it. The longer spelling is a real label
    /// on other events — `testTheLongestBookmakerNameFitsTheColumnItIsGiven`
    /// owns it — but writing it here would make this list a composite of two
    /// tables while claiming to be one, which is how a fixture starts flattering
    /// the code.
    private static let productionBooks = [
        "ballybet", "betanysports", "betmgm", "betonlineag", "betparx",
        "betrivers", "betus", "bovada", "draftkings", "fanatics",
    ]

    /// Every label set either list draws, on every phone we ship, at every size.
    private static let everyList: [(name: String, labels: [String], weight: Font.Weight)] = [
        ("sources", ["Sportsbooks (19)", "Bain Luck Model", "MLB Model", "Kalshi", "Polymarket"],
         .medium),
        ("sources, worst case", ["Sportsbooks (100)"], .medium),
        ("books", productionBooks, .regular),
        ("books, short", ["betrivers", "betus", "bovada", "draftkings", "fanatics", "lowvig"],
         .regular),
        ("books, worst case", ["betanysportsbook"], .regular),
    ]

    /// How many lines `label` needs in the width the model actually gives it.
    private func linesDrawn(
        _ label: String, _ columns: EventSourceLabelColumn.Columns,
        _ typeSize: DynamicTypeSize, _ weight: Font.Weight
    ) -> Int {
        EventSourceLabelColumn.labelLineCount(
            label, width: columns.label, typeSize: typeSize, weight: weight)
    }

    /// THE REGRESSION, STATED END TO END: NO LABEL EVER TRUNCATES.
    ///
    /// This is the assertion #4208's build fails. The file promised "a long label
    /// takes two lines; it does not truncate", and photographed at a11y5 it read
    /// `be-tri…` / `bo-va…` / `draf tki…`. Measured with UIKit's own line
    /// breaking at the width the model hands the column, the five-source table on
    /// a 375pt phone needs 3 lines at a11y3 and 5 at a11y5.
    ///
    /// Deliberately says nothing about WHICH layout delivers this. It is the
    /// reader's outcome, so it survives any future change to how the row decides
    /// its shape — including replacing the reflow with something better.
    ///
    /// The limit is written as the literal `2` rather than `maximumLabelLines`
    /// for the reason `testTheAdvertisedBarFloorIsStillSeventyTwoPoints` gives:
    /// this is a claim about what a reader can see, and it cannot be checked
    /// against the variable that is supposed to encode it.
    func testNoLabelTruncatesOnAnyPhoneAtAnyTypeSize() {
        for width in [narrowRow, wideRow] {
            for list in Self.everyList {
                for typeSize in Self.everyTypeSize {
                    let columns = EventSourceLabelColumn.columns(
                        labels: list.labels, values: widestValues, availableWidth: width,
                        typeSize: typeSize, weight: list.weight)
                    for label in list.labels {
                        XCTAssertLessThanOrEqual(
                            linesDrawn(label, columns, typeSize, list.weight), 2,
                            "\(label) truncates in the \(list.name) list at \(typeSize) "
                                + "on a \(Int(width))pt phone — \(columns.layout), "
                                + "column \(columns.label)pt")
                    }
                }
            }
        }
    }

    /// The eligible case, asserted rather than assumed: the sweep above passes
    /// vacuously on a build where no row was ever in trouble. This pins that the
    /// inline layout GENUINELY fails on a real render — the specimen Alex would
    /// see — so the test above is measuring a rescue and not a calm.
    func testTheInlineLayoutGenuinelyTruncatesWhereTheReflowRescuesIt() {
        let books = Self.everyList[2]
        let inline = inlineLabel(
            books.labels, widestValues, narrowRow, .accessibility5, books.weight)
        let worstInline = books.labels.map {
            EventSourceLabelColumn.labelLineCount(
                $0, width: inline, typeSize: .accessibility5, weight: books.weight)
        }.max() ?? 0
        XCTAssertGreaterThan(
            worstInline, EventSourceLabelColumn.maximumLabelLines,
            "the inline row no longer over-subscribes on a 375pt phone at a11y5 — "
                + "the reflow is untested and this whole section may be dead")

        let columns = EventSourceLabelColumn.columns(
            labels: books.labels, values: widestValues, availableWidth: narrowRow,
            typeSize: .accessibility5, weight: books.weight)
        XCTAssertEqual(columns.layout, .stacked)
    }

    /// THE LINE COUNT MODELS HYPHENATION, BECAUSE `Text` DOES.
    ///
    /// The photographed miss, pinned as its own case. On event 14780138 at a11y3
    /// the books clamp is 131pt, and in that column `betanysportsbook` is TWO
    /// lines to `boundingRect` with no paragraph style — it breaks the word by
    /// character — and THREE as SwiftUI actually draws it, which hyphenates. The
    /// first version of this trigger asked the unhyphenated question, concluded
    /// the row fit, and shipped a frame reading `be-` / `tanys…` beneath four
    /// visibly hyphenated neighbours (`bally-bet`, `beton-lineag`, `bet-parx`).
    ///
    /// A hard 3 rather than "more than the limit": the whole failure was an
    /// off-by-one-line, so a test that would pass at 4 would have passed at 2.
    func testTheLineCountAgreesWithTheHyphenationSwiftUIPerforms() {
        XCTAssertEqual(
            EventSourceLabelColumn.labelLineCount(
                "betanysportsbook", width: 131, typeSize: .accessibility3, weight: .regular),
            3,
            "the line count has stopped modelling hyphenation — it will read this "
                + "label as fitting and leave the row inline, which is #4233's own miss")
    }

    /// And the sweep visits that exact render, so the case above cannot become
    /// unreachable while still passing on its hardcoded width.
    func testTheProductionBooksTableReflowsAtTheSizeItWasPhotographedTruncating() {
        let columns = EventSourceLabelColumn.columns(
            labels: Self.productionBooks, values: ["37%", "63%"],
            availableWidth: narrowRow, typeSize: .accessibility3, weight: .regular)
        XCTAssertEqual(
            columns.layout, .stacked,
            "this is the render in artifacts-native-081/AFTER-4233-sources-a11y3.png, "
                + "where `betanysportsbook` truncated inline")
    }

    /// THE LINE COUNT MEASURES IN THE FACE IT IS HANDED.
    ///
    /// Found by mutation: measuring the books list in the sources list's medium
    /// face survived every guard above. It over-counts, so it only ever reflows
    /// MORE — safe-looking, invisible, and the exact direction #4107's own
    /// docstring warns about, because a row that stacks when it did not need to
    /// costs the reader a line of height for nothing.
    ///
    /// Asserted as the relationship rather than two point counts: the same label
    /// in the same column needs at least as many lines in the heavier face, and
    /// somewhere in the sweep it needs strictly more.
    func testTheLineCountHonoursTheWeightItIsGiven() {
        var strictlyMore = 0
        for label in Self.productionBooks + ["betanysportsbook", "Sportsbooks (100)"] {
            for typeSize in Self.everyTypeSize {
                for width in [80.0, 110.0, 131.0, 160.0] {
                    let regular = EventSourceLabelColumn.labelLineCount(
                        label, width: width, typeSize: typeSize, weight: .regular)
                    let medium = EventSourceLabelColumn.labelLineCount(
                        label, width: width, typeSize: typeSize, weight: .medium)
                    XCTAssertLessThanOrEqual(
                        regular, medium,
                        "\(label) at \(typeSize) in \(width)pt needs FEWER lines in the "
                            + "heavier face — the weight is not reaching the measurement")
                    if regular < medium { strictlyMore += 1 }
                }
            }
        }
        XCTAssertGreaterThan(
            strictlyMore, 0,
            "the two faces never differ anywhere in this sweep — `weight:` is being "
                + "ignored and the assertion above is vacuous")
    }

    /// THE STACKED LABEL LINE FITS INSIDE THE ROW IT IS DRAWN IN.
    ///
    /// Also found by mutation: dropping the padding from `labelLineWidth` gives
    /// the label the row's whole width, which every "does it fit in two lines?"
    /// guard is happy with — a wider column always fits — while the view draws it
    /// 32pt past the padding it sits inside. A width guard that only ever checks
    /// for TOO NARROW cannot see an overflow.
    func testTheStackedLabelLineStaysInsideTheRowsPadding() {
        for width in [narrowRow, wideRow, 700] {
            XCTAssertLessThanOrEqual(
                EventSourceLabelColumn.labelLineWidth(availableWidth: width),
                width - EventSourceLabelColumn.horizontalPadding * 2,
                "the stacked label line overflows the row's own padding at \(width)pt")
        }
    }

    /// The stacked row has three children and therefore two gaps.
    ///
    /// Pinned to the literal for the reason the bar floor is: the internal
    /// consistency test compares `Columns.fixedRowCost` against
    /// `stackedFixedRowCost`, so a change to the count moves both sides at once
    /// and that test cannot see it (native/079's surviving mutant, again).
    func testTheStackedRowHasOneGapFewerThanTheInlineRow() {
        XCTAssertEqual(EventSourceLabelColumn.stackedInterColumnGapCount, 2)
        XCTAssertEqual(
            EventSourceLabelColumn.stackedFixedRowCost(numericWidth: 40),
            EventSourceLabelColumn.fixedRowCost(numericWidth: 40)
                - EventSourceLabelColumn.interColumnSpacing,
            accuracy: 0.001,
            "the label left the line, so exactly one gap should have left with it")
    }

    /// WHY AN UNMEASURED ROW CANNOT REFLOW, stated so the guard that says so is
    /// not resting on luck.
    ///
    /// `columns(...)` has an `availableWidth > 0` clause on the reflow, and
    /// mutation shows removing it changes nothing — an EQUIVALENT mutant, which
    /// is worth writing down rather than leaving as an unexplained survivor. The
    /// reason: an unmeasured row is clamped by `.infinity`, so its label column
    /// IS its ink, and a label always fits its own ink on one line. The clause is
    /// belt and braces over that invariant, and this is the invariant.
    func testAnUnmeasuredRowsLabelIsAlwaysOneLineWhichIsWhyItCannotReflow() {
        for list in Self.everyList {
            for typeSize in Self.everyTypeSize {
                let columns = EventSourceLabelColumn.columns(
                    labels: list.labels, values: widestValues, availableWidth: 0,
                    typeSize: typeSize, weight: list.weight)
                XCTAssertEqual(columns.layout, .inline)
                for label in list.labels {
                    XCTAssertEqual(
                        linesDrawn(label, columns, typeSize, list.weight), 1,
                        "\(label) needs more than one line at its own ink width — the "
                            + "invariant behind the unmeasured-row guard has broken")
                }
            }
        }
    }

    /// And the advertised limit itself, so it cannot be raised somewhere else to
    /// make the sweep pass. Same shape and same reason as the bar floor's pin: a
    /// three-line label in a table of six rows is a wall of text, not a table.
    func testTheAdvertisedLabelLineLimitIsStillTwo() {
        XCTAssertEqual(EventSourceLabelColumn.maximumLabelLines, 2)
    }

    /// THE TRIGGER IS MEASURED, NOT A SIZE THRESHOLD.
    ///
    /// The obvious implementation is `dynamicTypeSize >= .accessibility1`, and it
    /// would be this file's original bug written a third time — a constant that
    /// is right for one text size on one screen width. The proof that it is not
    /// one: on identical text sizes the two phones we ship DISAGREE about whether
    /// the same list reflows, because 27 more points of row is enough to keep the
    /// books table inside two lines all the way up the scale.
    ///
    /// A threshold implementation cannot produce this and would fail here.
    /// Stated as the property rather than as two pinned cells, deliberately.
    ///
    /// The first version of this test named the one render where the phones then
    /// disagreed, and modelling hyphenation moved it — a guard that has to be
    /// re-pinned every time the measurement improves is a guard that gets
    /// re-pinned without being read. What must hold is that the two widths
    /// disagree SOMEWHERE, and that is what a threshold implementation cannot do.
    func testTheReflowPointDependsOnTheWidthAndNotOnlyTheTypeSize() {
        var disagreements = 0
        for list in Self.everyList {
            for typeSize in Self.everyTypeSize {
                func layout(_ width: Double) -> EventSourceLabelColumn.RowLayout {
                    EventSourceLabelColumn.columns(
                        labels: list.labels, values: ["49%", "51%"], availableWidth: width,
                        typeSize: typeSize, weight: list.weight).layout
                }
                // More room never causes a reflow. A trigger with its comparison
                // the wrong way round would still disagree across widths, so the
                // count below is not enough on its own.
                if layout(narrowRow) == .inline {
                    XCTAssertEqual(
                        layout(wideRow), .inline,
                        "\(list.name) at \(typeSize) stacks on the WIDER phone while the "
                            + "narrower one holds it inline — the trigger's comparison "
                            + "is inverted")
                }
                if layout(narrowRow) != layout(wideRow) { disagreements += 1 }
            }
        }
        XCTAssertGreaterThan(
            disagreements, 0,
            "the two phones we ship never disagree about a single render — the "
                + "trigger has stopped reading the width and is a size threshold")
    }

    /// And it depends on the LABELS, not only on the geometry: the same row, same
    /// phone, same size, reflows for a table of long names and not for a table of
    /// short ones. A trigger that ignored the strings would answer both alike.
    func testTheReflowPointDependsOnTheLabelsThemselves() {
        func layout(_ labels: [String]) -> EventSourceLabelColumn.RowLayout {
            EventSourceLabelColumn.columns(
                labels: labels, values: ["49%", "51%"], availableWidth: narrowRow,
                typeSize: .accessibility5, weight: .regular).layout
        }
        XCTAssertEqual(layout(["draftkings"]), .stacked)
        XCTAssertEqual(layout(["bet"]), .inline, "a short table has no reason to reflow")
    }

    /// One decision for the whole list, not per row.
    ///
    /// Rows that each chose their own shape would give a table with a ragged edge
    /// down it — a stacked row directly above an inline one reads as a rendering
    /// fault, not as a considered layout. So the widest label decides for every
    /// row, which is exactly what a single `Columns` per list buys.
    func testOneLongLabelReflowsTheWholeTableIncludingItsShortRows() {
        let mixed = ["Kalshi", "Polymarket", "Sportsbooks (100)"]
        let columns = EventSourceLabelColumn.columns(
            labels: mixed, values: widestValues, availableWidth: narrowRow,
            typeSize: .accessibility5)
        XCTAssertEqual(columns.layout, .stacked)
        // `Kalshi` would have been comfortable inline; it stacks anyway, and it
        // gets the same full line as the label that forced the decision.
        XCTAssertEqual(
            columns.label,
            EventSourceLabelColumn.labelLineWidth(availableWidth: narrowRow),
            accuracy: 0.001)
    }

    /// The reflow's payoff for the bar, swept: wherever the row stacks, the bar
    /// is not merely present but back over the floor the inline row had given up.
    func testTheStackedBarClearsTheFloorTheInlineRowHadToGiveUp() {
        var stackedCases = 0
        for width in [narrowRow, wideRow] {
            for list in Self.everyList {
                for typeSize in Self.everyTypeSize {
                    let columns = EventSourceLabelColumn.columns(
                        labels: list.labels, values: widestValues, availableWidth: width,
                        typeSize: typeSize, weight: list.weight)
                    guard columns.layout == .stacked else { continue }
                    stackedCases += 1
                    XCTAssertGreaterThanOrEqual(
                        columns.barWidth(availableWidth: width), 72,
                        "a stacked row is supposed to have room for its bar — "
                            + "\(list.name) at \(typeSize) on \(Int(width))pt")
                }
            }
        }
        XCTAssertGreaterThan(stackedCases, 0, "no row stacked — the sweep proved nothing")
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
            labels: [label], values: productionValues, availableWidth: narrowRow,
            typeSize: .accessibility5, weight: .regular)
        // Unmeasured takes the whole of the ink; measured yields to the bar.
        //
        // #4233 — asked of the clamp rather than of `measured.label`, because at
        // a11y5 this row reflows and its label is then the full line, which is
        // WIDER than the unmeasured ink and would read as the clamp having
        // vanished. The clamp is still there and still doing this; it is the
        // layout on top of it that changed.
        XCTAssertGreaterThan(
            unmeasured.label,
            inlineLabel([label], productionValues, narrowRow, .accessibility5, .regular),
            "an unmeasured row is supposed to be the UNCLAMPED one")
        XCTAssertEqual(
            inlineLabel([label], productionValues, narrowRow, .accessibility5, .regular),
            EventSourceLabelColumn.maximumLabelWidth(
                availableWidth: narrowRow, numericWidth: measured.numeric),
            accuracy: 0.001, "the measured row should be sitting on the clamp here")
        // And the thing the clamp is for: on the unmeasured row the bar is gone.
        XCTAssertLessThan(unmeasured.barWidth(availableWidth: narrowRow), 72)
        XCTAssertEqual(
            unmeasured.layout, .inline,
            "an unmeasured row must not reflow — a first frame that stacks and then "
                + "snaps inline is a visible flicker")
    }

    /// The longest real bookmaker name this list draws, at the size that cut it on
    /// a 375pt phone. #4107 shipped its first half with this row still truncating.
    func testTheLongestBookmakerNameFitsTheColumnItIsGiven() {
        let books = ["ballybet", "betanysportsbook", "betmgm", "betonlineag",
                     "betparx", "betrivers", "betus", "bovada", "draftkings", "espnbet"]
        let columns = EventSourceLabelColumn.columns(
            labels: books, values: productionValues, availableWidth: narrowRow,
            typeSize: .xxxLarge, weight: .regular)
        let widest = books
            .map { EventSourceLabelColumn.textWidth($0, typeSize: .xxxLarge, weight: .regular) }
            .max() ?? 0
        // Not clamped at this size, so the column holds the whole string.
        XCTAssertGreaterThanOrEqual(columns.label, widest)
        XCTAssertLessThanOrEqual(
            columns.label,
            EventSourceLabelColumn.maximumLabelWidth(
                availableWidth: narrowRow, numericWidth: columns.numeric))
    }

    // MARK: -

    private static let everyTypeSize: [DynamicTypeSize] = [
        .xSmall, .small, .medium, .large, .xLarge, .xxLarge, .xxxLarge,
        .accessibility1, .accessibility2, .accessibility3, .accessibility4,
        .accessibility5,
    ]
}
