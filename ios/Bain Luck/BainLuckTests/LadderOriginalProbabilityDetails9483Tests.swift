import XCTest
@testable import Bain_Luck

/// Prepared, not executed. The ladder Details content reads the held card's
/// selected point and nothing else: `Point.chance` / `now` / `result` drive the
/// headline and rail; `Detail` is provenance.
///
/// Real bodies: `event-15320337-game-matrix-9483-nba-final` (Clippers 104–101
/// Warriors, every option settled with no pin and no quote) and
/// `event-15327183-game-matrix-9483-nba-pregame` (Raptors @ Knicks before
/// tip-off). Every other card here is a CONSTRUCTED presentation control, not a
/// provider specimen. Dates go through `SourceAge.preciseStamp`, so nothing
/// depends on the test machine's time zone. Geometry, fit and VoiceOver
/// focus are NOT asserted here.
@MainActor
final class LadderOriginalProbabilityDetails9483Tests: XCTestCase {
    private typealias Model = LadderOriginalProbabilityDetails9483
    private typealias Point = NBALadderCard9483.Point
    private typealias Detail = NBALadderCard9483.Detail

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

    private func finalTotal() throws -> NBALadderCard9483 {
        let b = try body("event-15320337-game-matrix-9483-nba-final.20261015.json")
        return try XCTUnwrap(NBALadderCard9483.total(.init(
            matrix: b.gameQuestionMatrix, status: "completed",
            commenceTime: date("2026-10-04T23:00:00Z"), homeScore: b.homeScore, awayScore: b.awayScore,
            pregameProjection: nil, homeShort: "Clippers", awayShort: "Warriors",
            now: date("2026-10-05T04:00:00Z"))))
    }

    private func pregameMargin() throws -> NBALadderCard9483 {
        let b = try body("event-15327183-game-matrix-9483-nba-pregame.20261015.json")
        return try XCTUnwrap(NBALadderCard9483.margin(.init(
            matrix: b.gameQuestionMatrix, status: "scheduled",
            commenceTime: date("2026-10-15T23:30:00Z"), homeScore: nil, awayScore: nil,
            pregameProjection: nil, homeShort: "Knicks", awayShort: "Raptors",
            now: date("2026-10-15T18:40:00Z"))))
    }

    // MARK: - Constructed controls

    private let t1 = "2026-10-15T23:20:00Z"
    private let t2 = "2026-10-16T01:05:00Z"

    private func detail(quoted: Double? = nil, observedAt: String? = nil, baseline: Double? = nil,
                        baselineAt: String? = nil, result: Bool? = nil) -> Detail {
        Detail(label: "Over 210.5 points", marketName: "Toronto vs New York: Total Points",
               source: "kalshi", quoted: quoted, observedAt: observedAt,
               baseline: baseline, baselineObservedAt: baselineAt, result: result)
    }

    private func point(_ key: String = "o:1", chance: Double?, now: Double? = nil,
                       observedAt: String? = nil, result: Bool? = nil, detail: Detail? = nil) -> Point {
        Point(optionKey: key, x: 210.5, label: "Over 210.5", side: .game, chance: chance, now: now,
              observedAt: observedAt, result: result, detail: detail ?? self.detail())
    }

    private func card(_ phase: NBALadderCard9483.Phase, _ points: [Point]) -> NBALadderCard9483 {
        NBALadderCard9483(family: .total, phase: phase, points: points, actual: nil, forecast: nil,
                          awayShort: "Raptors", homeShort: "Knicks")
    }

    // MARK: - Real final (15320337)

    func testTheRealFinalPrintsTheProducersResultAndNoFabricatedBaseline() throws {
        let final = try finalTotal()
        let lost = try XCTUnwrap(Model.content(card: final, optionKey: "o:240505185"))
        XCTAssertEqual(lost.selected, "Over 206.5")
        XCTAssertEqual(lost.readings.map(\.label), ["Pregame chance"], "no Current chance after the final")
        XCTAssertNil(lost.readings[0].value, "the capture serves no pin; none is fabricated")
        XCTAssertEqual(lost.readings[0].text, Model.unavailable)
        XCTAssertEqual(lost.readings[0].marker, .hollow)
        XCTAssertTrue(lost.marks.isEmpty, "no reading, no rail")
        XCTAssertEqual(lost.result, .miss)
        XCTAssertTrue(lost.about.contains(Model.Row(label: "Pregame baseline", value: Model.unavailable)))
        XCTAssertFalse(lost.about.contains { $0.label == "Last recorded probability" }, "a result is not a recorded value")

        let won = try XCTUnwrap(Model.content(card: final, optionKey: "o:240505186"))
        XCTAssertEqual(won.selected, "Over 204.5")
        XCTAssertEqual(won.result, .hit)
        XCTAssertFalse(Model.spoken(won).contains("%"), "a result never becomes 100%")
    }

