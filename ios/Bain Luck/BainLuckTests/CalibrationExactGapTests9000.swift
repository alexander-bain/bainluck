import XCTest
@testable import Bain_Luck

/// #9000: the phone's Source table prints the same Polymarket figure the
/// website's By Source panel prints.
///
/// Production `/api/calibration` (generated 2026-09-26 22:17Z), all outcomes:
/// the server publishes Polymarket `by_source[].ece` 1.96 → "2.0". The phone
/// computes provider ECE from `CalibrationMath.aggregate`, whose `error` is
/// rounded to 0.1pp; averaging those rounded errors gave 1.950 → "1.9". The
/// metrics now average `errorExact`, the unrounded gap: 1.963 → "2.0".
///
/// The ten bins below are that payload's Polymarket rows pooled on
/// `bucket_idx` (every category and `price_moved` state summed; summing is
/// exact). Web pins the same specimen in
/// `frontend/__tests__/sourceComparisonMatchesItsPanel9000.test.ts`.
final class CalibrationExactGapTests9000: XCTestCase {

    /// (bucket_idx, n, winners, sum_prob) — production, Polymarket, all outcomes.
    private static let polymarket: [(Int, Int, Int, Double)] = [
        (0, 94517, 4185, 4291.7274),
        (1, 32074, 4218, 4617.4388),
        (2, 34574, 7854, 8570.2672),
        (3, 56359, 18927, 19385.5902),
        (4, 64368, 25140, 29728.8338),
        (5, 77731, 39537, 40474.6683),
        (6, 21273, 14074, 13706.3891),
        (7, 15825, 12275, 11776.5632),
        (8, 10250, 8722, 8675.8337),
        (9, 12123, 11413, 11307.0122),
    ]

    private static func buckets() -> [CalibrationBucket] {
        polymarket.map { idx, n, w, sp in
            CalibrationBucket(
                bucketIdx: idx, source: "polymarket", category: "agg", priceMoved: nil,
                n: n, winners: w, sumProb: sp, sumSqErr: 0,
                ciLower: nil, ciUpper: nil, avgProb: nil
            )
        }
    }

    func testPolymarketPrintsThePanelsDigit() {
        let agg = CalibrationMath.aggregate(Self.buckets())
        XCTAssertEqual(agg.reduce(0) { $0 + $1.n }, 419_094)
        let e = CalibrationMath.ece(agg)
        XCTAssertEqual(e, 1.963, accuracy: 0.0005)
        XCTAssertEqual(String(format: "%.1f", e), "2.0")
    }

    /// Strawman: the same bins averaged off the ROUNDED error — the defect.
    func testTheRoundedErrorsPrintOneNine() {
        let rounded = CalibrationMath.aggregate(Self.buckets()).map {
            CalibrationMath.AggBucket(
                bucketIdx: $0.bucketIdx, n: $0.n, winners: $0.winners,
                avgProb: $0.avgProb, actual: $0.actual, error: $0.error,
                ciLower: $0.ciLower, ciUpper: $0.ciUpper
            )
        }
        let e = CalibrationMath.ece(rounded)
        XCTAssertEqual(e, 1.950, accuracy: 0.0005)
        XCTAssertEqual(String(format: "%.1f", e), "1.9")
    }

    func testDisplayErrorStaysAtOneDecimalAndCarriesTheExactGap() {
        for b in CalibrationMath.aggregate(Self.buckets()) {
            XCTAssertEqual((b.error * 10).rounded() / 10, b.error)
            let exact = try? XCTUnwrap(b.errorExact)
            XCTAssertNotNil(exact)
            XCTAssertLessThanOrEqual(abs(b.error - (exact ?? .nan)), 0.05 + 1e-9)
        }
    }

    func testMCEAlsoReadsTheExactGap() {
        let agg = CalibrationMath.aggregate(Self.buckets())
        let exactMean = agg.reduce(0.0) { $0 + abs($1.errorExact ?? .nan) } / Double(agg.count)
        XCTAssertEqual(CalibrationMath.mce(agg), exactMean, accuracy: 1e-12)
    }
}
