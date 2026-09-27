import XCTest
@testable import Bain_Luck

/// #8985 — the Accuracy screen's stat row counts sources, not every resolved market.
///
/// THE BUG THIS PINS. On master `e572580054` against production's payload
/// (2026-09-27 00:19Z) the row under the headline read
/// `505,595 OUTCOMES · 1,183,348 MARKETS · 0.175 BRIER` — more markets than
/// outcomes, which a reader can see is impossible. `total_markets` is
/// `count(*) FROM futures_markets WHERE status='resolved'`, the whole table, not
/// the markets behind the curve. The website stopped printing it in July (#887)
/// and shows Sources 4 in that place; the phone now does the same.
///
/// The count is web's `cohortProviderGroups`: one per provider with outcomes in
/// the active cohort. A provider the cohort empties (`no-cohort-data`) is not
/// counted; a censored one (all won, #6211) still is, because it has outcomes.
final class CalibrationSourcesTileNotMarkets8985Tests: XCTestCase {

    /// Four providers. The three Odds API keys pool into one (#8485). DataGolf has
    /// only untraded (`price_moved: false`) buckets, as production serves it, so
    /// the default cohort empties it. `total_markets` is production's figure.
    private static let payload = """
    {
      "buckets": [
        {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0},
        {"bucket_idx": 6, "source": "polymarket", "category": "politics", "price_moved": true, "n": 120, "winners": 80, "avg_prob": 0.65, "sum_prob": 78.0, "sum_sq_err": 27.0},
        {"bucket_idx": 5, "source": "odds_api", "category": "baseball_mlb", "price_moved": null, "n": 300, "winners": 160, "avg_prob": 0.55, "sum_prob": 165.0, "sum_sq_err": 74.0},
        {"bucket_idx": 4, "source": "odds_api_spreads", "category": "football", "price_moved": null, "n": 90, "winners": 40, "avg_prob": 0.45, "sum_prob": 40.5, "sum_sq_err": 22.0},
        {"bucket_idx": 4, "source": "odds_api_totals", "category": "football", "price_moved": null, "n": 80, "winners": 38, "avg_prob": 0.47, "sum_prob": 37.6, "sum_sq_err": 20.0},
        {"bucket_idx": 6, "source": "datagolf", "category": "golf", "price_moved": false, "n": 14, "winners": 14, "avg_prob": 0.6504, "sum_prob": 9.1056, "sum_sq_err": 1.7213}
      ],
      "total_markets": 1183348, "total_outcomes": 804, "total_winners": 392,
      "generated_at": "2026-09-26T22:17:00+00:00", "min_category_outcomes": 1000
    }
    """

    @MainActor
    private func model() throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return CalibrationViewModel(preloaded: try dec.decode(CalibrationData.self, from: Data(Self.payload.utf8)))
    }

    @MainActor
    func testTheTileCountsTheCohortsProvidersNotEveryResolvedMarket() throws {
        let vm = try model()
        // Default cohort: kalshi, polymarket, Sportsbooks. DataGolf has nothing traded.
        XCTAssertEqual(vm.cohortSourceCount, 3)
        XCTAssertEqual(vm.formattedCohortSources, "3")
        XCTAssertEqual(vm.cohortSourceCount, vm.sourceRows.filter { $0.n > 0 }.count,
                       "the tile agrees with the Source Comparison rows below it")
        // The number the old tile printed is still decoded, and still not shown.
        XCTAssertEqual(vm.data?.totalMarkets, 1_183_348)
        XCTAssertGreaterThan(vm.data?.totalMarkets ?? 0, vm.cohortN,
                             "the fixture reproduces the defect: more markets than outcomes")
        XCTAssertNotEqual(vm.formattedCohortSources, "1,183,348")
    }

    @MainActor
    func testIncludingUntradedCountsTheProviderItBringsBack() throws {
        let vm = try model()
        vm.includeThin = true
        // DataGolf's 14 all won — censored (#6211), but it has outcomes, so it counts,
        // exactly as web's `sourceRowsExcludedFromRollup` keeps censored rows.
        let golf = try XCTUnwrap(vm.sourceRows.first { $0.source == "datagolf" })
        XCTAssertEqual(golf.state, .censored)
        XCTAssertEqual(vm.cohortSourceCount, 4)
    }

    @MainActor
    func testNoPayloadIsADashNotAZero() {
        let vm = CalibrationViewModel()
        XCTAssertEqual(vm.formattedCohortSources, "\u{2014}")
    }

    /// The view is what the reader sees, so read it: the stat row prints the
    /// sources tile and nothing in it prints `total_markets`.
    func testTheStatRowNoLongerPrintsTotalMarkets() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let view = try String(contentsOf: root.appendingPathComponent(
            "ios/Bain Luck/Bain Luck/Views/CalibrationView.swift"), encoding: .utf8)
        let start = try XCTUnwrap(view.range(of: "private var statCardsSection"))
        let end = try XCTUnwrap(view.range(of: "private var eceHeroCard", range: start.upperBound..<view.endIndex))
        let section = String(view[start.lowerBound..<end.lowerBound])
        XCTAssertTrue(section.contains("miniStatCard(\"SOURCES\", viewModel.formattedCohortSources"), section)
        XCTAssertFalse(section.contains("MARKETS"), section)
        XCTAssertFalse(section.contains("totalMarkets"), section)
        XCTAssertFalse(section.contains("formattedMarkets"), section)
    }
}
