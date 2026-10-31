import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game adapter, part four (the final stories and the
/// associated series), on the RETAINED REAL `/game-markets` and
/// `/related-futures` of the White Sox–Astros game (`BaseballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The final stories are the production deal (`MLBFinalDeck11284`) taken
/// unchanged; what is pinned here is that they are exactly that deal, each
/// with its production default and colour, that the host's held selection is
/// passed through untouched, that only a finished game deals them, and that a
/// story's Details request resolves only an original the page holds.
@MainActor
final class BaseballStoriesAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias S = BaseballStoriesAdapter10868
    private typealias G = BaseballGamePageAdapter10868

    private func deal(_ event: EventDetail) throws -> [MLBFinalCard11284] {
        S.finalCards(event, markets: try F.markets(), related: try F.related())
    }

    func testAfterTheFinalTheStoriesAreTheProductionDealWithItsOwnDefaultsAndColours() throws {
        let event = try F.finalEvent()
        let markets = try F.markets()
        let related = try F.related()
        let cards = try deal(event)
        XCTAssertEqual(cards, MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: F.eventID, sportKey: "baseball_mlb", status: "completed",
            homeTeam: event.homeTeam, awayTeam: event.awayTeam, homeScore: 3, awayScore: 7,
            gameMarkets: markets, relatedFutures: related)))
        let tints = G.tints(event)

        let homeRuns = try XCTUnwrap(S.homeRuns(cards, event: event))
        XCTAssertEqual(homeRuns.card.entries.map(\.player), ["Yordan Alvarez", "Christian Walker", "Munetaka Murakami"])
        XCTAssertEqual(homeRuns.awayColor, tints.away)
        XCTAssertEqual(homeRuns.homeColor, tints.home)

        let strikeouts = try XCTUnwrap(S.strikeouts(cards, event: event, selected: nil))
        XCTAssertEqual(strikeouts.card.player, "Hunter Brown")
        XCTAssertEqual(strikeouts.selectedRowID, "Hunter Brown: Strikeouts O/U 6.5-Over", "the production default, 7+")
        XCTAssertEqual(strikeouts.color, PlayerPropsTeam.color(for: strikeouts.card.side, home: tints.home, away: tints.away))
        XCTAssertEqual(S.strikeouts(cards, event: event, selected: "held")?.selectedRowID, "held",
                       "a held target is passed through, never re-elected")

        let totals = try XCTUnwrap(S.finalTotals(cards, event: event, selected: nil))
        XCTAssertEqual(totals.card.actualTotal, 10)
        XCTAssertEqual(totals.selectedOptionKey, "o:244311417", "the highest line the final total cleared, 9.5")
        XCTAssertEqual(totals.homeScore, 3)
        XCTAssertEqual(totals.awayScore, 7)
        XCTAssertEqual(totals.homeName, G.names(event).home)
        XCTAssertEqual(totals.awayName, G.names(event).away)
        XCTAssertEqual(S.finalTotals(cards, event: event, selected: "o:244311410")?.selectedOptionKey, "o:244311410")

        let series = try XCTUnwrap(S.series(event, related: related, question: nil, option: nil))
        XCTAssertEqual(series.card.questions.count, 4)
        XCTAssertEqual(series.card.optionCount, 9)
        XCTAssertEqual(series.selectedQuestionKey, series.card.questions.first?.questionKey)
        XCTAssertNil(series.selectedOptionKey, "no outcome is chosen for the reader")
        XCTAssertEqual(series.color, tints.home)
        let held = try XCTUnwrap(S.series(event, related: related, question: "m:62898790", option: "o:held"))
        XCTAssertEqual(held.selectedQuestionKey, "m:62898790")
        XCTAssertEqual(held.selectedOptionKey, "o:held")

        XCTAssertEqual(S.totals(event, markets: markets, cards: cards, selected: nil, host: F.milestoneHost(F.finalNow)),
                       .finalTargets(totals))
    }

    func testBeforeAndDuringPlayNoFinalStoryIsDealtTheSeriesStaysAndTheTotalsAreMilestones() throws {
        let markets = try F.markets()
        let related = try F.related()
        let live = try F.liveEvent()
        let before = try F.beforeEvent()
        let phases: [(EventDetail, Date)] = [(live, F.liveNow), (before, F.beforeNow)]
        for (event, now) in phases {
            let cards = try deal(event)
            XCTAssertTrue(cards.isEmpty, "\(event.status ?? "-")")
            XCTAssertNil(S.homeRuns(cards, event: event))
            XCTAssertNil(S.strikeouts(cards, event: event, selected: nil))
            XCTAssertNil(S.finalTotals(cards, event: event, selected: nil))
            XCTAssertEqual(S.series(event, related: related, question: nil, option: nil)?.card.questions.count, 4,
                           "the series is its own scope in every phase")
            let host = F.milestoneHost(now)
            let milestones = try XCTUnwrap(BaseballRunMilestonesAdapter10868.input(event, markets: markets, host: host))
            XCTAssertEqual(S.totals(event, markets: markets, cards: cards, selected: nil, host: host),
                           .milestones(milestones))
        }
    }

    /// CONSTRUCTED: the final detail with only `id` changed, then with only
    /// `home_score` null.
    func testAnotherEventsBodiesDealNothingAndAnUnprintedScoreIsNoActual() throws {
        let other = try F.detail(F.edited(F.finalDetail, setting: ["id": 1]))
        XCTAssertTrue(try deal(other).isEmpty)
        XCTAssertNil(S.series(other, related: try F.related(), question: nil, option: nil))

        let noScore = try F.detail(F.edited(F.finalDetail, setting: ["home_score": NSNull()]))
        let totals = try XCTUnwrap(S.finalTotals(try deal(noScore), event: noScore, selected: nil))
        XCTAssertNil(totals.card.actualTotal, "never a total from one side's score")
        XCTAssertNil(totals.homeScore)
        XCTAssertNil(totals.awayScore)
        XCTAssertEqual(totals.selectedOptionKey, totals.card.lines.first?.optionKey, "the lowest line without a total")
    }

    func testAStoryDetailsRequestResolvesOnlyAnOriginalThePageHolds() throws {
        let final = try F.finalEvent()
        let built = BaseballEventPageHost10868.build(
            event: final, history: nil, markets: try F.markets(), related: try F.related(),
            probabilityObservedAt: nil, now: F.finalNow, calendar: F.pacific, locale: F.locale)
        let homeRun = try XCTUnwrap(built.input.homeRuns?.card.entries.first?.original)
        let target = try XCTUnwrap(built.input.strikeouts?.card.targets.first?.original)
        let outcome = try XCTUnwrap(built.input.series?.card.questions.first?.options.first?.original)
        XCTAssertEqual(S.original(homeRun.id, in: built.input), homeRun)
        XCTAssertEqual(S.original(target.id, in: built.input), target)
        XCTAssertEqual(S.original(outcome.id, in: built.input), outcome)
        guard case .finalTargets(let totals)? = built.input.totals else { return XCTFail("final targets") }
        let line = try XCTUnwrap(totals.card.lines.last?.original)
        XCTAssertEqual(S.original(line.id, in: built.input), line)
        XCTAssertNil(S.original("not-an-original", in: built.input))

        // During play the page holds no home-run story, so its original is not
        // resolved from the payload behind it.
        let live = BaseballEventPageHost10868.build(
            event: try F.liveEvent(), history: nil, markets: try F.markets(), related: try F.related(),
            probabilityObservedAt: F.liveObservedAt, now: F.liveNow, calendar: F.pacific, locale: F.locale)
        XCTAssertNil(S.original(homeRun.id, in: live.input))
        XCTAssertEqual(S.original(outcome.id, in: live.input), outcome, "the series is held in every phase")
    }
}
