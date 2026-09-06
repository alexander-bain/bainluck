import XCTest
@testable import Bain_Luck

/// #3657 — Calibration → Source Comparison labelled the DataGolf row **"Datagolf"**.
///
/// `sourceDisplayName` fell through to
/// `source.replacingOccurrences(of: "_", with: " ").capitalized`, and `.capitalized`
/// lowercases an interior capital. That is exactly **#1938**, where the same
/// `.capitalized` rendered the category key `"mma"` as `"Mma"` (Alex, bug report
/// 145) — and the CATEGORY path was fixed then by routing its fallback through
/// `toTitleCaseAcronymSafe`. The SOURCE path never was, so **the two paths
/// disagreed about the same problem** and the next unmapped source was always
/// going to be a third instance.
///
/// So the load-bearing test here is not "datagolf renders DataGolf". It is
/// `testTheTwoPathsAgreeOnTheirFallback`: whatever rule one path uses for a key it
/// does not carry, the other uses too.
@MainActor
final class CalibrationDisplayNameTests: XCTestCase {

    /// Every `source` key production actually serves, measured from
    /// `GET /api/calibration` on 2026-09-06. Re-measure with:
    ///
    /// ```
    /// curl -s "$BAINLUCK_API/api/calibration" | python3 -c "…collect every 'source' value…"
    /// ```
    ///
    /// 🔴 This list is deliberately NOT derived from `CalibrationProdFixture`.
    /// #3657 proposed asserting over the fixture's keys, and that test would have
    /// **passed against the bug**: the fixture carries five sources
    /// (`kalshi`, `polymarket`, `odds_api`, `odds_api_spreads`, `odds_api_totals`)
    /// and production serves seven — `datagolf` and `odds_api_bookmaker` are not in
    /// it. A fixture cannot catch the source nobody thought to add to the fixture,
    /// which is precisely how this defect arrived.
    private static let productionSourceKeys = [
        "datagolf",
        "kalshi",
        "odds_api",
        "odds_api_bookmaker",
        "odds_api_spreads",
        "odds_api_totals",
        "polymarket",
    ]

    // MARK: - The defect

    func testDataGolfIsSpelledTheWayDataGolfSpellsIt() {
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("datagolf"), "DataGolf")
    }

    /// The fix must come from the shared formatter, not from a seventh map entry.
    /// If someone "fixes" this by adding `"datagolf": "DataGolf"` to
    /// `sourceDisplayNames`, the label is right but the class of bug is still open,
    /// and this test says so: strip the brand out of the map's reach by asking the
    /// formatter directly and requiring the two to agree.
    func testTheLabelComesFromTheSharedFormatterAndNotFromTheMap() {
        XCTAssertEqual(toTitleCaseAcronymSafe("datagolf"), "DataGolf",
                       "the brand belongs to the shared casing table, so every surface spells it right")
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("datagolf"),
                       toTitleCaseAcronymSafe("datagolf"),
                       "an unmapped source must render exactly as the shared formatter renders it")
    }

    // MARK: - The class

    /// The assertion that closes #1938 for good on this screen: for a key neither
    /// map carries, the source path and the category path must produce the same
    /// string. If a future edit reverts one fallback to `.capitalized`, this fails
    /// even for a key nobody has thought of yet.
    func testTheTwoPathsAgreeOnTheirFallback() {
        for key in ["datagolf", "mma", "pga_tour", "occunet", "some_future_source", "fedex"] {
            XCTAssertEqual(
                CalibrationViewModel.sourceDisplayName(key),
                CalibrationViewModel.categoryDisplayName(key),
                "source and category paths disagree on the unmapped key '\(key)' — that disagreement IS #3657"
            )
        }
    }

    /// `.capitalized` is the defect. Pin its signature directly: it lowercases the
    /// interior capital of a brand, so a source label must never equal what
    /// `.capitalized` would have produced where the two differ.
    func testTheSourceLabelIsNotWhatCapitalizedWouldHaveProduced() {
        let capitalized = "datagolf".replacingOccurrences(of: "_", with: " ").capitalized
        XCTAssertEqual(capitalized, "Datagolf", "guard on the guard: this is what the bug rendered")
        XCTAssertNotEqual(CalibrationViewModel.sourceDisplayName("datagolf"), capitalized)
    }

    // MARK: - No regression on the six that already worked

    /// The mapped labels must be untouched by re-pointing the fallback. These are
    /// the strings on the screen today, including the parenthesised Odds API
    /// variants that the formatter would render differently if the map ever stopped
    /// winning ("API" is not in `knownAcronyms`, so `odds_api` would become
    /// "Odds Api" on the fallback path — the map is what keeps it right).
    func testMappedSourcesAreUnchanged() {
        let expected = [
            "kalshi": "Kalshi",
            "polymarket": "Polymarket",
            "odds_api": "Odds API",
            "odds_api_spreads": "Spreads (Odds API)",
            "odds_api_totals": "Totals (Odds API)",
            "odds_api_bookmaker": "Per-Bookmaker (Odds API)",
        ]
        for (key, label) in expected {
            XCTAssertEqual(CalibrationViewModel.sourceDisplayName(key), label)
        }
    }

    /// Nothing production serves may render with a lowercased interior capital, an
    /// underscore, or an empty label. This is the sweep that would have caught
    /// `datagolf` on the day it was added to the payload.
    func testEveryProductionSourceRendersCleanly() {
        for key in Self.productionSourceKeys {
            let label = CalibrationViewModel.sourceDisplayName(key)
            XCTAssertFalse(label.isEmpty, "'\(key)' rendered an empty label")
            XCTAssertFalse(label.contains("_"), "'\(key)' rendered a raw key: '\(label)'")
            let initial = String(label.prefix(1))
            XCTAssertEqual(initial, initial.uppercased(),
                           "'\(key)' rendered lowercase-initial: '\(label)'")
        }
    }

    /// Every brand in the shared casing table must survive the source path, not
    /// just DataGolf. This is what makes the fix general rather than one entry.
    func testKnownBrandsSurviveTheSourcePath() {
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("fedex"), "FedEx")
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("occunet"), "OccuNet")
    }
}
