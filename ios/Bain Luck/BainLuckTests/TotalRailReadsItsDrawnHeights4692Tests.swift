import XCTest
@testable import Bain_Luck

/// native/094 — #4692: a totals card asks whether the rail it is about to draw
/// has a shape, instead of whether the lines behind it were distinct.
///
/// THE PHOTOGRAPH. Event 15308052 (Cincinnati Reds 1 – Los Angeles Dodgers 14,
/// MLB, `completed`), iPhone 17 simulator against production, 2026-09-10 00:50
/// PT — `artifacts-native-093/before-4692-mlb-15308052-s1000.png`. Four map
/// cards in one column, and the page disagrees with itself:
///
/// ```
/// Run margin map    Final margin              distinct blue blocks   ← right
/// 1st half margin   Half margin               two blue blocks        ← right, and
///                                                                      it WITHHELD the word
/// Runs map          Final runs distribution   uniform pale, empty    ← overclaims
/// 1st half total    Half runs distribution    uniform pale, empty    ← overclaims
/// ```
///
/// The two margin cards read `marginRailHasDistribution(density:)` — the heights
/// they are about to draw. The two totals cards read
/// `totalRailHasDistribution(thresholds:)` — whether the served lines were
/// distinct. Same page, same reader, same second, two answers.
///
/// THE MECHANISM, from the event's own `/api/events/15308052/game-markets`,
/// measured 2026-09-10: eleven totals rows, 2.5 through 12.5, **every one served
/// at `over_probability = 0.99`**. The Dodgers won by thirteen, so every line
/// below the final resolved to the same certainty. Distinct thresholds, so the
/// old rule said true; every adjacent `dp` is `0.99 - 0.99 = 0`, so
/// `densityFromThresholds` returns fourteen zeros and the rail paints one
/// uniform `alpha 0.15` block under the word "distribution".
///
/// THE CENSUS, and it is why this is a rule and not a `status` check. A settled
/// game does NOT collapse to one price by construction — only a BLOWOUT does,
/// because only then does every line land on one side of the final. Production
/// 2026-09-10, a random 60 of the 500 events completed in the previous five
/// days, probed through `GET /api/events/{id}/game-markets` (the card's own
/// feed, not a SQL proxy for it) **and then through `extractTotalThresholds`'
/// own filter**: **34 draw two or more lines. 9 lose the word. 25 keep it.**
/// The keepers straddle their final and their prices step where the total
/// landed. The same census over 70 upcoming events: 12 draw two or more lines
/// and 6 lose the word.
///
/// 🟠 A FEED ROW IS NOT A DRAWN LINE, and counting the first as the second cost
/// this ship a wasted before/after pair. `extractTotalThresholds` keeps only
/// outcomes whose NAME contains "over", so event 15309206 — which serves
/// `Over 36.5` and `Under 38.5` — is a ONE-line card that both the old rule and
/// the new one correctly refuse, and photographing it produced two identical
/// frames. Ask the parse, not the payload.
///
/// THE SECOND ARM, and it is a fix rather than a regression. Two lines are a
/// single interval, so the builder's `rawPdf.count == 1` branch gives all
/// fourteen segments one height, which normalises to 96 — a solid, fully
/// saturated band edge to edge. Photographed on US Open WTA 15308901 (Rybakina
/// v Gauff, `scheduled`), `artifacts-native-020/before-4692-twoline-15308901-s900.png`:
/// a full-strength purple band running the entire width of an `11 · 22 · 32+`
/// axis, while the card's OWN two rungs directly beneath it — Over 21.5 at 59%,
/// Over 22.5 at 52% — say the mass sits around 22. The band asserts every total
/// from 11 to 32+ is equally likely and the card contradicts it in its own
/// second paragraph. A bare track with the PROJECTION marker on it is strictly
/// more honest, and the after-frame beside it is that.
final class TotalRailReadsItsDrawnHeights4692Tests: XCTestCase {

    // MARK: - The specimens, as production served them

    /// Reds 1 – Dodgers 14, `completed`. Eleven lines, one price.
    private let dodgers: [(threshold: Double, overProb: Double)] = [
        (2.5, 0.99), (3.5, 0.99), (4.5, 0.99), (5.5, 0.99), (6.5, 0.99), (7.5, 0.99),
        (8.5, 0.99), (9.5, 0.99), (10.5, 0.99), (11.5, 0.99), (12.5, 0.99),
    ]

