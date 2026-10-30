import XCTest
@testable import Bain_Luck

/// #9483 — the finished NFL final-versus-forecast comparison
/// (`NFLFinalComparisonPresentation9483`). Prepared tests: NOT_RUN at source
/// handback.
///
/// Real retained input: event 14780563 (`FinalForecastComparison11296Tests`),
/// Washington Commanders 17 @ San Francisco 49ers 23, the served qualified
/// pair away 22.2 / home 29.4 printed 22 / 29. The Eagles 7 / Bears 27 card on
/// an earlier 23 / 19.5 history point is the existing deck tests' value.
/// Every other value below is a CONTROL, named as one, not an observed game.
///
/// What these pin, and the mutation each kills:
/// - swap the teams or print the served halves → `testTheRetainedCommandersFinalKeepsItsOrientationAndPrintedForecast`
/// - call a history point "Projection before scheduled start", or round it → `testAHistoryPointKeepsItsOwnNameAndHalfPoint`
/// - print a level pair while the headline grades a leader → `testAPairPrintedLevelPrintsAndGradesLevel`
/// - lose a zero, or one of two coincident marks, off the axis → `testZeroAndCoincidentValuesStayOnTheSharedAxis`
/// - draw a live, pregame or final-less card → `testOnlyAFinishedCardWithAFinalIsDrawn`
/// - speak a number the card does not print → `testVoiceOverSaysThePrintedNumbersUnderTheirBasis`
@MainActor
final class NFLFinalComparisonPresentation9483Tests: XCTestCase {
    private typealias Presentation = NFLFinalComparisonPresentation9483

    private static let washington = "Washington Commanders"
    private static let sanFrancisco = "San Francisco 49ers"
    /// 14780563's served `ended_at`, 2026-10-20T03:22:26Z.
    private static let endedAt = Date(timeIntervalSince1970: 1_792_466_546)

    /// 14780563 as `NFLFinishCard9483.build` returns it after the final with
    /// the headline's qualified pair: scheduled-start basis, no single clock.
    private var commanders: NFLFinishCard9483 {
        NFLFinishCard9483(phase: .after, pregame: .init(away: 22.2, home: 29.4, at: nil), projectedNow: nil,
                          final: .init(away: 17, home: 23, at: Self.endedAt), pregameBasis: .scheduledStart)
    }

    private func t(_ minutes: Double) -> Date { Self.endedAt.addingTimeInterval(minutes * 60) }

    func testTheRetainedCommandersFinalKeepsItsOrientationAndPrintedForecast() {
        let card = commanders
        XCTAssertTrue(Presentation.applies(card))
        let sides = Presentation.sides(card, awayName: Self.washington, homeName: Self.sanFrancisco)
        XCTAssertEqual(sides.map(\.name), [Self.washington, Self.sanFrancisco], "away first, keyed by team")
        XCTAssertEqual(sides.map(\.isHome), [false, true])
        XCTAssertEqual(sides.map(\.final), [17, 23], "the admitted final, unchanged")
        XCTAssertEqual(sides.map(\.earlier), [22.2, 29.4], "the marks keep the served halves")
        XCTAssertEqual(sides.map(Presentation.finalText), ["17", "23"])
        XCTAssertEqual(sides.map { Presentation.earlierText(card, $0) }, ["22", "29"],
                       "printed per side as the headline prints it")
        XCTAssertEqual(card.pregameName, "Projection before scheduled start")
        XCTAssertEqual(card.headline(awayName: Self.washington, homeName: Self.sanFrancisco),
                       "San Francisco 49ers won as projected")
        XCTAssertEqual(card.key, "Points · outline = projection before scheduled start · cross = final")
        // One axis for both teams, from the existing card's own domain.
        XCTAssertEqual(Presentation.domain(card), 0...38.5)
        XCTAssertEqual(Presentation.ticks(card), [0, 7, 14, 21, 28, 35])
        for side in sides { XCTAssertTrue(Presentation.domain(card).contains(side.final) && Presentation.domain(card).contains(side.earlier)) }
    }

    func testAHistoryPointKeepsItsOwnNameAndHalfPoint() {
        let card = NFLFinishCard9483(phase: .after, pregame: .init(away: 23, home: 19.5, at: t(-230)),
                                     projectedNow: nil, final: .init(away: 7, home: 27, at: t(0)))
        XCTAssertEqual(card.pregameBasis, .history)
        let sides = Presentation.sides(card, awayName: "Eagles", homeName: "Bears")
        XCTAssertEqual(sides.map { Presentation.earlierText(card, $0) }, ["23", "19.5"], "the history point is not rounded")
        XCTAssertEqual(card.pregameName, NFLFinishCard9483.earlierForecast,
                       "a different basis says so, never \"Projection before scheduled start\"")
        XCTAssertEqual(Presentation.spoken(card, sides[1]), "Bears. Final 27. Earlier forecast 19.5.")
        XCTAssertEqual(card.headline(awayName: "Eagles", homeName: "Bears"), "Bears beat the forecast")
    }

