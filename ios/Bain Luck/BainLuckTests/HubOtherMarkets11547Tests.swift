import XCTest
@testable import Bain_Luck

/// #11547 — Alex, build 82: "What the heck is a "question"?!?!" A collection hub's
/// side-market section is "Other markets", the same name as the game page's
/// related-markets tab, and no section the hub names is a "question".
final class HubOtherMarkets11547Tests: XCTestCase {
    func testTheSideMarketSectionIsOtherMarkets() {
        XCTAssertEqual(ContainerHubPresentation.sectionTitle("side_question"), "Other markets")
    }

    func testNoHubSectionIsCalledAQuestion() {
        for sectionClass in ["match_winner", "prop", "title", "advancement", "side_question", "doubles", "unknown"] {
            XCTAssertFalse(ContainerHubPresentation.sectionTitle(sectionClass).lowercased().contains("question"), sectionClass)
        }
    }
}
