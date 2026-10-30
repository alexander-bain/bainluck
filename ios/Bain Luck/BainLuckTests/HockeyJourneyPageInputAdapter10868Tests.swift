import XCTest
@testable import Bain_Luck

/// #10868 — the hockey journey screen's page input and its manual story
/// stream (part five). Pure composition: which stories are offered, which card
/// is shown, what Previous/Next name, and that the stream offers no playback,
/// dwell or automatic election. CONSTRUCTED: the stream state and the offered
/// set (part three's real inputs are tested in its own file).
@MainActor
final class HockeyJourneyPageInputAdapter10868Tests: XCTestCase {
    private typealias P = HockeyJourneyPageInputAdapter10868
    private let scope = "nhl:15169793:final"

    func testTheStreamShowsTheHeldCardNamesTheOtherAndOffersNoPlaybackOrDwell() {
        let stream = P.stream(scope: scope, offered: [.points, .assists], state: .init(displayed: .assists))
        XCTAssertEqual(stream.primary, .init(scope: scope, id: "assists"))
        XCTAssertEqual(stream.next, .init(scope: scope, id: "points"))
        XCTAssertEqual(stream.previous, .init(scope: scope, id: "points"))
        XCTAssertEqual(stream.position, "2 of 2")
        XCTAssertNil(stream.playback, "no owner auto-advances hockey stories, so no playback control is offered")
        XCTAssertNil(stream.dwellFraction)
        XCTAssertEqual(stream.status, "Use Previous or Next to see each story")
        XCTAssertEqual(stream.cards.map(\.id), ["points", "assists"])
    }

    func testAHeldCardNoLongerOfferedFallsBackToTheFirstOfferedNeverANeighbourGuess() {
        let stream = P.stream(scope: scope, offered: [.points], state: .init(displayed: .assists))
        XCTAssertEqual(stream.primary, .init(scope: scope, id: "points"))
        XCTAssertNil(stream.next)
        XCTAssertNil(stream.previous)
        XCTAssertNil(stream.companion)
        XCTAssertNil(stream.status, "one story needs no browsing words")
        XCTAssertEqual(stream.position, "1 of 1")
    }

    func testNoStoriesShowsNothingAndTheReaderStateSuppressesRequests() {
        let empty = P.stream(scope: scope, offered: [], state: .init())
        XCTAssertNil(empty.primary)
        XCTAssertNil(empty.position)
        let reading = P.stream(scope: scope, offered: [.points, .assists], state: .init(readerOpen: true, wide: true))
        XCTAssertTrue(reading.readerOpen)
        XCTAssertTrue(reading.wide)
    }

    func testStoriesLinkEachOfferedCardIdToItsLeafAndTheCopyCountsOriginals() {
        XCTAssertEqual(P.stories([.points, .assists]).map(\.cardID), ["points", "assists"])
        XCTAssertEqual(P.stories([.assists]).map(\.card), [.assists])
        XCTAssertEqual(P.copy(originalsCount: 149).allPropsLabel, "All 149 original outcomes")
        XCTAssertEqual(P.copy(originalsCount: 1).allPropsLabel, "1 original outcome")
        XCTAssertNil(P.copy(originalsCount: 0).allPropsLabel, "no originals: no entry")
        XCTAssertNil(P.copy(originalsCount: nil).allPropsLabel)
    }
}
