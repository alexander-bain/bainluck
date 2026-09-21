import XCTest
@testable import Bain_Luck

/// #7722 — the Accuracy screen's Category Breakdown printed two database keys.
///
/// | Category | Outcomes |
/// |---|---|
/// | **Aussierules Afl** | 1.2K |
/// | **Rugbyleague Nrl** | 1.2K |
///
/// Web printed **AFL** and **NRL** for the same two rows on the same payload.
///
/// ## The defect is the FALLBACK, not two missing labels
///
/// `frontend/lib/calibrationCategories.ts` records the mechanism in its own
/// header, and it is a scheduled failure rather than an oversight:
///
/// > the page has a SCHEDULED failure mode — a category renders correctly until
/// > the day it grows past the 1,000-outcome floor without a map entry, and then
/// > prints a database identifier at a reader. Nothing on our side changes when
/// > it fires; the trigger is upstream data growth.
///
/// Web answered it with BOTH halves — a curated label, *and* a fallback that
/// cannot emit a raw key (`DISPLAY_NAMES[cat] || nicheCatLabel(cat)`). This app
/// shipped the map and a BARE title-caser, so it kept the mechanism. Both keys
/// crossed the floor upstream and both reached a reader.
///
/// So the assertion that closes this is not "AFL renders AFL". It is
/// `testTheFallbackIsTheLeagueAwareLabeller`: whatever a published key the map
/// does not carry renders as, it renders through the same labeller web uses.
///
/// ## The measured population
///
/// The 21 rows the Category Breakdown published on `GET /api/calibration`,
/// 2026-09-21 13:45Z, at `min_category_outcomes` 1000. These are POST-rollup
/// keys — what `categoryRows` actually draws — not raw payload keys, and the
/// two differ sharply (39 raw keys clear the bar, 21 rows survive
/// `normalizedCategory`). Re-measure with:
///
/// ```
/// curl -s "$BAINLUCK_API/api/calibration" \
///   | python3 -c "…sum b['n'] by normalizedCategory(b['category']), keep >= 1000…"
/// ```
///
/// 🔴 Deliberately NOT derived from a fixture, for the reason
/// `CalibrationDisplayNameTests` states about `productionSourceKeys`: a fixture
/// cannot carry the key nobody thought to add to the fixture, and arriving as an
/// unanticipated key IS this defect. Both offenders below are absent from every
/// fixture in the suite.
@MainActor
final class CalibrationPublishedCategoryLabelTests7722: XCTestCase {

    private static let publishedCategories = [
        "baseball", "soccer", "basketball", "tennis", "weather", "football",
        "table_tennis", "hockey", "esports", "golf", "politics", "economics",
        "entertainment", "mma", "motorsports", "tech", "cricket", "geopolitics",
        "rugbyleague_nrl", "aussierules_afl", "other",
    ]

    /// The three of those 21 that the explicit map does not carry — the only
    /// rows whose label comes from the fallback, and therefore the only rows
    /// this ship can move. `other` was already correct and the two league keys
    /// were the defect, which is the pairing that keeps the sweep below
    /// meaningful rather than tautological: a rule that condemned all three
    /// would be a rule about underscores, not about raw keys reaching readers.
    private static let fallbackCategories = [
        "rugbyleague_nrl", "aussierules_afl", "other",
    ]

    // MARK: - 0. The sweeps are about something

    /// 🔴 Both sweeps below iterate a list, and a list can be emptied. Every
    /// `for … in` assertion in this file passes against an empty population, so
    /// without this the population itself is the soft spot: delete three strings
    /// and the guard goes green while the screen goes wrong. Asserted as a count
    /// and by name, because "non-empty" would still admit the wrong three.
    func testTheSweptPopulationsAreNotEmptyAndAreAboutTheOffendingRows() {
        XCTAssertEqual(Self.publishedCategories.count, 21,
                       "the published set moved — re-measure it before trusting this file")
        XCTAssertEqual(Self.fallbackCategories.count, 3,
                       "the uncurated set moved — re-measure it before trusting this file")
        for key in ["aussierules_afl", "rugbyleague_nrl"] {
            XCTAssertTrue(Self.publishedCategories.contains(key),
                          "'\(key)' has left the population this file is about")
            XCTAssertTrue(Self.fallbackCategories.contains(key),
                          "'\(key)' is no longer swept as an uncurated row")
        }
        for key in Self.fallbackCategories {
            XCTAssertTrue(Self.publishedCategories.contains(key),
                          "'\(key)' is swept as a published row and is not one")
        }
    }

