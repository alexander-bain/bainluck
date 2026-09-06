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
        let oldRowSpend = ChampionshipRowLayout.labelWidth          // 80
            + ChampionshipRowLayout.spacing                          //  8
            + ChampionshipRowLayout.spacing                          //  8
            + ChampionshipRowLayout.valueBadgeWidth                  // 70
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
            "nor can an ordinary card: 80 + 8 + 36 + 8 + 70 = 202 > 166. The bar "
            + "was dead on every card, not only the clinched one (#3580).")
    }

    func testStackingGivesBothProductionCardsARealBar() throws {
        let brewersBar = ChampionshipRowLayout.barWidth(
            contentWidth: 166, stages: try brewersStages())
        let redsBar = ChampionshipRowLayout.barWidth(
            contentWidth: 166, stages: try redsStages())

        XCTAssertEqual(brewersBar, 166 - 8 - 96, accuracy: 0.01)   // 62
        XCTAssertEqual(redsBar, 166 - 8 - 70, accuracy: 0.01)      // 88

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

    // MARK: - The symptom, measured on the rendered view

    /// A wrapped badge makes its row taller. That is what `clinc` / `hed` *is*.
    ///
    /// So: render the same card twice, once with the trend badge that busted the
    /// column and once without it, and require the two to be the same height.
    /// Before this fix the clinched-and-moved card was taller, because both of
    /// its `Text`s had broken across two lines.
    @MainActor
    func testAClinchedRowIsNoTallerForCarryingItsTrendBadge() throws {
        func height(trend: Double?) throws -> CGFloat {
            let view = ChampionshipPathView(progression: try brewersProgression(
                stageJSON: stageJSON("make_playoffs", "Make Playoffs",
                                     probability: 0.996, trend: trend)))
            return renderedHeight(of: view, width: 402)
        }

        let withTrend = try height(trend: 0.9133)
        let withoutTrend = try height(trend: nil)

        XCTAssertGreaterThan(withoutTrend, 0, "precondition: the card must render")
        XCTAssertEqual(
            withTrend, withoutTrend, accuracy: 0.5,
            "the clinched row grew by \(withTrend - withoutTrend) pt when its trend "
            + "badge appeared. That extra height is a second line inside the badge "
            + "column — the `clinc` / `hed` break of #3574. The column must be wide "
            + "enough to hold an arrow, a delta, a checkmark and the word.")
    }

    /// The control for the test above: it must be able to see a wrap at all.
    /// A row whose column is deliberately far too narrow *does* grow, so an
    /// equal-height assertion is measuring something.
    @MainActor
    func testTheHeightAssertionCanSeeAWrap() throws {
        let view = ChampionshipPathView(progression: try brewersProgression(
            stageJSON: stageJSON("make_playoffs", "Make Playoffs",
                                 probability: 0.996, trend: 0.9133)))

        XCTAssertGreaterThan(
            renderedHeight(of: view, width: 150), renderedHeight(of: view, width: 402),
            "squeezed to 150 pt the same card must get taller — otherwise the "
            + "equal-height test above passes because nothing can ever change "
            + "the height, not because the wrap is gone")
    }

    @MainActor
    private func renderedHeight<V: View>(of view: V, width: CGFloat) -> CGFloat {
        let host = UIHostingController(rootView: view.frame(width: width))
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: width, height: .greatestFiniteMagnitude)).height
    }

    /// The Brewers card alone, carrying whatever stages the caller wants, built
    /// the way production serves it so the decode path is the one under test too.
    private func brewersProgression(stageJSON: String) throws -> TeamProgressionResponse {
        let json = #"""
        {"event_id": 15305463, "league": "mlb", "league_name": "MLB Playoffs 2026",
         "away_team": {"name": "Milwaukee Brewers", "short_name": "Brewers",
                       "record": "88-55", "conference": "National League",
                       "stages": [\#(stageJSON)]}}
        """#
        return try decoder().decode(TeamProgressionResponse.self, from: Data(json.utf8))
    }
}
