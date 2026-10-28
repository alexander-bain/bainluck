import XCTest
@testable import Bain_Luck

/// Prepared, not executed: production matrix/admission/selection remains the
/// authority. A live-status control reuses the existing retained pregame matrix;
/// it is not evidence that a live observation was delivered on a device.
@MainActor
final class NBAScoringPresentation9483Tests: XCTestCase {
    private struct Body: Decodable { let gameQuestionMatrix: EventQuestionMatrix? }

    private func liveCard() throws -> NBALadderCard9483 {
        let path = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures/event-15327183-game-matrix-9483-nba-pregame.20261015.json")
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let body = try decoder.decode(Body.self, from: Data(contentsOf: path))
        let input = NBALadderCard9483.Input(
            matrix: body.gameQuestionMatrix, status: "live",
            commenceTime: ISO8601DateFormatter().date(from: "2026-10-15T18:00:00Z"),
            homeScore: 20, awayScore: 18, pregameProjection: nil,
            homeShort: "Knicks", awayShort: "Raptors",
            now: ISO8601DateFormatter().date(from: "2026-10-15T18:40:00Z")!)
        return try XCTUnwrap(NBALadderCard9483.total(input))
    }

    func testLiveProbabilityIsReadableWithoutInventingPregameBaseline() throws {
        let card = try liveCard()
        let point = try XCTUnwrap(card.points.first { $0.now != nil })
        XCTAssertNil(point.chance)
        let spoken = NBAScoringChanceComparison9483.accessibilitySummary(for: point)
        XCTAssertTrue(spoken.contains("Pregame chance: Unavailable"))
        XCTAssertTrue(spoken.contains("Current chance: \(formatProbability(try XCTUnwrap(point.now)))"))
    }

    func testExpiredCurrentValueDoesNotReturnFromRetainedDetails() throws {
        let card = try liveCard()
        let selected = try XCTUnwrap(card.points.first { $0.now != nil })
        let aged = card.current(at: ISO8601DateFormatter().date(from: "2026-10-15T23:40:00Z")!)
        let point = try XCTUnwrap(aged.points.first { $0.optionKey == selected.optionKey })
        XCTAssertNil(point.now)
        XCTAssertNotNil(point.detail.quoted, "Retained details remain independently available")
        let spoken = NBAScoringChanceComparison9483.accessibilitySummary(for: point)
        XCTAssertTrue(spoken.contains("Current chance: Unavailable"))
        XCTAssertFalse(spoken.contains("Current chance: \(formatProbability(try XCTUnwrap(point.detail.quoted)))"))
        XCTAssertEqual(aged.actual, card.actual)
    }

    func testMissingSelectionNeverReadsANeighbor() throws {
        let card = try liveCard()
        let state = NFLCardDeckState9483()
        let selected = try XCTUnwrap(state.selectedIndex(in: card))
        state.move(in: card, by: selected == 0 ? 1 : -1)
        let chosen = try XCTUnwrap(state.selectedIndex(in: card))
        let key = card.points[chosen].optionKey
        let withdrawn = NBALadderCard9483(
            family: card.family, phase: card.phase,
            points: card.points.filter { $0.optionKey != key }, actual: card.actual,
            forecast: card.forecast, awayShort: card.awayShort, homeShort: card.homeShort)
        let index = state.selectedIndex(in: withdrawn)
        XCTAssertNil(index)
        let spoken = NBAScoringChanceComparison9483.accessibilitySummary(for: index.map { withdrawn.points[$0] })
        XCTAssertTrue(spoken.contains("Selected market unavailable"))
        XCTAssertFalse(spoken.contains("%"))
        XCTAssertEqual(state.selectedIndex(in: card).map { card.points[$0].optionKey }, key)
    }

