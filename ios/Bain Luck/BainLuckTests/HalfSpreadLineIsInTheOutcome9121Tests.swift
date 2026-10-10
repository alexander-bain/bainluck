import XCTest
@testable import Bain_Luck

/// #9121 (reader half). Every Kalshi half/quarter spread leg serves `threshold`
/// as the PERIOD digit — the server takes the first number in the name, and in
/// `"Cruz Azul wins the 1H by more than 1.5 goals"` that is the "1" of "1H".
/// `SpreadRungs` trusted `threshold` first, so every rung of a half margin map
/// sat at 1 (first half) or 2 (second half) whatever the line said.
///
/// Measured over 41 football/soccer pages on production 2026-09-27 12:20Z:
/// 1,587 spread legs read a different line under the text-first rule, every one
/// of them a half/quarter market carrying its period digit; no full-game leg
/// moved.
///
/// Every fixture is a VERBATIM production row from
/// `GET /api/events/{id}/game-markets`, captured 2026-09-27, served
/// `threshold` included.
final class HalfSpreadLineIsInTheOutcome9121Tests: XCTestCase {

    private func leg(_ market: String, _ outcome: String, _ threshold: Double?, _ p: Double?) -> SpreadRungs.Leg {
        SpreadRungs.Leg(marketName: market, outcomeName: outcome, threshold: threshold, probability: p)
    }

    private func margins(_ legs: [SpreadRungs.Leg], home: String, away: String, sport: String) -> [Double] {
        SpreadRungs.map(from: legs, home: home, away: away, sportUnit: SportVocab.forSport(sport).unit)
            .rungs.map(\.margin).sorted()
    }

    /// Event 15315795, Cruz Azul 3-3 Toluca (Liga MX, settled) — the specimen.
    /// home `Cruz Azul`, away `Toluca`.
    func testTheSpecimensHalvesDrawAtOnePointFiveNotAtTheirPeriodNumber() {
        let first = [
            leg("Cruz Azul vs Toluca: First Half Spread", "Cruz Azul wins the 1H by more than 1.5 goals", 1.0, 1.0),
            leg("Cruz Azul vs Toluca: First Half Spread", "Toluca wins the 1H by more than 1.5 goals", 1.0, nil),
        ]
        let second = [
            leg("Cruz Azul vs Toluca: Second Half Spread", "Toluca wins the 2H by more than 1.5 goals", 2.0, 1.0),
            leg("Cruz Azul vs Toluca: Second Half Spread", "Cruz Azul wins the 2H by more than 1.5 goals", 2.0, nil),
        ]
        // #6676 / #10850 — the unpriced leg of each half is no rung (it used to
        // draw as a made-up 50%); the priced leg still sits at 1.5, not at its
        // period digit, which is what this case is about.
        XCTAssertEqual(margins(first, home: "Cruz Azul", away: "Toluca", sport: "soccer_mexico_ligamx"), [1.5])
        XCTAssertEqual(margins(second, home: "Cruz Azul", away: "Toluca", sport: "soccer_mexico_ligamx"), [-1.5])
    }

    /// Event 14870011, Texas @ Tennessee (NCAAF). home `Tennessee Volunteers`,
    /// away `Texas Longhorns`. Every leg of the first half served `threshold 1.0`,
    /// so the whole ladder collapsed onto one rung per side at 1.
    func testACollegeFootballHalfLadderKeepsEveryLine() {
        let market = "Texas vs Tennessee: 1st Half Spread"
        let legs = [
            leg(market, "Texas wins 1H by over 2.5 points", 1.0, 0.9),
            leg(market, "Texas wins 1H by over 6.5 points", 1.0, 0.7),
            leg(market, "Texas wins 1H by over 17.5 points", 1.0, 0.2),
            leg(market, "Tennessee wins 1H by over 3.5 points", 1.0, 0.1),
            leg(market, "Tennessee wins 1H by over 10.5 points", 1.0, 0.05),
        ]
        XCTAssertEqual(
            margins(legs, home: "Tennessee Volunteers", away: "Texas Longhorns", sport: "americanfootball_ncaaf"),
            [-17.5, -6.5, -2.5, 3.5, 10.5]
        )
    }

    // MARK: - The reader

    func testTheLineIsTheLastNumberThatIsNotAPeriod() {
        XCTAssertEqual(SpreadRungs.lineInOutcome("Cruz Azul wins the 1H by more than 1.5 goals"), 1.5)
        XCTAssertEqual(SpreadRungs.lineInOutcome("Texas wins 1H by over 17.5 points"), 17.5)
        XCTAssertEqual(SpreadRungs.lineInOutcome("Indiana wins 1Q by over 16.5 points"), 16.5)
        XCTAssertEqual(SpreadRungs.lineInOutcome("Lakers -4.5 (1st Half)"), 4.5)
        XCTAssertEqual(SpreadRungs.lineInOutcome("Tie 2nd Half"), nil)
        XCTAssertEqual(SpreadRungs.lineInOutcome("Seattle wins by 15 or more points"), 15)
        XCTAssertEqual(SpreadRungs.lineInOutcome("Texas"), nil)
    }

    // MARK: - Controls: what must NOT move

    /// A full-game leg whose text and served `threshold` agree reads exactly as
    /// before (event 14780138, New England @ Seattle, verbatim).
    func testCONTROLAFullGameLegIsUnchanged() {
        let legs = [
            leg("New England vs Seattle: Spread", "Seattle wins by over 1.5 points", 1.5, 0.145),
            leg("New England vs Seattle: Spread", "New England wins by over 4.5 points", 4.5, 0.145),
        ]
        XCTAssertEqual(margins(legs, home: "Seattle Seahawks", away: "New England Patriots", sport: "americanfootball_nfl"),
                       [-4.5, 1.5])
    }

    /// An outcome that states no line still falls back to the served
    /// `threshold` — the fallback survives, only the precedence changed.
    func testCONTROLAnOutcomeWithNoNumberStillReadsTheServedThreshold() {
        let legs = [leg("Texans vs Colts: Spread", "Houston Texans", 3.5, 0.55)]
        XCTAssertEqual(margins(legs, home: "Houston Texans", away: "Indianapolis Colts", sport: "americanfootball_nfl"),
                       [3.5])
    }
}
