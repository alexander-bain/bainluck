import Foundation
import XCTest
@testable import Bain_Luck

/// #925 — the scrub readout shows score, period/clock AND the wall-clock time,
/// and a state carried forward from an older row says so.
///
/// Before this ship `GamePlayCardView` printed the badge (`Q4 1:09`) and the
/// score, and nothing else: no time of day at all, and `enrichWithGameState`
/// forward-filled score/period/clock across every point after a row with no
/// record of where they came from. A reader scrubbing the 7:44 PM price saw
/// `Q4 1:09` — the game clock last seen at 7:41 — presented as if observed
/// there. The assignment's clause: "carry-forward state must disclose its
/// age/uncertainty, rather than pretending an old game clock was observed at a
/// new price timestamp."
///
/// The web's answer (`GamePlayCard.tsx`, same ship) is the vocabulary used here:
/// `~` on the badge, the point's own time under it, and `as of 7:41 PM` when the
/// state is a minute or more older than the point. Reader copy names a time,
/// never a mechanism.
///
/// NATIVE EXECUTION: NOT RUN by the author (no Xcode in the authoring
/// environment). Statically validated only; Native runs this file.
final class ScrubReadoutDatesCarriedState925Tests: XCTestCase {

    private func date(_ iso: String) -> Date { iso.asDate! }

    private func point(timestamp: String, period: String? = "4th Quarter", clock: String? = "1:09",
                       homeScore: Int? = 101, awayScore: Int? = 98,
                       observedAt: String? = nil, approx: Bool = false) -> GamePlayPoint {
        GamePlayPoint(
            timestamp: timestamp,
            homeProb: 0.62,
            awayProb: 0.38,
            homeScore: homeScore,
            awayScore: awayScore,
            period: period,
            clock: clock,
            stateObservedAt: observedAt.map { date($0) },
            stateApprox: approx
        )
    }

    // MARK: - The rule

    func testAnObservationAMinuteOrOlderIsCarried() {
        let seen = date("2026-06-15T20:41:00+00:00")
        XCTAssertFalse(OddsChartView.carriedStateIsApproximate(pointDate: seen, observedAt: seen))
        XCTAssertFalse(OddsChartView.carriedStateIsApproximate(
            pointDate: seen.addingTimeInterval(59), observedAt: seen))
        XCTAssertTrue(OddsChartView.carriedStateIsApproximate(
            pointDate: seen.addingTimeInterval(60), observedAt: seen))
        XCTAssertTrue(OddsChartView.carriedStateIsApproximate(
            pointDate: seen.addingTimeInterval(40 * 60), observedAt: seen))
    }

    /// The 90-second look-ahead in `enrichWithGameState` can match a row NEWER
    /// than the point. That is not stale.
    func testANewerRowIsNotStale() {
        let seen = date("2026-06-15T20:41:00+00:00")
        XCTAssertFalse(OddsChartView.carriedStateIsApproximate(
            pointDate: seen.addingTimeInterval(-30), observedAt: seen))
    }

    /// Late first observation: no row yet means no state, not a doubtful one.
    func testNoObservationIsNotApproximate() {
        XCTAssertFalse(OddsChartView.carriedStateIsApproximate(
            pointDate: date("2026-06-15T20:30:00+00:00"), observedAt: nil))
    }

    // MARK: - The card's copy

    func testAnExactPointSaysNothingAboutAge() {
        let p = point(timestamp: "2026-06-15T20:41:00+00:00", observedAt: "2026-06-15T20:41:00+00:00")
        XCTAssertEqual(p.timeDisplay, "Q4 1:09")
        XCTAssertNil(p.stateAsOfDisplay)
        XCTAssertEqual(p.wallClockDisplay, GamePlayPoint.clockText(date("2026-06-15T20:41:00+00:00")))
        XCTAssertFalse(p.wallClockDisplay.isEmpty)
    }

