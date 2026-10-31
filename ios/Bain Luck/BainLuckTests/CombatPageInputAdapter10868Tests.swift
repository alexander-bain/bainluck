import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen's adapter, part five (the whole page input
/// and its manual story stream), composed from the REAL retained bodies in
/// `CombatBoutPageAdapter10868Tests` (detail, byte for byte) and
/// `CombatOriginalsAdapter10868Tests` (`/game-markets`, reduced verbatim
/// subset); paths and sha256 are written there.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The stream is MANUAL: no owner ranks or auto-advances combat stories, so
/// nothing here elects a card, plays or dwells. CONSTRUCTED: the offered card
/// lists and the held state handed to `stream`, and the reader's calendar.
@MainActor
final class CombatPageInputAdapter10868Tests: XCTestCase {
    private typealias P = CombatPageInputAdapter10868
    private typealias Fixtures = CombatBoutPageAdapter10868Tests
    private typealias Ref = StoryStreamPresentation10868.CardRef

    private func ref(_ card: CombatEventPageCard10868) -> Ref { Ref(scope: "combat:1:during", id: card.rawValue) }

    // MARK: - The stream

    func testNoOfferedStoryIsNoStreamAtAll() {
        XCTAssertNil(P.stream(scope: "combat:1:during", offered: [], state: .init()))
        XCTAssertEqual(P.offeredCards(methods: nil, rounds: nil, knockout: nil, duration: nil), [])
        XCTAssertEqual(P.stories([]), [])
    }

    func testTheManualStreamShowsTheHeldCardAndNamesItsNeighboursWithoutPlayback() throws {
        let offered: [CombatEventPageCard10868] = [.methods, .rounds, .duration]
        let first = try XCTUnwrap(P.stream(scope: "combat:1:during", offered: offered, state: .init()))
        XCTAssertEqual(first.heading, "Fight stories")
        XCTAssertNil(first.eyebrow)
        XCTAssertEqual(first.cards.map(\.name), ["Finish method", "Fighter rounds", "Fight length"])
        XCTAssertEqual(first.primary, ref(.methods), "nothing held shows the first offered card")
        XCTAssertEqual(first.companion, ref(.rounds))
        XCTAssertEqual(first.companionLabel, "Next")
        XCTAssertEqual(first.previous, ref(.duration))
        XCTAssertEqual(first.next, ref(.rounds))
        XCTAssertEqual(first.position, "1 of 3")
        XCTAssertEqual(first.status, "Use Previous or Next to see each story")
        XCTAssertNil(first.dwellFraction)
        XCTAssertNil(first.playback)

        let held = try XCTUnwrap(P.stream(scope: "combat:1:during", offered: offered,
                                          state: .init(displayed: .duration, readerOpen: true, wide: true)))
        XCTAssertEqual(held.primary, ref(.duration))
        XCTAssertEqual(held.next, ref(.methods))
        XCTAssertEqual(held.previous, ref(.rounds))
        XCTAssertEqual(held.position, "3 of 3")
        XCTAssertTrue(held.readerOpen)
        XCTAssertTrue(held.wide)

        let withdrawn = try XCTUnwrap(P.stream(scope: "combat:1:during", offered: offered,
                                               state: .init(displayed: .knockout)))
        XCTAssertEqual(withdrawn.primary, ref(.methods), "a held card no longer offered falls back to the first")
    }

    func testOneOfferedStoryHasNoNeighbourAndNoBrowseWords() throws {
        let only = try XCTUnwrap(P.stream(scope: "combat:1:during", offered: [.knockout], state: .init()))
        XCTAssertEqual(only.primary, ref(.knockout))
        XCTAssertNil(only.companion)
        XCTAssertNil(only.companionLabel)
        XCTAssertNil(only.previous)
        XCTAssertNil(only.next)
        XCTAssertNil(only.status)
        XCTAssertEqual(only.position, "1 of 1")
        XCTAssertEqual(P.stories([.knockout]), [CombatEventPageStory10868(cardID: "knockout", card: .knockout)])
        XCTAssertNil(P.stories([.knockout])[0].reason, "no owner ranks combat stories, so no reason is invented")
    }

    // MARK: - Copy

    func testTheAllPropsLabelCountsTheCataloguesOriginals() {
        XCTAssertNil(P.copy(originalsCount: nil).allPropsLabel)
        XCTAssertNil(P.copy(originalsCount: 0).allPropsLabel)
        XCTAssertEqual(P.copy(originalsCount: 1).allPropsLabel, "1 original prop")
        XCTAssertEqual(P.copy(originalsCount: 31).allPropsLabel, "All 31 original props")
        XCTAssertEqual(P.copy(originalsCount: 31).headlineUnavailable, CombatBoutPageAdapter10868.Words.headlineUnavailable)
        XCTAssertEqual(P.copy(originalsCount: 31).storiesLabel, "Fight stories")
    }

    // MARK: - The whole input (the retained state)

    func testTheRetainedBoutComposesWithNoStoriesAndAllItsOriginalsInAllProps() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let now = try XCTUnwrap(Fixtures.readAt.asDate)
        let host = CombatBoutPageAdapter10868.Host(probabilityObservedAt: event.heroProbabilityObservedAt?.asDate,
                                                   now: now, calendar: Fixtures.pacific, locale: Fixtures.locale)
        let input = P.input(event, history: CombatHistoryAdapter10868.unavailable(event: event, phase: .during),
                            methods: nil, rounds: nil, knockout: nil, duration: nil, originalsCount: 31,
                            stream: .init(), host: host)
        XCTAssertEqual(input.phase, .during)
        XCTAssertEqual(input.eventID, "15318681")
        XCTAssertEqual(input.headline, CombatBoutPageAdapter10868.headline(event, host: host))
        XCTAssertEqual(input.reader, CombatBoutPageAdapter10868.readerHeader(event, host: host))
        XCTAssertEqual(input.about, CombatBoutPageAdapter10868.about(event, host: host))
        XCTAssertNil(input.notice)
        XCTAssertNil(input.stream, "no owner-proved story, no stream")
        XCTAssertTrue(input.stories.isEmpty)
        XCTAssertEqual(input.copy.allPropsLabel, "All 31 original props")
        XCTAssertEqual(P.scope(event, phase: .during), "combat:15318681:during")
    }
}
