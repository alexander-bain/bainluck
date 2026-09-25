import XCTest
@testable import Bain_Luck

/// #6211 on the phone: a population that all won is not a measurement.
///
/// THE BUG THIS PINS. Production's `/api/calibration` (read 2026-09-25 05:2xZ)
/// publishes DataGolf as 5 buckets, 36 outcomes, **36 winners**, all
/// `price_moved: false`. With "include untraded" on, the phone's Source
/// Comparison printed `36 · 36.5 · 35.8 · 0.142` and ranked DataGolf last. The
/// website prints "All 36 won — no losses to measure against." in those cells,
/// and has since bae9f393b7.
///
/// The fixture below is those five production buckets verbatim, plus one Kalshi
/// bucket as the measured comparison. `CalibrationRowOrderingTests` keeps its
/// 30-of-36 DataGolf fixture as the CONTROL: a two-sided population with the
/// same count stays measured and ranked. That arm fails if the verdict turns
/// into a threshold.
final class CalibrationCensoredSourceRow6211Tests: XCTestCase {

    // MARK: - The verdict, on its own terms

    func testOnlyAnExactlyOneSidedPopulationIsCensored() {
        XCTAssertTrue(CalibrationRowOrdering.censoringVerdict(outcomes: 36, winners: 36))
        XCTAssertTrue(CalibrationRowOrdering.censoringVerdict(outcomes: 36, winners: 0),
                      "all-lost is price-determined by the same arithmetic")
        XCTAssertFalse(CalibrationRowOrdering.censoringVerdict(outcomes: 36, winners: 35),
                       "35 of 36 is a skewed population, and still a measurement")
        XCTAssertFalse(CalibrationRowOrdering.censoringVerdict(outcomes: 36, winners: 1))
        XCTAssertFalse(CalibrationRowOrdering.censoringVerdict(outcomes: 0, winners: 0),
                       "no population is not a censored one")
    }

