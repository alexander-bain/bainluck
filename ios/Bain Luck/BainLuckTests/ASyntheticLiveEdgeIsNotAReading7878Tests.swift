import XCTest
@testable import Bain_Luck

/// #7547/#7878 D (codex 2026-09-23) — the backend's synthetic `live_edge` point
/// is a delivery time, not an observation, on the phone as on the web.
///
/// `_extend_win_prob_history_to_live_edge` appends ONE point per series at the
/// request's own "now", carrying the last real value, whenever that series has
/// been quiet 30 s or more on a live game. The phone decoded no `live_edge`
/// key, so that point was an ordinary reading: it seeded the series' cadence
/// and, after a long quiet, `observationSegments` split it off into a run of
/// one — which the chart draws as a lone mark at an instant nobody read.
///
/// The web keeps it for one job (`chartObservationSupport.ts`): the anchor of
/// the TRAILING interval. So does this. The controls are half the suite: a
/// short quiet still ends the line at "now", and a payload with no flag at all
/// segments exactly as before.
final class ASyntheticLiveEdgeIsNotAReading7878Tests: XCTestCase {

    private static let commence = Date(timeIntervalSince1970: 1_758_654_000)

    private func real(_ offsets: [TimeInterval], source: String = "kalshi") -> [ChartDataPoint] {
        offsets.map {
            ChartDataPoint(date: Self.commence.addingTimeInterval($0), probability: 0.4, source: source)
        }
    }

    private func edge(_ offset: TimeInterval, source: String = "kalshi") -> ChartDataPoint {
        var point = ChartDataPoint(date: Self.commence.addingTimeInterval(offset), probability: 0.4, source: source)
        point.isLiveEdge = true
        return point
    }

    private func decode(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    // MARK: - Decode

    /// The served key reaches the chart point; a row without it is a reading.
    func testTheServedFlagReachesTheChartPoint() throws {
        let history = try decode("""
        {
          "event_id": 15317706, "home_team": "Kicker", "away_team": "Dellien", "status": "live",
          "history": [],
          "win_prob_history": {"kalshi": [
            {"timestamp": "2026-09-23T21:40:00Z", "home_probability": 0.2},
            {"timestamp": "2026-09-23T22:20:00Z", "home_probability": 0.2, "live_edge": true}
          ]}
        }
        """)

        let points = OddsChartView.chartPoints(from: history).filter { $0.source == "kalshi" }
            .sorted { $0.date < $1.date }

        XCTAssertEqual(points.map(\.isLiveEdge), [false, true])
    }

    /// An older payload with no key decodes, and nothing is synthetic.
    func testAPayloadWithoutTheKeyHasNoSyntheticPoint() throws {
        let history = try decode("""
        {
          "event_id": 1, "home_team": "A", "away_team": "B", "status": "live", "history": [],
          "win_prob_history": {"kalshi": [{"timestamp": "2026-09-23T21:40:00Z", "home_probability": 0.2}]}
        }
        """)

        XCTAssertFalse(OddsChartView.chartPoints(from: history).contains(where: \.isLiveEdge))
    }

    // MARK: - The defect

    /// Twenty readings two minutes apart, then 40 quiet minutes and the edge.
    ///
    /// Before: the 40-minute interval clears both the 600 s floor and 15× the
    /// 120 s cadence, so the edge came back as its own run — a lone mark at
    /// "now". After: the line ends at the last real reading and nothing is
    /// drawn after it.
    func testALongQuietDoesNotLeaveAMarkAtNow() {
        let readings = real(stride(from: 60.0, through: 60 + 19 * 120, by: 120).map { $0 })
        let lastReal = readings.last!.date
        let segments = OddsChartView.observationSegments(
            readings + [edge(60 + 19 * 120 + 2_400)], gameStart: Self.commence)

        XCTAssertEqual(segments.count, 1, "the quiet is trailing: nothing resumes after it")
        XCTAssertFalse(segments.contains { $0.count == 1 && $0[0].isLiveEdge },
                       "a synthetic point is never a run of its own")
        XCTAssertFalse(segments.joined().contains(where: \.isLiveEdge),
                       "an unsupported trailing interval draws nothing past the last reading")
        XCTAssertEqual(segments.last?.last?.date, lastReal)
    }

    /// The edge does not seed the cadence it is judged by.
    ///
    /// Real intervals 100 s and 2,000 s: the series' own median is 2,000 s, so
    /// its 2,000 s interval is its rhythm and stays joined. Counting the
    /// edge's 100 s as a third interval drags the median to 100 s and splits a
    /// line nobody stopped watching.
    func testTheEdgeDoesNotSeedTheCadence() {
        let readings = real([60, 160, 2_160])
        let segments = OddsChartView.observationSegments(
            readings + [edge(2_260)], gameStart: Self.commence)

        XCTAssertEqual(segments.count, 1, "judged on its own rhythm the series has no hole")
        XCTAssertEqual(segments[0].count, 4, "a 100 s trailing interval is supported: the line reaches now")
        XCTAssertEqual(segments[0].last?.isLiveEdge, true)
    }

    /// Only the edge survived the window (Since Start, one reading ago): no mark.
    func testALoneEdgeDrawsNothing() {
        XCTAssertTrue(OddsChartView.observationSegments([edge(900)], gameStart: Self.commence).isEmpty)
    }

    // MARK: - Controls

    /// A short quiet on a healthy series still carries the line to now.
    func testAShortQuietStillReachesNow() {
        let readings = real([60, 180, 300, 420])
        let segments = OddsChartView.observationSegments(
            readings + [edge(600)], gameStart: Self.commence)

        XCTAssertEqual(segments.count, 1)
        XCTAssertEqual(segments[0].count, 5)
        XCTAssertEqual(segments[0].last?.isLiveEdge, true)
    }

    /// No commence ⇒ nothing is judged, the edge included (as before).
    func testNoGameStartJudgesNothing() {
        let readings = real([60, 180])
        let segments = OddsChartView.observationSegments(readings + [edge(9_000)], gameStart: nil)

        XCTAssertEqual(segments.map(\.count), [3])
    }

    /// An interior hole still breaks, and the edge after it still follows the
    /// trailing rule — the two judgements are independent.
    func testAnInteriorHoleStillBreaksWithAnEdgePresent() {
        let readings = real([60, 180, 300, 420, 540, 12_000, 12_120])
        let segments = OddsChartView.observationSegments(
            readings + [edge(12_200)], gameStart: Self.commence)

        XCTAssertEqual(segments.map(\.count), [5, 3])
        XCTAssertEqual(segments.last?.last?.isLiveEdge, true)
    }

    // MARK: - Score Differential

    /// The edge re-serves the last row's score at "now"; that is no score anyone saw then.
    func testScoreDifferentialTakesNoScoreFromTheEdge() throws {
        let history = try decode("""
        {
          "event_id": 1, "home_team": "A", "away_team": "B", "status": "live", "history": [],
          "win_prob_history": {"espn": [
            {"timestamp": "2026-09-23T21:40:00Z", "home_probability": 0.6,
             "game_state": {"period": "Q2", "home_score": 14, "away_score": 7}},
            {"timestamp": "2026-09-23T22:20:00Z", "home_probability": 0.6, "live_edge": true,
             "game_state": {"period": "Q2", "home_score": 14, "away_score": 7}}
          ]}
        }
        """)

        let diffs = ScoreDifferentialChartView.winProbStateScoreDiffs(history: history, since: nil)

        XCTAssertEqual(diffs.count, 1, "only the real row is an actual score")
        XCTAssertEqual(diffs.values.first?.date, "2026-09-23T21:40:00Z".asDate)
    }
}
