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
}
