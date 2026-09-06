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

    // MARK: - The measurement the photograph pins

    func testTeamCardContentWidthReproducesTheMeasuredProductionCard() {
        // 396.0 pt of cards, two of them: the exact span measured off the PNG.
        let content = ChampionshipRowLayout.teamCardContentWidth(totalWidth: 396, cardCount: 2)
        XCTAssertEqual(
            content, 166.0, accuracy: 0.01,
            "the formula must land on the 166.0 pt measured off "
            + "AFTER-mlb-15305463-s900.png (card 190.0 pt less 12 pt padding each "
            + "side). A fit formula that drops the 16 pt gap or the 24 pt of "
            + "padding is how the row came to believe it had room for a bar.")

        // A single card takes the whole width — no gap to subtract.
        XCTAssertEqual(
            ChampionshipRowLayout.teamCardContentWidth(totalWidth: 396, cardCount: 1),
            372.0, accuracy: 0.01)
    }

    /// The defect itself, stated as arithmetic: the old row spent every point it
    /// had before reaching the bar.
    func testTheOldFixedColumnsConsumedTheEntireCard() {
        // 70 is written out rather than read from `valueBadgeWidth`: this test
        // is about the column that shipped, and it must keep describing that
        // column after the constant moves.
        let oldRowSpend = ChampionshipRowLayout.labelWidth          // 80
            + ChampionshipRowLayout.spacing                          //  8
            + ChampionshipRowLayout.spacing                          //  8
            + 70                                                     // the old badge column
        XCTAssertEqual(
            oldRowSpend, 166.0, accuracy: 0.01,
            "80 + 8 + 8 + 70 is exactly the 166 pt a row has, which is why the "
            + "GeometryReader was offered 0.0 pt and every bar drew the 2 pt "
            + "floor — 99.6% and 13.4% alike (#3580).")
    }

    // MARK: - The rule

    func testBothProductionCardsStackAtIPhoneWidth() throws {
        let brewers = try brewersStages()
        let reds = try redsStages()

        XCTAssertTrue(
            ChampionshipRowLayout.stacksBelowLabel(contentWidth: 166, stages: brewers),
            "the clinched card cannot hold label + bar + 'clinched' on one line "
            + "at 166 pt (#3574)")
        XCTAssertTrue(
            ChampionshipRowLayout.stacksBelowLabel(contentWidth: 166, stages: reds),
            "nor can an ordinary card: 80 + 8 + 36 + 8 + 76 = 208 > 166. The bar "
            + "was dead on every card, not only the clinched one (#3580).")
    }

    func testStackingGivesBothProductionCardsARealBar() throws {
        let brewersBar = ChampionshipRowLayout.barWidth(
            contentWidth: 166, stages: try brewersStages())
        let redsBar = ChampionshipRowLayout.barWidth(
            contentWidth: 166, stages: try redsStages())

        XCTAssertEqual(brewersBar, 58, accuracy: 0.01)   // 166 - 8 - 100
        XCTAssertEqual(redsBar, 82, accuracy: 0.01)      // 166 -  8 -  76

        // Absolute, not `>= minBarWidth`: a bar compared against the same
        // constant the layout used to place it agrees by construction and would
        // survive that constant being set back to the 2 pt floor.
        for (name, bar) in [("Brewers", brewersBar), ("Reds", redsBar)] {
            XCTAssertGreaterThanOrEqual(
                bar, 100.0 / 3.0,
                "\(name): measured 2.00 pt before this fix. A bar narrower than "
                + "33.4 pt cannot render one percentage point in one device pixel "
                + "at 3x, so it cannot resolve the quantity it is a picture of.")
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

    func testOnlyAClinchedCardWidensItsBadgeColumn() throws {
        XCTAssertEqual(
            ChampionshipRowLayout.badgeWidth(for: try redsStages()),
            ChampionshipRowLayout.valueBadgeWidth,
            "a card of ordinary percentage rows must keep exactly the 70 pt "
            + "column it has today")
        XCTAssertEqual(
            ChampionshipRowLayout.badgeWidth(for: try brewersStages()),
            ChampionshipRowLayout.clinchedBadgeWidth)
    }

    /// One width for the whole card, not per row. Three bars of three different
    /// track lengths cannot be compared to each other, and comparing them is the
    /// only reason to draw three.
    ///
    /// The Brewers card is the case: one clinched row (99.6%) and three ordinary
    /// ones. The card takes the wide column, so all four bars stay one length.
    func testOneClinchedRowSetsTheColumnForEveryRowOfThatCard() throws {
        let brewers = try brewersStages()
        XCTAssertEqual(brewers.filter {
            ChampionshipRowLayout.isClinched(probability: $0.probability)
        }.count, 1, "precondition: exactly one Brewers row is clinched")

        XCTAssertEqual(
            ChampionshipRowLayout.badgeWidth(for: brewers),
            ChampionshipRowLayout.clinchedBadgeWidth,
            "one clinched row must widen the column its three ordinary siblings "
            + "also draw in, or the four bars get four different track lengths")

        // Drop the clinched row and the same card reverts to the narrow column.
        let ordinaryOnly = Array(brewers.dropFirst())
        XCTAssertEqual(
            ChampionshipRowLayout.badgeWidth(for: ordinaryOnly),
            ChampionshipRowLayout.valueBadgeWidth)
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
    /// setting `clinchedBadgeWidth` back to 70 left a height test green.)
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
            ChampionshipRowLayout.clinchedBadgeWidth, clinched.width,
            "the widest clinched row (\(clinched.describe)) wants \(clinched.width) pt "
            + "and the column offers \(ChampionshipRowLayout.clinchedBadgeWidth) pt. "
            + "Short by any amount and the row breaks its own words (#3574).")

        // The column must not be padded far past what it holds either — every
        // point it takes is a point off the bar (#3580).
        XCTAssertLessThan(
            ChampionshipRowLayout.valueBadgeWidth - ordinary.width, 4,
            "the ordinary column is wider than it needs to be, at the bar's expense")
        XCTAssertLessThan(
            ChampionshipRowLayout.clinchedBadgeWidth - clinched.width, 4,
            "the clinched column is wider than it needs to be, at the bar's expense")
    }

    /// The precondition the whole fix rests on: the content genuinely did not fit
    /// the 70 pt column that shipped. If it did, #3574 could not have happened
    /// and every test above is guarding nothing.
    @MainActor
    func testThePhotographedRowDidNotFitTheOldColumn() throws {
        let photographed = try stage(
            "make_playoffs", "Make Playoffs", probability: 0.996, trend: 0.9133)
        XCTAssertGreaterThan(
            naturalWidth(of: ChampionshipStageBadges(stage: photographed)), 70,
            "'↑91.3%  ✓ clinched' — the Brewers row in "
            + "AFTER-mlb-15305463-s900.png — must want more than the 70 pt it was "
            + "given, or the `clinc` / `hed` break has some other cause")
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

    // MARK: - The view has to actually consult the rule

    /// A rule the view does not call is a description, not a decider — and every
    /// test above would stay green while the card kept its 2 pt bar.
    ///
    /// The two shapes differ in height: a stacked row puts the label on its own
    /// line. So render one card narrow and the same card wide, and require the
    /// narrow one to be taller. Only a view that branches on its measured width
    /// can produce that.
    @MainActor
    func testTheCardRendersTheShapeTheRuleChose() throws {
        let card = ChampionshipPathView(progression: try brewersAtRedsProgression(
            stageJSON: [
                stageJSON("make_playoffs", "Make Playoffs", probability: 0.996, trend: 0.9133),
                stageJSON("division", "Division", probability: 0.9615, trend: -0.0258),
                stageJSON("championship", "World Series", probability: 0.134, trend: 0.0039),
            ].joined(separator: ",")))

        let phone = renderedHeight(of: card, width: 402)
        let wide = renderedHeight(of: card, width: 1200)

        XCTAssertGreaterThan(phone, 0, "precondition: the card must render at all")
        XCTAssertGreaterThan(
            phone, wide,
            "at 402 pt the rule says stack (166 pt of content, and a clinched row "
            + "needs \(ChampionshipRowLayout.inlineRowMinimumWidth(badgeWidth: ChampionshipRowLayout.clinchedBadgeWidth)) "
            + "pt to stay on one line); at 1200 pt it says keep the one line. Equal "
            + "heights mean the view is drawing one shape regardless and never "
            + "asks — which is the state that shipped a 2 pt bar (#3580).")
    }

    /// Lays the card out and lets the width measurement come back before asking.
    ///
    /// The card learns its width from a preference, which arrives on a second
    /// pass — a single synchronous `layoutIfNeeded` measures the card before it
    /// knows how wide it is, and would report the unmeasured shape at every
    /// width.
    @MainActor
    private func renderedHeight<V: View>(of view: V, width: CGFloat) -> CGFloat {
        let host = UIHostingController(rootView: view.frame(width: width))
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
    private func naturalWidth<V: View>(of view: V) -> CGFloat {
        let host = UIHostingController(rootView: view)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
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