    func testACarriedClockIsDated() {
        let p = point(timestamp: "2026-06-15T20:44:00+00:00",
                      observedAt: "2026-06-15T20:41:00+00:00", approx: true)
        XCTAssertEqual(p.timeDisplay, "~Q4 1:09")
        XCTAssertEqual(p.stateAsOfDisplay, "as of \(GamePlayPoint.clockText(date("2026-06-15T20:41:00+00:00")))")
        XCTAssertEqual(p.wallClockDisplay, GamePlayPoint.clockText(date("2026-06-15T20:44:00+00:00")))
    }

    /// Baseball: no clock, the half-inning is the badge, and a carried one wears
    /// the same mark — the top/bottom is preserved in the readout even though the
    /// chip strip collapses it to the whole inning (#3348).
    func testACarriedHalfInningWearsTheMarkAndKeepsItsHalf() {
        let p = point(timestamp: "2026-06-15T20:47:00+00:00", period: "Top 8th", clock: nil,
                      homeScore: 11, awayScore: 2,
                      observedAt: "2026-06-15T20:41:00+00:00", approx: true)
        XCTAssertEqual(p.timeDisplay, "~Top 8th")
        XCTAssertNotNil(p.stateAsOfDisplay)
    }

    func testACarriedScoreWithNoBadgeIsStillDated() {
        let p = point(timestamp: "2026-06-15T20:50:00+00:00", period: nil, clock: nil,
                      observedAt: "2026-06-15T20:41:00+00:00", approx: true)
        XCTAssertEqual(p.timeDisplay, "")
        XCTAssertTrue(p.hasScore)
        XCTAssertNotNil(p.stateAsOfDisplay)
    }

    /// Nothing to date: no score, no badge, no age line — and no `~` on an empty
    /// badge, which is the card's cue to draw nothing.
    func testAPointWithNoStatePrintsNoAge() {
        let p = point(timestamp: "2026-06-15T20:30:00+00:00", period: nil, clock: nil,
                      homeScore: nil, awayScore: nil, observedAt: nil, approx: false)
        XCTAssertEqual(p.timeDisplay, "")
        XCTAssertNil(p.stateAsOfDisplay)
    }

    /// `stateApprox` without a date to name is not printable: the mark stays,
    /// the age line does not invent a time.
    func testApproxWithoutAnObservationDateHasNoAgeLine() {
        let p = point(timestamp: "2026-06-15T20:50:00+00:00", observedAt: nil, approx: true)
        XCTAssertEqual(p.timeDisplay, "~Q4 1:09")
        XCTAssertNil(p.stateAsOfDisplay)
    }

    /// The existing construction sites pass neither new field and must read as
    /// exact — the resting "last point" under a live chart is the latest row.
    func testDefaultsAreAnExactObservation() {
        let p = GamePlayPoint(timestamp: "2026-06-15T20:41:00+00:00", homeProb: 0.6, awayProb: 0.4,
                              homeScore: 1, awayScore: 0, period: "Bottom 7th", clock: nil)
        XCTAssertFalse(p.stateApprox)
        XCTAssertNil(p.stateObservedAt)
        XCTAssertEqual(p.timeDisplay, "Bottom 7th")
        XCTAssertNil(p.stateAsOfDisplay)
    }

    func testAnUnparseableTimestampDrawsNoWallClock() {
        let p = point(timestamp: "")
        XCTAssertEqual(p.wallClockDisplay, "")
    }

    // MARK: - The enrichment on a real-shaped history

