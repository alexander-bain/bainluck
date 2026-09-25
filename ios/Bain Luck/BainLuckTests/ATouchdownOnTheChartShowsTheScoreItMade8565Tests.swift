import Foundation
import XCTest
@testable import Bain_Luck

/// #8565 (iOS half) — a scoring play on the chart sits beside the score it
/// produced, not the score from before it.
///
/// Since #8501 the server stamps each scoring play at the FIRST served sighting
/// of its post-play score, across `espn_history` AND `score_history`.
/// `enrichWithGameState` forward-filled the score from ESPN rows only, and
/// attached a play to every price within 60 seconds EITHER side of its stamp.
/// Two ways the readout printed a touchdown beside the old score:
///
/// 1. The play was stamped from a `score_history` sighting ESPN had not yet
///    caught (15315984: the 17–34 touchdown at 03:28:17, ESPN uncaptured
///    between 03:27:17 and 03:31:17, so the 03:28 price read 17–27).
/// 2. A price in the minute BEFORE the stamp carried the play, beside the score
///    the play had not yet changed. The web builds minute-aligned points so it
///    never meets this; the phone plots raw snapshot times, so it does.
///
/// Specimen: the web's banked /history for 15315984 (read after #8501 went
/// live), shared rather than copied so the two platforms are graded on one
/// file: `frontend/__tests__/fixtures/chartReadoutScoreHistory8565.json`.
final class ATouchdownOnTheChartShowsTheScoreItMade8565Tests: XCTestCase {

    private func date(_ iso: String) -> Date { iso.asDate! }

    // MARK: - Harness

