import XCTest
@testable import Bain_Luck

/// #9708 — rage shake #164, Red Sox @ Yankees AL Wild Card game 1 (15319563),
/// live: "Projected total runs · PRE-GAME 6 · PACE 0 · 0 scored" and "Pace
/// projects −6.0 vs pre-game expectation", under a header reading BOS 0 – NYY 1.
///
/// Two ways the served pace says something false, both withheld by
/// ``LivePaceStanding``:
///
/// 1. scoreless — `projected_total = total_scored / fraction_elapsed` is 0 at
///    every fraction before anyone scores (web #6831);
/// 2. an older score — the pace rides `/game-markets`, the header rides the live
///    event; a pace at 0 scored beneath a 1–0 header is a projection from a game
///    state the page no longer shows.
///
/// The views are SwiftUI and not rasterised; the rule is asserted, and the two
/// views that draw a live pace are pinned to it.
final class ALivePaceAgreesWithTheHeader9708Tests: XCTestCase {

    private func pace(scored: Int?, projected: Double?, elapsed: Double? = 0.44) -> GameMarketPace {
        GameMarketPace(totalScored: scored, projectedTotal: projected,
                       fractionElapsed: elapsed, timeRemainingDisplay: nil)
    }

    // MARK: - The photographed frame

    /// The card's pace (0 scored, pace 0) under the header's 1–0.
    func testThePhotographedPaceUnderAOneNilHeaderProjectsNothing() {
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 0, projected: 0),
                                                 scoreboardHome: 1, scoreboardAway: 0))
    }

    /// The same stale body, even had it scored: a pace at 1 under a 2–1
    /// header is still an older game state. This is the arm the scoreless rule
    /// alone would miss.
    func testAPaceFromAnOlderNonZeroScoreProjectsNothing() {
        let older = pace(scored: 1, projected: 2)
        XCTAssertFalse(LivePaceStanding.agrees(older, scoreboardHome: 2, scoreboardAway: 1))
        XCTAssertNil(LivePaceStanding.projection(older, scoreboardHome: 2, scoreboardAway: 1))
    }

    /// Web #6831's arm: a scoreless game whose header agrees (0–0) still has no
    /// projection — `0` is not `nil`.
    func testAScorelessPaceProjectsNothingEvenWhenTheHeaderAgrees() {
        let scoreless = pace(scored: 0, projected: 0)
        XCTAssertTrue(LivePaceStanding.agrees(scoreless, scoreboardHome: 0, scoreboardAway: 0))
        XCTAssertNil(LivePaceStanding.projection(scoreless, scoreboardHome: 0, scoreboardAway: 0))
    }

    // MARK: - Controls: what still draws

    /// What `_estimate_game_pace` would have served at 1–0 in the top of the
    /// 5th (24 of 54 model minutes): 1 scored, pace 2. Kills the
    /// "withhold every live pace" mutant.
    func testCONTROLAPaceAtTheHeadersScoreProjects() throws {
        let live = try XCTUnwrap(LivePaceStanding.projection(pace(scored: 1, projected: 2),
                                                             scoreboardHome: 1, scoreboardAway: 0))
        XCTAssertEqual(live.scored, 1)
        XCTAssertEqual(live.projected, 2)
    }

    /// With no scoreboard on the page there is nothing to contradict; the pace
    /// stands on its own score (the pre-#9708 behaviour, minus the scoreless 0).
    func testCONTROLNoScoreboardLeavesAScoredPaceStanding() throws {
        let live = try XCTUnwrap(LivePaceStanding.projection(pace(scored: 3, projected: 7),
                                                             scoreboardHome: nil, scoreboardAway: nil))
        XCTAssertEqual(live.projected, 7)
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 0, projected: 0),
                                                 scoreboardHome: nil, scoreboardAway: 0))
    }

    func testAnIncompletePaceProjectsNothing() {
        XCTAssertNil(LivePaceStanding.projection(nil, scoreboardHome: 1, scoreboardAway: 0))
        XCTAssertNil(LivePaceStanding.projection(pace(scored: 1, projected: nil),
                                                 scoreboardHome: 1, scoreboardAway: 0))
        XCTAssertNil(LivePaceStanding.projection(pace(scored: nil, projected: 2),
                                                 scoreboardHome: nil, scoreboardAway: nil))
    }

    // MARK: - The wiring: every view that draws a live pace asks the rule

    private func code(_ component: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("\(component).swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// The spectrum strip: the live tense and the strip's numbers both come
    /// from the rule, and the page's scoreboard is what it is asked against.
    func testTheSpectrumStripDrawsOnlyAStandingPace() throws {
        let src = try code("TotalPointsSpectrumView")
        XCTAssertTrue(src.contains(
            "LivePaceStanding.projection(gameMarkets.pace,scoreboardHome:homeScore,scoreboardAway:awayScore)"))
        XCTAssertTrue(src.contains("ifisLive,countsTheUnit,liveProjection!=nil{return.live}"),
                      "the live tense is back on a presence-only pace guard")
        XCTAssertTrue(src.contains("ifletlive=liveProjection{liveStrip(pregameTotal:pregame,paceTotal:live.projected,scored:live.scored)"))
        XCTAssertFalse(src.contains("pace.projectedTotal"),
                       "the spectrum reads the served pace around the #9708 rule again")
    }

    /// The totals map: the ACTUAL + PROJECTED pair and the empty-chrome
    /// predicate share one reading.
    func testTheTotalsMapDrawsOnlyAStandingPace() throws {
        let src = try code("MarketMapView")
        XCTAssertTrue(src.contains(
            "LivePaceStanding.projection(scoredPace,scoreboardHome:homeScore,scoreboardAway:awayScore)"))
        XCTAssertTrue(src.contains("hasProjectedTotal:scoreboardIsComparable&&liveProjection!=nil"))
        XCTAssertTrue(src.contains("letproj=liveProjection?.projected{"))
        XCTAssertFalse(src.contains("pace.projectedTotal"),
                       "the map reads the served pace around the #9708 rule again")
        XCTAssertFalse(src.contains("scoredPace?.projectedTotal"))
    }
}
