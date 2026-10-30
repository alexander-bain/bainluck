import SwiftUI
import XCTest
@testable import Bain_Luck

/// #9483 — the finished NBA ladder's overview and selected reading
/// (`FinalLadderComparison9483`). Prepared, not executed.
///
/// RETAINED: `event-15320337-game-matrix-9483-nba-final` (Clippers 104–101
/// Warriors, final) through the production `NBALadderCard9483` builders — the
/// same game the v99 reference draws. Its options are settled results with
/// `not_quoted` comparisons and no pin, so the retained capture carries NO
/// pregame chance: "Clippers by 2+" (`o:240505100`) is Won with its chance
/// unavailable. v99's 38.5% is visual evidence and is not claimed here.
///
/// CONSTRUCTED (labelled at each use): the pregame projection
/// (home 109.8 / away 112.5, the existing `NBAEventCards9483Tests` control that
/// gives v99's Warriors by 2.7), hand-built cards for the other actual/forecast
/// pairs and missing values, and points with a chance or a quote set by hand.
/// Fixed clocks only (gotcha #44). These are model tests, not render, fit,
/// interaction or VoiceOver evidence.
@MainActor
final class FinalLadderComparison9483Tests: XCTestCase {

    private struct Body: Decodable {
        let homeScore: Int?
        let awayScore: Int?
        let gameQuestionMatrix: EventQuestionMatrix?
    }

    private func body(_ name: String) throws -> Body {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/\(name)")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(Body.self, from: Data(contentsOf: url))
    }

    private func date(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }

    /// The retained final through the production builder. `projection` is
    /// CONSTRUCTED when supplied.
    private func finalInput(projection: (home: Double, away: Double)? = nil,
                            scored: Bool = true) throws -> NBALadderCard9483.Input {
        let b = try body("event-15320337-game-matrix-9483-nba-final.20261015.json")
        return .init(matrix: b.gameQuestionMatrix, status: "completed",
                     commenceTime: date("2026-10-04T23:00:00Z"),
                     homeScore: scored ? b.homeScore : nil, awayScore: scored ? b.awayScore : nil,
                     pregameProjection: projection, homeShort: "Clippers", awayShort: "Warriors",
                     now: date("2026-10-05T04:00:00Z"))
    }

    /// The retained pregame matrix (Raptors @ Knicks) before tip-off, or with
    /// a CONSTRUCTED live status and score.
    private func earlierInput(status: String, home: Int? = nil, away: Int? = nil,
                              commence: String) throws -> NBALadderCard9483.Input {
        let b = try body("event-15327183-game-matrix-9483-nba-pregame.20261015.json")
        return .init(matrix: b.gameQuestionMatrix, status: status, commenceTime: date(commence),
                     homeScore: home, awayScore: away, pregameProjection: (home: 110, away: 108),
                     homeShort: "Knicks", awayShort: "Raptors", now: date("2026-10-15T18:40:00Z"))
    }

    private let gameProjection = (home: 109.8, away: 112.5) // CONSTRUCTED

    /// CONSTRUCTED: a finished card with the given values.
    private func card(_ family: NBALadderCard9483.Family, actual: Double?, forecast: Double?,
                      points: [NBALadderCard9483.Point] = [],
                      phase: NBALadderCard9483.Phase = .after) -> NBALadderCard9483 {
        NBALadderCard9483(family: family, phase: phase, points: points, actual: actual,
                          forecast: forecast, awayShort: "Warriors", homeShort: "Clippers")
    }

    /// CONSTRUCTED: `point` with its chance, result and Details numbers set by hand.
    private func with(_ point: NBALadderCard9483.Point, chance: Double?, result: Bool?,
                      quoted: Double? = nil, baseline: Double? = nil) -> NBALadderCard9483.Point {
        let d = point.detail
        return NBALadderCard9483.Point(
            optionKey: point.optionKey, x: point.x, label: point.label, side: point.side,
            chance: chance, now: nil, observedAt: point.observedAt, result: result,
            detail: .init(label: d.label, marketName: d.marketName, source: d.source, quoted: quoted,
                          observedAt: d.observedAt, baseline: baseline,
                          baselineObservedAt: d.baselineObservedAt, result: d.result))
    }

