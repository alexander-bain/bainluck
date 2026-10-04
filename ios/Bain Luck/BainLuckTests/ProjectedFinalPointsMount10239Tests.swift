import XCTest
@testable import Bain_Luck

/// #10239 / #10478 — the page's admission for the projected final-points
/// module, decoded from a served `/history` shape (twin of web
/// `projectedFinalPointsMount`). Rows count by the #10461 provenance contract:
/// `kind: "recorded"` plus `observed_at`, our original capture with its offset.
@MainActor
final class ProjectedFinalPointsMount10239Tests: XCTestCase {
    private static let observedQ1 = #"{"period":"1st Quarter","source":"espn_state","precision":"first_seen","not_before":"2026-09-14T00:20:00Z"}"#
    private static let estimatedQ1 = #"{"period":"1st Quarter","source":"estimated","precision":"first_seen","not_before":"2026-09-14T00:20:00Z"}"#
    /// A pregame 0–0 BEFORE the observed floor, then two real scores.
    private static let scores = """
    [{"timestamp":"2026-09-14T00:10:00+00:00","home_score":0,"away_score":0},
     {"timestamp":"2026-09-14T00:50:00+00:00","home_score":7,"away_score":0},
     {"timestamp":"2026-09-14T02:00:00+00:00","home_score":14,"away_score":3}]
    """

    // MARK: - Fixture

