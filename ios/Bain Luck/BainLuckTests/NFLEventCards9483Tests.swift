import SwiftUI
import Vision
import XCTest
@testable import Bain_Luck

/// #9483 — the NFL cards and their full-size reader (design ref #10868 v107,
/// v110 selection, v157/v158 held reading, v159 forecast expiry).
///
/// What these pin, and the mutation each kills:
/// - say "flipped" when the leader did not change → `testAProjectionThatKeepsItsLeaderNeverSaysFlipped`
/// - drop the flip when it did → `testAProjectionWhoseLeaderChangedSaysFlipped`
/// - read a stale live projection as "now" → `testAStaleLiveProjectionIsNotProjectedNow`
/// - make the final a projection → `testTheFinalIsTheScoreNotAProjection`
/// - call a beaten forecast "as projected" → `testAFinalAgainstThePregameLeaderSaysBeatTheForecast`
/// - relabel a live/settled price "pregame" → `testOncePlayStartsTheCardReadsThePregameMarkNeverTheLivePrice`
/// - show a grade or actual before the final → `testNoGradeOrActualBeforeTheFinal`
/// - admit a D/ST or a two-line ladder → `testTeamSubjectsAndShortLaddersAreNotCards`
/// - more than two, or two of one player → `testAtMostTwoPlayerCardsOnePerPlayer`
/// - a different deck on relaunch → `testTheDeckOrderIsStable`
/// - select a neighbour when the chosen row vanishes → `testAWithdrawnRowSelectsNothing`
/// - rewrite a held card under the reader → `testTheReaderHoldsWhatItOpenedOn`
/// - keep an expired projection because the reader was looking → `testAnExpiredProjectionLeavesTheHeldCard`
/// - lose the card Back returns to → `testBackReturnsToTheCardItOpenedFrom`
///
/// Design-owner return of 23654f0b (10/14), one guard per finding:
/// - admit a stale or undated pregame quote as current → `testFreshStaleAndMissingClocksAreThreeDifferentDisplays`
/// - keep a price current because the reader was open → `testAHeldPregamePriceExpiresWhileTheReaderIsOpen`
/// - copy today's price into a missing baseline → `testAMissingPregameMarkIsNeverTheLivePrice`
/// - read an Under leg as the over chance → `testAnUnderLegIsNotARung`
/// - let Details show a newer row than the held card → `testDetailsRowsAreHeldWithTheCardsUntilRefresh`
/// - plot an actual outside the stat axis → `testTheStatAxisAdmitsActualsBelowWithinAndAboveTheLadder`
/// - rebuild the large-text chrome → `testTheReaderRendersTheMatchLineCountAndBack`
@MainActor
final class NFLEventCards9483Tests: XCTestCase {

    private let base = Date(timeIntervalSince1970: 1_791_000_000)
    private func t(_ minutes: Double) -> Date { base.addingTimeInterval(minutes * 60) }

    private func pair(_ minutes: Double, home: Double, away: Double) -> ProjectedFinalPointsSeries.Pair {
        .init(at: t(minutes), home: home, away: away, homeProbability: nil, kind: .recorded)
    }

    private func input(_ pairs: [ProjectedFinalPointsSeries.Pair], floor: Double?, final: Double? = nil,
                       actuals: [ProjectedFinalPointsSeries.Actual] = [], now: Double) -> ProjectedFinalPointsSeries.Input {
        .init(sportKey: "americanfootball_nfl", sourceKey: "draftkings",
              basis: .sameBookSameCaptureFullGameSpreadAndTotal, pairs: pairs, actuals: actuals,
              kickoffAt: nil, scoreObservationStartAt: floor.map(t), finalAt: final.map(t),
              asOf: t(now), windowStartAt: nil, requestCutoffAt: nil)
    }

