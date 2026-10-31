import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the football screen's whole page input and its manual story
/// stream, composed from the other football adapters on RETAINED REAL bodies
/// (`FootballRetained10868`). The live Eagles–Jaguars subset carries a
/// projected finish, two passing-yards milestone cards and the team field
/// goals pair; it serves no sacks and no combined market.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class FootballPageInputAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias P = FootballPageInputAdapter10868
    private typealias Card = FootballEventPageCard10868

    private static let hurts = Card.milestone("Jalen Hurts|Philadelphia vs Jacksonville: Passing Yards")
    private static let lawrence = Card.milestone("Trevor Lawrence|Philadelphia vs Jacksonville: Passing Yards")

    private func live(_ route: FootballRoute10868, state: P.StreamState = P.StreamState()) throws
        -> FootballEventPageInput10868 {
        let event = try F.detail(F.liveDetail)
        let history = try F.history(F.liveHistory)
        let markets = try F.markets(F.liveMarkets)
        let deck = FootballDeckAdapter10868.deck(event, history: history, markets: markets,
                                                 host: F.deckHost(F.liveNow, arrivedAt: F.liveNow))
        let team = F.teamHost(F.liveNow)
        let originals = FootballOriginalsAdapter10868.originals(event, markets: markets,
                                                                host: F.originalsHost(F.liveNow), tint: .blue)
        return P.input(
            event, route: route,
            history: FootballHistoryAdapter10868.history(history, event: event, phase: .live,
                                                         host: F.historyHost(F.liveNow)),
            deck: deck,
            teamSacks: FootballTeamMilestonesAdapter10868.input(.sacks, event: event, markets: markets, host: team),
            teamFieldGoals: FootballTeamMilestonesAdapter10868.input(.fieldGoals, event: event, markets: markets,
                                                                     host: team),
            combined: FootballCombinedYardsAdapter10868.stories(event, markets: markets, deck: deck, now: F.liveNow),
            originalsCount: originals.catalogue?.originals.count,
            stream: state,
            host: F.pageHost(F.liveNow, observedAt: F.liveObservedAt, history: history))
    }

    func testTheLivePageOffersEveryServedStoryInTheScreensFixedOrder() throws {
        let input = try live(.nfl)
        XCTAssertEqual(input.phase, .live)
        XCTAssertEqual(input.stories.map(\.card), [.finish, Self.hurts, Self.lawrence, .teamFieldGoals])
        XCTAssertEqual(input.stories.map(\.cardID), input.stories.map(\.card.key))
        XCTAssertTrue(FootballEventPageModel10868(input).headlineResolves)

        let stream = input.stream
        XCTAssertEqual(stream.scope, "nfl:14639175:live")
        XCTAssertEqual(stream.heading, "Expectations and performance")
        XCTAssertEqual(stream.primary?.id, Card.finish.key)
        XCTAssertEqual(stream.companion?.id, Self.hurts.key)
        XCTAssertEqual(stream.companionLabel, "Next")
        XCTAssertEqual(stream.next?.id, Self.hurts.key)
        XCTAssertEqual(stream.previous?.id, Card.teamFieldGoals.key)
        XCTAssertEqual(stream.position, "1 of 4")
        XCTAssertEqual(stream.status, "Use Previous or Next to see each story")
        // Manual: no playback control, no dwell.
        XCTAssertNil(stream.playback)
        XCTAssertNil(stream.dwellFraction)

        let deckNames = input.deck.map(\.title)
        XCTAssertEqual(stream.cards.map(\.name), deckNames + ["The kicking game"])
    }

    func testTheHeldStoryIsShownAndItsNeighboursWrap() throws {
        let input = try live(.nfl, state: P.StreamState(displayed: .teamFieldGoals, readerOpen: true, wide: true))
        XCTAssertEqual(input.stream.primary?.id, Card.teamFieldGoals.key)
        XCTAssertEqual(input.stream.next?.id, Card.finish.key)
        XCTAssertEqual(input.stream.previous?.id, Self.lawrence.key)
        XCTAssertEqual(input.stream.position, "4 of 4")
        XCTAssertTrue(input.stream.readerOpen)
        XCTAssertTrue(input.stream.wide)
    }

    func testAHeldStoryThePageNoLongerOffersFallsBackToTheFirst() throws {
        let input = try live(.nfl, state: P.StreamState(displayed: .teamSacks))
        XCTAssertEqual(input.stream.primary?.id, Card.finish.key)
    }

    func testEachRouteOffersOnlyItsOwnCardSet() throws {
        XCTAssertEqual(try live(.live).stories.map(\.card), [.finish, Self.hurts, Self.lawrence])
        XCTAssertEqual(try live(.teamStats).stories.map(\.card), [.teamFieldGoals])
        XCTAssertEqual(try live(.stories).stories.map(\.card), [.finish, Self.hurts, Self.lawrence, .teamFieldGoals])
        XCTAssertEqual(try live(.replay).stories.map(\.card), [.finish, Self.hurts, Self.lawrence, .teamFieldGoals])

        let single = try live(.teamStats)
        XCTAssertNil(single.stream.companion)
        XCTAssertNil(single.stream.status)
        XCTAssertEqual(single.stream.position, "1 of 1")

        // No combined market is served: the combined route offers no story at
        // all, and the stream displays nothing rather than another route's card.
        let combined = try live(.combined)
        XCTAssertTrue(combined.stories.isEmpty)
        XCTAssertNil(combined.stream.primary)
        XCTAssertTrue(combined.stream.cards.isEmpty)
    }

    func testAllPropsCountsTheServedOriginals() throws {
        let count = try XCTUnwrap(FootballOriginalsAdapter10868.originals(
            try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets),
            host: F.originalsHost(F.liveNow), tint: .blue).catalogue?.originals.count)
        XCTAssertEqual(try live(.nfl).copy.allPropsLabel, "All \(count) original outcomes")
        XCTAssertEqual(P.copy(originalsCount: 1).allPropsLabel, "1 original outcome")
        XCTAssertNil(P.copy(originalsCount: 0).allPropsLabel)
        XCTAssertNil(P.copy(originalsCount: nil).allPropsLabel)
        XCTAssertEqual(P.copy(originalsCount: nil).headlineUnavailable, "Win chance unavailable")
    }
}
