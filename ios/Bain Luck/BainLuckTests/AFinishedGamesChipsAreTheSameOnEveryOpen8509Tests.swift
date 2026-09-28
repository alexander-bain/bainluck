import XCTest
@testable import Bain_Luck

/// #8509 — a finished game's inning chips are the same on every open.
///
/// Mets @ Rangers (15318166), production `/history` read 2026-09-28: two
/// win-probability sources carry the inning, and they see it at different
/// times. `stat_model` first reads the 4th at 19:32:04Z ("Top 4th"); `espn`
/// first reads it at 19:39:08Z ("Bottom 4th"). For the 9th: 21:02:07Z vs
/// 21:07:07Z. Both charts let whichever source the `Dictionary` yielded first
/// claim the label, so the chip moved (and the spacing rule dropped a
/// neighbour) between two opens of the same bytes.
///
/// The rule: the earliest sighting across all sources; ties go to the
/// alphabetically first source.
@MainActor
final class AFinishedGamesChipsAreTheSameOnEveryOpen8509Tests: XCTestCase {

    private func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func reading(_ stamp: String, _ period: String? = nil, home: Int? = nil, away: Int? = nil) -> String {
        var state: [String] = []
        if let period { state.append("\"period\": \"\(period)\"") }
        if let home { state.append("\"home_score\": \(home)") }
        if let away { state.append("\"away_score\": \(away)") }
        return "{\"timestamp\": \"\(stamp)\", \"home_probability\": 0.5, \"game_state\": {\(state.joined(separator: ", "))}}"
    }

    /// The specimen's two sources, trimmed to the readings that decide the 4th
    /// and 9th chips. `espnWrittenFirst` flips the order the keys are WRITTEN in.
    private func mets(espnWrittenFirst: Bool) throws -> EventHistoryResponse {
        let espn = "\"espn\": [\(reading("2026-09-24T19:39:08Z", "Bottom 4th")), \(reading("2026-09-24T21:07:07Z", "Top 9th"))]"
        let model = """
        "stat_model": [\(reading("2026-09-24T19:31:04Z", "End 3rd")), \(reading("2026-09-24T19:32:04Z", "Top 4th")),
          \(reading("2026-09-24T19:38:04Z", "Bottom 4th")), \(reading("2026-09-24T21:01:07Z", "End 8th")),
          \(reading("2026-09-24T21:02:07Z", "Top 9th"))]
        """
        let body = espnWrittenFirst ? "\(espn), \(model)" : "\(model), \(espn)"
        return try decode("""
        {"event_id": 15318166, "home_team": "Texas Rangers", "away_team": "New York Mets",
         "status": "completed", "history": [], "win_prob_history": {\(body)}}
        """)
    }

    // MARK: - The rule

    /// THE SHIP. The 4th and the 9th go where the first source to see them saw
    /// them, whichever source that is and however the keys arrive.
    func testEachInningIsPlacedAtItsEarliestSightingAcrossSources() throws {
        let sightings = WinProbPeriodSightings.earliest(
            in: try mets(espnWrittenFirst: true).winProbHistory, sportKey: "baseball_mlb")
        let byLabel = Dictionary(uniqueKeysWithValues: sightings.map { ($0.label, $0) })

        // `espn` sorts before `stat_model`, so a rule that just walked sources
        // in sorted order would put these at espn's LATER times.
        XCTAssertEqual(byLabel["4th"]?.date, "2026-09-24T19:32:04Z".asDate, "the 4th was not placed at its first sighting")
        XCTAssertEqual(byLabel["9th"]?.date, "2026-09-24T21:02:07Z".asDate, "the 9th was not placed at its first sighting")
        // notBefore comes from the source that won the label.
        XCTAssertEqual(byLabel["4th"]?.notBefore, "2026-09-24T19:31:04Z".asDate)
        XCTAssertEqual(sightings.map(\.date), sightings.map(\.date).sorted(), "sightings are not in time order")
    }

    /// Same bytes, many decodes, both key orders: one answer.
    func testTheSameBytesGiveTheSameChipsOnEveryDecode() throws {
        let reference = WinProbPeriodSightings.earliest(
            in: try mets(espnWrittenFirst: true).winProbHistory, sportKey: "baseball_mlb")
        XCTAssertFalse(reference.isEmpty)
        for attempt in 0..<40 {
            let again = WinProbPeriodSightings.earliest(
                in: try mets(espnWrittenFirst: attempt.isMultiple(of: 2)).winProbHistory, sportKey: "baseball_mlb")
            XCTAssertEqual(again, reference, "decode \(attempt) placed different chips")
        }
    }

