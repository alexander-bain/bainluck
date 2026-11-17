import XCTest
@testable import Bain_Luck

/// #10873 / #12315 — unit tests for `SearchInBainLuckTerm10873` and search link
/// routing through `IntentRouteHandoff10873` + `NavigationCoordinator`.
@MainActor
final class SearchInBainLuck10873Tests: XCTestCase {

    func testEmptyOrWhitespaceTermPostsNothing() {
        XCTAssertNil(SearchInBainLuckTerm10873.destination(for: ""))
        XCTAssertNil(SearchInBainLuckTerm10873.destination(for: "   "))
        XCTAssertNil(SearchInBainLuckTerm10873.destination(for: "\n\t "))
    }

    func testWholePhraseMyStuffTermsRouteToMyStuff() {
        for phrase in [
            "My Stuff",
            "my stuff",
            "  MY   STUFF  ",
            "my saved games",
            "My Saved Games",
            "saved",
            "SAVED",
            "my pins",
            "My Pins",
        ] {
            XCTAssertEqual(
                SearchInBainLuckTerm10873.destination(for: phrase),
                IntentLinks10873.myStuff,
                "Expected My Stuff link for '\(phrase)'"
            )
        }
    }

    func testLongerPhraseStartingWithMyStuffSearchesInstead() {
        let dest = SearchInBainLuckTerm10873.destination(for: "my stuff tonight")
        XCTAssertNotEqual(dest, IntentLinks10873.myStuff)
        XCTAssertEqual(dest?.absoluteString, "bainluck://search?q=my%20stuff%20tonight")
    }

    func testTeamAndSpotlightTermsRouteToAppSearchAndCoordinatorConsumesThem() throws {
        for (raw, expected) in [
            ("Chiefs", "Chiefs"),
            ("  kc  ", "kc"),
            ("kansas city football", "kansas city football"),
        ] {
            let url = try XCTUnwrap(SearchInBainLuckTerm10873.destination(for: raw))
            let handoff = IntentRouteHandoff10873()
            XCTAssertTrue(handoff.post(url), "Handoff must accept \(url)")
            let consumed = try XCTUnwrap(handoff.consume())

            let nav = NavigationCoordinator()
            XCTAssertTrue(nav.handleURL(consumed))
            XCTAssertEqual(nav.selectedTab, .search)
            XCTAssertEqual(nav.consumeSearchQuery(), expected)
        }
    }
}
