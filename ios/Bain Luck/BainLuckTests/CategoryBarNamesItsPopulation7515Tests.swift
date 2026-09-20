import XCTest
@testable import Bain_Luck

/// native (#7515) — the accuracy screen's category caption names the population
/// its publish bar counts.
///
/// **What the caption did.** It stated a bar ("Categories below 1.0K resolved
/// outcomes are held out") directly above a column counted on a *different*
/// population, and named neither. Eligibility is decided on the **all-cohort**
/// count (#7195/#7302); the Outcomes column is **cohort-scoped** (#7190). In the
/// default traded view the bar therefore counts a superset of what the column
/// prints — measured on `/api/calibration` 2026-09-20 14:05Z, Soccer is 132,357
/// all-cohort and 58,440 traded — and nothing on the card let a reader tell that
/// from a stuck number.
///
/// **The consequence is live on web and latent here**, which is why the second
/// clause is keyed on data rather than switched on. `geopolitics` is 1,749
/// all-cohort / **732** traded against a 1,000 bar, and web publishes that row.
/// Native's table takes the 15 largest categories by all-cohort outcomes and
/// then the top 10 of those by ECE, and `geopolitics` is 19th of the 21 that
/// clear the bar, so it does not reach this screen today. A clause hard-wired on
/// would be a permanent paragraph about a row nobody can see (notice 34); a
/// clause hard-wired off is the defect. It is gated on the rendered counts, so
/// it says something true on both surfaces and on tomorrow's payload.
///
/// Every case below is a state of the two populations, not a happy path with
/// variations.
final class CategoryBarNamesItsPopulation7515Tests: XCTestCase {

    /// The clause the niche card on web has carried since #7195, word for word.
    /// One bar, one vocabulary — a reader who meets the bar twice on one page
    /// must not meet it two different ways.
    private static let unitsClause = "That bar counts every resolved outcome, traded or not"

    // MARK: - The units clause is unconditional

    /// The bar's population is a fact about the bar, so it is stated whether or
    /// not a row is currently contradicting it.
    ///
    /// 🪤 This is the assertion that kills "restore the defect": the shipped
    /// caption before #7515 ended at "— see below." and said nothing about which
    /// outcomes the bar counted.
    func testTheBarNamesItsPopulationEvenWhenNoRowContradictsIt() {
        let note = CalibrationPopulation.categoryTableNote(
            bar: 1000, renderedRowOutcomes: [129_771, 118_714, 58_440, 22_684])

        XCTAssertTrue(note.contains(Self.unitsClause),
                      "the caption states a bar without saying which outcomes it counts: \(note)")
    }

    /// The same clause on the native top-10 as it actually renders today, so the
    /// suite carries the measured shape and not only invented ones.
    func testTodaysNativeTopTenGetsTheUnitsClauseAndNoWarning() {
        // Traded-cohort `n` for the ten rows `topCategoryRows` draws, measured
        // against `/api/calibration` on 2026-09-20 14:05Z in ECE order.
        let rendered = [129_771, 10_207, 118_714, 8_108, 22_684,
                        58_440, 8_329, 19_211, 13_872, 12_967]
        let note = CalibrationPopulation.categoryTableNote(bar: 1000, renderedRowOutcomes: rendered)

        XCTAssertTrue(note.contains(Self.unitsClause))
        XCTAssertFalse(note.contains("can show fewer than"),
                       "no row on this screen is below the bar today, so the warning is noise")
        XCTAssertTrue(note.hasSuffix("traded or not."),
                      "the unconditional clause must close the sentence when it is the last one")
    }

    // MARK: - The consequence clause is conditional on the rendered rows

    /// The web-visible case, on the row that produced the report: 732 under a
    /// 1,000 bar. If native's two slices ever stop hiding it, the caption
    /// answers the reader at the point of confusion instead of a session later.
    func testARowBelowTheBarEarnsTheClauseThatExplainsIt() {
        let note = CalibrationPopulation.categoryTableNote(
            bar: 1000, renderedRowOutcomes: [129_771, 58_440, 732])

        XCTAssertTrue(note.contains("so a row here can show fewer than 1.0K in the Outcomes column."),
                      "a sub-bar row is published with nothing to reconcile it: \(note)")
        XCTAssertTrue(note.contains(Self.unitsClause),
                      "the consequence replaced the units clause instead of extending it")
    }

    /// 🪤 A row sitting EXACTLY on the bar is published, so it is not below it.
    /// This is the boundary an `<=` would get wrong, and the only case that
    /// separates `<` from `<=`.
    func testARowExactlyOnTheBarIsNotBelowIt() {
        let note = CalibrationPopulation.categoryTableNote(
            bar: 1000, renderedRowOutcomes: [1000, 58_440])

        XCTAssertFalse(note.contains("can show fewer than"),
                       "a row AT the bar triggered a warning about rows BELOW it: \(note)")
    }

