import XCTest
@testable import Bain_Luck

/// #1833 — a finished game's charts end where its readings end, not where the
/// backend learned the result.
///
/// `/events/15292394` (Real Madrid 77–78 Dubai, 2026-09-24): the last real
/// reading is 17:52Z, `completed_at` is 21:23:09Z, and `/history` stamps the
/// synthetic settlement point (1.0, `bookmaker_count: 0`) and the final-score
/// capture at `completed_at`. On master `a1830d986f` the phone drew Since Start
/// 9 AM → 2:25 PM PT, the line stopping near 11 AM and the 100% dot and the
/// final-score dot alone at 2:24 PM. `TerminalStamp` moves those points to the
/// last reading + 1 min, so the existing "end at the last game data point" rule
/// holds.
@MainActor
final class AFinishedChartEndsAtItsLastReading1833Tests: XCTestCase {

    private func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// The served specimen, trimmed to its edges (production read 2026-10-01).
    private func specimen(status: String = "completed",
                          completedAt: String? = "2026-09-24T21:23:09.917982+00:00",
                          extraHistory: String = "",
                          scoreHistory: String = #"[{"timestamp":"2026-09-24T21:23:09.980092+00:00","home_score":78,"away_score":77}]"#,
                          espn: String = "[]", winProb: String = "{}", aggregate: String = "null",
                          terminal: String = "2026-09-24T21:23:00+00:00") throws -> EventHistoryResponse {
        let completed = completedAt.map { "\"\($0)\"" } ?? "null"
        return try decode("""
        {"event_id":15292394,"home_team":"Dubai Basketball","away_team":"Real Madrid",
         "commence_time":"2026-09-24T16:00:00+00:00","completed_at":\(completed),"status":"\(status)",
         "commence_time_is_kickoff":true,
         "history":[
          {"timestamp":"2026-09-24T16:00:00+00:00","home_probability":0.57,"away_probability":0.43,"bookmaker_count":6},
          {"timestamp":"2026-09-24T17:20:00+00:00","home_probability":0.31,"away_probability":0.69,"bookmaker_count":5},
          {"timestamp":"2026-09-24T17:52:00+00:00","home_probability":0.5752,"away_probability":0.4248,"bookmaker_count":1}\(extraHistory),
          {"timestamp":"\(terminal)","home_probability":1.0,"away_probability":0.0,"bookmaker_count":0}],
         "bookmaker_history":{"betmgm":[{"timestamp":"2026-09-24T17:52:00+00:00","home_probability":0.5752}]},
         "score_history":\(scoreHistory),
         "espn_history":\(espn),"win_prob_history":\(winProb),"aggregate_line":\(aggregate)}
        """)
    }

    private func date(_ s: String) -> Date { s.asDate! }

    private func sinceStart(_ h: EventHistoryResponse) -> ClosedRange<Date>? {
        SharedChartWindow.domain(status: h.status, commenceTime: "2026-09-24T16:00:00+00:00",
                                 history: h, range: .sinceStart, sportKey: "basketball_euroleague")
    }

    func testTheSpecimenEndsAtItsLastReadingNotWhenTheResultWasLearned() throws {
        let raw = try specimen()
        // Strawman: the served payload IS the defect — the window runs to the settlement stamp.
        XCTAssertEqual(sinceStart(raw)?.upperBound, date("2026-09-24T21:23:30Z"))

        let confined = TerminalStamp.confined(raw)
        XCTAssertEqual(sinceStart(confined)?.lowerBound, date("2026-09-24T16:00:00Z"))
        XCTAssertEqual(sinceStart(confined)?.upperBound, date("2026-09-24T17:53:30Z"),
                       "the window ends one minute (+30 s pad) after the 17:52 reading")

        // The result is unchanged — only its x moved.
        let settled = try XCTUnwrap(confined.history.last)
        XCTAssertEqual(settled.homeProbability, 1.0)
        XCTAssertEqual(settled.bookmakerCount, 0)
        XCTAssertEqual(settled.timestamp.asDate, date("2026-09-24T17:53:00Z"))
        XCTAssertEqual(confined.history.count, raw.history.count)
        XCTAssertEqual(Array(confined.history.dropLast()).map(\.timestamp),
                       Array(raw.history.dropLast()).map(\.timestamp), "real readings never move")

        let final = try XCTUnwrap(confined.scoreHistory?.last)
        XCTAssertEqual(final.timestamp.asDate, date("2026-09-24T17:53:00Z"))
        XCTAssertEqual([final.homeScore, final.awayScore], [78, 77])
        XCTAssertEqual(confined.completedAt, raw.completedAt, "completed_at itself is not rewritten")
    }