    /// One served row. `kind` / `observed` are RAW JSON fragments so a test can
    /// serve a mistyped or null value; nil omits the key.
    private func row(_ minute: String, _ home: Double, _ away: Double, prob: Double = 0.8,
                     kind: String? = nil, observed: String? = nil) -> String {
        var fields = [#""timestamp":"2026-09-14T\#(minute):00+00:00""#, #""home_probability":\#(prob)"#,
                      #""projected_home_score":\#(home)"#, #""projected_away_score":\#(away)"#]
        if let kind { fields.append(#""kind":\#(kind)"#) }
        if let observed { fields.append(#""observed_at":\#(observed)"#) }
        return "{" + fields.joined(separator: ",") + "}"
    }

    /// A row as the producer serves a genuine capture: 30.123456 s into its
    /// displayed minute, in Python's `isoformat()` shape.
    private func rec(_ minute: String, _ home: Double, _ away: Double) -> String {
        row(minute, home, away, kind: #""recorded""#, observed: #""2026-09-14T\#(minute):30.123456+00:00""#)
    }

    /// The instant a `rec` row is placed at (whole milliseconds, as parsed).
    private func capture(_ minute: String) -> Date {
        "2026-09-14T\(minute):30.123+00:00".asDate!
    }

    private func books(_ byKey: [String: [String]]) -> String {
        let entries = byKey.keys.sorted().map { key -> String in
            let rows = byKey[key]!.joined(separator: ",")
            return "\"\(key)\":[\(rows)]"
        }
        return "{" + entries.joined(separator: ",") + "}"
    }

    /// `status` / `completedAt` are raw JSON (`"null"` serves null).
    private func history(status: String = #""completed""#, completedAt: String = #""2026-09-14T03:30:00Z""#,
                         books: String, scores: String = Self.scores,
                         markers: [String] = [Self.observedQ1]) throws -> EventHistoryResponse {
        let json = """
        {"event_id":14780549,"home_team":"Home","away_team":"Away","status":\(status),
         "completed_at":\(completedAt),"history":[],
         "bookmaker_history":\(books),
         "score_history":\(scores),
         "period_markers":[\(markers.joined(separator: ","))]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func mount(_ h: EventHistoryResponse?, page: String = "completed", sport: String = "americanfootball_nfl",
                       now: Date? = nil) -> ProjectedFinalPointsSeries.Input? {
        ProjectedFinalPointsMount.input(sportKey: sport, eventStatus: page, history: h,
                                        finalHome: 27, finalAway: 7, asOf: now)
    }

    /// The pre-contract finished fixture: draftkings unmarked, plus an unnamed
    /// book with more pairs that must never win.
    private func legacyFinished(firstRowKind: String? = nil, historyStatus: String = #""completed""#,
                                markers: [String] = [Self.observedQ1]) throws -> EventHistoryResponse {
        try history(status: historyStatus, books: books([
            "draftkings": [row("00:10", 27, 7.5, kind: firstRowKind), row("01:00", 28, 8, prob: 0.85)],
            "unknownbook": [row("00:10", 30, 3), row("00:20", 30, 3), row("00:30", 30, 3)],
        ]), scores: #"[{"timestamp":"2026-09-14T01:30:00Z","home_score":7,"away_score":0},{"timestamp":"2026-09-14T03:20:00Z","home_score":26,"away_score":7}]"#,
            markers: markers)
    }

    private let live = #""live""#
    private let scheduled = #""scheduled""#

    // MARK: - Provenance

    func testARecordedRowIsPlacedAtItsOriginalCaptureNotItsDisplayedMinute() throws {
        let h = try history(books: books(["draftkings": [rec("00:10", 27, 7.5), rec("01:00", 28, 8)]]))
        let input = try XCTUnwrap(mount(h))
        XCTAssertEqual(input.pairs.map(\.kind), [.recorded, .recorded])
        XCTAssertEqual(input.pairs.map(\.at), [capture("00:10"), capture("01:00")])
    }

    func testEveryMalformedProvenanceRefusesEvenWhereUnmarkedRowsWouldPass() throws {
        // A finished page over a finished history admits UNMARKED rows, so each
        // refusal below is the provenance itself, not the phase.
        let valid = #""2026-09-14T00:10:30+00:00""#
        let cases: [(String, String?, String?)] = [
            ("synthetic", #""synthetic""#, valid),
            ("unknown kind", #""estimated""#, valid),
            ("mistyped kind", "7", valid),
            ("null kind", "null", valid),
            ("observed_at alone", nil, valid),
            ("recorded without observed_at", #""recorded""#, nil),
            ("null observed_at", #""recorded""#, "null"),
            ("mistyped observed_at", #""recorded""#, "1789"),
            ("offset-less local time", #""recorded""#, #""2026-09-14T00:10:30""#),
            // ISO8601DateFormatter reads this onto the right minute; the strict parse does not.
            ("colon-less offset", #""recorded""#, #""2026-09-14T00:10:30+0000""#),
            ("bare date", #""recorded""#, #""2026-09-14""#),
            ("impossible day", #""recorded""#, #""2026-02-30T00:10:30+00:00""#),
            ("another minute's capture", #""recorded""#, #""2026-09-14T00:11:30+00:00""#),
        ]
        for (name, kind, observed) in cases {
            let h = try history(books: books(["draftkings": [row("00:10", 27, 7.5, kind: kind, observed: observed),
                                                             rec("01:00", 28, 8)]]))
            let input = try XCTUnwrap(mount(h), name)
            XCTAssertEqual(input.pairs.map(\.kind), [.synthetic, .recorded], name)
        }
    }

    func testTheDTOTellsMalformedProvenanceFromNone() throws {
        let h = try history(books: books(["draftkings": [row("00:10", 27, 7), row("00:11", 27, 7, kind: "7"),
                                                         row("00:12", 27, 7, kind: "null"),
                                                         row("00:13", 27, 7, observed: #""2026-09-14T00:13:05+00:00""#)]]))
        let rows = try XCTUnwrap(h.bookmakerHistory?["draftkings"])
        XCTAssertEqual(rows.map(\.servesProvenance), [false, true, true, true])
        XCTAssertNil(rows[1].kind, "a bad kind never blanks the envelope")
        XCTAssertEqual(rows[3].observedAt, "2026-09-14T00:13:05+00:00")
    }

    // MARK: - Before

    func testBeforeDrawsRecordedForecastsWithNoScoreFloorActualsOrFinal() throws {
        // The history retains an observed Q1 marker and scores; before the game neither is read.
        let h = try history(status: scheduled, completedAt: "null",
                            books: books(["draftkings": [rec("00:05", 27, 10), rec("00:10", 28, 10)]]))
        let input = try XCTUnwrap(mount(h, page: "scheduled", now: "2026-09-14T00:15:00Z".asDate))
        XCTAssertNil(input.scoreObservationStartAt)
        XCTAssertNil(input.kickoffAt)
        XCTAssertNil(input.finalAt)
        XCTAssertTrue(input.actuals.isEmpty)
        XCTAssertEqual(input.asOf, "2026-09-14T00:15:00Z".asDate)
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))
        XCTAssertEqual(series.phase, .before)
        XCTAssertTrue(series.actualSteps.isEmpty)
        XCTAssertNil(series.latestActual, "no invented 0–0")
        XCTAssertEqual(series.latest.home, 28)
        XCTAssertEqual(series.latest.away, 10)
    }

    func testBeforeAndDuringNeverPromoteUnmarkedRows() throws {
        let unmarked = books(["draftkings": [row("00:05", 27, 10), row("00:10", 28, 10)]])
        XCTAssertNil(mount(try history(status: scheduled, completedAt: "null", books: unmarked),
                           page: "scheduled", now: "2026-09-14T00:15:00Z".asDate))
        XCTAssertNil(mount(try history(status: live, completedAt: "null", books: unmarked),
                           page: "live", now: "2026-09-14T02:10:00Z".asDate))
    }

    func testBeforeAndDuringNeedTheReaderClockAndNoCompletionStamp() throws {
        let rows = books(["draftkings": [rec("00:05", 27, 10), rec("00:10", 28, 10)]])
        let now = "2026-09-14T00:30:00Z".asDate
        XCTAssertNil(mount(try history(status: scheduled, completedAt: "null", books: rows), page: "scheduled"))
        XCTAssertNil(mount(try history(status: live, completedAt: "null", books: rows), page: "live"))
        // A stamp on a game both sides call unfinished is stale or early, never the end of the line.
        XCTAssertNil(mount(try history(status: scheduled, books: rows), page: "scheduled", now: now))
        XCTAssertNil(mount(try history(status: live, books: rows), page: "live", now: now))
    }

    func testACaptureAfterTheReaderClockIsNeverRevealed() throws {
        // 00:05's displayed minute is before the clock; its capture (00:05:30) is not.
        let h = try history(status: scheduled, completedAt: "null",
                            books: books(["draftkings": [rec("00:04", 27, 10), rec("00:05", 31, 10)]]))
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(
            try XCTUnwrap(mount(h, page: "scheduled", now: "2026-09-14T00:05:10Z".asDate))))
        XCTAssertEqual(series.latest.at, capture("00:04"))
        XCTAssertEqual(series.latest.home, 27)
    }

    // MARK: - During

    private func duringHistory(markers: [String] = [Self.observedQ1]) throws -> EventHistoryResponse {
        try history(status: live, completedAt: "null", books: books(["draftkings": [
            rec("00:10", 27, 10), rec("00:40", 28, 10), rec("01:00", 30, 12), rec("02:05", 31, 13),
        ]]), markers: markers)
    }

    func testDuringFloorsActualStepsAtTheObservedFirstQuarter() throws {
        let input = try XCTUnwrap(mount(try duringHistory(), page: "live", now: "2026-09-14T02:10:00Z".asDate))
        XCTAssertEqual(input.scoreObservationStartAt, "2026-09-14T00:20:00Z".asDate)
        XCTAssertNil(input.kickoffAt, "an observed marker is a score floor, not a kickoff")
        XCTAssertNil(input.finalAt)
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))
        XCTAssertEqual(series.phase, .during)
        XCTAssertEqual(series.actualSteps.map(\.at), ["2026-09-14T00:50:00Z".asDate!, "2026-09-14T02:00:00Z".asDate!],
                       "the pregame 0–0 before the floor is not a step")
        XCTAssertEqual(series.latestActual, .init(at: "2026-09-14T02:00:00Z".asDate!, home: 14, away: 3))
    }

    func testDuringWithoutAnObservedFloorMountsNothing() throws {
        let now = "2026-09-14T02:10:00Z".asDate
        XCTAssertNil(mount(try duringHistory(markers: [Self.estimatedQ1]), page: "live", now: now))
        XCTAssertNil(mount(try duringHistory(markers: []), page: "live", now: now))
        // A floor after the reader's clock is not a game state they can see yet.
        XCTAssertNil(mount(try duringHistory(), page: "live", now: "2026-09-14T00:15:00Z".asDate))
    }

    func testDuringKeepsOrientationAndBreaksAtACaptureGap() throws {
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(
            try XCTUnwrap(mount(try duringHistory(), page: "live", now: "2026-09-14T02:10:00Z".asDate))))
        // 01:00:30 → 02:05:30 is 65 minutes of silence: two runs, never held through it.
        XCTAssertEqual(series.segments.map { $0.map(\.at) },
                       [[capture("00:10"), capture("00:40"), capture("01:00")], [capture("02:05")]])
        XCTAssertEqual(series.latest.home, 31, "home stays home")
        XCTAssertEqual(series.latest.away, 13)
    }

    func testDuringScrubClipsForecastsAndScores() throws {
        let input = try XCTUnwrap(mount(try duringHistory(), page: "live", now: "2026-09-14T02:10:00Z".asDate))
        let cursor = try XCTUnwrap(ProjectedFinalPointsSeries.at("2026-09-14T01:00:10Z".asDate!, input: input))
        XCTAssertEqual(cursor.latest.at, capture("00:40"), "01:00's capture is 20 s past the cursor")
        XCTAssertEqual(cursor.actualSteps.map(\.at), ["2026-09-14T00:50:00Z".asDate!])
    }

    // MARK: - Final (legacy compatibility)

    func testFinishedNFLMountsTheNamedBookWithNoCutoff() throws {
        let input = try XCTUnwrap(mount(try legacyFinished()))
        XCTAssertEqual(input.sourceKey, "draftkings", "an unnamed book never wins, however many pairs it has")
        XCTAssertNil(input.requestCutoffAt)
        XCTAssertNil(input.kickoffAt, "an observed marker is a score floor, not a kickoff")
        XCTAssertEqual(input.scoreObservationStartAt, "2026-09-14T00:20:00Z".asDate)
        XCTAssertEqual(input.asOf, "2026-09-14T03:30:00Z".asDate)
        XCTAssertEqual(input.pairs.map(\.kind), [.recorded, .recorded])
    }

    func testThePagesFinalIsTheLastActualAndNeverAForecast() throws {
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(try XCTUnwrap(mount(try legacyFinished()))))
        XCTAssertEqual(series.latestActual, .init(at: "2026-09-14T03:30:00Z".asDate!, home: 27, away: 7),
                       "score_history ends 26–7; the hero's 27–7 is the final")
        XCTAssertEqual(series.latest.home, 28)
        XCTAssertEqual(series.latest.away, 8)
        XCTAssertFalse(series.segments.flatMap { $0 }.contains { $0.home == 27 && $0.away == 7 })
    }

    func testUnmarkedRowsNeedBothAFinishedPageAndAFinishedHistory() throws {
        // completed_at is set in every case; only one side's status differs.
        for status in [live, scheduled, "null"] {
            XCTAssertNil(mount(try legacyFinished(historyStatus: status)), status)
        }
        let finished = try legacyFinished()
        let now = "2026-09-14T04:00:00Z".asDate
        for page in ["live", "scheduled", "upcoming", "postponed"] {
            XCTAssertNil(mount(finished, page: page, now: now), page)
        }
        XCTAssertNil(mount(finished, sport: "baseball_mlb"))
        XCTAssertNil(mount(nil))
    }

    func testUnobservedFirstQuarterMountsNothingAfterTheGame() throws {
        XCTAssertNil(mount(try legacyFinished(markers: [Self.estimatedQ1])))
        XCTAssertNil(mount(try legacyFinished(markers: [#"{"period":"1st Quarter","source":"espn_state","precision":"first_score","not_before":"2026-09-14T00:20:00Z"}"#])))
        XCTAssertNil(mount(try legacyFinished(markers: [#"{"period":"2nd Quarter","source":"espn_state","precision":"first_seen","not_before":"2026-09-14T00:20:00Z"}"#])))
    }

    func testAServedSyntheticOrUnknownKindIsNeverPromotedAfterTheGame() throws {
        for kind in [#""synthetic""#, #""estimated""#, "7"] {
            XCTAssertEqual(try XCTUnwrap(mount(try legacyFinished(firstRowKind: kind)), kind).pairs.map(\.kind),
                           [.synthetic, .recorded], kind)
        }
    }

    func testNoUsablePairMountsNothing() throws {
        let rows = #"{"draftkings":[{"timestamp":"2026-09-14T00:10:00Z","projected_home_score":null,"projected_away_score":7}]}"#
        XCTAssertNil(mount(try history(books: rows)))
    }

    // MARK: - Book picker

    func testATieGoesToTheFirstNamedBookInSortedOrder() throws {
        let h = try history(status: live, completedAt: "null", books: books([
            "fanduel": [rec("00:40", 29, 10), rec("01:00", 29, 10)],
            "draftkings": [rec("00:40", 28, 10), rec("01:00", 28, 10)],
        ]))
        XCTAssertEqual(mount(h, page: "live", now: "2026-09-14T01:10:00Z".asDate)?.sourceKey, "draftkings")
    }

    func testRefusedVolumeCannotHideABookWithRealReadings() throws {
        // betmgm sorts first and has six valid-looking pairs, none admissible:
        // re-stamps, an unproven kind, and a capture after the reader's clock.
        let h = try history(status: live, completedAt: "null", books: books([
            "betmgm": [row("00:25", 30, 10, kind: #""synthetic""#), row("00:26", 30, 10, kind: #""synthetic""#),
                       row("00:27", 30, 10, kind: #""synthetic""#), row("00:28", 30, 10, kind: #""estimated""#),
                       row("00:29", 30, 10, kind: #""recorded""#), rec("01:30", 30, 10)],
            "fanduel": [rec("00:40", 29, 10)],
        ]))
        let input = try XCTUnwrap(mount(h, page: "live", now: "2026-09-14T01:10:00Z".asDate))
        XCTAssertEqual(input.sourceKey, "fanduel")
        // After the game, rows WITH provenance still need it to be valid.
        let after = try history(books: books([
            "betmgm": (0..<6).map { row("00:2\($0)", 30, 10, kind: #""estimated""#) },
            "fanduel": [row("00:40", 29, 10)],
        ]))
        XCTAssertEqual(mount(after)?.sourceKey, "fanduel")
    }
}
