import XCTest
@testable import Bain_Luck

/// native/040 — #3533. The margin-map half of #3509's rule: **a rung's unit is
/// declared by its own market name, and the sport's unit is only the fallback.**
///
/// `MarketQuotedUnitTests` pins the totals half. This pins the margin half, the
/// rail that follows from it, the title that names it, and the footnote that
/// must stop pointing at a map it no longer describes.
final class MarginQuotedUnitTests: XCTestCase {

    private let tennis = SportVocab.forSport("tennis_atp_us_open")
    private let nfl = SportVocab.forSport("americanfootball_nfl")
    private let mlb = SportVocab.forSport("baseball_mlb")
    private let nhl = SportVocab.forSport("hockey_nhl")
    private let mma = SportVocab.forSport("mma_mixed_martial_arts")

    // MARK: - What a market title declares

    /// The verbatim production titles, 2026-09-06.
    func testTheVenuesOwnTitlesDeclareTheirUnit() {
        XCTAssertEqual(SportVocab.declaredMarginUnit(inMarketName: "Set Handicap: Swiatek (-1.5) vs Zheng (+1.5)"), "sets")
        XCTAssertEqual(SportVocab.declaredMarginUnit(inMarketName: "Game Spread: Swiatek (-5.5) vs Zheng (+5.5)"), "games")
        XCTAssertEqual(SportVocab.declaredMarginUnit(inMarketName: "Set Handicap: Medvedev (-2.5) vs Tiafoe (+2.5)"), "sets")
    }

