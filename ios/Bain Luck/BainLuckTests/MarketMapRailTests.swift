import XCTest
@testable import Bain_Luck

/// native/035 — #3503: a totals map stops drawing a rail in a unit the match is
/// not played in, and stops drawing a rail at all when it has nothing to put on
/// one.
///
/// THE PHOTOGRAPH. Event 15305808 (Kasnikowski vs Marrero, `tennis_other`,
/// status `live`), iPhone 17 simulator against production, 2026-09-06 06:08 EDT
/// — `artifacts-native-034/CONTROL-live-tennis-15305808.png`. A card headed
/// **"Games map / Projected total games"** drew a flat purple bar over an axis
/// reading **`170 · 205 · 240+`**. A tennis match is 20–40 games.
///
/// THE MECHANISM, from the event's own `/api/events/15305808/game-markets`:
/// `totals` held exactly one row, `outcome_name: "Under"`, market name
/// `"Ivan Marrero vs. Maks Kasnikowski: Total Sets O/U 2.5"`.
/// `extractTotalThresholds` keeps only outcomes whose name contains `"over"`,
/// so nothing parsed and the rail fell back to the literals in
/// `MarketMapView`: `max(0, 180 - 10) = 170`, `230 + 10 = 240`, midpoint
/// `(170 + 240) / 2 = 205`. Digit for digit the photographed axis. `180` and
/// `230` are basketball points and were applied to every sport in the app.
///
/// With no thresholds there was also no ladder and no density
/// (`buildDensityFromThresholds` returns a flat array below two points) and no
/// marker (`ouLine` had no source left), so the card carried three invented
/// numbers and nothing else.
final class MarketMapRailTests: XCTestCase {

    private let tennis = SportVocab.forSport("tennis_atp_us_open")
    private let nba = SportVocab.forSport("basketball_nba")
    private let cricket = SportVocab.forSport("cricket_ipl")

    // MARK: - Direction 1: real lines must keep setting their own rail

    /// 🔴 THE REGRESSION THAT WOULD BE WORSE THAN THE BUG. A fallback that
    /// starts overriding values a market actually quoted breaks every sport
    /// that works today. Pinned first, and pinned as the exact arithmetic the
    /// pre-#3503 code did, so "the fallback leaked into the data path" fails
    /// here rather than in a screenshot.
    func testQuotedLinesAloneSetTheRailAndTheSportsSpanIsIgnored() {
        let bounds = MarketMapRail.totalBounds(
            thresholds: [21.5, 22.5, 23.5],
            markerValues: [22.5],
            declared: tennis.totalRange,
            pad: 10
        )
        XCTAssertEqual(bounds.min, 11.5, "21.5 - 10, not tennis's declared 12")
        XCTAssertEqual(bounds.max, 33.5, "23.5 + 10, not tennis's declared 48")
    }

    /// The same, on the sport whose literals these were. NBA's rail must not
    /// move at all on a fix aimed at everyone else.
    func testBasketballWithRealLinesIsUntouched() {
        let bounds = MarketMapRail.totalBounds(
            thresholds: [215.5, 220.5, 225.5],
            markerValues: [220.5],
            declared: nba.totalRange,
            pad: 10
        )
        XCTAssertEqual(bounds.min, 205.5)
        XCTAssertEqual(bounds.max, 235.5)
    }

    /// A total cannot be negative — the floor predates #3503 and must survive
    /// it. (A stray 2.5 line among 21.5s used to drag a US Open rail to −7.)
    func testTheRailNeverStartsBelowZero() {
        let bounds = MarketMapRail.totalBounds(
            thresholds: [2.5, 21.5], markerValues: [], declared: tennis.totalRange, pad: 10
        )
        XCTAssertEqual(bounds.min, 0, "2.5 - 10 is -7.5, and no match scores below zero")
        XCTAssertEqual(bounds.max, 31.5)
    }

    // MARK: - Direction 2: no lines must NOT mean basketball's scale

