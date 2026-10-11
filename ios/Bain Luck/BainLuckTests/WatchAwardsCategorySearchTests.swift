import Foundation
import XCTest
@testable import Bain_Luck

final class WatchAwardsCategorySearchTests: XCTestCase {
    // Local presentation values only; no new producer or production specimen.
    private var page: WatchAwardsPage {
        WatchAwardsPage(key: "event:awards:oscars-2027", name: "The Oscars 2027",
            categories: [
                .init(id: 101, name: "Best Picture", resultUnconfirmed: false),
                .init(id: 202, name: "Best Supporting Actor", resultUnconfirmed: true),
                .init(id: 303, name: "Best Supporting Actress", resultUnconfirmed: false),
                .init(id: 404, name: "Meilleur court métrage", resultUnconfirmed: true)
            ], isSaved: true, hasUnavailableCategories: true)
    }

    func testBlankSearchRestoresEveryAdmittedCategoryInOrder() {
        let value = page
        XCTAssertEqual(value.categories(matching: ""), value.categories)
        XCTAssertEqual(value.categories(matching: " \n\t"), value.categories)
    }

    func testPartialNamePreservesExactIDsFullNamesOrderAndUnconfirmedFlags() {
        let value = page
        let matches = value.categories(matching: " SUPPORTING \n")
        XCTAssertEqual(matches.map(\.id), [202, 303])
        XCTAssertEqual(matches, [value.categories[1], value.categories[2]])
        XCTAssertEqual(matches.map(\.resultUnconfirmed), [true, false])
    }

    func testAccentInsensitiveSearchAndNoMatchRemainLocal() {
        let value = page
        XCTAssertEqual(value.categories(matching: "metrage").map(\.id), [404])
        XCTAssertTrue(value.categories(matching: "not a category").isEmpty)
        XCTAssertEqual(value.categories(matching: "").map(\.id), [101, 202, 303, 404])
        XCTAssertEqual(value.key, "event:awards:oscars-2027")
        XCTAssertTrue(value.isSaved)
        XCTAssertTrue(value.hasUnavailableCategories)
    }

    func testSearchCannotInventAResultOrMatchMetadataInsteadOfAName() {
        let value = page
        XCTAssertTrue(value.categories(matching: "unconfirmed").isEmpty)
        XCTAssertTrue(value.categories(matching: "2027").isEmpty)
        let empty = WatchAwardsPage(key: value.key, name: value.name, categories: [],
                                   isSaved: false, hasUnavailableCategories: true)
        XCTAssertTrue(empty.categories(matching: "Picture").isEmpty)
        XCTAssertTrue(empty.hasUnavailableCategories)
    }
}
