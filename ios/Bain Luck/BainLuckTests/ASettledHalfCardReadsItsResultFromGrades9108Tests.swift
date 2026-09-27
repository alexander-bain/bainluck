import XCTest
@testable import Bain_Luck

/// #9108 (iOS twin) — `/events/15315795`, Cruz Azul 3-3 Toluca, `espn_history`
/// empty: all four half cards on the phone drew no result. The rows below are
/// the served `period_markets`, verbatim, 2026-09-27.
final class ASettledHalfCardReadsItsResultFromGrades9108Tests: XCTestCase {

    private let home = "Cruz Azul"
    private let away = "Toluca"

    private let specimenJSON = """
    [
     {"market_name":"m","market_type":"half_spread","period":"1H","threshold":1.0,"outcome_name":"Cruz Azul wins the 1H by more than 1.5 goals","is_winner":true,"resolution_source":"api_settlement","probability":0.99,"source":"kalshi"},
     {"market_name":"m","market_type":"half_spread","period":"1H","threshold":1.0,"outcome_name":"Toluca wins the 1H by more than 1.5 goals","is_winner":false,"resolution_source":"api_settlement","probability":0.02,"source":"kalshi"},
     {"market_name":"m","market_type":"half_winner","period":"2H","threshold":2.0,"outcome_name":"Toluca wins 2nd Half","is_winner":true,"resolution_source":"api_settlement","probability":1.0,"source":"kalshi"},
     {"market_name":"m","market_type":"half_winner","period":"2H","threshold":2.0,"outcome_name":"Tie 2nd Half","is_winner":false,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_winner","period":"2H","threshold":2.0,"outcome_name":"Cruz Azul wins 2nd Half","is_winner":false,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_spread","period":"2H","threshold":2.0,"outcome_name":"Toluca wins the 2H by more than 1.5 goals","is_winner":true,"resolution_source":"api_settlement","probability":1.0,"source":"kalshi"},
     {"market_name":"m","market_type":"half_spread","period":"2H","threshold":2.0,"outcome_name":"Cruz Azul wins the 2H by more than 1.5 goals","is_winner":false,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_winner","period":"1H","threshold":1.0,"outcome_name":"Cruz Azul wins 1st Half","is_winner":true,"resolution_source":"api_settlement","probability":0.99,"source":"kalshi"},
     {"market_name":"m","market_type":"half_winner","period":"1H","threshold":1.0,"outcome_name":"Tie 1st Half","is_winner":false,"resolution_source":"api_settlement","probability":0.03,"source":"kalshi"},
     {"market_name":"m","market_type":"half_winner","period":"1H","threshold":1.0,"outcome_name":"Toluca wins 1st Half","is_winner":false,"resolution_source":"api_settlement","probability":0.01,"source":"kalshi"},
     {"market_name":"m","market_type":"half_total","period":"1H","threshold":0.5,"outcome_name":"Over 0.5 1H goals scored","is_winner":true,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_total","period":"1H","threshold":1.5,"outcome_name":"Over 1.5 1H goals scored","is_winner":true,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_total","period":"1H","threshold":2.5,"outcome_name":"Over 2.5 1H goals scored","is_winner":false,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_total","period":"2H","threshold":0.5,"outcome_name":"Over 0.5 2H goals scored","is_winner":true,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_total","period":"2H","threshold":1.5,"outcome_name":"Over 1.5 2H goals scored","is_winner":true,"resolution_source":"api_settlement","probability":null,"source":"kalshi"},
     {"market_name":"m","market_type":"half_total","period":"2H","threshold":2.5,"outcome_name":"Over 2.5 2H goals scored","is_winner":true,"resolution_source":"api_settlement","probability":null,"source":"kalshi"}
    ]
    """

    private func decode(_ json: String) throws -> [GameMarketOutcome] {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode([GameMarketOutcome].self, from: Data(json.utf8))
    }

    private func split(_ rows: [GameMarketOutcome], _ h: Int, _ a: Int) -> HalfScores.Pair {
        HalfScoresFromGrades.split(rows: rows, finalHome: h, finalAway: a, home: home, away: away)
    }

    private func row(_ type: String, _ period: String, _ threshold: Double?, _ outcome: String,
                     won: Bool, source: String? = "api_settlement") -> String {
        let t = threshold.map { "\($0)" } ?? "null"
        let s = source.map { "\"\($0)\"" } ?? "null"
        return #"{"market_name":"m","market_type":"\#(type)","period":"\#(period)","threshold":\#(t),"outcome_name":"\#(outcome)","is_winner":\#(won),"resolution_source":\#(s),"probability":null,"source":"kalshi"}"#
    }

    // MARK: - the specimen

    func test_the_pre_fix_path_had_nothing_to_draw() throws {
        // Strawman: no halftime reading ⇒ the ESPN rule returns `.none`.
        XCTAssertEqual(HalfScores.split(readings: [], currentHome: 3, currentAway: 3, isDone: true), .none)
    }

    func test_the_grades_leave_one_split_of_the_final() throws {
        let pair = split(try decode(specimenJSON), 3, 3)
        XCTAssertEqual(pair.first, HalfScoreSplit(home: 2, away: 0))
        XCTAssertEqual(pair.second, HalfScoreSplit(home: 1, away: 3))
        XCTAssertTrue(pair.isComplete(.first))
        XCTAssertTrue(pair.isComplete(.second))
    }