    /// Two sources seeing a label at the same instant: the alphabetically first
    /// one wins, visible through which source's `notBefore` the chip carries.
    func testATieGoesToTheAlphabeticallyFirstSource() throws {
        let history = try decode("""
        {"event_id": 1, "home_team": "A", "away_team": "B", "status": "completed", "history": [],
         "win_prob_history": {
           "zeta": [\(reading("2026-09-24T19:25:00Z", "Top 3rd")), \(reading("2026-09-24T19:40:00Z", "Top 4th"))],
           "alpha": [\(reading("2026-09-24T19:20:00Z", "Top 3rd")), \(reading("2026-09-24T19:40:00Z", "Top 4th"))]
         }}
        """)
        let fourth = WinProbPeriodSightings.earliest(in: history.winProbHistory, sportKey: "baseball_mlb")
            .first { $0.label == "4th" }
        XCTAssertEqual(fourth?.notBefore, "2026-09-24T19:20:00Z".asDate, "the tie went to the later-sorting source")
    }

    /// The score chart's window still filters before anything is chosen.
    func testAReadingOutsideTheWindowIsNotASighting() throws {
        let cutoff = try XCTUnwrap("2026-09-24T19:35:00Z".asDate)
        let sightings = WinProbPeriodSightings.earliest(
            in: try mets(espnWrittenFirst: false).winProbHistory, sportKey: "baseball_mlb",
            admits: { $0 >= cutoff })
        let fourth = sightings.first { $0.label == "4th" }
        XCTAssertEqual(fourth?.date, "2026-09-24T19:38:04Z".asDate, "a reading before the window placed the chip")
        XCTAssertNil(fourth?.notBefore, "notBefore was taken from a reading outside the window")
    }

    // MARK: - The score line's fallback

    /// Two sources reading the score in the same minute: the earlier reading is
    /// the one drawn, on every decode.
    func testTheScoreFallbackTakesTheEarliestReadingInAMinute() throws {
        for attempt in 0..<20 {
            let late = "\"alpha\": [\(reading("2026-09-24T19:40:50Z", home: 2, away: 2))]"
            let early = "\"zeta\": [\(reading("2026-09-24T19:40:05Z", home: 3, away: 2))]"
            let body = attempt.isMultiple(of: 2) ? "\(late), \(early)" : "\(early), \(late)"
            let history = try decode("""
            {"event_id": 1, "home_team": "A", "away_team": "B", "status": "completed", "history": [],
             "win_prob_history": {\(body)}}
            """)
            let diffs = ScoreDifferentialChartView.winProbStateScoreDiffs(history: history, since: nil)
            XCTAssertEqual(diffs.count, 1)
            XCTAssertEqual(diffs.values.first?.diff, 1, "decode \(attempt) drew the later reading")
            XCTAssertEqual(diffs.values.first?.date, "2026-09-24T19:40:05Z".asDate)
        }
    }

    // MARK: - No chart walks the sources in Dictionary order to pick a winner

    /// Every `for (_, x) in …winProbHistory` first-wins loop is the defect's
    /// shape — including through the `wpHistory` local the probability chart
    /// bound it to. Order-independent reads (`.values` into a min/max, or a flat list
    /// that is sorted afterwards) are not this shape and are not flagged.
    func testNoChartPicksAWinnerInDictionaryOrder() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let app = root.appendingPathComponent("Bain Luck")
        let files = try XCTUnwrap(FileManager.default.enumerator(at: app, includingPropertiesForKeys: nil))
            .compactMap { $0 as? URL }
            .filter { $0.pathExtension == "swift" }
        XCTAssertGreaterThan(files.count, 50, "the scan found too few Swift files to mean anything")
        var offenders: [String] = []
        for file in files {
            let lines = try String(contentsOf: file, encoding: .utf8).split(separator: "\n")
            for (index, line) in lines.enumerated()
            where line.range(of: #"for \(_,\s*\w+\) in .*(winProbHistory|wpHistory)"#, options: .regularExpression) != nil {
                offenders.append("\(file.lastPathComponent):\(index + 1)")
            }
        }
        XCTAssertEqual(offenders, [], "a loop takes the first source a Dictionary yields")
    }
}
