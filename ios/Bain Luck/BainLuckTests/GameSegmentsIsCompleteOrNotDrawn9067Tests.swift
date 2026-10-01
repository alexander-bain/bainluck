import XCTest
@testable import Bain_Luck

/// #9067, second specimen — rage #165 (Alex, iPhone 1.0.1 build 32,
/// 2026-09-30 02:48:56Z). Red Sox @ Yankees, AL Wild Card game 1, event
/// `15319563`, live at BOS 0 – NYY 4. Game Segments read
///
///     BOS 0 0 0 0 0 0 0   0
///     NYY 0 · · 0 · · 0   4
///
/// under a caption wrapped to "Score by period · · = not recorded", and Alex
/// circled it: "This formatting is all messed up." Every `·` was honest — the
/// pollers missed those half-innings — and the card still read as broken: a
/// row of zeros beside a 4, plus a sentence explaining why.
///
/// The rule now: Game Segments prints a complete line score or nothing
/// (notice 34). These tests build the real card (`SegmentBreakdown`) from a
/// decoded payload.
final class GameSegmentsIsCompleteOrNotDrawn9067Tests: XCTestCase {

    // MARK: - Fixtures

    /// `/api/events/15319563/history` `espn_history`, every row up to Alex's
    /// shake (02:48:56Z), as (timestamp, period, home NYY, away BOS).
    private static let yankeesAtTheShake: [(String, String, Int, Int)] = [
        ("2026-09-30T00:29:04Z", "Bottom 1st", 0, 0),
        ("2026-09-30T00:42:05Z", "Top 2nd", 0, 0),
        ("2026-09-30T00:50:05Z", "Bottom 2nd", 0, 0),
        ("2026-09-30T01:09:04Z", "Bottom 3rd", 1, 0),
        ("2026-09-30T01:17:05Z", "Top 4th", 1, 0),
        ("2026-09-30T01:52:05Z", "Bottom 5th", 1, 0),
        ("2026-09-30T02:11:05Z", "Bottom 6th", 2, 0),
        ("2026-09-30T02:31:04Z", "Bottom 7th", 2, 0),
        ("2026-09-30T02:48:05Z", "Top 8th", 4, 0),
    ]

    private func history(_ rows: [(String, String, Int, Int)]) throws -> EventHistoryResponse {
        let object: [String: Any] = [
            "event_id": 15319563,
            "home_team": "New York Yankees",
            "away_team": "Boston Red Sox",
            "history": [],
            "espn_history": rows.map {
                ["timestamp": $0.0, "period": $0.1, "home_score": $0.2, "away_score": $0.3]
            },
        ]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            EventHistoryResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func lineScore(home: [Int?], away: [Int?]) throws -> EventBoxScoreData {
        let object: [String: Any] = [
            "home_period_scores": home.map { $0 as Any? ?? NSNull() },
            "away_period_scores": away.map { $0 as Any? ?? NSNull() },
        ]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(
            EventBoxScoreData.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func texts(_ breakdown: SegmentBreakdown) -> (home: [String], away: [String]) {
        (breakdown.segments.map(\.home.text), breakdown.segments.map(\.away.text))
    }

    // MARK: - The specimen

    /// The payload served no line score (live withheld a box that had fallen
    /// behind the scoreboard), so the card fell back to these polled rows.
    func testRage165DrawsNoCard() throws {
        XCTAssertNil(SegmentBreakdown(
            history: try history(Self.yankeesAtTheShake),
            isFinished: false, sportKey: "baseball_mlb",
            finalHomeScore: 4, finalAwayScore: 0
        ), "a line score with gaps beside NYY 4 is the card Alex circled")
    }

    /// The specimen really is the gapped shape — so the test above is refusing
    /// it for the new reason, not because the inference failed outright.
    func testTheSpecimensInferenceHasGaps() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            Self.yankeesAtTheShake.map { .init(period: $0.1, homeScore: $0.2, awayScore: $0.3) },
            isFinished: false, homeFinal: 4, awayFinal: 0
        ))
        XCTAssertTrue(rows.home.contains(.unknown))
        XCTAssertFalse(StoredLineScore.isDrawable(home: rows.home, away: rows.away))
    }

    /// The same game finished 9–0: `GET /api/events/15319563` (read 09:3xZ
    /// 10/1) serves this complete line score, and the card prints it, the
    /// unneeded bottom 9th an `X`.
    func testCONTROLTheSameGamesCompleteLineScoreIsDrawn() throws {
        let breakdown = try XCTUnwrap(SegmentBreakdown(
            history: nil,
            lineScore: try lineScore(home: [0, 1, 0, 0, 1, 0, 2, 5], away: [0, 0, 0, 0, 0, 0, 0, 0, 0]),
            isFinished: true, sportKey: "baseball_mlb",
            finalHomeScore: 9, finalAwayScore: 0
        ))
        XCTAssertEqual(texts(breakdown).home, ["0", "1", "0", "0", "1", "0", "2", "5", "X"])
        XCTAssertEqual(texts(breakdown).away, ["0", "0", "0", "0", "0", "0", "0", "0", "0"])
    }

