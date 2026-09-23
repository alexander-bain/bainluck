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
/// The web's answer (`GamePlayCard.tsx`, #8206) is the vocabulary used here:
/// `~` on the carried half of the badge, the point's own time under it, and
/// `as of 7:41 PM` naming the OLDEST carried component on screen when any is a
/// minute or more older than the point. Reader copy names a time, never a
/// mechanism.
///
/// CODEX CORRECTIONS 2026-09-23 pinned below: period and clock age on their
/// OWN observation rows (a period-only row must not refresh a carried clock's
/// age, a clock-only row must not present a carried period as fresh); and the
/// ESPN lookup no longer lets a first observation in a LATER minute stand,
/// exact, on an earlier price — the test that blessed that case
/// (`testANewerRowIsNotStale`) is replaced by an enrichment regression.
///
/// NATIVE EXECUTION: NOT RUN by the author (no Xcode in the authoring
/// environment). Statically validated only; Native runs this file.
final class ScrubReadoutDatesCarriedState925Tests: XCTestCase {

    private func date(_ iso: String) -> Date { iso.asDate! }

    private func point(timestamp: String, period: String? = "4th Quarter", clock: String? = "1:09",
                       homeScore: Int? = 101, awayScore: Int? = 98,
                       periodAt: String? = nil, clockAt: String? = nil, scoreAt: String? = nil,
                       periodApprox: Bool = false, clockApprox: Bool = false, scoreApprox: Bool = false) -> GamePlayPoint {
        GamePlayPoint(
            timestamp: timestamp,
            homeProb: 0.62,
            awayProb: 0.38,
            homeScore: homeScore,
            awayScore: awayScore,
            period: period,
            clock: clock,
            periodObservedAt: periodAt.map { date($0) },
            clockObservedAt: clockAt.map { date($0) },
            scoreObservedAt: scoreAt.map { date($0) },
            periodApprox: periodApprox,
            clockApprox: clockApprox,
            scoreApprox: scoreApprox
        )
    }

    private func asOf(_ iso: String) -> String { "as of \(GamePlayPoint.clockText(date(iso)))" }

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

    /// A row inside the point's own minute is the same observation at the
    /// chart's resolution — not stale, and the only "newer than the point" a
    /// row may now be (`observationCutoff(for:)`).
    func testARowInThePointsOwnMinuteIsNotStale() {
        let seen = date("2026-06-15T20:41:30+00:00")
        XCTAssertFalse(OddsChartView.carriedStateIsApproximate(
            pointDate: date("2026-06-15T20:41:00+00:00"), observedAt: seen))
    }

    func testTheObservationCutoffIsTheStartOfTheNextMinute() {
        XCTAssertEqual(OddsChartView.observationCutoff(for: date("2026-06-15T20:41:00+00:00")),
                       date("2026-06-15T20:42:00+00:00"))
        XCTAssertEqual(OddsChartView.observationCutoff(for: date("2026-06-15T20:41:59+00:00")),
                       date("2026-06-15T20:42:00+00:00"))
    }

    /// Late first observation: no row yet means no state, not a doubtful one.
    func testNoObservationIsNotApproximate() {
        XCTAssertFalse(OddsChartView.carriedStateIsApproximate(
            pointDate: date("2026-06-15T20:30:00+00:00"), observedAt: nil))
    }

    // MARK: - The card's copy

    func testAnExactPointSaysNothingAboutAge() {
        let p = point(timestamp: "2026-06-15T20:41:00+00:00",
                      periodAt: "2026-06-15T20:41:00+00:00", clockAt: "2026-06-15T20:41:00+00:00")
        XCTAssertEqual(p.timeDisplay, "Q4 1:09")
        XCTAssertNil(p.stateAsOfDisplay)
        XCTAssertEqual(p.wallClockDisplay, GamePlayPoint.clockText(date("2026-06-15T20:41:00+00:00")))
        XCTAssertFalse(p.wallClockDisplay.isEmpty)
    }

