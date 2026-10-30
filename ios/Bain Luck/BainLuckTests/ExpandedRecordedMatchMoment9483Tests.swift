import XCTest
@testable import Bain_Luck

/// #9483 — the expanded reading of one inspected match-history moment
/// (`ExpandedRecordedMatchMoment9483`): both named chances, the score with its
/// own observation time, the game state and the play, from a point the owner
/// already resolved with `OddsChartView.playPoint`.
///
/// Two kinds of input, labelled at each test:
/// - REAL: Mets @ Rangers, 15318166, the retained production `/history` read
///   (`Fixtures/event-15318166-history-7878-contract.20260925.json`; its note
///   says `history` was emptied and `espn_history` dropped for size, so its game
///   state is `score_history` only — no period or clock). Decoded with the
///   app's own `EventHistoryResponse`, `chartPoints`, `enrichWithGameState` and
///   `playPoint`; no private parser and no invented values.
/// - CONSTRUCTED: fixed `GamePlayPoint` controls with fixed dates. They are not
///   real games. Expected dates come from the shared helpers
///   (`SourceAge.preciseStamp`, `GamePlayPoint.asOfText`), so no expectation
///   depends on the machine's time zone.
///
/// NATIVE EXECUTION: NOT RUN by the author (no compile or XCTest grant).
/// Syntax-parsed only.
@MainActor
final class ExpandedRecordedMatchMoment9483Tests: XCTestCase {

    private typealias Model = ExpandedRecordedMatchMoment9483

    /// 2026-10-04T20:15:00Z.
    private let t0 = Date(timeIntervalSince1970: 1_791_144_900)

    private func point(at date: Date? = nil, home: Double = 0.62, away: Double? = 0.38,
                       homeScore: Int? = nil, awayScore: Int? = nil,
                       period: String? = nil, clock: String? = nil,
                       scoringPlay: ScoringPlay? = nil,
                       periodAt: Date? = nil, clockAt: Date? = nil, scoreAt: Date? = nil,
                       periodApprox: Bool = false, clockApprox: Bool = false, scoreApprox: Bool = false,
                       phase: ChartReadoutPhase9483? = nil) -> GamePlayPoint {
        GamePlayPoint(
            timestamp: (date ?? t0).ISO8601Format(),
            homeProb: home, awayProb: away,
            homeScore: homeScore, awayScore: awayScore,
            period: period, clock: clock, scoringPlay: scoringPlay,
            periodObservedAt: periodAt, clockObservedAt: clockAt, scoreObservedAt: scoreAt,
            periodApprox: periodApprox, clockApprox: clockApprox, scoreApprox: scoreApprox,
            phase: phase)
    }

    private func content(_ point: GamePlayPoint?, finished: Bool = false) -> Model.Content? {
        Model.content(point: point, homeName: "Philadelphia Eagles", awayName: "Jacksonville Jaguars",
                      gameFinished: finished)
    }

    private func play(_ json: String) throws -> ScoringPlay {
        try JSONDecoder().decode(ScoringPlay.self, from: Data(json.utf8))
    }

    // MARK: - CONSTRUCTED: the resolved point, read as given

    func testTheResolvedPointsOwnSidesAndTime() throws {
        let p = point()
        let c = try XCTUnwrap(content(p))
        let printed = GamePlayCardView.printedLabels(home: 0.62, away: 0.38)
        XCTAssertEqual(c.home, Model.Side(name: "Philadelphia Eagles", chance: printed.home, score: nil))
        XCTAssertEqual(c.away, Model.Side(name: "Jacksonville Jaguars", chance: printed.away, score: nil))
        XCTAssertEqual(c.home.chance, "62%")
        XCTAssertEqual(c.away.chance, "38%")
        XCTAssertEqual(c.heading, "Recorded win chance")
        XCTAssertEqual(c.recordedLine, "Recorded \(try XCTUnwrap(SourceAge.preciseStamp(p.timestamp)))")

        let unparseable = GamePlayPoint(timestamp: "not a time", homeProb: 0.62, awayProb: 0.38)
        XCTAssertEqual(content(unparseable)?.recordedLine, "Time unknown")
        XCTAssertEqual(content(unparseable)?.stamp, nil)
    }

