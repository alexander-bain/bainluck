import XCTest
@testable import Bain_Luck

/// native (#7533) — the Category Breakdown draws every category that clears the
/// publish bar, because the bar is the only filter the caption declares.
///
/// ── WHAT THE READER WAS TOLD, AND WHAT WAS DONE ─────────────────────────────
///
/// The caption above the table says categories are *"sorted by ECE"* and that
/// *"categories below 1.0K resolved outcomes are held out — see below."* A
/// reader takes two things from that: the bar is the only reason a category is
/// missing, and the rows are the best-calibrated ones. Both were false.
///
/// Two undeclared slices stood between the bar and the table:
///
///   * `categories` ended in `.prefix(15)`, **by all-cohort outcomes**;
///   * `topCategoryRows` then took `.prefix(10)`, **by ECE**.
///
/// Measured against `/api/calibration` on 2026-09-20: **21 categories cleared
/// the bar and 10 were drawn.** The 11 in the gap were in no list on the
/// screen — the niche card below is the backend's `small_sample_categories`,
/// the population *under* the bar, so a category that cleared the bar and lost
/// a slice appeared nowhere, while both lists read as exhaustive. Web had the
/// same defect with one slice and deleted it in #7302 (21 cleared, 15 drawn, 6
/// vanished); native carried a second one on top, so it dropped 11 where web
/// dropped 6.
///
/// ── THE SECOND SLICE ALSO CORRUPTED THE RANKING THE CAPTION PROMISES ────────
///
/// The two slices sorted on **different orderings**, so the outcomes slice
/// could cut a row that belonged in the ECE ranking — leaving "sorted by ECE"
/// over ten rows that are not the ten best by ECE. On the measured payload it
/// did exactly that: rank 7 of the drawn rows was Politics (8.3K, ECE 2.69)
/// where the uncapped ranking puts `other` (1,356, ECE 2.50) — better
/// calibrated, and cut for being smaller. That is #3650's finding arriving from
/// the other direction: a row's POSITION is a published claim.
///
/// ── WHY THE EXISTING GUARDS PASSED ──────────────────────────────────────────
///
/// `CalibrationSurfaceTests` proves the sample gate holds and
/// `CalibrationRowOrderingTests` proves the ECE ordering is correct **for the
/// rows it is handed**. Neither asserts anything about *how many* rows it is
/// handed, so a slice applied before the ordering was invisible to both. This
/// suite is about the population that reaches the table.
///
/// Every case below is a state of that population, not a happy path with
/// variations.
final class CategoryTableDrawsEveryEligibleCategory7533Tests: XCTestCase {

    // MARK: - Fixture

    private static let bar = 1000

    /// Categories that clear the bar, largest first. Sixteen of them, which is
    /// deliberately **more than fifteen**: the dropped `.prefix(15)` kept the 15
    /// largest, so a fixture with fifteen or fewer eligible categories passes
    /// every assertion below with the defect fully restored.
    private static let bulkCounts: [Int] = (0..<16).map { 5000 - $0 * 100 }   // 5000 … 3500

    /// The case the two slices interacted on: a category that clears the bar by
    /// the smallest margin and is **perfectly calibrated**, so it is last by
    /// outcomes and FIRST by ECE. `.prefix(15)` by outcomes cut it; the caption
    /// then claimed an ECE ranking whose best row was missing.
    private static let smallPerfectN = 1000

    /// Below the bar. It must stay out — this suite widens what the table draws
    /// and must not be able to pass by drawing everything.
    private static let underBarN = 400