    // MARK: - 1. The defect

    func testTheTwoRowsThatPrintedDatabaseKeysNowNameTheirLeague() {
        XCTAssertEqual(CalibrationViewModel.categoryDisplayName("aussierules_afl"), "AFL")
        XCTAssertEqual(CalibrationViewModel.categoryDisplayName("rugbyleague_nrl"), "NRL")
    }

    /// Guard on the guard: pin what the screenshot showed, so the assertions
    /// above are known to be about a string that really was rendered. If the
    /// bare title-caser ever starts producing "AFL" on its own, this fails and
    /// tells the reader the test has stopped being about anything.
    func testTheBareTitleCaserStillProducesExactlyWhatTheReaderSaw() {
        XCTAssertEqual(toTitleCaseAcronymSafe("aussierules_afl"), "Aussierules Afl")
        XCTAssertEqual(toTitleCaseAcronymSafe("rugbyleague_nrl"), "Rugbyleague Nrl")
        for key in ["aussierules_afl", "rugbyleague_nrl"] {
            XCTAssertNotEqual(
                CalibrationViewModel.categoryDisplayName(key), toTitleCaseAcronymSafe(key),
                "'\(key)' is still being rendered by the formatter that printed the raw key"
            )
        }
    }

    // MARK: - 2. The class

    /// **The ship.** A published category the map does not carry is named by the
    /// LEAGUE-AWARE labeller — the Swift twin of the `nicheCatLabel` web falls
    /// through to — and not by the bare title-caser. Stated over the whole
    /// published set rather than over the two offenders, so the next key to
    /// cross the 1,000-outcome floor inherits the fix instead of reproducing the
    /// defect.
    func testTheFallbackIsTheLeagueAwareLabeller() {
        for key in Self.fallbackCategories {
            XCTAssertEqual(
                CalibrationViewModel.categoryDisplayName(key), nicheCategoryLabel(key),
                "the table's fallback for '\(key)' is not the labeller web uses"
            )
        }
    }

    /// The same rule as a reader-facing claim: **no published row prints a bare
    /// prettification of its own database key.** A compound key either has a
    /// curated label or the labeller renamed it into something that is not just
    /// the underscore swapped for a space.
    ///
    /// `table_tennis` is why this is scoped to keys the map does not carry: its
    /// prettification is genuinely the right label, web curates it for exactly
    /// that reason, and a rule that condemned it would be a rule about
    /// underscores rather than about raw keys reaching readers.
    func testNoPublishedRowPrintsABarePrettifiedCompoundKey() {
        let compound = Self.publishedCategories.filter { $0.contains("_") }
        XCTAssertEqual(Set(compound), ["table_tennis", "rugbyleague_nrl", "aussierules_afl"],
                       "the published set has changed shape — re-measure before trusting this sweep")

        for key in compound where Self.fallbackCategories.contains(key) {
            XCTAssertNotEqual(
                CalibrationViewModel.categoryDisplayName(key), toTitleCaseAcronymSafe(key),
                "'\(key)' reaches a reader as its own payload key, prettified: "
                    + "'\(CalibrationViewModel.categoryDisplayName(key))'"
            )
        }

        // The map-carried remainder: a curated label MAY coincide with the
        // prettification — `table_tennis` does, on both surfaces — so the only
        // thing to require of it is that it is a label and not a key.
        for key in compound where !Self.fallbackCategories.contains(key) {
            XCTAssertFalse(CalibrationViewModel.categoryDisplayName(key).contains("_"))
        }
    }