    /// Nil is "unavailable" — this view has no latest point or neighbour to reach for.
    func testANilMomentIsUnavailable() {
        XCTAssertNil(content(nil))
        XCTAssertEqual(Model.unavailableTitle, "Recorded moment unavailable")
    }

    /// A draw-priced point arrives with no away price: the away side says
    /// Unavailable by name; no complement is printed for it.
    func testAMissingAwayChanceStaysUnavailableForThatSide() throws {
        let c = try XCTUnwrap(content(point(home: 0.62, away: nil)))
        XCTAssertEqual(c.home.chance, GamePlayCardView.printedLabels(home: 0.62, away: nil).home)
        XCTAssertNil(c.away.chance)
        XCTAssertEqual(c.away.chanceText, "Unavailable")
        XCTAssertTrue(c.spoken.contains("Jacksonville Jaguars win chance unavailable"), c.spoken)
        XCTAssertFalse(c.spoken.contains("38%"), c.spoken)
        XCTAssertFalse(c.spoken.contains("0%"), c.spoken)
    }

    func testLiveExtremesKeepTheGuardAndAFinishedEndPrintsTheResult() throws {
        let live = try XCTUnwrap(content(point(home: 0.996, away: 0.004)))
        XCTAssertEqual(live.home.chance, ">99%")
        XCTAssertEqual(live.away.chance, "<1%")

        let liveEnd = try XCTUnwrap(content(point(home: 1.0, away: 0.0)))
        XCTAssertEqual(liveEnd.home.chance, GamePlayCardView.printedLabels(home: 1.0, away: 0.0).home)
        XCTAssertNotEqual(liveEnd.home.chance, "100%", "a live 1.0 keeps the guard")

        let finishedEnd = try XCTUnwrap(content(point(home: 1.0, away: 0.0), finished: true))
        XCTAssertEqual(finishedEnd.home.chance, "100%")
        XCTAssertEqual(finishedEnd.away.chance, "0%")
    }

    /// `gameFinished` decides only how a settled end prints. The heading reads
    /// the point's own phase: an earlier reading of a finished game is not Final.
    func testAFinishedGamesEarlierPointIsNotCalledFinal() throws {
        let earlier = try XCTUnwrap(content(point(home: 0.65, away: 0.35), finished: true))
        XCTAssertEqual(earlier.heading, "Recorded win chance")
        for word in ["Final", "Current", "Live"] {
            XCTAssertFalse(earlier.spoken.contains(word), earlier.spoken)
        }
        let end = try XCTUnwrap(content(point(home: 1.0, away: 0.0, phase: .final), finished: true))
        XCTAssertEqual(end.heading, "Final chart reading")
        XCTAssertEqual(end.badge, "Final")
        XCTAssertEqual(end.spoken.components(separatedBy: "Final").count - 1, 1,
                       "the badge does not repeat the heading's phase: \(end.spoken)")
    }