    func testAbsenceBeatsCensoring() {
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: 0, winners: 0), .noCohortData)
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: 36, winners: 36), .censored)
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: 36, winners: 30), .measured)
    }

    func testACensoredFigureIsDiscardedWhereTheRowIsBuilt() {
        XCTAssertNil(CalibrationRowOrdering.metric(36.5, outcomes: 36, winners: 36))
        XCTAssertNil(CalibrationRowOrdering.metric(36.5, outcomes: 36, winners: 0))
        XCTAssertEqual(CalibrationRowOrdering.metric(38.3, outcomes: 36, winners: 30), 38.3)
    }

    /// Web's pooling: per-bucket clamp to `n`, floor at 0. A bucket claiming more
    /// winners than outcomes pools as one-sided, which withholds the row.
    func testPoolingClampsACorruptBucketToTheFailClosedSide() throws {
        let buckets = try Self.decode("""
        [
          {"bucket_idx": 4, "source": "x", "category": "c", "price_moved": false, "n": 3, "winners": 9, "sum_prob": 1.3, "sum_sq_err": 0.9},
          {"bucket_idx": 5, "source": "x", "category": "c", "price_moved": false, "n": 2, "winners": 2, "sum_prob": 1.1, "sum_sq_err": 0.4}
        ]
        """, as: [CalibrationBucket].self)
        let w = CalibrationRowOrdering.pooledWinners(buckets)
        XCTAssertEqual(w, 5, "3 (clamped from 9) + 2")
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: 5, winners: w), .censored)
    }

    // MARK: - The words are web's

    /// The sentence is paired to web's `censoredPopulationText`, read from the
    /// web source, not copied from it. If either surface rewords, this fails.
    func testTheSentenceIsByteIdenticalToTheWebsites() throws {
        let web = try String(contentsOf: Self.repoRoot
            .appendingPathComponent("frontend/lib/calibrationSourceRows.ts"), encoding: .utf8)
        let placeholder = "${n.toLocaleString()}"
        let lost = try XCTUnwrap(Self.template(in: web, containing: " lost "), "web's all-lost template")
        let won = try XCTUnwrap(Self.template(in: web, containing: " won "), "web's all-won template")
        XCTAssertTrue(lost.contains(placeholder) && won.contains(placeholder))

        for n in [36, 1_234, 318_956] {
            let count = n.formatted(.number.locale(Locale(identifier: "en_US")))
            XCTAssertEqual(CalibrationRowOrdering.censoredPopulationText(outcomes: n, winners: n),
                           won.replacingOccurrences(of: placeholder, with: count))
            XCTAssertEqual(CalibrationRowOrdering.censoredPopulationText(outcomes: n, winners: 0),
                           lost.replacingOccurrences(of: placeholder, with: count))
        }
        XCTAssertEqual(CalibrationRowOrdering.censoredPopulationText(outcomes: 1_234, winners: 1_234),
                       "All 1,234 won \u{2014} no losses to measure against.")
    }

    // MARK: - The view model, on production's DataGolf buckets

    /// The five DataGolf buckets exactly as production serves them, and one Kalshi bucket.
    private static let productionDataGolfPayload = """
    {
      "buckets": [
        {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
        {"bucket_idx": 4, "source": "datagolf", "category": "golf", "price_moved": false, "n": 3, "winners": 3, "avg_prob": 0.4367, "sum_prob": 1.3101, "sum_sq_err": 0.955, "ci_lower": 0.4385, "ci_upper": 1.0},
        {"bucket_idx": 5, "source": "datagolf", "category": "golf", "price_moved": false, "n": 9, "winners": 9, "avg_prob": 0.5552, "sum_prob": 4.9968, "sum_sq_err": 1.7875, "ci_lower": 0.7, "ci_upper": 1.0},
        {"bucket_idx": 6, "source": "datagolf", "category": "golf", "price_moved": false, "n": 14, "winners": 14, "avg_prob": 0.6504, "sum_prob": 9.1056, "sum_sq_err": 1.7213, "ci_lower": 0.78, "ci_upper": 1.0},
        {"bucket_idx": 7, "source": "datagolf", "category": "golf", "price_moved": false, "n": 9, "winners": 9, "avg_prob": 0.7355, "sum_prob": 6.6195, "sum_sq_err": 0.6335, "ci_lower": 0.7, "ci_upper": 1.0},
        {"bucket_idx": 8, "source": "datagolf", "category": "golf", "price_moved": false, "n": 1, "winners": 1, "avg_prob": 0.8326, "sum_prob": 0.8326, "sum_sq_err": 0.028, "ci_lower": 0.2, "ci_upper": 1.0}
      ],
      "total_markets": 12, "total_outcomes": 236, "total_winners": 96,
      "generated_at": "2026-09-15T11:16:10+00:00", "min_category_outcomes": 1000,
      "date_range": {"start": "2021-07-13T00:00:00+00:00", "end": "2026-09-15T00:05:00+00:00"}
    }
    """

    @MainActor
    private func model() throws -> CalibrationViewModel {
        CalibrationViewModel(preloaded: try Self.decode(Self.productionDataGolfPayload, as: CalibrationData.self))
    }

    /// The photographed row, end to end: with the toggle on, DataGolf is listed
    /// with its real count, prints no metric, is out of the ranking, and states
    /// which side its population fell on.
    @MainActor
    func testWithUntradedOnDataGolfStatesItsPopulationInsteadOfAFigure() throws {
        let vm = try model()
        vm.includeThin = true

        let golf = try XCTUnwrap(vm.sourceRows.first { $0.source == "datagolf" })
        XCTAssertEqual(golf.n, 36, "the count is real and stays")
        XCTAssertEqual(golf.winners, 36)
        XCTAssertEqual(golf.state, .censored)
        XCTAssertNil(golf.ece, "the 36.5pp it used to print is price-determined")
        XCTAssertNil(golf.mce); XCTAssertNil(golf.brier)
        XCTAssertEqual(CalibrationRowOrdering.censoredPopulationText(outcomes: golf.n, winners: golf.winners),
                       "All 36 won \u{2014} no losses to measure against.")

        XCTAssertEqual(vm.sourceRows.map(\.source), ["kalshi", "datagolf"],
                       "measured first; the censored row joins the unranked tail")
        XCTAssertNotNil(vm.sourceRows.first?.ece)
        XCTAssertTrue(CalibrationRowOrdering.withheld(vm.sourceRows).isEmpty,
                      "the 'no outcomes in this cohort' set is absence only, as on web")
    }

    /// The default cohort is unchanged: DataGolf has no traded outcomes, so it is
    /// absent, not censored.
    @MainActor
    func testTheDefaultCohortStillReadsAsAbsence() throws {
        let golf = try XCTUnwrap(try model().sourceRows.first { $0.source == "datagolf" })
        XCTAssertEqual(golf.n, 0)
        XCTAssertEqual(golf.state, .noCohortData)
    }

    // MARK: - Helpers

    private static var repoRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
    }

    /// The backtick template literal in `source` whose text contains `marker`.
    private static func template(in source: String, containing marker: String) -> String? {
        source.components(separatedBy: "`")
            .first { $0.hasPrefix("All ") && $0.contains("${") && $0.contains(marker) }
    }

    private static func decode<T: Decodable>(_ json: String, as type: T.Type) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(T.self, from: Data(json.utf8))
    }
}
