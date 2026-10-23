import XCTest
@testable import Bain_Luck

/// #7074's original three-row floor remains; selected A (#9642) also seats
/// the fourth question rather than charging a tap to reveal one extra row.
final class SmallGroupsAreDrawnWhole7074Tests: XCTestCase {
    private typealias Card = DiscoverGroupRows

    func testAGroupOfFourOrFewerIsDrawnWholeWithoutATap() {
        for count in 1...4 {
            XCTAssertTrue(Card.showsEveryRow(itemCount: count, expanded: false))
            XCTAssertEqual(Card.visibleCount(itemCount: count, expanded: false), count)
        }
    }

    func testLargerGroupsSeatThreeQuestionsBeforeExpansion() {
        for count in 5...12 {
            XCTAssertFalse(Card.showsEveryRow(itemCount: count, expanded: false))
            XCTAssertEqual(Card.visibleCount(itemCount: count, expanded: false), 3)
        }
    }

    func testExpandingShowsEveryRowRatherThanStoppingAtSix() {
        for count in 1...12 {
            XCTAssertTrue(Card.showsEveryRow(itemCount: count, expanded: true))
            XCTAssertEqual(Card.visibleCount(itemCount: count, expanded: true), count)
        }
    }

    func testFourIsWholeAndFiveIsTheFirstCollapsedGroup() {
        XCTAssertEqual(Card.showsEveryRowUpTo, 4)
        XCTAssertTrue(Card.showsEveryRow(itemCount: 4, expanded: false))
        XCTAssertFalse(Card.showsEveryRow(itemCount: 5, expanded: false))
    }

    func testEmptyGroupCannotOfferExpansion() {
        XCTAssertEqual(Card.visibleCount(itemCount: 0, expanded: false), 0)
        XCTAssertTrue(Card.showsEveryRow(itemCount: 0, expanded: false))
        XCTAssertFalse(Card.canExpand(itemCount: 0, kind: nil))
        XCTAssertNil(Card.footerTitle(memberTypes: [], kind: nil, expanded: false))
    }

    private func members(_ count: Int, _ type: String = "futures") -> [String] {
        Array(repeating: type, count: count)
    }

    func testFooterNamesTheMembersAndShortThemesOpenFullCards() {
        let kinds: [String?] = [nil, "theme", "comparison"]
        for kind in kinds {
            XCTAssertEqual(Card.footerTitle(memberTypes: members(5), kind: kind, expanded: false), "All 5 markets")
            XCTAssertNil(Card.footerTitle(memberTypes: members(5), kind: kind, expanded: true))
        }
        for count in 1...4 {
            XCTAssertEqual(Card.footerTitle(memberTypes: members(count), kind: "theme", expanded: false), "Expand")
            XCTAssertTrue(Card.canExpand(itemCount: count, kind: "theme"))
            XCTAssertNil(Card.footerTitle(memberTypes: members(count), kind: "comparison", expanded: false))
            XCTAssertFalse(Card.canExpand(itemCount: count, kind: "comparison"))
        }
    }

    /// #10877 — web's `bundleExpandLabel`: every member a game says games, a
    /// mix gets no noun, and no footer ever says "questions".
    func testFooterSaysGamesForAllGamesAndNoNounForAMix() {
        XCTAssertEqual(Card.footerTitle(memberTypes: members(6, "event"), kind: "theme", expanded: false), "All 6 games")
        XCTAssertEqual(Card.footerTitle(memberTypes: members(4) + members(2, "event"), kind: "theme", expanded: false), "See all 6")
        XCTAssertEqual(Card.footerTitle(memberTypes: members(5, "event"), kind: "theme", expanded: true), nil)
        for count in 0...12 {
            for types in [members(count), members(count, "event"), members(count, "something_new")] {
                for kind in [nil, "theme", "comparison"] as [String?] {
                    let title = Card.footerTitle(memberTypes: types, kind: kind, expanded: false) ?? ""
                    XCTAssertFalse(title.localizedCaseInsensitiveContains("question"), title)
                }
            }
        }
    }
}