    func test_the_grade_fields_decode_and_absent_keys_are_nil() throws {
        let rows = try decode(specimenJSON)
        XCTAssertEqual(rows[0].isWinner, true)
        XCTAssertEqual(rows[0].resolutionSource, "api_settlement")
        let bare = try decode(#"[{"market_name":"m","outcome_name":"o","probability":0.5}]"#)
        XCTAssertNil(bare[0].isWinner)
        XCTAssertNil(bare[0].resolutionSource)
    }

    // MARK: - what fails closed

    func test_grades_that_contradict_the_final_draw_nothing() throws {
        // 1H total pinned at 2 and 2H over 2.5 cannot sum to a 1-1 final.
        XCTAssertEqual(split(try decode(specimenJSON), 1, 1), .none)
    }

    func test_grades_that_do_not_decide_draw_nothing() throws {
        let rows = try decode("[" + [
            row("half_winner", "1H", 1.0, "Cruz Azul wins 1st Half", won: true),
            row("half_winner", "2H", 2.0, "Toluca wins 2nd Half", won: true),
        ].joined(separator: ",") + "]")
        XCTAssertEqual(split(rows, 3, 3), .none)
    }

    func test_ungraded_rows_do_not_vote() throws {
        let nulled = specimenJSON.replacingOccurrences(of: #""api_settlement""#, with: "null")
        XCTAssertEqual(split(try decode(nulled), 3, 3), .none)
        let retracted = specimenJSON.replacingOccurrences(of: "api_settlement", with: "ungradeable_result")
        XCTAssertEqual(split(try decode(retracted), 3, 3), .none)
    }

    func test_no_final_score_is_no_split() throws {
        let rows = try decode(specimenJSON)
        XCTAssertEqual(HalfScoresFromGrades.split(rows: rows, finalHome: nil, finalAway: 3, home: home, away: away), .none)
    }

    // MARK: - each vote kind carries its own weight

    /// 1H total pinned at 2 of a 2-2 final leaves (2,0), (1,1), (0,2); only the
    /// spread row picks one — so these fail if its vote is dropped.
    private func pinnedTotal() -> [String] {
        [row("half_total", "1H", 1.5, "Over 1.5 1H goals scored", won: true),
         row("half_total", "1H", 2.5, "Over 2.5 1H goals scored", won: false)]
    }

    func test_the_spread_line_is_read_from_its_text_not_the_served_threshold() throws {
        // Served threshold is the half number (1.0) — the specimen's shape.
        let rows = try decode("[" + (pinnedTotal() + [
            row("half_spread", "1H", 1.0, "Cruz Azul wins the 1H by more than 0.5 goals", won: true),
        ]).joined(separator: ",") + "]")
        XCTAssertEqual(split(rows, 2, 2).first, HalfScoreSplit(home: 2, away: 0))
    }

    func test_a_half_winner_row_votes() throws {
        let rows = try decode("[" + (pinnedTotal() + [
            row("half_winner", "1H", 1.0, "Toluca wins 1st Half", won: true),
        ]).joined(separator: ",") + "]")
        XCTAssertEqual(split(rows, 2, 2).first, HalfScoreSplit(home: 0, away: 2))
    }

    func test_a_tie_row_votes() throws {
        let rows = try decode("[" + (pinnedTotal() + [
            row("half_winner", "1H", 1.0, "Tie 1st Half", won: true),
        ]).joined(separator: ",") + "]")
        XCTAssertEqual(split(rows, 2, 2).first, HalfScoreSplit(home: 1, away: 1))
    }

    func test_a_signed_handicap_leg_does_not_vote() throws {
        // "+1.5" means the opposite of "-1.5"; only "wins … by more than N" is read.
        let rows = try decode("[" + (pinnedTotal() + [
            row("half_spread", "1H", 1.5, "Toluca +1.5", won: true),
        ]).joined(separator: ",") + "]")
        XCTAssertEqual(split(rows, 2, 2), .none)
    }

    func test_an_integer_total_line_does_not_vote() throws {
        // An integer line can push: `>` and `>=` disagree. On a 2-1 final with
        // Cruz Azul winning the 1H, (1,0), (2,0), (2,1) survive; were the
        // `Over 1` row allowed to vote it would leave (1,0) alone.
        let rows = try decode("[" + [
            row("half_total", "1H", 1.0, "Over 1 1H goals scored", won: false),
            row("half_winner", "1H", 1.0, "Cruz Azul wins 1st Half", won: true),
        ].joined(separator: ",") + "]")
        XCTAssertEqual(split(rows, 2, 1), .none)
    }

    func test_a_row_naming_both_sides_does_not_vote() throws {
        let rows = try decode("[" + (pinnedTotal() + [
            row("half_winner", "1H", 1.0, "Cruz Azul or Toluca wins 1st Half", won: true),
        ]).joined(separator: ",") + "]")
        XCTAssertEqual(split(rows, 2, 2), .none)
    }

    // MARK: - wiring

    func test_the_event_page_falls_back_only_without_a_halftime_reading() {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        guard let src = try? String(contentsOf: url, encoding: .utf8) else {
            return XCTFail("could not read \(url.path)")
        }
        XCTAssertTrue(src.contains("guard fromHistory.first == nil, isFinished else { return fromHistory }"))
        XCTAssertTrue(src.contains("HalfScoresFromGrades.split("))
    }
}
