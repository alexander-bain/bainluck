import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game adapter, part six (the whole page input and its
/// manual story stream), on the RETAINED REAL bodies (`BaseballRetained10868`)
/// through the host's pure builder, and on the stream rules directly.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The stream is manual: no owner ranks or auto-advances baseball story cards,
/// so the held card is shown, Previous and Next name the others, and nothing
/// offers playback, dwell or a timer.
@MainActor
final class BaseballPageInputAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias P = BaseballPageInputAdapter10868
    private typealias Host = BaseballEventPageHost10868

    private func built(_ event: EventDetail, now: Date, observedAt: Date? = nil,
                       reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        Host.build(event: event, history: nil, markets: try F.markets(), related: try F.related(),
                   probabilityObservedAt: observedAt, now: now, reading: reading,
                   calendar: F.pacific, locale: F.locale)
    }

    private func ref(_ scope: String, _ card: BaseballEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
        .init(scope: scope, id: card.rawValue)
    }

    func testAfterTheFinalEveryStoryIsOfferedInTheProductionDecksOrderUnderItsProductionTitle() throws {
        let page = try built(try F.finalEvent(), now: F.finalNow)
        let input = page.input
        let stream = input.stream
        let scope = "mlb:15321836:final"

        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(stream.scope, scope)
        XCTAssertEqual(stream.heading, "Explore the game")
        XCTAssertEqual(stream.cards.map(\.id), ["homeRuns", "strikeouts", "totals", "series"])
        XCTAssertEqual(stream.cards.map(\.name), ["Home runs", "Hunter Brown · Strikeouts", "Run totals", "The series"])
        XCTAssertEqual(input.stories.map(\.cardID), input.stories.map(\.card.rawValue))
        XCTAssertEqual(stream.primary, ref(scope, .homeRuns))
        XCTAssertEqual(stream.companion, ref(scope, .strikeouts))
        XCTAssertEqual(stream.companionLabel, "Next")
        XCTAssertEqual(stream.position, "1 of 4")
        XCTAssertEqual(stream.status, "Use Previous or Next to see each story")
        XCTAssertEqual(stream.previous, ref(scope, .series))
        XCTAssertEqual(stream.next, ref(scope, .strikeouts))
        XCTAssertNil(stream.playback, "no playback: nothing advances on its own")
        XCTAssertNil(stream.dwellFraction)
        XCTAssertFalse(stream.readerOpen)

        let count = try XCTUnwrap(page.originals.catalogue?.originals.count)
        XCTAssertEqual(input.copy, BaseballEventPageCopy10868(
            storiesLabel: "Game stories",
            storyUnavailable: "This story isn’t available for this game state. Every original is still in All props.",
            matrixUnavailable: "Comparison unavailable for this game state",
            allPropsLabel: "All props · \(count)"))
        XCTAssertEqual(input.headline, BaseballGamePageAdapter10868.headline(
            try F.finalEvent(), host: F.pageHost(F.finalNow, observedAt: nil)))
    }

    func testBeforeAndDuringPlayOnlyTheRunMilestonesAndTheSeriesAreOffered() throws {
        let live = try built(try F.liveEvent(), now: F.liveNow, observedAt: F.liveObservedAt).input
        XCTAssertEqual(live.phase, .live)
        XCTAssertEqual(live.stream.scope, "mlb:15321836:live")
        XCTAssertEqual(live.stream.cards.map(\.id), ["totals", "series"])
        guard case .milestones(let milestones)? = live.totals else { return XCTFail("run milestones") }
        XCTAssertEqual(milestones.phase, .during)
        XCTAssertNil(live.homeRuns)
        XCTAssertNil(live.strikeouts)

        let before = try built(try F.beforeEvent(), now: F.beforeNow, observedAt: F.beforeObservedAt).input
        XCTAssertEqual(before.phase, .before)
        XCTAssertEqual(before.stream.cards.map(\.id), ["totals", "series"])
        XCTAssertEqual(before.stream.position, "1 of 2")
    }

    func testOnlyAStoryInItsOwnPhaseIsOfferedAndEveryCardHasAReaderName() throws {
        let final = try built(try F.finalEvent(), now: F.finalNow).input
        // The final stories handed to an earlier phase are not offered there.
        XCTAssertEqual(P.offeredCards(phase: .live, homeRuns: final.homeRuns, strikeouts: final.strikeouts,
                                      totals: final.totals, series: nil), [])
        XCTAssertEqual(P.offeredCards(phase: .final, homeRuns: final.homeRuns, strikeouts: nil,
                                      totals: nil, series: final.series), [.homeRuns, .series])
        XCTAssertEqual(P.name(.strikeouts, strikeouts: nil), "Strikeouts", "never a raw identifier")
        XCTAssertEqual(P.name(.history, strikeouts: nil), "Win probability")
        XCTAssertNil(P.copy(originalsCount: 0).allPropsLabel)
        XCTAssertNil(P.copy(originalsCount: nil).allPropsLabel)
        XCTAssertEqual(P.copy(originalsCount: 623).allPropsLabel, "All props · 623")
    }

    func testTheHeldCardIsShownAndOneNoLongerOfferedFallsBackToTheFirst() {
        let scope = "mlb:15321836:final"
        let all: [BaseballEventPageCard10868] = [.homeRuns, .strikeouts, .totals, .series]

        let held = P.stream(scope: scope, offered: all, strikeouts: nil,
                            state: .init(displayed: .totals, readerOpen: true, wide: true))
        XCTAssertEqual(held.primary, ref(scope, .totals))
        XCTAssertEqual(held.position, "3 of 4")
        XCTAssertEqual(held.previous, ref(scope, .strikeouts))
        XCTAssertEqual(held.next, ref(scope, .series))
        XCTAssertTrue(held.readerOpen)
        XCTAssertTrue(held.wide)

        let gone = P.stream(scope: scope, offered: [.totals, .series], strikeouts: nil, state: .init(displayed: .homeRuns))
        XCTAssertEqual(gone.primary, ref(scope, .totals))

        let one = P.stream(scope: scope, offered: [.series], strikeouts: nil, state: .init())
        XCTAssertEqual(one.primary, ref(scope, .series))
        XCTAssertNil(one.companion)
        XCTAssertNil(one.companionLabel)
        XCTAssertNil(one.status, "no browsing words with nothing to browse")
        XCTAssertNil(one.previous)
        XCTAssertNil(one.next)
        XCTAssertEqual(one.position, "1 of 1")

        let none = P.stream(scope: scope, offered: [], strikeouts: nil, state: .init())
        XCTAssertNil(none.primary)
        XCTAssertNil(none.position)
        XCTAssertTrue(none.cards.isEmpty)
    }
}
