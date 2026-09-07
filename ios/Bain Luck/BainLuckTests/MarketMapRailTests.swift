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
}