    func testASettlementAlreadyBesideItsLastReadingStaysPut() throws {
        let raw = try specimen(completedAt: "2026-09-24T17:53:20+00:00",
                               scoreHistory: #"[{"timestamp":"2026-09-24T17:53:21+00:00","home_score":78,"away_score":77}]"#,
                               terminal: "2026-09-24T17:53:00+00:00")
        let confined = TerminalStamp.confined(raw)
        XCTAssertEqual(confined.history.map(\.timestamp), raw.history.map(\.timestamp))
        XCTAssertEqual(confined.scoreHistory?.map(\.timestamp), raw.scoreHistory?.map(\.timestamp))
    }

    func testAnInGameScoreCaptureIsAReadingAndStaysPut() throws {
        let raw = try specimen(scoreHistory: """
        [{"timestamp":"2026-09-24T18:05:00+00:00","home_score":75,"away_score":77},
         {"timestamp":"2026-09-24T21:23:09.980092+00:00","home_score":78,"away_score":77}]
        """)
        let confined = TerminalStamp.confined(raw)
        XCTAssertEqual(confined.scoreHistory?.first?.timestamp, "2026-09-24T18:05:00+00:00")
        XCTAssertEqual(confined.scoreHistory?.last?.timestamp.asDate, date("2026-09-24T18:06:00Z"))
        XCTAssertEqual(confined.history.last?.timestamp.asDate, date("2026-09-24T18:06:00Z"),
                       "the in-game capture is evidence the game ran past the last odds reading")
    }

    func testEverySeriesSettlementMovesButARealZeroOrOneReadingDoesNot() throws {
        let raw = try specimen(
            espn: """
            [{"timestamp":"2026-09-24T18:10:00+00:00","home_probability":0.93,"period":"4th Quarter"},
             {"timestamp":"2026-09-24T21:23:00+00:00","home_probability":1.0,"period":"Final","game_clock":"Final","home_score":78,"away_score":77}]
            """,
            winProb: """
            {"espn":[{"timestamp":"2026-09-24T18:09:00+00:00","home_probability":1.0},
                     {"timestamp":"2026-09-24T21:23:00+00:00","home_probability":1.0}]}
            """,
            aggregate: """
            [{"timestamp":"2026-09-24T18:10:00+00:00","home_probability":0.93},
             {"timestamp":"2026-09-24T21:23:00+00:00","home_probability":1.0}]
            """)
        let confined = TerminalStamp.confined(raw)
        let end = date("2026-09-24T18:11:00Z")
        XCTAssertEqual(confined.espnHistory?.last?.timestamp.asDate, end)
        XCTAssertEqual(confined.espnHistory?.last?.period, "Final")
        XCTAssertEqual(confined.winProbHistory?["espn"]?.last?.timestamp.asDate, end)
        XCTAssertEqual(confined.winProbHistory?["espn"]?.first?.timestamp, "2026-09-24T18:09:00+00:00",
                       "a real 100% reading at another minute is a reading, not the settlement")
        XCTAssertEqual(confined.aggregateLine?.last?.timestamp.asDate, end)
        XCTAssertEqual(confined.history.last?.timestamp.asDate, end)
        XCTAssertEqual(sinceStart(confined)?.upperBound, end.addingTimeInterval(30))
    }

