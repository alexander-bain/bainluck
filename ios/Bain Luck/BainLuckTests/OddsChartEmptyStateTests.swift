import XCTest
@testable import Bain_Luck

/// #3278 — a live match in its first minutes drew an EMPTY win-probability chart:
/// the full frame (both rotated player labels, the 0/25/50/75/100% gridlines, the
/// legend) around no line at all.
///
/// The cause was a branch that asked the wrong question. `OddsChartView` tested
/// `dataPoints.isEmpty` to decide whether to say something instead of drawing, but
/// "not empty" is not "drawable": a `LineMark` needs TWO points in ONE series, and
/// Swiatek–Bouzkova five minutes after the first ball had exactly one snapshot
/// inside the "Since Start" window. One point is not empty, so the frame rendered.
///
/// These pin the two pure functions that replaced that test — the drawability rule
/// and the sentence. The LAYOUT half of the claim (a sentence where the frame used
/// to be) cannot be asserted here and is photographed in
/// `OddsChartEmptyStateRenderSmokeTests`.
final class OddsChartEmptyStateTests: XCTestCase {

    private func point(_ source: String, _ minute: Int, _ probability: Double = 0.6) -> ChartDataPoint {
        ChartDataPoint(
            date: Date(timeIntervalSince1970: 1_757_000_000 + Double(minute) * 60),
            probability: probability,
            source: source
        )
    }

    private func history(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    // MARK: - Drawability

    func testOnePointDrawsNoLine() {
        // THE #3278 CASE. One snapshot since the first ball. Not empty, not drawable.
        XCTAssertFalse(OddsChartView.hasDrawableLine(in: [point("consensus", 0)]))
    }

    func testNoPointsDrawsNoLine() {
        XCTAssertFalse(OddsChartView.hasDrawableLine(in: []))
    }

    func testTwoPointsInOneSeriesDrawsALine() {
        XCTAssertTrue(OddsChartView.hasDrawableLine(in: [point("consensus", 0), point("consensus", 5)]))
    }

    func testTwoSourcesHoldingOnePointEachDrawNoLine() {
        // The trap a total-count test (`count >= 2`) falls into: two points, two
        // series, no line — the identical empty frame #3278 reported. Drawability is
        // per series because `chartContent` draws one series per visible source.
        let points = [point("consensus", 0), point("espn", 0)]
        XCTAssertEqual(points.count, 2, "precondition: a count test would call this drawable")
        XCTAssertFalse(OddsChartView.hasDrawableLine(in: points))
    }

    func testALonelyBlendHidesARichConsensus() {
        // "The blend is the product": when an aggregate point exists it is the ONLY
        // visible source, so a one-point blend draws nothing however many consensus
        // snapshots sit behind it. Drawability must read the VISIBLE set, not all
        // points — otherwise the frame renders around an invisible line again.
        let points = [point("aggregate", 3)] + (0..<20).map { point("consensus", $0) }
        XCTAssertEqual(OddsChartView.defaultVisibleSources(in: points), ["aggregate"])
        XCTAssertFalse(OddsChartView.hasDrawableLine(in: points))
    }

    func testTwoBlendPointsDrawALine() {
        let points = [point("aggregate", 3), point("aggregate", 9), point("consensus", 0)]
        XCTAssertTrue(OddsChartView.hasDrawableLine(in: points))
    }

    // MARK: - The production payload that reported the bug

    func testSwiatekBouzkovaFirstMinutesIsNotDrawable() throws {
        // Measured on 15302923 at 2026-09-05 ~11:00am PT and quoted in #3278:
        // commence_time 17:55:03Z, one snapshot at 17:58Z since that instant, an
        // empty aggregate_line. Replayed through the real decode + transform.
        let h = try history("""
        {
          "event_id": 15302923, "home_team": "Iga Swiatek", "away_team": "Marie Bouzkova",
          "history": [
            {"timestamp": "2026-09-05T17:58:00Z", "home_probability": 0.88}
          ],
          "aggregate_line": []
        }
        """)
        let points = OddsChartView.chartPoints(from: h)
        XCTAssertFalse(points.isEmpty, "precondition: the old isEmpty branch did NOT fire here")
        XCTAssertFalse(OddsChartView.hasDrawableLine(in: points))
    }

    func testSameMatchOnceASecondReadingLandsIsDrawable() throws {
        // The state the page reaches a poll later — the chart must come back on its
        // own, with no range change and no reload.
        let h = try history("""
        {
          "event_id": 15302923, "home_team": "Iga Swiatek", "away_team": "Marie Bouzkova",
          "history": [
            {"timestamp": "2026-09-05T17:58:00Z", "home_probability": 0.88},
            {"timestamp": "2026-09-05T18:03:00Z", "home_probability": 0.91}
          ]
        }
        """)
        XCTAssertTrue(OddsChartView.hasDrawableLine(in: OddsChartView.chartPoints(from: h)))
    }

    // MARK: - What it says instead

    func testSinceStartWithNothingYetSaysSoAndOffersAll() {
        let message = OddsChartView.emptyChartMessage(
            range: .sinceStart, hasAnyPointInRange: false, allIsDrawable: true
        )
        XCTAssertEqual(message, "No readings since the start yet. Switch to All for the pre-match market.")
    }

    func testSinceStartWithOneReadingNamesTheReasonAndOffersAll() {
        let message = OddsChartView.emptyChartMessage(
            range: .sinceStart, hasAnyPointInRange: true, allIsDrawable: true
        )
        XCTAssertEqual(
            message,
            "Not enough readings since the start to draw a line yet. Switch to All for the pre-match market."
        )
    }

    func testNeverPointsAtAllWhenAllIsAlsoEmpty() {
        // The suggestion must never send a reader to a SECOND empty frame. This is
        // why the caller passes drawability of the UNFILTERED points rather than a
        // guess that pre-match data usually exists.
        for hasAnyPointInRange in [true, false] {
            let message = OddsChartView.emptyChartMessage(
                range: .sinceStart, hasAnyPointInRange: hasAnyPointInRange, allIsDrawable: false
            )
            XCTAssertFalse(message.contains("Switch to All"), "offered All with nothing to show there")
            XCTAssertFalse(message.isEmpty)
        }
    }

    func testAllRangeWithNoDataKeepsTheOriginalSentence() {
        // The genuinely-no-data case is unchanged: no range to fall back to, so no
        // suggestion, and the copy readers already see stays put.
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(range: .all, hasAnyPointInRange: false, allIsDrawable: false),
            "No probability data available"
        )
    }

    func testAllRangeWithOneReadingNamesTheReason() {
        XCTAssertEqual(
            OddsChartView.emptyChartMessage(range: .all, hasAnyPointInRange: true, allIsDrawable: true),
            "Not enough readings yet to draw a line."
        )
    }

    func testNoMessageEverPointsAtTheRangeAlreadySelected() {
        // A suggestion to switch to the segment that is already active would be the
        // empty frame with extra words.
        let message = OddsChartView.emptyChartMessage(
            range: .all, hasAnyPointInRange: true, allIsDrawable: true
        )
        XCTAssertFalse(message.contains("Switch to All"))
    }
}
