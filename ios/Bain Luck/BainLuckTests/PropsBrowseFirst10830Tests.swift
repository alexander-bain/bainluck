import XCTest
@testable import Bain_Luck

/// #10830, Alex 10/10: "how could they possibly know what to type into this
/// field? We need to give them clear options." The props browser leads with a
/// labelled Stat chooser; these pin the rules behind it.
///
/// The other half of each test is what the chooser may NOT do: drop a family
/// a reader could only reach by typing, or print the protected contract with
/// the same words as plain touchdowns.
final class PropsBrowseFirst10830Tests: XCTestCase {

    /// The chooser prints what the protected contract counts and ties its rule
    /// to the chip; the family key ("Protected TDs") is never what a reader sees.
    func testTheProtectedChipSaysWhatItCountsAndCarriesItsRule() {
        let key = PlayerPropsFamily.protectedTouchdownFamily
        XCTAssertEqual(PlayerPropsFamily.chooserTitle(family: key), "Touchdowns scored")
        XCTAssertEqual(PlayerPropsFamily.chooserNote(family: key), "Participation rule")
        XCTAssertNotEqual(PlayerPropsFamily.chooserTitle(family: key), key)
    }

    /// Every other family prints its own stat words and carries no rule —
    /// including plain touchdowns and an unverified "(Protected)" stat.
    func testOtherFamiliesKeepTheirWordsAndCarryNoRule() {
        for family in ["Touchdowns", "Receiving Yards", "Receiving Yards (Protected)",
                       PlayerPropsFamily.unpricedFamily] {
            XCTAssertEqual(PlayerPropsFamily.chooserTitle(family: family), family)
            XCTAssertNil(PlayerPropsFamily.chooserNote(family: family), family)
        }
    }

    /// Protected and plain touchdowns stay two distinguishable choices: what a
    /// reader (or VoiceOver) is told about each differs.
    func testProtectedAndPlainTouchdownsAreTwoDistinctChoices() {
        let plain = PlayerPropsFamily.family(statLabel: "Touchdowns", isPriced: true)
        let protected = PlayerPropsFamily.protectedTouchdownFamily
        func told(_ f: String) -> String {
            [PlayerPropsFamily.chooserTitle(family: f), PlayerPropsFamily.chooserNote(family: f) ?? ""]
                .joined(separator: "|")
        }
        XCTAssertNotEqual(told(plain), told(protected))
    }

    /// Chips in the open up to the limit, a labelled menu past it, and always a
    /// menu at accessibility text (one chip can outgrow the screen there).
    func testTheChooserBecomesAMenuOnlyWhenChipsWouldNotFit() {
        let limit = MarketBrowserLogic.chooserChipLimit
        XCTAssertFalse(MarketBrowserLogic.choosesFromMenu(groupCount: 2, accessibilityText: false))
        XCTAssertFalse(MarketBrowserLogic.choosesFromMenu(groupCount: limit, accessibilityText: false))
        XCTAssertTrue(MarketBrowserLogic.choosesFromMenu(groupCount: limit + 1, accessibilityText: false))
        XCTAssertTrue(MarketBrowserLogic.choosesFromMenu(groupCount: 2, accessibilityText: true))
    }

    /// With NO query, choosing each family in turn reaches every item: nothing
    /// in the collection needs typing to reach.
    func testEveryItemIsReachableFromTheChooserAlone() {
        let names = ["Protected TDs", "Touchdowns", "Passing Yards", "Touchdowns",
                     "Receptions", PlayerPropsFamily.unpricedFamily, "Passing Yards"]
        let texts = names.indices.map { "player\($0)" }
        var reached = Set<Int>()
        for family in MarketBrowserLogic.groups(names) {
            reached.formUnion(MarketBrowserLogic.matchingIndices(
                groupNames: names, searchTexts: texts, query: "", selected: family))
        }
        XCTAssertEqual(reached, Set(names.indices))
    }
}