    func testARealReadingAtTheSettlementMinuteMeansNothingMoves() throws {
        // A sportsbook reading genuinely taken in the minute the result was
        // learned: the line DID run that late, so the settlement is honest there.
        let raw = try specimen(extraHistory: #",{"timestamp":"2026-09-24T21:23:00+00:00","home_probability":0.62,"away_probability":0.38,"bookmaker_count":2}"#)
        let confined = TerminalStamp.confined(raw)
        XCTAssertEqual(confined.history.map(\.timestamp), raw.history.map(\.timestamp))
        XCTAssertEqual(confined.scoreHistory?.map(\.timestamp), raw.scoreHistory?.map(\.timestamp))
    }

    func testItIsIdempotent() throws {
        let once = TerminalStamp.confined(try specimen())
        let twice = TerminalStamp.confined(once)
        XCTAssertEqual(twice.history.map(\.timestamp), once.history.map(\.timestamp))
        XCTAssertEqual(twice.scoreHistory?.map(\.timestamp), once.scoreHistory?.map(\.timestamp))
    }

    func testALiveGameIsUntouched() throws {
        let raw = try specimen(status: "live", completedAt: nil)
        let confined = TerminalStamp.confined(raw)
        XCTAssertEqual(confined.history.map(\.timestamp), raw.history.map(\.timestamp))
        XCTAssertEqual(confined.scoreHistory?.map(\.timestamp), raw.scoreHistory?.map(\.timestamp))
    }

    // MARK: - The page takes the confined payload

    private final class Client: EventDetailProviding {
        struct Down: Error {}
        let detail: EventDetail
        let historyResponse: EventHistoryResponse
        init(_ detail: EventDetail, _ history: EventHistoryResponse) {
            self.detail = detail; historyResponse = history
        }
        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { historyResponse }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Down() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Down() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Down() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Down() }
    }

    func testThePageTakesTheConfinedPayload() async throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let detail = try decoder.decode(EventDetail.self, from: Data("""
        {"id":15292394,"home_team":"Dubai Basketball","away_team":"Real Madrid","status":"completed",
         "commence_time":"2026-09-24T16:00:00+00:00","home_score":78,"away_score":77}
        """.utf8))
        let vm = EventDetailViewModel(eventId: 15292394, client: Client(detail, try specimen()),
                                      sleep: { _ in try? await Task.sleep(for: .seconds(60)) })
        await vm.load()
        vm.stopRefresh()
        XCTAssertEqual(vm.history?.history.last?.timestamp.asDate, date("2026-09-24T17:53:00Z"))
        XCTAssertEqual(vm.history?.scoreHistory?.last?.timestamp.asDate, date("2026-09-24T17:53:00Z"))
    }

    /// Every write of a page's history goes through `TerminalStamp`, or takes a
    /// payload the page already confined. A census, not a per-site check: a new
    /// write that skips the stamp fails here by name.
    func testEveryHistoryWriteIsConfined() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        var writes: [String] = []
        for path in ["ViewModels/EventDetailViewModel.swift", "Components/OddsChartView.swift"] {
            let code = try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
            for line in code.components(separatedBy: "\n") {
                let t = line.trimmingCharacters(in: .whitespaces)
                guard !t.hasPrefix("//"),
                      t.range(of: #"^(self\.)?history = "#, options: .regularExpression) != nil else { continue }
                writes.append("\(path): \(t)")
            }
        }
        XCTAssertEqual(writes.sorted(), [
            // Both take EventDetailViewModel.history, which was confined on the way in.
            "Components/OddsChartView.swift: history = fresh",
            "Components/OddsChartView.swift: history = TerminalStamp.confined(",
            "Components/OddsChartView.swift: self.history = preloaded",
            "ViewModels/EventDetailViewModel.swift: history = TerminalStamp.confined(h)",
            "ViewModels/EventDetailViewModel.swift: history = TerminalStamp.confined(h)",
        ].sorted())
    }
}
