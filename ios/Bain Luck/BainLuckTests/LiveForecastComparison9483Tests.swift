import SwiftUI
import XCTest
@testable import Bain_Luck

/// #9483 — the earlier-versus-current projected finish before and during a
/// game (`LiveForecastComparison9483`). Prepared tests: NOT_RUN at source
/// handback.
///
/// Inputs, by provenance:
/// - The Eagles @ Bears halftime card is the existing deck tests' value
///   (`NFLEventCards9483Tests.testAProjectionWhoseLeaderChangedSaysFlipped`):
///   a history point 23 / 19.5 before the floor, 18 / 25.5 after it, built
///   here through the real `NFLFinishCard9483.build`. It is a test control
///   in the production model, not captured wire data. Its earlier pair is a
///   history point, never a scheduled-start or kickoff forecast.
/// - The Jaguars @ Eagles pair 25 / 17 → 19.8 / 20.8 is COPIED from the
///   browser reference (`forecast-shift-visual-20261026/browser.patch`, test
///   "retained Jaguars and Eagles forecasts use one unnormalised points
///   scale", reading the prototype's `src/atlas.json`; one sportsbook's
///   pair). It is a CONTROL in the production model, not an app blend and
///   not a wire capture.
/// - Every other value below is a CONTROL, named as one.
///
/// What these pin, and the mutation each kills:
/// - draw a finished card, or let a final reach the chart → `testOnlyBeforeAndDuringAreDrawnAndNoFinalLeaks`
/// - swap the teams, or lose the earlier basis → `testTheDeckCardKeepsItsOrderValuesAndHistoryBasis`
/// - relabel a scheduled-start pair, or round its halves while live → `testAScheduledStartPairKeepsItsNameAndHalves`
/// - invent a current column before play → `testBeforePlayTheOnePairIsShownOnce`
/// - keep or substitute a current projection after expiry → `testAnExpiredCurrentProjectionLeavesNoMarkLineOrChange`
/// - say "unchanged" for a real sub-decimal move, or lose a true zero → `testChangeWordsComeFromTheExactDifference`
/// - squash NBA's 100-plus scores, or give the teams different axes → `testBothTeamsShareOneDomainInFootballAndBasketball`
/// - invent a clock or a source → `testNoClockOrSourceIsAddedToWhatTheCardHolds`
/// - speak a number the card does not print, or a cut name → `testVoiceOverSaysWholeNamesBasesAndTheComparisonInOrder`
/// - stop stacking at large text, or grow a blank track → `testAccessibilityLayoutDecisions`
@MainActor
final class LiveForecastComparison9483Tests: XCTestCase {
    private typealias Comparison = LiveForecastComparison9483

    private let base = Date(timeIntervalSince1970: 1_791_000_000)
    private func t(_ minutes: Double) -> Date { base.addingTimeInterval(minutes * 60) }

    private func pair(_ minutes: Double, home: Double, away: Double) -> ProjectedFinalPointsSeries.Pair {
        .init(at: t(minutes), home: home, away: away, homeProbability: nil, kind: .recorded)
    }

    private func input(_ pairs: [ProjectedFinalPointsSeries.Pair], floor: Double?,
                       now: Double, sportKey: String = "americanfootball_nfl") -> ProjectedFinalPointsSeries.Input {
        .init(sportKey: sportKey, sourceKey: "draftkings",
              basis: .sameBookSameCaptureFullGameSpreadAndTotal, pairs: pairs, actuals: [],
              kickoffAt: nil, scoreObservationStartAt: floor.map(t), finalAt: nil,
              asOf: t(now), windowStartAt: nil, requestCutoffAt: nil)
    }

