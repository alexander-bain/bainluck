import XCTest
@testable import Bain_Luck

/// #9944 — CHW @ HOU (15321836), live, bottom of the 1st at 4–1 (21:47Z 9/30):
/// `/game-markets` served `pace = {total_scored: 5, projected_total: 90,
/// fraction_elapsed: 0.056}` and the totals map read "PROJECTED 90" — one
/// half-inning's runs run forward over the whole game. The served opening total
/// was 7.5; the sportsbook live total 12.5.
///
/// ``LivePaceStanding`` now anchors the early game to the opening total
/// (`scored + (1 − elapsed) × opening` = 12.08), and with no opening draws the
/// bare run-forward only from half the game on — web's `liveProjectedTotal`
/// (PR #9945). Both views pass the opening their own Pre-game marker draws;
/// ``ALivePaceAgreesWithTheHeader9708Tests`` pins that wiring.
final class AnEarlyPaceIsAnchoredToThePregameTotal9944Tests: XCTestCase {

    private func pace(scored: Int?, projected: Double?, elapsed: Double?) -> GameMarketPace {
        GameMarketPace(totalScored: scored, projectedTotal: projected,
                       fractionElapsed: elapsed, timeRemainingDisplay: nil)
    }

    /// The photographed body, decoded from snake_case, under its own 4–1 header
    /// and the served 7.5 opening: 12, not 90.
    func testThePhotographedFirstInningPaceProjectsTwelveNotNinety() throws {
        let body = #"{"total_scored": 5, "projected_total": 90.0, "fraction_elapsed": 0.056}"#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let served = try decoder.decode(GameMarketPace.self, from: Data(body.utf8))
        let live = try XCTUnwrap(LivePaceStanding.projection(served, openingTotal: 7.5,
                                                             scoreboardHome: 1, scoreboardAway: 4))
        XCTAssertEqual(live.projected, 5 + 0.944 * 7.5, accuracy: 1e-9)
        XCTAssertEqual(Int(live.projected.rounded()), 12)
        XCTAssertEqual(live.scored, 5)
    }

    /// No opening served: a sliver of the game has no projection at all.
    func testWithoutAnOpeningAnEarlyRunForwardProjectsNothing() {
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 5, projected: 90, elapsed: 0.056),
                                                 openingTotal: nil, scoreboardHome: 1, scoreboardAway: 4))
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 5, projected: 10.2, elapsed: 0.49),
                                                 openingTotal: nil, scoreboardHome: 1, scoreboardAway: 4))
        // A non-positive opening is no opening.
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 5, projected: 90, elapsed: 0.056),
                                                 openingTotal: 0, scoreboardHome: 1, scoreboardAway: 4))
    }

    /// The anchor never resurrects what the earlier rules refuse.
    func testTheAnchorKeepsTheEarlierRefusals() {
        // #6831 — scoreless.
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 0, projected: 0, elapsed: 0.3),
                                                 openingTotal: 7.5, scoreboardHome: 0, scoreboardAway: 0))
        // #9708 — an older score than the header.
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 5, projected: 90, elapsed: 0.056),
                                                 openingTotal: 7.5, scoreboardHome: 2, scoreboardAway: 4))
        // #9930 — regulation ran out.
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 6, projected: 6, elapsed: 1.0),
                                                 openingTotal: 7.5, scoreboardHome: 3, scoreboardAway: 3))
        // No game behind it.
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 1, projected: nil, elapsed: 0),
                                                 openingTotal: 7.5, scoreboardHome: 1, scoreboardAway: 0))
    }

    // MARK: - Controls: what still draws

    /// With an opening, a late game is anchored too — not the run-forward — so
    /// the projection and the Pre-game marker read one number all game.
    func testCONTROLWithAnOpeningALateGameIsAnchoredNotRunForward() throws {
        let live = try XCTUnwrap(LivePaceStanding.projection(pace(scored: 6, projected: 8, elapsed: 0.75),
                                                             openingTotal: 8, scoreboardHome: 4, scoreboardAway: 2))
        XCTAssertEqual(live.projected, 8, accuracy: 1e-9)   // 6 + 0.25 × 8
        let other = try XCTUnwrap(LivePaceStanding.projection(pace(scored: 6, projected: 8, elapsed: 0.75),
                                                              openingTotal: 12, scoreboardHome: 4, scoreboardAway: 2))
        XCTAssertEqual(other.projected, 9, accuracy: 1e-9)  // 6 + 0.25 × 12
    }

    /// No opening, half the game behind it: the served run-forward stands, at
    /// the boundary itself (`>= 0.5`).
    func testCONTROLWithoutAnOpeningTheRunForwardStandsFromHalfTheGame() throws {
        let half = try XCTUnwrap(LivePaceStanding.projection(pace(scored: 4, projected: 8, elapsed: 0.5),
                                                             openingTotal: nil, scoreboardHome: 3, scoreboardAway: 1))
        XCTAssertEqual(half.projected, 8)
    }

    /// No fraction served: the run-forward reads as served (nothing to anchor
    /// or refuse on), opening or not.
    func testCONTROLAPaceWithoutAFractionReadsAsServed() throws {
        let live = try XCTUnwrap(LivePaceStanding.projection(pace(scored: 3, projected: 7, elapsed: nil),
                                                             openingTotal: 7.5, scoreboardHome: 2, scoreboardAway: 1))
        XCTAssertEqual(live.projected, 7)
    }
}