    // MARK: - Every path

    /// A stored array with a hole is not drawn, and with no polled rows to fall
    /// back on there is no card.
    func testAStoredLineScoreWithAHoleIsNotDrawn() throws {
        XCTAssertNil(SegmentBreakdown(
            history: nil,
            lineScore: try lineScore(home: [7, nil, 17, 7], away: [10, 10, 0, 7]),
            isFinished: true, sportKey: "americanfootball_ncaaf",
            finalHomeScore: 34, finalAwayScore: 27
        ))
    }

    /// A live box one score behind the scoreboard: the running quarter would
    /// be `·`, so the card waits for the box to catch up instead.
    func testAStoredLineScoreBehindTheScoreboardIsNotDrawn() throws {
        XCTAssertNil(SegmentBreakdown(
            history: nil,
            lineScore: try lineScore(home: [7, 3, 17], away: [10, 10, 0]),
            isFinished: false, sportKey: "americanfootball_ncaaf",
            finalHomeScore: 34, finalAwayScore: 20
        ))
    }

    /// GT @ Stanford (15315948), the first specimen, served arrays that add up:
    /// drawn exactly as served.
    func testCONTROLACompleteStoredLineScoreIsDrawn() throws {
        let breakdown = try XCTUnwrap(SegmentBreakdown(
            history: nil,
            lineScore: try lineScore(home: [7, 3, 17, 7], away: [10, 10, 0, 7]),
            isFinished: true, sportKey: "americanfootball_ncaaf",
            finalHomeScore: 34, finalAwayScore: 27
        ))
        XCTAssertEqual(texts(breakdown).home, ["7", "3", "17", "7"])
        XCTAssertEqual(texts(breakdown).away, ["10", "10", "0", "7"])
    }

    /// The generic fallback (no half-inning labels) with an inning the pollers
    /// never saw: not drawn.
    func testTheGenericFallbackWithAMissedInningIsNotDrawn() throws {
        XCTAssertNil(SegmentBreakdown(
            history: try history([
                ("2026-09-30T00:30:00Z", "1st Inning", 0, 0),
                ("2026-09-30T01:10:00Z", "3rd Inning", 1, 0),
            ]),
            isFinished: false, sportKey: "baseball_mlb",
            finalHomeScore: 1, finalAwayScore: 0
        ))
    }

    /// The generic fallback on a live game with every inning so far observed:
    /// drawn, and the innings still to come are blank — they are not gaps, and
    /// marking them `·` would hide the card for the rest of every such game.
    func testCONTROLTheGenericFallbackLeavesInningsToComeBlankAndDraws() throws {
        let breakdown = try XCTUnwrap(SegmentBreakdown(
            history: try history([
                ("2026-09-30T00:30:00Z", "1st Inning", 0, 0),
                ("2026-09-30T00:50:00Z", "2nd Inning", 1, 0),
                ("2026-09-30T01:10:00Z", "3rd Inning", 1, 0),
            ]),
            isFinished: false, sportKey: "baseball_mlb",
            finalHomeScore: 1, finalAwayScore: 0
        ))
        XCTAssertEqual(texts(breakdown).home, ["0", "1", "0", "", "", "", "", "", ""])
        XCTAssertEqual(texts(breakdown).away, ["0", "0", "0", "", "", "", "", "", ""])
    }

    // MARK: - The rule

    func testIsDrawable() {
        XCTAssertTrue(StoredLineScore.isDrawable(home: [.score(1), .notPlayed], away: [.score(0), .notPlayed]))
        XCTAssertTrue(StoredLineScore.isDrawable(home: [.score(1), .notNeeded], away: [.score(0), .score(0)]))
        XCTAssertFalse(StoredLineScore.isDrawable(home: [.score(1), .unknown], away: [.score(0), .score(0)]))
        XCTAssertFalse(StoredLineScore.isDrawable(home: [.score(1), .score(0)], away: [.unknown, .score(0)]))
    }

    /// With no `·` left to explain, the caption cannot carry the
    /// "not recorded" sentence Alex's screenshot wrapped onto two lines.
    func testTheCaptionNoLongerExplainsAGap() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.contains("not recorded\""), "Game Segments' caption explains a gap again")
    }
}