    /// The deck tests' Eagles @ Bears card at halftime, through `build`.
    private func eaglesBears() throws -> NFLFinishCard9483 {
        try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 19.5, away: 23), pair(30, home: 25.5, away: 18)], floor: 0, now: 40)))
    }

    /// CONTROL: the browser reference's Jaguars @ Eagles pair, live, on the
    /// history basis.
    private var jaguarsEagles: NFLFinishCard9483 {
        NFLFinishCard9483(phase: .during, pregame: .init(away: 25, home: 17, at: t(-30)),
                          projectedNow: .init(away: 19.8, home: 20.8, at: t(30)), final: nil)
    }

    // MARK: - Phase and leakage

    func testOnlyBeforeAndDuringAreDrawnAndNoFinalLeaks() throws {
        let before = NFLFinishCard9483(phase: .before, pregame: .init(away: 18, home: 20.5, at: t(-30)),
                                       projectedNow: nil, final: nil)
        XCTAssertTrue(Comparison.applies(before))
        XCTAssertTrue(Comparison.applies(try eaglesBears()))
        XCTAssertTrue(Comparison.applies(try eaglesBears().withoutProjectedNow))
        let after = NFLFinishCard9483(phase: .after, pregame: .init(away: 23, home: 19.5, at: t(-30)),
                                      projectedNow: nil, final: .init(away: 7, home: 27, at: t(200)))
        XCTAssertFalse(Comparison.applies(after), "a finished card belongs to the final renderer")
        XCTAssertTrue(Comparison.sides(after, awayName: "Eagles", homeName: "Bears").isEmpty)
        // CONTROL: `build` never puts a final on a live card; the value type
        // allows it, and nothing of it may reach this chart.
        let carried = NFLFinishCard9483(phase: .during, pregame: .init(away: 23, home: 19.5, at: t(-30)),
                                        projectedNow: .init(away: 18, home: 25.5, at: t(30)),
                                        final: .init(away: 70, home: 3, at: t(40)))
        let sides = Comparison.sides(carried, awayName: "Eagles", homeName: "Bears")
        XCTAssertEqual(sides, Comparison.sides(try eaglesBears(), awayName: "Eagles", homeName: "Bears"))
        XCTAssertEqual(Comparison.domain(carried), Comparison.domain(try eaglesBears()),
                       "a final never widens the axis")
        for side in sides {
            XCTAssertFalse(Comparison.spoken(carried, side).contains("70"))
            XCTAssertFalse(Comparison.spoken(carried, side).contains("Final "), "no final is said")
        }
        // CONTROL: a value no axis can hold draws nothing, never a zero mark.
        let invalid = NFLFinishCard9483(phase: .during, pregame: .init(away: .nan, home: 20, at: t(-30)),
                                        projectedNow: nil, final: nil)
        XCTAssertFalse(Comparison.applies(invalid))
        let invalidNow = NFLFinishCard9483(phase: .during, pregame: .init(away: 18, home: 20, at: t(-30)),
                                           projectedNow: .init(away: 21, home: .infinity, at: t(30)), final: nil)
        XCTAssertFalse(Comparison.applies(invalidNow))
        XCTAssertTrue(Comparison.sides(invalidNow, awayName: "A", homeName: "B").isEmpty)
    }

    // MARK: - Values, order and basis

    func testTheDeckCardKeepsItsOrderValuesAndHistoryBasis() throws {
        let card = try eaglesBears()
        XCTAssertEqual(card.phase, .during)
        XCTAssertEqual(card.pregameBasis, .history)
        let sides = Comparison.sides(card, awayName: "Philadelphia Eagles", homeName: "Chicago Bears")
        XCTAssertEqual(sides.map(\.name), ["Philadelphia Eagles", "Chicago Bears"], "away first")
        XCTAssertEqual(sides.map(\.isHome), [false, true])
        XCTAssertEqual(sides.map(\.earlier), [23, 19.5], "the card's values, unrounded")
        XCTAssertEqual(sides.map(\.current), [18, 25.5])
        XCTAssertEqual(sides.map { Comparison.earlierText(card, $0) }, ["23", "19.5"])
        XCTAssertEqual(sides.map(Comparison.currentText), ["18", "25.5"])
        XCTAssertEqual(sides.map(Comparison.changeText), ["5.0 points lower", "6.0 points higher"])
        XCTAssertEqual(card.pregameName, NFLFinishCard9483.earlierForecast,
                       "the history point is not proven kickoff; it is never called pregame while live")
        XCTAssertEqual(card.headline(awayName: "Philadelphia Eagles", homeName: "Chicago Bears"),
                       "The projected finish has flipped", "the card's own headline, unchanged")
        XCTAssertEqual(Comparison.currentLabel, "Projected now")

        let jaguars = Comparison.sides(jaguarsEagles, awayName: "Jacksonville Jaguars", homeName: "Philadelphia Eagles")
        XCTAssertEqual(jaguars.map { Comparison.earlierText(jaguarsEagles, $0) }, ["25", "17"])
        XCTAssertEqual(jaguars.map(Comparison.currentText), ["19.8", "20.8"])
        XCTAssertEqual(jaguars.map(Comparison.changeText), ["5.2 points lower", "3.8 points higher"],
                       "the reference's own words for its pair")
    }

    func testAScheduledStartPairKeepsItsNameAndHalves() {
        // CONTROL: a live card on the headline's qualified pair
        // (`liveBaseline`), which claims no single clock.
        let card = NFLFinishCard9483(phase: .during, pregame: .init(away: 22.2, home: 29.4, at: nil),
                                     projectedNow: .init(away: 17.5, home: 31, at: t(30)), final: nil,
                                     pregameBasis: .scheduledStart)
        let sides = Comparison.sides(card, awayName: "Washington Commanders", homeName: "San Francisco 49ers")
        XCTAssertEqual(card.pregameName, FinalForecastComparison11296.label)
        XCTAssertFalse(card.printsPregameWhole, "only a finished card prints the qualified pair whole")
        XCTAssertEqual(sides.map { Comparison.earlierText(card, $0) }, ["22.2", "29.4"])
        XCTAssertEqual(sides.map(Comparison.changeText), ["4.7 points lower", "1.6 points higher"])
        for side in sides {
            let spoken = Comparison.spoken(card, side)
            XCTAssertTrue(spoken.contains(FinalForecastComparison11296.label))
            XCTAssertFalse(spoken.lowercased().contains("pregame"), "never an unqualified pregame")
            XCTAssertFalse(spoken.lowercased().contains("kickoff"), "never a proven kickoff")
        }
    }

    func testBeforePlayTheOnePairIsShownOnce() {
        let card = NFLFinishCard9483(phase: .before, pregame: .init(away: 18, home: 20.5, at: t(-30)),
                                     projectedNow: nil, final: nil)
        let sides = Comparison.sides(card, awayName: "Philadelphia Eagles", homeName: "Chicago Bears")
        XCTAssertEqual(sides.map(\.earlier), [18, 20.5])
        XCTAssertEqual(sides.map(\.current), [nil, nil], "no current column before play")
        XCTAssertEqual(sides.map(Comparison.changeText), [nil, nil], "no change before play")
        XCTAssertNil(card.missingCurrentNote, "nothing is missing before play")
        XCTAssertEqual(card.pregameName, "Pregame projection")
        XCTAssertEqual(Comparison.spoken(card, sides[1]), "Chicago Bears. Pregame projection 20.5 points.")
        // CONTROL: `build` never puts a current projection on a pregame card;
        // if one were carried it is still not drawn.
        let carried = NFLFinishCard9483(phase: .before, pregame: card.pregame,
                                        projectedNow: .init(away: 30, home: 3, at: t(-5)), final: nil)
        XCTAssertEqual(Comparison.sides(carried, awayName: "Philadelphia Eagles", homeName: "Chicago Bears"), sides)
        XCTAssertEqual(Comparison.domain(carried), Comparison.domain(card))
    }

    func testAnExpiredCurrentProjectionLeavesNoMarkLineOrChange() throws {
        let live = try eaglesBears()
        let expired = live.withoutProjectedNow
        let sides = Comparison.sides(expired, awayName: "Philadelphia Eagles", homeName: "Chicago Bears")
        XCTAssertEqual(sides.map(\.earlier), [23, 19.5], "the earlier values stay visible")
        XCTAssertEqual(sides.map(\.current), [nil, nil], "never the earlier value or a final in its place")
        XCTAssertEqual(sides.map(Comparison.currentText), [nil, nil])
        XCTAssertEqual(sides.map(Comparison.changeText), [nil, nil], "no numeric change without a current value")
        XCTAssertEqual(expired.missingCurrentNote, NFLFinishCard9483.noRecentProjectionUpdate)
        XCTAssertEqual(Comparison.spoken(expired, sides[0]),
                       "Philadelphia Eagles. Earlier forecast 23 points. Projected now: No recent projection update.")
        XCTAssertEqual(Comparison.domain(expired), NFLFinishCardView9483.pointDomain([23, 19.5], step: 7),
                       "the withdrawn values no longer shape the axis")
        // The same card built past the capture gap reads the same way.
        let stale = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 19.5, away: 23), pair(30, home: 25.5, away: 18)], floor: 0, now: 30 + 61)))
        XCTAssertEqual(Comparison.sides(stale, awayName: "Philadelphia Eagles", homeName: "Chicago Bears"), sides)
    }

    // MARK: - Change words

    func testChangeWordsComeFromTheExactDifference() {
        XCTAssertEqual(Comparison.changeText(from: 20.5, to: 20.5), "Unchanged", "coincident")
        XCTAssertEqual(Comparison.changeText(from: 0, to: 0), "Unchanged", "a true zero is a value")
        XCTAssertEqual(Comparison.changeText(from: 0, to: 3), "3.0 points higher", "up from a true zero")
        XCTAssertEqual(Comparison.changeText(from: 10, to: 0), "10.0 points lower", "down to a true zero")
        XCTAssertEqual(Comparison.changeText(from: 20.5, to: 20.54), "Less than 0.1 points higher")
        XCTAssertEqual(Comparison.changeText(from: 20.5, to: 20.46), "Less than 0.1 points lower")
        // The magnitude is `deltaPointsNumber`'s, unsigned, no percent sign.
        let words = Comparison.changeText(from: 24, to: 26.3)
        XCTAssertEqual(words, "\(deltaPointsNumber(2.3)) points higher")
        XCTAssertFalse(words.contains("%"))
        XCTAssertFalse(words.contains("+"), "the word carries the direction")

        // CONTROL: a coincident live pair draws both marks and no line.
        let coincident = NFLFinishCard9483(phase: .during, pregame: .init(away: 0, home: 17, at: t(-30)),
                                           projectedNow: .init(away: 0, home: 17, at: t(30)), final: nil)
        let sides = Comparison.sides(coincident, awayName: "Away control", homeName: "Home control")
        XCTAssertEqual(sides.map(\.current), [0, 17], "a current zero is a value, not an absence")
        XCTAssertEqual(sides.map(Comparison.changeText), ["Unchanged", "Unchanged"])
        XCTAssertEqual(Comparison.domain(coincident).lowerBound, 0, "football keeps its zero-based axis")
        XCTAssertEqual(Comparison.ticks(coincident).first, 0, "zero is a labelled tick")
    }

    // MARK: - One shared domain

    func testBothTeamsShareOneDomainInFootballAndBasketball() throws {
        let nfl = try eaglesBears()
        XCTAssertEqual(Comparison.domain(nfl), 0...31.5)
        XCTAssertEqual(Comparison.ticks(nfl), [0, 7, 14, 21, 28])
        XCTAssertEqual(Comparison.domain(nfl), NFLFinishCardView9483.pointDomain([23, 19.5, 18, 25.5], step: 7),
                       "the existing card's domain over every drawn value")

        // CONTROL: an NBA live card built through `build`, 100-plus scores.
        let nba = try XCTUnwrap(NFLFinishCard9483.build(input(
            [pair(-30, home: 112, away: 108.5), pair(30, home: 104, away: 121.5)], floor: 0, now: 40,
            sportKey: "basketball_nba")))
        XCTAssertEqual(nba.tickStep, 20)
        XCTAssertEqual(nba.startWord, "tip-off")
        XCTAssertEqual(Comparison.domain(nba), 80...150,
                       "basketball keeps its bounded axis, not a zero-based one that crowds the last tenth")
        XCTAssertEqual(Comparison.ticks(nba), [80, 100, 120, 140])
        let sides = Comparison.sides(nba, awayName: "Boston Celtics", homeName: "New York Knicks")
        for side in sides {
            let current = try XCTUnwrap(side.current)
            XCTAssertTrue(Comparison.domain(nba).contains(side.earlier))
            XCTAssertTrue(Comparison.domain(nba).contains(current))
        }
        XCTAssertEqual(sides.map(Comparison.changeText), ["13.0 points higher", "8.0 points lower"])
        XCTAssertEqual(sides.map(Comparison.currentText), ["121.5", "104"])
    }

    // MARK: - No clock, no source

    func testNoClockOrSourceIsAddedToWhatTheCardHolds() throws {
        let card = try eaglesBears()
        // The same values without the earlier clock: nothing the view says or
        // draws depends on a clock, so none can be invented or dropped.
        let undated = NFLFinishCard9483(phase: .during, pregame: .init(away: 23, home: 19.5, at: nil),
                                        projectedNow: .init(away: 18, home: 25.5, at: nil), final: nil)
        let a = Comparison.sides(card, awayName: "Eagles", homeName: "Bears")
        let b = Comparison.sides(undated, awayName: "Eagles", homeName: "Bears")
        XCTAssertEqual(a, b)
        XCTAssertEqual(a.map { Comparison.spoken(card, $0) }, b.map { Comparison.spoken(undated, $0) })
        for text in a.map({ Comparison.spoken(card, $0) }) + [Comparison.scaleCaption] {
            for word in ["AM", "PM", "draftkings", "DraftKings", "sportsbook", "Recorded", "%"] {
                XCTAssertFalse(text.contains(word), "\"\(word)\" is not on the card: \(text)")
            }
        }
        XCTAssertTrue(Comparison.scaleCaption.contains("Projected final points"), "projections, not chances or scores")
    }

    // MARK: - VoiceOver and layout

    func testVoiceOverSaysWholeNamesBasesAndTheComparisonInOrder() {
        let card = jaguarsEagles
        let sides = Comparison.sides(card, awayName: "Jacksonville Jaguars", homeName: "Philadelphia Eagles")
        XCTAssertEqual(Comparison.spoken(card, sides[0]),
                       "Jacksonville Jaguars. Earlier forecast 25 points. Projected now 19.8 points. 5.2 points lower.")
        XCTAssertEqual(Comparison.spoken(card, sides[1]),
                       "Philadelphia Eagles. Earlier forecast 17 points. Projected now 20.8 points. 3.8 points higher.")
        let long = Comparison.sides(card, awayName: "Washington Commanders", homeName: "San Francisco 49ers")
        XCTAssertTrue(Comparison.spoken(card, long[0]).hasPrefix("Washington Commanders. "), "the whole name")
        XCTAssertTrue(Comparison.spoken(card, long[1]).hasPrefix("San Francisco 49ers. "))
    }

    func testAccessibilityLayoutDecisions() {
        XCTAssertFalse(Comparison.alwaysStacksPanels(.large), "side by side only where both fit")
        XCTAssertTrue(Comparison.alwaysStacksPanels(.xxxLarge))
        XCTAssertTrue(Comparison.alwaysStacksPanels(.accessibility5))
        XCTAssertFalse(Comparison.alwaysStacksFigures(.xxxLarge), "two columns where both fit")
        XCTAssertTrue(Comparison.alwaysStacksFigures(.accessibility1))
        XCTAssertTrue(Comparison.alwaysStacksFigures(.accessibility5))
        // The track grows with its tick labels and nothing else.
        let small = Comparison.trackHeight(axisFontSize: 12, expanded: false)
        let large = Comparison.trackHeight(axisFontSize: 24, expanded: false)
        XCTAssertGreaterThan(large, small)
        XCTAssertEqual(large - small, 18, accuracy: 0.001, "one label line's growth, no blank band")
        XCTAssertLessThan(Comparison.trackHeight(axisFontSize: 12, expanded: true), 120, "never a giant track")
    }
}