    private func replacing(_ card: NBALadderCard9483, _ point: NBALadderCard9483.Point) -> NBALadderCard9483 {
        NBALadderCard9483(family: card.family, phase: card.phase,
                          points: card.points.map { $0.optionKey == point.optionKey ? point : $0 },
                          actual: card.actual, forecast: card.forecast,
                          awayShort: card.awayShort, homeShort: card.homeShort)
    }

    private let clippersBy2 = "o:240505100"

    // MARK: - Overview

    func testTheRetainedFinalMarginComparesActualWithTheProjectedMargin() throws {
        let card = try XCTUnwrap(NBALadderCard9483.margin(finalInput(projection: gameProjection)))
        XCTAssertTrue(FinalLadderComparison9483.applies(card))
        XCTAssertEqual(card.actual, 3, "Clippers by 3, the retained final score")
        XCTAssertEqual(card.forecast, -2.7, "Warriors by 2.7, the constructed projection")
        XCTAssertEqual(FinalLadderComparison9483.performance(card),
                       "Clippers beat the projected margin by 5.7 points")
        XCTAssertNil(FinalLadderComparison9483.unavailable(card))
    }

    func testTheMarginSentenceNamesTheSideThatBeatTheProjectionNotTheWinner() {
        // Away beats it: Warriors by 4 against a projected Clippers by 1.5.
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.margin, actual: -4, forecast: 1.5)),
                       "Warriors beat the projected margin by 5.5 points")
        // The Clippers WON by 1, but a projected Clippers by 3.5 means the
        // Warriors beat the projected margin. No winner is named.
        let differentWinner = FinalLadderComparison9483.performance(card(.margin, actual: 1, forecast: 3.5))
        XCTAssertEqual(differentWinner, "Warriors beat the projected margin by 2.5 points")
        XCTAssertFalse(differentWinner?.contains("won") ?? true)
        // The Warriors won by 2, projected to win by 6: the Clippers beat it.
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.margin, actual: -2, forecast: -6)),
                       "Clippers beat the projected margin by 4.0 points")
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.margin, actual: 3, forecast: 3)),
                       "Final margin matched the projected margin")
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.margin, actual: 0, forecast: 0)),
                       "Final margin matched the projected margin")
    }

    func testTheTotalSentenceSaysAboveBelowOrMatchedWithItsUnit() throws {
        // Retained 205 against the constructed 222.3.
        let retained = try XCTUnwrap(NBALadderCard9483.total(finalInput(projection: gameProjection)))
        XCTAssertEqual(retained.actual, 205)
        XCTAssertEqual(retained.forecast, 222.3)
        XCTAssertEqual(FinalLadderComparison9483.performance(retained),
                       "Total finished 17.3 points below the pregame projection")
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.total, actual: 212, forecast: 208.6)),
                       "Total finished 3.4 points above the pregame projection")
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.total, actual: 205, forecast: 205)),
                       "Total matched the pregame projection")
    }

    func testATinyNonzeroDifferenceNeverReadsAsAMatch() {
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.total, actual: 205, forecast: 204.96)),
                       "Total finished <0.1 points above the pregame projection")
        XCTAssertEqual(FinalLadderComparison9483.performance(card(.margin, actual: 3, forecast: 3.04)),
                       "Warriors beat the projected margin by <0.1 points")
        XCTAssertEqual(FinalLadderComparison9483.magnitude(-5.7), deltaPointsNumber(5.7),
                       "the magnitude is the shared precision, unsigned")
        XCTAssertEqual(FinalLadderComparison9483.magnitude(0.04), "<0.1")
    }

    func testAMissingActualOrProjectionIsNamedAndMakesNoSentence() throws {
        let noProjection = try XCTUnwrap(NBALadderCard9483.margin(finalInput()))
        XCTAssertNil(noProjection.forecast)
        XCTAssertNil(FinalLadderComparison9483.performance(noProjection))
        XCTAssertEqual(FinalLadderComparison9483.unavailable(noProjection), "Pregame projection unavailable")

        let noScore = try XCTUnwrap(NBALadderCard9483.margin(finalInput(projection: gameProjection, scored: false)))
        XCTAssertNil(noScore.actual)
        XCTAssertNil(FinalLadderComparison9483.performance(noScore))
        XCTAssertEqual(FinalLadderComparison9483.unavailable(noScore), "Actual final unavailable")

        let neither = card(.total, actual: nil, forecast: nil)
        XCTAssertNil(FinalLadderComparison9483.performance(neither))
        XCTAssertEqual(FinalLadderComparison9483.unavailable(neither),
                       "Actual final and pregame projection unavailable")
        XCTAssertEqual(FinalLadderComparison9483.overviewSummary(neither),
                       "Actual final and pregame projection unavailable.",
                       "no projection words are spoken for a projection that is not there")
    }

    // MARK: - Selected reading

    func testTheRetainedSelectedLineKeepsItsResultWithItsChanceUnavailable() throws {
        let card = try XCTUnwrap(NBALadderCard9483.margin(finalInput(projection: gameProjection)))
        let point = try XCTUnwrap(FinalLadderComparison9483.selected(card, key: clippersBy2))
        XCTAssertEqual(point.label, "Clippers by 2+")
        XCTAssertNil(point.chance, "the retained capture admits no pregame chance for this line")
        XCTAssertNil(FinalLadderComparison9483.chance(point))
        XCTAssertEqual(FinalLadderComparison9483.result(point), "Won")
        XCTAssertEqual(FinalLadderComparison9483.readingSummary(point),
                       "Selected line: Clippers by 2+. Pregame chance unavailable. Result: Won.")
    }

    func testAKnownPregameChancePrintsThroughTheSharedFormatter() throws {
        let retained = try XCTUnwrap(NBALadderCard9483.margin(finalInput(projection: gameProjection)))
        let base = try XCTUnwrap(retained.points.first { $0.optionKey == clippersBy2 })
        let card = replacing(retained, with(base, chance: 0.385, result: true)) // CONSTRUCTED chance
        let point = try XCTUnwrap(FinalLadderComparison9483.selected(card, key: clippersBy2))
        XCTAssertEqual(FinalLadderComparison9483.chance(point), formatProbability(0.385))
        XCTAssertEqual(FinalLadderComparison9483.chance(point), "39%",
                       "whole percent pending the owner's precision decision; v99 prints 38.5%")
        XCTAssertEqual(FinalLadderComparison9483.result(point), "Won")
    }

    func testAnUnknownResultNeverHidesAKnownChance() throws {
        let retained = try XCTUnwrap(NBALadderCard9483.margin(finalInput()))
        let base = try XCTUnwrap(retained.points.first { $0.optionKey == clippersBy2 })
        let point = with(base, chance: 0.385, result: nil) // CONSTRUCTED
        XCTAssertEqual(FinalLadderComparison9483.chance(point), "39%")
        XCTAssertEqual(FinalLadderComparison9483.result(point), "Result unavailable")
        XCTAssertEqual(FinalLadderComparison9483.readingSummary(point),
                       "Selected line: Clippers by 2+. Pregame chance: 39%. Result unavailable.")
    }

    func testTheChanceIsThePointsOwnNeverAQuoteABaselineOrASibling() throws {
        let retained = try XCTUnwrap(NBALadderCard9483.margin(finalInput()))
        let base = try XCTUnwrap(retained.points.first { $0.optionKey == clippersBy2 })
        let sibling = try XCTUnwrap(retained.points.first { $0.optionKey != clippersBy2 && $0.side == .home })
        // CONSTRUCTED: Details carry numbers, the drawn chance is nil, and a
        // neighbour has a chance.
        var card = replacing(retained, with(base, chance: nil, result: true, quoted: 0.6, baseline: 0.4))
        card = replacing(card, with(sibling, chance: 0.7, result: sibling.result))
        let point = try XCTUnwrap(FinalLadderComparison9483.selected(card, key: clippersBy2))
        XCTAssertNil(FinalLadderComparison9483.chance(point))
        let spoken = FinalLadderComparison9483.readingSummary(point)
        for borrowed in ["60%", "40%", "70%", "100%", "0%"] {
            XCTAssertFalse(spoken.contains(borrowed), borrowed)
        }
    }

    func testTheResultIsTheProducersVerdictNotTheScoreOrTheChance() throws {
        let retained = try XCTUnwrap(NBALadderCard9483.margin(finalInput()))
        let base = try XCTUnwrap(retained.points.first { $0.optionKey == clippersBy2 })
        // CONSTRUCTED: the score (Clippers by 3) clears by 2+, the chance is
        // high, and the producer says Lost. Lost is printed.
        let point = with(base, chance: 0.9, result: false)
        XCTAssertEqual(FinalLadderComparison9483.result(point), "Lost")
        XCTAssertEqual(FinalLadderComparison9483.result(with(base, chance: 0.1, result: true)), "Won")
    }

    func testANilOrWithdrawnSelectionSelectsNothing() throws {
        let card = try XCTUnwrap(NBALadderCard9483.margin(finalInput()))
        XCTAssertNotNil(card.defaultIndex, "the card has a default this view must not fall back to")
        XCTAssertNil(FinalLadderComparison9483.selected(card, key: nil))
        XCTAssertNil(FinalLadderComparison9483.selected(card, key: "o:999999999"))
        XCTAssertEqual(FinalLadderComparison9483.readingSummary(nil), "Selected line unavailable.")
        let view = FinalLadderReading9483(card: card, selectedOptionKey: "o:999999999",
                                          awayColor: .blue, homeColor: .red, onDetails: { _ in })
        XCTAssertFalse(view.hasDetailsAction, "no line, no Details control")
    }

    func testDetailsOpenTheExactLineOnlyWhenTheHostSuppliesACallback() throws {
        let card = try XCTUnwrap(NBALadderCard9483.margin(finalInput()))
        var opened: [String] = []
        let wired = FinalLadderReading9483(card: card, selectedOptionKey: clippersBy2,
                                           awayColor: .blue, homeColor: .red,
                                           onDetails: { opened.append($0) })
        XCTAssertTrue(wired.hasDetailsAction)
        wired.openDetails()
        XCTAssertEqual(opened, [clippersBy2], "the selected original, by its own key")

        let plain = FinalLadderReading9483(card: card, selectedOptionKey: clippersBy2,
                                           awayColor: .blue, homeColor: .red)
        XCTAssertFalse(plain.hasDetailsAction, "no callback, no control")
        plain.openDetails()
        XCTAssertEqual(opened, [clippersBy2])
        let point = try XCTUnwrap(FinalLadderComparison9483.selected(card, key: clippersBy2))
        XCTAssertEqual(NBAScoringLineControls9483.detailsLabel(point), "Details and timing for Clippers by 2+")
    }

    // MARK: - Phases and words

    func testBeforeAndDuringPlayTheViewsDecline() throws {
        let before = try XCTUnwrap(NBALadderCard9483.margin(
            earlierInput(status: "scheduled", commence: "2026-10-15T23:30:00Z")))
        // CONSTRUCTED live status and score on the retained pregame matrix.
        let during = try XCTUnwrap(NBALadderCard9483.margin(
            earlierInput(status: "live", home: 20, away: 18, commence: "2026-10-15T18:00:00Z")))
        XCTAssertEqual(before.phase, .before)
        XCTAssertEqual(during.phase, .during)
        for card in [before, during] {
            XCTAssertFalse(FinalLadderComparison9483.applies(card))
            XCTAssertNil(FinalLadderComparison9483.performance(card), "\(card.phase)")
            XCTAssertNil(FinalLadderComparison9483.unavailable(card))
            XCTAssertEqual(FinalLadderComparison9483.overviewSummary(card), "")
            let key = try XCTUnwrap(card.points.first?.optionKey)
            XCTAssertNil(FinalLadderComparison9483.selected(card, key: key))
            XCTAssertFalse(FinalLadderReading9483(card: card, selectedOptionKey: key, awayColor: .blue,
                                                  homeColor: .red, onDetails: { _ in }).hasDetailsAction)
        }
    }

    func testTheSpokenOverviewAndReadingSayWhatEachNumberIs() throws {
        let card = try XCTUnwrap(NBALadderCard9483.margin(finalInput(projection: gameProjection)))
        XCTAssertEqual(FinalLadderComparison9483.overviewSummary(card),
                       "Clippers beat the projected margin by 5.7 points. "
                       + "Actual final: Clippers by 3. Pregame projection: Warriors by 2.7.")
        let point = try XCTUnwrap(FinalLadderComparison9483.selected(card, key: clippersBy2))
        let spoken = [FinalLadderComparison9483.overviewSummary(card),
                      FinalLadderComparison9483.readingSummary(point)].joined(separator: " ")
        for word in ["question", "Saved chance", "Hit", "Miss", "Current chance"] {
            XCTAssertFalse(spoken.contains(word), word)
        }
    }
}
