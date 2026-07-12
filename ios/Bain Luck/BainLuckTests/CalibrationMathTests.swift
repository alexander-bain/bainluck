import XCTest
@testable import Bain_Luck

/// #894 (L2-82): verifies the native calibration tab decodes payload v2 and that
/// `CalibrationMath` reproduces the web page's numbers exactly (the native-vs-web
/// parity fix). Every expected value below was cross-computed independently from
/// the web's `frontend/lib/calibrationMath.ts` math on the same fixture, so a
/// regression in either the port or the rounding fails this suite.
///
/// NOTE: this file is NOT yet wired into an Xcode target — the project currently
/// has no unit-test bundle (see BainLuckTests/README.md). Once a `Bain LuckTests`
/// target exists and includes this file, `xcodebuild test` runs it as-is.
final class CalibrationMathTests: XCTestCase {

    // A deterministic payload-v2-shaped fixture with hand-verifiable math:
    // well-traded cohort = price_moved != false (buckets 1, 2, 4); the unchanged
    // cohort is bucket 3. snake_case keys + .convertFromSnakeCase, exactly like
    // the app's APIClient.
    private let sampleJSON = """
    {
      "buckets": [
        {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
        {"bucket_idx": 7, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 100, "winners": 70, "avg_prob": 0.75, "sum_prob": 75.0, "sum_sq_err": 22.0, "ci_lower": 0.60, "ci_upper": 0.79},
        {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": false, "n": 50, "winners": 20, "avg_prob": 0.55, "sum_prob": 27.5, "sum_sq_err": 12.0, "ci_lower": 0.27, "ci_upper": 0.54},
        {"bucket_idx": 2, "source": "odds_api", "category": "baseball_mlb", "price_moved": null, "n": 400, "winners": 100, "avg_prob": 0.25, "sum_prob": 100.0, "sum_sq_err": 80.0, "ci_lower": 0.21, "ci_upper": 0.29}
      ],
      "total_markets": 12,
      "total_outcomes": 750,
      "total_winners": 250,
      "mce_ci_lower": 0.6,
      "mce_ci_upper": 1.7,
      "mce_closing_line": 1.5,
      "mce_opening_price": 2.2,
      "generated_at": "2026-07-12T01:00:00+00:00",
      "min_category_outcomes": 1000,
      "small_sample_categories": [
        {"category": "cricket_ipl", "outcomes": 949},
        {"category": "esports", "outcomes": 500}
      ],
      "corrections": [
        {"date": "2026-07-09", "title": "Polymarket hockey sign-flip", "rows": 36207, "description": "Re-graded."},
        {"date": "2026-07-08", "title": "DataGolf survivorship", "rows": null, "description": "Excluded DNPs."}
      ],
      "date_range": {"start": "2021-07-13T00:00:00+00:00", "end": "2026-07-12T00:05:00+00:00"}
    }
    """

