import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — whole-input event identity for the football screen: another game's
/// history or markets supply nothing, at the host boundary AND at every wrapper
/// a direct caller can reach, while this game's own headline and every part
/// whose payload is this game's keep showing. On RETAINED REAL bodies
/// (`FootballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here, and only here: the "foreign" payloads are the real
/// Eagles–Jaguars bodies with ONLY their served `event_id` replaced by another
/// id (14639176). Everything else stays — the same live status, the same clubs,
/// the same players and markets — which is exactly the case the shared helpers
/// cannot tell apart: `ProjectedFinalPointsMount.input` reads a sport, a status
/// and a history, and `NFLMilestoneCard9483.cards` reads bare props.
@MainActor
final class FootballInputIdentityAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias I = FootballInputIdentityAdapter10868
    private typealias Host = FootballEventPageHost10868
    private typealias Card = FootballEventPageCard10868

    private static let otherGame = 14639176

    private func foreign(_ json: String) throws -> String {
        try F.edited(json, setting: ["event_id": Self.otherGame])
    }

    private func build(_ event: EventDetail, history: EventHistoryResponse?,
                       markets: GameMarketsResponse?) -> Host.Built {
        Host.build(route: .nfl, event: event, history: history, historyArrivedAt: F.liveNow, markets: markets,
                   probabilityObservedAt: F.liveObservedAt, now: F.liveNow, calendar: F.pacific, locale: F.locale)
    }

    // MARK: - The rule itself

    func testOnlyAnExactServedEventIdBelongsToTheEvent() throws {
        let event = try F.detail(F.liveDetail)
        let own = try F.history(F.liveHistory)
        let other = try F.history(try foreign(F.liveHistory))
        // Same status, same clubs: still another game's.
        XCTAssertEqual(other.status, own.status)
        XCTAssertEqual(other.homeTeam, own.homeTeam)
        XCTAssertNotNil(I.history(own, for: event))
        XCTAssertNil(I.history(other, for: event))
        XCTAssertNotNil(I.markets(try F.markets(F.liveMarkets), for: event))
        XCTAssertNil(I.markets(try F.markets(try foreign(F.liveMarkets)), for: event))

        let scoped = I.scoped(event, history: other, markets: try F.markets(F.liveMarkets))
        XCTAssertNil(scoped.history)
        XCTAssertTrue(scoped.historyRefused)
        XCTAssertNotNil(scoped.markets, "a foreign history never costs the event its own markets")
        XCTAssertFalse(scoped.marketsRefused)
        // Absent is not refused.
        XCTAssertFalse(I.scoped(event, history: nil, markets: nil).historyRefused)

        XCTAssertEqual(I.ladder(own, for: event).home, 20.0)
        XCTAssertNil(I.ladder(other, for: event).home)
        XCTAssertNil(I.ladder(other, for: event).away)
    }

    // MARK: - Same-status foreign history

    func testAForeignHistoryLeavesTheChartAndProjectedFinishOutAndKeepsEverythingElse() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(F.liveMarkets)
        let other = try F.history(try foreign(F.liveHistory))
        let built = build(event, history: other, markets: markets)

        XCTAssertEqual(built.input.history, FootballHistoryAdapter10868.unavailable(event: event, phase: .live))
        XCTAssertNil(FootballDeckAdapter10868.finishCard(built.input.deck))
        XCTAssertFalse(built.input.stories.contains { $0.card == .finish })
        // The event's own headline and the markets' stories stay.
        XCTAssertTrue(FootballEventPageModel10868(built.input).headlineResolves)
        XCTAssertEqual(built.input.stories.map(\.card), [
            .milestone("Jalen Hurts|Philadelphia vs Jacksonville: Passing Yards"),
            .milestone("Trevor Lawrence|Philadelphia vs Jacksonville: Passing Yards"),
            .teamFieldGoals,
        ])
        XCTAssertNotNil(built.originals.catalogue)
        XCTAssertNil(built.scoped.history)

        // With its own history the same page deals the projected finish first.
        let ownBuilt = build(event, history: try F.history(F.liveHistory), markets: markets)
        XCTAssertEqual(ownBuilt.input.stories.first?.card, .finish)
    }

    func testAForeignHistoryGivesTheHeadlineNoLadderFallback() throws {
        let event = try F.detail(F.liveDetail)
        let other = try F.history(try foreign(F.liveHistory))
        let host = F.pageHost(F.liveNow, observedAt: F.liveObservedAt, history: other)
        XCTAssertNil(host.ladder(for: event).home)
        guard case .live(let arm) = FootballEventPageAdapter10868.headline(event, host: host).arm else {
            return XCTFail("the live arm is the event's own and stays")
        }
        let hasScore = EventDetailView.showsScore(status: event.status, away: event.awayScore, home: event.homeScore)
        XCTAssertEqual(arm.forecast, EventDetailView.liveForecast11296(
            event, ladderHome: nil, ladderAway: nil, hasScore: hasScore, now: F.liveNow))
    }

    // MARK: - Foreign markets with plausible clubs and players

    func testForeignMarketsDealNoMarketStoryNoOriginalAndNoDetailsRow() throws {
        let event = try F.detail(F.liveDetail)
        let history = try F.history(F.liveHistory)
        let other = try F.markets(try foreign(F.liveMarkets))
        // The foreign body names the same clubs and players.
        XCTAssertEqual(other.homeTeam, "Jacksonville Jaguars")
        XCTAssertTrue(other.playerProps?.contains { $0.outcomeName.hasPrefix("Jalen Hurts:") } == true)

        let built = build(event, history: history, markets: other)
        XCTAssertEqual(built.input.stories.map(\.card), [.finish], "only the history's own story is left")
        XCTAssertTrue(FootballDeckAdapter10868.milestoneCards(built.input.deck).isEmpty)
        XCTAssertNil(built.input.teamFieldGoals)
        XCTAssertNil(built.input.teamSacks)
        XCTAssertTrue(built.input.combined.isEmpty)
        XCTAssertNil(built.originals.catalogue)
        XCTAssertNil(built.input.copy.allPropsLabel)
        XCTAssertTrue(FootballEventPageModel10868(built.input).headlineResolves)
        XCTAssertNil(built.scoped.markets)
        // The chart is the event's own history, unchanged by the foreign markets.
        XCTAssertEqual(built.input.history, build(event, history: history, markets: nil).input.history)

        // Details lookups read the event's own markets only.
        let ownBuilt = build(event, history: history, markets: try F.markets(F.liveMarkets))
        XCTAssertTrue(Host.rows(ownBuilt.input, event: event, markets: other).isEmpty)
        XCTAssertFalse(Host.rows(ownBuilt.input, event: event, markets: try F.markets(F.liveMarkets)).isEmpty)
        let row = try XCTUnwrap(other.playerProps?.first { $0.outcomeName == "Jacksonville: 2+" })
        XCTAssertNil(Host.teamOriginal(HockeyJourneyContributionAdapter10868.milestoneID(row), event: event,
                                       markets: other, now: F.liveNow, scope: ownBuilt.originals))
    }

    // MARK: - Direct helper callers

    func testEveryWrapperRefusesAForeignPayloadForADirectCaller() throws {
        let event = try F.detail(F.liveDetail)
        let otherHistory = try F.history(try foreign(F.liveHistory))
        let otherMarkets = try F.markets(try foreign(F.liveMarkets))
        let deckHost = F.deckHost(F.liveNow, arrivedAt: F.liveNow)

        XCTAssertEqual(FootballHistoryAdapter10868.history(otherHistory, event: event, phase: .live,
                                                           host: F.historyHost(F.liveNow)),
                       FootballHistoryAdapter10868.unavailable(event: event, phase: .live))
        XCTAssertNil(FootballDeckAdapter10868.projectedInput(event, history: otherHistory, host: deckHost))
        XCTAssertNil(FootballDeckAdapter10868.finish(event, history: otherHistory, host: deckHost))
        XCTAssertTrue(FootballDeckAdapter10868.milestones(event, markets: otherMarkets, host: deckHost).isEmpty)
        XCTAssertTrue(FootballDeckAdapter10868.deck(event, history: otherHistory, markets: otherMarkets,
                                                    host: deckHost).isEmpty)
        XCTAssertNil(FootballTeamMilestonesAdapter10868.input(.fieldGoals, event: event, markets: otherMarkets,
                                                              host: F.teamHost(F.liveNow)))
        XCTAssertNil(FootballOriginalsAdapter10868.originals(event, markets: otherMarkets,
                                                             host: F.originalsHost(F.liveNow), tint: .blue).catalogue)
        // CONSTRUCTED on top: the combined rename, in the foreign body.
        let renamed = try F.editedProps(try foreign(F.liveMarkets), marketName: "Philadelphia vs Jacksonville: Passing Yards",
                                        subject: "Jalen Hurts",
                                        setting: ["market_name": "Philadelphia vs Jacksonville: Rushing + Receiving Yards"])
        XCTAssertTrue(FootballCombinedYardsAdapter10868.cards(event, markets: try F.markets(renamed), now: F.liveNow).isEmpty)

        // The same calls on the event's own payloads still produce their parts.
        XCTAssertNotNil(FootballDeckAdapter10868.finish(event, history: try F.history(F.liveHistory), host: deckHost))
        XCTAssertEqual(FootballDeckAdapter10868.milestones(event, markets: try F.markets(F.liveMarkets),
                                                           host: deckHost).count, 2)
    }

    func testThePeriodWinnerStoryRefusesForeignMarketsAndAForeignBinding() throws {
        let event = try F.detail(F.finalDetail)
        let host = F.periodHost(F.finalNow)
        XCTAssertNotNil(FootballPeriodWinnersAdapter10868.input(event, markets: try F.markets(F.finalMarkets),
                                                                binding: F.quarterBinding, selectedID: nil, host: host))
        XCTAssertNil(FootballPeriodWinnersAdapter10868.input(event, markets: try F.markets(try foreign(F.finalMarkets)),
                                                             binding: F.quarterBinding, selectedID: nil, host: host))
        // CONSTRUCTED: the same binding made for another event.
        let otherBinding = FootballPeriodWinnersAdapter10868.Binding(
            eventID: Self.otherGame, verifiedStart: F.quarterBinding.verifiedStart,
            originals: F.quarterBinding.originals)
        XCTAssertNil(FootballPeriodWinnersAdapter10868.input(event, markets: try F.markets(F.finalMarkets),
                                                             binding: otherBinding, selectedID: nil, host: host))
        XCTAssertTrue(FootballPeriodWinnersAdapter10868.admitted(event, markets: try F.markets(F.finalMarkets),
                                                                 binding: otherBinding, host: host).isEmpty)
    }
}
