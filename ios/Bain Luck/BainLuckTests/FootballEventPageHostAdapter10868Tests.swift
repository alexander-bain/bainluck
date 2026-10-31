import XCTest
@testable import Bain_Luck

/// #10868 — the football screen's host glue: its pure build and the exact
/// lookups its controls use, on RETAINED REAL bodies (`FootballRetained10868`).
/// The mount itself is PROPOSED only (Native's call); nothing here renders.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class FootballEventPageHostAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias Host = FootballEventPageHost10868
    private typealias Card = FootballEventPageCard10868

    private func build(_ event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                       route: FootballRoute10868 = .nfl, reading: Host.Reading = Host.Reading(),
                       binding: FootballPeriodWinnersAdapter10868.Binding? = nil,
                       now: Date? = nil) -> Host.Built {
        let clock = now ?? F.liveNow
        return Host.build(route: route, event: event, history: history, historyArrivedAt: clock,
                          markets: markets, probabilityObservedAt: F.liveObservedAt, periodBinding: binding,
                          now: clock, reading: reading, calendar: F.pacific, locale: F.locale)
    }

    func testOnlyAnNFLGameTakesTheFootballScreen() throws {
        XCTAssertTrue(Host.applies(try F.detail(F.liveDetail)))
        // CONSTRUCTED: the live detail with only its `sport` key replaced.
        XCTAssertFalse(Host.applies(try F.detail(F.edited(F.liveDetail, setting: ["sport": "basketball_nba"]))))
    }

    func testWithoutAHistoryTheScreenStillShowsItsComparisonStoriesAndAllProps() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(F.liveMarkets)
        let built = build(event, history: nil, markets: markets)

        XCTAssertEqual(built.input.history, FootballHistoryAdapter10868.unavailable(event: event, phase: .live))
        XCTAssertTrue(FootballEventPageModel10868(built.input).headlineResolves)
        // The projected finish needs the history; the milestones and the field
        // goals do not.
        XCTAssertEqual(built.input.stories.map(\.card), [
            .milestone("Jalen Hurts|Philadelphia vs Jacksonville: Passing Yards"),
            .milestone("Trevor Lawrence|Philadelphia vs Jacksonville: Passing Yards"),
            .teamFieldGoals,
        ])
        XCTAssertNotNil(built.originals.catalogue)
        XCTAssertNotNil(built.input.copy.allPropsLabel)
    }

    func testWithTheHistoryTheProjectedFinishLeadsTheStories() throws {
        let built = build(try F.detail(F.liveDetail), history: try F.history(F.liveHistory),
                          markets: try F.markets(F.liveMarkets))
        XCTAssertEqual(built.input.stories.first?.card, .finish)
        XCTAssertEqual(built.input.stories.count, 4)
    }

    func testEveryPassRebuildsFromTheValuesItIsGiven() throws {
        let history = try F.history(F.liveHistory)
        let markets = try F.markets(F.liveMarkets)
        let event = try F.detail(F.liveDetail)
        XCTAssertEqual(build(event, history: history, markets: markets).input,
                       build(event, history: history, markets: markets).input)
        // CONSTRUCTED: the same detail with a later served score. No memo holds
        // the old one.
        let later = try F.detail(F.edited(F.liveDetail, setting: ["home_score": 10]))
        XCTAssertEqual(build(later, history: history, markets: markets).input.header.score,
                       FootballEventPageAdapter10868.scoreWords(later))
        XCTAssertNotEqual(build(later, history: history, markets: markets).input.header.score,
                          build(event, history: history, markets: markets).input.header.score)
    }

    func testTheHeldReadingReachesTheBuildUnchanged() throws {
        let reading = Host.Reading(story: .teamFieldGoals, fieldGoalGroup: "teamFieldGoals:2+",
                                   readerOpen: true, wide: false)
        let built = build(try F.detail(F.liveDetail), history: try F.history(F.liveHistory),
                          markets: try F.markets(F.liveMarkets), reading: reading)
        XCTAssertEqual(built.input.stream.primary?.id, Card.teamFieldGoals.key)
        XCTAssertEqual(built.input.teamFieldGoals?.selectedGroupID, "teamFieldGoals:2+")
        XCTAssertNil(built.input.teamSacks)
        XCTAssertTrue(built.input.stream.readerOpen)
    }

    func testAStreamIdNamesExactlyOneCardOrNone() throws {
        let built = build(try F.detail(F.liveDetail), history: try F.history(F.liveHistory),
                          markets: try F.markets(F.liveMarkets))
        XCTAssertEqual(Host.card("finish", in: built.input.stories), .finish)
        XCTAssertEqual(Host.card("teamFieldGoals", in: built.input.stories), .teamFieldGoals)
        XCTAssertNil(Host.card("teamSacks", in: built.input.stories))
        XCTAssertNil(Host.card("history", in: built.input.stories))
        // CONSTRUCTED: a duplicated link resolves to nothing.
        let doubled = built.input.stories + built.input.stories.prefix(1)
        XCTAssertNil(Host.card("finish", in: Array(doubled)))
    }

    func testAMilestoneLinesDetailsNameTheExactServedRow() throws {
        let markets = try F.markets(F.liveMarkets)
        let built = build(try F.detail(F.liveDetail), history: try F.history(F.liveHistory), markets: markets)
        let rows = Host.rows(built.input, event: try F.detail(F.liveDetail), markets: markets)
        let id = "Philadelphia vs Jacksonville: Passing Yards-Jalen Hurts: 200+"
        XCTAssertEqual(rows[id]?.pregameMark, 0.425)
        // The team field goals are not a milestone card's rows.
        XCTAssertNil(rows["Philadelphia vs Jacksonville: Team Field Goals-Philadelphia: 1+"])
    }

    func testATeamMilestonesDetailsOpenThatExactOriginal() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(F.liveMarkets)
        let built = build(event, history: try F.history(F.liveHistory), markets: markets)
        let row = try XCTUnwrap(markets.playerProps?.first { $0.outcomeName == "Jacksonville: 2+" })
        let selection = try XCTUnwrap(Host.teamOriginal(
            HockeyJourneyContributionAdapter10868.milestoneID(row), event: event, markets: markets, now: F.liveNow,
            scope: built.originals))
        XCTAssertEqual(selection.scope, built.originals.catalogue?.scope)
        let chosen = built.originals.catalogue?.originals.filter { $0.identity == selection.identity } ?? []
        XCTAssertEqual(chosen.count, 1)
        XCTAssertNil(Host.teamOriginal("kalshi|no such row", event: event, markets: markets, now: F.liveNow,
                                       scope: built.originals))
    }

    // MARK: - The restored final period-winner story (Design 2026-10-31)

    func testTheCompletedNflLivePageMountsThePeriodWinnersDirectlyBeforeThePlayers() throws {
        let event = try F.detail(F.finalDetail)
        let markets = try F.markets(F.finalMarkets)
        let built = build(event, history: nil, markets: markets, route: .live, binding: F.quarterBinding,
                          now: F.finalNow)
        let cards = built.input.stories.map(\.card)
        // No history here, so no projected finish: the period card leads, then the players.
        XCTAssertEqual(cards.first, .periodWinners)
        let model = FootballEventPageModel10868(built.input)
        XCTAssertFalse(model.milestones.isEmpty)
        XCTAssertEqual(Array(cards.dropFirst()), model.milestones.map { Card.milestone($0.id) })
        XCTAssertTrue(model.isMounted(.periodWinners))
        XCTAssertEqual(built.periodWinners.count, 12)

        // Another route, the same game: not its card.
        let nfl = build(event, history: nil, markets: markets, route: .nfl, binding: F.quarterBinding,
                        now: F.finalNow)
        XCTAssertFalse(nfl.input.stories.contains { $0.card == .periodWinners })
        XCTAssertFalse(FootballEventPageModel10868(nfl.input).isMounted(.periodWinners))

        // No owner binding: the story is not offered at all.
        let unbound = build(event, history: nil, markets: markets, route: .live, now: F.finalNow)
        XCTAssertNil(unbound.input.periodWinners)
        XCTAssertFalse(unbound.input.stories.contains { $0.card == .periodWinners })

        // The live game: not its phase.
        let live = build(try F.detail(F.liveDetail), history: try F.history(F.liveHistory),
                         markets: try F.markets(F.liveMarkets), route: .live, binding: F.quarterBinding)
        XCTAssertNil(live.input.periodWinners)
    }

    func testAPeriodOriginalsDetailsOpenThatExactCatalogueOriginalWithTheSameTrade() throws {
        let event = try F.detail(F.finalDetail)
        let built = build(event, history: nil, markets: try F.markets(F.finalMarkets), route: .live,
                          binding: F.quarterBinding, now: F.finalNow)
        let q2 = try XCTUnwrap(built.periodWinners.first { $0.original.period == 2 && $0.original.side == .away })
        let selection = try XCTUnwrap(Host.periodOriginal(q2.cellID, admitted: built.periodWinners,
                                                          scope: built.originals))
        XCTAssertEqual(selection.scope, built.originals.catalogue?.scope)
        XCTAssertEqual(selection.identity, q2.identity)
        let made = try XCTUnwrap(built.originals.catalogue?.originals.first { $0.identity == q2.identity })
        XCTAssertEqual(made.pregame.figure, .value("29%"))
        XCTAssertNil(Host.periodOriginal("kalshi|0|0", admitted: built.periodWinners, scope: built.originals))
    }

    func testTheHeldPeriodOriginalReachesTheCardUnchanged() throws {
        let event = try F.detail(F.finalDetail)
        let first = build(event, history: nil, markets: try F.markets(F.finalMarkets), route: .live,
                          binding: F.quarterBinding, now: F.finalNow)
        let q3Home = try XCTUnwrap(first.periodWinners.first { $0.original.period == 3 && $0.original.side == .home })
        let held = build(event, history: nil, markets: try F.markets(F.finalMarkets), route: .live,
                         reading: Host.Reading(periodSelection: q3Home.cellID), binding: F.quarterBinding,
                         now: F.finalNow)
        XCTAssertEqual(held.input.periodWinners?.selectedID, q3Home.cellID)
    }
}
