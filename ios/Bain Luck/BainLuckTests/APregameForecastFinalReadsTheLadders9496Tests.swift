import XCTest
@testable import Bain_Luck

/// #9496 — before first pitch the iPhone game page prints the market's
/// forecast final wherever the server already serves a genuine one, and never
/// a final the sport cannot produce.
///
/// Specimen: Yankees (home) v Red Sox (away), `events/15319563`, first pitch
/// 2026-09-30 00:00Z, read 2026-09-29 05:58Z. `/history` served
/// `pm_spread_data.projected_final = {home 3.2, away 3.0, kalshi/kalshi}` while
/// `current_odds.projected_*` were null, and the app decoded no
/// `pm_spread_data` at all. Web prints the ladders' pair before kickoff where
/// the sportsbooks' is not a margin (`eventPageProjectedPair`), then withholds
/// `3 – 3` because baseball cannot end level (#8156). So this specimen's right
/// answer is SILENCE, and the same page with a non-level ladder pair prints it.
final class APregameForecastFinalReadsTheLadders9496Tests: XCTestCase {
    private static let now = Date(timeIntervalSince1970: 1_790_000_000)
    private static let beforeTheOff = now.addingTimeInterval(3 * 3600)
    private static let underway = now.addingTimeInterval(-3600)

    private func text(
        _ sport: String, status: String = "scheduled", start: Date = beforeTheOff,
        books: (home: Double, away: Double)? = nil,
        ladder: (home: Double, away: Double)? = nil, hasScore: Bool = false
    ) -> String? {
        EventDetailView.projectionText(
            sport: sport, status: status, commenceTime: start,
            projectedHome: books?.home, projectedAway: books?.away,
            ladderHome: ladder?.home, ladderAway: ladder?.away,
            hasScore: hasScore, now: Self.now)
    }

    private func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func history(pmSpreadData: String) -> String {
        """
        {"event_id": 15319563, "home_team": "New York Yankees", "away_team": "Boston Red Sox",
         "status": "scheduled", "history": [], "score_history": [],
         "pm_spread_data": \(pmSpreadData)}
        """
    }

    // MARK: - The served block reaches the page

    /// The block exactly as production served it (ladders trimmed to two rungs).
    func testTheSpecimensServedProjectedFinalDecodes() throws {
        let decoded = try decode(history(pmSpreadData: """
            {"implied_spreads": {"kalshi": {"spread": -0.2, "home_margin": 0.2, "confidence": 0.85,
               "contracts": [{"threshold": -1.5, "probability": 0.695}, {"threshold": 1.5, "probability": 0.355}]}},
             "implied_totals": {"kalshi": {"total": 6.2, "confidence": 0.9,
               "contracts": [{"threshold": 6.5, "probability": 0.475}]}},
             "projected_final": {"home_score": 3.2, "away_score": 3.0,
               "spread_source": "kalshi", "total_source": "kalshi"}}
            """))
        let final = try XCTUnwrap(decoded.pmSpreadData?.projectedFinal,
                                  "the app still drops the served forecast final")
        XCTAssertEqual(final.homeScore, 3.2)
        XCTAssertEqual(final.awayScore, 3.0)
        XCTAssertEqual(final.spreadSource, "kalshi")
        XCTAssertEqual(final.totalSource, "kalshi")
    }