    /// Zverev 3 – van de Zandschulp 0, US Open ATP, `completed`. Five games
    /// lines, all at 0.01 — the same collapse from the other side.
    private let zverev: [(threshold: Double, overProb: Double)] = [
        (29.5, 0.01), (34.5, 0.01), (36.5, 0.01), (38.5, 0.01), (39.5, 0.01),
    ]

    /// Leeds 3 – Chelsea 6, EFL Cup, `completed`. Six goal lines, all at 0.99.
    private let chelsea: [(threshold: Double, overProb: Double)] = [
        (0.5, 0.99), (1.5, 0.99), (2.5, 0.99), (3.5, 0.99), (4.5, 0.99), (5.5, 0.99),
    ]

    /// Hamburger SV 0 – FSV Mainz 05 5, `completed`. The step sits at the top of
    /// the ladder rather than in the middle of it, and it is still a step.
    private let mainz: [(threshold: Double, overProb: Double)] = [
        (1.5, 0.999), (2.5, 0.999), (3.5, 0.999), (4.5, 0.999), (5.5, 0.001),
    ]

    /// Rybakina v Gauff, US Open WTA, `scheduled`. Exactly two lines PARSE, and
    /// they are the two the photographed band runs behind.
    private let twoLine: [(threshold: Double, overProb: Double)] = [
        (21.5, 0.585), (22.5, 0.515),
    ]

    // MARK: - The defect

    /// 🔴 The photographed card, end to end: served rows in, drawn heights out,
    /// rule on the heights, sentence off the rule. Every step is the production
    /// path — nothing here restates the builder's arithmetic.
    func test_theBlowoutStopsClaimingADistributionItDoesNotDraw() {
        let drawn = drawnHeights(dodgers)
        XCTAssertEqual(
            drawn, Array(repeating: 0.0, count: 14),
            "eleven lines at one price difference to nothing"
        )
        XCTAssertFalse(MarketMapRail.totalRailHasDistribution(density: drawn))
        XCTAssertEqual(
            MarketMapRail.fullTotalSubtitle(
                isDone: true,
                hasDistribution: MarketMapRail.totalRailHasDistribution(density: drawn),
                unit: "runs"
            ),
            "Final runs",
            "the photographed sentence was `Final runs distribution` over an empty rail"
        )
    }

    /// The same defect on the half card, which is the second overclaiming line
    /// in the same photograph.
    func test_theHalfCardOnTheSamePageStopsTooAndSaysSo() {
        let drawn = drawnHeights(dodgers)
        XCTAssertEqual(
            MarketMapRail.halfTotalSubtitle(
                hasDistribution: MarketMapRail.totalRailHasDistribution(density: drawn),
                unit: "runs"
            ),
            "Half runs",
            "`Half runs distribution` was printed over the same fourteen zeros"
        )
    }

    /// The collapse arrives from BOTH sides — every line above the final is a
    /// price as identical as every line below it. A rule keyed to 0.99 would
    /// pass the Dodgers and miss the tennis.
    func test_theCollapseIsRefusedFromEitherSideOfTheFinal() {
        XCTAssertFalse(MarketMapRail.totalRailHasDistribution(density: drawnHeights(zverev)))
        XCTAssertFalse(MarketMapRail.totalRailHasDistribution(density: drawnHeights(chelsea)))
    }

    // MARK: - What must NOT move

    /// 🔴 THE MIRROR REGRESSION, and the reason the census is in the class doc.
    /// Stripping the word from every settled game would be a worse product than
    /// the bug: 27 of the 35 measured settled cards have a real shape, because
    /// their lines straddle the final and the prices step there.
    func test_aSettledGameWhoseLinesStraddleItsFinalKeepsItsWord() {
        let drawn = drawnHeights(mainz)
        XCTAssertTrue(
            MarketMapRail.totalRailHasDistribution(density: drawn),
            "Mainz scored five past Hamburg: over 4.5 resolved true, over 5.5 false, and the rail draws that"
        )
        XCTAssertEqual(
            MarketMapRail.fullTotalSubtitle(isDone: true, hasDistribution: true, unit: "goals"),
            "Final goals distribution"
        )
    }