    // MARK: - Before tip-off

    func testTheRealPregameMarginReadsTheSelectedTeamsOwnPublishedChance() throws {
        let card = try pregameMargin()
        let selected = try XCTUnwrap(card.points.first { $0.side == .away && $0.chance != nil })
        let content = try XCTUnwrap(Model.content(card: card, optionKey: selected.optionKey))
        let chance = try XCTUnwrap(selected.chance)
        XCTAssertEqual(content.selected, selected.label)
        XCTAssertEqual(content.readings.count, 1)
        XCTAssertEqual(content.readings[0].text, formatProbability(chance))
        XCTAssertEqual(content.readings[0].value, chance, "the raw value, never a complement")
        XCTAssertEqual(content.readings[0].marker, .solid)
        XCTAssertEqual(content.readings[0].time, SourceAge.preciseStamp(selected.observedAt))
        XCTAssertNil(content.result)
    }

    func testBeforeTipOffDetailValuesNeverReplaceOrJoinThePointsChance() {
        // Constructed: Detail disagrees with the Point on purpose.
        let p = point(chance: 0.62, observedAt: t1,
                      detail: detail(quoted: 0.70, observedAt: t2, baseline: 0.40, baselineAt: t1))
        let content = Model.content(card: card(.before, [p]), optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.label), ["Pregame chance"])
        XCTAssertEqual(content.readings[0].text, formatProbability(0.62))
        XCTAssertEqual(content.readings[0].time, SourceAge.preciseStamp(t1))
        XCTAssertEqual(content.marks.map(\.value), [0.62])
        XCTAssertFalse(content.about.contains { $0.label == "Pregame baseline" },
                       "no second comparison before tip-off")
        XCTAssertTrue(content.about.contains(Model.Row(
            label: "Last recorded probability",
            value: "\(formatProbability(0.70)), recorded \(SourceAge.preciseStamp(t2)!)")))
        XCTAssertFalse(Model.spoken(content).contains(formatProbability(0.40)))
    }

    func testBeforeTipOffWithoutAChanceSaysSoAndDrawsNoRail() {
        let p = point(chance: nil, observedAt: t1, detail: detail(quoted: 0.70, observedAt: t1))
        let content = Model.content(card: card(.before, [p]), optionKey: "o:1")!
        XCTAssertEqual(content.readings[0].text, Model.noRecentUpdate)
        XCTAssertNil(content.readings[0].time, "an absent reading has no date")
        XCTAssertTrue(content.marks.isEmpty, "the quote is never promoted to a chance")
    }

    // MARK: - During play

    func testDuringPlayPairsTheHollowPregameAndSolidCurrentEachWithItsOwnClock() {
        let p = point(chance: 0.48, now: 0.61, observedAt: t2,
                      detail: detail(quoted: 0.90, observedAt: t1, baseline: 0.30, baselineAt: t1))
        let content = Model.content(card: card(.during, [p]), optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.label), ["Pregame chance", "Current chance"])
        XCTAssertEqual(content.readings.map(\.text), [formatProbability(0.48), formatProbability(0.61)])
        XCTAssertEqual(content.readings.map(\.marker), [.hollow, .solid])
        XCTAssertEqual(content.readings.map(\.time), [SourceAge.preciseStamp(t1), SourceAge.preciseStamp(t2)])
        XCTAssertNil(content.result)
        XCTAssertFalse(Model.spoken(content).contains("point"), "no invented delta")
    }

    func testDuringPlayMissingValuesAndDatesStayExplicit() {
        let neither = Model.content(card: card(.during, [point(chance: nil, now: nil)]), optionKey: "o:1")!
        XCTAssertEqual(neither.readings.map(\.text), [Model.unavailable, Model.noRecentUpdate])
        XCTAssertTrue(neither.marks.isEmpty)

        let undated = Model.content(card: card(.during, [point(chance: 0.5, now: 0.55, observedAt: nil)]),
                                    optionKey: "o:1")!
        XCTAssertEqual(undated.readings.map(\.time), [Model.timeUnknown, Model.timeUnknown], "never assumed now")
        XCTAssertEqual(undated.readings[0].dateLine, Model.timeUnknown)
    }

    func testAnExpiredCurrentLosesItsDotButKeepsTheBaseline() {
        let held = card(.during, [point(chance: 0.48, now: 0.61, observedAt: t2,
                                        detail: detail(quoted: 0.61, observedAt: t2, baseline: 0.48, baselineAt: t1))])
        let aged = held.current(at: date("2026-10-17T12:00:00Z"))
        let content = Model.content(card: aged, optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.text), [formatProbability(0.48), Model.noRecentUpdate])
        XCTAssertEqual(content.marks.map(\.marker), [.hollow])
        XCTAssertNotNil(aged.points[0].detail.quoted, "retained provenance is not a current chance")
    }

    func testZeroOneAndCoincidentReadingsAreAllMarked() {
        let ends = Model.content(card: card(.during, [point(chance: 0, now: 1, observedAt: t2)]), optionKey: "o:1")!
        XCTAssertEqual(ends.marks.map(\.value), [0, 1], "zero is a reading, not an absence")
        XCTAssertEqual(ends.readings.map(\.text), [formatProbability(0), formatProbability(1)])
        XCTAssertEqual(Model.railX(0, width: 200, inset: 8), 8)
        XCTAssertEqual(Model.railX(1, width: 200, inset: 8), 192)
        XCTAssertEqual(Model.railX(0.625, width: 200, inset: 8), 123, "raw value, not the rounded 63%")

        // Same value at two clocks: two marks, two dates.
        let same = Model.content(card: card(.during, [point(chance: 0.55, now: 0.55, observedAt: t2,
                                                           detail: detail(baselineAt: t1))]), optionKey: "o:1")!
        XCTAssertEqual(same.marks.map(\.marker), [.hollow, .solid])
        XCTAssertEqual(same.marks.map(\.value), [0.55, 0.55])
        XCTAssertNotEqual(same.readings[0].time, same.readings[1].time)
    }

    // MARK: - After the final

    func testTheFinalNeverPrintsACurrentChanceOrTheDetailsResult() {
        let injected = point(chance: 0.58, now: 0.90, observedAt: t2, result: nil,
                             detail: detail(quoted: 0.99, observedAt: t2, baseline: 0.58, baselineAt: t1, result: true))
        let content = Model.content(card: card(.after, [injected]), optionKey: "o:1")!
        XCTAssertEqual(content.readings.map(\.label), ["Pregame chance"])
        XCTAssertEqual(content.marks.map(\.value), [0.58])
        XCTAssertEqual(content.result, .unavailable, "Detail.result never fills Point.result")
        XCTAssertFalse(Model.spoken(content).contains("Current"))
        XCTAssertFalse(Model.spoken(content).contains("Hit"))

        let missed = point(chance: 0.58, result: false, detail: detail(result: true))
        XCTAssertEqual(Model.content(card: card(.after, [missed]), optionKey: "o:1")?.result, .miss)
    }

    func testNoResultBeforeTheFinal() {
        let leaked = point(chance: 0.5, now: 0.6, observedAt: t2, result: true, detail: detail(result: true))
        for phase in [NBALadderCard9483.Phase.before, .during] {
            let content = Model.content(card: card(phase, [leaked]), optionKey: "o:1")!
            XCTAssertNil(content.result)
            XCTAssertFalse(Model.spoken(content).contains("Result"))
        }
    }

    // MARK: - Identity

    func testOnlyTheExactKeyIsShownAndAWithdrawnKeyNamesNoNeighbour() throws {
        let final = try finalTotal()
        let withdrawn = NBALadderCard9483(
            family: final.family, phase: final.phase,
            points: final.points.filter { $0.optionKey != "o:240505185" }, actual: final.actual,
            forecast: final.forecast, awayShort: final.awayShort, homeShort: final.homeShort)
        XCTAssertNil(Model.content(card: withdrawn, optionKey: "o:240505185"))
        XCTAssertNil(Model.content(card: final, optionKey: nil))
        XCTAssertNil(Model.content(card: final, optionKey: "o:missing"))
        XCTAssertNil(Model.content(card: nil, optionKey: "o:240505185"))
        XCTAssertNil(Model.content(card: card(.before, [point(chance: 0.4), point(chance: 0.6)]), optionKey: "o:1"),
                     "an ambiguous key is no selection")
        let spoken = Model.spoken(nil)
        XCTAssertTrue(spoken.hasPrefix(Model.unavailableTitle))
        XCTAssertFalse(spoken.contains("%"))
    }

    // MARK: - Spoken

    func testTheSpokenSummaryNamesEachMeaningValueAndDate() {
        let p = point(chance: 0.48, now: 0.61, observedAt: t2, detail: detail(baselineAt: t1))
        let content = Model.content(card: card(.during, [p]), optionKey: "o:1")!
        XCTAssertEqual(Model.spoken(content),
                       "Scoring expectations. Selected line: Over 210.5. "
                       + "Pregame chance \(formatProbability(0.48)), recorded \(SourceAge.preciseStamp(t1)!). "
                       + "Current chance \(formatProbability(0.61)), recorded \(SourceAge.preciseStamp(t2)!).")
        for word in ["price", "odds", "quote", "question"] {
            XCTAssertFalse(Model.spoken(content).lowercased().contains(word))
            XCTAssertFalse(content.about.map { $0.label.lowercased() }.contains { $0.contains(word) })
        }
    }
}
