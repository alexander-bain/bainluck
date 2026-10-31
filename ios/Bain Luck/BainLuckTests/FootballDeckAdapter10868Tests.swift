import XCTest
@testable import Bain_Luck

/// #10868 — the football screen's production deck adapter: the projected
/// finish and the player milestone cards are `EventDetailView.nflCardDeck`'s,
/// rebuilt from the same public calls, on RETAINED REAL bodies
/// (`FootballRetained10868` lists the sources, sha256 and reductions).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// Expected values are served numbers, read off the kept rows:
///   - live projected points (DraftKings rows 21, 107, 108 of the live history):
///     13:36:58.468599Z home 24.0 / away 16.5 (moneyline 0.7405), the last row
///     before the first observed 1st-quarter start (`not_before`
///     13:38:37.131207Z); 15:36:58.917778Z home 20.0 / away 21.5 (0.4878), the
///     latest, 2.8 s before the reader's clock.
///   - live milestone marks: Jalen Hurts passing yards 150+…275+ = 0.725, 0.585,
///     0.425, 0.285, 0.185, 0.11; Trevor Lawrence 225+…350+ = 0.505, 0.355,
///     0.235, 0.14, 0.085, 0.045.
///   - Packers: the served `pregame_projection` away 27.6 / home 26.5
///     (`last_before_scheduled_start`), the final 13–23 at `completed_at`
///     03:48:13.207467Z.
///   - pregame (Bills at Rams, read at its own capture 05:45:12Z): every
///     passing-yards quote but Josh Allen's 325+ (05:40:56Z) and 350+
///     (05:19:24Z) is older than the page's 30-minute window, so no ladder has
///     the three priced lines a milestone card needs.
/// The run, gap and pick are the SUBSET's (see `FootballRetained10868`).
@MainActor
final class FootballDeckAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias D = FootballDeckAdapter10868

    // MARK: - Live

    func testTheLiveDeckIsTheProjectedFinishThenTheTwoPassingLadders() throws {
        let event = try F.detail(F.liveDetail)
        let history = try F.history(F.liveHistory)
        let markets = try F.markets(F.liveMarkets)
        let host = F.deckHost(F.liveNow, arrivedAt: F.liveNow, history: history)
        let deck = D.deck(event, history: history, markets: markets, host: host)

        XCTAssertEqual(deck.map(\.id), [
            "finish",
            "milestone:Jalen Hurts|Philadelphia vs Jacksonville: Passing Yards",
            "milestone:Trevor Lawrence|Philadelphia vs Jacksonville: Passing Yards",
        ])
        let finish = try XCTUnwrap(D.finishCard(deck))
        XCTAssertEqual(finish.phase, .during)
        XCTAssertEqual(finish.pregameBasis, .history)
        XCTAssertEqual(finish.pregame, NFLFinishCard9483.Pair(
            away: 16.5, home: 24.0, at: "2026-10-11T13:36:58.468599+00:00".asDate))
        XCTAssertEqual(finish.projectedNow, NFLFinishCard9483.Pair(
            away: 21.5, home: 20.0, at: "2026-10-11T15:36:58.917778+00:00".asDate))
        XCTAssertNil(finish.final)
        XCTAssertEqual(finish.pregameName, "Earlier forecast")
        XCTAssertEqual(finish.headline(awayName: "Eagles", homeName: "Jaguars"), "The projected finish has flipped")

        let milestones = D.milestoneCards(deck)
        XCTAssertEqual(milestones.map(\.basis), [.pregameMark, .pregameMark])
        XCTAssertEqual(milestones.first?.rungs.map(\.chance), [0.725, 0.585, 0.425, 0.285, 0.185, 0.11])
        XCTAssertEqual(milestones.last?.rungs.map(\.chance), [0.505, 0.355, 0.235, 0.14, 0.085, 0.045])
        XCTAssertEqual(milestones.first?.side, .away)
        XCTAssertEqual(milestones.last?.side, .home)
        // A live price is never relabelled pregame, and no grade exists yet.
        XCTAssertTrue(milestones.allSatisfy { $0.actual == nil && $0.rungs.allSatisfy { $0.hit == nil } })
    }

    func testTheDeckIsExactlyTheProductionCallsInProductionOrder() throws {
        let event = try F.detail(F.liveDetail)
        let history = try F.history(F.liveHistory)
        let markets = try F.markets(F.liveMarkets)
        let host = F.deckHost(F.liveNow, arrivedAt: F.liveNow, history: history)

        let input = ProjectedFinalPointsMount.input(
            sportKey: event.sport, eventStatus: event.status, history: history,
            finalHome: event.homeScore, finalAway: event.awayScore, asOf: F.liveNow)
        let finish = NFLFinishCard9483.build(input, finalBaseline: nil, liveBaseline: nil)
        let milestones = NFLMilestoneCard9483.cards(
            props: markets.playerProps ?? [], eventStatus: event.status, commenceTime: event.commenceTime?.asDate,
            homeTeam: event.homeTeam, awayTeam: event.awayTeam, now: F.liveNow)
        let expected = NFLEventCardDeck9483.cards(sportKey: event.sport, finish: finish, milestones: milestones)
            .map { $0.current(at: F.liveNow) }
        XCTAssertEqual(D.deck(event, history: history, markets: markets, host: host), expected)
        // The detail serves no pregame projection, so the live card compares
        // with the history's own earlier pair.
        XCTAssertNil(D.liveBaseline(event, host: host))
    }

    func testWithoutTheHistoryClockTheLiveFinishIsRefusedAsProductionRefusesIt() throws {
        let event = try F.detail(F.liveDetail)
        let history = try F.history(F.liveHistory)
        let markets = try F.markets(F.liveMarkets)
        let deck = D.deck(event, history: history, markets: markets,
                          host: F.deckHost(F.liveNow, arrivedAt: nil, history: history))
        XCTAssertNil(D.finishCard(deck))
        XCTAssertEqual(D.milestoneCards(deck).count, 2)
    }

    // MARK: - Final

    func testTheFinishedFinishComparesTheQualifiedForecastWithTheFinal() throws {
        let event = try F.detail(F.packersDetail)
        let history = try F.history(F.packersHistory)
        let finish = try XCTUnwrap(D.finish(event, history: history,
                                            host: F.deckHost(F.packersNow, arrivedAt: F.packersNow)))
        XCTAssertEqual(finish.phase, .after)
        XCTAssertEqual(finish.pregameBasis, .scheduledStart)
        XCTAssertEqual(finish.pregame.away, 27.6, accuracy: 1e-9)
        XCTAssertEqual(finish.pregame.home, 26.5, accuracy: 1e-9)
        XCTAssertNil(finish.pregame.at)
        XCTAssertEqual(finish.final, NFLFinishCard9483.Pair(
            away: 13, home: 23, at: "2026-10-19T03:48:13.207467+00:00".asDate))
        XCTAssertNil(finish.projectedNow)
        XCTAssertEqual(finish.kicker, "Final vs forecast")
    }

    func testTheFinishedMilestoneCardCarriesTheGradeAndTheServedActual() throws {
        let event = try F.detail(F.finalDetail)
        let markets = try F.markets(F.finalMarkets)
        let cards = D.milestones(event, markets: markets, host: F.deckHost(F.finalNow, arrivedAt: nil))
        let hurts = try XCTUnwrap(cards.first { $0.player == "Jalen Hurts" })
        XCTAssertEqual(hurts.basis, .pregameMark)
        XCTAssertEqual(hurts.actual, 220)
        XCTAssertEqual(hurts.rungs.map(\.threshold), [125, 150, 175, 200, 225, 250, 275, 300, 325])
        XCTAssertEqual(hurts.rungs.map(\.hit), [true, true, true, true, false, false, false, false, false])
        XCTAssertEqual(hurts.rungs.map(\.chance), [0.835, 0.725, 0.585, 0.425, 0.285, 0.185, 0.11, 0.065, 0.03])
    }

    // MARK: - Before the start

    func testAPregameQuoteOlderThanThePagesWindowDealsNoMilestoneCard() throws {
        let event = try F.detail(F.pregameDetail)
        let markets = try F.markets(F.pregameMarkets)
        let deck = D.deck(event, history: nil, markets: markets,
                          host: F.deckHost(F.pregameNow, arrivedAt: F.pregameNow))
        XCTAssertTrue(D.milestoneCards(deck).isEmpty)
        // No history, no projected points: nothing is drawn from nothing.
        XCTAssertNil(D.finishCard(deck))
    }

    func testAnotherSportGetsNoFootballDeck() throws {
        // CONSTRUCTED: the live detail with only its `sport` key replaced.
        let event = try F.detail(F.edited(F.liveDetail, setting: ["sport": "icehockey_nhl"]))
        let deck = D.deck(event, history: try F.history(F.liveHistory), markets: try F.markets(F.liveMarkets),
                          host: F.deckHost(F.liveNow, arrivedAt: F.liveNow))
        XCTAssertTrue(deck.isEmpty)
    }
}
