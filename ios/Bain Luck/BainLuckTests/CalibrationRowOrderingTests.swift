import XCTest
@testable import Bain_Luck

/// #3650 — an unmeasured source must not win a ranking it was never in.
///
/// THE BUG THIS PINS. The iPad Calibration screen ranked **DataGolf first at
/// `0.0`** in a table subheaded *"sorted by ECE … Lower is better"*
/// (`artifacts-native-042/ipad-calibration.png`). Measured against
/// `/api/calibration` on 2026-09-06: `datagolf` publishes **36 outcomes, all
/// `price_moved: false`**, so the default cohort holds zero of them and every
/// metric on that row was an empty reduction's identity element. Its real ECE,
/// with the never-moved outcomes included, is **36.49pp** — 13× the worst
/// measured source (polymarket, 2.81pp) and 104× the best (odds_api_spreads,
/// 0.35pp).
///
/// THE SHAPE OF THESE TESTS. A guard that only asserts "the right identifiers
/// appear" survives a permutation mutant, so every ordering assertion below
/// pins **positions**, and `testASwappedComparatorIsCaught` exists to fail if
/// the comparator's two arms are exchanged. Metrics are asserted `nil`, not
/// `0` — the distinction the whole fix is about.
final class CalibrationRowOrderingTests: XCTestCase {

    /// A minimal conformer so the ordering is tested on its own terms, without
    /// dragging a view model and a payload behind every assertion.
    private struct Row: CalibrationMetricRow, Equatable {
        let name: String
        let n: Int
        let ece: Double?

        /// Built the way production builds one: the metric is filtered through
        /// `metric(_:outcomes:)`, so a fixture cannot express the impossible
        /// state (n == 0 with a metric) that the fix exists to prevent.
        static func make(_ name: String, n: Int, ece: Double) -> Row {
            Row(name: name, n: n, ece: CalibrationRowOrdering.metric(ece, outcomes: n))
        }
    }

    // MARK: - State and metric withholding

