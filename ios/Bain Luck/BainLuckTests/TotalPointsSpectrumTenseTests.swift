import XCTest
@testable import Bain_Luck

/// #3905 — the scoring-spectrum card stops heading a fully graded ladder
/// "Projected", and — the part with the risk in it — does not start heading an
/// UNGRADED one "Final".
///
/// The view is SwiftUI and is not asserted here. What is asserted is the pure
/// rule it now defers to, `MarketMapRail.spectrumSectionTitle(finalTotal:)` /
/// `spectrumLadderTitle(finalTotal:unit:)`, and the invariant that binds those
/// two strings to the verdicts drawn beneath them.
///
/// TWO SPECIMENS, both read off production 2026-09-08:
///
/// 1. **15306209** — `Reds 3 — Dodgers 6`, `completed`, **9 runs**, eleven
///    `Over N runs scored` lines. The card in the issue's photograph: it says
///    `Final total runs / 9` and grades `7.5+ HIT`, under two headings that
///    said "Projected".
/// 2. **15305795** — `Zverev def. Darderi`, `completed`, **5** `game_total`
///    lines. Settled with NO final to grade against, because tennis scores in
///    sets and `SportVocab.scoreboardCountsTheUnit` is false for it. Every rung
///    on this card is captioned `PRE-GAME`.
final class TotalPointsSpectrumTenseTests: XCTestCase {

    /// The MLB specimen's final, and the lines the settled window draws.
    private let mlbFinal = 9
    private let mlbLadder: [Double] = [7.5, 8.5, 9.5, 10.5, 11.5]

    // MARK: - The defect in the issue

    /// The photographed frame: both headings, over a ladder that has verdicts.
    func testASettledCardWithAFinalSaysFinalInBothHeadings() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: mlbFinal),
            "Final scoring",
            "the card whose own value tile reads 'Final total runs' cannot be headed 'Projected'"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: mlbFinal, unit: "runs"),
            "Final combined runs"
        )
    }

    /// The map one card higher already reads this way — #3763. The two cards are
    /// on one screen, so they are asserted against each other rather than each
    /// against a literal: that is the disagreement the issue is about.
    func testTheHeadingAgreesWithTheMapAboveItOnTheSameScreen() {
        let mapSubtitle = MarketMapRail.fullTotalSubtitle(
            isDone: true, hasDistribution: true, unit: "runs"
        )
        XCTAssertEqual(mapSubtitle, "Final runs distribution")

        for heading in [
            MarketMapRail.spectrumSectionTitle(finalTotal: mlbFinal),
            MarketMapRail.spectrumLadderTitle(finalTotal: mlbFinal, unit: "runs"),
        ] {
            XCTAssertTrue(
                heading.hasPrefix("Final"),
                "'\(heading)' sits directly beneath '\(mapSubtitle)', about the same nine runs "
                + "of the same finished game"
            )
        }
    }

    // MARK: - Pre-game and live must not move

    func testAnUnsettledCardIsUnchanged() {
        XCTAssertEqual(MarketMapRail.spectrumSectionTitle(finalTotal: nil), "Projected scoring")
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "points"),
            "Projected combined points"
        )
    }

    /// #3509's fallback survives: where neither the markets nor the sport declare
    /// a unit the widget says "scoring", and it still does in both tenses.
    func testTheUnitIsTheWidgetsOwnInBothTenses() {
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "scoring"),
            "Projected combined scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: 4, unit: "scoring"),
            "Final combined scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: 22, unit: "games"),
            "Final combined games"
        )
    }

    // MARK: - 🔴 The control: settled is not the same fact as graded

    /// THE TEST THIS FIX EXISTS TO PASS, and the one an `isDone` gate fails.
    ///
    /// The tennis specimen is `completed`. It draws the FULL card — five
    /// `game_total` lines is `ladderRowLimit`, and the minimal card is
    /// pre-game-only, so 3- and 2-rung settled matches (15305796, 15305728)
    /// draw it too. It has no final: `actualTotal` guards on
    /// `scoreboardCountsTheUnit`, false for tennis. So every rung reads
    /// `PRE-GAME … 42%`, and a heading keyed on "the event is over" would say
    /// "Final scoring" over five of them — #3905's defect, re-created by
    /// #3905's fix, one sport across.
    func testASettledCardWithNoFinalKeepsTheProjectedHeadings() {
        let noFinal: Int? = nil
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: noFinal),
            "Projected scoring",
            "event 15305795 is completed and has nothing to grade — its rungs still say PRE-GAME"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: noFinal, unit: "games"),
            "Projected combined games"
        )
    }

    /// The invariant, stated over both specimens at once: a heading says "Final"
    /// exactly when the rungs beneath it carry verdicts. Both read the one value,
    /// so re-keying either on a second fact breaks this.
    func testTheHeadingSaysFinalExactlyWhenTheRungsGrade() {
        for finalTotal: Int? in [nil, mlbFinal, 0, 22] {
            let headingIsFinal = MarketMapRail
                .spectrumSectionTitle(finalTotal: finalTotal)
                .hasPrefix("Final")
            let rungsGrade = mlbLadder.allSatisfy { threshold in
                finalTotal.map {
                    MarketMapRail.totalLadderResult(threshold: threshold, finalTotal: $0)
                } != nil
            }
            XCTAssertEqual(
                headingIsFinal, rungsGrade,
                "finalTotal \(String(describing: finalTotal)): the heading and the verdicts "
                + "beneath it disagree about whether this card is settled"
            )
            XCTAssertEqual(
                headingIsFinal,
                MarketMapRail.spectrumLadderTitle(finalTotal: finalTotal, unit: "runs")
                    .hasPrefix("Final"),
                "the card's two headings must never be in different tenses"
            )
        }
    }

    /// A final of `0` is a real settled card — nil-vs-zero, not truthiness.
    /// `Reds 0 — Dodgers 0` grades every rung MISS and is still a final.
    func testAZeroFinalIsSettled() {
        XCTAssertEqual(MarketMapRail.spectrumSectionTitle(finalTotal: 0), "Final scoring")
        XCTAssertEqual(
            MarketMapRail.totalLadderResult(threshold: 7.5, finalTotal: 0), .under,
            "the control for the assertion above: a 0 final really does grade"
        )
    }
}