    func testZeroCurrentAndHistoricalBaselineAreIndependent() throws {
        let original = try XCTUnwrap(try liveCard().points.first)
        // Presentation boundary control, not a fabricated provider specimen.
        let point = NBALadderCard9483.Point(
            optionKey: original.optionKey, x: original.x, label: original.label,
            side: original.side, chance: 0.35, now: 0, observedAt: original.observedAt,
            result: nil, detail: original.detail)
        let spoken = NBAScoringChanceComparison9483.accessibilitySummary(for: point)
        XCTAssertTrue(spoken.contains("Pregame chance: \(formatProbability(0.35))"))
        XCTAssertTrue(spoken.contains("Current chance: \(formatProbability(0))"))
        XCTAssertFalse(spoken.contains("Unavailable"))
    }

    func testReorderingPreservesTheSelectedContractsSpokenValues() throws {
        let card = try liveCard()
        let state = NFLCardDeckState9483()
        state.move(in: card, by: 1)
        let chosen = try XCTUnwrap(state.selectedIndex(in: card))
        let point = card.points[chosen]
        let reordered = NBALadderCard9483(
            family: card.family, phase: card.phase, points: Array(card.points.reversed()),
            actual: card.actual, forecast: card.forecast,
            awayShort: card.awayShort, homeShort: card.homeShort)
        let next = try XCTUnwrap(state.selectedIndex(in: reordered))
        XCTAssertEqual(reordered.points[next].optionKey, point.optionKey)
        XCTAssertEqual(NBAScoringChanceComparison9483.accessibilitySummary(for: reordered.points[next]),
                       NBAScoringChanceComparison9483.accessibilitySummary(for: point))
    }

    // MARK: Second increment — actual vs pregame figures, line controls

    private func withForecast(_ card: NBALadderCard9483, family: NBALadderCard9483.Family? = nil,
                              actual: Double?, forecast: Double?) -> NBALadderCard9483 {
        NBALadderCard9483(family: family ?? card.family, phase: card.phase, points: card.points,
                          actual: actual, forecast: forecast,
                          awayShort: card.awayShort, homeShort: card.homeShort)
    }

    func testFiguresNameActualAndPregameProjectionSeparately() throws {
        let card = try liveCard()
        XCTAssertEqual(card.actual, 38, "Retained matrix with the test's live score 20–18")
        // Presentation control: the fixture's page passes no pregame pair.
        let spoken = NBAScoringFigures9483.accessibilitySummary(
            for: withForecast(card, actual: card.actual, forecast: 210.5))
        XCTAssertEqual(spoken, "Actual so far: 38 points. Pregame projection: 210.5 points.")
        XCTAssertFalse(spoken.localizedCaseInsensitiveContains("current"))
        XCTAssertFalse(spoken.contains("Projected final"))
    }

    func testMissingPregameProjectionIsNotFilled() throws {
        let card = try liveCard()
        XCTAssertNil(card.forecast)
        let spoken = NBAScoringFigures9483.accessibilitySummary(for: card)
        XCTAssertEqual(spoken, "Actual so far: 38 points.")
        XCTAssertFalse(spoken.contains("projection"))
    }

    func testMarginFiguresNameTheSideAndKeepATie() throws {
        let card = try liveCard()
        // Presentation control on the margin axis: words, not a provider specimen.
        let behind = withForecast(card, family: .margin, actual: -4, forecast: 2.5)
        XCTAssertEqual(NBAScoringFigures9483.accessibilitySummary(for: behind),
                       "Actual so far: Raptors by 4. Pregame projection: Knicks by 2.5.")
        let level = withForecast(card, family: .margin, actual: 0, forecast: nil)
        XCTAssertEqual(NBAScoringFigures9483.accessibilitySummary(for: level), "Actual so far: Tie.")
    }

