import XCTest
@testable import Bain_Luck

/// #10239 — the page's admission for the projected final-points module,
/// decoded from a served `/history` shape (twin of web `projectedFinalPointsMount`).
@MainActor
final class ProjectedFinalPointsMount10239Tests: XCTestCase {
    private func history(bookKind: String = "", historyStatus: String = #""completed""#, marker: String = #"{"period":"1st Quarter","source":"espn_state","precision":"first_seen","not_before":"2026-09-14T00:20:00Z"}"#,
                         books: String? = nil) throws -> EventHistoryResponse {
        let kindField = bookKind.isEmpty ? "" : #","kind":\#(bookKind)"#
        let bookRows = books ?? """
        {"draftkings":[
          {"timestamp":"2026-09-14T00:10:00Z","home_probability":0.8,"projected_home_score":27,"projected_away_score":7.5\(kindField)},
          {"timestamp":"2026-09-14T01:00:00Z","home_probability":0.85,"projected_home_score":28,"projected_away_score":8}],
         "unknownbook":[
          {"timestamp":"2026-09-14T00:10:00Z","projected_home_score":30,"projected_away_score":3},
          {"timestamp":"2026-09-14T00:20:00Z","projected_home_score":30,"projected_away_score":3},
          {"timestamp":"2026-09-14T00:30:00Z","projected_home_score":30,"projected_away_score":3}]}
        """
        let json = """
        {"event_id":14780549,"home_team":"Home","away_team":"Away","status":\(historyStatus),
         "completed_at":"2026-09-14T03:30:00Z","history":[],
         "bookmaker_history":\(bookRows),
         "score_history":[{"timestamp":"2026-09-14T01:30:00Z","home_score":7,"away_score":0},
                          {"timestamp":"2026-09-14T03:20:00Z","home_score":26,"away_score":7}],
         "period_markers":[\(marker)]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func mount(_ h: EventHistoryResponse?, sport: String = "americanfootball_nfl",
                       status: String = "completed") -> ProjectedFinalPointsSeries.Input? {
        ProjectedFinalPointsMount.input(sportKey: sport, eventStatus: status, history: h,
                                        finalHome: 27, finalAway: 7)
    }

    func testFinishedNFLMountsTheNamedBookWithNoCutoff() throws {
        let input = try XCTUnwrap(mount(try history()))
        XCTAssertEqual(input.sourceKey, "draftkings", "an unnamed book never wins, however many pairs it has")
        XCTAssertNil(input.requestCutoffAt)
        XCTAssertNil(input.kickoffAt, "an observed marker is a score floor, not a kickoff")
        XCTAssertEqual(input.scoreObservationStartAt, "2026-09-14T00:20:00Z".asDate)
        XCTAssertEqual(input.asOf, "2026-09-14T03:30:00Z".asDate)
        XCTAssertEqual(input.pairs.map(\.kind), [.recorded, .recorded])
    }

    func testThePagesFinalIsTheLastActualAndNeverAForecast() throws {
        let input = try XCTUnwrap(mount(try history()))
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))
        XCTAssertEqual(series.latestActual, .init(at: "2026-09-14T03:30:00Z".asDate!, home: 27, away: 7),
                       "score_history ends 26–7; the hero's 27–7 is the final")
        XCTAssertEqual(series.latest.home, 28)
        XCTAssertEqual(series.latest.away, 8)
        XCTAssertFalse(series.segments.flatMap { $0 }.contains { $0.home == 27 && $0.away == 7 })
    }

    func testOnlyFinishedNFLMounts() throws {
        let h = try history()
        for status in ["live", "scheduled", "upcoming"] {
            XCTAssertNil(mount(h, status: status), status)
        }
        XCTAssertNil(mount(h, sport: "baseball_mlb"))
        XCTAssertNil(mount(nil))
    }

    func testUnobservedFirstQuarterMountsNothing() throws {
        XCTAssertNil(mount(try history(marker: #"{"period":"1st Quarter","source":"estimated","precision":"first_seen","not_before":"2026-09-14T00:20:00Z"}"#)))
        XCTAssertNil(mount(try history(marker: #"{"period":"1st Quarter","source":"espn_state","precision":"first_score","not_before":"2026-09-14T00:20:00Z"}"#)))
        XCTAssertNil(mount(try history(marker: #"{"period":"2nd Quarter","source":"espn_state","precision":"first_seen","not_before":"2026-09-14T00:20:00Z"}"#)))
    }

    func testAServedSyntheticKindIsHonouredAndAMistypedOneDecodesNil() throws {
        let synthetic = try XCTUnwrap(mount(try history(bookKind: #""synthetic""#)))
        XCTAssertEqual(synthetic.pairs.map(\.kind), [.synthetic, .recorded])
        let mistyped = try history(bookKind: "7")
        XCTAssertNil(mistyped.bookmakerHistory?["draftkings"]?.first?.kind, "a bad kind never blanks the envelope")
    }

    func testAFinishedPageOverAnUnfinishedHistoryMountsNothing() throws {
        // completed_at is set in every case; only the history's own status differs.
        for status in [#""live""#, #""scheduled""#, "null"] {
            XCTAssertNil(mount(try history(historyStatus: status)), status)
        }
    }

    func testAnUnknownServedKindIsNeverPromotedToRecorded() throws {
        let unknown = try history(bookKind: #""estimated""#)
        XCTAssertEqual(unknown.bookmakerHistory?["draftkings"]?.first?.kind, "estimated", "the DTO keeps it")
        XCTAssertEqual(try XCTUnwrap(mount(unknown)).pairs.map(\.kind), [.synthetic, .recorded])
        let recorded = try XCTUnwrap(mount(try history(bookKind: #""recorded""#)))
        XCTAssertEqual(recorded.pairs.map(\.kind), [.recorded, .recorded])
    }

    func testNoUsablePairMountsNothing() throws {
        let books = #"{"draftkings":[{"timestamp":"2026-09-14T00:10:00Z","projected_home_score":null,"projected_away_score":7}]}"#
        XCTAssertNil(mount(try history(books: books)))
    }
}
