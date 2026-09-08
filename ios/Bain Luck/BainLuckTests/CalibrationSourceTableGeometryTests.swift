import XCTest
import SwiftUI
@testable import Bain_Luck

/// #3954 — every source name the Calibration table can print must draw in full at
/// phone width.
///
/// The names are read out of a real payload through `CalibrationViewModel`, never
/// written as literals here: the display mapping is production's
/// (`sourceDisplayNames`, private), and a copy of it in a test would keep passing
/// after the real one grew a longer entry — which is exactly the change that would
/// re-open this issue.
@MainActor
final class CalibrationSourceTableGeometryTests: XCTestCase {

    /// The four literals this fix removed: 54 + 48 + 46 + 52 = 200pt, sized for the
    /// widest value the table can ever hold and charged to the label on every row.
    private static let oldFixedWidths = CalibrationSourceTableGeometry.NumericWidths(
        n: 54, ece: 48, mce: 46, brier: 52)

    /// The widths the shipping table computes for `rows` + the Combined footer.
    ///
    /// Mirrors `CalibrationSurfaceView.sourceNumericWidths`. It is a mirror rather
    /// than a call because that property is private to the view; the strings it is
    /// built from are the model's, so a formatting change still reaches this test.
    private func widths(
        for rows: [CalSourceRow], cohort: (n: String, ece: Double, mce: Double, brier: Double),
        typeSize: DynamicTypeSize = .large
    ) -> CalibrationSourceTableGeometry.NumericWidths {
        func metric(_ value: Double?, _ format: String) -> String {
            guard let value else { return "\u{2014}" }
            return String(format: format, value)
        }
        func fmtN(_ n: Int) -> String {
            n >= 1000 ? String(format: "%.1fK", Double(n) / 1000) : "\(n)"
        }
        return CalibrationSourceTableGeometry.numericWidths(
            n: [cohort.n] + rows.map { fmtN($0.n) },
            ece: [String(format: "%.1f", cohort.ece)] + rows.map { metric($0.ece, "%.1f") },
            mce: [String(format: "%.1f", cohort.mce)] + rows.map { metric($0.mce, "%.1f") },
            brier: [String(format: "%.3f", cohort.brier)] + rows.map { metric($0.brier, "%.3f") },
            typeSize: typeSize)
    }

    /// A payload carrying every source key production has a display name for, plus
    /// the zero-outcome row (`datagolf`) that prints em dashes.
    ///
    /// The frozen production fixture is from 2026-08-02 and predates
    /// `odds_api_bookmaker` and `datagolf`, so it cannot see the two names that
    /// actually truncate. The bucket shape is the fixture's.
    /// Outcome counts shaped like the ones production serves, because THE COLUMN
    /// WIDTHS ARE A FUNCTION OF THE DIGITS IN THEM and a fixture of same-length
    /// numbers sizes a narrower table than the real one.
    ///
    /// Measured on the live surface, 2026-09-08: sources run 15.1K \u{2026} 219.0K
    /// and Combined is 437,910 \u{2014} a 6-character source cell under a
    /// 7-character footer. The first version of this fixture used 101.2K\u{2026}106.2K
    /// throughout, which understated the real MCE column by a character and made
    /// the render evidence look better than production.
    private static let productionShapedN = [219_000, 69_500, 17_600, 15_100, 15_500, 101_200]

    static let everySourcePayload: String = {
        let sources = [
            "kalshi", "polymarket", "odds_api",
            "odds_api_spreads", "odds_api_totals", "odds_api_bookmaker",
        ]
        let buckets = sources.enumerated().map { index, source in
            """
            {"bucket_idx": \(index + 1), "source": "\(source)", "category": "baseball_mlb", \
            "price_moved": true, "n": \(productionShapedN[index]), \
            "winners": \(productionShapedN[index] / 4 + index), \
            "avg_prob": 0.25, "sum_prob": \(productionShapedN[index] / 4).0, \
            "sum_sq_err": \(productionShapedN[index] / 5).0, \
            "ci_lower": 0.21, "ci_upper": 0.31}
            """
        } + [
            // n = 0: the withheld row, whose three metrics print "—".
            """
            {"bucket_idx": 8, "source": "datagolf", "category": "golf", "price_moved": true, \
            "n": 0, "winners": 0, "avg_prob": 0.5, "sum_prob": 0.0, "sum_sq_err": 0.0, \
            "ci_lower": 0.4, "ci_upper": 0.6}
            """
        ]
        let version = CalibrationRenderSmokeTests.renderableVersion
        return """
        {
          "population_version": "\(version)",
          "buckets": [\(buckets.joined(separator: ",\n"))],
          "total_markets": 40, "total_outcomes": 437910, "total_winners": 120000,
          "generated_at": "2026-09-08T04:00:00+00:00"
        }
        """
    }()

    private func everySourceModel() throws -> CalibrationViewModel {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try decoder.decode(CalibrationData.self, from: Data(Self.everySourcePayload.utf8))
        return CalibrationViewModel(preloaded: data)
    }

