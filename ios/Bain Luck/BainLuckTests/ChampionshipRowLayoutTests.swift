import XCTest
import SwiftUI
@testable import Bain_Luck

/// #3574 and #3580: a Championship Path row that broke its own words at one end
/// and drew a 0 pt progress bar at the other, because its two fixed columns and
/// their gaps added up to exactly the card's whole width.
///
/// The numbers these tests pin are measured, not chosen. They come from
/// `artifacts-native-038/AFTER-mlb-15305463-s900.png` — Brewers @ Reds, event
/// 15305463, iPhone 17 (402 pt, scale exactly 3.0), shot against production on
/// 2026-09-06 — by scanning the PNG for the card background rectangle:
///
/// * the two team cards span x = 3.0 … 398.7 pt, so the pair occupies 396.0 pt
/// * each card is 190.0 pt wide, with a 16.0 pt gap between them
/// * `teamCard`'s `.padding(12)` leaves each row 166.0 pt
/// * the three Brewers bars — 99.6%, 96.2% and 13.4% — all measured 2.00 pt
///   wide, all starting at x = 103.0 pt (= 3 + 12 + 80 + 8)
final class ChampionshipRowLayoutTests: XCTestCase {

    // MARK: - Fixtures

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func stageJSON(
        _ key: String, _ label: String, probability: Double?, trend: Double? = nil
    ) -> String {
        let trendPart = trend.map { #", "trend_24h": \#($0)"# } ?? ""
        let probPart = probability.map { "\($0)" } ?? "null"
        return #"{"key": "\#(key)", "label": "\#(label)", "probability": \#(probPart)\#(trendPart)}"#
    }

    private func stage(
        _ key: String, _ label: String, probability: Double?, trend: Double? = nil
    ) throws -> ProgressionStageData {
        try decoder().decode(
            ProgressionStageData.self,
            from: Data(stageJSON(key, label, probability: probability, trend: trend).utf8))
    }

    /// The Brewers card as production served it (`/api/events/15305463/team-progression`,
    /// read 2026-09-06). "Make Playoffs" is the clinched-and-moved row that broke.
    private func brewersStages() throws -> [ProgressionStageData] {
        [
            try stage("make_playoffs", "Make Playoffs", probability: 0.996, trend: 0.9133),
            try stage("division", "Division", probability: 0.9615, trend: -0.0258),
            try stage("pennant", "AL / NL Champ", probability: 0.2303, trend: 0.0054),
            try stage("championship", "World Series", probability: 0.134, trend: 0.0039),
        ]
    }

    /// The Reds card from the same payload: no row clinched, so nothing about
    /// this card's badge column may move.
    private func redsStages() throws -> [ProgressionStageData] {
        [
            try stage("make_playoffs", "Make Playoffs", probability: 0.0088, trend: 0.0078),
            try stage("division", "Division", probability: 0.0055, trend: 0.0045),
            try stage("pennant", "AL / NL Champ", probability: 0.0005, trend: 0.0),
            try stage("championship", "World Series", probability: 0.0005, trend: 0.0005),
        ]
    }

    // MARK: - The measurement the photographs pin

    /// The card the fix produces, measured off `artifacts-native-039/`: the pair
    /// of cards spans x = 31.7 … 370.0 pt (338.3 pt) inside the page's 16 pt
    /// padding, each card is 161.5 pt, and each row has 137.3 pt.
    func testTeamCardContentWidthReproducesTheMeasuredProductionCard() {
        let content = ChampionshipRowLayout.teamCardContentWidth(
            totalWidth: 338.3, cardCount: 2)
        XCTAssertEqual(
            content, 137.15, accuracy: 0.5,
            "the formula must land on the 137.3 pt measured off the live render. "
            + "A fit formula that drops the 16 pt gap or the 24 pt of padding is "
            + "how the row came to believe it had room for a bar.")

        // A single card takes the whole width — no gap to subtract.
        XCTAssertEqual(
            ChampionshipRowLayout.teamCardContentWidth(totalWidth: 338.3, cardCount: 1),
            314.3, accuracy: 0.01)
    }

    /// The defect itself, stated as arithmetic.
    ///
    /// The old card was 190.0 pt wide (measured off
    /// `artifacts-native-038/AFTER-mlb-15305463-s900.png`) for a circular reason:
    /// the row's fixed columns *demanded* 166 pt, so the card became 166 + 24 of
    /// padding, and two of those plus the gap came to 396 pt inside a 338.3 pt
    /// space. The card did not starve the row — the row inflated the card past
    /// the screen and then had nothing left over for itself.
    func testTheOldFixedColumnsConsumedEverythingTheyDemanded() {
        // 70 is written out rather than read from `valueBadgeWidth`: this test
        // is about the column that shipped, and it must keep describing that
        // column after the constant moves.
        let oldRowSpend = ChampionshipRowLayout.labelWidth          // 80
            + ChampionshipRowLayout.spacing                          //  8
            + ChampionshipRowLayout.spacing                          //  8
            + 70                                                     // the old badge column
        XCTAssertEqual(
            oldRowSpend, 166.0, accuracy: 0.01,
            "80 + 8 + 8 + 70 leaves the bar exactly nothing out of the 166 pt the "
            + "row itself demanded, which is why the GeometryReader was offered "
            + "0.0 pt and every bar drew the 2 pt floor — 99.6% and 13.4% alike "
            + "(#3580).")
    }

    // MARK: - The rule

    /// The real card width, not the one the broken layout inflated itself to.
    private let productionContentWidth: CGFloat = 137.3

    func testBothProductionCardsStackAtIPhoneWidth() throws {
        let brewers = try brewersStages()
        let reds = try redsStages()

        XCTAssertTrue(
            ChampionshipRowLayout.stacksBelowLabel(
                contentWidth: productionContentWidth, stages: brewers),
            "the clinched card cannot hold label + bar + 'clinched' on one line "
            + "at 137.3 pt (#3574)")
        XCTAssertTrue(
            ChampionshipRowLayout.stacksBelowLabel(
                contentWidth: productionContentWidth, stages: reds),
            "nor can an ordinary card: 80 + 8 + 36 + 8 + 76 = 208 > 137.3. The bar "
            + "was dead on every card, not only the clinched one (#3580).")
    }

    /// What the bar actually gets, checked against what the live render drew.
    ///
    /// Note what is NOT claimed: at 137.3 pt even the stacked shape cannot reach
    /// the 33.4 pt at which a bar resolves one percentage point, and the rule is
    /// not pretending otherwise — it hands the bar everything the card has and
    /// the card is small. 29 pt separates 13% from 96% plainly; it does not
    /// separate 96% from 99.6%, which is why both of those draw within a point
    /// of each other. That is a card-size question, not a layout-rule one.
    func testStackingGivesBothProductionCardsARealBar() throws {
        let brewersBar = ChampionshipRowLayout.barWidth(
            contentWidth: productionContentWidth, stages: try brewersStages())
        let redsBar = ChampionshipRowLayout.barWidth(
            contentWidth: productionContentWidth, stages: try redsStages())

        // Measured off artifacts-native-039/AFTER-mlb-15305463-s900.png: the
        // Brewers' clinched bar rendered 29.00 pt and the Reds' track ~52.4 pt.
        //
        // 🔴 THE BREWERS NUMBER MOVED WITH #4108, AND UPWARDS. Its card contains
        // three ordinary rows, so it now takes the same 76 pt column the Reds
        // take instead of the 100 pt clinched one — the wide column existed only
        // to hold a trend badge beside the word "clinched", and that badge is
        // gone. The bar gets those 24 pt back on every card with a clinched row.
        // A fix for a false sentence turning out to widen the picture beside it
        // is worth writing down rather than quietly re-pinning.
        XCTAssertEqual(brewersBar, 53.3, accuracy: 0.5)   // 137.3 - 8 - 76
        XCTAssertEqual(redsBar, 53.3, accuracy: 0.5)      // 137.3 - 8 - 76

        for (name, bar) in [("Brewers", brewersBar), ("Reds", redsBar)] {
            XCTAssertGreaterThan(
                bar, 2.0 * 10,
                "\(name): every bar on this card measured exactly 2.00 pt before "
                + "the fix, at every probability. Anything back near that floor "
                + "means the row is spending its width before it reaches the bar "
                + "again (#3580).")
        }
    }

    /// The floor itself, pinned to its reason rather than to itself.
    func testTheMinimumBarWidthResolvesOnePercentagePoint() {
        XCTAssertGreaterThanOrEqual(
            ChampionshipRowLayout.minBarWidth, 100.0 / 3.0,
            "one percentage point of a 0-100% bar is one device pixel at 3x only "
            + "from 33.4 pt up. Below that the criterion stops protecting the bar "
            + "and rows start qualifying for a one-line shape that starves it.")
    }

    /// The half that must not move: where there is room, the compact row survives.
    func testAWideCardKeepsTheOneLineRow() throws {
        // An iPad-class layout: 800 pt of cards, two of them -> 368 pt content.
        let content = ChampionshipRowLayout.teamCardContentWidth(totalWidth: 800, cardCount: 2)
        XCTAssertEqual(content, 368.0, accuracy: 0.01)

        for (name, stages) in [("Brewers", try brewersStages()), ("Reds", try redsStages())] {
            XCTAssertFalse(
                ChampionshipRowLayout.stacksBelowLabel(contentWidth: content, stages: stages),
                "\(name): 368 pt is wider than either row's minimum, so iPad and Mac "
                + "must keep the one-line shape they have today")
        }
    }

    /// An unmeasured card stacks. Stacking never wraps a word and never starves
    /// the bar, so it is the safe answer to "the width is not known yet".
    func testAnUnmeasuredCardStacks() throws {
        XCTAssertTrue(
            ChampionshipRowLayout.stacksBelowLabel(contentWidth: 0, stages: try redsStages()))
        XCTAssertEqual(
            ChampionshipRowLayout.barWidth(contentWidth: 0, stages: try redsStages()), 0)
    }

    // MARK: - Which badge column a card gets

    /// 🔴 THIS TEST ASSERTED THE OPPOSITE UNTIL #4108, AND WAS RIGHT TO.
    ///
    /// A clinched row used to draw its trend badge *and* `✓ clinched`, so it was
    /// the widest thing on the card and one of them widened the column for all
    /// four rows. #4108 removed the trend badge from a settled row — it was
    /// claiming a 90.9-point 24h move on a stage the same row calls decided — and
    /// `✓ clinched` alone now measures **53.5 pt** against an ordinary row's 72+.
    /// The clinched row became the narrow one, so the rule inverted with it.
    func testOnlyAnAllClinchedCardTakesTheNarrowColumn() throws {
        XCTAssertEqual(
            ChampionshipRowLayout.badgeWidth(for: try redsStages()),
            ChampionshipRowLayout.valueBadgeWidth,
            "a card of ordinary percentage rows keeps the full column")
        XCTAssertEqual(
            ChampionshipRowLayout.badgeWidth(for: try brewersStages()),
            ChampionshipRowLayout.valueBadgeWidth,
            "the Brewers card has three ordinary rows, so it keeps the full "
            + "column even though one row is clinched")

        let everyRowClinched = try [0.996, 0.9955, 0.999, 1.0].enumerated().map {
            try stage("k\($0.offset)", "L", probability: $0.element, trend: 0.9133)
        }
        XCTAssertEqual(
            ChampionshipRowLayout.badgeWidth(for: everyRowClinched),
            ChampionshipRowLayout.allClinchedBadgeWidth,
            "a team that clinched every stage draws no percentages and no trend "
            + "badges, so it must not pay for a column sized to hold them")
    }

    /// One width for the whole card, not per row. Three bars of three different
    /// track lengths cannot be compared to each other, and comparing them is the
    /// only reason to draw three.
    ///
    /// 🔴 THE FAILURE THIS CATCHES IS #3574 WITH THE ROLES SWAPPED. Post-#4108 it
    /// is tempting to give any card containing a clinched row the narrow column —
    /// the clinched row fits it. Its ordinary siblings do not, and they would
    /// truncate. The old suite could not have caught that: it only ever compared
    /// the clinched constant against clinched rows.
    @MainActor
    func testOneOrdinaryRowKeepsTheFullColumnForEveryRowOfThatCard() throws {
        let brewers = try brewersStages()
        XCTAssertEqual(brewers.filter {
            ChampionshipRowLayout.isClinched(probability: $0.probability)
        }.count, 1, "precondition: exactly one Brewers row is clinched")

        let column = ChampionshipRowLayout.badgeWidth(for: brewers)
        for row in brewers {
            XCTAssertGreaterThanOrEqual(
                column, naturalWidth(of: ChampionshipStageBadges(stage: row)),
                "every row of a mixed card must fit the one column the card "
                + "gives all of them, clinched or not")
        }
    }

    // MARK: - What a row shows

    func testClinchedIsTheSameThresholdTheRowAlwaysUsed() {
        XCTAssertFalse(ChampionshipRowLayout.isClinched(probability: 0.99))
        XCTAssertTrue(ChampionshipRowLayout.isClinched(probability: 0.9901))
        XCTAssertFalse(ChampionshipRowLayout.isClinched(probability: nil))
    }

    func testTinyMovementDrawsNoTrendBadge() {
        XCTAssertFalse(ChampionshipRowLayout.showsTrendBadge(trend: nil))
        XCTAssertFalse(ChampionshipRowLayout.showsTrendBadge(trend: 0.004))
        XCTAssertTrue(ChampionshipRowLayout.showsTrendBadge(trend: -0.005))
        XCTAssertTrue(ChampionshipRowLayout.showsTrendBadge(trend: 0.9133))
    }

    // MARK: - The column, measured against what the view actually draws

    /// Height cannot testify about this bug, so width has to.
    ///
    /// `clinc` / `hed` was a wrap, and a wrap makes a row taller — but the badge
    /// `Text`s now carry `lineLimit(1)`, so the same too-narrow column truncates
    /// instead and the row's height never moves. An equal-height assertion would
    /// pass for the same reason the bug would still be there. (Found by mutation:
    /// setting `allClinchedBadgeWidth` back to 70 left a height test green.)
    ///
    /// What is left is the honest question: does the column hold the content?
    /// So host the real badge view, ask it what width it wants, and require the
    /// constant to cover it. Nothing here re-derives the view's own arithmetic —
    /// if the fonts, spacings or the word "clinched" change, this fails.
    /// `trend_24h` is a difference of two probabilities, so the badge can read
    /// anything from `0.5%` to `100.0%`. Sweep it rather than trusting one
    /// fixture: a column sized against a convenient example is how 70 pt came to
    /// be 0.67 pt short of `↓99.9%` without anyone noticing.
    private let everyTrend: [Double?] = [nil, 0.005, 0.02, 0.9133, 0.999, 1.0]
    private let everyProbability: [Double] = [0.0005, 0.004, 0.134, 0.5, 0.99, 0.996, 1.0]

    @MainActor
    func testEachBadgeColumnHoldsTheWidestRowItCanEverBeAskedToDraw() throws {
        var worst: [Bool: (width: CGFloat, describe: String)] = [:]

        for trend in everyTrend {
            for probability in everyProbability {
                let row = try stage("k", "L", probability: probability, trend: trend)
                let clinched = ChampionshipRowLayout.isClinched(probability: probability)
                let wanted = naturalWidth(of: ChampionshipStageBadges(stage: row))
                let label = "trend \(trend.map { String(format: "%.1f%%", abs($0 * 100)) } ?? "none")"
                    + " + " + (clinched ? "clinched" : ChampionshipStageBadges.formatProb(probability))
                if wanted > (worst[clinched]?.width ?? 0) {
                    worst[clinched] = (wanted, label)
                }
            }
        }

        let ordinary = try XCTUnwrap(worst[false])
        let clinched = try XCTUnwrap(worst[true])

        XCTAssertGreaterThanOrEqual(
            ChampionshipRowLayout.valueBadgeWidth, ordinary.width,
            "the widest ordinary row (\(ordinary.describe)) wants \(ordinary.width) pt "
            + "and the column offers \(ChampionshipRowLayout.valueBadgeWidth) pt")
        XCTAssertGreaterThanOrEqual(
            ChampionshipRowLayout.allClinchedBadgeWidth, clinched.width,
            "the widest clinched row (\(clinched.describe)) wants \(clinched.width) pt "
            + "and the column offers \(ChampionshipRowLayout.allClinchedBadgeWidth) pt. "
            + "Short by any amount and the row breaks its own words (#3574).")

        // #4108 inverted the two: a clinched row draws no trend badge, so it is
        // now the NARROWER of the two kinds. Pinned, because `badgeWidth(for:)`
        // reads `allSatisfy` rather than `contains` on the strength of it — if a
        // clinched row ever grows back past an ordinary one, that rule is wrong
        // again and this says so before a card truncates.
        XCTAssertLessThan(
            clinched.width, ordinary.width,
            "a clinched row (\(clinched.describe), \(clinched.width) pt) must be "
            + "narrower than an ordinary one (\(ordinary.describe), \(ordinary.width) pt), "
            + "or the all-clinched narrow column is the wrong rule")

        // The column must not be padded far past what it holds either — every
        // point it takes is a point off the bar (#3580).
        XCTAssertLessThan(
            ChampionshipRowLayout.valueBadgeWidth - ordinary.width, 4,
            "the ordinary column is wider than it needs to be, at the bar's expense")
        XCTAssertLessThan(
            ChampionshipRowLayout.allClinchedBadgeWidth - clinched.width, 4,
            "the all-clinched column is wider than it needs to be, at the bar's expense")
    }

    /// #3574's row, re-measured after #4108 removed the thing that made it wide.
    ///
    /// This used to assert the opposite — that `↑91.3%  ✓ clinched` wants MORE
    /// than the 70 pt column it was given, which is why it broke into
    /// `clinc` / `hed`. That premise was true and is now unreachable: the trend
    /// badge is not drawn on a clinched row at all, so the same stage measures
    /// 53.5 pt and would have fitted the column that broke it.
    ///
    /// Kept rather than deleted, because #3574 was fixed by widening the column
    /// and #4108 fixed the content instead. The row that started it is the honest
    /// place to record that the width problem is now gone at the source.
    @MainActor
    func testThePhotographedRowNowFitsEvenTheColumnThatBrokeIt() throws {
        let photographed = try stage(
            "make_playoffs", "Make Playoffs", probability: 0.996, trend: 0.9133)
        let wanted = naturalWidth(of: ChampionshipStageBadges(stage: photographed))
        XCTAssertLessThan(
            wanted, 70,
            "the Brewers row in AFTER-mlb-15305463-s900.png drew "
            + "'↑91.3%  ✓ clinched' and wanted more than 70 pt. Drawing only "
            + "'✓ clinched' it wants \(wanted) pt — if that is back over 70 the "
            + "trend badge has returned to a settled row (#4108)")
    }

    /// The probability string is not what drives the column; the trend badge is.
    /// Worth pinning, because it is the reason `<1%` and `99%` need the same room
    /// and the reason a wider column buys nothing on a card with no movement.
    @MainActor
    func testTheProbabilityStringCostsTheColumnNothing() throws {
        XCTAssertEqual(ChampionshipStageBadges.formatProb(0.004), "<1%")
        XCTAssertEqual(ChampionshipStageBadges.formatProb(0.99), "99%")

        let widths = try [0.004, 0.134, 0.5, 0.99].map { probability in
            naturalWidth(of: ChampionshipStageBadges(
                stage: try stage("k", "L", probability: probability, trend: 0.02)))
        }
        XCTAssertEqual(Set(widths).count, 1,
                       "monospacedDigit() should make every percentage the same "
                       + "width; measured \(widths)")
    }

    // MARK: - #4328: the reader's text size is the third dimension

    /// Every size the reader can choose, not the one the suite happens to pin.
    ///
    /// 🔴 THIS SWEEP IS THE POINT OF #4328, AND ITS ABSENCE WAS MY OWN SHIP'S
    /// DOING. `testEachBadgeColumnHoldsTheWidestRowItCanEverBeAskedToDraw` above
    /// sweeps trend × probability and is a good guard — at `.large`. #4207 routed
    /// every hosted measurement through `hostForMeasurement`, which pins the
    /// content size so a verdict stops depending on whatever Dynamic Type the
    /// simulator was left at. That was right, and the cost, unnoticed until a
    /// screenshot showed `1…`, is that a column validated at exactly one text
    /// size is validated at exactly one text size. The answer is not to unpin the
    /// size — determinism was the whole point — but to sweep it on purpose.
    private let everyTextSize: [(name: String, size: DynamicTypeSize)] = [
        ("xSmall", .xSmall), ("small", .small), ("medium", .medium),
        ("large", .large), ("xLarge", .xLarge), ("xxLarge", .xxLarge),
        ("xxxLarge", .xxxLarge),
        ("a11y1", .accessibility1), ("a11y2", .accessibility2),
        ("a11y3", .accessibility3), ("a11y4", .accessibility4),
        ("a11y5", .accessibility5),
    ]

    /// The two card widths this app actually renders at: the measured phone card
    /// (137.3 pt, `artifacts-native-039/`) and an iPad-class one.
    private let everyCardWidth: [(name: String, content: CGFloat)] = [
        ("iPhone", 137.3), ("iPad", 368.0),
    ]

    /// The widest thing each column is asked to draw, measured at `size` — the
    /// same element-wise max the view's `ChampionshipColumnsKey` takes over its
    /// rows, so the rule is asked the question the card asks it.
    @MainActor
    private func measuredColumns(
        for stages: [ProgressionStageData], at size: DynamicTypeSize
    ) -> ChampionshipColumnWidths {
        stages.reduce(ChampionshipColumnWidths.zero) { widths, stage in
            widths.merged(with: ChampionshipColumnWidths(
                label: naturalWidth(of: Text(stage.label).font(.caption), at: size),
                badges: naturalWidth(of: ChampionshipStageBadges(stage: stage), at: size)))
        }
    }

    /// The defect, stated as the reason a constant cannot be the answer.
    ///
    /// `Text(formatProb(prob))` is `.font(.caption)` — a text style, so it grows
    /// with the reader's setting. The trend badge beside it is
    /// `.font(.system(size: 9))` — a point size, so it does not. A single number
    /// cannot describe a column with one half that scales and one that does not,
    /// at twelve sizes, which is why 76 was right at exactly one of them.
    @MainActor
    func testAFixedColumnIsWideEnoughAtOneTextSizeAndShortAboveIt() throws {
        // `<1%` with a 100.0% trend is the widest content the badge can draw
        // (`testEachBadgeColumnHoldsTheWidestRowItCanEverBeAskedToDraw` sweeps to
        // the same worst case; this is that row).
        let widest = try stage("k", "L", probability: 0.004, trend: 1.0)

        var shortfalls: [(String, CGFloat)] = []
        for (name, size) in everyTextSize {
            let wanted = naturalWidth(of: ChampionshipStageBadges(stage: widest), at: size)
            if wanted > ChampionshipRowLayout.valueBadgeWidth {
                shortfalls.append((name, wanted - ChampionshipRowLayout.valueBadgeWidth))
            }
        }

        // BOTH directions. The constant is genuinely enough at and below `.large`
        // — a guard that only said "76 is too small" would be satisfied by making
        // it 500 and starving every bar on the page (#3580).
        XCTAssertEqual(
            shortfalls.map(\.0), ["xLarge", "xxLarge", "xxxLarge", "a11y1", "a11y2",
                                  "a11y3", "a11y4", "a11y5"],
            "the shipping 76 pt column holds the widest badge at `.large` and is "
            + "short at every size above it — starting at `.xLarge`, which is ONE "
            + "notch up from the default and four below the first accessibility "
            + "setting. #4328 is filed as an accessibility defect and it is not "
            + "only one: any reader who has nudged the text up at all can lose the "
            + "number. Measured shortfalls: \(shortfalls.map { "\($0.0) +\(Int($0.1))pt" })")

        let atA11y3 = try XCTUnwrap(shortfalls.first { $0.0 == "a11y3" })
        XCTAssertGreaterThan(
            atA11y3.1, 30,
            "at `.accessibility3` the badge wants 41 pt more than the column has, "
            + "and `lineLimit(1)` turned that into `1…` — the number the row "
            + "exists to show (#4328's photograph, AFTER-4108-a11y.png)")
    }

    /// The ship: at every text size, on every card this app draws, the badge gets
    /// at least the width it needs — and it needs less than the card has.
    @MainActor
    func testEveryTextSizeGetsAColumnThatHoldsItsOwnProbability() throws {
        for (sizeName, size) in everyTextSize {
            for (cardName, content) in everyCardWidth {
                let stages = try brewersStages()
                let columns = ChampionshipRowLayout.columns(
                    measured: measuredColumns(for: stages, at: size), for: stages)
                let shape = ChampionshipRowLayout.shape(
                    contentWidth: content, columns: columns)

                // What the row hands the badges. In two of the three shapes that
                // is the column; in the third it is the whole card, which is the
                // only reason `.badgesAboveBar` exists.
                let given = shape == .badgesAboveBar ? content : columns.badges

                for stage in stages {
                    let taken = sizeWhenOffered(
                        given, to: ChampionshipStageBadges(stage: stage), at: size)
                    XCTAssertLessThanOrEqual(
                        taken.width, given + 0.5,
                        "\(sizeName)/\(cardName) (\(shape)): the badge came out "
                        + "\(taken.width) pt inside the \(given) pt it was given, "
                        + "so it is being squeezed and something on it truncates")
                }
            }
        }
    }

    /// The other half of that trade: the bar may not be paid for out of the
    /// number, nor the number out of the bar.
    @MainActor
    func testTheBarStillResolvesWhatItDrawsAtEveryTextSize() throws {
        for (sizeName, size) in everyTextSize {
            for (cardName, content) in everyCardWidth {
                let stages = try brewersStages()
                let columns = ChampionshipRowLayout.columns(
                    measured: measuredColumns(for: stages, at: size), for: stages)
                let bar = ChampionshipRowLayout.barWidth(
                    contentWidth: content, columns: columns)
                XCTAssertGreaterThanOrEqual(
                    bar, ChampionshipRowLayout.minBarWidth,
                    "\(sizeName)/\(cardName): the bar came out \(bar) pt. Below "
                    + "\(ChampionshipRowLayout.minBarWidth) it cannot resolve one "
                    + "percentage point and it is decoration again (#3580)")
            }
        }
    }

    /// 🔴 THE CONTROL FOR THE TEST ABOVE, AND THE REASON `.badgesAboveBar` HAD TO
    /// EXIST RATHER THAN BEING A WIDER COLUMN.
    ///
    /// At the top sizes there is no arrangement in which the bar and the badges
    /// share a line: the badge alone wants more than the phone card has. Without
    /// this the previous test could be satisfied by a rule that never chose the
    /// third shape at all, and it would still read green.
    @MainActor
    func testAtTheTopSizesTheBarAndTheBadgeCannotShareALine() throws {
        let stages = try brewersStages()
        let content: CGFloat = 137.3
        var takesTheThirdShape: [String] = []

        for (sizeName, size) in everyTextSize {
            let columns = ChampionshipRowLayout.columns(
                measured: measuredColumns(for: stages, at: size), for: stages)
            let shape = ChampionshipRowLayout.shape(contentWidth: content, columns: columns)
            guard shape == .badgesAboveBar else { continue }
            takesTheThirdShape.append(sizeName)

            // Necessity: the third shape is only allowed where the second one
            // genuinely cannot work, or it is a gratuitous relayout.
            XCTAssertLessThan(
                content - ChampionshipRowLayout.spacing - columns.badges,
                ChampionshipRowLayout.minBarWidth,
                "\(sizeName): a \(columns.badges) pt badge beside a bar in a 137.3 pt "
                + "card leaves the bar "
                + "\(content - ChampionshipRowLayout.spacing - columns.badges) pt, "
                + "which clears the minimum — so this row should have stacked")
        }

        XCTAssertEqual(
            takesTheThirdShape, ["a11y2", "a11y3", "a11y4", "a11y5"],
            "the measured boundary on the production phone card. Below it the badge "
            + "and the bar still fit on a line together; from `.accessibility2` up "
            + "they do not, at any column width, which is why widening the column "
            + "was not on its own an answer to #4328")
    }

    /// And where even the full card cannot hold the badge on one line, the badge
    /// takes two — it does not overflow the card and it does not truncate.
    @MainActor
    func testTheBadgeTakesASecondLineRatherThanOverflowTheCard() throws {
        let widest = try stage("k", "L", probability: 0.004, trend: 1.0)
        let content: CGFloat = 137.3

        let oneLine = naturalWidth(of: ChampionshipStageBadges(stage: widest), at: .accessibility5)
        XCTAssertGreaterThan(
            oneLine, content,
            "precondition: at `.accessibility5` the one-line badge wants \(oneLine) pt "
            + "and the card has \(content) — if this ever fits, the second arm is "
            + "unreachable and this test is proving nothing")

        let squeezed = sizeWhenOffered(
            content, to: ChampionshipStageBadges(stage: widest), at: .accessibility5)
        XCTAssertLessThanOrEqual(
            squeezed.width, content,
            "offered the whole card it still came out \(squeezed.width) pt wide, so "
            + "it overflowed instead of reflowing")

        // Two lines, not one truncated line: the arrangement is what gave.
        //
        // The second line is only as tall as the trend badge — a fixed 9 pt font
        // (#4109) next to a probability that scales — so the height grows by 13 pt
        // here, not by half again. Asserting a ratio would be asserting that the
        // two halves of the badge scale together, which is the very thing they do
        // not do.
        let oneLineHeight = sizeWhenOffered(
            .greatestFiniteMagnitude, to: ChampionshipStageBadges(stage: widest),
            at: .accessibility5).height
        XCTAssertGreaterThan(
            squeezed.height, oneLineHeight + 5,
            "the squeezed badge is \(squeezed.height) pt tall against \(oneLineHeight) "
            + "unconstrained. Unchanged height means it stayed on one line and lost "
            + "characters instead — which is the defect (#4328)")
        XCTAssertLessThan(
            squeezed.width, oneLine,
            "and it must be NARROWER than the one-line arrangement, or nothing "
            + "reflowed and the extra height came from somewhere else")

        // One size down it must NOT reflow: a badge that always stacks would pass
        // every assertion above and would be a different, gratuitous change.
        let a11y4 = sizeWhenOffered(
            content, to: ChampionshipStageBadges(stage: widest), at: .accessibility4)
        XCTAssertEqual(
            a11y4.height,
            sizeWhenOffered(.greatestFiniteMagnitude, to: ChampionshipStageBadges(stage: widest),
                            at: .accessibility4).height,
            accuracy: 0.5,
            "at `.accessibility4` the one-line badge fits the card, so it must stay "
            + "on one line")
    }

    /// 🔴 THE DEFAULT-SIZE RENDER MAY NOT MOVE. The constants are a floor and a
    /// measurement may only raise them, precisely so that this fix costs the
    /// reader who has changed nothing exactly nothing.
    @MainActor
    func testTheDefaultSizeRenderIsUntouched() throws {
        let stages = try brewersStages()
        let measured = measuredColumns(for: stages, at: .large)
        XCTAssertLessThan(
            measured.badges, ChampionshipRowLayout.valueBadgeWidth,
            "precondition: at `.large` the widest badge measures \(measured.badges) pt "
            + "against a 76 pt column, so the measurement is SMALLER and the floor "
            + "is what makes this a no-op")

        let columns = ChampionshipRowLayout.columns(measured: measured, for: stages)
        XCTAssertEqual(columns.badges, ChampionshipRowLayout.valueBadgeWidth)
        XCTAssertEqual(
            ChampionshipRowLayout.barWidth(contentWidth: 137.3, columns: columns),
            ChampionshipRowLayout.barWidth(contentWidth: 137.3, stages: stages),
            accuracy: 0.01,
            "the measured path and the constant path must give the phone card the "
            + "same bar at `.large` — 53.3 pt, the number pinned off "
            + "artifacts-native-039/")
        XCTAssertEqual(
            ChampionshipRowLayout.shape(contentWidth: 137.3, columns: columns), .stacked)
    }

    /// The label column had the same fault and it was already short — at the
    /// default size, on a label production serves today.
    @MainActor
    func testTheLabelColumnHoldsTheStageNamesTheApiActuallySends() throws {
        // The four labels in `/api/events/15305463/team-progression`, read 2026-09-06.
        let served = ["Make Playoffs", "Division", "AL / NL Champ", "World Series"]
        let widest = try XCTUnwrap(
            served.map { ($0, naturalWidth(of: Text($0).font(.caption))) }
                .max { $0.1 < $1.1 })

        XCTAssertGreaterThan(
            widest.1, ChampionshipRowLayout.labelWidth,
            "'\(widest.0)' wants \(widest.1) pt at `.large` and the column is "
            + "\(ChampionshipRowLayout.labelWidth) — so the one-line shape has been "
            + "wrapping this label on iPad since it shipped. The comment on "
            + "`labelWidth` measured 'Make Playoffs' and stopped there")

        let stages = try brewersStages()
        let columns = ChampionshipRowLayout.columns(
            measured: measuredColumns(for: stages, at: .large), for: stages)
        XCTAssertGreaterThanOrEqual(
            columns.label, widest.1,
            "the measured column must hold it")
    }

    // MARK: - The view has to actually consult the rule

    /// A rule the view does not call is a description, not a decider — and every
    /// test above would stay green while the card kept its 2 pt bar.
    ///
    /// The instrument has to be the bar itself. Row *height* looked like a
    /// discriminator and is not: bypassing the rule makes the row overflow, the
    /// stage label wraps instead, and the card gets taller for entirely the
    /// wrong reason. (Found by mutation — `stacked = false` left a height-based
    /// test green.) So measure what #3580 is actually about: paint the bars a
    /// colour nothing else in the card uses, render at the real phone width, and
    /// read how long they came out.
    @MainActor
    func testTheRenderedBarIsAsLongAsTheProbabilityItDraws() throws {
        func barLength(probability: Double) throws -> CGFloat {
            let card = ChampionshipPathView(
                progression: try brewersAtRedsProgression(
                    stageJSON: stageJSON("division", "Division", probability: probability)),
                homeTeamColor: Self.barColor, awayTeamColor: Self.barColor)
            return longestRun(of: Self.barColor, in: render(card, width: 402))
        }

        let long = try barLength(probability: 0.96)
        let short = try barLength(probability: 0.13)

        XCTAssertGreaterThanOrEqual(
            long, 100.0 / 3.0,
            "a 96% bar rendered \(long) pt long at iPhone width. It measured "
            + "2.00 pt in AFTER-mlb-15305463-s900.png, and anything under 33.4 pt "
            + "cannot resolve one percentage point at 3x (#3580).")
        XCTAssertGreaterThan(
            long, short * 3,
            "96% drew \(long) pt and 13% drew \(short) pt. A bar whose length does "
            + "not follow its probability is decoration: before this fix both "
            + "measured exactly 2.00 pt, because the row had spent all 166 pt of "
            + "the card before reaching them.")
    }

    /// #4328's half of the same question: does the CARD change shape when the
    /// reader's text size changes, or only the arithmetic in `ChampionshipRowLayout`?
    ///
    /// Every test above this one measures the rule. The rule could be perfect and
    /// the card could still draw `1…`, because until this ship the card asked for
    /// `badgeWidth(for:)` — a constant — and never told anyone what its rows
    /// wanted. So render the real card at two text sizes and read the bar.
    ///
    /// 🔴 THE SHIP IS THE BAR GETTING SHORTER, WHICH LOOKS LIKE A REGRESSION AND
    /// IS THE FIX. On master the bar measures the same at both sizes: the column
    /// is 76 pt whatever the reader does, so the bar keeps its 85 pt and the
    /// probability inside those 76 pt is what gives. Here the badge takes the room
    /// it needs and the bar takes what is left. A test asserting the bar did not
    /// move would be asserting the defect.
    @MainActor
    func testTheRenderedCardGivesTheNumberItsRoomAtAccessibilitySizes() throws {
        let probability = 0.96
        let trend = 0.0258
        let card = ChampionshipPathView(
            progression: try brewersAtRedsProgression(
                stageJSON: stageJSON("division", "Division",
                                     probability: probability, trend: trend)),
            homeTeamColor: Self.barColor, awayTeamColor: Self.barColor)

        // The width the card itself works out at this render width, not a literal.
        // `ChampionshipPathView` insets its whole body by `.padding()` — 16 pt a
        // side — before the two cards divide what is left, and leaving that out
        // was how #3580's fit formula came to believe it had room for a bar.
        let pagePadding: CGFloat = 16
        let content = ChampionshipRowLayout.teamCardContentWidth(
            totalWidth: 402 - pagePadding * 2, cardCount: 2)
        let row = try stage("division", "Division", probability: probability, trend: trend)

        for (name, size) in [("large", DynamicTypeSize.large),
                             ("a11y3", .accessibility3)] {
            let columns = ChampionshipRowLayout.columns(
                measured: measuredColumns(for: [row], at: size), for: [row])
            let expected = ChampionshipRowLayout.barWidth(
                contentWidth: content, columns: columns) * probability
            let drawn = longestRun(of: Self.barColor, in: render(card, width: 402, at: size))

            XCTAssertEqual(
                drawn, expected, accuracy: 6,
                "\(name): the card drew a \(drawn) pt fill where the rule says "
                + "\(expected) pt (badge column \(columns.badges)). A card that "
                + "ignores the measurement draws the same bar at every text size")
        }

        // And the discriminating clause: the two sizes must DIFFER. Equal bars are
        // what master draws, and what a fix that never reached the view would.
        let large = longestRun(of: Self.barColor, in: render(card, width: 402, at: .large))
        let a11y3 = longestRun(of: Self.barColor, in: render(card, width: 402, at: .accessibility3))
        XCTAssertLessThan(
            a11y3, large - 20,
            "the bar measured \(large) pt at `.large` and \(a11y3) pt at "
            + "`.accessibility3`. On master both are 81.6 pt, because the 76 pt "
            + "column never moves and the probability truncates inside it instead")
    }

    /// Nothing else in the card is this colour, so any run of it is bar.
    private static let barColor = Color(red: 1, green: 0, blue: 0)

    /// The longest horizontal run of `color`, in points. Text drawn in the same
    /// colour contributes only a few points; a bar contributes its whole length.
    @MainActor
    private func longestRun(of color: Color, in image: UIImage) -> CGFloat {
        guard let cg = image.cgImage else { return 0 }
        let width = cg.width, height = cg.height
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        guard let ctx = CGContext(
            data: &pixels, width: width, height: height, bitsPerComponent: 8,
            bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return 0 }
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))

