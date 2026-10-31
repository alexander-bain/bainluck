import SwiftUI
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

    // MARK: - One hold per action (Design 2026-10-31, FOOTBALL-READER-SELECTION-AND-DETAILS)
    //
    // Every landing is logged as one string, in order: the page's hold as
    // "hold", a presented mode by its `Presented` id ("present:reader.periodWinners",
    // "present:catalogue", "present:original", …), a held catalogue selection by
    // its exact identity ("select:kalshi|64559196|242843305"), a stream browse by
    // its card key, and the card selections the page writes directly
    // ("periodSelect:<original id>", "teamSelect:<card key>:<group id>"). The
    // stream hooks are the stream's own (`activationIntents`, `intents(for:)`),
    // sending into the host's own routes.

    /// The quarter originals' exact ids, as the retained binding names them
    /// (Kalshi market · contributor outcome).
    private static let q2Away = "kalshi|64559196|242843305"
    private static let q3Home = "kalshi|64559205|242843331"
    private static let q3Away = "kalshi|64559205|242843332"
    private static let q3Tie = "kalshi|64559205|242843333"
    private static let q4Tie = "kalshi|64559214|242843360"

    /// The completed game on `nfl-live` with the period card bound: the card the stream opens on.
    private func finalPage(reading: Host.Reading = Host.Reading(),
                           binding: FootballPeriodWinnersAdapter10868.Binding? = nil,
                           markets json: String? = nil) throws -> Host.Built {
        build(try F.detail(F.finalDetail), history: nil, markets: try F.markets(json ?? F.finalMarkets), route: .live,
              reading: reading, binding: binding ?? F.quarterBinding, now: F.finalNow)
    }

    /// The host's own routes for one mode, every landing logged.
    private func routes(_ built: Host.Built, _ mode: FootballEventPageMode10868, event: EventDetail, now: Date,
                        hook: Bool = true, log: @escaping (String) -> Void) -> Host.Routes {
        Host.routes(built, mode: mode, event: event, now: now, hold: hook ? { log("hold") } : nil,
                    present: { log("present:" + Host.Presented(mode: $0).id) },
                    select: { log("select:" + FootballPeriodWinnersAdapter10868.cellID($0.identity)) },
                    browse: { log("browse:" + ($0?.key ?? "none")) })
    }

    /// The page exactly as the host composes it, with the routes' callbacks and
    /// the card selections the host writes directly, logged.
    private func view(_ built: Host.Built, _ mode: FootballEventPageMode10868, routes: Host.Routes,
                      log: @escaping (String) -> Void) -> FootballEventPagePresentation10868 {
        FootballEventPagePresentation10868(
            input: built.input, cardState: NFLCardDeckState9483(), mode: mode, originals: built.originals,
            showsMilestoneDetails: true,
            onAbout: nil,
            onAllProps: routes.allProps,
            onOriginalSelect: routes.originalSelect,
            onOriginalHistory: nil,
            onStoryIntent: routes.storyIntent,
            onHistoryAction: routes.historyAction,
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onForecastInspection: routes.forecastInspection,
            onTeamMilestoneSelect: { card, id in log("teamSelect:\(card.key):\(id)") },
            onTeamMilestoneDetails: routes.teamDetails,
            onTeamMilestoneExpand: routes.teamExpand,
            onSplitDetails: nil,
            onPeriodSelect: { log("periodSelect:\($0)") },
            onPeriodDetails: routes.periodDetails,
            onPeriodExpand: routes.periodExpand)
    }

    /// The stream's own activation hook for one displayed card, sending into the routes.
    private func activation(_ built: Host.Built, _ card: Card, routes: Host.Routes) -> StoryStreamCardActivation10868 {
        let stream = built.input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: card.key)
        return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved),
                                              send: routes.storyIntent)
    }

    func testTheRetainedBindingNamesTheQuarterOriginalsTheseLogsUse() throws {
        let built = try finalPage()
        func id(_ period: Int, _ side: FootballPeriodWinnersAdapter10868.Side) -> String? {
            let found = built.periodWinners.filter { $0.original.period == period && $0.original.side == side }
            return found.count == 1 ? found[0].cellID : nil
        }
        XCTAssertEqual(id(2, .away), Self.q2Away)
        XCTAssertEqual(id(3, .home), Self.q3Home)
        XCTAssertEqual(id(3, .away), Self.q3Away)
        XCTAssertEqual(id(3, .tie), Self.q3Tie)
        XCTAssertEqual(id(4, .tie), Self.q4Tie)
        // Nothing held: the card opens on its suggested original, the Q2 upset.
        XCTAssertEqual(built.input.periodWinners?.selectedID, Self.q2Away)
        // Every one of the twelve resolves in this pass's catalogue, so each offers Details.
        XCTAssertEqual(built.input.periodWinners?.detailsOriginalIDs, Set(built.periodWinners.map(\.cellID)))
        XCTAssertEqual(built.input.periodWinners?.cells.count, 12)
    }

    func testThePagesStreamOpenAndThePeriodCardsOwnActionsHoldOnceAndTheRouteAddsNoSecondHold() throws {
        let event = try F.detail(F.finalDetail)
        let built = try finalPage()
        var log: [String] = []
        let routes = self.routes(built, .page, event: event, now: F.finalNow) { log.append($0) }
        let page = view(built, .page, routes: routes) { log.append($0) }
        let hook = activation(built, .periodWinners, routes: routes)
        XCTAssertTrue(hook.isAvailable)

        // Building the routes, the page and the card, and reading them, asks for nothing.
        let card = try XCTUnwrap(page.periodWinnersContent(activation: hook))
        _ = card.input.selected
        _ = card.input.detailsTarget(canOpenDetails: true)
        XCTAssertEqual(log, [])

        // The stream's own open: its interaction (the hold), then the open — one hold.
        let stream = built.input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: Card.periodWinners.key)
        let open = stream.intents(for: .open(ref), resolved: resolved)
        XCTAssertEqual(open, [.interaction(scope: stream.scope, card: ref), .open(ref)])
        open.forEach(routes.storyIntent)
        XCTAssertEqual(log, ["hold", "present:reader.periodWinners"])

        // The stream's browse: one hold, then the next card.
        log.removeAll()
        let next = try XCTUnwrap(resolved.next?.slot.ref)
        XCTAssertEqual(next.id, Card.milestone(try XCTUnwrap(FootballEventPageModel10868(built.input).milestones.first).id).key)
        stream.intents(for: .browse(.next), resolved: resolved).forEach(routes.storyIntent)
        XCTAssertEqual(log, ["hold", "browse:\(next.id)"])

        // The card's own Details, select and open: the card's stream hook holds
        // once, then the exact landing.
        log.removeAll()
        card.onDetails?(Self.q2Away)
        XCTAssertEqual(log, ["hold", "select:\(Self.q2Away)", "present:original"])
        log.removeAll()
        card.onSelect?(Self.q3Away)
        XCTAssertEqual(log, ["hold", "periodSelect:\(Self.q3Away)"])
        log.removeAll()
        card.onExpand?()
        XCTAssertEqual(log, ["hold", "present:reader.periodWinners"])
    }

    func testATeamCardsDetailsSelectAndOpenHoldOnceThroughTheStream() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(F.liveMarkets)
        let built = build(event, history: try F.history(F.liveHistory), markets: markets,
                          reading: Host.Reading(story: .teamFieldGoals))
        XCTAssertEqual(built.input.stream.primary?.id, Card.teamFieldGoals.key)
        let row = try XCTUnwrap(markets.playerProps?.first { $0.outcomeName == "Jacksonville: 2+" })
        let originalID = HockeyJourneyContributionAdapter10868.milestoneID(row)
        let target = try XCTUnwrap(Host.teamOriginal(originalID, event: event, markets: markets, now: F.liveNow,
                                                     scope: built.originals))
        var log: [String] = []
        let routes = self.routes(built, .page, event: event, now: F.liveNow) { log.append($0) }
        let paired = try XCTUnwrap(view(built, .page, routes: routes) { log.append($0) }
            .pairedContent(.teamFieldGoals, activation: activation(built, .teamFieldGoals, routes: routes)))
        XCTAssertEqual(log, [])

        paired.onDetails?(originalID)
        XCTAssertEqual(log, ["hold", "select:\(FootballPeriodWinnersAdapter10868.cellID(target.identity))",
                             "present:original"])
        log.removeAll()
        paired.onSelect?("teamFieldGoals:2+")
        XCTAssertEqual(log, ["hold", "teamSelect:teamFieldGoals:teamFieldGoals:2+"])
        log.removeAll()
        paired.onExpand?(Card.teamFieldGoals.key)
        XCTAssertEqual(log, ["hold", "present:reader.teamFieldGoals"])

        // Full size: the same callbacks, no activation, no hold.
        log.removeAll()
        let readerRoutes = self.routes(built, .reader(.teamFieldGoals), event: event, now: F.liveNow) { log.append($0) }
        let full = try XCTUnwrap(view(built, .reader(.teamFieldGoals), routes: readerRoutes) { log.append($0) }
            .pairedContent(.teamFieldGoals, activation: nil))
        XCTAssertNil(full.onExpand)
        full.onDetails?(originalID)
        XCTAssertEqual(log, ["select:\(FootballPeriodWinnersAdapter10868.cellID(target.identity))", "present:original"])
    }

    func testTheFullCardsActionsAlreadyHeldLandWithNoSecondHold() throws {
        let event = try F.detail(F.finalDetail)
        let built = try finalPage()
        var log: [String] = []
        let mode = FootballEventPageMode10868.reader(.periodWinners)
        let routes = self.routes(built, mode, event: event, now: F.finalNow) { log.append($0) }
        let card = try XCTUnwrap(view(built, mode, routes: routes) { log.append($0) }
            .periodWinnersContent(activation: nil))
        XCTAssertNil(card.onExpand, "the full card offers no open of its own")
        XCTAssertEqual(log, [])

        card.onDetails?(Self.q2Away)
        card.onSelect?(Self.q4Tie)
        // The full-size history's headline forecast control and Full chart route
        // with no second hold either.
        routes.forecastInspection(true)
        routes.historyAction(HockeyJourneyHistoryAdapter10868.expandActionID)
        XCTAssertEqual(log, ["select:\(Self.q2Away)", "present:original",
                             "periodSelect:\(Self.q4Tie)",
                             "present:reader.finish",
                             "present:reader.history"])
        XCTAssertFalse(log.contains("hold"))
    }

    func testUnrelayedPageActionsEachHoldOnceThenLandAndAnUnroutedIdHoldsNothing() throws {
        let event = try F.detail(F.finalDetail)
        let built = try finalPage()
        var log: [String] = []
        let routes = self.routes(built, .page, event: event, now: F.finalNow) { log.append($0) }
        let page = view(built, .page, routes: routes) { log.append($0) }
        _ = page.historyContent(reader: false)
        XCTAssertEqual(log, [])

        page.openAllProps()
        page.historyContent(reader: false).onAction?(HockeyJourneyHistoryAdapter10868.expandActionID)
        page.historyContent(reader: false).onAction?("constructed:not-a-host-action")
        routes.forecastInspection(false)
        XCTAssertEqual(log, ["hold", "present:catalogue",
                             "hold", "present:reader.history",
                             "hold", "present:reader.finish"])

        // A catalogue original: one hold, then the exact selection and its Details.
        log.removeAll()
        let chosen = try XCTUnwrap(Host.periodOriginal(Self.q2Away, admitted: built.periodWinners,
                                                       scope: built.originals))
        let catalogueRoutes = self.routes(built, .catalogue, event: event, now: F.finalNow) { log.append($0) }
        view(built, .catalogue, routes: catalogueRoutes) { log.append($0) }.catalogueContent()?.onSelect?(chosen)
        XCTAssertEqual(log, ["hold", "select:\(Self.q2Away)", "present:original"])

        // Without a hook every route is the host's own landing.
        log.removeAll()
        self.routes(built, .page, event: event, now: F.finalNow, hook: false) { log.append($0) }.allProps()
        XCTAssertEqual(log, ["present:catalogue"])
    }

    // MARK: - The held original and working Details (same review)

    func testAHeldPeriodOriginalSurvivesABindingOmissionAndReturnsByExactIdentity() throws {
        // CONSTRUCTED: a binding update that omits the held Q3 home original.
        let omitted = FootballPeriodWinnersAdapter10868.Binding(
            eventID: F.quarterBinding.eventID, verifiedStart: F.quarterBinding.verifiedStart,
            originals: F.quarterBinding.originals.filter { !($0.period == 3 && $0.side == .home) })
        let reading = Host.Reading(periodSelection: Self.q3Home)
        let without = try finalPage(reading: reading, binding: omitted)
        let card = try XCTUnwrap(without.input.periodWinners)
        XCTAssertEqual(card.selectedID, Self.q3Home, "the held id is not replaced")
        XCTAssertNil(card.selected, "the card shows its no-selection readout, never another original")
        XCTAssertEqual(card.cells.count, 11)
        XCTAssertNil(Host.detailsControls(without) { _ in XCTFail("nothing to open") }.period)

        // The exact original reappears: the same held id selects it, with working Details.
        let back = try finalPage(reading: reading)
        XCTAssertEqual(back.input.periodWinners?.selected?.cell.id, Self.q3Home)
        var opened: [OriginalMarketDetails9483.Selection] = []
        let controls = Host.detailsControls(back) { opened.append($0) }
        controls.period?(Self.q3Home)
        XCTAssertEqual(opened.map { FootballPeriodWinnersAdapter10868.cellID($0.identity) }, [Self.q3Home])
        XCTAssertEqual(opened.first?.scope, back.originals.catalogue?.scope)
    }

    func testASelectedWithdrawnOriginalOffersNoDeadDetailsWhileItsWorkingNeighbourDoes() throws {
        let event = try F.detail(F.finalDetail)
        // CONSTRUCTED: the Q3 tie row no longer served (its period row dropped).
        let json = try F.edited(F.finalMarkets, setting: ["period_markets": try periodRows(droppingOutcome: 242843333)])
        let withdrawn = try finalPage(reading: Host.Reading(periodSelection: Self.q3Tie), markets: json)
        let card = try XCTUnwrap(withdrawn.input.periodWinners)

        // Every comparison original stays, the withdrawn one included and still selected.
        XCTAssertEqual(card.cells.count, 12)
        XCTAssertEqual(card.selected?.cell.id, Self.q3Tie)
        XCTAssertEqual(card.selected?.cell.pregameMissing, FootballPeriodWinnersCopy10868.originalUnavailable)
        // Its own baselines and the unnormalized Q4 stand: 56% + 32% + 15% = 103%.
        let q4 = card.cells.filter { $0.periodID == FootballPeriodWinnersAdapter10868.periodID(event, 4) }
            .compactMap { $0.pregame?.probability }
        XCTAssertEqual(q4, [0.56, 0.32, 0.15])
        XCTAssertEqual(q4.reduce(0, +), 1.03, accuracy: 1e-9)

        // It is not in this pass's catalogue, so it offers no Details at any layer.
        XCTAssertNil(Host.periodOriginal(Self.q3Tie, admitted: withdrawn.periodWinners, scope: withdrawn.originals))
        let full = try finalPage()
        XCTAssertEqual(card.detailsOriginalIDs, Set(full.periodWinners.map(\.cellID)).subtracting([Self.q3Tie]))
        XCTAssertNil(card.detailsTarget(canOpenDetails: true))
        XCTAssertNil(Host.detailsControls(withdrawn) { _ in XCTFail("nothing to open") }.period)
        var log: [String] = []
        let routes = self.routes(withdrawn, .page, event: event, now: F.finalNow) { log.append($0) }
        XCTAssertNil(routes.periodDetails)
        let shown = try XCTUnwrap(view(withdrawn, .page, routes: routes) { log.append($0) }
            .periodWinnersContent(activation: activation(withdrawn, .periodWinners, routes: routes)))
        XCTAssertNil(shown.onDetails, "no enabled control that would open nothing")
        // The card is still selectable: its neighbour is one tap away.
        shown.onSelect?(Self.q3Home)
        XCTAssertEqual(log, ["hold", "periodSelect:\(Self.q3Home)"])

        // The working neighbour, held on the next pass, keeps its Details.
        log.removeAll()
        let neighbour = try finalPage(reading: Host.Reading(periodSelection: Self.q3Home), markets: json)
        XCTAssertEqual(neighbour.input.periodWinners?.detailsTarget(canOpenDetails: true), Self.q3Home)
        XCTAssertEqual(neighbour.input.periodWinners?.cells.count, 12)
        let neighbourRoutes = self.routes(neighbour, .page, event: event, now: F.finalNow) { log.append($0) }
        let working = try XCTUnwrap(view(neighbour, .page, routes: neighbourRoutes) { log.append($0) }
            .periodWinnersContent(activation: activation(neighbour, .periodWinners, routes: neighbourRoutes)))
        working.onDetails?(Self.q3Home)
        XCTAssertEqual(log, ["hold", "select:\(Self.q3Home)", "present:original"])
    }

    func testAnUnroutedOrUnnarrowedPeriodOriginalOffersNoDetailsAndNoNeighbourStandsIn() throws {
        let built = try finalPage(reading: Host.Reading(periodSelection: Self.q3Home))
        let catalogue = try XCTUnwrap(built.originals.catalogue)
        let q3Home = try XCTUnwrap(FootballPeriodWinnersAdapter10868.admitted(cellID: Self.q3Home,
                                                                              in: built.periodWinners))
        func originals(_ list: [OriginalMarketDetails9483.Original]) -> FootballEventPageOriginals10868 {
            FootballEventPageOriginals10868(
                catalogue: OriginalMarketDetails9483.Catalogue(scope: catalogue.scope, originals: list),
                selection: nil, heading: built.originals.heading, emptyWords: built.originals.emptyWords,
                unavailableChoice: built.originals.unavailableChoice, tint: built.originals.tint)
        }
        let card = try XCTUnwrap(built.input.periodWinners)
        let all = Set(built.periodWinners.map(\.cellID))

        // CONSTRUCTED: a catalogue that no longer lists the held original, and one that lists it twice.
        let lacking = originals(catalogue.originals.filter { $0.identity != q3Home.identity })
        let doubled = originals(catalogue.originals + catalogue.originals.filter { $0.identity == q3Home.identity })
        for scope in [lacking, doubled] {
            let narrowed = Host.offeringDetails(card, admitted: built.periodWinners, originals: scope)
            XCTAssertEqual(narrowed.detailsOriginalIDs, all.subtracting([Self.q3Home]))
            XCTAssertEqual(narrowed.cells, card.cells, "every comparison original stays")
            XCTAssertEqual(narrowed.selectedID, Self.q3Home)
            XCTAssertNil(narrowed.detailsTarget(canOpenDetails: true))
            var input = built.input
            input.periodWinners = narrowed
            let pass = Host.Built(input: input, originals: scope, scoped: built.scoped, periodWinners: built.periodWinners)
            XCTAssertNil(Host.detailsControls(pass) { _ in XCTFail("no neighbour opens in its place") }.period)
        }

        // No catalogue at all: no Details, every original still shown.
        let none = FootballEventPageOriginals10868(
            catalogue: nil, selection: nil, heading: built.originals.heading, emptyWords: built.originals.emptyWords,
            unavailableChoice: built.originals.unavailableChoice, tint: built.originals.tint)
        let bare = Host.offeringDetails(card, admitted: built.periodWinners, originals: none)
        XCTAssertEqual(bare.detailsOriginalIDs, [])
        XCTAssertEqual(bare.cells.count, 12)

        // An owner's own availability stays an upper bound.
        var owned = card
        owned.detailsOriginalIDs = [Self.q2Away]
        XCTAssertEqual(Host.offeringDetails(owned, admitted: built.periodWinners, originals: built.originals)
            .detailsOriginalIDs, [Self.q2Away])

        // CONSTRUCTED: a card not narrowed for this catalogue fails closed.
        var unnarrowed = built.input
        unnarrowed.periodWinners?.detailsOriginalIDs = nil
        let pass = Host.Built(input: unnarrowed, originals: built.originals, scoped: built.scoped,
                              periodWinners: built.periodWinners)
        XCTAssertNil(Host.detailsControls(pass) { _ in XCTFail("not narrowed") }.period)
        // The real pass: the held original resolves and opens exactly itself.
        var opened: [String] = []
        Host.detailsControls(built) { opened.append(FootballPeriodWinnersAdapter10868.cellID($0.identity)) }
            .period?(Self.q3Home)
        XCTAssertEqual(opened, [Self.q3Home])
    }

    /// The final body's period rows as served, less the row with one contributor outcome.
    private func periodRows(droppingOutcome outcome: Int) throws -> [[String: Any]] {
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(F.finalMarkets.utf8)) as? [String: Any])
        let rows = try XCTUnwrap(object["period_markets"] as? [[String: Any]])
        let kept = rows.filter { ($0["contributor_outcome_ids"] as? [Int]) != [outcome] }
        XCTAssertEqual(kept.count, rows.count - 1)
        return kept
    }
}