    /// The photographed defect, named by its numbers. Whatever the rule
    /// becomes, it may never again answer 170…240 for a tennis match.
    func testTennisWithNoLinesNeverGetsThePhotographed170To240Rail() {
        let bounds = MarketMapRail.totalBounds(
            thresholds: [], markerValues: [24.5], declared: tennis.totalRange, pad: 10
        )
        XCTAssertNotEqual(bounds, MarketMapRail.Bounds(min: 170, max: 240),
                          "this is the axis in CONTROL-live-tennis-15305808.png")
        XCTAssertEqual(bounds.min, 12, "tennis's own span, from SportVocab")
        XCTAssertEqual(bounds.max, 48)
        XCTAssertTrue(bounds.max < 100, "a tennis match is not played in the hundreds")
    }

    /// Every declared sport falls back to its OWN span, and no two sports that
    /// are played on different scales share one. A regression that re-points
    /// them all at one number fails here for five sports at once.
    func testEveryDeclaredSportFallsBackToItsOwnScale() {
        let expected: [(key: String, min: Double, max: Double)] = [
            ("baseball_mlb", 4, 14),
            ("icehockey_nhl", 2, 9),
            ("soccer_epl", 0, 7),
            ("tennis_wta_us_open", 12, 48),
            ("americanfootball_nfl", 28, 62),
            ("basketball_nba", 180, 230),
        ]
        for row in expected {
            let bounds = MarketMapRail.totalBounds(
                thresholds: [], markerValues: [],
                declared: SportVocab.forSport(row.key).totalRange, pad: 10
            )
            XCTAssertEqual(bounds.min, row.min, "\(row.key) floor")
            XCTAssertEqual(bounds.max, row.max, "\(row.key) ceiling")
        }
        // And they are genuinely distinct — a table where every row was
        // accidentally basketball would satisfy each assertion above only if
        // someone also edited the expectations, but not this one.
        let ceilings = Set(expected.map(\.max))
        XCTAssertEqual(ceilings.count, expected.count, "no two of these sports share a ceiling")
    }

    /// An undeclared sport has no span of ours, so the rail comes from the only
    /// number in evidence. Cricket at 320 must not be squeezed onto a rail
    /// built for something else, and must not invent one either.
    func testUndeclaredSportBuildsItsRailFromTheMarkerNotFromAGuess() {
        XCTAssertNil(cricket.totalRange, "we do not know what a cricket total looks like")
        let bounds = MarketMapRail.totalBounds(
            thresholds: [], markerValues: [320], declared: cricket.totalRange, pad: 10
        )
        XCTAssertTrue(bounds.min < 320 && bounds.max > 320,
                      "the marker must sit ON the rail, not at its end: \(bounds)")
        XCTAssertNotEqual(bounds, MarketMapRail.Bounds(min: 170, max: 240),
                          "the old literals put a 320 marker clean off the right edge")
    }

    /// A marker outside the sport's declared span widens the rail rather than
    /// falling off it — a 61.5-point NFL total is unusual, not impossible.
    func testAMarkerOutsideTheDeclaredSpanWidensTheRail() {
        let bounds = MarketMapRail.totalBounds(
            thresholds: [], markerValues: [71.5],
            declared: SportVocab.forSport("americanfootball_nfl").totalRange, pad: 10
        )
        XCTAssertEqual(bounds.min, 28)
        XCTAssertEqual(bounds.max, 71.5, "the rail stretches to hold its own marker")
    }

    /// The degenerate branch is deliberately absurd rather than plausible: a
    /// caller that ignores `totalMapDrawsNothing` on an undeclared sport gets a
    /// visibly broken rail, not a sourced-looking one (D55, loud beats silent).
    func testNothingAtAllOnAnUndeclaredSportIsLoudlyEmptyNotPlausible() {
        let bounds = MarketMapRail.totalBounds(
            thresholds: [], markerValues: [], declared: nil, pad: 10
        )
        XCTAssertEqual(bounds, MarketMapRail.Bounds(min: 0, max: 1))
    }

    // MARK: - The half rail

