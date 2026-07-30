import XCTest
@testable import Bain_Luck

/// L2-216 — the native win-probability chart must speak the SAME single 0–100
/// blended-probability language as the web/product contract:
///  • one primary line = the backend blend when present (the only default line),
///    else fail closed to the sportsbook consensus;
///  • a fixed, plainly labeled 0–100 axis — no mirrored ±50 delta where "80%"
///    appeared above AND below center;
///  • scrub reports the EXACT blended probability at the nearest REAL snapshot,
///    never an interpolated value;
///  • axis labels, plotted coordinates, scrub values, and accessibility text all
///    report the same probability basis.
/// These pin the pure statics on `OddsChartView` (SwiftUI bodies aren't rendered
/// in tests).
final class OddsChartAxisTests: XCTestCase {

    private func history(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func pt(_ t: Double, _ p: Double, _ src: String,
                    home: Int? = nil, away: Int? = nil,
                    period: String? = nil, clock: String? = nil) -> ChartDataPoint {
        ChartDataPoint(date: Date(timeIntervalSince1970: t), probability: p, source: src,
                       homeScore: home, awayScore: away, period: period, clock: clock)
    }

    // MARK: - Single 0–100 axis (no mirroring)

    func testYAxisTicksSpanZeroToOne() {
        XCTAssertEqual(OddsChartView.yAxisTicks, [0, 0.25, 0.5, 0.75, 1.0])
        XCTAssertEqual(OddsChartView.yAxisTicks.min(), 0.0)
        XCTAssertEqual(OddsChartView.yAxisTicks.max(), 1.0)
    }

    func testAxisLabelIsStraightPercentNotMirrored() {
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.0), "0%")
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.25), "25%")
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.5), "50%")
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.75), "75%")
        XCTAssertEqual(OddsChartView.axisLabel(for: 1.0), "100%")
        // The defining property of the de-mirrored axis: 20% and 80% are distinct
        // labels. The old ±50 delta axis rendered both as the same reading.
        XCTAssertNotEqual(OddsChartView.axisLabel(for: 0.2), OddsChartView.axisLabel(for: 0.8))
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.2), "20%")
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.8), "80%")
    }

    func testAxisLabelEdgesAndNinetyNine() {
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.99), "99%")
        XCTAssertEqual(OddsChartView.axisLabel(for: 0.01), "1%")
    }

    // MARK: - One primary blend; source detail never competes

    func testAggregatePlusSourcesShowsBlendOnly() throws {
        let h = try history("""
        {
          "event_id": 1, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.90}],
          "win_prob_history": {
            "espn": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.40}],
            "kalshi": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.55}]
          },
          "aggregate_line": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.72, "away_probability": 0.28}
          ]
        }
        """)
        let points = OddsChartView.chartPoints(from: h)
        XCTAssertEqual(OddsChartView.defaultVisibleSources(in: points), ["aggregate"],
                       "when the blend exists it is the ONLY default line")
        XCTAssertEqual(OddsChartView.primarySource(in: points), "aggregate")
    }

    func testMissingAggregateFailsClosedToFullSetWithConsensus() throws {
        let h = try history("""
        {
          "event_id": 2, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.70}],
          "win_prob_history": {
            "espn": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.40}]
          }
        }
        """)
        let points = OddsChartView.chartPoints(from: h)
        let visible = OddsChartView.defaultVisibleSources(in: points)
        XCTAssertTrue(visible.contains("consensus"))
        XCTAssertTrue(visible.contains("espn"))
        XCTAssertFalse(visible.contains("aggregate"), "no client-synthesized blend")
        XCTAssertEqual(OddsChartView.primarySource(in: points), "consensus")
    }

    func testOneSourceFallbackIsConsensusOnly() throws {
        let h = try history("""
        {
          "event_id": 3, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.55},
            {"timestamp": "2026-07-27T12:05:00Z", "home_probability": 0.58}
          ]
        }
        """)
        let points = OddsChartView.chartPoints(from: h)
        XCTAssertEqual(OddsChartView.defaultVisibleSources(in: points), ["consensus"])
        XCTAssertEqual(OddsChartView.primarySource(in: points), "consensus")
    }

    // MARK: - Plotted coordinate basis (probability, not delta)

    func testPlottedProbabilitiesAreRawAcrossTheFullRange() throws {
        // 0%, a lead change, and 99% must survive verbatim as the plotted value —
        // the coordinate IS the probability, so no delta/offset is applied.
        let h = try history("""
        {
          "event_id": 4, "home_team": "H", "away_team": "A",
          "history": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.0},
            {"timestamp": "2026-07-27T12:05:00Z", "home_probability": 0.35},
            {"timestamp": "2026-07-27T12:10:00Z", "home_probability": 0.65},
            {"timestamp": "2026-07-27T12:15:00Z", "home_probability": 0.99}
          ]
        }
        """)
        let consensus = OddsChartView.chartPoints(from: h)
            .filter { $0.source == "consensus" }
            .sorted { $0.date < $1.date }
            .map(\.probability)
        XCTAssertEqual(consensus, [0.0, 0.35, 0.65, 0.99])
    }

    // MARK: - Scrub truth: nearest REAL snapshot, never interpolated

    func testNearestSnapshotReturnsExactRealPointNotInterpolated() {
        let points = [pt(1000, 0.35, "consensus"), pt(2800, 0.82, "consensus")]
        // Scrub closer to the second point (t=2500 of 1000…2800).
        let n = OddsChartView.nearestSnapshot(to: Date(timeIntervalSince1970: 2500), in: points)
        XCTAssertEqual(n?.probability, 0.82, "returns the real snapshot, not an interpolated midpoint")
        XCTAssertEqual(n?.date, Date(timeIntervalSince1970: 2800))
    }

    func testNearestSnapshotUsesTheBlendLineWhenPresent() {
        // Blend and a divergent source at the same instant: scrub reads the BLEND.
        let points = [pt(1000, 0.72, "aggregate"), pt(1000, 0.40, "espn")]
        let n = OddsChartView.nearestSnapshot(to: Date(timeIntervalSince1970: 1000), in: points)
        XCTAssertEqual(n?.source, "aggregate")
        XCTAssertEqual(n?.probability, 0.72)
    }

    func testNearestSnapshotEmptyIsNil() {
        XCTAssertNil(OddsChartView.nearestSnapshot(to: Date(timeIntervalSince1970: 0), in: []))
    }

    func testNearestSnapshotOnePointReturnsThatPoint() {
        let points = [pt(1000, 0.61, "consensus")]
        let n = OddsChartView.nearestSnapshot(to: Date(timeIntervalSince1970: 99999), in: points)
        XCTAssertEqual(n?.probability, 0.61)
    }

    // MARK: - Read-out / accessibility share the axis basis

    func testSelectionReadoutUsesHomeAwayPercent() {
        let p = pt(1000, 0.62, "aggregate", home: 3, away: 1, period: "Q3", clock: "5:12")
        let r = OddsChartView.selectionReadout(for: p, homeShort: "BOS", awayShort: "NYY")
        XCTAssertTrue(r.contains("BOS 62%"), r)
        XCTAssertTrue(r.contains("NYY 38%"), r)
        XCTAssertTrue(r.contains("score 3–1"), r)
        XCTAssertTrue(r.contains("Q3"), r)
        XCTAssertTrue(r.contains("5:12"), r)
    }

    func testReadoutEdgesLeadChangeAndTerminal() {
        let zero = OddsChartView.selectionReadout(for: pt(1, 0.0, "aggregate"), homeShort: "H", awayShort: "A")
        XCTAssertTrue(zero.contains("H 0%") && zero.contains("A 100%"), zero)
        let terminal = OddsChartView.selectionReadout(for: pt(1, 1.0, "aggregate"), homeShort: "H", awayShort: "A")
        XCTAssertTrue(terminal.contains("H 100%") && terminal.contains("A 0%"), terminal)
    }

    func testAccessibilityValueMatchesAxisLabelBasis() throws {
        // Completed game: aggregate ends at 1.0. Resting (no scrub) read-out reports
        // the latest blend snapshot, in the same % basis as the axis label.
        let h = try history("""
        {
          "event_id": 5, "home_team": "H", "away_team": "A",
          "history": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.60}],
          "win_prob_history": {"espn": [{"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.62}]},
          "aggregate_line": [
            {"timestamp": "2026-07-27T12:00:00Z", "home_probability": 0.60, "away_probability": 0.40},
            {"timestamp": "2026-07-27T14:00:00Z", "home_probability": 1.0, "away_probability": 0.0}
          ]
        }
        """)
        let points = OddsChartView.chartPoints(from: h)
        let value = OddsChartView.accessibilityValue(dataPoints: points, selectedDate: nil,
                                                     homeShort: "H", awayShort: "A")
        XCTAssertTrue(value.contains("H 100%"), value)
        XCTAssertTrue(value.contains("A 0%"), value)
        // Same basis as the axis: the latest blend is 1.0 → "100%".
        XCTAssertTrue(value.contains(OddsChartView.axisLabel(for: 1.0)), value)
    }

    func testAccessibilityValueEmptyIsSafe() {
        let value = OddsChartView.accessibilityValue(dataPoints: [], selectedDate: nil,
                                                     homeShort: "H", awayShort: "A")
        XCTAssertEqual(value, "No probability data")
    }
}