    /// Both halves carried from the same row: the clock wears the mark, the
    /// period does not (one tilde per badge), and the line names the row.
    func testACarriedBadgeIsDated() {
        let p = point(timestamp: "2026-06-15T20:44:00+00:00",
                      periodAt: "2026-06-15T20:41:00+00:00", clockAt: "2026-06-15T20:41:00+00:00",
                      periodApprox: true, clockApprox: true)
        XCTAssertEqual(p.timeDisplay, "Q4 ~1:09")
        XCTAssertEqual(p.stateAsOfDisplay, asOf("2026-06-15T20:41:00+00:00"))
        XCTAssertEqual(p.wallClockDisplay, GamePlayPoint.clockText(date("2026-06-15T20:44:00+00:00")))
    }

    /// CODEX ARM 1 — a period-only observation at 20:03 must not erase the age
    /// of a clock last seen at 20:00. RED on the reviewed candidate (one shared
    /// date), GREEN now.
    func testAPeriodOnlyObservationDoesNotEraseTheCarriedClocksAge() {
        let p = point(timestamp: "2026-06-15T20:03:00+00:00", period: "1st Quarter", clock: "7:41",
                      periodAt: "2026-06-15T20:03:00+00:00", clockAt: "2026-06-15T20:00:00+00:00",
                      periodApprox: false, clockApprox: true)
        XCTAssertEqual(p.timeDisplay, "Q1 ~7:41")
        XCTAssertEqual(p.stateAsOfDisplay, asOf("2026-06-15T20:00:00+00:00"))
    }

    /// CODEX ARM 2 — a clock-only observation at 20:03 must not present a
    /// period last seen at 20:00 as freshly observed. The period is the stale
    /// half of a badge whose clock is fresh, so IT wears the mark.
    func testAClockOnlyObservationDoesNotPresentACarriedPeriodAsFresh() {
        let p = point(timestamp: "2026-06-15T20:03:00+00:00", period: "1st Quarter", clock: "4:41",
                      periodAt: "2026-06-15T20:00:00+00:00", clockAt: "2026-06-15T20:03:00+00:00",
                      periodApprox: true, clockApprox: false)
        XCTAssertEqual(p.timeDisplay, "~Q1 4:41")
        XCTAssertEqual(p.stateAsOfDisplay, asOf("2026-06-15T20:00:00+00:00"))
    }

    /// The line names the OLDEST carried component, whichever half that is.
    func testTheAgeLineNamesTheOldestCarriedHalf() {
        let p = point(timestamp: "2026-06-15T20:10:00+00:00", period: "1st Quarter", clock: "4:41",
                      periodAt: "2026-06-15T20:00:00+00:00", clockAt: "2026-06-15T20:07:00+00:00",
                      periodApprox: true, clockApprox: true)
        XCTAssertEqual(p.timeDisplay, "Q1 ~4:41", "one tilde: the clock carries it when both are carried")
        XCTAssertEqual(p.stateAsOfDisplay, asOf("2026-06-15T20:00:00+00:00"))
    }

    /// Baseball: no clock, the half-inning is the badge, and a carried one wears
    /// the mark — the top/bottom is preserved in the readout even though the
    /// chip strip collapses it to the whole inning (#3348).
    func testACarriedHalfInningWearsTheMarkAndKeepsItsHalf() {
        let p = point(timestamp: "2026-06-15T20:47:00+00:00", period: "Top 8th", clock: nil,
                      homeScore: 11, awayScore: 2,
                      periodAt: "2026-06-15T20:41:00+00:00", periodApprox: true)
        XCTAssertEqual(p.timeDisplay, "~Top 8th")
        XCTAssertEqual(p.stateAsOfDisplay, asOf("2026-06-15T20:41:00+00:00"))
    }

    /// A clock `liveStatusText` refuses to print (`0:00`, which ESPN sends
    /// between periods) cannot date or mark the badge: decided over what is
    /// RENDERED, not what the point carries.
    func testASuppressedClockCannotDateTheBadge() {
        let p = point(timestamp: "2026-06-15T20:47:00+00:00", period: "4th Quarter", clock: "0:00",
                      periodAt: "2026-06-15T20:47:00+00:00", clockAt: "2026-06-15T20:41:00+00:00",
                      periodApprox: false, clockApprox: true)
        XCTAssertEqual(p.timeDisplay, "Q4")
        XCTAssertNil(p.stateAsOfDisplay)
    }

