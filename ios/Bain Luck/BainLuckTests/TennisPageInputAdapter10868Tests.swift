import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen's adapter, part five (the whole page input
/// and its manual story stream), composed from the REAL retained bodies in
/// `TennisMatchPageAdapter10868Tests` (details, byte for byte),
/// `TennisHistoryAdapter10868Tests` (`/history`, reduced verbatim subsets) and
/// `TennisOriginalsAdapter10868Tests` (`/game-markets`, reduced verbatim
/// subsets); paths and sha256 are written there.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The stream is MANUAL: no owner ranks or auto-advances tennis stories, so
/// nothing here elects a card, plays or dwells. No production owner supplies a
/// tennis story card today, so the retained pages compose with no stream.
/// CONSTRUCTED: the offered card lists and the held state handed to `stream`,
/// and the reader's calendar.
@MainActor
final class TennisPageInputAdapter10868Tests: XCTestCase {
    private typealias P = TennisPageInputAdapter10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests
    private typealias Ref = StoryStreamPresentation10868.CardRef

    private func ref(_ card: TennisEventPageCard10868, _ scope: String = "tennis:1:during") -> Ref {
        Ref(scope: scope, id: card.rawValue)
    }

    // MARK: - The stream

    func testNoOfferedStoryIsNoStreamAtAll() {
        XCTAssertNil(P.stream(scope: "tennis:1:during", offered: [], phase: .during, state: .init()))
        XCTAssertEqual(P.offeredCards(sets: nil, totals: nil, exact: nil, handicaps: nil), [])
        XCTAssertEqual(P.stories([]), [])
    }

    func testTheManualStreamShowsTheHeldCardAndNamesItsNeighboursWithoutPlayback() throws {
        let offered: [TennisEventPageCard10868] = [.sets, .totals, .handicaps]
        let first = try XCTUnwrap(P.stream(scope: "tennis:1:during", offered: offered, phase: .during, state: .init()))
        XCTAssertEqual(first.heading, "Match stories")
        XCTAssertNil(first.eyebrow)
        XCTAssertEqual(first.cards.map(\.name), ["First-set expectations", "Total-game milestones", "Set and game handicaps"])
        XCTAssertEqual(first.primary, ref(.sets), "nothing held shows the first offered card")
        XCTAssertEqual(first.companion, ref(.totals))
        XCTAssertEqual(first.companionLabel, "Next")
        XCTAssertEqual(first.previous, ref(.handicaps))
        XCTAssertEqual(first.next, ref(.totals))
        XCTAssertEqual(first.position, "1 of 3")
        XCTAssertEqual(first.status, "Use Previous or Next to see each story")
        XCTAssertNil(first.dwellFraction)
        XCTAssertNil(first.playback)

        let held = try XCTUnwrap(P.stream(scope: "tennis:1:during", offered: offered, phase: .during,
                                          state: .init(displayed: .handicaps, readerOpen: true, wide: true)))
        XCTAssertEqual(held.primary, ref(.handicaps))
        XCTAssertEqual(held.next, ref(.sets))
        XCTAssertEqual(held.previous, ref(.totals))
        XCTAssertEqual(held.position, "3 of 3")
        XCTAssertTrue(held.readerOpen)
        XCTAssertTrue(held.wide)

        let withdrawn = try XCTUnwrap(P.stream(scope: "tennis:1:during", offered: offered, phase: .during,
                                               state: .init(displayed: .exact)))
        XCTAssertEqual(withdrawn.primary, ref(.sets), "a held card no longer offered falls back to the first")
    }

    func testTheFinalNamesItsCardsInTheFinalsWords() throws {
        let offered: [TennisEventPageCard10868] = [.sets, .totals, .exact, .handicaps]
        let finished = try XCTUnwrap(P.stream(scope: "tennis:1:final", offered: offered, phase: .final, state: .init()))
        XCTAssertEqual(finished.cards.map(\.name), ["Set winners", "Total games", "Exact set finishes", "Set and game handicaps"])
    }