    func testEveryPublishedRowRendersCleanly() {
        for key in Self.publishedCategories {
            let label = CalibrationViewModel.categoryDisplayName(key)
            XCTAssertFalse(label.isEmpty, "'\(key)' rendered an empty label")
            XCTAssertFalse(label.contains("_"), "'\(key)' rendered a raw key: '\(label)'")
            let initial = String(label.prefix(1))
            XCTAssertEqual(initial, initial.uppercased(),
                           "'\(key)' rendered lowercase-initial: '\(label)'")
        }
    }

    /// The published rows that already read correctly must be untouched by
    /// re-pointing the fallback — this is the whole of the blast radius, stated
    /// as an assertion rather than as a claim in a PR body.
    func testRepointingTheFallbackMovedOnlyTheTwoOffendingRows() {
        let expected = [
            "baseball": "Baseball", "soccer": "Soccer", "basketball": "Basketball",
            "tennis": "Tennis", "weather": "Weather", "football": "Football",
            "table_tennis": "Table Tennis", "hockey": "Hockey", "esports": "Esports",
            "golf": "Golf", "politics": "Politics", "economics": "Economics",
            "entertainment": "Entertainment", "mma": "MMA", "motorsports": "Motorsports",
            "tech": "Tech", "cricket": "Cricket", "geopolitics": "Geopolitics",
            "other": "Other",
        ]
        for (key, label) in expected {
            XCTAssertEqual(CalibrationViewModel.categoryDisplayName(key), label)
        }
        XCTAssertEqual(Set(expected.keys).union(["aussierules_afl", "rugbyleague_nrl"]),
                       Set(Self.publishedCategories),
                       "a published row is neither pinned unchanged nor named as one that moved")
    }

    // MARK: - 3. The #7532 trap

    /// 🔴 The tempting fix is a bare `"aussierules"` / `"rugbyleague"` entry in
    /// `categoryDisplayNames`, and it is the #7532 defect. `normalizedCategory`
    /// rolls a key up to its base **only if the base is in that map**, so adding
    /// the parent would collapse AFLW and every other variant onto one label —
    /// and would silently re-group the buckets the table counts.
    ///
    /// Both halves are asserted: the parent is not a label, and it is not a
    /// grouping key either.
    func testTheParentKeysAreStillAbsentFromTheMap() {
        for (variant, sibling) in [("aussierules_aflw", "AFL"), ("rugbyleague_super_league", "NRL")] {
            XCTAssertEqual(CalibrationViewModel.normalizedCategory(variant), variant,
                           "'\(variant)' now rolls up — a parent key was added to the map")
            XCTAssertNotEqual(CalibrationViewModel.categoryDisplayName(variant), sibling,
                              "'\(variant)' is wearing its sibling league's name")
        }
    }

    /// Adding leaf labels must not change how buckets are GROUPED. `categories`
    /// and `categoryRows` both key on `normalizedCategory`, so a rollup that
    /// moved would change the numbers beside the names as well as the names.
    func testTheGroupingKeysAreUnchanged() {
        for key in Self.publishedCategories {
            XCTAssertEqual(CalibrationViewModel.normalizedCategory(key), key,
                           "'\(key)' no longer normalises to itself, so the row it counts moved")
        }
    }

    // MARK: - 4. One name per category, published or parked

    /// A category does not change its name on the day it crosses the bar. Both
    /// keys sat below the floor as chips before upstream growth published them;
    /// the chip named them by their own tokens then, and the table does now.
    ///
    /// This does not breach L2-103 Item 3b (a chip must not print a PUBLISHED
    /// PARENT's name): neither key rolls up, so the name it shares is its own.
    func testAChipAndATableRowNameACompoundKeyIdentically() {
        for key in ["aussierules_afl", "rugbyleague_nrl"] {
            XCTAssertEqual(CalibrationViewModel.nicheDisplayName(key),
                           CalibrationViewModel.categoryDisplayName(key))
            XCTAssertEqual(CalibrationViewModel.normalizedCategory(key), key,
                           "guard on the guard: this only holds because '\(key)' has no parent")
        }
    }
}
