import XCTest
@testable import Bain_Luck

/// #10598 — a finished game in iPhone Search suggestions says who won.
///
/// Native fix check for #10581, 2026-10-06 07:23Z (master `2ac8b41137`,
/// production v5510): typing `brewers` showed "San Diego Padres at Milwaukee
/// Brewers · FINAL · Oct 4, 1:00 PM" with no score, while pressing Search
/// showed 3 - 4 for the same game. `/api/events/typeahead?q=brewers` serves
/// 15323985 `status: completed, home_score: 4, away_score: 3`
/// (`_typeahead_final_score`, #9226), and `TypeaheadSuggestion` had no field
/// to decode them into. The web dropdown's half is `finalScoreText` in
/// `frontend/lib/searchSuggestionDisplay.ts`.
///
/// The view's wiring (the row draws `finalScoreText` and passes `timeStyle`)
/// is pinned by `frontend/__tests__/ios/searchSuggestionFinalScore10598.test.ts`,
/// because XCTest cannot see an arm inside a `some View` body.
final class SearchSuggestionFinalScore10598Tests: XCTestCase {

    private static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private static func row(_ json: String) throws -> TypeaheadSuggestion {
        try decoder().decode(TypeaheadSuggestion.self, from: Data(json.utf8))
    }

    private static let commence = "2026-10-04T18:10:00+00:00"

    // MARK: - Decode

    func testTheServedFinalDecodesBothScores() throws {
        // The production specimen's row, keys as `_typeahead_final_score` writes them.
        let rows = try Self.decoder().decode(TypeaheadResponse.self, from: Data("""
        {"query":"brewers","did_you_mean":null,"suggestions":[
         {"type":"event","text":"San Diego Padres at Milwaukee Brewers","event_id":15323985,
          "sport_key":"baseball_mlb","status":"completed",
          "commence_time":"\(Self.commence)","home_score":4,"away_score":3}]}
        """.utf8)).suggestions
        XCTAssertEqual(rows[0].homeScore, 4)
        XCTAssertEqual(rows[0].awayScore, 3)
        XCTAssertEqual(rows[0].finalScoreText, "3 - 4", "away first, as the row's text and the results row")
    }

    func testARowWithoutTheKeysStillDecodesAndPrintsNoScore() throws {
        // Every non-finished row, and any final the server had no score for.
        let row = try Self.row("""
        {"type":"event","text":"New York Yankees at Tampa Bay Rays","event_id":1,
         "status":"completed","commence_time":"\(Self.commence)"}
        """)
        XCTAssertNil(row.homeScore)
        XCTAssertNil(row.awayScore)
        XCTAssertNil(row.finalScoreText)
    }

    // MARK: - What a finished row prints

    func testAClosedRowPrintsItsScoreToo() throws {
        let row = try Self.row("""
        {"type":"event","text":"A at B","status":"closed","home_score":2,"away_score":5}
        """)
        XCTAssertEqual(row.finalScoreText, "5 - 2")
    }

    func testZeroIsAScore() throws {
        let row = try Self.row("""
        {"type":"event","text":"A at B","status":"completed","home_score":0,"away_score":0}
        """)
        XCTAssertEqual(row.finalScoreText, "0 - 0")
    }

    func testAHalfScorePrintsNothing() throws {
        for json in [
            #"{"type":"event","text":"A at B","status":"completed","home_score":4}"#,
            #"{"type":"event","text":"A at B","status":"completed","away_score":3}"#,
            #"{"type":"event","text":"A at B","status":"completed","home_score":4,"away_score":null}"#,
        ] {
            XCTAssertNil(try Self.row(json).finalScoreText, json)
        }
    }

    // MARK: - Live and scheduled rows are unchanged

    func testStrayScoreKeysOnAnUnfinishedRowPrintNothing() throws {
        for status in ["scheduled", "live", "suspended"] {
            let row = try Self.row("""
            {"type":"event","text":"A at B","status":"\(status)",
             "commence_time":"\(Self.commence)","home_score":1,"away_score":0}
            """)
            XCTAssertNil(row.finalScoreText, "\(status) printed a score")
            XCTAssertEqual(row.timeStyle, .full, "\(status) lost its clock")
        }
    }

    func testANonEventRowNeverPrintsAScore() throws {
        let row = try Self.row("""
        {"type":"team","text":"Milwaukee Brewers","status":"completed","home_score":4,"away_score":3}
        """)
        XCTAssertNil(row.finalScoreText)
    }

    // MARK: - A finished row prints the day, not the clock (#6444)

    func testAFinishedRowPrintsTheDayAndAScheduledOneKeepsTheClock() throws {
        let final = try Self.row("""
        {"type":"event","text":"A at B","status":"completed","commence_time":"\(Self.commence)",
         "home_score":4,"away_score":3}
        """)
        let scheduled = try Self.row("""
        {"type":"event","text":"A at B","status":"scheduled","commence_time":"\(Self.commence)"}
        """)
        XCTAssertEqual(final.timeStyle, .dayOnly)
        XCTAssertEqual(scheduled.timeStyle, .full)

        // Five days later: the dated arm in every reader's zone. Asserting on
        // the clock's colon keeps this independent of the locale's month form.
        let now = Self.commence.asDate!.addingTimeInterval(5 * 86_400)
        let finalText = RelativeTimeText.text(
            for: final.commenceTime, now: now, style: final.timeStyle) ?? ""
        let scheduledText = RelativeTimeText.text(
            for: scheduled.commenceTime, now: now, style: scheduled.timeStyle) ?? ""
        XCTAssertFalse(finalText.isEmpty)
        XCTAssertFalse(finalText.contains(":"), "a finished suggestion printed a clock: \(finalText)")
        XCTAssertTrue(scheduledText.contains(":"), "a scheduled suggestion lost its clock: \(scheduledText)")
    }
}
