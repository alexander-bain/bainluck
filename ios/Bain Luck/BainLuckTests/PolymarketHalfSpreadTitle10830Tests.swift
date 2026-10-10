import XCTest
@testable import Bain_Luck

/// #10830. A live NCAAF page priced only on Polymarket drew a `1st half margin`
/// card with its title and nothing under it. Polymarket writes a half's line in
/// the market name the way #8739 found it writes the game's
/// (`1H Spread: Indiana (-9.5)`, legs `Nebraska` / `Indiana`, `threshold`
/// null), and ``SpreadRungs/TitledSpread`` is anchored at `Spread:`.
///
/// Every fixture is a VERBATIM production row from
/// `GET /api/events/15322373/game-markets`, captured 2026-10-10 16:41Z, live
/// in the 1st quarter. home `Nebraska Cornhuskers`, away `Indiana Hoosiers`.
final class PolymarketHalfSpreadTitle10830Tests: XCTestCase {

    private let footballUnit = SportVocab.forSport("americanfootball_ncaaf").unit
    private let home = "Nebraska Cornhuskers"
    private let away = "Indiana Hoosiers"

    private func leg(_ market: String, _ outcome: String, _ p: Double) -> SpreadRungs.Leg {
        SpreadRungs.Leg(marketName: market, outcomeName: outcome, probability: p)
    }

    /// All twelve 1H legs, as served.
    private var firstHalf: [SpreadRungs.Leg] { [
        leg("1H Spread: Indiana (-7.5)", "Nebraska", 0.78),
        leg("1H Spread: Indiana (-7.5)", "Indiana", 0.22),
        leg("1H Spread: Indiana (-6.5)", "Nebraska", 0.69),
        leg("1H Spread: Indiana (-6.5)", "Indiana", 0.31),
        leg("1H Spread: Indiana (-5.5)", "Nebraska", 0.665),
        leg("1H Spread: Indiana (-5.5)", "Indiana", 0.335),
        leg("1H Spread: Indiana (-4.5)", "Nebraska", 0.65),
        leg("1H Spread: Indiana (-4.5)", "Indiana", 0.35),
        leg("1H Spread: Indiana (-9.5)", "Nebraska", 0.805),
        leg("1H Spread: Indiana (-9.5)", "Indiana", 0.195),
        leg("1H Spread: Indiana (-2.5)", "Nebraska", 0.535),
        leg("1H Spread: Indiana (-2.5)", "Indiana", 0.465),
    ] }

    /// The 2H legs, as served (their prices are not monotone in the line).
    private var secondHalf: [SpreadRungs.Leg] { [
        leg("2H Spread: Indiana (-4.5)", "Indiana", 0.515),
        leg("2H Spread: Indiana (-4.5)", "Nebraska", 0.485),
        leg("2H Spread: Indiana (-3.5)", "Indiana", 0.555),
        leg("2H Spread: Indiana (-3.5)", "Nebraska", 0.445),
        leg("2H Spread: Indiana (-2.5)", "Indiana", 0.615),
        leg("2H Spread: Indiana (-2.5)", "Nebraska", 0.385),
        leg("2H Spread: Indiana (-7.5)", "Nebraska", 0.625),
        leg("2H Spread: Indiana (-7.5)", "Indiana", 0.375),
    ] }

    func testAHalfMapReadsTheHalfTitledLadderOnTheCoverTeamsSide() {
        let map = SpreadRungs.map(
            from: firstHalf, home: home, away: away, sportUnit: footballUnit, readsHalfTitles: true
        )
        XCTAssertEqual(map.rungs.map(\.margin), [-2.5, -4.5, -5.5, -6.5, -7.5, -9.5])
        XCTAssertEqual(map.rungs.map(\.probability), [0.465, 0.35, 0.335, 0.31, 0.22, 0.195])
        XCTAssertTrue(map.rungs.allSatisfy { !$0.isHome }, "Indiana is away; every rung is its cover")
    }

    func testTheSecondHalfReadsTooAndKeepsTheMonotoneRule() {
        let map = SpreadRungs.map(
            from: secondHalf, home: home, away: away, sportUnit: footballUnit, readsHalfTitles: true
        )
        // -2.5 61.5%, -3.5 55.5%, -4.5 51.5%, -7.5 37.5%: already monotone.
        XCTAssertEqual(map.rungs.map(\.margin), [-2.5, -3.5, -4.5, -7.5])
        XCTAssertEqual(map.rungs.map(\.probability), [0.615, 0.555, 0.515, 0.375])
    }

    /// The control: the full-game map never reads a half's title, so a half
    /// leg that reached it would still draw nothing (this was the only
    /// behaviour before #10830, and it is the full-game map's still).
    func testTheFullGameMapStillRefusesAHalfTitle() {
        XCTAssertTrue(
            SpreadRungs.map(from: firstHalf, home: home, away: away, sportUnit: footballUnit).rungs.isEmpty
        )
        XCTAssertNil(SpreadRungs.TitledSpread.read(marketName: "1H Spread: Indiana (-9.5)"))
    }

    func testOnlyAHalfPrefixIsAllowed() {
        XCTAssertEqual(
            SpreadRungs.TitledSpread.read(marketName: "1H Spread: Indiana (-9.5)", readsHalfTitles: true),
            SpreadRungs.TitledSpread(coverTeam: "Indiana", line: 9.5)
        )
        XCTAssertEqual(
            SpreadRungs.TitledSpread.read(marketName: "2nd Half Spread: Indiana (-3.5)", readsHalfTitles: true),
            SpreadRungs.TitledSpread(coverTeam: "Indiana", line: 3.5)
        )
        // #8785's floor: an innings market is not a half, even on a half map.
        XCTAssertNil(SpreadRungs.TitledSpread.read(
            marketName: "1st 5 Innings Spread: Dodgers (-1.5)", readsHalfTitles: true
        ))
        // The plain title still reads on either map.
        XCTAssertEqual(
            SpreadRungs.TitledSpread.read(marketName: "Spread: Texas (-7.5)", readsHalfTitles: true),
            SpreadRungs.TitledSpread(coverTeam: "Texas", line: 7.5)
        )
    }
}
