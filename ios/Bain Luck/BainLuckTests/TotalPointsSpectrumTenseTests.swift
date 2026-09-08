import SwiftUI
import XCTest
@testable import Bain_Luck

/// #3905 — the scoring-spectrum card stops heading a fully graded ladder
/// "Projected", and — the part with the risk in it — does not start heading an
/// UNGRADED one "Final".
///
/// #3930 — and stops heading a match that has been over for hours "Projected"
/// either. That is the third state, and it is the one #3905 could not name:
/// its two-way `finalTotal == nil` rule had to put "settled but ungradeable"
/// somewhere, and "Projected" was the safer of the two wrong answers.
///
/// The view is SwiftUI and is not asserted here. What is asserted is the pure
/// rule it defers to — `MarketMapRail.spectrumSectionTitle(finalTotal:isSettled:)`,
/// `spectrumLadderTitle(finalTotal:unit:isSettled:)` and, since #3930 put all
/// three of the card's strings behind one `SpectrumTense`, the rung caption
/// that has to agree with them.
///
/// TWO SPECIMENS, both read off production 2026-09-08:
///
/// 1. **15306209** — `Reds 3 — Dodgers 6`, `completed`, **9 runs**, eleven
///    `Over N runs scored` lines. #3905's photograph: it says `Final total
///    runs / 9` and grades `7.5+ HIT`, under two headings that said "Projected".
/// 2. **15305795** — `Zverev def. Darderi`, `completed`, **5** `game_total`
///    lines. Settled with NO final to grade against, because tennis scores in
///    sets and `SportVocab.scoreboardCountsTheUnit` is false for it. #3930's
///    photograph: after #3929 every rung on this card correctly says
///    `LAST QUOTE`, under two headings that still said "Projected".
final class TotalPointsSpectrumTenseTests: XCTestCase {

    /// The MLB specimen's final, and the lines the settled window draws.
    private let mlbFinal = 9
    private let mlbLadder: [Double] = [7.5, 8.5, 9.5, 10.5, 11.5]

    // MARK: - #3905's defect

