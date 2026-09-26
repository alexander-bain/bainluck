import Foundation
import XCTest
@testable import Bain_Luck

/// #8652 — on Liberty's final (build 23) the unscrubbed readout said 31–69
/// while the plotted line ended at 0–100.
///
/// The readout's resting moment was built by the PAGE: its number came from
/// the newest point of ANY `win_prob_history` source (then consensus, then a
/// fabricated 50%) and its score/period from the last ESPN row. The chart
/// draws only its primary line — the backend blend when served, else the
/// sportsbook consensus — clipped at the game's end, so a venue print later
/// than the blend's last point printed a number the line never reached.
///
/// The chart now supplies the resting moment itself: the last point of the
/// line it draws, read the way a scrub to that point reads it.
final class TheRestingReadoutPrintsWhereTheLineEnds8652Tests: XCTestCase {

    private func history(
        status: String = "completed",
        consensus: String = "[]",
        winProb: String = "{}",
        aggregate: String = "null",
        espn: String = "[]"
    ) throws -> EventHistoryResponse {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventHistoryResponse.self, from: Data("""
        {"event_id": 1, "home_team": "Home", "away_team": "Away", "status": "\(status)",
         "history": \(consensus), "win_prob_history": \(winProb),
         "aggregate_line": \(aggregate), "espn_history": \(espn)}
        """.utf8))
    }

    private func resting(_ h: EventHistoryResponse, sport: String? = "basketball_wnba") -> GamePlayPoint? {
        let points = OddsChartView.enrichWithGameState(OddsChartView.chartPoints(from: h), history: h)
        return OddsChartView.restingPlayPoint(in: points, sportKey: sport)
    }

    // MARK: - The specimen: 15315984, Liberty 34–17 at Coastal Carolina

    /// The tail (>= 03:20Z) of the served /history, read 2026-09-26 — every
    /// series verbatim, including `aggregate_line`'s own (unsorted) order.
    private func specimen() throws -> EventHistoryResponse {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/event-15315984-history-8652-tail.20260926.json")
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventHistoryResponse.self, from: Data(contentsOf: url))
    }

    /// The chart's drawn set for a finished game: points, state, then the
    /// finished-game clip (`filterPoints`' first step). The page's shared
    /// window narrows further on the device (it closed at 03:38 in the render),
    /// which `testATieOnTheLastStampRestsOnTheVertexDrawnLast` covers.
    private func drawn(_ h: EventHistoryResponse) throws -> [ChartDataPoint] {
        let end = try XCTUnwrap(OddsChartView.gameEndDate(status: h.status, history: h))
        return OddsChartView.enrichWithGameState(OddsChartView.chartPoints(from: h), history: h)
            .filter { $0.date <= end }
    }

    /// Alex's build-23 frames: the line ends on the baseline for the
    /// Chanticleers, the card said 31–69. The drawn line's last point is the
    /// blend's 03:40 minute (1%, inside the clip's two-minute grace after
    /// ESPN's 03:38 final), and the readout now prints exactly that, beside
    /// the final score it was observed with.
    func testTheSpecimenRestsOnTheDrawnLinesEndNotAPostGamePrint() throws {
        let h = try specimen()
        let point = try XCTUnwrap(OddsChartView.restingPlayPoint(in: try drawn(h), sportKey: "americanfootball_ncaaf"))
        XCTAssertEqual(point.homeProb, 0.01)
        XCTAssertEqual(try XCTUnwrap(point.awayProb), 0.99, accuracy: 1e-9)
        XCTAssertEqual(point.homeScore, 17)
        XCTAssertEqual(point.awayScore, 34)
        XCTAssertEqual(point.period, "Final")
        XCTAssertEqual(point.timestamp.asDate, "2026-09-25T03:40:00Z".asDate)
    }

    /// Control, on the same bytes: the page's old rule reaches the post-game
    /// Polymarket print at 03:44:44 — the 31% on Alex's phone.
    func testTheSpecimenUnderTheOldRuleIsTheThirtyOnePercentOnTheDevice() throws {
        let h = try specimen()
        let newestAny = try XCTUnwrap(h.winProbHistory?.values.flatMap { $0 }
            .max { ($0.timestamp.asDate ?? .distantPast) < ($1.timestamp.asDate ?? .distantPast) })
        XCTAssertEqual(newestAny.homeProbability, 0.31)
        XCTAssertEqual(newestAny.timestamp, "2026-09-25T03:44:44.187229+00:00",
                       "the old rule's number is the post-game Polymarket print")
        XCTAssertTrue(h.winProbHistory?["polymarket"]?.contains { $0.timestamp == newestAny.timestamp } == true)
    }

    /// Why the clip matters: the unclipped blend's newest point is a
    /// post-final 1% (03:44), which is not where the drawn line ends.
    func testTheUnclippedBlendEndsPastTheGame() throws {
        let h = try specimen()
        let unclipped = OddsChartView.chartPoints(from: h)
        let last = try XCTUnwrap(OddsChartView.latestPrimaryPoint(in: unclipped))
        XCTAssertEqual(last.probability, 0.01)
        XCTAssertNotEqual(last.date, OddsChartView.latestPrimaryPoint(in: try drawn(h))?.date)
    }

    /// The specimen's shape: the blend ends at 0; a Kalshi print five minutes
    /// later still reads 31%. The line ends at 0, so the readout does.
    func testALaterVenuePrintDoesNotOutrankTheLineTheChartDraws() throws {
        let h = try history(
            winProb: """
            {"kalshi": [{"timestamp": "2026-09-20T02:00:00Z", "home_probability": 0.40},
                        {"timestamp": "2026-09-20T02:35:00Z", "home_probability": 0.31}],
             "espn":   [{"timestamp": "2026-09-20T02:00:00Z", "home_probability": 0.42}]}
            """,
            aggregate: """
            [{"timestamp": "2026-09-20T02:00:00Z", "home_probability": 0.41},
             {"timestamp": "2026-09-20T02:30:00Z", "home_probability": 0.0}]
            """)
        let point = try XCTUnwrap(resting(h))
        XCTAssertEqual(point.homeProb, 0.0)
        XCTAssertEqual(point.awayProb, 1.0)
        XCTAssertEqual(point.timestamp.asDate, "2026-09-20T02:30:00Z".asDate,
                       "the resting moment is the line's last point, not the newest venue print")
    }

    /// Strawman: the page's old rule (newest point of any served source) on
    /// the same payload is the defect — proves the specimen discriminates.
    func testTheOldRuleOnTheSamePayloadPrintsTheVenueNumber() throws {
        let h = try history(
            winProb: """
            {"kalshi": [{"timestamp": "2026-09-20T02:35:00Z", "home_probability": 0.31}]}
            """,
            aggregate: """
            [{"timestamp": "2026-09-20T02:30:00Z", "home_probability": 0.0}]
            """)
        let newestAny = h.winProbHistory?.values.flatMap { $0 }
            .max { ($0.timestamp.asDate ?? .distantPast) < ($1.timestamp.asDate ?? .distantPast) }
        XCTAssertEqual(newestAny?.homeProbability, 0.31)
        XCTAssertNotEqual(try XCTUnwrap(resting(h)).homeProb, newestAny?.homeProbability)
    }

    /// No blend served: the chart's primary line is the consensus, and the
    /// readout rests on it — not on a later venue print beside it.
    func testWithNoBlendTheReadoutRestsOnTheConsensus() throws {
        let h = try history(
            consensus: """
            [{"timestamp": "2026-09-20T02:00:00Z", "home_probability": 0.55},
             {"timestamp": "2026-09-20T02:20:00Z", "home_probability": 0.62}]
            """,
            winProb: """
            {"kalshi": [{"timestamp": "2026-09-20T02:40:00Z", "home_probability": 0.20}]}
            """)
        let point = try XCTUnwrap(resting(h))
        XCTAssertEqual(point.homeProb, 0.62)
    }

    /// No primary line to end on ⇒ nil, so the card keeps the page's point
    /// rather than the chart inventing one.
    func testNoPrimaryLineIsNoRestingPoint() throws {
        let h = try history(winProb: """
            {"kalshi": [{"timestamp": "2026-09-20T02:40:00Z", "home_probability": 0.20}]}
            """)
        XCTAssertNil(resting(h))
        XCTAssertNil(OddsChartView.restingPlayPoint(in: [], sportKey: nil))
    }

    /// The state printed beside the number is what was observed at THAT point:
    /// an ESPN row a minute after the line's last point belongs to no point on
    /// the line, so it must not dress the resting moment.
    func testGameStateComesFromTheRowAtThePointNotALaterOne() throws {
        let h = try history(
            status: "in_progress",
            // A blend is only read where a venue series is served beside it.
            winProb: """
            {"kalshi": [{"timestamp": "2026-09-20T02:05:00Z", "home_probability": 0.60}]}
            """,
            aggregate: """
            [{"timestamp": "2026-09-20T02:10:00Z", "home_probability": 0.64}]
            """,
            espn: """
            [{"timestamp": "2026-09-20T02:09:30Z", "home_score": 50, "away_score": 48,
              "period": "3", "game_clock": "4:12"},
             {"timestamp": "2026-09-20T02:14:00Z", "home_score": 55, "away_score": 48,
              "period": "3", "game_clock": "1:02"}]
            """)
        let point = try XCTUnwrap(resting(h))
        XCTAssertEqual(point.homeProb, 0.64)
        XCTAssertEqual(point.homeScore, 50)
        XCTAssertEqual(point.awayScore, 48)
        XCTAssertEqual(point.clock, "4:12")
    }

    /// #5271 holds on the resting moment: a draw-priced sport prints no away
    /// complement.
    func testADrawPricedSportPrintsNoAwayComplement() throws {
        let h = try history(
            winProb: """
            {"kalshi": [{"timestamp": "2026-09-20T02:05:00Z", "home_probability": 0.50}]}
            """,
            aggregate: """
            [{"timestamp": "2026-09-20T02:10:00Z", "home_probability": 0.48}]
            """)
        let point = try XCTUnwrap(resting(h, sport: "soccer_epl"))
        XCTAssertEqual(point.homeProb, 0.48)
        XCTAssertNil(point.awayProb)
    }

    /// The scrub and the resting moment are one read of one kind of point.
    func testTheRestingMomentReadsLikeAScrubToTheLinesEnd() throws {
        var end = ChartDataPoint(date: "2026-09-20T02:30:00Z".asDate!, probability: 0.2, source: "aggregate")
        end.homeScore = 70
        end.awayScore = 81
        end.period = "Final"
        let points = [
            ChartDataPoint(date: "2026-09-20T02:00:00Z".asDate!, probability: 0.5, source: "aggregate"),
            end,
            ChartDataPoint(date: "2026-09-20T02:31:00Z".asDate!, probability: 0.9, source: "kalshi"),
        ]
        let resting = try XCTUnwrap(OddsChartView.restingPlayPoint(in: points, sportKey: "basketball_wnba"))
        let scrubbed = OddsChartView.playPoint(for: end, sportKey: "basketball_wnba")
        XCTAssertEqual(resting.timestamp, scrubbed.timestamp)
        XCTAssertEqual(resting.homeProb, scrubbed.homeProb)
        XCTAssertEqual(resting.awayProb, scrubbed.awayProb)
        XCTAssertEqual(resting.homeScore, 70)
        XCTAssertEqual(resting.period, "Final")
    }

    /// The specimen's 03:38 minute carries the blend twice — 1%, then the
    /// served terminal 0%. The line is drawn in point order and ends on the
    /// second; so does the readout (the render of 15315984, clipped at 03:38
    /// by the page's window, printed 1% before this).
    func testATieOnTheLastStampRestsOnTheVertexDrawnLast() throws {
        let h = try specimen()
        let end = "2026-09-25T03:38:00Z".asDate!
        let windowed = try drawn(h).filter { $0.date <= end }
        let point = try XCTUnwrap(OddsChartView.restingPlayPoint(in: windowed, sportKey: "americanfootball_ncaaf"))
        XCTAssertEqual(point.homeProb, 0.0)
        XCTAssertEqual(point.homeScore, 17)
        XCTAssertEqual(point.awayScore, 34)
        XCTAssertEqual(point.period, "Final")
        // The drawn line's own last vertex in the primary series.
        let lastDrawn = try XCTUnwrap(windowed.last { $0.source == "aggregate" })
        XCTAssertEqual(lastDrawn.probability, 0.0)
    }

    /// `resting(on:)` replaces the page's point only with a real one.
    func testRestingOnNilKeepsThePagesPoint() {
        let page = GamePlayPoint(timestamp: "2026-09-20T02:40:00Z", homeProb: 0.31, awayProb: 0.69)
        let chart = GamePlayPoint(timestamp: "2026-09-20T02:30:00Z", homeProb: 0.0, awayProb: 1.0)
        let card = GamePlayCardView(homeTeam: "H", awayTeam: "A", lastPoint: page)
        XCTAssertEqual(card.resting(on: chart).lastPoint?.homeProb, 0.0)
        XCTAssertEqual(card.resting(on: nil).lastPoint?.homeProb, 0.31)
        XCTAssertNil(card.resting(on: chart).selectedPoint, "resting never becomes the scrubbed moment")
    }

    /// Both places the chart draws the readout rest it on the drawn points
    /// (`dataPoints`: after the finished-game clip and the window), not on the
    /// unclipped set a late post-game print lives in.
    func testBothReadoutSitesRestOnTheDrawnPoints() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/OddsChartView.swift")
        let chart = try String(contentsOf: url, encoding: .utf8)
        XCTAssertEqual(chart.components(
            separatedBy: "readout.resting(on: Self.restingPlayPoint(in: dataPoints, sportKey: sportKey))").count - 1, 2)
    }
}
