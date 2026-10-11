import Foundation
import XCTest
@testable import Bain_Luck

final class WatchMyStuffSearchTests: XCTestCase {
    private var section: WatchMyStuffSnapshot.Section {
        .init(state: .failed, items: [
            .init(kind: "team", targetID: 71, relation: "follow", title: "Montréal team"),
            .init(kind: "team", targetID: 71, relation: "rival", title: "Montréal team"),
            .init(kind: "future", targetID: 71, relation: nil, title: "Montréal award?", unavailable: true),
            .init(kind: "event", targetID: 99, relation: nil, title: "Other game")
        ], syncedAt: Date(timeIntervalSince1970: 1_800_000_000), omittedCount: 9)
    }

    func testBlankSearchRestoresExactReceivedOrder() {
        let value = section
        XCTAssertEqual(value.items(matching: ""), value.items)
        XCTAssertEqual(value.items(matching: " \n\t"), value.items)
    }

    func testNameSearchRetainsDifferentRelationsAndKindsWithTheSameNumericID() {
        let value = section
        let matches = value.items(matching: " MONTREAL \n")
        XCTAssertEqual(matches.map(\.id), ["team:71:follow", "team:71:rival", "future:71:"])
        XCTAssertEqual(matches, Array(value.items.prefix(3)))
        XCTAssertTrue(matches[2].unavailable)
    }

    func testNoMatchDoesNotTurnFailedSyncIntoAnEmptyLoadedSection() {
        let value = section
        XCTAssertTrue(value.items(matching: "absent name").isEmpty)
        XCTAssertEqual(value.state, .failed)
        XCTAssertEqual(value.omittedCount, 9)
        XCTAssertEqual(value.syncedAt, Date(timeIntervalSince1970: 1_800_000_000))
        XCTAssertEqual(value.items(matching: "").count, 4)
    }

    func testSearchUsesTitlesAndKeepsPendingAndUnsupportedItems() {
        var value = section
        value.state = .pending
        value.items.append(.init(kind: "unsupported", targetID: 55, relation: nil,
                                 title: "Montréal saved item"))
        XCTAssertTrue(value.items(matching: "rival").isEmpty)
        XCTAssertEqual(value.items(matching: "saved item").map(\.id), ["unsupported:55:"])
        XCTAssertEqual(value.state, .pending)
        let empty = WatchMyStuffSnapshot.Section(state: .loaded, items: [], omittedCount: 3)
        XCTAssertTrue(empty.items(matching: "team").isEmpty)
        XCTAssertEqual(empty.omittedCount, 3)
    }
}