    /// Null, absent and mistyped blocks cost the projection, never the chart.
    func testAMalformedBlockNeverBlanksTheHistory() throws {
        XCTAssertNil(try decode(history(pmSpreadData: "null")).pmSpreadData?.projectedFinal)
        XCTAssertNil(try decode(history(pmSpreadData: #"{"projected_final": null}"#)).pmSpreadData?.projectedFinal)
        XCTAssertNil(try decode(history(pmSpreadData: #"{"projected_final": "3-3"}"#)).pmSpreadData?.projectedFinal)
        XCTAssertNil(try decode(history(pmSpreadData: #"{"projected_final": {"home_score": 3.2}}"#)).pmSpreadData?.projectedFinal)
        XCTAssertNil(try decode(history(pmSpreadData: "7")).pmSpreadData?.projectedFinal)
    }

    // MARK: - The specimen and its control

    /// Ruling 240: A (#12992): `3.2 – 3.0` rounds to `3-3` and prints (`#8156` removed).
    func testTheSpecimenPrintsLevelPairUnder240A() {
        XCTAssertEqual(text("baseball_mlb", ladder: (3.2, 3.0)), "Proj. 3-3",
                       "240: A — level rounded baseball pair prints")
        XCTAssertEqual(text("baseball_mlb", ladder: (4.1, 2.9)), "Proj. 3-4")
    }

    /// The run line (#8617) and puck line (#13007) stay withheld; only the ladders speak for baseball and hockey.
    func testTheRunLineIsStillNotAProjection() {
        XCTAssertNil(text("baseball_mlb", books: (4.5, 3.0)))
        XCTAssertEqual(text("baseball_mlb", books: (4.5, 3.0), ladder: (4.1, 2.9)), "Proj. 3-4",
                       "a run-line pair displaced the ladders' forecast")
        XCTAssertNil(text("icehockey_nhl", books: (4.5, 3.0)))
        XCTAssertEqual(text("icehockey_nhl", books: (4.5, 3.0), ladder: (4.1, 2.9)), "Proj. 3-4",
                       "a puck-line pair displaced the ladders' forecast")
    }

    // MARK: - Web's precedence

    /// #9034: pre-game the sportsbooks' pair is the search card's, so it wins
    /// wherever it is a margin. Dolphins @ Chiefs: card 18-29, ladders 17-28.
    func testTheSportsbooksPairWinsWhereItIsAMargin() {
        XCTAssertEqual(text("americanfootball_nfl", books: (28.7, 17.5), ladder: (27.6, 17.2)),
                       "Proj. 18-29")
        XCTAssertEqual(text("americanfootball_nfl", ladder: (27.6, 17.2)), "Proj. 17-28",
                       "control: with no sportsbook pair the ladders answer")
        XCTAssertEqual(text("americanfootball_nfl", books: (28.7, -1), ladder: (27.6, 17.2)),
                       "Proj. 17-28", "a negative sportsbook half is not a points line")
    }

    /// Once underway the page keeps today's sportsbook-only behaviour.
    func testTheLaddersArePregameOnly() {
        XCTAssertNil(text("baseball_mlb", status: "live", start: Self.underway,
                          ladder: (4.1, 2.9), hasScore: true))
        XCTAssertNil(text("icehockey_nhl", status: "live", start: Self.underway,
                          ladder: (4.1, 2.9), hasScore: true))
        XCTAssertNil(text("baseball_mlb", status: "scheduled", start: Self.underway,
                          ladder: (4.1, 2.9), hasScore: true),
                     "a start time already passed is underway whatever the status says")
        XCTAssertEqual(text("basketball_nba", status: "live", start: Self.underway,
                            books: (104.5, 98.0), hasScore: true), "Proj. 98-105")
    }

    func testAFinishedGameIsNeverProjected() {
        XCTAssertNil(text("baseball_mlb", status: "completed", start: Self.underway,
                          ladder: (4.1, 2.9), hasScore: true))
    }

    /// Web's `hasDerivedSpread`: tennis quotes games and scores sets, and an
    /// undeclared sport has no unit to state.
    func testTheLaddersSpeakOnlyForSportsScoredInTheirUnit() {
        XCTAssertNil(text("tennis_atp_us_open", ladder: (20.4, 17.1)))
        XCTAssertNil(text("mma_mixed_martial_arts", ladder: (2.4, 1.1)))
    }

    // MARK: - Ruling 240: A (#12992) on whichever pair is chosen

    func testALevelFinalPrintsInEverySportUnder240A() {
        XCTAssertEqual(text("basketball_nba", books: (110.2, 109.8)), "Proj. 110-110")
        XCTAssertEqual(text("icehockey_nhl", ladder: (3.1, 2.8)), "Proj. 3-3")
        XCTAssertEqual(text("americanfootball_nfl", books: (24.2, 23.9)), "Proj. 24-24")
        XCTAssertEqual(text("soccer_epl", books: (1.2, 1.3)), "Proj. 1-1")
    }

    /// Web asks the RAW halves to be positive, so a low soccer half prints `0`.
    func testALowHalfStillPrintsWhereItRoundsToZero() {
        XCTAssertEqual(text("soccer_epl", books: (1.6, 0.4)), "Proj. 0-2")
        XCTAssertNil(text("soccer_epl", books: (1.6, 0)))
    }

    // MARK: - The chart

    /// A pregame history with no projection points draws no Score Differential
    /// chart at all — no 0–0 actual line, no invented margin history. The gate
    /// is the page's own state test, so it cannot be opened by data.
    func testThereIsNoPregameScoreDifferentialChart() throws {
        let source = try String(contentsOf: URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift"), encoding: .utf8)
        let squashed = source.filter { !$0.isWhitespace }
        // #10549 added one more clause — the projection's shared decision can
        // replace the card — which only ever narrows this gate.
        XCTAssertTrue(squashed.contains(
            "iflethistory=vm.history,(isLive||isFinished),!projectionReplacesDifferential{ScoreDifferentialChartView("),
            "the Score Differential chart is no longer gated to live and finished games")
        XCTAssertEqual(squashed.components(separatedBy: "ScoreDifferentialChartView(").count - 1, 1)
    }
}
