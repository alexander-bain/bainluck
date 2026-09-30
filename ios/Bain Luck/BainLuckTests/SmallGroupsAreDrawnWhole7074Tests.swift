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
        XCTAssertNil(Card.footerTitle(itemCount: 0, kind: nil, expanded: false))
    }

    func testFooterNamesAllQuestionsAndShortThemesOpenFullCards() {
        let kinds: [String?] = [nil, "theme", "comparison"]
        for kind in kinds {
            XCTAssertEqual(Card.footerTitle(itemCount: 5, kind: kind, expanded: false), "All 5 questions")
            XCTAssertNil(Card.footerTitle(itemCount: 5, kind: kind, expanded: true))
        }
        for count in 1...4 {
            XCTAssertEqual(Card.footerTitle(itemCount: count, kind: "theme", expanded: false), "Expand")
            XCTAssertTrue(Card.canExpand(itemCount: count, kind: "theme"))
            XCTAssertNil(Card.footerTitle(itemCount: count, kind: "comparison", expanded: false))
            XCTAssertFalse(Card.canExpand(itemCount: count, kind: "comparison"))
        }
    }
}