    /// #4880 — soccer serves period == clock and the rule prints ONE token, the
    /// clock's. A carried one wears one mark and is dated once.
    func testSoccersSingleTokenIsMarkedOnce() {
        let s = point(timestamp: "2026-06-15T20:47:00+00:00", period: "25'", clock: "25'",
                      periodAt: "2026-06-15T20:41:00+00:00", clockAt: "2026-06-15T20:41:00+00:00",
                      periodApprox: true, clockApprox: true)
        XCTAssertEqual(s.timeDisplay, "~25'")
        XCTAssertEqual(s.stateAsOfDisplay, asOf("2026-06-15T20:41:00+00:00"))
    }

    /// #3273 — football's period detail carries its own clock prefix; the badge
    /// strips it and prints the clock once. Both halves are then on screen and
    /// each is judged on its own observation.
    func testFootballsPrefixedPeriodStillHasTwoHalvesToDate() {
        let p = point(timestamp: "2026-06-15T20:47:00+00:00", period: "9:44 - 2nd Quarter", clock: "9:44",
                      periodAt: "2026-06-15T20:47:00+00:00", clockAt: "2026-06-15T20:41:00+00:00",
                      periodApprox: false, clockApprox: true)
        XCTAssertEqual(p.timeDisplay, "Q2 ~9:44")
        XCTAssertEqual(p.stateAsOfDisplay, asOf("2026-06-15T20:41:00+00:00"))
    }

    func testACarriedScoreWithNoBadgeIsStillDated() {
        let p = point(timestamp: "2026-06-15T20:50:00+00:00", period: nil, clock: nil,
                      scoreAt: "2026-06-15T20:41:00+00:00", scoreApprox: true)
        XCTAssertEqual(p.timeDisplay, "")
        XCTAssertTrue(p.hasScore)
        XCTAssertEqual(p.stateAsOfDisplay, asOf("2026-06-15T20:41:00+00:00"))
    }

    /// With a badge on screen the score's age is not what is disclosed — the
    /// badge is what the line dates. (Same choice as the web: one line.)
    func testACarriedScoreUnderAFreshBadgeAddsNoLine() {
        let p = point(timestamp: "2026-06-15T20:50:00+00:00",
                      periodAt: "2026-06-15T20:50:00+00:00", clockAt: "2026-06-15T20:50:00+00:00",
                      scoreAt: "2026-06-15T20:41:00+00:00", scoreApprox: true)
        XCTAssertEqual(p.timeDisplay, "Q4 1:09")
        XCTAssertNil(p.stateAsOfDisplay)
    }

    /// Nothing to date: no score, no badge, no age line — and no `~` on an empty
    /// badge, which is the card's cue to draw nothing.
    func testAPointWithNoStatePrintsNoAge() {
        let p = point(timestamp: "2026-06-15T20:30:00+00:00", period: nil, clock: nil,
                      homeScore: nil, awayScore: nil)
        XCTAssertEqual(p.timeDisplay, "")
        XCTAssertNil(p.stateAsOfDisplay)
    }

    /// An approx flag without a date to name is not printable: the mark stays,
    /// the age line does not invent a time.
    func testApproxWithoutAnObservationDateHasNoAgeLine() {
        let p = point(timestamp: "2026-06-15T20:50:00+00:00", periodApprox: true, clockApprox: true)
        XCTAssertEqual(p.timeDisplay, "Q4 ~1:09")
        XCTAssertNil(p.stateAsOfDisplay)
    }