    private func history(espnRows: String) throws -> EventHistoryResponse {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventHistoryResponse.self, from: Data("""
        {"event_id": 1, "home_team": "Home", "away_team": "Away", "status": "completed",
         "history": [], "espn_history": \(espnRows)}
        """.utf8))
    }

    private func points(_ isos: [String]) -> [ChartDataPoint] {
        isos.map { ChartDataPoint(date: date($0), probability: 0.5, source: "kalshi") }
    }

    /// Stale carried state: one ESPN row at 20:41, prices every minute after it.
    /// The 20:41 point is exact; 20:42 and 20:44 carry the row and are dated by it.
    func testEnrichmentDatesTheCarriedRow() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:41:00+00:00", "home_probability": 0.6, "game_clock": "1:09",
          "period": "4th Quarter", "home_score": 101, "away_score": 98}]
        """)
        let out = OddsChartView.enrichWithGameState(
            points(["2026-06-15T20:41:00+00:00", "2026-06-15T20:42:00+00:00", "2026-06-15T20:44:00+00:00"]),
            history: h)
        XCTAssertEqual(out.map(\.clock), ["1:09", "1:09", "1:09"])
        XCTAssertEqual(out.map(\.homeScore), [101, 101, 101])
        XCTAssertEqual(out.map(\.stateObservedAt), Array(repeating: Optional(date("2026-06-15T20:41:00+00:00")), count: 3))
        XCTAssertEqual(out.map(\.stateApprox), [false, true, true])
    }

    /// Late first observation: the price points before the first ESPN row have
    /// no state and are not marked approximate.
    func testEnrichmentLeavesTheMinutesBeforeTheFirstRowUndated() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:32:00+00:00", "home_probability": 0.6,
          "period": "2nd Quarter", "home_score": 7, "away_score": 0}]
        """)
        let out = OddsChartView.enrichWithGameState(
            points(["2026-06-15T20:30:00+00:00", "2026-06-15T20:31:00+00:00", "2026-06-15T20:32:00+00:00"]),
            history: h)
        XCTAssertNil(out[0].stateObservedAt)
        XCTAssertFalse(out[0].stateApprox)
        XCTAssertNil(out[0].period)
        XCTAssertEqual(out[2].period, "2nd Quarter")
        XCTAssertFalse(out[2].stateApprox)
    }

    /// MLB shape: a score row with `period: null` (most ESPN rows) does not
    /// refresh the age of the half-inning seen minutes earlier. The badge is
    /// dated by its own row.
    func testAScoreOnlyRowDoesNotRefreshThePeriodsAge() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:49:00+00:00", "home_probability": 0.6,
          "period": "Top 8th", "home_score": 0, "away_score": 1},
         {"timestamp": "2026-06-15T20:52:00+00:00", "home_probability": 0.61, "home_score": 0, "away_score": 1}]
        """)
        let out = OddsChartView.enrichWithGameState(points(["2026-06-15T20:53:00+00:00"]), history: h)
        XCTAssertEqual(out[0].period, "Top 8th")
        XCTAssertEqual(out[0].homeScore, 0)
        XCTAssertEqual(out[0].stateObservedAt, date("2026-06-15T20:49:00+00:00"))
        XCTAssertTrue(out[0].stateApprox)
    }

    /// And with no period ever seen, the score's own row dates the readout.
    func testWithNoBadgeTheScoreRowDatesTheReadout() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:20:00+00:00", "home_probability": 0.5, "home_score": 0, "away_score": 0}]
        """)
        let out = OddsChartView.enrichWithGameState(
            points(["2026-06-15T20:20:00+00:00", "2026-06-15T20:25:00+00:00"]), history: h)
        XCTAssertNil(out[0].period)
        XCTAssertFalse(out[0].stateApprox)
        XCTAssertEqual(out[1].stateObservedAt, date("2026-06-15T20:20:00+00:00"))
        XCTAssertTrue(out[1].stateApprox)
    }

    /// A row that carries a probability and no state is not an observation of
    /// state, so it does not refresh the date on what is being carried.
    func testAStatelessRowDoesNotRefreshTheDate() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:41:00+00:00", "home_probability": 0.6, "game_clock": "1:09",
          "period": "4th Quarter", "home_score": 101, "away_score": 98},
         {"timestamp": "2026-06-15T20:45:00+00:00", "home_probability": 0.61}]
        """)
        let out = OddsChartView.enrichWithGameState(points(["2026-06-15T20:46:00+00:00"]), history: h)
        XCTAssertEqual(out[0].clock, "1:09")
        XCTAssertEqual(out[0].stateObservedAt, date("2026-06-15T20:41:00+00:00"))
        XCTAssertTrue(out[0].stateApprox)
    }
}