    func testLineStepsNameTheAdjacentLine() throws {
        let card = try liveCard()
        let state = NFLCardDeckState9483()
        let selected = try XCTUnwrap(state.selectedIndex(in: card))
        let previous = NBAScoringLineControls9483.stepLabel(card, selected: selected, by: -1)
        let next = NBAScoringLineControls9483.stepLabel(card, selected: selected, by: 1)
        XCTAssertEqual(previous, selected > 0 ? "Previous line: \(card.points[selected - 1].label)" : "Previous line")
        XCTAssertEqual(next, selected < card.points.count - 1
                       ? "Next line: \(card.points[selected + 1].label)" : "Next line")
        XCTAssertEqual(NBAScoringLineControls9483.stepLabel(card, selected: 0, by: -1), "Previous line")
        XCTAssertEqual(NBAScoringLineControls9483.stepLabel(card, selected: card.points.count - 1, by: 1),
                       "Next line")
        // Labels describe; they never move the selection.
        XCTAssertEqual(state.selectedIndex(in: card), selected)
    }

    func testWithdrawnSelectionNamesNoNeighbourInControls() throws {
        let card = try liveCard()
        let state = NFLCardDeckState9483()
        let chosen = try XCTUnwrap(state.selectedIndex(in: card))
        state.move(in: card, by: chosen == 0 ? 1 : -1)
        let moved = try XCTUnwrap(state.selectedIndex(in: card))
        let key = card.points[moved].optionKey
        let withdrawn = NBALadderCard9483(
            family: card.family, phase: card.phase,
            points: card.points.filter { $0.optionKey != key }, actual: card.actual,
            forecast: card.forecast, awayShort: card.awayShort, homeShort: card.homeShort)
        let index = state.selectedIndex(in: withdrawn)
        XCTAssertNil(index)
        XCTAssertEqual(NBAScoringLineControls9483.stepLabel(withdrawn, selected: index, by: -1), "Previous line")
        XCTAssertEqual(NBAScoringLineControls9483.stepLabel(withdrawn, selected: index, by: 1), "Next line")
        XCTAssertEqual(NBAScoringLineControls9483.detailsLabel(index.map { withdrawn.points[$0] }),
                       "Selected market unavailable")
    }

    func testDetailsActionNamesTheSelectedLine() throws {
        let card = try liveCard()
        let state = NFLCardDeckState9483()
        let selected = try XCTUnwrap(state.selectedIndex(in: card))
        let point = card.points[selected]
        XCTAssertEqual(NBAScoringLineControls9483.detailsLabel(point), "Details and timing for \(point.label)")
    }

    // MARK: Density correction — side/unit beside the number

    private func joined(_ parts: (lead: String, figure: String, unit: String)) -> String {
        [parts.lead, parts.figure, parts.unit].filter { !$0.isEmpty }.joined(separator: " ")
    }

    func testFigurePartsRebuildTheSpokenTextExactly() throws {
        let card = try liveCard()
        // Presentation controls on both axes, not provider specimens.
        let margin = withForecast(card, family: .margin, actual: -4, forecast: 2.5)
        for (sample, value) in [(card, 38.0), (card, 210.5), (margin, -4), (margin, 2.5), (margin, 0)] {
            XCTAssertEqual(joined(NBAScoringFigures9483.parts(sample, value)),
                           NBAScoringFigures9483.text(sample, value))
        }
    }

    func testFigurePartsKeepTheSideAndUnitApartFromTheNumber() throws {
        let card = try liveCard()
        let total = NBAScoringFigures9483.parts(card, 210.5)
        XCTAssertEqual(total.lead, "")
        XCTAssertEqual(total.figure, "210.5")
        XCTAssertEqual(total.unit, "points")
        let margin = withForecast(card, family: .margin, actual: -4, forecast: 2.5)
        let away = NBAScoringFigures9483.parts(margin, -4)
        XCTAssertEqual(away.lead, "Raptors by")
        XCTAssertEqual(away.figure, "4")
        let home = NBAScoringFigures9483.parts(margin, 2.5)
        XCTAssertEqual(home.lead, "Knicks by")
        XCTAssertEqual(home.figure, "2.5")
        let tie = NBAScoringFigures9483.parts(margin, 0)
        XCTAssertEqual(tie.lead, "")
        XCTAssertEqual(tie.figure, "Tie")
        XCTAssertEqual(tie.unit, "")
    }
}