    /// Derived from the whole-match span, so a half can never be left behind on
    /// a literal the way `?? 90` / `?? 120` were.
    func testHalfSpansAreHalfTheMatchAndNilWhereTheMatchSpanIs() {
        XCTAssertEqual(nba.halfTotalRange, 90...115)
        XCTAssertEqual(tennis.halfTotalRange, 6...24)
        XCTAssertEqual(SportVocab.forSport("soccer_epl").halfTotalRange, 0...3)
        XCTAssertNil(cricket.halfTotalRange)
    }

    /// A soccer half is 0–3 goals; the old fallback gave it 85–125.
    func testASoccerHalfFallsBackToGoalsNotBasketballPoints() {
        let bounds = MarketMapRail.totalBounds(
            thresholds: [], markerValues: [1.5],
            declared: SportVocab.forSport("soccer_epl").halfTotalRange, pad: 5
        )
        XCTAssertEqual(bounds.min, 0)
        XCTAssertEqual(bounds.max, 3)
        XCTAssertNotEqual(bounds, MarketMapRail.Bounds(min: 85, max: 125))
    }

    // MARK: - The production control: a working card must stay working

    /// 🔴 THE CONTROL, on real production data rather than an invented array.
    ///
    /// Event **14780138** (Patriots at Seahawks, `americanfootball_nfl`, the
    /// Sep 9 opener), full-game Over thresholds read from
    /// `/api/events/14780138/game-markets` on 2026-09-06 — all 19 of them,
    /// verbatim. This is the card the #3503 fix must NOT touch: it has real
    /// lines, so it keeps deriving its own rail, and it must never be
    /// suppressed as empty chrome.
    ///
    /// It is here rather than in a screenshot because the totals map on that
    /// page sits below the fold and `tools/native-shoot.sh` cannot scroll — and
    /// because a raster could not assert the bound anyway.
    func testTheNFLOpenersRealThresholdsKeepDerivingTheirOwnRail() {
        let production: [Double] = [
            23.5, 26.5, 29.5, 32.5, 35.5, 38.5, 41.5, 42.5, 43.5, 44.5,
            45.5, 46.5, 47.5, 50.5, 53.5, 56.5, 59.5, 62.5, 65.5,
        ]
        XCTAssertEqual(production.count, 19, "all 19 lines the event actually served")

        let nfl = SportVocab.forSport("americanfootball_nfl")
        let bounds = MarketMapRail.totalBounds(
            thresholds: production, markerValues: [44.5], declared: nfl.totalRange, pad: 10
        )
        XCTAssertEqual(bounds.min, 13.5, "23.5 - 10, from the market")
        XCTAssertEqual(bounds.max, 75.5, "65.5 + 10, from the market")
        XCTAssertNotEqual(bounds.min, 28, "NFL's declared floor must NOT override a real line")
        XCTAssertNotEqual(bounds.max, 62, "nor its declared ceiling")

        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: true, overUnder: 44.5, isLive: false, isDone: false,
            hasScoreboardTotal: false, hasProjectedTotal: false
        ), "a card with 19 real lines is never empty chrome")
    }

    // MARK: - Empty chrome: does the card draw anything at all?

    /// The photographed card, condition for condition: live tennis, one
    /// unparseable "Under" row, no over/under passed down, and scores that
    /// `scoredHomeScore` has already nulled because the scoreboard counts sets.
    func testThePhotographedTennisCardDrawsNothingAndIsSuppressed() {
        XCTAssertTrue(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false, overUnder: nil,
            isLive: true, isDone: false,
            hasScoreboardTotal: false, hasProjectedTotal: false
        ))
    }

    /// 🔴 BOTH DIRECTIONS. The damaging mirror regression is suppressing a card
    /// that HAS something to say, which would delete working totals maps from
    /// every sport. Each of the four things a card can carry is pinned on its
    /// own, so a guard that collapsed to `return true` fails four times.
    func testAnyOneThingWorthDrawingKeepsTheCard() {
        // A parsed ladder + density.
        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: true, overUnder: nil, isLive: false, isDone: false,
            hasScoreboardTotal: false, hasProjectedTotal: false))
        // A pre-game line handed down from the event, with nothing parsed.
        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false, overUnder: 44.5, isLive: false, isDone: false,
            hasScoreboardTotal: false, hasProjectedTotal: false))
        // A FINAL total on a finished match.
        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false, overUnder: nil, isLive: false, isDone: true,
            hasScoreboardTotal: true, hasProjectedTotal: false))
        // ACTUAL + PROJECTED on a live one.
        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false, overUnder: nil, isLive: true, isDone: false,
            hasScoreboardTotal: true, hasProjectedTotal: true))
    }

    /// The live pair is BOTH markers or neither — `MarketMapView` appends
    /// ACTUAL and PROJECTED under one `if`, so a live card with a scoreboard
    /// but no pace projection still draws nothing.
    func testALiveCardWithAScoreButNoPaceProjectionStillDrawsNothing() {
        XCTAssertTrue(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false, overUnder: nil, isLive: true, isDone: false,
            hasScoreboardTotal: true, hasProjectedTotal: false))
    }

    /// A scoreboard total only becomes a FINAL marker once the match is over —
    /// a pre-match card holding a stale score must not be kept alive by it.
    func testAScoreboardTotalBeforeTheMatchIsNotSomethingToDraw() {
        XCTAssertTrue(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false, overUnder: nil, isLive: false, isDone: false,
            hasScoreboardTotal: true, hasProjectedTotal: true))
    }

    // MARK: - #3576: the card draws, but is the shape on it data?

    /// The photographed card, condition for condition. Event 15292756 (Lions @
    /// Colts, NFL, `completed`, DET 25 – IND 16) served **0 totals rows** —
    /// re-measured against production 2026-09-06 and still 0 — under a subtitle
    /// reading "Final points distribution".
    ///
    /// Three things are asserted together because the fix is only right if all
    /// three hold: the card is still drawn, it no longer claims a distribution,
    /// and the rail is told not to shade one.
    func testThePhotographedSettledNFLCardKeepsItsCardAndDropsTheWordDistribution() {
        let served: [Double] = []   // 0 totals rows, measured

        XCTAssertFalse(MarketMapRail.totalMapDrawsNothing(
            hasThresholds: false, overUnder: nil, isLive: false, isDone: true,
            hasScoreboardTotal: true, hasProjectedTotal: false
        ), "#2086 — the FINAL tile is a real fact, so the card is declared, not deleted")

        XCTAssertFalse(
            MarketMapRail.totalRailHasDistribution(thresholds: served),
            "nothing was quoted, so the flat rail is a placeholder"
        )
        XCTAssertEqual(
            MarketMapRail.fullTotalSubtitle(isDone: true, hasDistribution: false, unit: "points"),
            "Final points",
            "the sentence is the defect: the card may not promise a distribution it has not got"
        )
    }

    /// 🔴 BOTH DIRECTIONS. The damaging mirror regression is stripping the word
    /// from every settled game that DOES have a distribution, which would make
    /// the fix a downgrade on every well-quoted NFL game. The 19 lines are the
    /// ones event 14632820 actually served.
    func testASettledGameWithRealLinesKeepsItsDistributionAndItsWord() {
        let production: [Double] = [
            23.5, 30.5, 33.5, 36.5, 39.5, 41.5, 42.5, 43.5, 44.5,
            45.5, 46.5, 47.5, 50.5, 53.5, 56.5, 59.5, 62.5, 65.5,
        ]
        XCTAssertTrue(MarketMapRail.totalRailHasDistribution(thresholds: production))
        XCTAssertEqual(
            MarketMapRail.fullTotalSubtitle(isDone: true, hasDistribution: true, unit: "points"),
            "Final points distribution"
        )
        XCTAssertEqual(
            MarketMapRail.halfTotalSubtitle(hasDistribution: true, unit: "points"),
            "Half points distribution"
        )
    }

    /// The rule mirrors `buildDensityFromThresholds`'s two flat exits, so it is
    /// pinned against both of them and against the smallest real distribution.
    func testTheRuleMirrorsBothOfTheDensityBuildersFlatExits() {
        // Exit 1 — fewer than two lines.
        XCTAssertFalse(MarketMapRail.totalRailHasDistribution(thresholds: []))
        XCTAssertFalse(MarketMapRail.totalRailHasDistribution(thresholds: [44.5]))
        // Exit 2 — two lines, no positive gap between any pair. `rawPdf` skips
        // every `dt <= 0`, so this returns the same flat array as exit 1.
        XCTAssertFalse(MarketMapRail.totalRailHasDistribution(thresholds: [44.5, 44.5]))
        XCTAssertFalse(MarketMapRail.totalRailHasDistribution(thresholds: [7, 7, 7]))
        // The smallest thing that IS a distribution.
        XCTAssertTrue(MarketMapRail.totalRailHasDistribution(thresholds: [44.5, 45.5]))
        // A duplicate alongside a genuine gap is still a distribution.
        XCTAssertTrue(MarketMapRail.totalRailHasDistribution(thresholds: [44.5, 44.5, 45.5]))
    }

    /// `extractTotalThresholds` sorts, but this rule is handed a bare array and
    /// must not depend on that: it sorts for itself.
    func testTheRuleDoesNotDependOnTheCallerHavingSorted() {
        XCTAssertTrue(MarketMapRail.totalRailHasDistribution(thresholds: [65.5, 23.5, 44.5]))
        XCTAssertTrue(MarketMapRail.totalRailHasDistribution(thresholds: [45.5, 44.5]))
    }

    /// An UNSETTLED card is out of scope and must not move. Its subtitle never
    /// contained the word, so neither state may change it — a fix that routed
    /// this string through the new rule would rewrite every upcoming game's
    /// card for no reason.
    func testAnUnsettledCardsSubtitleIsIdenticalInBothStates() {
        for hasDistribution in [true, false] {
            XCTAssertEqual(
                MarketMapRail.fullTotalSubtitle(
                    isDone: false, hasDistribution: hasDistribution, unit: "points"
                ),
                "Projected total points",
                "the pre-game subtitle promises a projected total, and the PROJECTION marker is one"
            )
        }
    }

    /// The half card gets the same treatment because it has the same defect —
    /// the same `buildDensityFromThresholds`, the same hard-coded word.
    func testTheHalfCardDropsTheWordOnTheSameCondition() {
        XCTAssertEqual(
            MarketMapRail.halfTotalSubtitle(hasDistribution: false, unit: "points"),
            "Half points"
        )
    }

    /// #3630 — the subtitle is unit-aware and must stay so on both branches; a
    /// bases map that started saying "points" would be a fresh bug of the class
    /// `SportVocab.totalTitle` exists to close.
    func testBothSubtitleBranchesCarryTheMapsOwnUnit() {
        XCTAssertEqual(
            MarketMapRail.fullTotalSubtitle(isDone: true, hasDistribution: false, unit: "bases"),
            "Final bases"
        )
        XCTAssertEqual(
            MarketMapRail.fullTotalSubtitle(isDone: true, hasDistribution: true, unit: "games"),
            "Final games distribution"
        )
        XCTAssertEqual(
            MarketMapRail.halfTotalSubtitle(hasDistribution: false, unit: "runs"),
            "Half runs"
        )
    }

    // MARK: - #3763: the same question, asked of the margin card

    /// Every density literal below is what `buildDensityFromSpreads` returns for
    /// a REAL event page, replayed from that page's own
    /// `/api/events/<id>/game-markets` spreads through the builder's arithmetic —
    /// production, 2026-09-06, 22 drawable margin maps over seven leagues
    /// (`artifacts-native-049/census049-margin.json`). Heights are rounded to one
    /// decimal for legibility; the rule reads distinctness, which rounding here
    /// preserves.

    /// The photographed card. Event 15305580 (Zheng @ Swiatek, US Open) after
    /// #3743 left it at one honest rung: one bin at full height, thirteen at
    /// zero, under "Projected margin distribution".
    func testThePhotographedSingleRungMarginCardDropsTheWordDistribution() {
        let swiatekZheng: [Double] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 96, 0]

        XCTAssertFalse(
            MarketMapRail.marginRailHasDistribution(density: swiatekZheng),
            "one bar is not a distribution, however tall"
        )
        XCTAssertEqual(
            MarketMapRail.fullMarginSubtitle(isDone: false, hasDistribution: false),
            "Projected margin",
            "the sentence is the defect: the card may not promise a shape it has not got"
        )
    }

    /// 🔴 THE CARD THAT DECIDES THE SIGNATURE. Event 15305475 (Twins @ White Sox)
    /// draws FIVE populated bins, all at exactly the same height. A
    /// `populatedBins >= 2` rule — the obvious port of the totals rule — passes
    /// this card and prints "distribution" over a solid uniform block, which is
    /// #3576's complaint verbatim.
    ///
    /// It is a settled game, and that is why this is a class and not a specimen:
    /// its five legs are "Chicago WS wins by over 1.5 … 5.5 runs" at `0.99` each,
    /// because the White Sox won by six. Every settled game with a spread ladder
    /// flattens the same way — the lines inside the final margin all resolve to
    /// ~1 — so a bin-count rule would overclaim on all of them.
    func testFivePopulatedBinsAtOneHeightAreStillNotADistribution() {
        let flatPlateau: [Double] = [0, 0, 0, 0, 0, 0, 96, 96, 96, 96, 96, 0, 0, 0]

        XCTAssertEqual(flatPlateau.filter { $0 > 0 }.count, 5, "five bins are populated")
        XCTAssertFalse(
            MarketMapRail.marginRailHasDistribution(density: flatPlateau),
            "a five-bin flat plateau asserts no shape — bin COUNT would have passed it"
        )
    }

    /// 🔴 BOTH DIRECTIONS. The damaging mirror regression is stripping the word
    /// from every well-quoted card. Event 14780138 (Patriots @ Seahawks, NFL)
    /// serves 31 rungs and draws a genuinely peaked rail across 12 bins; 13 of
    /// the 22 censused cards are of this kind and none of them may move.
    func testAWellQuotedNFLMarginCardKeepsItsShapeAndItsWord() {
        let patriotsSeahawks: [Double] = [
            0, 37.2, 37.2, 67.1, 89.8, 89.8, 96, 89.8, 78.5, 37.2, 31, 37.2, 12.4, 0,
        ]
        XCTAssertTrue(MarketMapRail.marginRailHasDistribution(density: patriotsSeahawks))
        XCTAssertEqual(
            MarketMapRail.fullMarginSubtitle(isDone: false, hasDistribution: true),
            "Projected margin distribution"
        )
        XCTAssertEqual(
            MarketMapRail.fullMarginSubtitle(isDone: true, hasDistribution: true),
            "Final margin distribution"
        )
        XCTAssertEqual(
            MarketMapRail.halfMarginSubtitle(hasDistribution: true),
            "Half margin distribution"
        )
    }

    /// 🔴 THE DIFFERENCE FROM THE TOTALS RULE, and the one a port would miss.
    /// `fullTotalSubtitle` leaves its unsettled string alone because that string
    /// never said "distribution". The margin card's does, in BOTH states, so both
    /// are gated. The censused single-rung population is mixed — live US Open
    /// matches and the completed MLB game 15305471 — so a settled-only gate would
    /// have left most of them overclaiming.
    func testTheMarginCardIsGatedBeforeTheGameAsWellAsAfterIt() {
        XCTAssertEqual(
            MarketMapRail.fullMarginSubtitle(isDone: false, hasDistribution: false),
            "Projected margin",
            "an upcoming or live card overclaims too — this is not a settled-only rule"
        )

        // 15305471, Rays @ Rangers, `completed`: one rung, one bin.
        let settledSingleRung: [Double] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 96, 0, 0, 0, 0]
        XCTAssertFalse(MarketMapRail.marginRailHasDistribution(density: settledSingleRung))
        XCTAssertEqual(
            MarketMapRail.fullMarginSubtitle(isDone: true, hasDistribution: false),
            "Final margin"
        )
    }

    /// The half card has the same hard-coded word over the same builder's output,
    /// exactly as `halfTotalCard` did before #3576.
    func testTheHalfMarginCardDropsTheWordOnTheSameCondition() {
        XCTAssertEqual(MarketMapRail.halfMarginSubtitle(hasDistribution: false), "Half margin")
    }

    /// The degenerate rails, pinned so a future edit cannot make one of them
    /// claim a shape. The all-`5` array is what `buildDensityFromSpreads` returns
    /// for NO rungs at all — a uniform rail that `marginMapIsEmptyChrome` usually
    /// suppresses, and which must never read as a distribution if it does draw.
    func testTheDegenerateRailsClaimNothing() {
        XCTAssertFalse(MarketMapRail.marginRailHasDistribution(density: []))
        XCTAssertFalse(MarketMapRail.marginRailHasDistribution(density: Array(repeating: 0, count: 14)))
        XCTAssertFalse(
            MarketMapRail.marginRailHasDistribution(density: Array(repeating: 5, count: 14)),
            "`buildDensityFromSpreads([])`'s flat rail is a placeholder, not data"
        )
        XCTAssertFalse(MarketMapRail.marginRailHasDistribution(density: [96]))
    }

    /// The admitted borderline, asserted so it is on the record as a decision
    /// rather than an accident. Event 15298326 (Cardinals @ Rockies) draws two
    /// bins at wildly different heights. Two bars do say where the mass is, so
    /// this is a distribution; what the rule refuses is a rail asserting NO
    /// shape, not one asserting a coarse shape.
    func testTwoBinsOfDifferentHeightAreADistribution() {
        let cardinalsRockies: [Double] = [0, 0, 0, 0, 96, 0, 0, 0, 0, 1.9, 0, 0, 0, 0]
        XCTAssertTrue(MarketMapRail.marginRailHasDistribution(density: cardinalsRockies))
    }

    /// Zero is not a height. A rail whose only variation is between "shaded" and
    /// "not shaded" has one height on it, and the rule must not read the zeros as
    /// a second one — that reading would call every single-rung card a
    /// distribution and fix nothing.
    func testTheZeroBinsAreNotCountedAsASecondHeight() {
        XCTAssertFalse(MarketMapRail.marginRailHasDistribution(density: [0, 96, 0]))
        XCTAssertFalse(MarketMapRail.marginRailHasDistribution(density: [96, 0, 96, 0, 96]))
        XCTAssertTrue(MarketMapRail.marginRailHasDistribution(density: [96, 0, 95.9]))
    }

    // MARK: - #3820: a marker dot stays on the rail it names

    /// The specimen, replayed as arithmetic. Every number here was read off
    /// `artifacts-native-051/mlb-15305472-s700.png` in pixels at @3x BEFORE the
    /// fix was written, and the model was required to reproduce BOTH dots
    /// before either was believed — a model that fits one marker and misses its
    /// twin is describing a hidden variable, not the layout.
    private let railWidth: Double = 342      // 402 - 2*16 page - 2*14 card
    private let dotWidth: Double = 24        // 22 pt frame + a 2 pt centred stroke

    /// 🔴 THE DEFECT. `FINAL 18` on a `4 … 18` rail is 100%, so `.position`
    /// centred the dot on the rail's own trailing edge and half of it — 12 pt —
    /// hung outside the track. Measured centre 1115.5 px against a rail ending
    /// at 1115.5 px: the same number, which is the whole bug.
    func testAValueAtTheTopOfTheScaleKeepsItsDotOnTheRail() {
        let ideal = railWidth   // (18 - 4) / (18 - 4) = 100%
        XCTAssertEqual(ideal, 342, "the pre-fix centre was the rail's own end")

        let placed = MarketMapRail.clampedMarkerCenterX(
            idealX: ideal, markerWidth: dotWidth, railWidth: railWidth
        )
        XCTAssertEqual(placed, 330, accuracy: 0.001)
        XCTAssertLessThanOrEqual(
            placed + dotWidth / 2, railWidth,
            "the dot's trailing edge must not pass the end of its own track"
        )
    }

    /// The other end, which no production frame has photographed yet and which
    /// is reachable by any game landing on the floor of its scale. Asserted in
    /// the same breath because a clamp written for one end is exactly the shape
    /// of bug that ships fixing only one end.
    func testAValueAtTheBottomOfTheScaleKeepsItsDotOnTheRail() {
        let placed = MarketMapRail.clampedMarkerCenterX(
            idealX: 0, markerWidth: dotWidth, railWidth: railWidth
        )
        XCTAssertEqual(placed, 12, accuracy: 0.001)
        XCTAssertGreaterThanOrEqual(
            placed - dotWidth / 2, 0,
            "the dot's leading edge must not pass the start of its own track"
        )
    }

    /// 🔴 THE HALF THE CLAMP IS UNSAFE AGAINST. Over-correcting an overhang is
    /// safe against a dot leaving the track and UNSAFE against that dot closing
    /// on its neighbour — a bound is only ever safe against one of the two
    /// failures, so the other one gets a number.
    ///
    /// On the specimen the two centres sit 132 px = 44 pt apart. The clamp moves
    /// `FINAL` 12 pt and leaves `PRE-GAME` alone, so 32 pt remains against a
    /// 24 pt drawn width: 8 pt of visible track still between them, which is
    /// what the photograph must show. A future change to `markerRadius` that
    /// would push these two into contact fails HERE.
    func testFinalAndPreGameStayApartAfterTheClamp() {
        let final = MarketMapRail.clampedMarkerCenterX(
            idealX: railWidth, markerWidth: dotWidth, railWidth: railWidth
        )
        // (16.2 - 4) / (18 - 4) = 87.142…%
        let preIdeal = railWidth * (16.2 - 4) / (18 - 4)
        let pre = MarketMapRail.clampedMarkerCenterX(
            idealX: preIdeal, markerWidth: dotWidth, railWidth: railWidth
        )
        XCTAssertEqual(pre, preIdeal, accuracy: 0.001, "a mid-scale dot is never moved")

        let separation = final - pre
        XCTAssertEqual(separation, 32.0, accuracy: 0.5)
        XCTAssertGreaterThan(
            separation, dotWidth,
            "the clamp must not push the end dot into the one beside it"
        )
    }

    /// A dot that is not at an end is not moved AT ALL. This is the assertion
    /// that stops the fix from quietly becoming an inset rail: every marker on
    /// every map in the app is mid-scale, and if this drifts, every card in the
    /// app is drawing its values in the wrong place to fix two of them.
    func testEveryInteriorValueIsLeftExactlyWhereItWas() {
        for pct in stride(from: 4.0, through: 96.0, by: 4.0) {
            let ideal = railWidth * pct / 100
            XCTAssertEqual(
                MarketMapRail.clampedMarkerCenterX(
                    idealX: ideal, markerWidth: dotWidth, railWidth: railWidth
                ),
                ideal, accuracy: 0.001,
                "\(pct)% is \(dotWidth / 2) pt clear of both ends and must not move"
            )
        }
    }

    /// The narrow rail. `densityRail` also draws inside a half-width card on
    /// iPad, where `markerRadius` drops to 11 and the drawn dot to 20 pt; the
    /// clamp must scale with the dot it is given rather than with a constant
    /// copied from the phone.
    func testTheClampFollowsTheDotSizeNotAHardCodedPhoneNumber() {
        let narrowDot: Double = 20   // markerRadius 11 → 11*2 - 4 + 2
        XCTAssertEqual(
            MarketMapRail.clampedMarkerCenterX(
                idealX: 280, markerWidth: narrowDot, railWidth: 280
            ),
            270, accuracy: 0.001
        )
    }

    /// The degenerate pass. SwiftUI hands a `GeometryReader` a zero width before
    /// it hands out a real one, and a rail narrower than its own dot has no
    /// placement that keeps the dot on it. Centre it rather than pick an end, so
    /// the first frame is symmetric instead of jammed left — and so the call
    /// site never grows an `if` for a case the geometry already answers.
    func testARailNarrowerThanItsOwnDotCentresTheDot() {
        XCTAssertEqual(
            MarketMapRail.clampedMarkerCenterX(idealX: 0, markerWidth: dotWidth, railWidth: 0),
            0, accuracy: 0.001
        )
        XCTAssertEqual(
            MarketMapRail.clampedMarkerCenterX(idealX: 30, markerWidth: dotWidth, railWidth: 16),
            8, accuracy: 0.001
        )
    }
}