    /// The fixture is worthless if it does not actually contain the long names, and
    /// it would fail silently: six short names all fit, and the guard below would go
    /// green having proved nothing. Asserted first, by the same route the table uses.
    func testTheFixtureCarriesTheNamesThatTruncated() throws {
        let names = Set(try everySourceModel().sourceRows.map(\.name))
        XCTAssertTrue(names.contains("Per-sportsbook (Odds API)"),
                      "the longest source name is missing from the fixture; got \(names.sorted())")
        XCTAssertTrue(names.contains("Spreads (Odds API)"))
        XCTAssertTrue(names.contains("Totals (Odds API)"))
    }

    // MARK: - The way a measured column goes wrong

    /// A column must clear its HEADER, not only its values.
    ///
    /// `Brier` is wider than several of the numbers under it, and `MCE` is wider
    /// than a one-digit cell. Sizing on values alone compiles, passes the fit tests
    /// above (the label only gets wider) and silently truncates the header instead
    /// \u{2014} moving the defect one row up rather than fixing it.
    func testAColumnIsWideEnoughForItsHeaderNotJustItsValues() {
        let column = CalibrationSourceTableGeometry.columnWidth(
            header: "Brier", values: ["0.2"])
        let headerInk = CalibrationSourceTableGeometry.textWidth("Brier", font: .header)
        XCTAssertGreaterThanOrEqual(
            column, headerInk,
            "a Brier column holding only \"0.2\" came out \(Int(column.rounded()))pt, "
            + "narrower than the \(Int(headerInk.rounded()))pt the word \"Brier\" draws")
    }

    /// Larger text must widen the columns.
    ///
    /// The literals never did, which is the second half of the defect: every step
    /// above `.large` drew wider numbers inside the same 200pt and clipped them.
    /// `.caption` resolves against the view's `dynamicTypeSize`, so a model that
    /// reads the app-level setting instead measures a different font from the one
    /// on screen.
    func testTheColumnsWidenWithDynamicType() throws {
        let model = try everySourceModel()
        let cohort = (model.formattedCohortOutcomes, model.cohortECE,
                      model.cohortMCE, model.cohortBrier)
        let atLarge = widths(for: model.sourceRows, cohort: cohort, typeSize: .large)
        let atAccessibility = widths(
            for: model.sourceRows, cohort: cohort, typeSize: .accessibility3)
        XCTAssertGreaterThan(
            atAccessibility.total, atLarge.total,
            "the columns measured \(Int(atAccessibility.total.rounded()))pt at "
            + "accessibility3 against \(Int(atLarge.total.rounded()))pt at large \u{2014} "
            + "the type size is not reaching the measurement, so the numbers will be "
            + "drawn wider than the boxes holding them")
    }

    // MARK: - The ship, measured against ink rather than arithmetic

    /// The columns really did give width back \u{2014} the point of measuring them.
    ///
    /// 200pt \u{2192} 157.2pt at `.large`, all of it handed to the label. That
    /// 42.8pt is what turns `Spreads (Odds\u{2026}` back into `Spreads (Odds API)`.
    func testTheMeasuredColumnsAreNarrowerThanTheLiteralsTheyReplaced() throws {
        let model = try everySourceModel()
        let columns = widths(
            for: model.sourceRows,
            cohort: (model.formattedCohortOutcomes, model.cohortECE,
                     model.cohortMCE, model.cohortBrier))
        XCTAssertLessThan(
            columns.total, Self.oldFixedWidths.total,
            "the measured columns took \(Int(columns.total.rounded()))pt against the "
            + "literals' \(Int(Self.oldFixedWidths.total))pt \u{2014} no width was freed "
            + "for the label")
    }

    /// The table lays out at every phone width without collapsing, and the width
    /// actually reaches the layout.
    ///
    /// THIS IS NOT THE TRUNCATION GUARD, and saying so matters: a raster assertion
    /// cannot read text, so the claim "every name draws in full at 393pt" is carried
    /// by the screenshots on the PR, not by this test. What an arithmetic model
    /// claimed about that today was wrong by about 21pt in the safe-looking
    /// direction \u{2014} it reported the label had 148pt when the render proves it
    /// had under 127 \u{2014} which is why the fit assertions it supported were
    /// deleted rather than loosened. A guard that mispredicts is worse than no
    /// guard, because it answers the question anyway.
    func testTheTableRendersAtEveryPhoneWidthAndReflowsWithIt() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try decoder.decode(
            CalibrationData.self, from: Data(Self.everySourcePayload.utf8))

        var rasters: [Double: Data] = [:]
        for width in [375.0, 393.0, 402.0] {
            let view = CalibrationSurfaceView(
                viewModel: CalibrationViewModel(preloaded: data), scrolls: false)
                .frame(width: width)
            let renderer = ImageRenderer(content: view)
            renderer.scale = 2
            let image = try XCTUnwrap(renderer.uiImage, "\(width)pt produced no raster")
            XCTAssertEqual(image.size.width, width, accuracy: 1,
                           "\(width)pt did not fill its canvas")
            XCTAssertGreaterThan(image.size.height, 100, "\(width)pt collapsed")
            rasters[width] = try XCTUnwrap(image.pngData())
        }
        XCTAssertNotEqual(
            rasters[375.0], rasters[402.0],
            "375pt and 402pt rasterised identically \u{2014} the width is not reaching "
            + "the table, so nothing below it is being measured at the width it claims")
    }
}
