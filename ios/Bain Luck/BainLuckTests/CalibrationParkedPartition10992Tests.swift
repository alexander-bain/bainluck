import XCTest
@testable import Bain_Luck

/// #10992 — the niche card names the categories that are genuinely waiting for
/// enough results, the same ones the website names, from one bank.
///
/// On the payload served 2026-10-13 07:29Z the website said **42 categories**
/// (Rugby 427, Other 386, Boxing 300 …) and the phone said **115 categories /
/// 27.8K outcomes** (Serie A 977, ATP Canadian Open 976 …). Two defects, both
/// needed for parity:
///
///   * `smallSampleCategories` sorted the raw `small_sample_categories` list
///     without web's #7325 join, so a sub-league whose parent is published
///     (Serie A inside Soccer) was called "still accumulating";
///   * the two normalisation maps had drifted — web rolls `mlb` up to Baseball
///     and `lacrosse_*` up to Lacrosse, this app did not. With the join alone,
///     the real payload read 46 parked led by `lacrosse_ncaa` 829, against
///     web's 42 led by Rugby 427.
///
/// The fixture carries one specimen of each: a mapped sub-league (CFL, Serie A),
/// the two map keys that drifted (`mlb`, `lacrosse_*`), and real held-out
/// categories (rugby, other, boxing). The jest twin
/// `frontend/__tests__/ios/calibrationParkedPartitionParity10992.test.ts` runs
/// web's own `normalizeCat` over the same rows and pins the maps key-for-key.
final class CalibrationParkedPartition10992Tests: XCTestCase {

    private static let payload = """
    {
      "buckets": [
        {"bucket_idx": 5, "source": "kalshi", "category": "americanfootball_nfl", "price_moved": true, "n": 1500, "winners": 750, "sum_prob": 750.0, "sum_sq_err": 375.0},
        {"bucket_idx": 5, "source": "kalshi", "category": "soccer_epl", "price_moved": true, "n": 1200, "winners": 600, "sum_prob": 600.0, "sum_sq_err": 300.0},
        {"bucket_idx": 5, "source": "polymarket", "category": "lacrosse", "price_moved": false, "n": 600, "winners": 300, "sum_prob": 300.0, "sum_sq_err": 150.0},
        {"bucket_idx": 5, "source": "polymarket", "category": "lacrosse_ncaa", "price_moved": true, "n": 500, "winners": 250, "sum_prob": 250.0, "sum_sq_err": 125.0},
        {"bucket_idx": 5, "source": "kalshi", "category": "mlb", "price_moved": true, "n": 700, "winners": 350, "sum_prob": 350.0, "sum_sq_err": 175.0},
        {"bucket_idx": 5, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 450, "winners": 225, "sum_prob": 225.0, "sum_sq_err": 112.5},
        {"bucket_idx": 5, "source": "polymarket", "category": "rugby", "price_moved": true, "n": 427, "winners": 200, "sum_prob": 210.0, "sum_sq_err": 105.0},
        {"bucket_idx": 5, "source": "polymarket", "category": "other", "price_moved": false, "n": 386, "winners": 190, "sum_prob": 190.0, "sum_sq_err": 95.0},
        {"bucket_idx": 5, "source": "polymarket", "category": "boxing", "price_moved": true, "n": 300, "winners": 150, "sum_prob": 150.0, "sum_sq_err": 75.0}
      ],
      "total_markets": 9,
      "total_outcomes": 6063,
      "generated_at": "2026-10-13T07:29:25+00:00",
      "min_category_outcomes": 1000,
      "small_sample_categories": [
        {"category": "soccer_italy_serie_a", "outcomes": 977},
        {"category": "americanfootball_cfl", "outcomes": 847},
        {"category": "lacrosse_ncaa", "outcomes": 829},
        {"category": "mlb", "outcomes": 700},
        {"category": "lacrosse_pll", "outcomes": 538},
        {"category": "rugby", "outcomes": 427},
        {"category": "other", "outcomes": 386},
        {"category": "boxing", "outcomes": 300}
      ]
    }
    """

    /// What web's `parkedCategories` yields on these rows — the jest twin
    /// asserts the same list from web's own normaliser.
    private static let expectedParked: [(key: String, outcomes: Int, label: String)] = [
        ("rugby", 427, "Rugby"), ("other", 386, "Other"), ("boxing", 300, "Boxing"),
    ]