    /// One bucket for one category. `avg_prob` is `sum_prob / n`; `actual` is
    /// `winners / n`; the row's error is the difference, so the calibration of
    /// each category is set purely by its winners.
    ///
    /// - Parameter winnersRate: `0.25` ⇒ error 0.0pp (perfect); `0.35` ⇒ 10.0pp
    ///   (`round1` renders the fraction as a 0.1-precision percent), the same
    ///   for every bulk category so the ordering below turns on the perfect row
    ///   and not on invented spread. Equal bulk ECEs tie, and
    ///   `CalibrationRowOrdering` breaks ties on name — deterministic, and not
    ///   something this suite asserts a position within.
    private static func bucket(_ category: String, n: Int, winnersRate: Double) -> String {
        let winners = Int((Double(n) * winnersRate).rounded())
        let sumProb = Double(n) * 0.25
        return """
        {"bucket_idx": 2, "source": "kalshi", "category": "\(category)", "price_moved": true, \
        "n": \(n), "winners": \(winners), "sum_prob": \(sumProb), "sum_sq_err": 1.0, \
        "ci_lower": 0.21, "ci_upper": 0.31}
        """
    }

    /// Synthetic category keys on purpose: `normalizedCategory` rolls real keys
    /// up through `sportKeyMap`, and two fixture keys quietly becoming one
    /// rollup would change the counts this suite asserts for a reason that has
    /// nothing to do with the slices.
    private static func payload() -> String {
        var rows = bulkCounts.enumerated().map { idx, n in
            bucket(String(format: "zbulk%02d", idx), n: n, winnersRate: 0.35)
        }
        rows.append(bucket("zsmallperfect", n: smallPerfectN, winnersRate: 0.25))
        rows.append(bucket("zunderbar", n: underBarN, winnersRate: 0.35))

        return """
        {
          "buckets": [\(rows.joined(separator: ",\n"))],
          "total_markets": 12,
          "total_outcomes": 100000,
          "total_winners": 35000,
          "mce_ci_lower": 0.6,
          "mce_ci_upper": 1.7,
          "mce_closing_line": 1.5,
          "mce_opening_price": 2.2,
          "generated_at": "2026-09-20T04:00:00+00:00",
          "min_category_outcomes": \(bar),
          "small_sample_categories": [
            {"category": "zunderbar", "outcomes": \(underBarN)}
          ],
          "date_range": {"start": "2021-07-13T00:00:00+00:00", "end": "2026-09-20T00:05:00+00:00"}
        }
        """
    }

