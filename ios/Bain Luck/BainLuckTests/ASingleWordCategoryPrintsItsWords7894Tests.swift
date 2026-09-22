import XCTest
@testable import Bain_Luck

/// #7894 — a payload key the upstream spells as ONE word reached readers as one
/// word with a capital on the front: **"Aussierules"**, and **"Xgames"**.
///
/// ## Where a reader met it
///
/// Search "Brisbane Lions" in the app. The Futures row read "Aussierules" while
/// the five event rows above it and both filter pills read "AFL" / "AFL
/// Women's" — one screen, two spellings of one league, and the wrong one under
/// the market a reader is being asked to trust
/// (`artifacts/native-295/n295-search-brisbane-scrolled.png`, production data,
/// 2026-09-22). That label comes from `sportCategoryDisplayName`, so the string
/// is not confined to the parked accuracy chips #7894 was filed about; the
/// issue's "whether the app renders parked categories at all is native's call"
/// is answered by the screenshot: the app prints it somewhere else entirely.
///
/// Production population by `llm_sport_category` (db-query, 2026-09-22):
/// `aussierules` **162** futures markets, `xgames` **1**.
///
/// ## Why neither labeller could get there on its own
///
/// Both are token-shaped. `raw.split("_")` on a key with no underscore is a
/// no-op, so the casing rule alone runs and yields "Aussierules" — which is
/// neither a raw key nor lowercase, so it passes every rule either labeller
/// enforces. That is why this survived #5723, #7532 and #7722: each of those
/// guards asks "did a key leak?", and no key leaked.
///
/// ## The shape of the fix, and the two maps it deliberately avoids
///
/// `singleWordCompounds` is a whole-key spelling consulted by BOTH labellers
/// before anything tokenizes — the mirror of web's `SINGLE_WORD_COMPOUNDS`,
/// consulted at the same point in `nicheCatLabel`. It is not an entry in
/// `sportFamilyDisplayNames` (that would drop `aussierules_afl`'s prefix) and
/// not one in the calibration page map (that would re-group the buckets the
/// accuracy table counts). `frontend/__tests__/ios/calibrationCategoryLabelParity7722.test.ts`
/// pins both absences from the web side; `testTheCompoundsStayOutOfTheTwoMapsThatWouldRegroupRows`
/// pins them here, where a Swift edit is made.
final class ASingleWordCategoryPrintsItsWords7894Tests: XCTestCase {

    // MARK: - The ship, on both call paths

    /// The photographed surface: search rows, Discover badges, futures cards —
    /// everything that goes through the app's one category labeller.
    func testTheSearchAndBadgeLabellerPrintsTheWords() {
        XCTAssertEqual(sportCategoryDisplayName("aussierules"), "Aussie Rules")
        XCTAssertEqual(sportCategoryDisplayName("xgames"), "X Games")
    }

    /// The accuracy screen's niche chips, the surface #7894 was filed from.
    func testTheNicheChipLabellerPrintsTheWords() {
        XCTAssertEqual(nicheCategoryLabel("aussierules"), "Aussie Rules")
        XCTAssertEqual(nicheCategoryLabel("xgames"), "X Games")
    }

    /// One spelling, two surfaces — the drift this map exists to make
    /// impossible. Asserted as EQUALITY of the two labellers rather than as two
    /// literals, so a future edit that fixes one of them alone fails here.
    func testBothLabellersAgreeOnEveryCompound() {
        for (key, words) in singleWordCompounds {
            XCTAssertEqual(sportCategoryDisplayName(key), words, "badge labeller disagrees on \(key)")
            XCTAssertEqual(nicheCategoryLabel(key), words, "chip labeller disagrees on \(key)")
        }
        XCTAssertEqual(singleWordCompounds.count, 2, "a new compound needs a line in this test's population note")
    }

    // MARK: - What the fix must NOT have moved

    /// `aussierules_afl` is curated on both surfaces and stays "AFL". A family
    /// entry would have derived it instead, and derivation is what #7722 fixed.
    func testTheCuratedLeagueKeyIsUntouched() {
        XCTAssertEqual(nicheCategoryLabel("aussierules_afl"), "AFL")
        XCTAssertEqual(nicheCategoryLabel("rugbyleague_nrl"), "NRL")
    }

    /// The compound map is a whole-key match, so a key that merely STARTS with
    /// a compound is unaffected — including the one the accuracy table counts
    /// separately.
    func testAKeyThatOnlyStartsWithACompoundIsUnaffected() {
        XCTAssertEqual(sportCategoryDisplayName("aussierules_afl"), "Aussierules Afl")
        XCTAssertEqual(nicheCategoryLabel("aussierules_aflw"), "Aussierules Aflw")
    }

    /// Both absences, pinned where the edit happens. `sportFamilyDisplayNames`
    /// would drop the prefix of every `aussierules_*` key; the calibration page
    /// map would roll those keys up onto one row.
    func testTheCompoundsStayOutOfTheTwoMapsThatWouldRegroupRows() {
        for key in singleWordCompounds.keys {
            XCTAssertNil(sportFamilyDisplayNames[key], "\(key) must not become a droppable sport family")
            XCTAssertNil(leagueAcronyms[key], "\(key) is a sport's name, not a league acronym")
        }
    }

    /// The neighbours on the same fallback arm, so "fix the arm" never becomes
    /// "re-case everything that reaches it". These keys are correct today and
    /// the compound map must not touch them.
    func testTheRestOfTheFallbackArmIsUnchanged() {
        XCTAssertEqual(sportCategoryDisplayName("table_tennis"), "Table Tennis")
        XCTAssertEqual(sportCategoryDisplayName("horse_racing"), "Horse Racing")
        XCTAssertEqual(sportCategoryDisplayName("darts"), "Darts")
        XCTAssertEqual(sportCategoryDisplayName("word_games"), "Word Games")
    }
}