    /// CONTROL (#11536 F1's shape): a qualified pair less than a point apart
    /// that prints level. The printed figures and the headline agree.
    func testAPairPrintedLevelPrintsAndGradesLevel() {
        let card = NFLFinishCard9483(phase: .after, pregame: .init(away: 21.75, home: 22.25, at: nil),
                                     projectedNow: nil, final: .init(away: 17, home: 20, at: t(0)),
                                     pregameBasis: .scheduledStart)
        let sides = Presentation.sides(card, awayName: "Away control", homeName: "Home control")
        XCTAssertEqual(sides.map { Presentation.earlierText(card, $0) }, ["22", "22"])
        XCTAssertEqual(card.headline(awayName: "Away control", homeName: "Home control"), "Home control won",
                       "no leader the reader cannot see")
        XCTAssertEqual(sides.map(\.earlier), [21.75, 22.25], "the marks keep the served halves")
    }

    /// CONTROLS: a shutout side whose forecast was also zero, and a side whose
    /// final equals its forecast. Both numbers print, and every mark sits on
    /// the zero-based axis.
    func testZeroAndCoincidentValuesStayOnTheSharedAxis() {
        let card = NFLFinishCard9483(phase: .after, pregame: .init(away: 0, home: 17, at: nil),
                                     projectedNow: nil, final: .init(away: 0, home: 17, at: t(0)),
                                     pregameBasis: .scheduledStart)
        let sides = Presentation.sides(card, awayName: "Away control", homeName: "Home control")
        XCTAssertEqual(sides.map(Presentation.finalText), ["0", "17"])
        XCTAssertEqual(sides.map { Presentation.earlierText(card, $0) }, ["0", "17"])
        XCTAssertEqual(Presentation.domain(card).lowerBound, 0, "football keeps its zero-based axis")
        XCTAssertGreaterThanOrEqual(Presentation.domain(card).upperBound, 17)
        XCTAssertEqual(Presentation.ticks(card).first, 0, "zero is a labelled tick")
        XCTAssertEqual(Presentation.spoken(card, sides[0]),
                       "Away control. Final 0. Projection before scheduled start 0.", "both numbers are said")
        // An all-zero card still draws a readable axis.
        let blank = NFLFinishCard9483(phase: .after, pregame: .init(away: 0, home: 0, at: nil), projectedNow: nil,
                                      final: .init(away: 0, home: 0, at: t(0)), pregameBasis: .scheduledStart)
        XCTAssertEqual(Presentation.domain(blank), 0...14)
        XCTAssertEqual(Presentation.ticks(blank), [0, 7, 14])
    }

    func testOnlyAFinishedCardWithAFinalIsDrawn() {
        let before = NFLFinishCard9483(phase: .before, pregame: .init(away: 18, home: 20.5, at: t(-30)),
                                       projectedNow: nil, final: nil)
        let live = NFLFinishCard9483(phase: .during, pregame: .init(away: 18, home: 20.5, at: t(-30)),
                                     projectedNow: .init(away: 24, home: 21, at: t(-5)), final: nil)
        // CONTROL: `build` never returns a finished card without a final; the
        // value type still allows it, and the view must not fill it in.
        let noFinal = NFLFinishCard9483(phase: .after, pregame: .init(away: 18, home: 20.5, at: nil),
                                        projectedNow: nil, final: nil, pregameBasis: .scheduledStart)
        for card in [before, live, noFinal] {
            XCTAssertFalse(Presentation.applies(card))
            XCTAssertTrue(Presentation.sides(card, awayName: "Eagles", homeName: "Bears").isEmpty,
                          "nothing drawn; the host keeps its existing card")
        }
        // A finished card that still carried a live projection never shows it.
        let carried = NFLFinishCard9483(phase: .after, pregame: commanders.pregame,
                                        projectedNow: .init(away: 40, home: 3, at: t(-5)), final: commanders.final,
                                        pregameBasis: .scheduledStart)
        let sides = Presentation.sides(carried, awayName: Self.washington, homeName: Self.sanFrancisco)
        XCTAssertEqual(sides, Presentation.sides(commanders, awayName: Self.washington, homeName: Self.sanFrancisco))
        XCTAssertEqual(Presentation.domain(carried), Presentation.domain(commanders), "a projection never widens the axis")
    }

    func testVoiceOverSaysThePrintedNumbersUnderTheirBasis() {
        let card = commanders
        let sides = Presentation.sides(card, awayName: Self.washington, homeName: Self.sanFrancisco)
        XCTAssertEqual(Presentation.spoken(card, sides[0]),
                       "Washington Commanders. Final 17. Projection before scheduled start 22.")
        XCTAssertEqual(Presentation.spoken(card, sides[1]),
                       "San Francisco 49ers. Final 23. Projection before scheduled start 29.")
        for side in sides {
            XCTAssertFalse(["22.2", "29.4"].contains { Presentation.spoken(card, side).contains($0) },
                           "never the unrounded half the card does not print")
            XCTAssertFalse(Presentation.spoken(card, side).lowercased().contains("pregame"),
                           "never an unqualified \"pregame\"")
        }
    }
}