    private static func decoded() throws -> CalibrationData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(CalibrationData.self, from: Data(payload().utf8))
    }

    @MainActor
    private func model() throws -> CalibrationViewModel {
        CalibrationViewModel(preloaded: try Self.decoded())
    }

    /// 16 bulk + 1 small-perfect. The count the whole suite is measured against.
    private static let eligibleCount = 17

    // MARK: - 1. Every eligible category reaches the table

    /// 🪤 This is the assertion that kills "restore the slice". With
    /// `.prefix(15)` the count is 15; with `.prefix(10)` on top of it, 10.
    @MainActor
    func testEveryCategoryThatClearsTheBarIsDrawn() throws {
        let vm = try model()

        XCTAssertEqual(vm.categories.count, Self.eligibleCount,
                       "a filter other than the publish bar is thinning the eligible set")
        XCTAssertEqual(vm.categoryRows.count, Self.eligibleCount,
                       "the table draws fewer rows than the bar admits: \(vm.categoryRows.map(\.category))")
    }

    /// The gap the report is named for, stated as the invariant rather than as a
    /// count: a category is either drawn or below the bar, and never neither.
    /// A future cap reopens the gap between two lists a reader reads as complete,
    /// and this fails when it does.
    @MainActor
    func testNoCategoryFallsBetweenTheDrawnTableAndTheBelowBarList() throws {
        let vm = try model()
        let drawn = Set(vm.categoryRows.map(\.category))

        // The eligible population computed independently of the view model's own
        // chain — straight off the decoded payload — so this cannot agree with
        // the table by sharing the defect with it.
        var allCohort: [String: Int] = [:]
        for b in try Self.decoded().buckets { allCohort[b.category, default: 0] += b.n }

        for (category, total) in allCohort where total >= Self.bar {
            XCTAssertTrue(drawn.contains(category),
                          "\(category) clears the bar at \(total) and is in neither list: it is not "
                              + "drawn, and the niche card below holds only categories UNDER the bar")
        }
    }

    // MARK: - 2. The bar still bites

    /// 🪤 The fix widens what the table draws, so the failure mode it introduces
    /// is drawing everything. A below-bar category must still be held out —
    /// otherwise the caption's one true claim becomes false too.
    @MainActor
    func testACategoryBelowTheBarIsStillHeldOut() throws {
        let vm = try model()

        XCTAssertFalse(vm.categories.contains("zunderbar"),
                       "the publish bar stopped filtering: a 400-outcome category is published")
        XCTAssertFalse(vm.categoryRows.contains { $0.category == "zunderbar" },
                       "a below-bar category reached the table as a graded row")
        XCTAssertTrue(vm.smallSampleCategories.contains { $0.category == "zunderbar" },
                      "...and it must not vanish either: it is accounted for below the bar")
    }

    // MARK: - 3. "Sorted by ECE" is true of the whole eligible set

    /// 🪤 The ordering defect, isolated. `zsmallperfect` is **last by outcomes**
    /// and **first by ECE**. Under `.prefix(15)` by outcomes it was cut before
    /// the ECE sort ever saw it, so the table promised a ranking whose best row
    /// was missing. This fails if either slice returns, and it fails for a
    /// different reason from case 1 — that one counts rows, this one reads
    /// position 1.
    @MainActor
    func testTheBestCalibratedCategoryIsNotCutForBeingTheSmallest() throws {
        let vm = try model()

        let first = try XCTUnwrap(vm.categoryRows.first)
        XCTAssertEqual(first.category, "zsmallperfect",
                       "the table says 'sorted by ECE' and its first row is not the best by ECE")
        XCTAssertEqual(try XCTUnwrap(first.ece), 0, accuracy: 0.000_001,
                       "the perfectly-calibrated fixture row is not reading as perfect")

        // It is genuinely the smallest eligible row, so case 1 and this case are
        // not the same assertion wearing two names.
        let smallest = try XCTUnwrap(vm.categoryRows.min { $0.n < $1.n })
        XCTAssertEqual(smallest.category, "zsmallperfect")
    }

    /// The headline cards rank over the same population as the table. With the
    /// slices in place "Best calibrated" named the best of an arbitrary subset,
    /// which is the table's defect promoted to a headline.
    @MainActor
    func testTheBestCalibratedCardRanksOverEveryEligibleCategory() throws {
        let vm = try model()

        XCTAssertEqual(try XCTUnwrap(vm.bestCategoryRow).category, "zsmallperfect",
                       "'Best calibrated' is naming the best of a subset, not of the published set")
        // `round1` renders a fraction as a 0.1-precision PERCENT, so a bulk
        // category's 0.35-vs-0.25 miss is 10.0pp, not 0.1.
        XCTAssertEqual(try XCTUnwrap(XCTUnwrap(vm.worstCategoryRow).ece), 10.0, accuracy: 0.05,
                       "'Needs attention' is not reading the worst eligible row")
    }

    // MARK: - 4. The caption and the table describe one array

    /// 🪤 The caption's `renderedRowOutcomes` and the `ForEach` must read the
    /// SAME property. They drifted apart once already — that is how a cap on
    /// `topCategoryRows` survived #7302's sweep of the cap on `categories` — so
    /// the relationship is asserted in source, not assumed.
    func testTheViewDrawsAndDescribesTheSameUncappedArray() throws {
        let view = try String(contentsOf: Self.viewURL, encoding: .utf8)

        XCTAssertTrue(view.contains("renderedRowOutcomes: viewModel.categoryRows.map(\\.n)"),
                      "the caption is keyed on something other than the rows the ForEach draws")
        XCTAssertTrue(view.contains("ForEach(Array(viewModel.categoryRows.enumerated())"),
                      "the table is drawing something other than the array the caption describes")
        XCTAssertFalse(view.contains("topCategoryRows"),
                       "the capped property is back in the view")
    }

    /// 🪤 The view model must not reintroduce either slice, under any name. Both
    /// literals are checked because the two caps were different numbers on
    /// different orderings and only one of them was ever web's.
    ///
    /// 🪤 The scan reads CODE ONLY. The doc comment above `categories` explains
    /// the removal by naming `.prefix(15)` and `.prefix(10)` in prose, so a scan
    /// over the raw file fails on the explanation of the fix — the defect
    /// reported by its own description. Stripping comment lines is the whole
    /// difference between a guard on the code and a guard on the writing about
    /// it; `codeOnly` is asserted non-trivial below.
    func testNeitherSliceIsBackInTheViewModel() throws {
        let vm = Self.codeOnly(try String(contentsOf: Self.viewModelURL, encoding: .utf8))

        XCTAssertFalse(vm.contains("var topCategoryRows"),
                       "the top-10 property is back")
        XCTAssertFalse(vm.contains(".prefix(15)"), "the outcomes slice is back")
        XCTAssertFalse(vm.contains(".prefix(10)"), "the ECE slice is back")
    }

    /// 🪤 `codeOnly` is the reason the case above can pass, so it gets its own
    /// proof: it must remove the prose mentions and keep the executable lines.
    /// A stripper that returned "" would make every `XCTAssertFalse` above
    /// vacuous.
    func testTheCommentStripperRemovesProseAndKeepsCode() throws {
        let raw = try String(contentsOf: Self.viewModelURL, encoding: .utf8)
        let code = Self.codeOnly(raw)

        XCTAssertTrue(raw.contains(".prefix(15)"),
                      "the doc comment that explains the removal is gone, so this case "
                          + "is no longer proving the stripper does anything")
        XCTAssertFalse(code.contains(".prefix(15)"), "the stripper left a comment mention behind")
        XCTAssertTrue(code.contains("var categoryRows: [CalCategoryRow] {"),
                      "the stripper ate executable code")
        XCTAssertGreaterThan(code.count, 8_000, "the stripper returned far too little to scan")
    }

    /// Source with `//` and `///` lines removed. Line-based on purpose: a real
    /// Swift comment parser would have to handle strings containing `//`, and
    /// this only ever reads one file whose comments are all whole-line.
    private static func codeOnly(_ source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// Strawman: the two scans above read real files with real content, so their
    /// `XCTAssertFalse`s cannot be passing because a read returned nothing.
    func testTheSourceScansAreReadingTheFilesTheyThinkTheyAre() throws {
        let view = try String(contentsOf: Self.viewURL, encoding: .utf8)
        let vm = try String(contentsOf: Self.viewModelURL, encoding: .utf8)

        XCTAssertGreaterThan(view.count, 20_000, "CalibrationView.swift read back far too small")
        XCTAssertGreaterThan(vm.count, 20_000, "CalibrationViewModel.swift read back far too small")
        XCTAssertTrue(view.contains("private var categoryBreakdownSection"),
                      "the section this suite is about is not in the file it read")
        XCTAssertTrue(vm.contains("var categoryRows: [CalCategoryRow]"),
                      "the property this suite is about is not in the file it read")
    }

    // MARK: - Paths

    /// 🪤 `#filePath` keeps the spelling the compiler was given while
    /// `FileManager` standardises it, so prefix arithmetic between the two eats
    /// the middle out of the path. Going up the URL avoids the subtraction.
    private static var sourceRoot: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck")
    }

    private static var viewURL: URL {
        sourceRoot.appendingPathComponent("Views/CalibrationView.swift")
    }

    private static var viewModelURL: URL {
        sourceRoot.appendingPathComponent("ViewModels/CalibrationViewModel.swift")
    }
}
