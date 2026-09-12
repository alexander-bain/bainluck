import XCTest
@testable import Bain_Luck

/// #4782 — an event page printed the same threshold and the same percentage
/// twice, about a screen-third apart, in two different notations.
///
/// The photographed pair (native/095, master `d29c068a`):
///
/// ```
/// Games map / Projected total games
///   PROJECTION 21.5      [11 ————(22)———— 32+]
///   • Over 21.5   59%
///   • Over 22.5   52%
///
/// Projected scoring
///   PRE-GAME LINE   22.5        Probability the total clears 22.5   52%
/// ```
///
/// — `22.5 at 52%`, twice. And on a suspended NPB game the two cards printed
/// the SAME FOUR ROWS, changing only `Over 5.5` into `5.5+`.
///
/// 🔴 **THE RULE IS "EVERY LINE", AND THE MEASUREMENT IS WHY.** Production,
/// 2026-09-12, 288 event pages sampled across scheduled/live/suspended/settled:
/// 162 draw the Projected scoring card, 133 of those also draw the totals map,
/// and on **43** of those 133 the scoring card holds a rung the map does not.
/// The map's window is the six LOWEST lines while this card strides across the
/// whole range, so an NCAAF page draws `44.5 / 47.5 / 50.5` on the scoring card
/// and nowhere else. A "mostly the same" test would have deleted those.
/// `testAPartialOverlapIsNotARestatement` is that population.
final class TotalsSaidOnce4782Tests: XCTestCase {

    // MARK: - Which rows are rungs at all

    /// Only outcomes NAMED "over" parse. An "Under" row prices the same line
    /// from the other side and would draw a second rung at the same threshold.
    func testOnlyAnOverOutcomeIsARung() {
        XCTAssertEqual(
            MarketMapRail.totalRungThreshold(outcomeName: "Over 21.5", threshold: 21.5), 21.5
        )
        XCTAssertNil(
            MarketMapRail.totalRungThreshold(outcomeName: "Under 21.5", threshold: 21.5)
        )
    }

    /// The line comes from the payload where it has one, and off the end of the
    /// name where it does not.
    func testARungWithNoServedLineIsReadOffItsName() {
        XCTAssertEqual(
            MarketMapRail.totalRungThreshold(outcomeName: "Over 9.5", threshold: nil), 9.5
        )
        XCTAssertNil(
            MarketMapRail.totalRungThreshold(outcomeName: "Over", threshold: nil)
        )
    }

    /// The served line WINS over the name — they can disagree, and the payload
    /// is the authority. (`Self.extractNumber` was only ever the fallback.)
    func testTheServedLineOutranksTheNameWhenBothExist() {
        XCTAssertEqual(
            MarketMapRail.totalRungThreshold(outcomeName: "Over 8.5", threshold: 9.5), 9.5
        )
    }

    func testRungsComeBackAscendingWithTheirOwnIndices() {
        let rungs = MarketMapRail.fullTotalRungs(
            outcomeNames: ["Over 11.5", "Under 5.5", "Over 5.5", "Over 7.5"],
            thresholds: [11.5, 5.5, 5.5, 7.5]
        )
        XCTAssertEqual(rungs.map(\.threshold), [5.5, 7.5, 11.5])
        // Index 2 is "Over 5.5" in the INPUT array — the caller reads that row's
        // price back through it, so a wrong index misprices a rung.
        XCTAssertEqual(rungs.map(\.index), [2, 3, 0])
    }

    // MARK: - Which rungs the map actually prints

    /// Before a result, the lowest `limit` lines.
    func testAnUnsettledMapDrawsTheLowestSixLines() {
        let names = (0..<9).map { "Over \(Double($0) + 0.5)" }
        let drawn = MarketMapRail.drawnFullTotalRungs(
            outcomeNames: names,
            thresholds: (0..<9).map { Double($0) + 0.5 },
            settledTotal: nil,
            limit: MarketMapRail.totalMapLadderLimit
        )
        XCTAssertEqual(drawn.map(\.threshold), [0.5, 1.5, 2.5, 3.5, 4.5, 5.5])
    }

    /// After one, the lines the result decided — `settledLadderWindow`'s step.
    func testASettledMapDrawsTheLinesTheResultDecided() {
        let names = (0..<9).map { "Over \(Double($0) + 0.5)" }
        let drawn = MarketMapRail.drawnFullTotalRungs(
            outcomeNames: names,
            thresholds: (0..<9).map { Double($0) + 0.5 },
            settledTotal: 7,
            limit: MarketMapRail.totalMapLadderLimit
        )
        XCTAssertTrue(drawn.map(\.threshold).contains(6.5), "the last line the 7 cleared")
        XCTAssertTrue(drawn.map(\.threshold).contains(7.5), "the first it did not")
    }