    @MainActor
    private func model() throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return CalibrationViewModel(preloaded: try dec.decode(CalibrationData.self, from: Data(Self.payload.utf8)))
    }

    // MARK: - 1. The card prints web's count, total and chips

    @MainActor
    func testTheNicheCardNamesOnlyTheGenuinelyParkedCategories() throws {
        let vm = try model()
        XCTAssertEqual(vm.smallSampleCategories.map(\.category), Self.expectedParked.map(\.key),
                       "the niche card lists a category whose parent is published, or drops a held-out one")
        XCTAssertEqual(vm.smallSampleCategories.map(\.outcomes), Self.expectedParked.map(\.outcomes))
        XCTAssertEqual(vm.smallSampleTotal, 1113, "the card's 'N outcomes' must sum the joined list, not the raw one")
        XCTAssertEqual(vm.smallSampleCategories.map { CalibrationViewModel.nicheDisplayName($0.category) },
                       Self.expectedParked.map(\.label))
    }

    /// 🪤 The specimens, by name. A sub-league whose parent the table publishes
    /// is not waiting for anything: it can never "appear above automatically".
    @MainActor
    func testASubLeagueInsideAPublishedParentIsNotParked() throws {
        let parked = Set(try model().smallSampleCategories.map(\.category))
        for raw in ["soccer_italy_serie_a", "americanfootball_cfl", "lacrosse_ncaa", "lacrosse_pll", "mlb"] {
            XCTAssertFalse(parked.contains(raw), "\(raw) is inside a published parent and still reads as parked")
        }
    }

    // MARK: - 2. The map keys that drifted from web

    /// Without web's `lacrosse` and `mlb` entries the join still runs, but on a
    /// different vocabulary: lacrosse never publishes and its leagues lead the card.
    @MainActor
    func testLacrosseAndMlbRollUpAsTheyDoOnWeb() throws {
        XCTAssertEqual(CalibrationViewModel.normalizedCategory("lacrosse_ncaa"), "lacrosse")
        XCTAssertEqual(CalibrationViewModel.normalizedCategory("lacrosse_pll"), "lacrosse")
        XCTAssertEqual(CalibrationViewModel.normalizedCategory("mlb"), "baseball")
        let vm = try model()
        XCTAssertTrue(vm.categories.contains("lacrosse"), "Lacrosse clears the bar at 1,100 and is not published")
        XCTAssertTrue(vm.categories.contains("baseball"), "Baseball clears the bar at 1,150 and is not published")
        XCTAssertEqual(CalibrationViewModel.categoryDisplayName("lacrosse"), "Lacrosse")
    }

    // MARK: - 3. One partition, in one vocabulary

    @MainActor
    func testPublishedAndParkedAreDisjointAndAccountForEveryCategory() throws {
        let vm = try model()
        let published = Set(vm.categories)
        let parked = Set(vm.smallSampleCategories.map { CalibrationViewModel.normalizedCategory($0.category) })
        XCTAssertTrue(published.isDisjoint(with: parked), "in both lists: \(published.intersection(parked))")

        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let data = try dec.decode(CalibrationData.self, from: Data(Self.payload.utf8))
        let carried = Set(data.buckets.map { CalibrationViewModel.normalizedCategory($0.category) })
            .union((data.smallSampleCategories ?? []).map { CalibrationViewModel.normalizedCategory($0.category) })
        XCTAssertEqual(published.union(parked), carried, "a category the payload carries is in neither list")
        XCTAssertEqual(published, ["football", "soccer", "lacrosse", "baseball"])
    }

    /// #7195 — the bar counts every resolved outcome, so flipping traded/all
    /// moves neither list. Lacrosse is the edge: 500 traded, 1,100 all-cohort.
    @MainActor
    func testTheTradedToggleMovesNeitherList() throws {
        let vm = try model()
        vm.includeThin = false
        let tradedPublished = vm.categories
        let tradedParked = vm.smallSampleCategories.map(\.category)
        vm.includeThin = true
        XCTAssertEqual(Set(vm.categories), Set(tradedPublished))
        XCTAssertEqual(vm.smallSampleCategories.map(\.category), tradedParked)
        XCTAssertTrue(tradedPublished.contains("lacrosse"))
    }
}