    /// The photographed frame: both headings, over a ladder that has verdicts.
    func testASettledCardWithAFinalSaysFinalInBothHeadings() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: mlbFinal, isSettled: true),
            "Final scoring",
            "the card whose own value tile reads 'Final total runs' cannot be headed 'Projected'"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: mlbFinal, unit: "runs", isSettled: true),
            "Final combined runs"
        )
    }

    /// The map one card higher already reads this way — #3763. The two cards are
    /// on one screen, so they are asserted against each other rather than each
    /// against a literal: that is the disagreement #3905 was about.
    func testTheHeadingAgreesWithTheMapAboveItOnTheSameScreen() {
        let mapSubtitle = MarketMapRail.fullTotalSubtitle(
            isDone: true, hasDistribution: true, unit: "runs"
        )
        XCTAssertEqual(mapSubtitle, "Final runs distribution")

        for heading in [
            MarketMapRail.spectrumSectionTitle(finalTotal: mlbFinal, isSettled: true),
            MarketMapRail.spectrumLadderTitle(finalTotal: mlbFinal, unit: "runs", isSettled: true),
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
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: nil, isSettled: false),
            "Projected scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "points", isSettled: false),
            "Projected combined points"
        )
    }

    /// #3509's fallback survives: where neither the markets nor the sport declare
    /// a unit the widget says "scoring", and it still does in all three tenses.
    func testTheUnitIsTheWidgetsOwnInEveryTense() {
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "scoring", isSettled: false),
            "Projected combined scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "scoring", isSettled: true),
            "Settled combined scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: 4, unit: "scoring", isSettled: true),
            "Final combined scoring"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: 22, unit: "games", isSettled: true),
            "Final combined games"
        )
    }

    // MARK: - 🔴 #3930: the third state, and the two it must not swallow

    /// THE TEST THIS FIX EXISTS TO PASS — and note what it replaced.
    ///
    /// Until #3930 the assertion on these exact two calls was that they say
    /// **"Projected"**, with #3905's reasoning attached: a heading keyed on "the
    /// event is over" would have said "Final scoring" over five ungraded rungs,
    /// so between two wrong answers it took the smaller lie. Both halves of that
    /// are still true and neither is what this card says now. The third state
    /// has a name.
    func testASettledCardWithNoFinalSaysSettledInBothHeadings() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: nil, isSettled: true),
            "Settled scoring",
            "event 15305795 has been over for hours — it is not a projection"
        )
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "games", isSettled: true),
            "Settled combined games"
        )
    }

    /// 🔴 **THE CONTROL #3905 WROTE, KEPT POINTING THE SAME WAY.** Naming the
    /// third state must not have quietly re-created the defect #3905's parameter
    /// choice existed to avoid: a card with nothing to grade may never claim a
    /// final. This is the assertion an `isDone` gate fails, and it is the one
    /// that a careless three-state rewrite fails too.
    func testASettledCardWithNoFinalStillNeverSaysFinal() {
        for heading in [
            MarketMapRail.spectrumSectionTitle(finalTotal: nil, isSettled: true),
            MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "games", isSettled: true),
        ] {
            XCTAssertFalse(
                heading.hasPrefix("Final"),
                "'\(heading)' would be a final stated over five rungs that say LAST QUOTE, on a "
                + "sport whose scoreboard does not count this widget's unit"
            )
        }
    }

    /// The other direction, and #3905's ship: a card that CAN grade says "Final"
    /// and never "Settled", even though it is every bit as settled. The final
    /// wins, which is what makes 15306209 keep printing `HIT` rather than
    /// regressing to the softer word.
    func testAGradeableFinalOutranksMerelyBeingSettled() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: mlbFinal, isSettled: true),
            "Final scoring"
        )
        XCTAssertEqual(
            MarketMapRail.SpectrumTense.of(finalTotal: mlbFinal, isSettled: true), .graded,
            "the precedence, stated once where all three of the card's strings read it"
        )
    }

    /// "Settled" is reachable only by being settled — a live or scheduled card
    /// cannot land on it however the rest of the payload looks.
    func testAnUnsettledCardCanNeverSaySettled() {
        for finalTotal: Int? in [nil, 0, 9, 22] {
            let heading = MarketMapRail.spectrumSectionTitle(
                finalTotal: finalTotal, isSettled: false
            )
            XCTAssertFalse(
                heading.hasPrefix("Settled"),
                "finalTotal \(String(describing: finalTotal)) on a card that is not over"
            )
        }
    }

    // MARK: - One card, one tense

    /// 🔴 **THE #3930 INVARIANT, AND THE ONE THE CARD ACTUALLY BROKE.** #3930 was
    /// not a wrong string; it was three strings that were each defensible and
    /// did not agree — "Projected scoring" over rungs saying "LAST QUOTE". So
    /// the assertion is over all three at once, across every state the card can
    /// be in, rather than each against a literal of its own.
    func testAllThreeOfTheCardsStringsAreInOneTense() {
        for isSettled in [true, false] {
            for finalTotal: Int? in [nil, 0, 9] {
                let tense = MarketMapRail.SpectrumTense.of(
                    finalTotal: finalTotal, isSettled: isSettled
                )
                let section = MarketMapRail.spectrumSectionTitle(
                    finalTotal: finalTotal, isSettled: isSettled
                )
                let ladder = MarketMapRail.spectrumLadderTitle(
                    finalTotal: finalTotal, unit: "runs", isSettled: isSettled
                )
                let caption = MarketMapRail.spectrumRungCaption(
                    finalTotal: finalTotal, isSettled: isSettled
                )
                let where_ = "finalTotal \(String(describing: finalTotal)), isSettled \(isSettled)"

                switch tense {
                case .projected:
                    XCTAssertEqual(section, "Projected scoring", where_)
                    XCTAssertEqual(ladder, "Projected combined runs", where_)
                    XCTAssertEqual(caption, "PRE-GAME", where_)
                case .settled:
                    XCTAssertEqual(section, "Settled scoring", where_)
                    XCTAssertEqual(ladder, "Settled combined runs", where_)
                    XCTAssertEqual(
                        caption, SettledQuote.prefix.uppercased(),
                        where_ + " — the heading and the rungs beneath it are one sentence"
                    )
                case .graded:
                    XCTAssertEqual(section, "Final scoring", where_)
                    XCTAssertEqual(ladder, "Final combined runs", where_)
                    XCTAssertNil(
                        caption, where_ + " — a graded rung's verdict badge owns the row"
                    )
                }
            }
        }
    }

    /// The invariant, stated over the two specimens at once: a heading says
    /// "Final" exactly when the rungs beneath it carry verdicts. Both read one
    /// value, so re-keying either on a second fact breaks this. #3930 added a
    /// second fact and this test is why it could not be wired to the wrong one.
    func testTheHeadingSaysFinalExactlyWhenTheRungsGrade() {
        for isSettled in [true, false] {
            for finalTotal: Int? in [nil, mlbFinal, 0, 22] {
                let headingIsFinal = MarketMapRail
                    .spectrumSectionTitle(finalTotal: finalTotal, isSettled: isSettled)
                    .hasPrefix("Final")
                let rungsGrade = mlbLadder.allSatisfy { threshold in
                    finalTotal.map {
                        MarketMapRail.totalLadderResult(threshold: threshold, finalTotal: $0)
                    } != nil
                }
                XCTAssertEqual(
                    headingIsFinal, rungsGrade,
                    "finalTotal \(String(describing: finalTotal)), isSettled \(isSettled): the "
                    + "heading and the verdicts beneath it disagree about whether this card grades"
                )
            }
        }
    }

    /// The two headings are one sentence in two sizes, so they may differ in
    /// wording but never in tense.
    func testTheCardsTwoHeadingsAreNeverInDifferentTenses() {
        for isSettled in [true, false] {
            for finalTotal: Int? in [nil, mlbFinal, 0, 22] {
                let section = MarketMapRail.spectrumSectionTitle(
                    finalTotal: finalTotal, isSettled: isSettled
                )
                let ladder = MarketMapRail.spectrumLadderTitle(
                    finalTotal: finalTotal, unit: "runs", isSettled: isSettled
                )
                XCTAssertEqual(
                    section.split(separator: " ").first, ladder.split(separator: " ").first,
                    "'\(section)' over '\(ladder)' — one card, two tenses, which is #3930"
                )
            }
        }
    }

    /// A final of `0` is a real settled card — nil-vs-zero, not truthiness.
    /// `Reds 0 — Dodgers 0` grades every rung MISS and is still a final.
    func testAZeroFinalIsSettled() {
        XCTAssertEqual(
            MarketMapRail.spectrumSectionTitle(finalTotal: 0, isSettled: true), "Final scoring"
        )
        XCTAssertEqual(
            MarketMapRail.totalLadderResult(threshold: 7.5, finalTotal: 0), .under,
            "the control for the assertion above: a 0 final really does grade"
        )
    }

    // MARK: - 🟠 The fixed-width trap, asked of a slot that has no fixed width

    /// #3552's class, checked rather than assumed — this lane's most repeated
    /// defect is a string that got longer than the room it was given, and #3925
    /// bit exactly that way ten minutes before this fix (`LAST QUOTE` wanted
    /// 58.7 pt of a 52 pt column).
    ///
    /// Neither heading slot has a fixed frame, so there is no constant to size
    /// here and the honest question is relative: **is any new heading wider than
    /// the longest one this same slot already ships?** If not, every layout that
    /// fits today still fits, and no separate width constant has to be invented
    /// or maintained. Measured, not counted in characters — both types are
    /// proportional, and "Settled" has two ascenders where "Projected" has one.
    ///
    /// **What it measured, read off the assertion inverted so it had to print:**
    ///
    /// ```
    /// section: 'Settled scoring'          109.0  pt  vs 'Projected scoring'          126.33 pt
    /// ladder:  'Settled combined scoring' 151.33 pt  vs 'Projected combined scoring' 165.67 pt
    /// ```
    ///
    /// So both new strings are NARROWER than the longest their slot already
    /// lays out, by 17.3 pt and 14.3 pt — this fix cannot truncate anything.
    /// The number is here because the answer was not obvious in advance and a
    /// passing relative assertion does not tell you it: "Settled" is two
    /// characters shorter than "Projected" but the fonts are proportional, and
    /// the last time this lane assumed instead of measuring it was 6.7 pt out
    /// in the direction that ships `LAST QUO…`.
    @MainActor
    func testTheSettledHeadingsFitWhereTheShippingOnesDo() {
        let sectionShipping = ["Projected scoring", "Final scoring"]
        let ladderShipping = [
            "Projected combined scoring", "Final combined scoring",
            "Projected combined runs", "Projected combined points",
        ]

        for (label, font, shipping, new) in [
            (
                "section", TotalPointsSpectrumView.sectionTitleFont, sectionShipping,
                [MarketMapRail.spectrumSectionTitle(finalTotal: nil, isSettled: true)]
            ),
            (
                "ladder", TotalPointsSpectrumView.ladderTitleFont, ladderShipping,
                ["scoring", "runs", "points", "games"].map {
                    MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: $0, isSettled: true)
                }
            ),
        ] {
            let widestShipping = shipping
                .map { ($0, naturalWidth(of: $0, font: font)) }
                .max { $0.1 < $1.1 }!
            let widestNew = new
                .map { ($0, naturalWidth(of: $0, font: font)) }
                .max { $0.1 < $1.1 }!

            XCTAssertLessThanOrEqual(
                widestNew.1, widestShipping.1,
                "\(label) heading: the widest string #3930 adds is '\(widestNew.0)' at "
                + "\(widestNew.1) pt, against '\(widestShipping.0)' at \(widestShipping.1) pt "
                + "which this slot already lays out. Wider, and a rewording has taken room the "
                + "card was never asked whether it had."
            )
        }
    }

    @MainActor
    private func naturalWidth(of string: String, font: Font) -> CGFloat {
        let host = UIHostingController(rootView: Text(string).font(font).lineLimit(1))
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }
}