    /// A row the cohort emptied renders as `0` in the Outcomes column
    /// (`CalibrationRowOrdering` withholds its metrics, never the row), so it is
    /// a visible sub-bar row and earns the clause. An empty table has no row to
    /// warn about — the distinction a `renderedRowOutcomes.isEmpty` shortcut or
    /// an `allSatisfy` rewrite would collapse.
    func testAZeroOutcomeRowIsStillBelowTheBarAndOneEmptyTableIsNot() {
        let withheldRow = CalibrationPopulation.categoryTableNote(
            bar: 1000, renderedRowOutcomes: [58_440, 0])
        XCTAssertTrue(withheldRow.contains("can show fewer than"),
                      "a rendered row reading 0 IS below the bar and the reader can see it")

        let noRows = CalibrationPopulation.categoryTableNote(bar: 1000, renderedRowOutcomes: [])
        XCTAssertFalse(noRows.contains("can show fewer than"),
                       "a table with no rows has no row to warn about: \(noRows)")
        XCTAssertTrue(noRows.contains(Self.unitsClause),
                      "the bar is still stated when the table is empty")
    }

    // MARK: - The bar is the payload's, in the column's characters

    /// 🪤 The bar is Redis-tunable (#997) and arrives on the payload. A literal
    /// `1,000` baked into the prose would read correctly today and lie the first
    /// time the threshold moves — which is the whole reason `minCategoryOutcomes`
    /// is a payload field rather than a constant.
    func testTheStatedBarFollowsThePayloadRatherThanAHardCodedThousand() {
        let note = CalibrationPopulation.categoryTableNote(
            bar: 2500, renderedRowOutcomes: [58_440, 1_900])

        XCTAssertTrue(note.contains("Categories below 2.5K resolved outcomes are held out"),
                      "the caption quoted a bar the payload did not publish: \(note)")
        XCTAssertTrue(note.contains("fewer than 2.5K in the Outcomes column"),
                      "the warning quoted a different bar from the rule above it: \(note)")
        XCTAssertFalse(note.contains("1.0K"), "a hard-coded 1,000 survived in the copy: \(note)")
    }

    /// 🪤 Both mentions of the bar are the SAME characters, and they are the
    /// characters the Outcomes column prints. A caption saying "1,000" over a
    /// column reading "0.7K" gives the reader two numbers to compare and no way
    /// to compare them — the #7515 defect in different digits. This is what
    /// `compactCount` being shared with the view is for.
    func testTheCaptionQuotesTheBarInTheCharactersTheColumnPrints() {
        let bar = 1000
        let columnRendering = CalibrationPopulation.compactCount(bar)
        let note = CalibrationPopulation.categoryTableNote(bar: bar, renderedRowOutcomes: [732])

        XCTAssertEqual(columnRendering, "1.0K", "the shared count formatter changed under the caption")
        XCTAssertEqual(note.components(separatedBy: columnRendering).count - 1, 2,
                       "the rule and its consequence must quote one bar, identically: \(note)")
        XCTAssertFalse(note.contains("1,000"),
                       "the caption spelled the bar a second way: \(note)")
    }

    // MARK: - The view is wired to the derivation

    /// 🪤 The helper can be perfect and unreferenced. The caption has to be
    /// derived, and it has to be derived from the array the `ForEach` below it
    /// actually draws — a clause computed from a recomputed population would be
    /// describing rows that are not on screen.
    func testTheCaptionIsDerivedFromTheRowsTheTableDraws() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)

        XCTAssertTrue(body.contains("CalibrationPopulation.categoryTableNote("),
                      "Category Breakdown no longer derives its caption")
        XCTAssertTrue(body.contains("renderedRowOutcomes: viewModel.topCategoryRows.map(\\.n)"),
                      "the clause is keyed on something other than the rows the ForEach draws")
        XCTAssertTrue(body.contains("ForEach(Array(viewModel.topCategoryRows.enumerated())"),
                      "the table stopped drawing topCategoryRows, so the caption now describes "
                          + "an array that is not on screen")
        XCTAssertFalse(body.contains("resolved outcomes are held out — see below.\")"),
                       "the pre-#7515 literal caption is back in the view")
    }

    /// 🪤 The view's own `fmtN` delegates rather than keeping a second copy of
    /// the rule. Two formatters is how the caption and the column drift apart.
    func testTheViewSharesOneCountFormatterWithTheCaption() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)

        XCTAssertTrue(body.contains("CalibrationPopulation.compactCount(n)"),
                      "CalibrationView.fmtN stopped delegating to the shared formatter")
        XCTAssertFalse(body.contains("String(format: \"%.1fK\", Double(n) / 1000)"),
                       "a second copy of the count rule is back in the view")
    }

    /// Strawman: the scans above read a real file with real content, so the
    /// `XCTAssertFalse`s cannot be passing because a read returned nothing.
    func testTheSourceScanIsReadingTheFileItThinksItIs() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)
        XCTAssertGreaterThan(body.count, 20_000, "CalibrationView.swift read back far too small")
        XCTAssertTrue(body.contains("import SwiftUI"), "that is not the Swift file")
        XCTAssertTrue(body.contains("private var categoryBreakdownSection"),
                      "the section this suite is about is not in the file it read")
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given while
    /// `FileManager` standardises it, so prefix arithmetic between the two eats
    /// the middle out of the path. Going up the URL avoids the subtraction.
    private static var viewURL: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views/CalibrationView.swift")
    }
}