    func testStateComesFromTheCountBecauseAMetricCannotReportItsOwnAbsence() {
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: 0), .noCohortData)
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: -1), .noCohortData)
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: 1), .measured)
        XCTAssertEqual(CalibrationRowOrdering.state(outcomes: 36), .measured)
    }

    func testAMetricOverZeroOutcomesIsWithheldRatherThanZeroed() {
        // The exact value `CalibrationMath.ece([])` returns. It must not survive.
        XCTAssertNil(CalibrationRowOrdering.metric(0, outcomes: 0))
        XCTAssertNil(CalibrationRowOrdering.metric(36.49, outcomes: 0))
        // A real zero from a real cohort is a measurement and must survive.
        XCTAssertEqual(CalibrationRowOrdering.metric(0, outcomes: 5), 0)
        XCTAssertEqual(CalibrationRowOrdering.metric(2.81, outcomes: 69_492), 2.81)
        // NaN/inf are not measurements either.
        XCTAssertNil(CalibrationRowOrdering.metric(.nan, outcomes: 5))
        XCTAssertNil(CalibrationRowOrdering.metric(.infinity, outcomes: 5))
    }

    // MARK: - The ordering, by position

    /// The production case, in the production order, with the real numbers.
    func testTheUnmeasuredSourceGoesLastNotFirst() {
        let rows = CalibrationRowOrdering.orderedByECE([
            Row.make("DataGolf", n: 0, ece: 0),               // the empty reduction
            Row.make("Odds API Spreads", n: 15_120, ece: 0.35),
            Row.make("Kalshi", n: 219_022, ece: 1.29),
            Row.make("Polymarket", n: 69_492, ece: 2.81),
        ])
        XCTAssertEqual(rows.map(\.name),
                       ["Odds API Spreads", "Kalshi", "Polymarket", "DataGolf"])
        // Position, stated as position: last, and not first.
        XCTAssertEqual(rows.last?.name, "DataGolf")
        XCTAssertNotEqual(rows.first?.name, "DataGolf")
        XCTAssertNil(rows.last?.ece, "an unmeasured row must carry no metric")
        XCTAssertEqual(rows.first?.ece, 0.35)
    }

    /// The mutant the restock warned about: exchanging the comparator's arms.
    ///
    /// A guard that asserted only "the body mentions measured and unmeasured"
    /// would pass with the arms swapped. This one cannot: with the swap, the
    /// unmeasured row returns to first place, which is precisely the bug.
    func testASwappedComparatorIsCaught() {
        let rows = CalibrationRowOrdering.orderedByECE([
            Row.make("Zeta", n: 0, ece: 0),
            Row.make("Alpha", n: 100, ece: 9.9),
        ])
        // "Zeta" beats "Alpha" alphabetically in neither direction that matters
        // and has the LOWER raw metric (0 < 9.9), so only the measured/unmeasured
        // split can produce this order. Both facts are pinned at once.
        XCTAssertEqual(rows.map(\.name), ["Alpha", "Zeta"])
        XCTAssertEqual(rows[0].ece, 9.9, "the measured row leads even at 9.9pp")
        XCTAssertNil(rows[1].ece)
    }

    func testMeasuredRowsAreOrderedByECEAscendingAndTiesBreakOnLabel() {
        let rows = CalibrationRowOrdering.orderedByECE([
            Row.make("Charlie", n: 10, ece: 2.0),
            Row.make("Alpha", n: 10, ece: 2.0),
            Row.make("Bravo", n: 10, ece: 0.5),
        ])
        XCTAssertEqual(rows.map(\.name), ["Bravo", "Alpha", "Charlie"])
    }

    /// A stable tail matters: without it the row order would track the payload's
    /// source ordering, a change a reader would read as a change in the data.
    func testTheUnmeasuredTailIsAlphabeticalRegardlessOfInputOrder() {
        let names = ["Yankee", "Alpha", "Mike"]
        let forwards = CalibrationRowOrdering.orderedByECE(names.map { Row.make($0, n: 0, ece: 0) })
        let backwards = CalibrationRowOrdering.orderedByECE(names.reversed().map { Row.make($0, n: 0, ece: 0) })
        XCTAssertEqual(forwards.map(\.name), ["Alpha", "Mike", "Yankee"])
        XCTAssertEqual(backwards.map(\.name), forwards.map(\.name))
    }

    func testEveryRowMeasuredIsAPlainRanking() {
        let rows = CalibrationRowOrdering.orderedByECE([
            Row.make("B", n: 1, ece: 3.0), Row.make("A", n: 1, ece: 1.0),
        ])
        XCTAssertEqual(rows.map(\.name), ["A", "B"])
        XCTAssertTrue(rows.allSatisfy { $0.ece != nil })
    }

    func testEmptyInputIsEmptyOutput() {
        XCTAssertTrue(CalibrationRowOrdering.orderedByECE([Row]()).isEmpty)
    }

    // MARK: - Naming the absence, and the remedy

    func testWithheldSelectsExactlyTheZeroOutcomeRows() {
        let rows = [Row.make("DataGolf", n: 0, ece: 0), Row.make("Kalshi", n: 219_022, ece: 1.29)]
        XCTAssertEqual(CalibrationRowOrdering.withheld(rows).map(\.name), ["DataGolf"])
    }

    func testTheNoteNamesTheSourceAndTheToggleThatMeasuresIt() throws {
        let note = try XCTUnwrap(CalibrationRowOrdering.withheldNote(
            labels: ["DataGolf"], toggleLabel: "Include never-moved (+303,577)"))
        XCTAssertTrue(note.contains("DataGolf"))
        XCTAssertTrue(note.contains("no outcomes in this cohort"))
        XCTAssertTrue(note.contains("not ranked above"))
        // The remedy must be NAMED, not implied.
        XCTAssertTrue(note.contains("Include never-moved (+303,577)"))
        XCTAssertTrue(note.contains("has"), "singular agreement")
        XCTAssertFalse(note.contains("have"))
    }

    func testTheNotePluralisesAndIsAbsentWhenNothingWasWithheld() {
        let many = CalibrationRowOrdering.withheldNote(labels: ["A", "B"], toggleLabel: "T")
        XCTAssertEqual(many?.contains("A, B"), true)
        XCTAssertEqual(many?.contains("have no outcomes"), true)
        XCTAssertEqual(many?.contains("they are"), true)
        // No sentence about an empty set.
        XCTAssertNil(CalibrationRowOrdering.withheldNote(labels: [], toggleLabel: "T"))
    }

    // MARK: - The view model, on the production shape

    /// `datagolf`'s real situation: outcomes exist, but every one of them is
    /// `price_moved: false`, so the DEFAULT cohort holds none of them and the
    /// toggle brings them all back. Kalshi is the measured comparison.
    private static let dataGolfShapedPayload = """
    {
      "buckets": [
        {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
        {"bucket_idx": 8, "source": "datagolf", "category": "golf_pga", "price_moved": false, "n": 36, "winners": 30, "avg_prob": 0.45, "sum_prob": 16.2, "sum_sq_err": 9.0, "ci_lower": 0.3, "ci_upper": 0.6}
      ],
      "total_markets": 12, "total_outcomes": 236, "total_winners": 90,
      "generated_at": "2026-09-06T19:00:00+00:00", "min_category_outcomes": 1000,
      "date_range": {"start": "2021-07-13T00:00:00+00:00", "end": "2026-09-06T00:05:00+00:00"}
    }
    """

    @MainActor
    private func model() throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return CalibrationViewModel(
            preloaded: try dec.decode(CalibrationData.self, from: Data(Self.dataGolfShapedPayload.utf8)))
    }

    /// The photographed bug, end to end: DataGolf is listed, is LAST, prints no
    /// metrics, and the screen says why and how to fix it.
    @MainActor
    func testDataGolfIsListedLastWithNoMetricsAndAStatedReason() throws {
        let vm = try model()
        let rows = vm.sourceRows

        let golf = try XCTUnwrap(rows.first { $0.source == "datagolf" },
                                 "the row must still be LISTED — it is not dropped")
        XCTAssertEqual(golf.n, 0, "the default cohort holds none of its 36 outcomes")
        XCTAssertEqual(golf.state, .noCohortData)
        XCTAssertNil(golf.ece); XCTAssertNil(golf.mce); XCTAssertNil(golf.brier)

        XCTAssertEqual(rows.last?.source, "datagolf", "ordered out of the ranking")
        XCTAssertEqual(rows.first?.source, "kalshi", "the measured source leads")
        XCTAssertNotNil(rows.first?.ece)

        let note = try XCTUnwrap(vm.withheldSourcesNote)
        XCTAssertTrue(note.contains(CalibrationViewModel.sourceDisplayName("datagolf")))
        XCTAssertTrue(note.contains(vm.cohortToggleLabel),
                      "the note must name the toggle that measures it")
    }

    /// Turning the toggle on is the remedy the note promises, so it has to work:
    /// the row becomes measured, carries a real metric, and the note disappears.
    @MainActor
    func testTheToggleTheNoteNamesActuallyMeasuresTheWithheldSource() throws {
        let vm = try model()
        vm.includeThin = true

        let golf = try XCTUnwrap(vm.sourceRows.first { $0.source == "datagolf" })
        XCTAssertEqual(golf.n, 36)
        XCTAssertEqual(golf.state, .measured)
        // 30/36 won against a 45% average prediction: ~38.3pp of error. The
        // point is that it is LARGE and REAL, not the 0.0 it used to print.
        XCTAssertGreaterThan(try XCTUnwrap(golf.ece), 20)
        XCTAssertNil(vm.withheldSourcesNote, "nothing is withheld once the toggle is on")
        XCTAssertEqual(vm.sourceRows.last?.source, "datagolf",
                       "and now it is last on merit, not on absence")
    }
}