    /// An UNSETTLED card's subtitle never contained the word, so on the two-line
    /// arm the only thing that moves is the SHADING. Pinned because it is what
    /// the two-line LOOK is looking at: the caption is identical before and
    /// after, and a reader who reads only captions would call the ship inert.
    func test_theTwoLineArmMovesTheBandAndNotTheSentence() {
        let drawn = drawnHeights(twoLine)
        XCTAssertEqual(
            drawn, Array(repeating: 96.0, count: 14),
            "one interval, so every segment takes the same height and the band saturates"
        )
        XCTAssertFalse(
            MarketMapRail.totalRailHasDistribution(density: drawn),
            "a solid edge-to-edge band asserts no shape — #3763 refused exactly this on the margin side"
        )
        for hasDistribution in [true, false] {
            XCTAssertEqual(
                MarketMapRail.fullTotalSubtitle(
                    isDone: false, hasDistribution: hasDistribution, unit: "games"
                ),
                "Projected total games",
                "the pre-game sentence is out of scope and must read identically either way"
            )
        }
    }

    // MARK: - The class, not the specimens

    /// THE CLASS RULE. After this ship both map families ask ONE question of the
    /// heights they draw. #3554's lesson is that two copies of a rule drift
    /// apart; this asserts they cannot, on every array rather than a chosen one.
    func test_bothMapFamiliesNowAnswerEveryArrayIdentically() {
        let arrays: [[Double]] = [
            [],
            [96],
            Array(repeating: 0.0, count: 14),
            Array(repeating: 8.0, count: 14),
            Array(repeating: 96.0, count: 14),
            [0, 96, 0],
            [96, 0, 96, 0, 96],
            [1.9, 96.0],
            [96, 0, 95.9],
            [0, 0, 1.9, 96.0, 0, 0],
            drawnHeights(dodgers),
            drawnHeights(mainz),
            drawnHeights(twoLine),
        ]
        for density in arrays {
            XCTAssertEqual(
                MarketMapRail.totalRailHasDistribution(density: density),
                MarketMapRail.marginRailHasDistribution(density: density),
                "the totals subtitle rule disagreed with the margin one on \(density)"
            )
        }
    }

    /// 🔴 EVERY assertion above passes with the view still handing the rule its
    /// thresholds — they pin the RULE, and #4671's own lesson on this same file
    /// is that a correct rule one layer away from the thing that draws is the
    /// whole bug. The signature change makes the old call fail to compile today,
    /// but an overload or a re-derived local would put it back silently.
    ///
    /// Asserted structurally: every `totalRailHasDistribution` call in the view
    /// passes the same `density` the card hands `mapCard`, and no totals card
    /// computes its flag from a threshold array.
    func test_bothTotalsCardsPassTheRuleTheHeightsTheyDraw() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck
            .appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        // Comments first — this file's own prose quotes the call it guards, and
        // a scanner that reads prose is measuring the write-up
        // (`MarketMapMidAxisLabelTests` learned that on this same file).
        let source = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        let calls = source.components(separatedBy: "MarketMapRail.totalRailHasDistribution(").dropFirst()
        XCTAssertEqual(
            calls.count, 2,
            "the full-game and half totals cards are the two callers; a third or a missing one is a story"
        )
        for call in calls {
            let argument = call.prefix(while: { $0 != ")" })
            XCTAssertEqual(
                argument.trimmingCharacters(in: .whitespaces), "density: density",
                "a totals card asked something other than the heights it draws: `\(argument)`"
            )
        }
        XCTAssertTrue(
            source.contains("MarketMapRail.densityFromThresholds("),
            "the builder moved to `MarketMapRail` so the rule and the arithmetic live together"
        )
    }

    // MARK: -

    /// The heights the totals card draws for a set of served rows — the card's
    /// own two calls, in the card's own order.
    private func drawnHeights(
        _ served: [(threshold: Double, overProb: Double)]
    ) -> [Double] {
        let bounds = MarketMapRail.totalBounds(
            thresholds: served.map(\.threshold), markerValues: [], declared: nil, pad: 10
        )
        return MarketMapRail.densityFromThresholds(
            served, rangeMin: bounds.min, rangeMax: bounds.max, segments: 14
        )
    }
}