    private static var specimenURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .deletingLastPathComponent()      // ios
            .deletingLastPathComponent()      // repo root
            .appendingPathComponent("frontend/__tests__/fixtures/chartReadoutScoreHistory8565.json")
    }

    private struct Specimen {
        let history: EventHistoryResponse
        let prices: [ChartDataPoint]
    }

    /// The app's own decode (`APIClient`: snake_case → camelCase) over the
    /// banked rows. `includeScoreHistory: false` is the served payload with the
    /// one series the old enrichment ignored removed — the control.
    private func specimen(includeScoreHistory: Bool = true) throws -> Specimen {
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: Self.specimenURL)) as! [String: Any]
        var body: [String: Any] = [
            "event_id": raw["event_id"]!,
            "home_team": raw["home_team"]!,
            "away_team": raw["away_team"]!,
            "status": "completed",
            "history": [Any](),
            "espn_history": raw["espn_history"]!,
            "scoring_plays": raw["scoring_plays"]!,
        ]
        if includeScoreHistory { body["score_history"] = raw["score_history"]! }
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let history = try d.decode(EventHistoryResponse.self,
                                   from: JSONSerialization.data(withJSONObject: body))
        // The blend is the primary line the scrub reads (`nearestSnapshot`).
        let prices = (raw["price_minutes"] as! [String]).map {
            ChartDataPoint(date: date($0), probability: 0.5, source: "aggregate")
        }
        return Specimen(history: history, prices: prices)
    }

    private func history(espn: String = "[]", scores: String = "[]", plays: String = "[]") throws -> EventHistoryResponse {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventHistoryResponse.self, from: Data("""
        {"event_id": 1, "home_team": "Home", "away_team": "Away", "status": "in_progress",
         "history": [], "espn_history": \(espn), "score_history": \(scores), "scoring_plays": \(plays)}
        """.utf8))
    }

    private func prices(_ isos: [String]) -> [ChartDataPoint] {
        isos.map { ChartDataPoint(date: date($0), probability: 0.5, source: "aggregate") }
    }

    private func score(_ p: ChartDataPoint) -> String {
        guard let h = p.homeScore, let a = p.awayScore else { return "none" }
        return "\(h)–\(a)"
    }

    // MARK: - The specimen

    /// Every play reaches the chart, and every price that carries one reads
    /// the play's own score.
    func testEveryPlayOnTheSpecimenSitsBesideItsOwnScore() throws {
        let s = try specimen()
        let plays = s.history.scoringPlays ?? []
        XCTAssertEqual(plays.count, 9, "the banked specimen has nine scoring plays")

        let out = OddsChartView.enrichWithGameState(s.prices, history: s.history)
        var attached = Set<String>()
        for p in out {
            guard let play = p.scoringPlay else { continue }
            attached.insert(play.timestamp ?? "")
            XCTAssertEqual(score(p), "\(play.homeScore!)–\(play.awayScore!)",
                           "\(p.date): \(play.description ?? "") beside the wrong score")
        }
        XCTAssertEqual(attached.count, 9, "a play went missing from the chart")
    }

    /// Alex's reading: scrub to the touchdown that made it 17–34.
    func testTheSpecimensLastTouchdownReads17to34() throws {
        let s = try specimen()
        let out = OddsChartView.enrichWithGameState(s.prices, history: s.history)
        let at = try XCTUnwrap(OddsChartView.nearestSnapshot(to: date("2026-09-25T03:28:17Z"), in: out))
        XCTAssertEqual(at.scoringPlay?.awayScore, 34)
        XCTAssertEqual(score(at), "17–34")
        XCTAssertFalse(at.scoreApprox, "the 03:28:17 sighting is inside the 03:28 price's own minute")
    }

    /// CONTROL — the same rows without `score_history`: the fixture carries the
    /// defect, so the guard above is not green for want of one.
    func testWithoutScoreHistoryTheSpecimenPrintsTheMiss() throws {
        let s = try specimen(includeScoreHistory: false)
        let out = OddsChartView.enrichWithGameState(s.prices, history: s.history)
        let at = try XCTUnwrap(OddsChartView.nearestSnapshot(to: date("2026-09-25T03:28:17Z"), in: out))
        XCTAssertEqual(at.scoringPlay?.awayScore, 34)
        XCTAssertEqual(score(at), "17–27", "ESPN alone had not seen the touchdown at 03:28")
    }

    // MARK: - The score fold

    /// A score sighting is an observation of the SCORE only: it dates the score
    /// and leaves the period's age with the ESPN row that saw it.
    func testAScoreSightingDatesTheScoreAndNotThePeriod() throws {
        let h = try history(
            espn: """
            [{"timestamp": "2026-09-24T20:00:10+00:00", "period": "1st Quarter", "game_clock": "12:00",
              "home_score": 0, "away_score": 0}]
            """,
            scores: #"[{"timestamp": "2026-09-24T20:03:20+00:00", "home_score": 7, "away_score": 0}]"#)
        let out = OddsChartView.enrichWithGameState(prices(["2026-09-24T20:03:40+00:00"]), history: h)
        XCTAssertEqual(score(out[0]), "7–0")
        XCTAssertEqual(out[0].scoreObservedAt, date("2026-09-24T20:03:20+00:00"))
        XCTAssertFalse(out[0].scoreApprox)
        XCTAssertEqual(out[0].periodObservedAt, date("2026-09-24T20:00:10+00:00"))
        XCTAssertTrue(out[0].periodApprox)
    }

    /// A score sighting in a LATER minute does not reach an earlier price —
    /// the same cutoff an ESPN row obeys.
    func testAScoreSightingInALaterMinuteDoesNotReachAnEarlierPrice() throws {
        let h = try history(
            espn: #"[{"timestamp": "2026-09-24T20:00:10+00:00", "home_score": 0, "away_score": 0}]"#,
            scores: #"[{"timestamp": "2026-09-24T20:04:05+00:00", "home_score": 7, "away_score": 0}]"#)
        let out = OddsChartView.enrichWithGameState(prices(["2026-09-24T20:03:50+00:00"]), history: h)
        XCTAssertEqual(score(out[0]), "0–0")
    }

    /// Inside one minute the LATER observation wins, whichever series it came
    /// from; on an exact tie the ESPN row stands (the web's strict `>`).
    func testTheLaterObservationWinsAndAnESPNRowWinsATie() throws {
        let later = try history(
            espn: #"[{"timestamp": "2026-09-24T20:05:05+00:00", "home_score": 0, "away_score": 0}]"#,
            scores: #"[{"timestamp": "2026-09-24T20:05:17+00:00", "home_score": 7, "away_score": 0}]"#)
        XCTAssertEqual(score(OddsChartView.enrichWithGameState(
            prices(["2026-09-24T20:05:30+00:00"]), history: later)[0]), "7–0")

        let earlier = try history(
            espn: #"[{"timestamp": "2026-09-24T20:05:25+00:00", "home_score": 7, "away_score": 3}]"#,
            scores: #"[{"timestamp": "2026-09-24T20:05:17+00:00", "home_score": 7, "away_score": 0}]"#)
        XCTAssertEqual(score(OddsChartView.enrichWithGameState(
            prices(["2026-09-24T20:05:30+00:00"]), history: earlier)[0]), "7–3")

        let tie = try history(
            espn: #"[{"timestamp": "2026-09-24T20:05:17+00:00", "home_score": 7, "away_score": 3}]"#,
            scores: #"[{"timestamp": "2026-09-24T20:05:17+00:00", "home_score": 7, "away_score": 0}]"#)
        XCTAssertEqual(score(OddsChartView.enrichWithGameState(
            prices(["2026-09-24T20:05:30+00:00"]), history: tie)[0]), "7–3")
    }

    // MARK: - Where a play attaches

    private let touchdown = """
    [{"timestamp": "2026-09-24T20:05:20+00:00", "description": "J. Doe 12 yd pass", "type": "Touchdown",
      "home_score": 7, "away_score": 0, "period": "1", "clock": "9:02"}]
    """

    /// The phone plots raw snapshot times. A price 40 seconds BEFORE the stamp,
    /// in the previous minute, has not seen the play — it must not carry it
    /// beside 0–0. The price after the stamp carries it beside 7–0.
    func testAPriceInTheMinuteBeforeAPlayDoesNotCarryIt() throws {
        let h = try history(
            espn: #"[{"timestamp": "2026-09-24T20:00:10+00:00", "home_score": 0, "away_score": 0}]"#,
            scores: #"[{"timestamp": "2026-09-24T20:05:20+00:00", "home_score": 7, "away_score": 0}]"#,
            plays: touchdown)
        let out = OddsChartView.enrichWithGameState(
            prices(["2026-09-24T20:04:40+00:00", "2026-09-24T20:05:45+00:00"]), history: h)
        XCTAssertNil(out[0].scoringPlay, "20:04:40 is before the touchdown")
        XCTAssertEqual(score(out[0]), "0–0")
        XCTAssertEqual(out[1].scoringPlay?.type, "Touchdown")
        XCTAssertEqual(score(out[1]), "7–0")
    }

    /// Same minute as the stamp, a few seconds earlier: the chart's resolution
    /// is the minute, and the score fold already counts the sighting there.
    func testAPriceInThePlaysOwnMinuteCarriesItWithItsScore() throws {
        let h = try history(
            espn: #"[{"timestamp": "2026-09-24T20:00:10+00:00", "home_score": 0, "away_score": 0}]"#,
            scores: #"[{"timestamp": "2026-09-24T20:05:20+00:00", "home_score": 7, "away_score": 0}]"#,
            plays: touchdown)
        let out = OddsChartView.enrichWithGameState(prices(["2026-09-24T20:05:05+00:00"]), history: h)
        XCTAssertEqual(out[0].scoringPlay?.type, "Touchdown")
        XCTAssertEqual(score(out[0]), "7–0")
    }

    /// A price more than a minute after the stamp is ordinary line.
    func testAPriceAMinuteAfterThePlayDoesNotCarryIt() throws {
        let h = try history(
            scores: #"[{"timestamp": "2026-09-24T20:05:20+00:00", "home_score": 7, "away_score": 0}]"#,
            plays: touchdown)
        let out = OddsChartView.enrichWithGameState(
            prices(["2026-09-24T20:05:45+00:00", "2026-09-24T20:06:25+00:00"]), history: h)
        XCTAssertNotNil(out[0].scoringPlay)
        XCTAssertNil(out[1].scoringPlay)
    }

    /// Two plays a price has seen: it names the later one, whose score it holds.
    func testThePriceNamesTheLatestPlayItHasSeen() throws {
        let h = try history(
            scores: """
            [{"timestamp": "2026-09-24T20:05:05+00:00", "home_score": 7, "away_score": 0},
             {"timestamp": "2026-09-24T20:05:40+00:00", "home_score": 8, "away_score": 0}]
            """,
            plays: """
            [{"timestamp": "2026-09-24T20:05:05+00:00", "type": "Touchdown", "home_score": 7, "away_score": 0},
             {"timestamp": "2026-09-24T20:05:40+00:00", "type": "Extra Point Good", "home_score": 8, "away_score": 0}]
            """)
        let out = OddsChartView.enrichWithGameState(prices(["2026-09-24T20:05:50+00:00"]), history: h)
        XCTAssertEqual(out[0].scoringPlay?.type, "Extra Point Good")
        XCTAssertEqual(score(out[0]), "8–0")
    }

    /// The last thing the series saw: no price at or after the stamp's minute,
    /// so the marker falls back to the price just before rather than vanish
    /// (the web's `attachScoringPlays` fallback).
    func testAPlayNoLaterPriceSawKeepsItsMarker() throws {
        let h = try history(
            scores: #"[{"timestamp": "2026-09-24T20:05:20+00:00", "home_score": 7, "away_score": 0}]"#,
            plays: touchdown)
        let out = OddsChartView.enrichWithGameState(prices(["2026-09-24T20:04:40+00:00"]), history: h)
        XCTAssertEqual(out[0].scoringPlay?.type, "Touchdown")
    }

    /// The fallback is only for a play NO price saw: once a later price carries
    /// it, the earlier one stays clean (a fallback that ran for every play
    /// would restore the miss this ship removes).
    func testTheFallbackDoesNotFireForAPlayALaterPriceSaw() throws {
        let h = try history(
            scores: #"[{"timestamp": "2026-09-24T20:05:20+00:00", "home_score": 7, "away_score": 0}]"#,
            plays: touchdown)
        let out = OddsChartView.enrichWithGameState(
            prices(["2026-09-24T20:04:40+00:00", "2026-09-24T20:05:45+00:00"]), history: h)
        XCTAssertNil(out[0].scoringPlay)
        XCTAssertNotNil(out[1].scoringPlay)
    }
}
