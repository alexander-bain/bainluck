import XCTest
@testable import Bain_Luck

/// L2-183 — the native acronym-safe title caser (mirror of
/// `frontend/lib/titleCase.ts`). Guards the "pga" -> "Pga" class the queue
/// called out, plus the underscore-key path the category-browse rail feeds it,
/// and confirms it reuses the shared `knownAcronyms` / `brandCasing` sets.
final class TextFormattingTests: XCTestCase {

    func testPreservesAcronymsOnLowercaseKeys() {
        XCTAssertEqual(toTitleCaseAcronymSafe("pga"), "PGA")
        XCTAssertEqual(toTitleCaseAcronymSafe("mma"), "MMA")
        XCTAssertEqual(toTitleCaseAcronymSafe("nba"), "NBA")
        XCTAssertEqual(toTitleCaseAcronymSafe("ufc"), "UFC")
    }

    // #1930 — tokens that reached the web list first now arrive through the
    // shared contract (CategoryAcronyms.generated.swift); a bare key must
    // shout on native exactly as it does on web.
    func testSharedCategoryAcronymsShout() {
        XCTAssertEqual(toTitleCaseAcronymSafe("epl"), "EPL")
        XCTAssertEqual(toTitleCaseAcronymSafe("npb"), "NPB")
        XCTAssertEqual(toTitleCaseAcronymSafe("kbo"), "KBO")
        XCTAssertEqual(toTitleCaseAcronymSafe("uefa"), "UEFA")
        XCTAssertEqual(toTitleCaseAcronymSafe("fifa"), "FIFA")
        XCTAssertEqual(toTitleCaseAcronymSafe("afc"), "AFC")
        XCTAssertEqual(toTitleCaseAcronymSafe("nfc"), "NFC")
    }

    func testUnderscoreKeysSplitAndTitleCase() {
        XCTAssertEqual(toTitleCaseAcronymSafe("pga_tour"), "PGA Tour")
        XCTAssertEqual(toTitleCaseAcronymSafe("horse_racing"), "Horse Racing")
        XCTAssertEqual(toTitleCaseAcronymSafe("auto_industry"), "Auto Industry")
    }

    func testPlainWordsStillTitleCase() {
        XCTAssertEqual(toTitleCaseAcronymSafe("politics"), "Politics")
        XCTAssertEqual(toTitleCaseAcronymSafe("best picture"), "Best Picture")
    }

    func testBrandCasingBeatsAcronymEntry() {
        // "occunet" is in BOTH knownAcronyms (OCCUNET) and brandCasing (OccuNet);
        // the brand form must win.
        XCTAssertEqual(toTitleCaseAcronymSafe("occunet"), "OccuNet")
    }

    func testEmptyInput() {
        XCTAssertEqual(toTitleCaseAcronymSafe(""), "")
    }

    // properTitleCase (the repair-only sibling) must still leave already-correct
    // mixed case alone while fixing garbled acronyms.
    func testProperTitleCaseRepairsAcronyms() {
        XCTAssertEqual(properTitleCase("Rbc Canadian Open"), "RBC Canadian Open")
    }
}