        var best = 0
        for y in 0..<height {
            var run = 0
            for x in 0..<width {
                let i = (y * width + x) * 4
                let isBar = pixels[i] > 180 && pixels[i + 1] < 90 && pixels[i + 2] < 90
                run = isBar ? run + 1 : 0
                best = max(best, run)
            }
        }
        return CGFloat(best) / image.scale
    }

    @MainActor
    private func render<V: View>(
        _ view: V, width: CGFloat, at size: DynamicTypeSize = .large
    ) -> UIImage {
        let host = hostForMeasurement(view.frame(width: width), at: size)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 1200))
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        let bounds = host.view.bounds
        return UIGraphicsImageRenderer(bounds: bounds).image { _ in
            host.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    /// Lays the card out and lets the width measurement come back before asking.
    ///
    /// The card learns its width from a preference, which arrives on a second
    /// pass — a single synchronous `layoutIfNeeded` measures the card before it
    /// knows how wide it is, and would report the unmeasured shape at every
    /// width.
    @MainActor
    private func renderedHeight<V: View>(of view: V, width: CGFloat) -> CGFloat {
        let host = hostForMeasurement(view.frame(width: width))
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 2000))
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        return host.sizeThatFits(
            in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude)).height
    }

    /// The width the view asks for when nothing constrains it.
    @MainActor
    private func naturalWidth<V: View>(of view: V, at size: DynamicTypeSize = .large) -> CGFloat {
        let host = hostForMeasurement(view, at: size)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }

    /// What the view actually comes out as when it is offered `width` — which is
    /// not the same question as `naturalWidth`, and is the one #4328 is about.
    @MainActor
    private func sizeWhenOffered<V: View>(
        _ width: CGFloat, to view: V, at size: DynamicTypeSize
    ) -> CGSize {
        let host = hostForMeasurement(view, at: size)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: width, height: CGFloat.greatestFiniteMagnitude))
    }

    /// Brewers @ Reds as production serves it — **both** cards, because the card
    /// count is half the arithmetic. A one-team fixture gets the whole 346 pt and
    /// stays on one line at phone width, quite correctly, and would hide every
    /// question this file is about.
    private func brewersAtRedsProgression(stageJSON: String) throws -> TeamProgressionResponse {
        let json = #"""
        {"event_id": 15305463, "league": "mlb", "league_name": "MLB Playoffs 2026",
         "away_team": {"name": "Milwaukee Brewers", "short_name": "Brewers",
                       "record": "88-55", "conference": "National League",
                       "stages": [\#(stageJSON)]},
         "home_team": {"name": "Cincinnati Reds", "short_name": "Reds",
                       "record": "68-74", "conference": "National League",
                       "stages": [\#(stageJSON)]}}
        """#
        return try decoder().decode(TeamProgressionResponse.self, from: Data(json.utf8))
    }
}
