import XCTest
@testable import Bain_Luck

/// calibration (#8917) — a category listed on its all-outcome total but thin in
/// the view on screen is never a headline card.
///
/// Production, 2026-09-26: Table Tennis cleared the 1,000-outcome bar on 4,772
/// outcomes (the bar is all-cohort, #7195) and held 26 traded ones. The default
/// view graded those 26 at 21.6pp — the worst row in the table — and
/// `worstCategoryRow` is the table's last measured row, so the phone's
/// "Needs attention" card named it.
///
/// The fixture carries that straddle AND a control: a category comfortably over
/// the bar in the traded view with a bad (but less bad) error, which is what the
/// card should name instead. Without the control, "never show the card" would
/// pass.
final class ThinCategoryRowIsNotAHeadline8917Tests: XCTestCase {

    private static let bar = 1000

    private static func bucket(_ category: String, n: Int, priceMoved: Bool, winnersRate: Double) -> String {
        let winners = Int((Double(n) * winnersRate).rounded())
        let sumProb = Double(n) * 0.25
        return """
        {"bucket_idx": 2, "source": "kalshi", "category": "\(category)", "price_moved": \(priceMoved), \
        "n": \(n), "winners": \(winners), "sum_prob": \(sumProb), "sum_sq_err": 1.0, \
        "ci_lower": 0.21, "ci_upper": 0.31}
        """
    }

    /// Synthetic keys so `normalizedCategory` cannot roll two of them together.
    private static func payload() -> String {
        let rows = [
            bucket("zgood", n: 5000, priceMoved: true, winnersRate: 0.25),      // 0.0pp
            bucket("zbad", n: 2000, priceMoved: true, winnersRate: 0.35),       // 10.0pp, over the bar
            // SPECIMEN: 26 traded (worst), 4,746 untraded — listed on 4,772.
            bucket("zthin", n: 26, priceMoved: true, winnersRate: 0.50),
            bucket("zthin", n: 4746, priceMoved: false, winnersRate: 0.25),
        ]
        return """
        {
          "buckets": [\(rows.joined(separator: ",\n"))],
          "total_markets": 12,
          "total_outcomes": 11772,
          "total_winners": 3000,
          "mce_ci_lower": 0.6,
          "mce_ci_upper": 1.7,
          "mce_closing_line": 1.5,
          "mce_opening_price": 2.2,
          "generated_at": "2026-09-26T20:20:00+00:00",
          "min_category_outcomes": \(bar),
          "small_sample_categories": [],
          "date_range": {"start": "2021-07-13T00:00:00+00:00", "end": "2026-09-26T00:05:00+00:00"}
        }
        """
    }

    @MainActor
    private func model() throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let vm = CalibrationViewModel(preloaded: try dec.decode(CalibrationData.self, from: Data(Self.payload().utf8)))
        vm.includeThin = false   // the default (traded) view, whatever the launch rig says
        return vm
    }

    /// The straddle is real in the fixture, or every assertion below is vacuous.
    @MainActor
    func testFixtureListsTheThinRowAndItIsTheWorstInTheTable() throws {
        let vm = try model()
        let thin = try XCTUnwrap(vm.categoryRows.first { $0.category == "zthin" },
                                 "the thin category must still be listed — the bar is all-cohort")
        XCTAssertEqual(thin.n, 26)
        XCTAssertEqual(vm.categoryRows.last?.category, "zthin",
                       "fixture: the thin row must be the table's worst, as on production")
    }

    /// 🔴 The headline card names a row at the bar, not the 26-outcome one.
    @MainActor
    func testNeedsAttentionSkipsARowThinInThisView() throws {
        let vm = try model()
        XCTAssertEqual(vm.worstCategoryRow?.category, "zbad",
                       "'Needs attention' named \(vm.worstCategoryRow?.category ?? "nil") — a row under the bar in this view")
        XCTAssertEqual(vm.bestCategoryRow?.category, "zgood")
    }

    /// Showing untraded outcomes lifts the row back over the bar: it is then an
    /// ordinary row, eligible for a headline on its merits.
    @MainActor
    func testTheSameRowIsOrdinaryOnceItClearsTheBarInTheView() throws {
        let vm = try model()
        vm.includeThin = true
        let row = try XCTUnwrap(vm.categoryRows.first { $0.category == "zthin" })
        XCTAssertEqual(row.n, 4772)
        XCTAssertFalse(CalibrationPopulation.isThinInView(n: row.n, bar: Self.bar))
        XCTAssertEqual(vm.worstCategoryRow?.category, "zbad")
    }

    /// Same boundary as the caption's "a row here can show fewer" clause.
    func testThinBoundaryMatchesTheCaption() {
        XCTAssertTrue(CalibrationPopulation.isThinInView(n: 999, bar: 1000))
        XCTAssertFalse(CalibrationPopulation.isThinInView(n: 1000, bar: 1000))
        let note = CalibrationPopulation.categoryTableNote(bar: 1000, renderedRowOutcomes: [26, 5000])
        XCTAssertTrue(note.contains("can show fewer"))
    }
}