    func testOneOfferedStoryHasNoNeighbourAndNoBrowseWords() throws {
        let only = try XCTUnwrap(P.stream(scope: "tennis:1:during", offered: [.exact], phase: .during, state: .init()))
        XCTAssertEqual(only.primary, ref(.exact))
        XCTAssertNil(only.companion)
        XCTAssertNil(only.companionLabel)
        XCTAssertNil(only.previous)
        XCTAssertNil(only.next)
        XCTAssertNil(only.status)
        XCTAssertEqual(only.position, "1 of 1")
        XCTAssertEqual(P.stories([.exact]), [TennisEventPageStory10868(cardID: "exact", card: .exact)])
        XCTAssertNil(P.stories([.exact])[0].reason, "no owner ranks tennis stories, so no reason is invented")
    }

    // MARK: - Copy

    func testTheAllPropsLabelCountsTheCataloguesOriginals() {
        XCTAssertNil(P.copy(originalsCount: nil).allPropsLabel)
        XCTAssertNil(P.copy(originalsCount: 0).allPropsLabel)
        XCTAssertEqual(P.copy(originalsCount: 1).allPropsLabel, "1 original prop")
        XCTAssertEqual(P.copy(originalsCount: 12).allPropsLabel, "All 12 original props")
        XCTAssertEqual(P.copy(originalsCount: 12).headlineUnavailable,
                       TennisMatchPageAdapter10868.Words.headlineUnavailable)
        XCTAssertEqual(P.copy(originalsCount: 12).storiesLabel, "Match stories")
    }

    // MARK: - The whole input (the retained states)

    func testTheRetainedLiveMatchComposesWithNoStoriesAndAllItsOriginalsInAllProps() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let now = try XCTUnwrap(Fixtures.liveReadAt.asDate)
        let host = TennisMatchPageAdapter10868.Host(probabilityObservedAt: event.heroProbabilityObservedAt?.asDate,
                                                    now: now, calendar: Fixtures.pacific, locale: Fixtures.locale)
        let response = try TennisHistoryAdapter10868Tests.live()
        let history = TennisHistoryAdapter10868.history(
            response, event: event, phase: .during,
            host: TennisHistoryAdapter10868.Host(now: now, calendar: Fixtures.pacific, locale: Fixtures.locale))
        let series = try XCTUnwrap(TennisReadingAdapter10868.series(response, event: event, now: now))
        let reading = TennisReadingAdapter10868.reading(series, held: nil, event: event, now: now)
        let input = P.input(event, history: history, reading: reading, originalsCount: 12, stream: .init(), host: host)
        XCTAssertEqual(input.phase, .during)
        XCTAssertEqual(input.eventID, "15327807")
        XCTAssertEqual(input.headline, TennisMatchPageAdapter10868.headline(event, host: host))
        XCTAssertEqual(input.reader, TennisMatchPageAdapter10868.readerHeader(event, host: host))
        XCTAssertEqual(input.about, TennisMatchPageAdapter10868.about(event, host: host))
        XCTAssertEqual(input.history, history)
        XCTAssertEqual(input.reading, reading)
        XCTAssertNil(input.notice)
        XCTAssertNil(input.sets)
        XCTAssertNil(input.totals)
        XCTAssertNil(input.exact)
        XCTAssertNil(input.handicaps)
        XCTAssertNil(input.stream, "no owner-proved story, no stream")
        XCTAssertTrue(input.stories.isEmpty)
        XCTAssertEqual(input.copy.allPropsLabel, "All 12 original props")
        XCTAssertEqual(P.scope(event, phase: .during), "tennis:15327807:during")

        // The composed screen mounts the headline and the history, and no page reading until one is held.
        let model = TennisEventPageModel10868(input)
        XCTAssertNil(model.pageReading, "the hero already prints the current chance (#9517)")
        XCTAssertNotNil(model.readerReading)
    }

    func testTheRetainedFinalComposesInTheFinalPhase() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let now = try XCTUnwrap(Fixtures.finalReadAt.asDate)
        let host = TennisMatchPageAdapter10868.Host(probabilityObservedAt: nil, now: now,
                                                    calendar: Fixtures.pacific, locale: Fixtures.locale)
        let input = P.input(event, history: TennisHistoryAdapter10868.unavailable(event: event, phase: .final),
                            reading: nil, originalsCount: 18, stream: .init(), host: host)
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.headline.phase, .final)
        XCTAssertEqual(input.history.plotAbsence?.title, "History unavailable")
        XCTAssertNil(input.reading)
        XCTAssertEqual(input.copy.allPropsLabel, "All 18 original props")
    }
}
