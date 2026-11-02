import CoreText
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
/// - read the selected line from the axis label, or from a missing, changed, clipped or neighbouring percent (#11667 reader53) → `testTheReaderRendersTheMatchLineCountAndBack`
///
/// Native runtime review of 0a69b708 (10/14), PR #11038:
/// - hang a stat label off its tick (iOS 27 `AxisValueLabel`, "40+" under the 50+ stem) → `testADenseLadderCentresEveryLabelOnItsOwnTick`, `testADenseLadderRendersEachLabelUnderItsOwnStem`
/// - print two labels over each other, or drop the selected line's → `testADenseLadderCentresEveryLabelOnItsOwnTick`
/// - leave Refresh on an id no card carries ("1 of 0") → `testRefreshMovesOffACardThatLeftTheDeck`
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
        // #9483 A3 — the history point is not proven pregame, and the old pair
        // is never read as current.
        XCTAssertEqual(card.headline(awayName: "Eagles", homeName: "Bears"), "Eagles led the earlier forecast")
        XCTAssertEqual(card.missingCurrentNote, "No recent projection update")
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
        other = .init(sportKey: "basketball_wnba", sourceKey: other.sourceKey, basis: other.basis, pairs: other.pairs,
                      actuals: [], kickoffAt: nil, scoreObservationStartAt: other.scoreObservationStartAt,
                      finalAt: nil, asOf: other.asOf, windowStartAt: nil, requestCutoffAt: nil)
        XCTAssertNil(NFLFinishCard9483.build(other), "NFL and NBA only")
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

    func testTheDeckIsNFLAndNBAOnly() {
        XCTAssertTrue(NFLEventCardDeck9483.cards(sportKey: "basketball_wnba", finish: nil, milestones: []).isEmpty)
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
            let image = try renderImage(reader, size: size, name: name, scrolled: scrolled)
            let text = try recognisedText(image)
            XCTAssertTrue(text.contains("2 of 2"), "\(name): opened on the card it was asked for: \(text)")
            XCTAssertFalse(text.contains("beat the forecast"), "\(name): the rail is still on card 1: \(text)")
            // Design return finding 4: no repeated chrome.
            XCTAssertFalse(text.contains("Back to the game"), "\(name): Back is short on screen: \(text)")
            XCTAssertFalse(text.contains("Swipe to explore"), "\(name): no footer instruction: \(text)")
            XCTAssertFalse(text.contains("Bears won"), "\(name): the score already says who won: \(text)")
            XCTAssertFalse(text.contains("Final 84"), "\(name): no second, clipped final label: \(text)")
            if scrolled {
                // Scrolled to the card's end, the selected line, its percent and
                // its Details control are reachable at AX3. The line and its
                // percent are read on the selected line itself (#11667 reader53):
                // the whole frame's "59.5+" can be the axis label alone.
                let row = try Self.selectedLineText9483(in: image)
                print("NFL reader53 selected line: [\(row.text)] words \(row.words) | whole: \(text)")
                XCTAssertTrue(row.text.contains("53%"), "\(name): the selected line's chance: \(row.text) | \(text)")
                XCTAssertTrue(row.text.contains("59.5+"), "\(name): the selected line: \(row.text) | \(text)")
                XCTAssertTrue(text.contains("59.5+"), "\(name): the selected line: \(text)")
                XCTAssertTrue(text.contains("details"), "\(name): the Details control: \(text)")
                try assertTheSelectedLineReaderRefusesWhatIsNotThere(image, words: row.words)
            } else {
                XCTAssertTrue(text.contains("Back"), "\(name): \(text)")
                XCTAssertTrue(text.contains("Eagles 7–27 Bears") || text.contains("Eagles 7-27 Bears"),
                              "\(name): \(text)")
                // The RAIL is on that card too, not only the footer (the first
                // build drew card 1 under a "2 of 2" footer).
                XCTAssertTrue(text.contains("kickoff"), "\(name): the rail shows the opened card: \(text)")
            }
        }
        // Control (#11667 reader53): the same reader on the NEIGHBOURING line.
        // Its readout is found, and it does not read as 59.5+ at 53%.
        let state = NFLCardDeckState9483()
        state.open(cards[1].id)
        state.move(in: milestone, by: -1)
        let other = try renderImage(NFLCardReader9483(
            liveCards: cards,
            liveHeader: .init(match: "Eagles 7–27 Bears · Final", chances: ""),
            awayName: "Eagles", homeName: "Bears", awayColor: .teal, homeColor: .indigo,
            state: state, liveRows: [:]), size: .accessibility3, name: "reader-ax3-scrolled-other-line", scrolled: true)
        let otherRow = try Self.selectedLineText9483(in: other)
        print("NFL reader53 control other-line: [\(otherRow.text)] words \(otherRow.words)")
        XCTAssertFalse(otherRow.words.isEmpty, "other line: its readout is found: \(otherRow.text)")
        XCTAssertFalse(otherRow.text.contains("59.5+") && otherRow.text.contains("53%"),
                       "other line: a different selected line is not read as 59.5+ at 53%: \(otherRow.text)")
    }

    /// A pregame specimen with one line no longer observed, at both sizes:
    /// the line stays, says "No recent probability update", and draws no dot.
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
                XCTAssertTrue(text.contains("No recent probability update"), "\(name): the stale selected line says so: \(text)")
            }
            if !scrolled {
                XCTAssertTrue(text.contains("Pregame chance"), "\(name): \(text)")
            }
        }
    }


    // MARK: - Stat-axis labels (native runtime review of 0a69b708)

    /// A 5-yard ladder of 14 lines, at the default and the largest label size,
    /// on a full-size and a compact plot: every drawn label is centred on its
    /// own tick (moved inward only at the plot's edges), no two touch, and the
    /// selected line's label is always one of them.
    func testADenseLadderCentresEveryLabelOnItsOwnTick() {
        let lines = stride(from: 39.5, through: 104.5, by: 5).map { $0 }
        XCTAssertGreaterThanOrEqual(lines.count, 10)
        let texts = lines.map(PlayerPropsFamily.targetLabel)
        for (plotWidth, fontSize) in [(CGFloat(330), CGFloat(12)), (330, 16), (260, 12), (260, 16)] {
            let ticks = lines.map { CGFloat(($0 - 37) / (107 - 37)) * plotWidth }
            let widths = texts.map { NFLStatAxisLabels9483.labelWidth($0, fontSize: fontSize) }
            for keep in [1, 6, lines.count - 2] {
                let shown = NFLStatAxisLabels9483.placements(tickPositions: ticks, widths: widths,
                                                             plotWidth: plotWidth, keep: keep)
                let tag = "plot \(plotWidth) font \(fontSize) keep \(keep)"
                XCTAssertTrue(shown.contains { $0.index == keep }, "\(tag): the selected line keeps its label")
                XCTAssertGreaterThan(shown.count, 2, "\(tag): a dense row still names several lines")
                for label in shown {
                    let half = widths[label.index] / 2
                    XCTAssertEqual(label.center, min(max(ticks[label.index], half), plotWidth - half),
                                   accuracy: 0.001, "\(tag): \(texts[label.index]) is centred on its own tick")
                    XCTAssertGreaterThanOrEqual(label.center - half, -0.001, "\(tag): inside the plot")
                    XCTAssertLessThanOrEqual(label.center + half, plotWidth + 0.001, "\(tag): inside the plot")
                }
                for (left, right) in zip(shown, shown.dropFirst()) {
                    XCTAssertGreaterThanOrEqual(
                        right.center - left.center,
                        (widths[left.index] + widths[right.index]) / 2 + OddsChartView.xAxisLabelMinGap - 0.001,
                        "\(tag): \(texts[left.index]) and \(texts[right.index]) do not touch")
                }
            }
        }
        // A sparse row draws every label.
        let sparse = NFLStatAxisLabels9483.placements(tickPositions: [20, 120, 220], widths: [24, 24, 24],
                                                      plotWidth: 240, keep: nil)
        XCTAssertEqual(sparse.map(\.index), [0, 1, 2])
        XCTAssertEqual(sparse.map(\.center), [20, 120, 220])
    }

    /// The same dense ladder RENDERED, default size and AX3: each interior
    /// label the page prints is found by its ink, must sit over a stem drawn
    /// in the card's colour, and must read as THAT stem's line (native saw
    /// "40+" under the 50+ stem on iOS 27).
    @MainActor
    func testADenseLadderRendersEachLabelUnderItsOwnStem() throws {
        let lines = stride(from: 39.5, through: 104.5, by: 5).map { $0 }
        let marks = lines.indices.map { 0.9 - Double($0) * 0.055 }   // 90% … 18.5%, all stems tall enough to see
        let card = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: ladder("Courtland Sutton", "Receiving Yards", lines: lines, prices: marks, marks: marks),
            eventStatus: "live", commenceTime: t(-60), homeTeam: "Denver Broncos",
            awayTeam: "Seattle Seahawks", now: t(0)).first)
        XCTAssertEqual(card.rungs.count, lines.count)
        for (name, size) in [("axis-large", DynamicTypeSize.large), ("axis-ax3", .accessibility3)] {
            let view = NFLMilestoneCardView9483(card: card, color: Color(red: 1, green: 0, blue: 0),
                                                state: NFLCardDeckState9483(), expanded: true)
                .padding(16)
                .frame(width: 402)
                .background(Color.white)
            let (labels, stems, scale, read) = try labelsAndStems(view, size: size, name: name)
            let tag = "\(name): labels \(labels.map { "\($0.text)@\(Int($0.x))" }) stems \(stems) read \(read)"
            XCTAssertEqual(stems.count, lines.count, "\(tag): one stem per line was found")
            // An END label may move inward off its tick to stay inside the
            // plot (at most half its width, < 25 pt); every other label may not.
            let ends = [stems.first ?? 0, stems.last ?? 0]
            let interior = labels.filter { label in ends.allSatisfy { abs($0 - label.x) / scale > 25 } }
            XCTAssertGreaterThanOrEqual(interior.count, 2, "\(tag): the row was read")
            for label in interior {
                let offsets = stems.map { abs($0 - label.x) }
                let nearest = offsets.min() ?? .infinity
                // 3 pt: the ink centre is measured to a pixel; a label hung
                // off its tick misses by half its own width (~15 pt), and a
                // neighbouring stem is ≥ 20 pt away.
                XCTAssertLessThanOrEqual(nearest / scale, 3, "\(tag): \(label.text) sits on a stem")
                if stems.count == lines.count, let stem = offsets.firstIndex(of: nearest) {
                    XCTAssertEqual(label.text, PlayerPropsFamily.targetLabel(lines[stem]),
                                   "\(tag): the label under the \(PlayerPropsFamily.targetLabel(lines[stem])) stem names it")
                }
            }
            // Stems and lines share one linear axis: left to right in line order.
            let readable = labels.sorted { $0.x < $1.x }.compactMap { Double($0.text.dropLast()) }
            XCTAssertEqual(readable.count, labels.count, "\(tag): every label read as a line")
            XCTAssertEqual(readable, readable.sorted(), "\(tag): left to right in line order")
        }
    }

    /// Renders `view`; returns the centres of the card-coloured stems and of
    /// every axis label's ink, in image pixels, with what each label reads.
    ///
    /// A first recognition pass only locates the label row. The stems are the
    /// red columns in a band inside the plot just above it. Each label is the
    /// run of dark (primary-ink) columns in the row — labels stand at least
    /// `xAxisLabelMinGap` apart, glyphs far less — so its centre is the ink's,
    /// not a recognition box's (those ran ~7 pt off on "74.5+"), and its text is
    /// read from a crop of that one label.
    @MainActor
    private func labelsAndStems<V: View>(_ view: V, size: DynamicTypeSize, name: String)
        throws -> (labels: [(text: String, x: CGFloat)], stems: [CGFloat], scale: CGFloat, read: [String]) {
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
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("nfl-cards-9483-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("NFL card axis rendered evidence: \(url.path)")
        let cg = try XCTUnwrap(image.cgImage)
        let (width, height) = (cg.width, cg.height)
        let scale = CGFloat(width) / host.view.bounds.width
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        let context = try XCTUnwrap(CGContext(
            data: &pixels, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))

        /// Recognised strings in `image`, with each one's vertical centre in pixels.
        func recognise(_ image: CGImage) throws -> [(text: String, mid: CGFloat)] {
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = false
            try VNImageRequestHandler(cgImage: image).perform([request])
            return (request.results ?? []).compactMap { observation in
                observation.topCandidates(1).first.map {
                    ($0.string, (1 - observation.boundingBox.midY) * CGFloat(image.height))
                }
            }
        }
        /// The runs of columns in `columns`, split where a gap exceeds `gap` pixels.
        func runs(_ columns: Set<Int>, gap: Int) -> [(first: Int, last: Int)] {
            var found: [(first: Int, last: Int)] = []
            for x in columns.sorted() {
                if let last = found.last, x - last.last <= gap { found[found.count - 1].last = x } else { found.append((x, x)) }
            }
            return found
        }
        func columns(rows: Range<Int>, where test: (Int, Int, Int) -> Bool) -> Set<Int> {
            var hit = Set<Int>()
            for y in max(rows.lowerBound, 0)..<min(max(rows.upperBound, 0), height) {
                for x in 0..<width {
                    let i = (y * width + x) * 4
                    if test(Int(pixels[i]), Int(pixels[i + 1]), Int(pixels[i + 2])) { hit.insert(x) }
                }
            }
            return hit
        }

        // Pass 1: the axis row is the HIGHEST line of "N+" text (the readout's
        // "74.5+" sits below the chart).
        let whole = try recognise(cg)
        let read = whole.map(\.text)
        guard let rowMid = whole.filter({ $0.text.contains(/\d\+/) }).map(\.mid).min() else {
            return ([], [], scale, read)
        }

        // Stems: card-red columns in a band inside the plot above that row. A
        // label's centre sits 12.7–17 pt below the plot's bottom edge.
        let stems = runs(columns(rows: Int(rowMid - 32 * scale)..<Int(rowMid - 19 * scale)) { r, g, b in
            r > 180 && r - g > 40 && r - b > 40
        }, gap: 1).map { CGFloat($0.first + $0.last) / 2 }

        // Labels: dark ink in the row. The grey tick marks and the grey
        // y-axis "0%" stay out of it.
        let rowRange = Int(rowMid - 7 * scale)..<Int(rowMid + 7 * scale)
        let ink = runs(columns(rows: rowRange) { r, g, b in max(r, g, b) < 110 },
                       gap: Int(3 * scale))
        let labels = try ink.map { run -> (text: String, x: CGFloat) in
            // Crop to this label's own ink, so the readout below never joins it.
            let inkRows = rowRange.filter { y in
                (run.first...run.last).contains { x in
                    let i = (y * width + x) * 4
                    return max(pixels[i], pixels[i + 1], pixels[i + 2]) < 110
                }
            }
            let pad = 3 * scale
            let top = CGFloat(inkRows.first ?? Int(rowMid)), bottom = CGFloat(inkRows.last ?? Int(rowMid))
            let crop = CGRect(x: CGFloat(run.first) - pad, y: top - pad,
                              width: CGFloat(run.last - run.first) + 2 * pad, height: bottom - top + 2 * pad).integral
            let found = try recognise(try XCTUnwrap(cg.cropping(to: crop)))
            let text = found.min { abs($0.mid - crop.height / 2) < abs($1.mid - crop.height / 2) }?.text ?? ""
            return (text.replacingOccurrences(of: " ", with: ""), CGFloat(run.first + run.last) / 2)
        }
        return (labels, stems, scale, read)
    }

    // MARK: - Refresh reconciliation (design supplement 10/14)

    func testRefreshMovesOffACardThatLeftTheDeck() {
        let old = ["finish", "milestone:a", "milestone:b"]
        XCTAssertEqual(NFLCardReaderHold9483.reconciled(visible: "milestone:a", old: old, new: old), "milestone:a",
                       "a card that stayed stays open")
        XCTAssertEqual(NFLCardReaderHold9483.reconciled(visible: "milestone:a", old: old,
                                                        new: ["finish", "milestone:b"]), "milestone:b",
                       "the open card left: the next card that stayed")
        XCTAssertEqual(NFLCardReaderHold9483.reconciled(visible: "milestone:b", old: old,
                                                        new: ["finish", "milestone:a"]), "milestone:a",
                       "the last card left: the previous card that stayed")
        XCTAssertEqual(NFLCardReaderHold9483.reconciled(visible: "milestone:b", old: old,
                                                        new: ["milestone:c"]), "milestone:c",
                       "nothing old stayed: the first new card")
        XCTAssertNil(NFLCardReaderHold9483.reconciled(visible: "milestone:b", old: old, new: []),
                     "no card left: nothing is named")
    }

    @MainActor
    private func render<V: View>(_ view: V, size: DynamicTypeSize, name: String, scrolled: Bool) throws -> String {
        try recognisedText(renderImage(view, size: size, name: name, scrolled: scrolled))
    }

    private func recognisedText(_ image: CGImage) throws -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: image).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    @MainActor
    private func renderImage<V: View>(_ view: V, size: DynamicTypeSize, name: String, scrolled: Bool) throws -> CGImage {
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
        return try XCTUnwrap(image.cgImage)
    }

    // MARK: - The selected line, read on its own (#11667 reader53)

    /// iOS 26.5 read the whole AX3 frame's "59.5+ · 53%" as "595+5%,", and
    /// the old "59.5+" check passed on the axis label. The selected line is
    /// read here from its own ink instead: the card-accent rows directly above
    /// its "details" line, split into words at gaps wider than a third of the
    /// line's height, each word recognised alone from accent ink only.

    /// The card's accent ink (indigo, (95, 85, 237) on the frame), not the
    /// system-blue chevrons ((59, 134, 247)), grey or black text.
    nonisolated static func isAccent9483(_ r: Int, _ g: Int, _ b: Int) -> Bool {
        b > 150 && b - g > 60 && g - r < 30
    }

    /// The selected line's word boxes, left to right, in pixels from the top
    /// left. Scanning up from `detailsTop`, the line is the first run of rows
    /// holding accent ink, ended by the first row without it, and no more than
    /// two and a half `lineHeight`s up (the plot's accent stems sit further
    /// up). No accent rows in reach: no words.
    nonisolated static func selectedLineWords9483(rgba pixels: [UInt8], width: Int, height: Int,
                                                  detailsTop: Int, lineHeight: Int) -> [CGRect] {
        func accentColumns(_ y: Int) -> [Int] {
            (0..<width).filter { x in
                let i = (y * width + x) * 4
                return isAccent9483(Int(pixels[i]), Int(pixels[i + 1]), Int(pixels[i + 2]))
            }
        }
        var rows: [Int] = []
        var columns = Set<Int>()
        let start = min(detailsTop, height) - 1, end = max(detailsTop - 5 * lineHeight / 2, 0)
        if start >= end {
            for y in stride(from: start, through: end, by: -1) {
                let found = accentColumns(y)
                if found.isEmpty {
                    if !rows.isEmpty { break }
                } else {
                    rows.append(y)
                    columns.formUnion(found)
                }
            }
        }
        guard let top = rows.last, let bottom = rows.first else { return [] }
        let gap = max((bottom - top + 1) / 3, 1)
        var words: [(first: Int, last: Int)] = []
        for x in columns.sorted() {
            if let last = words.last, x - last.last <= gap { words[words.count - 1].last = x } else { words.append((x, x)) }
        }
        return words.map { CGRect(x: $0.first, y: top, width: $0.last - $0.first + 1, height: bottom - top + 1) }
    }

    /// RGBA bytes of `image`, rows from the top.
    nonisolated static func rgba9483(_ image: CGImage) -> [UInt8]? {
        var pixels = [UInt8](repeating: 0, count: image.width * image.height * 4)
        guard let context = CGContext(
            data: &pixels, width: image.width, height: image.height, bitsPerComponent: 8, bytesPerRow: image.width * 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        return pixels
    }

    /// `word` with a quarter-line margin, every pixel that is not accent ink
    /// whitened.
    nonisolated static func accentInk9483(rgba pixels: [UInt8], width: Int, height: Int, around word: CGRect) -> CGImage? {
        let pad = Int(word.height) / 4 + 1
        let crop = word.insetBy(dx: CGFloat(-pad), dy: CGFloat(-pad))
            .intersection(CGRect(x: 0, y: 0, width: width, height: height))
        let (x0, y0, w, h) = (Int(crop.minX), Int(crop.minY), Int(crop.width), Int(crop.height))
        guard w > 0, h > 0 else { return nil }
        var ink = [UInt8](repeating: 255, count: w * h * 4)
        for y in 0..<h {
            for x in 0..<w {
                let i = ((y0 + y) * width + x0 + x) * 4, o = (y * w + x) * 4
                if isAccent9483(Int(pixels[i]), Int(pixels[i + 1]), Int(pixels[i + 2])) {
                    for c in 0..<4 { ink[o + c] = pixels[i + c] }
                }
            }
        }
        return CGContext(
            data: &ink, width: w, height: h, bitsPerComponent: 8, bytesPerRow: w * 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)?.makeImage()
    }

    /// The selected line's text, its words joined left to right, and the word
    /// boxes it was read from. Each word is read from `accentInk9483` alone,
    /// so a neighbouring control or line inside the crop never reads as the
    /// line.
    /// No "details" line, or no accent line above it: "" and no words.
    nonisolated static func selectedLineText9483(in image: CGImage) throws -> (text: String, words: [CGRect]) {
        func recognise(_ image: CGImage, correcting: Bool) throws -> [VNRecognizedTextObservation] {
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.usesLanguageCorrection = correcting
            try VNImageRequestHandler(cgImage: image).perform([request])
            return request.results ?? []
        }
        let (width, height) = (image.width, image.height)
        guard let details = try recognise(image, correcting: true)
                .first(where: { $0.topCandidates(1).first?.string.contains("details") == true }),
              let pixels = rgba9483(image) else { return ("", []) }
        let words = selectedLineWords9483(
            rgba: pixels, width: width, height: height,
            detailsTop: Int((1 - details.boundingBox.maxY) * CGFloat(height)),
            lineHeight: max(Int(details.boundingBox.height * CGFloat(height)), 1))
        let read = try words.map { word -> String in
            guard let masked = accentInk9483(rgba: pixels, width: width, height: height, around: word) else { return "" }
            return try recognise(masked, correcting: false)
                .sorted { $0.boundingBox.minX < $1.boundingBox.minX }
                .compactMap { $0.topCandidates(1).first?.string }
                .joined(separator: " ")
        }
        return (read.filter { !$0.isEmpty }.joined(separator: " "), words)
    }

    /// `image` with `edit` applied in pixel coordinates from the top left.
    nonisolated static func edited9483(_ image: CGImage, _ edit: (CGContext) -> Void) -> CGImage? {
        let (width, height) = (image.width, image.height)
        guard let context = CGContext(
            data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: width * 4,
            space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        context.translateBy(x: 0, y: CGFloat(height))
        context.scaleBy(x: 1, y: -1)
        edit(context)
        return context.makeImage()
    }

    /// Draws `text` with its baseline on the bottom of `box`, digits about
    /// `box.height` tall, in a top-left-origin context.
    nonisolated static func draw9483(_ text: String, in box: CGRect, red: CGFloat, green: CGFloat, blue: CGFloat,
                                     _ context: CGContext) {
        let font = CTFontCreateWithName("Helvetica-Bold" as CFString, box.height / 0.72, nil)
        let color = CGColor(srgbRed: red / 255, green: green / 255, blue: blue / 255, alpha: 1)
        let line = CTLineCreateWithAttributedString(NSAttributedString(string: text, attributes: [
            NSAttributedString.Key(kCTFontAttributeName as String): font,
            NSAttributedString.Key(kCTForegroundColorAttributeName as String): color]))
        context.saveGState()
        context.translateBy(x: box.minX, y: box.maxY)
        context.scaleBy(x: 1, y: -1)
        context.textPosition = .zero
        CTLineDraw(line, context)
        context.restoreGState()
    }

    /// The selected-line reader refuses each frame that does not show
    /// "59.5+ · 53%" on the selected line, built from the real frame: the
    /// percent missing, changed, clipped at the bottom or the right, the
    /// whole line gone (only the axis "59.5+" left), and a "53%" from a
    /// neighbouring control (system blue) or line (grey) where the percent
    /// was. Wherever accent ink remains, the line must still be found, so no
    /// refusal is vacuous.
    @MainActor
    private func assertTheSelectedLineReaderRefusesWhatIsNotThere(_ image: CGImage, words: [CGRect]) throws {
        let first = try XCTUnwrap(words.first, "the selected line was found")
        let line = words.dropFirst().reduce(first) { $0.union($1) }
        let percent = try XCTUnwrap(words.last, "the selected line has a percent word")
        XCTAssertGreaterThanOrEqual(words.count, 2, "line and percent are separate words: \(words)")
        let pad = percent.height / 4
        let blank = percent.insetBy(dx: -pad, dy: -pad)
        let white = CGColor(srgbRed: 1, green: 1, blue: 1, alpha: 1)
        let negatives: [(name: String, keepsInk: Bool, edit: (CGContext) -> Void)] = [
            ("missing", true, { $0.setFillColor(white); $0.fill(blank) }),
            ("changed", true, { c in
                c.setFillColor(white); c.fill(blank)
                Self.draw9483("58%", in: percent, red: 95, green: 85, blue: 237, c)
            }),
            ("clipped-bottom", true, { c in
                c.setFillColor(white)
                c.fill(CGRect(x: line.minX - pad, y: line.minY + line.height * 0.55,
                              width: line.width + 2 * pad, height: line.height * 0.45 + pad))
            }),
            ("clipped-right", true, { c in
                c.setFillColor(white)
                c.fill(CGRect(x: percent.maxX - percent.width * 0.4, y: line.minY - pad,
                              width: percent.width * 0.4 + pad, height: line.height + 2 * pad))
            }),
            ("axis-only", false, { c in c.setFillColor(white); c.fill(line.insetBy(dx: -pad, dy: -pad)) }),
            ("neighbour-control", true, { c in
                c.setFillColor(white); c.fill(blank)
                Self.draw9483("53%", in: percent, red: 59, green: 134, blue: 247, c)
            }),
            ("neighbour-line", true, { c in
                c.setFillColor(white); c.fill(blank)
                Self.draw9483("53%", in: percent, red: 128, green: 128, blue: 133, c)
            }),
        ]
        for negative in negatives {
            let frame = try XCTUnwrap(Self.edited9483(image, negative.edit), negative.name)
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("nfl-cards-9483-reader53-control-\(negative.name).png")
            try XCTUnwrap(UIImage(cgImage: frame).pngData()).write(to: url)
            let read = try Self.selectedLineText9483(in: frame)
            print("NFL reader53 control \(negative.name): [\(read.text)] words \(read.words) evidence \(url.path)")
            XCTAssertFalse(read.text.contains("59.5+") && read.text.contains("53%"),
                           "\(negative.name): refused as the selected line 59.5+ at 53%: \(read.text)")
            if negative.keepsInk {
                XCTAssertFalse(read.words.isEmpty, "\(negative.name): the remaining line is still found")
            } else {
                XCTAssertTrue(read.words.isEmpty, "\(negative.name): no line is invented: \(read.words)")
            }
        }
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
