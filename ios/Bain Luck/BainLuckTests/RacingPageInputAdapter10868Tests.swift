import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the racing adapter, part four (the whole page input), on the REAL
/// retained Singapore Grand Prix driver-winner bodies before and after the race
/// (`RacingAdapterFixtures10868`), read through the composed screen's own model
/// (`RacingEventPageModel10868`).
///
/// CONSTRUCTED here, and only here: the reader's calendar and `now`, the host's
/// stream state, and the originals count.
@MainActor
final class RacingPageInputAdapter10868Tests: XCTestCase {
    private typealias A = RacingPageInputAdapter10868
    private typealias Page = RacingFieldPageAdapter10868
    private typealias F = RacingAdapterFixtures10868

    private func input(_ json: String, now: String, originalsCount: Int? = 4,
                       stream: A.StreamState = A.StreamState()) throws -> RacingEventPageInput10868 {
        let market = try F.market(json)
        let host = F.host(now)
        return A.input(market, history: RacingHistoryAdapter10868.unavailable(market, host: host),
                       originalsCount: originalsCount, stream: stream, host: host)
    }

    func testBeforeTheScreenComposesTheHeadlineHistoryAndAllPropsAndInventsNoStory() throws {
        let page = try input(F.winnerBefore, now: F.beforeCapture)
        XCTAssertEqual(page.phase, .before)
        XCTAssertEqual(page.headline.phase, .before)
        XCTAssertEqual(page.headline.displayed.map(\.name), ["Max Verstappen", "Lewis Hamilton", "Charles Leclerc"])
        XCTAssertNil(page.winPodium)
        XCTAssertNil(page.expectations)
        XCTAssertNil(page.chase)
        XCTAssertNil(page.finish)
        XCTAssertNil(page.readerChances)
        XCTAssertNil(page.winPodiumAbout)
        XCTAssertEqual(page.stories, [])
        XCTAssertEqual(page.reader, RacingEventPageReaderHeader10868(title: "Singapore Grand Prix: Driver Winner",
                                                                     state: "Race progress unavailable"))
        XCTAssertEqual(page.raceAbout, Page.raceAbout(try F.market(F.winnerBefore)))

        let model = RacingEventPageModel10868(page)
        XCTAssertNotNil(model.headline)
        XCTAssertTrue(model.readerShows(.history))
        for card in [RacingEventPageCard10868.winPodium, .expectations, .chase, .finish] {
            XCTAssertFalse(model.isMounted(card), "\(card)")
        }
        XCTAssertNil(model.story("win-podium"))
        XCTAssertNotNil(model.about(.race))
        XCTAssertNil(model.about(.winPodium))
        XCTAssertTrue(model.allPropsAvailable(canOpen: true))
    }

    func testTheStreamOffersNoCardSoItsOwnEmptyWordsShow() throws {
        let page = try input(F.winnerBefore, now: F.beforeCapture)
        XCTAssertEqual(page.stream.scope, "racing:63989371:before:stories")
        XCTAssertEqual(page.stream.heading, "Race stories")
        XCTAssertEqual(page.stream.cards, [])
        XCTAssertNil(page.stream.primary)
        XCTAssertNil(page.stream.playback)
        XCTAssertNil(page.stream.dwellFraction)
        XCTAssertNil(page.stream.previous)
        XCTAssertNil(page.stream.next)
        XCTAssertNil(page.stream.resolve(reduceMotion: false, actionable: true).primary)
    }

    func testAtTheFinalThePhaseIsTheMarketsOwnAndNoFinishStoryIsInvented() throws {
        let page = try input(F.winnerFinal, now: F.finalCapture)
        XCTAssertEqual(page.phase, .final)
        XCTAssertEqual(page.headline.phase, .final)
        XCTAssertEqual(page.stream.scope, "racing:63989371:final:stories")
        XCTAssertNil(page.finish)
        XCTAssertEqual(page.raceAbout?.paragraphs.count, 4)
        XCTAssertFalse(RacingEventPageModel10868(page).isMounted(.finish))
    }

    func testTheHostsReaderAndWideStateReachTheStream() throws {
        let page = try input(F.winnerBefore, now: F.beforeCapture, stream: A.StreamState(readerOpen: true, wide: true))
        XCTAssertTrue(page.stream.readerOpen)
        XCTAssertTrue(page.stream.wide)
    }

    func testTheAllPropsEntryCountsTheCatalogueOrDrawsNone() {
        XCTAssertNil(A.copy(originalsCount: nil).allPropsLabel)
        XCTAssertNil(A.copy(originalsCount: 0).allPropsLabel)
        XCTAssertEqual(A.copy(originalsCount: 1).allPropsLabel, "1 original outcome")
        XCTAssertEqual(A.copy(originalsCount: 23).allPropsLabel, "All 23 original outcomes")
        let copy = A.copy(originalsCount: 23)
        XCTAssertEqual(copy.storiesLabel, "Race stories")
        XCTAssertEqual(copy.headlineUnavailable, "Race headline unavailable for this moment")
    }
}