    /// A pregame point does not present the game facts carried onto it.
    func testPregameHidesCarriedScorePlayAndState() throws {
        let p = point(homeScore: 21, awayScore: 14, period: "4th Quarter", clock: "1:09",
                      scoringPlay: try play(#"{"type":"Touchdown","description":"Hurts 1 Yd Run"}"#),
                      clockAt: t0.addingTimeInterval(-600), scoreAt: t0.addingTimeInterval(-600),
                      clockApprox: true, scoreApprox: true, phase: .pregame)
        let c = try XCTUnwrap(content(p))
        XCTAssertEqual(c.heading, "Pregame win chance")
        XCTAssertEqual(c.badge, "Pregame")
        XCTAssertEqual(c.score, .hidden)
        XCTAssertNil(c.home.score)
        XCTAssertNil(c.away.score)
        XCTAssertNil(c.play)
        XCTAssertNil(c.stateAsOf)
        XCTAssertNotNil(p.stateAsOfDisplay, "precondition: the point does carry a dated state")
        for hidden in ["Score", "Touchdown", "Hurts", "as of"] {
            XCTAssertFalse(c.spoken.contains(hidden), "\(hidden) in \(c.spoken)")
        }
    }

    /// A genuine 0–0 is drawn; a half pair is never filled with 0.
    func testARealZeroScoreIsDrawnAndAPartialPairIsUnavailable() throws {
        let zero = try XCTUnwrap(content(point(homeScore: 0, awayScore: 0)))
        XCTAssertEqual(zero.home.score, 0)
        XCTAssertEqual(zero.away.score, 0)
        XCTAssertEqual(zero.score, .pair(note: nil))
        XCTAssertTrue(zero.spoken.contains("Score: Philadelphia Eagles 0, Jacksonville Jaguars 0"), zero.spoken)

        let partial = try XCTUnwrap(content(point(homeScore: 2, awayScore: nil)))
        XCTAssertEqual(partial.score, .unavailable)
        XCTAssertNil(partial.home.score)
        XCTAssertNil(partial.away.score)
        XCTAssertTrue(partial.spoken.contains("Score unavailable"), partial.spoken)
    }

    /// The score, period and clock were each observed at their own time. The
    /// score is dated by its own observation, here before local midnight, even
    /// though the badge's `as of` names a NEWER period time after it.
    func testScorePeriodAndClockKeepTheirOwnDatesAcrossMidnight() throws {
        let midnight = Calendar.current.startOfDay(for: t0.addingTimeInterval(86_400))
        let at = midnight.addingTimeInterval(1_800)
        let scoreAt = midnight.addingTimeInterval(-120)
        let p = point(at: at, homeScore: 101, awayScore: 98, period: "4th Quarter", clock: "1:09",
                      periodAt: midnight.addingTimeInterval(600),
                      clockAt: midnight.addingTimeInterval(1_680), scoreAt: scoreAt,
                      periodApprox: true, clockApprox: true, scoreApprox: true)
        let c = try XCTUnwrap(content(p))
        let scoreTime = GamePlayPoint.asOfText(scoreAt, pointDate: at)
        XCTAssertNotEqual(scoreTime, GamePlayPoint.clockText(scoreAt), "the score's time names its day")
        XCTAssertEqual(c.score, .pair(note: "Score from an earlier update, as of \(scoreTime)"))
        XCTAssertEqual(c.badge, p.badgeDisplay)
        XCTAssertEqual(c.stateAsOf, p.stateAsOfDisplay)
        let stateAsOf = try XCTUnwrap(c.stateAsOf)
        XCTAssertFalse(stateAsOf.contains(scoreTime), "the badge's as-of is the period's, not the score's")
        XCTAssertFalse(scoreTime.contains(GamePlayPoint.clockText(at)),
                       "the probability's time is never lent to the score")
    }

    func testACarriedScoreWithNoDateSaysTimeUnknown() throws {
        let undated = try XCTUnwrap(content(point(homeScore: 3, awayScore: 1, scoreApprox: true)))
        XCTAssertEqual(undated.score, .pair(note: "Score from an earlier update, time unknown"))

        let seenAt = t0.addingTimeInterval(-20)
        let exact = try XCTUnwrap(content(point(homeScore: 3, awayScore: 1, scoreAt: seenAt)))
        XCTAssertEqual(exact.score,
                       .pair(note: "Score as of \(GamePlayPoint.asOfText(seenAt, pointDate: t0))"))

        let exactUndated = try XCTUnwrap(content(point(homeScore: 3, awayScore: 1)))
        XCTAssertEqual(exactUndated.score, .pair(note: nil))
    }

    /// A scoring play reads in full beside the chances; it never takes their place.
    func testAPlayKeepsBothChances() throws {
        let td = try play(#"{"type":"Touchdown","description":"Hurts 1 Yd Run","shortText":"Hurts TD"}"#)
        let c = try XCTUnwrap(content(point(homeScore: 7, awayScore: 0, scoringPlay: td)))
        XCTAssertEqual(c.play, Model.Play(type: "Touchdown", text: "Hurts 1 Yd Run"))
        XCTAssertEqual(c.home.chance, "62%")
        XCTAssertEqual(c.away.chance, "38%")

        let short = try play(#"{"type":"Field Goal","shortText":"Elliott 44 Yd FG"}"#)
        XCTAssertEqual(Model.play(short), Model.Play(type: "Field Goal", text: "Elliott 44 Yd FG"))
        XCTAssertNil(Model.play(try play(#"{"type":"","description":""}"#)), "no invented prose")
    }

    func testTheSpokenSummary() throws {
        let scoreAt = t0.addingTimeInterval(-180)
        let p = point(homeScore: 101, awayScore: 98, period: "4th Quarter", clock: "1:09",
                      scoringPlay: try play(#"{"type":"Touchdown","description":"Hurts 1 Yd Run"}"#),
                      clockAt: scoreAt, scoreAt: scoreAt, clockApprox: true, scoreApprox: true)
        let c = try XCTUnwrap(content(p))
        let stamp = try XCTUnwrap(SourceAge.preciseStamp(p.timestamp))
        let asOf = try XCTUnwrap(p.stateAsOfDisplay)
        XCTAssertEqual(c.spoken, [
            "Recorded win chance, \(stamp)",
            "Philadelphia Eagles 62%",
            "Jacksonville Jaguars 38%",
            "Score: Philadelphia Eagles 101, Jacksonville Jaguars 98",
            "Score from an earlier update, as of \(GamePlayPoint.asOfText(scoreAt, pointDate: t0))",
            "Game state: \(p.badgeDisplay), \(asOf)",
            "Play: Touchdown, Hurts 1 Yd Run",
        ].joined(separator: ". "))
    }

    // MARK: - REAL: Mets @ Rangers, 15318166

    private static func specimen() throws -> EventHistoryResponse {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("event-15318166-history-7878-contract.20260925.json")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(contentsOf: url))
    }

    /// The blend's reading at `iso`, resolved exactly as the chart resolves it.
    private func realMoment(_ iso: String) throws -> GamePlayPoint {
        let history = try Self.specimen()
        let points = OddsChartView.enrichWithGameState(OddsChartView.chartPoints(from: history),
                                                       history: history)
            .filter { $0.source == "aggregate" }
        let context = ChartReadoutContext9483.chart(
            playStart: try XCTUnwrap("2026-09-24T18:35:00+00:00".asDate), gameFinished: true,
            readoutPoints: points, checkpoints: nil)
        let at = try XCTUnwrap(iso.asDate)
        let chartPoint = try XCTUnwrap(points.first { $0.date == at })
        return OddsChartView.playPoint(for: chartPoint, sportKey: "baseball_mlb", context: context)
    }

    private func realContent(_ point: GamePlayPoint) -> Model.Content? {
        Model.content(point: point, homeName: "Texas Rangers", awayName: "New York Mets",
                      gameFinished: true)
    }

    /// 19:00Z, 0.65. The 2–1 score was last seen at 18:55:04, so it is carried
    /// and dated by that row; the game is finished, the point is not Final.
    func testRealInPlayPointCarriesItsOwnScoreDate() throws {
        let p = try realMoment("2026-09-24T19:00:00+00:00")
        let c = try XCTUnwrap(realContent(p))
        XCTAssertEqual(c.heading, "Recorded win chance")
        XCTAssertEqual(c.home.chance, "65%")
        XCTAssertEqual(c.away.chance, "35%")
        XCTAssertEqual(c.home.chance, GamePlayCardView.printedLabels(home: p.homeProb, away: p.awayProb,
                                                                     gameFinished: true).home)
        XCTAssertEqual(c.home.score, 2)
        XCTAssertEqual(c.away.score, 1)
        XCTAssertTrue(p.scoreApprox)
        let seen = try XCTUnwrap(p.scoreObservedAt)
        let scoreTime = GamePlayPoint.asOfText(seen, pointDate: p.timestamp.asDate)
        XCTAssertEqual(c.score, .pair(note: "Score from an earlier update, as of \(scoreTime)"))
        // No period or clock in this capture: the badge is empty, and the point's
        // own `as of` (which then dates the score) is the score note's time.
        XCTAssertNil(c.badge)
        XCTAssertNil(c.stateAsOf)
        XCTAssertEqual(p.stateAsOfDisplay, "as of \(scoreTime)")
    }

    /// 18:20Z, before first pitch: Pregame, both sides' prices, no score.
    func testRealPregamePoint() throws {
        let p = try realMoment("2026-09-24T18:20:00+00:00")
        let c = try XCTUnwrap(realContent(p))
        XCTAssertEqual(p.phase, .pregame)
        XCTAssertEqual(c.heading, "Pregame win chance")
        XCTAssertEqual(c.badge, "Pregame")
        XCTAssertEqual(c.home.chance, "55%")
        XCTAssertEqual(c.away.chance, "45%")
        XCTAssertEqual(c.score, .hidden)
    }
}
