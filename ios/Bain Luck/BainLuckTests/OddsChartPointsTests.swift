import XCTest
@testable import Bain_Luck

/// L2-196 / C43 — the native win-probability chart must show the OBSERVED journey
/// and nothing else. These pin the pure `OddsChartView.chartPoints(from:)` transform
/// (SwiftUI bodies aren't rendered in tests) against the three confirmed defects:
///
///  1. **No client aggregation.** The only "aggregate" (Bain Luck blend) source is
///     the backend's canonical weighted line. When it is missing we fail closed —
///     never a locally reconstructed arithmetic mean labelled as the blend.
///  2. **No shape guessing.** Every backend-valid probability survives; legitimate
///     ~50% observations (real even-game crossings) are retained, not deleted.
///  3. Rendering connects these points with straight segments (`.linear`), so the
///     data layer inserts no synthetic intermediate points — count is conserved.
final class OddsChartPointsTests: XCTestCase {

    private func history(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    /// Points for one chart source, sorted by time, as (probability) values.
    private func probs(_ points: [ChartDataPoint], source: String) -> [Double] {
        points.filter { $0.source == source }
            .sorted { $0.date < $1.date }
            .map(\.probability)
    }

    // MARK: - No smoothing / sparse jump (data-level: nothing invented)

    func testSparseJumpKeepsExactlyTheObservedPoints() throws {
        // Two consensus snapshots 30 min apart with a large jump. The transform must
        // return exactly those two points — no bucketed/interpolated midpoint. The
        // linear render then draws a straight segment between them (no invented curve).
        let h = try history("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.35},
            {"timestamp": "2026-07-27T12:30:00Z", "home_probability": 0.82}
          ]
        }
        """)
        let points = OddsChartView.chartPoints(from: h)
        XCTAssertEqual(probs(points, source: "consensus"), [0.35, 0.82])
        XCTAssertTrue(points.allSatisfy { $0.source == "consensus" }, "no aggregate synthesized in sportsbooks-only mode")
    }

    // MARK: - Real 50/50 crossing is retained (was deleted)

    func testRealFiftyFiftyCrossingIsRetained() throws {
        // espn swings 0.80 → 0.50 → 0.20. The old heuristic deleted the 0.50 point
        // (|prev-0.5|>0.15 and |prob-0.5|<0.02), erasing a genuine even-game crossing.
        let h = try history("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [],
          "win_prob_history": {
            "espn": [
              {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.80},
              {"timestamp": "2026-07-27T12:05:00Z", "home_probability": 0.50},
              {"timestamp": "2026-07-27T12:10:00Z", "home_probability": 0.20}
            ]
          }
        }
        """)
        let espn = probs(OddsChartView.chartPoints(from: h), source: "espn")
        XCTAssertEqual(espn, [0.80, 0.50, 0.20], "the real 0.50 crossing must survive")
    }

    func testTieCapableEventKeepsClusteredFiftyPoints() throws {
        // A draw-capable (soccer-style) event hovering near 0.50 must keep every
        // near-even reading — none is a placeholder to strip.
        let h = try history("""
        {
          "event_id": 2, "home_team": "H", "away_team": "A",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.49},
              {"timestamp": "2026-07-27T12:05:00Z", "home_probability": 0.50},
              {"timestamp": "2026-07-27T12:10:00Z", "home_probability": 0.51}
            ]
          }
        }
        """)
        XCTAssertEqual(probs(OddsChartView.chartPoints(from: h), source: "kalshi"), [0.49, 0.50, 0.51])
    }

    // MARK: - Aggregate is backend-only; client mean is never labelled the blend

    func testAggregateUsesBackendLineNotArithmeticMean() throws {
        // Sources average to 0.60 ((0.90+0.30)/2) at 12:00, but the backend weighted
        // aggregate is 0.85. The chart's "aggregate" MUST equal the backend line, not
        // the arithmetic mean the old fallback would have produced.
        let h = try history("""
        {
          "event_id": 3, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.90}
          ],
          "win_prob_history": {
            "polymarket": [
              {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.30}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.85, "away_probability": 0.15}
          ]
        }
        """)
        let agg = probs(OddsChartView.chartPoints(from: h), source: "aggregate")
        XCTAssertEqual(agg, [0.85], "aggregate is the backend weighted line")
        XCTAssertNotEqual(agg, [0.60], "must NOT be the client arithmetic mean")
    }

    func testMissingAggregateFailsClosedNoClientMean() throws {
        // Multi-source, but the backend aggregate is absent. We must NOT synthesize
        // an "aggregate" source: consensus stays the primary line instead.
        let h = try history("""
        {
          "event_id": 4, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.70}
          ],
          "win_prob_history": {
            "espn": [
              {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.40}
            ]
          }
        }
        """)
        let points = OddsChartView.chartPoints(from: h)
        XCTAssertTrue(points.filter { $0.source == "aggregate" }.isEmpty,
                      "no aggregate line → fail closed, no client mean")
        XCTAssertEqual(probs(points, source: "consensus"), [0.70])
        XCTAssertEqual(probs(points, source: "espn"), [0.40])
    }

    func testEmptyAggregateLineIsTreatedAsMissing() throws {
        let h = try history("""
        {
          "event_id": 5, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.55}],
          "win_prob_history": {"espn": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.45}]},
          "aggregate_line": []
        }
        """)
        XCTAssertTrue(OddsChartView.chartPoints(from: h).filter { $0.source == "aggregate" }.isEmpty)
    }

    // MARK: - Terminal 100/0 and lifecycle edges

    func testTerminalOneZeroAggregateIsRetained() throws {
        // A settled game's final aggregate point (1.0) must survive as the terminal
        // point — "settled means settled", the completed journey ends at the result.
        let h = try history("""
        {
          "event_id": 6, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.60}],
          "win_prob_history": {"espn": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.62}]},
          "aggregate_line": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.60, "away_probability": 0.40},
            {"timestamp": "2026-07-27T14:00:00Z", "home_probability": 1.0, "away_probability": 0.0}
          ]
        }
        """)
        XCTAssertEqual(probs(OddsChartView.chartPoints(from: h), source: "aggregate"), [0.60, 1.0])
    }

    func testMissingScoreStillBuildsProbabilityPoints() throws {
        // No game_state / scores anywhere — probability points still build (score is
        // separate enrichment, not a prerequisite for the chart).
        let h = try history("""
        {
          "event_id": 7, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.55},
            {"timestamp": "2026-07-27T12:05:00Z", "home_probability": 0.58}
          ]
        }
        """)
        XCTAssertEqual(probs(OddsChartView.chartPoints(from: h), source: "consensus"), [0.55, 0.58])
    }

    func testLateFinalSnapshotIsIncludedByTheTransform() throws {
        // A late post-buzzer aggregate snapshot is returned by the transform; any
        // completed-domain clipping is a separate concern (filterPoints), so the
        // truth transform itself never drops it.
        let h = try history("""
        {
          "event_id": 8, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.50}],
          "win_prob_history": {"espn": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.50}]},
          "aggregate_line": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.50, "away_probability": 0.50},
            {"timestamp": "2026-07-27T15:30:00Z", "home_probability": 1.0, "away_probability": 0.0}
          ]
        }
        """)
        XCTAssertEqual(probs(OddsChartView.chartPoints(from: h), source: "aggregate").count, 2)
    }

    // MARK: - Skipped/malformed observations

    func testNilProbabilitiesAreSkippedNotZeroed() throws {
        let h = try history("""
        {
          "event_id": 9, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.60},
            {"timestamp": "2026-07-27T12:05:00Z", "home_probability": null}
          ]
        }
        """)
        XCTAssertEqual(probs(OddsChartView.chartPoints(from: h), source: "consensus"), [0.60],
                       "a null probability is skipped, never coerced to 0")
    }
}