    private func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }

    /// `observed` defaults to five minutes before the tests' `now` (t(0)):
    /// a current quote.
    private func prop(_ subject: String, _ market: String, _ line: Double, price: Double?, mark: Double? = nil,
                      team: String? = "home", actual: Double? = nil, hit: Bool? = nil,
                      observed: String? = "default", inverted: Bool? = nil) -> GameMarketPlayerProp {
        GameMarketPlayerProp(marketName: market,
                             outcomeName: "\(subject): \(PlayerPropsFamily.targetLabel(line)) \(market)",
                             threshold: line, overProbability: price, source: "kalshi", movement: nil,
                             playerHeadshot: nil, playerTeam: team, actual: actual, hit: hit, pregameMark: mark,
                             observedAt: observed == "default" ? iso(t(-5)) : observed, _inverted: inverted)
    }

    private func ladder(_ subject: String, _ market: String, lines: [Double], prices: [Double], marks: [Double]? = nil,
                        actual: Double? = nil, observed: [String?]? = nil) -> [GameMarketPlayerProp] {
        lines.indices.map { i in
            prop(subject, market, lines[i], price: prices[i], mark: marks?[i], actual: actual,
                 hit: actual.map { $0 >= lines[i] }, observed: observed.map { $0[i] } ?? "default")
        }
    }

    // MARK: - Projected finish

    func testAProjectionThatKeepsItsLeaderNeverSaysFlipped() throws {
        // v107: halftime 18–20.5 must not say the projected winner flipped.
        let card = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 20.5, away: 18), pair(30, home: 23, away: 19)], floor: 0, now: 40)))
        XCTAssertEqual(card.phase, .during)
        XCTAssertEqual(card.pregame.home, 20.5)
        XCTAssertEqual(card.projectedNow?.home, 23)
        XCTAssertEqual(card.headline(awayName: "Eagles", homeName: "Bears"), "Bears still projected ahead")
    }

    func testAProjectionWhoseLeaderChangedSaysFlipped() throws {
        let card = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 19.5, away: 23), pair(30, home: 25.5, away: 18)], floor: 0, now: 40)))
        XCTAssertEqual(card.headline(awayName: "Eagles", homeName: "Bears"), "The projected finish has flipped")
    }

    func testAStaleLiveProjectionIsNotProjectedNow() throws {
        let card = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 19.5, away: 23), pair(30, home: 25.5, away: 18)], floor: 0, now: 30 + 61)))
        XCTAssertNil(card.projectedNow, "a projection past the capture gap is not current")
        XCTAssertEqual(card.headline(awayName: "Eagles", homeName: "Bears"), "Eagles projected ahead before kickoff")
    }

    func testTheFinalIsTheScoreNotAProjection() throws {
        let card = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 19.5, away: 23), pair(60, home: 25.5, away: 18)], floor: 0, final: 200,
            actuals: [.init(at: t(200), home: 27, away: 7)], now: 200)))
        XCTAssertEqual(card.phase, .after)
        XCTAssertEqual(card.final?.home, 27)
        XCTAssertEqual(card.final?.away, 7)
        XCTAssertNil(card.projectedNow)
    }

    func testAFinalAgainstThePregameLeaderSaysBeatTheForecast() throws {
        let beat = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 19.5, away: 23)], floor: 0, final: 200,
            actuals: [.init(at: t(200), home: 27, away: 7)], now: 200)))
        XCTAssertEqual(beat.headline(awayName: "Eagles", homeName: "Bears"), "Bears beat the forecast")
        let asProjected = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 24, away: 17)], floor: 0, final: 200,
            actuals: [.init(at: t(200), home: 27, away: 7)], now: 200)))
        XCTAssertEqual(asProjected.headline(awayName: "Eagles", homeName: "Bears"), "Bears won as projected")
    }

    func testNoProjectionBeforeTheGameMeansNoCard() {
        XCTAssertNil(NFLFinishCard9483.build(input([pair(30, home: 25, away: 18)], floor: 0, now: 40)))
        var other = input([pair(-30, home: 20, away: 18)], floor: 0, now: 40)
        other = .init(sportKey: "basketball_nba", sourceKey: other.sourceKey, basis: other.basis, pairs: other.pairs,
                      actuals: [], kickoffAt: nil, scoreObservationStartAt: other.scoreObservationStartAt,
                      finalAt: nil, asOf: other.asOf, windowStartAt: nil, requestCutoffAt: nil)
        XCTAssertNil(NFLFinishCard9483.build(other), "NFL only")
    }

    // MARK: - Player milestones

    private let yards: [Double] = [39.5, 49.5, 59.5, 69.5, 79.5]

    func testBeforeKickoffTheCardReadsTheCurrentPregamePrice() throws {
        let props = ladder("D'Andre Swift", "Rushing Yards", lines: yards,
                           prices: [0.76, 0.64, 0.53, 0.40, 0.295], marks: [0.7, 0.6, 0.5, 0.4, 0.3])
        let card = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: props, eventStatus: "scheduled", commenceTime: t(60),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0)).first)
        XCTAssertEqual(card.basis, .pregamePrice)
        XCTAssertEqual(card.rungs.map(\.chance), [0.76, 0.64, 0.53, 0.40, 0.295])
        XCTAssertEqual(card.caption, "Pregame chance to reach each line")
    }

    func testOncePlayStartsTheCardReadsThePregameMarkNeverTheLivePrice() throws {
        let props = ladder("D'Andre Swift", "Rushing Yards", lines: yards,
                           prices: [1, 1, 0.9, 0.2, 0.05], marks: [0.76, 0.64, 0.53, 0.40, 0.295])
        let card = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: props, eventStatus: "live", commenceTime: t(-60),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0)).first)
        XCTAssertEqual(card.basis, .pregameMark)
        XCTAssertEqual(card.rungs.map(\.chance), [0.76, 0.64, 0.53, 0.40, 0.295])
        XCTAssertEqual(card.caption, "Chance before kickoff to reach each line")
        // No mark served ⇒ no card, never the live price in its place.
        let unmarked = ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: [0.9, 0.8, 0.7, 0.6, 0.5])
        XCTAssertTrue(NFLMilestoneCard9483.cards(
            props: unmarked, eventStatus: "live", commenceTime: t(-60),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0)).isEmpty)
    }

    func testNoGradeOrActualBeforeTheFinal() throws {
        let marks = [0.76, 0.64, 0.53, 0.40, 0.295]
        let live = ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: marks, marks: marks, actual: 84)
        let during = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: live, eventStatus: "live", commenceTime: t(-60),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0)).first)
        XCTAssertNil(during.actual)
        XCTAssertTrue(during.rungs.allSatisfy { $0.hit == nil })
        let after = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: live, eventStatus: "completed", commenceTime: t(-240),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0)).first)
        XCTAssertEqual(after.actual, 84)
        XCTAssertEqual(after.rungs.map(\.hit), [true, true, true, true, true])
    }

    func testTeamSubjectsAndShortLaddersAreNotCards() {
        let dst = ladder("Bears D/ST", "Fantasy Points", lines: [5, 7, 9, 11], prices: [0.8, 0.6, 0.4, 0.2])
        let short = ladder("Caleb Williams", "Passing Touchdowns", lines: [1, 2], prices: [0.8, 0.4])
        XCTAssertTrue(NFLMilestoneCard9483.cards(
            props: dst + short, eventStatus: "scheduled", commenceTime: t(60),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0)).isEmpty)
    }

    func testAtMostTwoPlayerCardsOnePerPlayer() {
        let props = ladder("A Player", "Rushing Yards", lines: yards, prices: [0.8, 0.6, 0.5, 0.3, 0.2])
            + ladder("A Player", "Receiving Yards", lines: yards, prices: [0.8, 0.6, 0.5, 0.3, 0.2])
            + ladder("B Player", "Rushing Yards", lines: yards, prices: [0.8, 0.6, 0.5, 0.3, 0.2])
            + ladder("C Player", "Rushing Yards", lines: yards, prices: [0.8, 0.6, 0.5, 0.3, 0.2])
        let cards = NFLMilestoneCard9483.cards(
            props: props, eventStatus: "scheduled", commenceTime: t(60),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0))
        XCTAssertEqual(cards.count, 2)
        XCTAssertEqual(Set(cards.map(\.player)).count, 2)
    }

    func testTheDeckOrderIsStable() {
        let props = ladder("B Player", "Rushing Yards", lines: yards, prices: [0.8, 0.6, 0.5, 0.3, 0.2])
            + ladder("A Player", "Rushing Yards", lines: yards, prices: [0.8, 0.6, 0.5, 0.3, 0.2])
            + ladder("C Player", "Receiving Yards", lines: yards, prices: [0.8, 0.6, 0.5, 0.3, 0.2])
        let first = NFLMilestoneCard9483.cards(props: props, eventStatus: "scheduled", commenceTime: t(60),
                                                homeTeam: "H", awayTeam: "A", now: t(0)).map(\.id)
        for _ in 0..<20 {
            XCTAssertEqual(NFLMilestoneCard9483.cards(props: props.shuffled(), eventStatus: "scheduled",
                                                      commenceTime: t(60), homeTeam: "H", awayTeam: "A",
                                                      now: t(0)).map(\.id), first)
        }
        // The most-quoted stat leads, then the key.
        XCTAssertEqual(first, ["A Player|Rushing Yards", "B Player|Rushing Yards"])
    }

    func testTheDeckIsNFLOnly() {
        XCTAssertTrue(NFLEventCardDeck9483.cards(sportKey: "basketball_nba", finish: nil, milestones: []).isEmpty)
    }

    // MARK: - Quote freshness (design return, finding 1)

    private func swiftCard(_ props: [GameMarketPlayerProp], status: String = "scheduled",
                           now: Double = 0) -> NFLMilestoneCard9483? {
        NFLMilestoneCard9483.cards(props: props, eventStatus: status,
                                   commenceTime: status == "scheduled" ? t(60) : t(-60),
                                   homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(now)).first
    }

    func testFreshStaleAndMissingClocksAreThreeDifferentDisplays() throws {
        let prices = [0.76, 0.64, 0.53, 0.40, 0.295]
        let fresh = iso(t(-5)), stale = iso(t(-31))
        // Identical numbers; only the last line's clock differs.
        let current = try XCTUnwrap(swiftCard(ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: prices,
                                                     observed: [fresh, fresh, fresh, fresh, fresh])))
        let aged = try XCTUnwrap(swiftCard(ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: prices,
                                                  observed: [fresh, fresh, fresh, fresh, stale])))
        let undated = try XCTUnwrap(swiftCard(ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: prices,
                                                     observed: [fresh, fresh, fresh, fresh, nil])))
        XCTAssertEqual(current.rungs.map(\.chance), prices)
        XCTAssertEqual(aged.rungs.map(\.chance), [0.76, 0.64, 0.53, 0.40, nil], "a stale quote prints no number")
        XCTAssertEqual(undated.rungs.map(\.chance), [0.76, 0.64, 0.53, 0.40, nil], "an undated quote is not current")
        XCTAssertEqual(aged.rungs.count, 5, "the line stays on the card")
        XCTAssertEqual(aged.rungs.last?.observedAt, stale, "the observation clock is retained for Details")
        XCTAssertNotEqual(current, aged)
        XCTAssertNotEqual(aged, undated, "stale and undated keep their own clocks")
        XCTAssertEqual(aged.profile?.milestones.count, 4, "the dot is drawn only for current lines")
        // Every quote aged ⇒ no shape to draw ⇒ no card in the deck (the
        // ladder stays in the player props below).
        XCTAssertNil(swiftCard(ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: prices,
                                      observed: Array(repeating: stale, count: 5))))
        // The bound is the page's live bound, inclusive.
        XCTAssertTrue(NFLMilestoneCard9483.isRecent(iso(t(-30)), now: t(0)))
        XCTAssertFalse(NFLMilestoneCard9483.isRecent(iso(t(-30.1)), now: t(0)))
    }

    func testAHeldPregamePriceExpiresWhileTheReaderIsOpen() throws {
        let card = try XCTUnwrap(swiftCard(ladder("D'Andre Swift", "Rushing Yards", lines: yards,
                                                  prices: [0.76, 0.64, 0.53, 0.40, 0.295])))
        let held: [NFLEventCard9483] = [.milestone(card)]
        // Ten minutes later nothing was re-quoted: still current (observed t(-5)).
        XCTAssertEqual(NFLCardReaderHold9483.displayed(held: held, live: held, now: t(10)), held)
        // Past the bound the held card loses its numbers — the reader being
        // open does not keep a price current.
        guard case .milestone(let shown) = NFLCardReaderHold9483.displayed(held: held, live: held, now: t(26))[0]
        else { return XCTFail("milestone card expected") }
        XCTAssertTrue(shown.rungs.allSatisfy { $0.chance == nil })
        XCTAssertEqual(shown.rungs.map(\.rowID), card.rungs.map(\.rowID), "every line stays")
        // The mark basis is historical and never ages.
        let marked = try XCTUnwrap(swiftCard(ladder("D'Andre Swift", "Rushing Yards", lines: yards,
                                                    prices: [1, 1, 0.9, 0.2, 0.05],
                                                    marks: [0.76, 0.64, 0.53, 0.40, 0.295]), status: "live"))
        XCTAssertEqual(marked.current(at: t(600)), marked)
    }

    func testAMissingPregameMarkIsNeverTheLivePrice() throws {
        let card = try XCTUnwrap(swiftCard(ladder("D'Andre Swift", "Rushing Yards", lines: yards,
                                                  prices: [0.9, 0.8, 0.7, 0.6, 0.5],
                                                  marks: [0.76, 0.64, 0.53, 0.40, 0.295]).enumerated().map { i, p in
            i == 4 ? prop("D'Andre Swift", "Rushing Yards", yards[4], price: 0.5, mark: nil) : p
        }, status: "live"))
        XCTAssertEqual(card.rungs.map(\.chance), [0.76, 0.64, 0.53, 0.40, nil])
    }

    func testAnUnderLegIsNotARung() throws {
        var props = ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: [0.76, 0.64, 0.53, 0.40, 0.295])
        props.append(prop("D'Andre Swift", "Rushing Yards", 89.5, price: 0.8, inverted: true))
        let card = try XCTUnwrap(swiftCard(props))
        XCTAssertEqual(card.rungs.map(\.threshold), yards, "an inverted (Under) leg reads no over chance")
    }

    // MARK: - Held Details (finding 2)

    func testDetailsRowsAreHeldWithTheCardsUntilRefresh() throws {
        let opened = ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: [0.76, 0.64, 0.53, 0.40, 0.295],
                            marks: [0.76, 0.64, 0.53, 0.40, 0.295])
        let card = try XCTUnwrap(swiftCard(opened, status: "live"))
        let cards: [NFLEventCard9483] = [.milestone(card)]
        let heldRows = NFLCardReaderHold9483.rows(for: cards, in: opened)
        XCTAssertEqual(Set(heldRows.keys), Set(card.rungs.map(\.rowID)))
        let header = NFLReaderHeader9483(match: "PHI 7–20 CHI · Q3 5:47", chances: "")
        XCTAssertFalse(NFLCardReaderHold9483.hasUpdate(held: cards, heldHeader: header, live: cards,
                                                       liveHeader: header, heldRows: heldRows, liveRows: heldRows,
                                                       now: t(0)))
        // A new live quote changes no number on the card (it reads the mark)
        // but changes the Details row: that is an update, offered by Refresh,
        // never shown in Details first.
        var quoted = opened
        quoted[2] = prop("D'Andre Swift", "Rushing Yards", yards[2], price: 0.91, mark: 0.53, observed: iso(t(0)))
        let liveCards: [NFLEventCard9483] = [.milestone(try XCTUnwrap(swiftCard(quoted, status: "live")))]
        XCTAssertEqual(liveCards, cards, "the card itself did not move")
        let liveRows = NFLCardReaderHold9483.rows(for: liveCards, in: quoted)
        XCTAssertNotEqual(liveRows[card.rungs[2].rowID], heldRows[card.rungs[2].rowID])
        XCTAssertTrue(NFLCardReaderHold9483.hasUpdate(held: cards, heldHeader: header, live: liveCards,
                                                      liveHeader: header, heldRows: heldRows, liveRows: liveRows,
                                                      now: t(0)))
        XCTAssertEqual(heldRows[card.rungs[2].rowID]?.overProbability, 0.53, "Details still read the held row")
        // A row that vanishes from the live payload leaves the held original.
        let vanished = NFLCardReaderHold9483.rows(for: cards, in: Array(opened.dropLast()))
        XCTAssertNil(vanished[card.rungs[4].rowID])
        XCTAssertNotNil(heldRows[card.rungs[4].rowID])
    }

    // MARK: - Stat axis (finding 3)

    func testTheStatAxisAdmitsActualsBelowWithinAndAboveTheLadder() {
        let ladder = 0.0...5.0          // a 0.5+ … 4.5+ ladder padded to 0
        let below = NFLMilestoneCard9483.statDomain(ladder, actual: 0)
        XCTAssertLessThan(below.lowerBound, 0, "a final 0 sits inside the plot, not on its edge")
        XCTAssertEqual(below.upperBound, 5)
        XCTAssertEqual(NFLMilestoneCard9483.statDomain(ladder, actual: 3), ladder, "within: unchanged")
        let above = NFLMilestoneCard9483.statDomain(35...85, actual: 84)
        XCTAssertGreaterThan(above.upperBound, 84)
        XCTAssertEqual(above.lowerBound, 35)
        let farBelow = NFLMilestoneCard9483.statDomain(35...85, actual: 12)
        XCTAssertLessThan(farBelow.lowerBound, 12)
        XCTAssertEqual(NFLMilestoneCard9483.statDomain(ladder, actual: nil), ladder)
    }

    // MARK: - Selection (v110)

    private func swift(prices: [Double] = [0.76, 0.64, 0.53, 0.40, 0.295]) throws -> NFLMilestoneCard9483 {
        try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: prices),
            eventStatus: "scheduled", commenceTime: t(60), homeTeam: "Chicago Bears",
            awayTeam: "Philadelphia Eagles", now: t(0)).first)
    }

    func testTheSelectionIsTheOriginalRowAndSurvivesARefresh() throws {
        let state = NFLCardDeckState9483()
        let card = try swift()
        XCTAssertEqual(state.selectedIndex(in: card), 2, "opens on the line nearest even odds")
        state.move(in: card, by: 2)
        XCTAssertEqual(state.selectedIndex(in: card), 4)
        // New prices on the same rows keep the same line selected.
        XCTAssertEqual(state.selectedIndex(in: try swift(prices: [0.7, 0.6, 0.5, 0.45, 0.33])), 4)
        state.move(in: card, by: 1)
        XCTAssertEqual(state.selectedIndex(in: card), 4, "never past the last line")
    }

    func testAWithdrawnRowSelectsNothing() throws {
        let state = NFLCardDeckState9483()
        let card = try swift()
        state.move(in: card, by: 2)
        let withdrawn = NFLMilestoneCard9483(id: card.id, player: card.player, stat: card.stat, side: card.side,
                                             basis: card.basis, rungs: Array(card.rungs.dropLast()), actual: nil)
        XCTAssertNil(state.selectedIndex(in: withdrawn), "a vanished line selects nothing, never a neighbour")
    }

    func testBackReturnsToTheCardItOpenedFrom() {
        let state = NFLCardDeckState9483()
        state.open("milestone:x")
        state.openCardID = "finish"          // the reader swiped to a neighbour
        state.detailsRowID = "row"
        state.close()
        XCTAssertNil(state.openCardID)
        XCTAssertNil(state.detailsRowID)
        XCTAssertEqual(state.returnCardID, "milestone:x")
    }

    // MARK: - Held reading (v157/v158, v159)

    private func finish(now: NFLFinishCard9483.Pair?) -> NFLEventCard9483 {
        .finish(NFLFinishCard9483(phase: .during, pregame: .init(away: 18, home: 20.5, at: t(-30)),
                                  projectedNow: now, final: nil))
    }

    func testTheReaderHoldsWhatItOpenedOn() {
        let held = [finish(now: .init(away: 19, home: 23, at: t(30)))]
        let live = [finish(now: .init(away: 21, home: 22, at: t(45)))]
        XCTAssertEqual(NFLCardReaderHold9483.displayed(held: held, live: live), held)
        let header = NFLReaderHeader9483(match: "PHI 7–20 CHI · Live", chances: "")
        XCTAssertTrue(NFLCardReaderHold9483.hasUpdate(held: held, heldHeader: header, live: live, liveHeader: header))
        XCTAssertFalse(NFLCardReaderHold9483.hasUpdate(held: live, heldHeader: header, live: live, liveHeader: header))
        let scored = NFLReaderHeader9483(match: "PHI 14–20 CHI · Live", chances: "")
        XCTAssertTrue(NFLCardReaderHold9483.hasUpdate(held: live, heldHeader: header, live: live, liveHeader: scored))
    }

    func testAnExpiredProjectionLeavesTheHeldCard() {
        let held = [finish(now: .init(away: 19, home: 23, at: t(30)))]
        let shown = NFLCardReaderHold9483.displayed(held: held, live: [finish(now: nil)])
        guard case .finish(let card) = shown[0] else { return XCTFail("finish card expected") }
        XCTAssertNil(card.projectedNow)
        XCTAssertEqual(card.pregame.home, 20.5, "the held pregame stays")
    }

    // MARK: - The reader, rendered

    @MainActor
    func testTheReaderRendersTheMatchLineCountAndBack() throws {
        let marks = [0.76, 0.64, 0.53, 0.40, 0.295]
        let milestone = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: ladder("D'Andre Swift", "Rushing Yards", lines: yards, prices: marks, marks: marks, actual: 84),
            eventStatus: "completed", commenceTime: t(-240), homeTeam: "Chicago Bears",
            awayTeam: "Philadelphia Eagles", now: t(0)).first)
        let finishCard = NFLFinishCard9483(phase: .after, pregame: .init(away: 23, home: 19.5, at: t(-30)),
                                           projectedNow: nil, final: .init(away: 7, home: 27, at: t(200)))
        let cards: [NFLEventCard9483] = [.finish(finishCard), .milestone(milestone)]
        for (name, size, scrolled) in [("reader-large", DynamicTypeSize.large, false),
                                       ("reader-ax3", .accessibility3, false),
                                       ("reader-ax3-scrolled", .accessibility3, true)] {
            let state = NFLCardDeckState9483()
            state.open(cards[1].id)
            let reader = NFLCardReader9483(
                liveCards: cards,
                liveHeader: .init(match: "Eagles 7–27 Bears · Final", chances: ""),
                awayName: "Eagles", homeName: "Bears", awayColor: .teal, homeColor: .indigo,
                state: state, liveRows: [:])
            let text = try render(reader, size: size, name: name, scrolled: scrolled)
            XCTAssertTrue(text.contains("2 of 2"), "\(name): opened on the card it was asked for: \(text)")
            XCTAssertFalse(text.contains("beat the forecast"), "\(name): the rail is still on card 1: \(text)")
            // Design return finding 4: no repeated chrome.
            XCTAssertFalse(text.contains("Back to the game"), "\(name): Back is short on screen: \(text)")
            XCTAssertFalse(text.contains("Swipe to explore"), "\(name): no footer instruction: \(text)")
            XCTAssertFalse(text.contains("Bears won"), "\(name): the score already says who won: \(text)")
            XCTAssertFalse(text.contains("Final 84"), "\(name): no second, clipped final label: \(text)")
            if scrolled {
                // Scrolled to the card's end, the selected line, its percent and
                // its Details control are reachable at AX3.
                XCTAssertTrue(text.contains("53%"), "\(name): the selected line's chance: \(text)")
                XCTAssertTrue(text.contains("59.5+"), "\(name): the selected line: \(text)")
                XCTAssertTrue(text.contains("details"), "\(name): the Details control: \(text)")
            } else {
                XCTAssertTrue(text.contains("Back"), "\(name): \(text)")
                XCTAssertTrue(text.contains("Eagles 7–27 Bears") || text.contains("Eagles 7-27 Bears"),
                              "\(name): \(text)")
                // The RAIL is on that card too, not only the footer (the first
                // build drew card 1 under a "2 of 2" footer).
                XCTAssertTrue(text.contains("kickoff"), "\(name): the rail shows the opened card: \(text)")
            }
        }
    }

    /// A pregame specimen with one line no longer observed, at both sizes:
    /// the line stays, says "No recent price", and draws no dot.
    @MainActor
    func testTheReaderRendersALineWithNoRecentPrice() throws {
        let now = Date()
        let fresh = iso(now.addingTimeInterval(-300)), stale = iso(now.addingTimeInterval(-3600))
        let props = yards.indices.map { i in
            prop("D'Andre Swift", "Rushing Yards", yards[i], price: [0.76, 0.64, 0.53, 0.40, 0.295][i],
                 observed: i == 2 ? stale : fresh)
        }
        let milestone = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: props, eventStatus: "scheduled", commenceTime: now.addingTimeInterval(3600),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: now).first)
        XCTAssertNil(milestone.rungs[2].chance)
        let cards: [NFLEventCard9483] = [.milestone(milestone)]
        for (name, size, scrolled) in [("reader-pregame-large", DynamicTypeSize.large, false),
                                       ("reader-pregame-ax3", .accessibility3, false),
                                       ("reader-pregame-ax3-scrolled", .accessibility3, true)] {
            let state = NFLCardDeckState9483()
            state.open(cards[0].id)
            state.move(in: milestone, by: -1)   // from 40% (nearest even) to the unpriced 60+
            let reader = NFLCardReader9483(
                liveCards: cards,
                liveHeader: .init(match: "Eagles vs Bears · Pregame", chances: "Win chances · Eagles 41% · Bears 59%"),
                awayName: "Eagles", homeName: "Bears", awayColor: .teal, homeColor: .indigo,
                state: state, liveRows: NFLCardReaderHold9483.rows(for: cards, in: props))
            let text = try render(reader, size: size, name: name, scrolled: scrolled)
            XCTAssertTrue(text.contains("1 of 1"), "\(name): \(text)")
            if scrolled || size == .large {
                XCTAssertTrue(text.contains("No recent price"), "\(name): the stale selected line says so: \(text)")
            }
            if !scrolled {
                XCTAssertTrue(text.contains("Pregame chance"), "\(name): \(text)")
            }
        }
    }

    @MainActor
    private func render<V: View>(_ view: V, size: DynamicTypeSize, name: String, scrolled: Bool) throws -> String {
        let host = hostForMeasurement(view, at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: 402, height: 874)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        let until = Date().addingTimeInterval(0.6)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.01))
        } while Date() < until
        // A first draw settles the window's safe areas (the bottom inset
        // arrives with it); scrolling before that clamps against bounds the
        // drawn frame no longer has.
        _ = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        if scrolled { scrollEveryCardToItsEnd(host.view) }
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("nfl-cards-9483-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("NFL card reader rendered evidence: \(url.path)")
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    /// Scrolls every vertically scrolling card in the reader to its end, the
    /// way a reader would at accessibility sizes. Repeated until the layout
    /// settles, so the offset is the end of the scroll view's FINAL bounds.
    @MainActor
    private func scrollEveryCardToItsEnd(_ root: UIView) {
        for _ in 0..<4 {
            var stack = [root]
            while let view = stack.popLast() {
                if let scroll = view as? UIScrollView, scroll.contentSize.height > scroll.bounds.height + 1 {
                    scroll.setContentOffset(CGPoint(x: scroll.contentOffset.x,
                                                    y: scroll.contentSize.height - scroll.bounds.height
                                                        + scroll.adjustedContentInset.bottom), animated: false)
                }
                stack.append(contentsOf: view.subviews)
            }
            let until = Date().addingTimeInterval(0.2)
            repeat {
                root.setNeedsLayout(); root.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.01))
            } while Date() < until
        }
    }

}
