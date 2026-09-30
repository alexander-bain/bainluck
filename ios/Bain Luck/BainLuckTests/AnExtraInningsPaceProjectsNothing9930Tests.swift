import XCTest
@testable import Bain_Luck

/// #9930 — PHI @ ATL Wild Card game 2 (15321782), live, Top 10th at 3–3:
/// `/game-markets` served `pace = {total_scored: 6, projected_total: 6,
/// fraction_elapsed: 1.0}` and the spectrum strip printed "PACE 6 · 6 scored",
/// a total a tied game cannot finish on. The estimator caps elapsed time at the
/// whole game, so from the end of regulation the projection is the tally.
///
/// Web refuses once `fraction_elapsed >= 1` (PR #9932); ``LivePaceStanding``
/// does the same, and both views that draw a live pace are already pinned to it
/// by ``ALivePaceAgreesWithTheHeader9708Tests``.
final class AnExtraInningsPaceProjectsNothing9930Tests: XCTestCase {

    private func pace(scored: Int?, projected: Double?, elapsed: Double?) -> GameMarketPace {
        GameMarketPace(totalScored: scored, projectedTotal: projected,
                       fractionElapsed: elapsed, timeRemainingDisplay: nil)
    }

    /// The photographed payload under its own 3–3 header. The score agrees and
    /// is non-zero, so neither #9708 arm withholds it — only the clock does.
    func testThePhotographedTopTenthPaceProjectsNothing() {
        let tenth = pace(scored: 6, projected: 6, elapsed: 1.0)
        XCTAssertTrue(LivePaceStanding.agrees(tenth, scoreboardHome: 3, scoreboardAway: 3))
        XCTAssertTrue(LivePaceStanding.clockRanOut(tenth))
        XCTAssertNil(LivePaceStanding.projection(tenth, scoreboardHome: 3, scoreboardAway: 3))
    }

    /// Decoded from the served snake_case body, not built by hand, so a key
    /// that stopped decoding (fraction → nil → "reads as it always did") fails.
    func testTheServedBodyDecodesToAPaceWhoseClockRanOut() throws {
        let body = #"{"total_scored": 6, "projected_total": 6.0, "fraction_elapsed": 1.0}"#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let served = try decoder.decode(GameMarketPace.self, from: Data(body.utf8))
        XCTAssertEqual(served.fractionElapsed, 1.0)
        XCTAssertNil(LivePaceStanding.projection(served, scoreboardHome: 3, scoreboardAway: 3))
    }

    /// No scoreboard on the page leaves only the pace's own evidence — still
    /// no time to run forward.
    func testWithoutAScoreboardAnOvertimePaceStillProjectsNothing() {
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 44, projected: 44, elapsed: 1.0),
                                                 scoreboardHome: nil, scoreboardAway: nil))
    }

    // MARK: - Controls: what still draws

    /// Bottom of the 9th, a sliver of regulation left: still a forecast. Kills
    /// the `> 0.9` / "refuse late game" mutant; with the `>= 1` boundary it
    /// also kills `> 1` via the photographed test above.
    func testCONTROLALateRegulationPaceStillProjects() throws {
        let ninth = try XCTUnwrap(LivePaceStanding.projection(pace(scored: 6, projected: 6.3, elapsed: 0.95),
                                                              scoreboardHome: 3, scoreboardAway: 3))
        XCTAssertEqual(ninth.projected, 6.3)
        XCTAssertEqual(ninth.scored, 6)
    }

    /// A pace that omits the fraction reads as it did before (web's posture:
    /// refused on the evidence, not on its absence).
    func testCONTROLAPaceWithoutAFractionStillProjects() throws {
        let unfractioned = pace(scored: 3, projected: 7, elapsed: nil)
        XCTAssertFalse(LivePaceStanding.clockRanOut(unfractioned))
        let live = try XCTUnwrap(LivePaceStanding.projection(unfractioned,
                                                             scoreboardHome: 2, scoreboardAway: 1))
        XCTAssertEqual(live.projected, 7)
    }
}
