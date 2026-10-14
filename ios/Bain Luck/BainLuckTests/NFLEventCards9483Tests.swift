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

    private func prop(_ subject: String, _ market: String, _ line: Double, price: Double?, mark: Double? = nil,
                      team: String? = "home", actual: Double? = nil, hit: Bool? = nil) -> GameMarketPlayerProp {
        GameMarketPlayerProp(marketName: market, outcomeName: "\(subject): \(PlayerPropsFamily.targetLabel(line)) \(market)",
                             threshold: line, overProbability: price, source: "kalshi", movement: nil,
                             playerHeadshot: nil, playerTeam: team, actual: actual, hit: hit, pregameMark: mark)
    }

    private func ladder(_ subject: String, _ market: String, lines: [Double], prices: [Double], marks: [Double]? = nil,
                        actual: Double? = nil) -> [GameMarketPlayerProp] {
        lines.indices.map { i in
            prop(subject, market, lines[i], price: prices[i], mark: marks?[i], actual: actual,
                 hit: actual.map { $0 >= lines[i] })
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
        XCTAssertEqual(card.caption, "Chance to reach each line")
    }

    func testOncePlayStartsTheCardReadsThePregameMarkNeverTheLivePrice() throws {
        let props = ladder("D'Andre Swift", "Rushing Yards", lines: yards,
                           prices: [1, 1, 0.9, 0.2, 0.05], marks: [0.76, 0.64, 0.53, 0.40, 0.295])
        let card = try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: props, eventStatus: "live", commenceTime: t(-60),
            homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles", now: t(0)).first)
        XCTAssertEqual(card.basis, .pregameMark)
        XCTAssertEqual(card.rungs.map(\.chance), [0.76, 0.64, 0.53, 0.40, 0.295])
        // No mark served ⇒ no rung, never the live price in its place.
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
        for (name, size) in [("reader-large", DynamicTypeSize.large), ("reader-ax3", .accessibility3)] {
            let state = NFLCardDeckState9483()
            state.open(cards[1].id)
            let reader = NFLCardReader9483(
                liveCards: cards,
                liveHeader: .init(match: "Eagles 7–27 Bears · Final", chances: "Bears won"),
                awayName: "Eagles", homeName: "Bears", awayColor: .teal, homeColor: .indigo,
                state: state, row: { _ in nil })
            let host = hostForMeasurement(reader, at: size)
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
            print("NFL card reader rendered evidence: \(url.path)")
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
            let text = (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
            XCTAssertTrue(text.contains("Back to the game"), "\(name): \(text)")
            XCTAssertTrue(text.contains("Eagles 7–27 Bears") || text.contains("Eagles 7-27 Bears"), "\(name): \(text)")
            XCTAssertTrue(text.contains("2 of 2"), "\(name): opened on the card it was asked for: \(text)")
            // The RAIL is on that card too, not only the footer (the first build
            // drew card 1 under a "2 of 2" footer).
            XCTAssertTrue(text.contains("Pre-game chance"), "\(name): the rail shows the opened card: \(text)")
            XCTAssertFalse(text.contains("beat the forecast"), "\(name): the rail is still on card 1: \(text)")
        }
    }
}
