import XCTest
@testable import Bain_Luck

/// #9067 — rage #159: Georgia Tech @ Stanford, live, Game Segments printed
/// Stanford `7 · 3 · 3` beside a total of 19. The card rebuilt the line score
/// from `espn_history`, whose last row predated a touchdown the hero already
/// had, while ESPN's own per-quarter arrays sat in `box_score_data`.
///
/// Every array below is a production row read 2026-09-27 (`events.box_score_data`).
final class GameSegmentsReadsTheStoredLineScore9067Tests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func event(boxScore: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data("""
        {"id": 15315948, "home_team": "Stanford Cardinal", "away_team": "Georgia Tech Yellow Jackets",
         "sport": "americanfootball_ncaaf", "status": "live", "home_score": 34, "away_score": 20,
         "box_score_data": \(boxScore)}
        """.utf8))
    }

    private func texts(_ columns: [LineScoreColumn]) -> (labels: [String], away: [String], home: [String]) {
        (columns.map(\.label), columns.map(\.away.text), columns.map(\.home.text))
    }

    // MARK: - The payload

    func testTheServedArraysDecodeBesidePlayers() throws {
        let decoded = try event(boxScore: """
        {"players": {"Ben Gulbranson": {"passing_yards": 212}},
         "home_period_scores": [7, 3, 17, 7], "away_period_scores": [10, 10, 0, 0]}
        """)
        XCTAssertEqual(decoded.boxScoreData?.homePeriodScores, [7, 3, 17, 7])
        XCTAssertEqual(decoded.boxScoreData?.awayPeriodScores, [10, 10, 0, 0])
    }

    /// Today's server: `players` only. The card must fall back, not go blank.
    func testAPlayersOnlyPayloadYieldsNoLineScore() throws {
        let decoded = try event(boxScore: #"{"players": {"Ben Gulbranson": {"passing_yards": 212}}}"#)
        XCTAssertNotNil(decoded.boxScoreData)
        XCTAssertNil(decoded.boxScoreData?.homePeriodScores)
        XCTAssertNil(StoredLineScore.columns(
            homePeriods: decoded.boxScoreData?.homePeriodScores,
            awayPeriods: decoded.boxScoreData?.awayPeriodScores,
            sportKey: "americanfootball_ncaaf", homeTotal: 34, awayTotal: 20, isFinished: false))
    }

    /// A bad line score must never cost the reader the event page.
    func testAMalformedBoxScoreStillDecodesTheEvent() throws {
        XCTAssertEqual(try event(boxScore: #""oops""#).id, 15315948)
        XCTAssertEqual(try event(boxScore: "null").id, 15315948)
        let mixed = try event(boxScore: #"{"home_period_scores": [7, "x"], "away_period_scores": [10.0, null, 2.5]}"#)
        XCTAssertNil(mixed.boxScoreData?.homePeriodScores)
        XCTAssertEqual(mixed.boxScoreData?.awayPeriodScores, [10, nil, nil])
    }

    // MARK: - The specimen

    /// Rage #159's moment: Stanford had 19 (7 + 3 + 9 so far in Q3).
    func testTheSpecimenRowAddsUpToItsTotal() throws {
        let columns = try XCTUnwrap(StoredLineScore.columns(
            homePeriods: [7, 3, 9], awayPeriods: [10, 10, 0],
            sportKey: "americanfootball_ncaaf", homeTotal: 19, awayTotal: 20, isFinished: false))
        let t = texts(columns)
        XCTAssertEqual(t.labels, ["Q1", "Q2", "Q3", "Q4"])
        XCTAssertEqual(t.home, ["7", "3", "9", ""])
        XCTAssertEqual(t.away, ["10", "10", "0", ""])
    }

    /// The box score is refetched about once a minute; the scoreboard can be
    /// ahead of it. The still-moving quarter becomes `·` — never the `3` the
    /// reader circled.
    func testAStaleRunningPeriodIsUnknownNotWrong() throws {
        let columns = try XCTUnwrap(StoredLineScore.columns(
            homePeriods: [7, 3, 3], awayPeriods: [10, 10, 0],
            sportKey: "americanfootball_ncaaf", homeTotal: 19, awayTotal: 20, isFinished: false))
        XCTAssertEqual(texts(columns).home, ["7", "3", "·", ""])
        XCTAssertEqual(texts(columns).away, ["10", "10", "0", ""])
    }

    /// Arrays that sum PAST the scoreboard contradict it; the card falls back.
    func testArraysAheadOfTheScoreboardAreRefused() {
        XCTAssertNil(StoredLineScore.columns(
            homePeriods: [7, 3, 17, 7], awayPeriods: [10, 10, 0, 0],
            sportKey: "americanfootball_ncaaf", homeTotal: 27, awayTotal: 20, isFinished: false))
    }

    // MARK: - Sports

    /// 15318890: the home side won and never batted in the 9th.
    func testBaseballsUnneededBottomNinthIsX() throws {
        let columns = try XCTUnwrap(StoredLineScore.columns(
            homePeriods: [0, 1, 0, 1, 2, 0, 4, 0], awayPeriods: [0, 0, 0, 0, 0, 4, 0, 0, 0],
            sportKey: "baseball_mlb", homeTotal: 8, awayTotal: 4, isFinished: true))
        let t = texts(columns)
        XCTAssertEqual(t.labels, (1...9).map(String.init))
        XCTAssertEqual(t.home, ["0", "1", "0", "1", "2", "0", "4", "0", "X"])
        XCTAssertFalse(columns.contains { $0.home == .unknown || $0.away == .unknown })
    }

    /// Top of the 5th: the bottom half has not happened, so it is blank.
    func testLiveBaseballKeepsItsNineInningLadder() throws {
        let columns = try XCTUnwrap(StoredLineScore.columns(
            homePeriods: [1, 0, 0, 2], awayPeriods: [0, 0, 1, 0, 0],
            sportKey: "baseball_mlb", homeTotal: 3, awayTotal: 1, isFinished: false))
        XCTAssertEqual(columns.count, 9)
        XCTAssertEqual(texts(columns).home[4], "")
        XCTAssertEqual(texts(columns).away[4], "0")
    }

    /// 15314743 went to overtime; 15315689's fifth entry is a shootout, which
    /// the NHL spells the same way as a playoff second overtime.
    func testHockeyNamesOneOvertimeAndRefusesAFifthEntry() throws {
        let overtime = try XCTUnwrap(StoredLineScore.columns(
            homePeriods: [1, 1, 0, 1], awayPeriods: [0, 0, 2, 0],
            sportKey: "icehockey_nhl", homeTotal: 3, awayTotal: 2, isFinished: true))
        XCTAssertEqual(texts(overtime).labels, ["P1", "P2", "P3", "OT"])
        XCTAssertNil(StoredLineScore.columns(
            homePeriods: [1, 1, 0, 0, 0], awayPeriods: [1, 0, 1, 0, 1],
            sportKey: "icehockey_nhl", homeTotal: 2, awayTotal: 3, isFinished: true))
    }

    func testPeriodVocabularyBySport() throws {
        func labels(_ sport: String, _ count: Int) -> [String]? {
            let row = Array(repeating: Optional(0), count: count)
            return StoredLineScore.columns(
                homePeriods: row, awayPeriods: row, sportKey: sport,
                homeTotal: 0, awayTotal: 0, isFinished: true)?.map(\.label)
        }
        XCTAssertEqual(labels("basketball_ncaab", 3), ["1H", "2H", "OT"])
        XCTAssertEqual(labels("basketball_wncaab", 4), ["Q1", "Q2", "Q3", "Q4"])
        XCTAssertEqual(labels("basketball_wnba", 5), ["Q1", "Q2", "Q3", "Q4", "OT"])
        XCTAssertEqual(labels("americanfootball_ncaaf", 6), ["Q1", "Q2", "Q3", "Q4", "OT", "2OT"])
        XCTAssertEqual(labels("soccer_epl", 2), ["1H", "2H"])
        XCTAssertNil(labels("soccer_epl", 3), "extra time is not an OT")
        XCTAssertNil(labels("tennis_atp_us_open", 3))
        XCTAssertNil(labels("", 4))
    }

    func testANullEntryIsAHoleNotAZero() throws {
        let columns = try XCTUnwrap(StoredLineScore.columns(
            homePeriods: [7, nil, 17, 0], awayPeriods: [10, 10, 0, 0],
            sportKey: "americanfootball_ncaaf", homeTotal: 27, awayTotal: 20, isFinished: true))
        XCTAssertEqual(texts(columns).home, ["7", "·", "17", "0"])
    }

    // MARK: - The promise, over every production row

    /// For every specimen, whatever the scoreboard says: the known cells never
    /// sum past the total, and a row with no `·` sums to exactly the total.
    func testNoBuiltRowDisagreesWithItsTotal() {
        let rows: [(String, [Int?], [Int?], Bool)] = [
            ("americanfootball_ncaaf", [0, 10, 0], [14, 7, 3], false),
            ("americanfootball_ncaaf_fcs", [7, 7, 7, 0], [0, 14, 0, 0], false),
            ("americanfootball_ncaaf", [10, 0, 7, 10], [3, 7, 3, 14], false),
            ("americanfootball_ncaaf", [7, 3, 17, 7], [10, 10, 0, 0], false),
            ("baseball_mlb", [1, 0, 2, 3, 2, 2, 0, 0], [0, 1, 1, 2, 0, 0, 0, 0, 3], true),
            ("baseball_mlb", [0, 0, 4, 0, 0, 0, 0, 1], [0, 3, 0, 0, 0, 1, 1, 1, 1], true),
            ("icehockey_nhl", [1, 0, 3, 0], [2, 1, 1, 0], true),
            ("icehockey_nhl", [1, 0, 0, 0], [1, 0, 0, 0], true),
        ]
        for (sport, home, away, finished) in rows {
            for homeTotal in 0...40 {
                for awayTotal in [0, 5, 20, 24] {
                    guard let columns = StoredLineScore.columns(
                        homePeriods: home, awayPeriods: away, sportKey: sport,
                        homeTotal: homeTotal, awayTotal: awayTotal, isFinished: finished)
                    else { continue }
                    for (cells, total) in [(columns.map(\.home), homeTotal), (columns.map(\.away), awayTotal)] {
                        let known = cells.reduce(0) { $0 + ($1.points ?? 0) }
                        XCTAssertLessThanOrEqual(known, total, "\(sport) \(home) \(away)")
                        if !cells.contains(.unknown) {
                            XCTAssertEqual(known, total, "\(sport) \(home) \(away) \(homeTotal)-\(awayTotal)")
                        }
                    }
                }
            }
        }
    }
}