    /// The two cards must reach the SAME settled total or they judge different
    /// rungs to have been drawn. A totals map quoting something the scoreboard
    /// does not count (soccer corners on a goals scoreboard) grades nothing.
    func testAMapQuotingAnUncountedUnitHasNoSettledTotal() {
        XCTAssertEqual(
            MarketMapRail.fullTotalSettledScore(
                isDone: true, scoreboardCountsTheSportUnit: true,
                mapUnit: "goals", sportUnit: "goals", homeScore: 2, awayScore: 1
            ), 3
        )
        XCTAssertNil(
            MarketMapRail.fullTotalSettledScore(
                isDone: true, scoreboardCountsTheSportUnit: true,
                mapUnit: "corners", sportUnit: "goals", homeScore: 2, awayScore: 1
            ), "corners on a goals scoreboard"
        )
        XCTAssertNil(
            MarketMapRail.fullTotalSettledScore(
                isDone: false, scoreboardCountsTheSportUnit: true,
                mapUnit: "goals", sportUnit: "goals", homeScore: 2, awayScore: 1
            ), "not finished"
        )
    }

    // MARK: - Is it a restatement?

    func testTheNPBSpecimenIsARestatement() {
        // Both cards drew 5.5 / 7.5 / 9.5 / 11.5, changing only the notation.
        XCTAssertTrue(MarketMapRail.totalsAreRestated(
            printing: [5.5, 7.5, 9.5, 11.5], alreadyShown: [5.5, 7.5, 9.5, 11.5]
        ))
    }

    func testTheTennisSpecimensSingleLineIsARestatement() {
        // minimalView printed 22.5; the map's ladder already had 21.5 and 22.5.
        XCTAssertTrue(MarketMapRail.totalsAreRestated(
            printing: [22.5], alreadyShown: [21.5, 22.5]
        ))
    }

    /// 🔴 The 43-page population. One line this card holds and the map does not
    /// is enough to keep the whole ladder — the reader would otherwise lose it.
    func testAPartialOverlapIsNotARestatement() {
        // Measured NCAAF shape: the map draws the six lowest, this card strides.
        XCTAssertFalse(MarketMapRail.totalsAreRestated(
            printing: [38.5, 41.5, 44.5, 47.5, 50.5],
            alreadyShown: [35.5, 36.5, 37.5, 38.5, 39.5, 41.5]
        ), "44.5 / 47.5 / 50.5 appear on no other card")
    }

    /// A vacuous `true` here would withhold a card for having had nothing to
    /// say, which is a different bug wearing this fix. `allSatisfy` over an
    /// empty array is `true`, so this is the trap the guard exists for.
    func testACardPrintingNothingIsNotRestatingAnything() {
        XCTAssertFalse(MarketMapRail.totalsAreRestated(printing: [], alreadyShown: [5.5]))
    }

    /// Where no map drew, this card is the only one showing the total.
    func testNoMapMeansNoRestatement() {
        XCTAssertFalse(MarketMapRail.totalsAreRestated(printing: [5.5], alreadyShown: []))
    }

    // MARK: - So does the card draw?

    /// Specimen A. The minimal layout IS its one line, so a restated minimal
    /// card has nothing left and does not draw.
    func testTheMinimalCardGoesWhenItsOneLineIsAlreadyOnTheMap() {
        XCTAssertTrue(MarketMapRail.spectrumDrawsNothingNew(
            printing: [22.5], alreadyShown: [21.5, 22.5],
            isMinimalLayout: true, hasProjectionStrip: false
        ))
    }

    /// Specimen B. Suspended, so #4018 suppressed the strip; the four rows were
    /// the whole card and they were all on the map. A heading over nothing is
    /// the shape #4018 refused, so the card goes.
    func testTheSuspendedCardGoesRatherThanBecomeABareHeading() {
        XCTAssertTrue(MarketMapRail.spectrumDrawsNothingNew(
            printing: [5.5, 7.5, 9.5, 11.5], alreadyShown: [5.5, 7.5, 9.5, 11.5],
            isMinimalLayout: false, hasProjectionStrip: false
        ))
    }

    /// 71 of the 90 restating pages. The pace narrative and the final in this
    /// card's own words are things the map cannot say, so the card stays — it
    /// just stops repeating the rows.
    func testARestatingCardWithAStripKeepsTheCardAndDropsTheRows() {
        XCTAssertFalse(MarketMapRail.spectrumDrawsNothingNew(
            printing: [5.5, 7.5], alreadyShown: [5.5, 7.5],
            isMinimalLayout: false, hasProjectionStrip: true
        ), "the strip is not a restatement and is the reason the card survives")
    }

    /// The 43-page population again, one layer up: nothing is withheld.
    func testACardHoldingItsOwnRungAlwaysDraws() {
        for minimal in [true, false] {
            for strip in [true, false] {
                XCTAssertFalse(MarketMapRail.spectrumDrawsNothingNew(
                    printing: [38.5, 44.5], alreadyShown: [35.5, 38.5],
                    isMinimalLayout: minimal, hasProjectionStrip: strip
                ), "minimal=\(minimal) strip=\(strip)")
            }
        }
    }

    /// The whole point, stated once: a card that restates nothing is untouched
    /// no matter what else is true of it.
    func testNothingIsWithheldOnAPageWithNoMap() {
        XCTAssertFalse(MarketMapRail.spectrumDrawsNothingNew(
            printing: [5.5, 7.5], alreadyShown: [],
            isMinimalLayout: true, hasProjectionStrip: false
        ))
    }
}