    /// The existing construction sites pass none of the new fields and must
    /// read as exact — the resting "last point" under a live chart is the
    /// latest row.
    func testDefaultsAreAnExactObservation() {
        let p = GamePlayPoint(timestamp: "2026-06-15T20:41:00+00:00", homeProb: 0.6, awayProb: 0.4,
                              homeScore: 1, awayScore: 0, period: "Bottom 7th", clock: nil)
        XCTAssertFalse(p.periodApprox)
        XCTAssertFalse(p.clockApprox)
        XCTAssertFalse(p.scoreApprox)
        XCTAssertNil(p.periodObservedAt)
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
        let seen = date("2026-06-15T20:41:00+00:00")
        XCTAssertEqual(out.map(\.periodObservedAt), [seen, seen, seen])
        XCTAssertEqual(out.map(\.clockObservedAt), [seen, seen, seen])
        XCTAssertEqual(out.map(\.scoreObservedAt), [seen, seen, seen])
        XCTAssertEqual(out.map(\.periodApprox), [false, true, true])
        XCTAssertEqual(out.map(\.clockApprox), [false, true, true])
        XCTAssertEqual(out.map(\.scoreApprox), [false, true, true])
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
        XCTAssertNil(out[0].periodObservedAt)
        XCTAssertFalse(out[0].periodApprox)
        XCTAssertNil(out[0].period)
        XCTAssertNil(out[1].period)
        XCTAssertEqual(out[2].period, "2nd Quarter")
        XCTAssertFalse(out[2].periodApprox)
    }