    private func decode() throws -> CalibrationData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(CalibrationData.self, from: Data(sampleJSON.utf8))
    }

    private let wellTraded: (CalibrationBucket) -> Bool = { $0.priceMoved != false }

    // MARK: - Payload v2 decode

    func testDecodesPayloadV2Fields() throws {
        let cd = try decode()
        XCTAssertEqual(cd.buckets.count, 4)
        XCTAssertEqual(cd.totalOutcomes, 750)
        XCTAssertEqual(cd.minCategoryOutcomes, 1000)
        XCTAssertEqual(cd.smallSampleCategories?.count, 2)
        XCTAssertEqual(cd.smallSampleCategories?.first?.category, "cricket_ipl")
        XCTAssertEqual(cd.corrections?.count, 2)
        XCTAssertEqual(cd.dateRange?.start, "2021-07-13T00:00:00+00:00")
        // null price_moved and null rows must decode to nil, not crash.
        XCTAssertNil(cd.buckets[3].priceMoved)
        XCTAssertEqual(cd.corrections?[0].rows, 36207)
        XCTAssertNil(cd.corrections?[1].rows)
    }

    // MARK: - Web-parity math (values cross-computed from calibrationMath.ts)

    func testWellTradedCohort() throws {
        let cd = try decode()
        let agg = CalibrationMath.aggregate(cd.buckets, filter: wellTraded)
        XCTAssertEqual(CalibrationMath.ece(agg), 2.1714, accuracy: 0.001)   // n-weighted headline
        XCTAssertEqual(CalibrationMath.mce(agg), 3.35, accuracy: 0.001)     // equal-weighted worst-bucket
        XCTAssertEqual(CalibrationMath.brier(cd.buckets, filter: wellTraded), 0.208571, accuracy: 0.0001)
        XCTAssertEqual(CalibrationMath.totalN(cd.buckets, filter: wellTraded), 700)
    }

    func testAllCohort() throws {
        let cd = try decode()
        let agg = CalibrationMath.aggregate(cd.buckets)
        XCTAssertEqual(CalibrationMath.ece(agg), 3.0267, accuracy: 0.001)
        XCTAssertEqual(CalibrationMath.mce(agg), 7.2333, accuracy: 0.001)
        XCTAssertEqual(CalibrationMath.totalN(cd.buckets), 750)
    }

    func testTradingActivitySplit() throws {
        let cd = try decode()
        let moved = CalibrationMath.aggregate(cd.buckets) { $0.priceMoved == true }
        let unchanged = CalibrationMath.aggregate(cd.buckets) { $0.priceMoved == false }
        XCTAssertEqual(CalibrationMath.ece(moved), 5.0, accuracy: 0.001)
        XCTAssertEqual(CalibrationMath.ece(unchanged), 15.0, accuracy: 0.001)
        // Active trading is dramatically better calibrated than opening-price only.
        XCTAssertLessThan(CalibrationMath.ece(moved), CalibrationMath.ece(unchanged))
    }

    func testPerSourceMetric() throws {
        let cd = try decode()
        let kalshiWT = CalibrationMath.aggregate(cd.buckets) { $0.source == "kalshi" && $0.priceMoved != false }
        XCTAssertEqual(CalibrationMath.ece(kalshiWT), 5.0, accuracy: 0.001)
    }

    // MARK: - Aggregation rounding + Wilson CI

    func testAggregateRoundingMatchesWeb() throws {
        let cd = try decode()
        let agg = CalibrationMath.aggregate(cd.buckets, filter: wellTraded)
        // idx 2 merges kalshi(true) + odds_api(null): n=600, winners=160,
        // avg=25.0%, actual=26.7% (rounded to 0.1%), error=+1.7pp.
        let idx2 = try XCTUnwrap(agg.first { $0.bucketIdx == 2 })
        XCTAssertEqual(idx2.n, 600)
        XCTAssertEqual(idx2.avgProb, 25.0, accuracy: 0.001)
        XCTAssertEqual(idx2.actual, 26.7, accuracy: 0.001)
        XCTAssertEqual(idx2.error, 1.7, accuracy: 0.001)
    }

    func testWilsonCIBounds() {
        let (lo, hi) = CalibrationMath.wilsonCI(wins: 60, total: 200)
        XCTAssertGreaterThan(lo, 0)
        XCTAssertLessThan(hi, 1)
        XCTAssertLessThan(lo, 0.30)   // point estimate 0.30 sits inside the interval
        XCTAssertGreaterThan(hi, 0.30)
        // Zero-sample guard.
        XCTAssertEqual(CalibrationMath.wilsonCI(wins: 0, total: 0).0, 0)
        XCTAssertEqual(CalibrationMath.wilsonCI(wins: 0, total: 0).1, 0)
    }

    func testEmptyInputsAreZero() {
        XCTAssertEqual(CalibrationMath.ece([]), 0)
        XCTAssertEqual(CalibrationMath.mce([]), 0)
        XCTAssertEqual(CalibrationMath.brier([]), 0)
    }
}