    /// 🔴 The reason this is narrowed to `knownUnits`. A venue writes the
    /// SUBJECT in the same slot, and reading it as a unit is the very bug this
    /// fixes wearing a new costume.
    func testASubjectInTheUnitSlotIsNotAUnit() {
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: "Asian Handicap: Arsenal (-1.5) vs Chelsea (+1.5)"))
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: "Alternate Spread: Chicago (-3.5) vs Carolina (+3.5)"))
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: "Team Handicap: A (-1.5) vs B (+1.5)"))
    }

    /// `Puck Line` is not a line in pucks — it is a line in goals, which is
    /// hockey's own unit, so nil is the right answer and the fallback gives it.
    func testPuckLineFallsBackToTheSportsUnitRatherThanInventingOne() {
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: "Puck Line: Bruins (-1.5) vs Sabres (+1.5)"))
        XCTAssertEqual(nhl.unit, "goals")
        XCTAssertEqual(nhl.marginRange(quotedBy: nhl.unit), 5)
    }

    /// `Run Line` and `Point Spread` do name real units, and they name the ones
    /// their sports already quote — so nothing about those maps moves.
    func testTheDeclaredUnitsThatAgreeWithTheirSportChangeNothing() {
        XCTAssertEqual(SportVocab.declaredMarginUnit(inMarketName: "Run Line: Braves (-1.5) vs Phillies (+1.5)"), "runs")
        XCTAssertEqual(mlb.marginRange(quotedBy: "runs"), 5)
        XCTAssertEqual(SportVocab.declaredMarginUnit(inMarketName: "Point Spread: Rams (-3.5) vs 49ers (+3.5)"), "points")
        XCTAssertEqual(nfl.marginRange(quotedBy: "points"), 18)
    }

    /// 🔴 THE CONTROL. Every named NFL ladder in production has a colon where
    /// the unit noun would be. If this ever started matching, every football
    /// map in the app would change rail on a fix aimed at tennis.
    func testANamedLadderDeclaresNothing() {
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: "New England vs Seattle: Spread"))
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: "San Francisco vs Los Angeles: Spread"))
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: "Chicago vs Carolina: Winning Margin"))
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: ""))
        XCTAssertNil(SportVocab.declaredMarginUnit(inMarketName: nil))
    }

    // MARK: - The rail that follows

    /// `marginRange` is "the sport's realistic spread IN `unit`", so it is
    /// meaningless on a rail quoted in anything else.
    func testTheSportsSpanIsWithheldFromAMapNotDrawnInItsUnit() {
        XCTAssertEqual(tennis.marginRange, 6)
        XCTAssertEqual(tennis.marginRange(quotedBy: "games"), 6)
        XCTAssertNil(tennis.marginRange(quotedBy: "sets"))
        XCTAssertNil(nfl.marginRange(quotedBy: "sets"))
        XCTAssertNil(mma.marginRange(quotedBy: "rounds"))
    }

    /// 🔴 With a declared span the arithmetic is verbatim what it was before
    /// #3533, so no map drawn in its own sport's unit moves by a pixel.
    /// Measured off event 14632820 (SF 49ers @ LA Rams, `artifacts-native-038`):
    /// margins `[-15.0, 20.5]` gave rail `[-18.0, 23.5]`.
    func testADeclaredSpanReproducesTheOldRailExactly() {
        let bounds = MarketMapRail.marginBounds(margins: [-15.0, 20.5], declared: 18, pad: 3)
        XCTAssertEqual(bounds.min, -18.0)
        XCTAssertEqual(bounds.max, 23.5)

        // And the sport's span still widens a rail narrower than it.
        let narrow = MarketMapRail.marginBounds(margins: [-1.5, 1.5], declared: 18, pad: 3)
        XCTAssertEqual(narrow.min, -18.0)
        XCTAssertEqual(narrow.max, 18.0)

        // No rungs at all. The old `?? Double(-maxMargin)` fed the fallback
        // THROUGH the pad, so an NFL card with nothing parsed drew ±21, not
        // ±18. That is verbatim what it did and verbatim what it still does —
        // pinned because it is surprising, and because this test was written
        // asserting ±18 and was wrong.
        let bare = MarketMapRail.marginBounds(margins: [], declared: 18, pad: 3)
        XCTAssertEqual(bare.min, -21.0)
        XCTAssertEqual(bare.max, 21.0)
    }

    /// Without one, the rungs set their own scale — symmetric, and rounded up
    /// past the outermost rung so the end labels ("by 2+") are true of it.
    /// A ±3 pad here would be three SETS of empty rail either side of a ±1.5
    /// handicap.
    func testAnUndeclaredSpanIsBuiltFromTheRungsAlone() {
        XCTAssertEqual(MarketMapRail.marginBounds(margins: [-1.5, 1.5], declared: nil, pad: 3),
                       MarketMapRail.Bounds(min: -2, max: 2))
        XCTAssertEqual(MarketMapRail.marginBounds(margins: [-2.5, 2.5], declared: nil, pad: 3),
                       MarketMapRail.Bounds(min: -3, max: 3))
        XCTAssertEqual(MarketMapRail.marginBounds(margins: [-1.5, 1.5, -2.5, 2.5], declared: nil, pad: 3),
                       MarketMapRail.Bounds(min: -3, max: 3))
        // A whole-number rung is not left sitting on the end of its own axis.
        XCTAssertEqual(MarketMapRail.marginBounds(margins: [-2, 2], declared: nil, pad: 3),
                       MarketMapRail.Bounds(min: -3, max: 3))
        // Nothing at all: visibly small rather than plausible.
        XCTAssertEqual(MarketMapRail.marginBounds(margins: [], declared: nil, pad: 3),
                       MarketMapRail.Bounds(min: -1, max: 1))
    }

    // MARK: - The title

    func testTheTitleNamesTheUnitTheMapIsActuallyDrawnIn() {
        XCTAssertEqual(tennis.marginTitle(quotedBy: "games"), "Game margin map", "verbatim the sport's own words")
        XCTAssertEqual(tennis.marginTitle(quotedBy: "sets"), "Set margin map")
        XCTAssertEqual(nfl.marginTitle(quotedBy: "points"), "Margin map")
        XCTAssertEqual(mlb.marginTitle(quotedBy: "runs"), "Run margin map")
        XCTAssertEqual(mma.marginTitle(quotedBy: ""), "Margin map")
    }

    // MARK: - The footnote (#3533 requirement 2, #3503's rule)

    /// 🔴 THE ORPHANED POINTER. `unitMismatchNote` prints *"The scoreboard
    /// reports sets, this market quotes games"* — a sentence about a map drawn
    /// in `unit` and no other. The old gate was `!scoreboardCountsTheUnit`,
    /// which is a fact about the SPORT, so a tennis SET margin map (which
    /// withholds nothing — the scoreboard reports sets) would have carried a
    /// footnote claiming it quoted games.
    func testTheNoteDescribesOnlyAMapDrawnInTheSportsUnit() {
        XCTAssertTrue(tennis.noteDescribesMap(quotedBy: "games"), "a games map on a sets scoreboard: the sentence is true")
        XCTAssertFalse(tennis.noteDescribesMap(quotedBy: "sets"), "a sets map withholds nothing")
        XCTAssertFalse(tennis.noteDescribesMap(quotedBy: ""))
    }

    /// And it never fires on a sport whose scoreboard counts what it quotes —
    /// which is every sport but tennis. This is the direction that would have
    /// printed the sentence over every margin map in the app.
    func testTheNoteNeverFiresOnASportWhoseScoreboardAgrees() {
        for vocab in [nfl, mlb, nhl, mma, SportVocab.forSport("soccer_epl"), SportVocab.forSport("basketball_nba")] {
            XCTAssertFalse(vocab.noteDescribesMap(quotedBy: vocab.unit))
            XCTAssertNil(vocab.unitMismatchNote(settled: false))
        }
    }
}