    /// CODEX 2026-09-23 — THE CASE THE CANDIDATE'S TEST BLESSED. The +90s
    /// look-ahead attached a first observation at 20:32:30 to the 20:31:00
    /// price, and the age rule then called it exact: a state nobody had seen
    /// yet, on a minute the reader can tell apart. RED on the candidate
    /// (`out[0].period == "2nd Quarter"`, `periodApprox == false`), GREEN now:
    /// the 20:31 price has no state, the 20:32 price (same minute as the row)
    /// reads it as its own observation, 20:33 carries it.
    func testALateFirstObservationIsNotAttachedExactToAnEarlierPrice() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:32:30+00:00", "home_probability": 0.6, "game_clock": "12:00",
          "period": "2nd Quarter", "home_score": 7, "away_score": 0}]
        """)
        let out = OddsChartView.enrichWithGameState(
            points(["2026-06-15T20:31:00+00:00", "2026-06-15T20:32:00+00:00", "2026-06-15T20:33:00+00:00"]),
            history: h)
        XCTAssertNil(out[0].period, "20:31 — nobody had seen Q2 yet")
        XCTAssertNil(out[0].clock)
        XCTAssertNil(out[0].homeScore)
        XCTAssertNil(out[0].periodObservedAt)
        XCTAssertFalse(out[0].periodApprox)
        XCTAssertEqual(out[1].period, "2nd Quarter", "20:32 — same minute as the row: its own observation")
        XCTAssertEqual(out[1].periodObservedAt, date("2026-06-15T20:32:30+00:00"))
        XCTAssertFalse(out[1].periodApprox)
        XCTAssertEqual(out[2].period, "2nd Quarter")
        XCTAssertFalse(out[2].periodApprox, "30s old: under the chart's one-minute resolution")
    }

    /// The same bound on a REFRESH: a clock observed at 20:03:20 does not reach
    /// the 20:02:00 price; that price keeps the 20:01:30 clock, dated by it.
    func testARowInALaterMinuteDoesNotRefreshAnEarlierPrice() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:01:30+00:00", "home_probability": 0.6, "game_clock": "5:00",
          "period": "2nd Quarter", "home_score": 7, "away_score": 0},
         {"timestamp": "2026-06-15T20:03:20+00:00", "home_probability": 0.6, "game_clock": "4:00",
          "period": "2nd Quarter", "home_score": 7, "away_score": 0}]
        """)
        let out = OddsChartView.enrichWithGameState(
            points(["2026-06-15T20:02:00+00:00", "2026-06-15T20:03:00+00:00"]), history: h)
        XCTAssertEqual(out[0].clock, "5:00")
        XCTAssertEqual(out[0].clockObservedAt, date("2026-06-15T20:01:30+00:00"))
        XCTAssertFalse(out[0].clockApprox, "30s old")
        XCTAssertEqual(out[1].clock, "4:00", "20:03:20 is inside the 20:03 minute")
        XCTAssertEqual(out[1].clockObservedAt, date("2026-06-15T20:03:20+00:00"))
    }

    /// MLB shape: a score row with `period: null` (most ESPN rows) does not
    /// refresh the age of the half-inning seen minutes earlier. The period is
    /// dated by its own row; the score by its own.
    func testAScoreOnlyRowDoesNotRefreshThePeriodsAge() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:49:00+00:00", "home_probability": 0.6,
          "period": "Top 8th", "home_score": 0, "away_score": 1},
         {"timestamp": "2026-06-15T20:52:00+00:00", "home_probability": 0.61, "home_score": 0, "away_score": 1}]
        """)
        let out = OddsChartView.enrichWithGameState(points(["2026-06-15T20:53:00+00:00"]), history: h)
        XCTAssertEqual(out[0].period, "Top 8th")
        XCTAssertEqual(out[0].homeScore, 0)
        XCTAssertEqual(out[0].periodObservedAt, date("2026-06-15T20:49:00+00:00"))
        XCTAssertTrue(out[0].periodApprox)
        XCTAssertEqual(out[0].scoreObservedAt, date("2026-06-15T20:52:00+00:00"))
        XCTAssertTrue(out[0].scoreApprox)
        XCTAssertNil(out[0].clockObservedAt)
    }

    /// CODEX ARM 1 through enrichment — a period-only row at 20:03 refreshes
    /// the period's date and leaves the clock's alone.
    func testAPeriodOnlyRowLeavesTheClocksAgeAlone() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:00:00+00:00", "home_probability": 0.6, "game_clock": "7:41", "period": "1st Quarter"},
         {"timestamp": "2026-06-15T20:03:00+00:00", "home_probability": 0.6, "period": "1st Quarter"}]
        """)
        let out = OddsChartView.enrichWithGameState(points(["2026-06-15T20:03:00+00:00"]), history: h)
        XCTAssertEqual(out[0].periodObservedAt, date("2026-06-15T20:03:00+00:00"))
        XCTAssertFalse(out[0].periodApprox)
        XCTAssertEqual(out[0].clock, "7:41")
        XCTAssertEqual(out[0].clockObservedAt, date("2026-06-15T20:00:00+00:00"))
        XCTAssertTrue(out[0].clockApprox)
    }

    /// CODEX ARM 2 through enrichment — a clock-only row at 20:03 refreshes
    /// the clock's date and leaves the period's alone.
    func testAClockOnlyRowLeavesThePeriodsAgeAlone() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:00:00+00:00", "home_probability": 0.6, "game_clock": "7:41", "period": "1st Quarter"},
         {"timestamp": "2026-06-15T20:03:00+00:00", "home_probability": 0.6, "game_clock": "4:41"}]
        """)
        let out = OddsChartView.enrichWithGameState(points(["2026-06-15T20:03:00+00:00"]), history: h)
        XCTAssertEqual(out[0].clock, "4:41")
        XCTAssertEqual(out[0].clockObservedAt, date("2026-06-15T20:03:00+00:00"))
        XCTAssertFalse(out[0].clockApprox)
        XCTAssertEqual(out[0].period, "1st Quarter")
        XCTAssertEqual(out[0].periodObservedAt, date("2026-06-15T20:00:00+00:00"))
        XCTAssertTrue(out[0].periodApprox)
    }

    /// And with no period ever seen, the score's own row dates the readout.
    func testWithNoBadgeTheScoreRowDatesTheReadout() throws {
        let h = try history(espnRows: """
        [{"timestamp": "2026-06-15T20:20:00+00:00", "home_probability": 0.5, "home_score": 0, "away_score": 0}]
        """)
        let out = OddsChartView.enrichWithGameState(
            points(["2026-06-15T20:20:00+00:00", "2026-06-15T20:25:00+00:00"]), history: h)
        XCTAssertNil(out[0].period)
        XCTAssertFalse(out[0].scoreApprox)
        XCTAssertEqual(out[1].scoreObservedAt, date("2026-06-15T20:20:00+00:00"))
        XCTAssertTrue(out[1].scoreApprox)
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
        XCTAssertEqual(out[0].clockObservedAt, date("2026-06-15T20:41:00+00:00"))
        XCTAssertEqual(out[0].periodObservedAt, date("2026-06-15T20:41:00+00:00"))
        XCTAssertTrue(out[0].clockApprox)
        XCTAssertTrue(out[0].periodApprox)
    }
}
