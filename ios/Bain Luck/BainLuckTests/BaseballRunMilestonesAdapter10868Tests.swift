import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game adapter, part three (the run milestones story
/// before first pitch and during play), on the RETAINED REAL `/game-markets`
/// of the White Sox–Astros game (`BaseballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The retained body was captured after the final: every full-game run line's
/// published value is the venue's `result` (no quote) and no option carries a
/// pregame pin. So, read as served, every chance slot says its own words —
/// that IS the honest reading, and it is asserted first. The chance rules
/// themselves are then shown on CONSTRUCTED copies that replace exactly the
/// named keys of ONE option (`BaseballRetained10868.markets(editingOption:)`).
@MainActor
final class BaseballRunMilestonesAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias A = BaseballRunMilestonesAdapter10868
    private typealias G = BaseballGamePageAdapter10868

    /// The served 10+ (Over 9.5) and 11+ (Over 10.5) options.
    private static let tenPlus = "o:244311417"
    private static let elevenPlus = "o:244311422"

    private static func quoted(_ value: Double, at stamp: String) -> [String: Any] {
        ["published": ["value": value, "value_state": "quoted", "basis": "published_source_display",
                       "source": "kalshi", "observed_at": stamp] as [String: Any]]
    }

    private static func row(_ input: TotalMilestoneInput10868, _ id: String) throws -> TotalMilestoneRow10868 {
        try XCTUnwrap(input.milestones.first { $0.id == id })
    }

    // MARK: - As served

    func testBeforeFirstPitchEveryOfferedRunLineIsAMilestoneAndAResultIsNeverAPregameChance() throws {
        let event = try F.beforeEvent()
        let markets = try F.markets()
        let input = try XCTUnwrap(A.input(event, markets: markets, host: F.milestoneHost(F.beforeNow)))
        let card = try XCTUnwrap(MLBTotalsCard11284.build(markets.gameQuestionMatrix, actualTotal: nil, eventID: F.eventID))

        XCTAssertEqual(A.lines(event, markets: markets).map(\.line), stride(from: 2.5, through: 14.5, by: 1).map { $0 })
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.eyebrow, "TOTAL RUNS · BOTH TEAMS")
        XCTAssertEqual(input.title, "How many runs?")
        XCTAssertEqual(input.chartTitle, "Chance of reaching each total")
        XCTAssertEqual(input.quantityAxisTitle, "Total runs in the game")
        XCTAssertEqual(input.milestones.map(\.id), card.lines.map(\.optionKey), "the production admission, in its order")
        XCTAssertEqual(input.milestones.map(\.quantityLabel), (3...15).map { "\($0)+" })
        XCTAssertEqual(input.milestones.first?.title, "3+ runs")
        for row in input.milestones {
            XCTAssertNil(row.before, row.id)
            XCTAssertEqual(row.beforeMissing, "Pregame chance unavailable")
            XCTAssertEqual(row.current, .unavailable("In-game chance unavailable"))
            XCTAssertNil(row.performance)
            XCTAssertEqual(row.result, .unconfirmed("Result unavailable"), "the venue's grade is not this card's")
        }
        XCTAssertNil(input.selectedMilestoneID, "no chance to open on")
        XCTAssertNil(input.timing)
        XCTAssertNil(input.actual, "no count before first pitch")
        XCTAssertNil(input.projection, "no projected total is admitted for baseball")
        XCTAssertEqual(input.markStyle, .stems)
        XCTAssertEqual(input.quantityDomain, TotalMilestoneDomain10868(lower: 0, upper: 16))
        XCTAssertEqual(input.quantityTicks.first, TotalMilestoneTick10868(value: 0, text: "0"))
        XCTAssertEqual(input.chanceTicks, A.chanceTicks)
    }

    func testDuringPlayTheRunsSoFarReachMilestonesAndNoReachedLineIsAChance() throws {
        let input = try XCTUnwrap(A.input(try F.liveEvent(), markets: try F.markets(), host: F.milestoneHost(F.liveNow)))

        XCTAssertEqual(input.phase, .during)
        XCTAssertEqual(input.title, "Runs so far against the milestones")
        // 3 + 7 = 10 runs so far: 3+ through 10+ are reached; 11+ and up are not.
        XCTAssertEqual(input.milestones.prefix(8).map(\.current), Array(repeating: .reached("Reached so far"), count: 8))
        XCTAssertEqual(input.milestones.prefix(8).map(\.performance), Array(repeating: nil, count: 8))
        XCTAssertEqual(input.milestones.suffix(5).map(\.current),
                       Array(repeating: .unavailable("In-game chance unavailable"), count: 5))
        XCTAssertEqual(input.milestones.suffix(5).map(\.performance),
                       ["1 more for 11+", "2 more for 12+", "3 more for 13+", "4 more for 14+", "5 more for 15+"])
        XCTAssertEqual(input.actual, .count(TotalMilestoneCount10868(
            quantity: 10, text: "10", unit: "runs", clock: nil, ruleLabel: "10 so far",
            accessibilityDetail: "10 runs so far")), "no score clock is served, so none is said")
        XCTAssertEqual(input.quantityDomain, TotalMilestoneDomain10868(lower: 0, upper: 16))
    }

    func testAfterTheFinalAnotherEventOrNoMarketsTheCardStepsAside() throws {
        XCTAssertNil(A.input(try F.finalEvent(), markets: try F.markets(), host: F.milestoneHost(F.finalNow)),
                     "after the final the run lines are the final targets card")
        // CONSTRUCTED: `beforeEvent` with only `id` changed — `/game-markets`
        // for another event is no ladder.
        XCTAssertNil(A.input(try F.beforeEvent(["id": 1]), markets: try F.markets(), host: F.milestoneHost(F.beforeNow)))
        XCTAssertTrue(A.lines(try F.beforeEvent(["id": 1]), markets: try F.markets()).isEmpty)
        XCTAssertNil(A.input(try F.beforeEvent(), markets: nil, host: F.milestoneHost(F.beforeNow)))
    }

    /// CONSTRUCTED: `liveEvent` with `home_score` null.
    func testDuringPlayAMissingScoreIsUnavailableAndReachesNothing() throws {
        let input = try XCTUnwrap(A.input(try F.liveEvent(["home_score": NSNull()]), markets: try F.markets(),
                                          host: F.milestoneHost(F.liveNow)))
        XCTAssertEqual(input.actual, .unavailable("Score unavailable"))
        XCTAssertFalse(input.milestones.contains { if case .reached = $0.current { return true } else { return false } })
        XCTAssertEqual(input.milestones.map(\.performance), Array(repeating: nil, count: 13))
    }

    // MARK: - The chance rules (CONSTRUCTED quotes)

    /// CONSTRUCTED: 10+'s `published` replaced by a Kalshi quote of 0.48
    /// observed 20:50:00Z.
    func testBeforeFirstPitchARecentQuoteIsThePregameChanceAndOpensTheCard() throws {
        let markets = try F.markets(editingOption: Self.tenPlus,
                                    setting: Self.quoted(0.48, at: "2026-09-30T20:50:00+00:00"))
        let host = F.milestoneHost(F.beforeNow)
        let input = try XCTUnwrap(A.input(try F.beforeEvent(), markets: markets, host: host))
        let at = "2026-09-30T20:50:00+00:00".asDate!
        let detail = "Recorded \(G.clockWords(at, host: host.page)) · Kalshi"

        XCTAssertEqual(try Self.row(input, Self.tenPlus).before, TotalMilestoneObservation10868(
            probability: 0.48, text: formatProbability(0.48), timeText: G.timeWords(at, host: host.page),
            accessibilityDetail: detail))
        XCTAssertEqual(input.milestones.compactMap(\.before).count, 1, "no other line is quoted")
        XCTAssertEqual(input.selectedMilestoneID, Self.tenPlus, "the only chance is the nearest even odds")
        XCTAssertEqual(input.timing, TotalMilestoneTiming10868(
            milestoneID: Self.tenPlus, title: "10+ runs · chance timing", lines: ["Pregame chance: \(detail)"]))

        // The host's held milestone wins.
        let held = try XCTUnwrap(A.input(try F.beforeEvent(), markets: markets, host: host,
                                         selectedMilestoneID: "o:244311410"))
        XCTAssertEqual(held.selectedMilestoneID, "o:244311410")
        XCTAssertEqual(held.timing?.lines, ["Pregame chance: Pregame chance unavailable"])

        // Thirty-one minutes later the same quote is no pregame chance.
        let stale = try XCTUnwrap(A.input(try F.beforeEvent(), markets: markets,
                                          host: F.milestoneHost(at.addingTimeInterval(31 * 60))))
        XCTAssertNil(try Self.row(stale, Self.tenPlus).before)
    }

    /// CONSTRUCTED: 11+'s `published` replaced by a Kalshi quote of 0.48 at
    /// the named instant; the reader's `now` is 21:10:00Z.
    func testDuringPlayOnlyARecentQuoteObservedAfterTheStartIsTheInGameChance() throws {
        let now = F.start.addingTimeInterval(10 * 60)
        let host = F.milestoneHost(now)

        let after = try F.markets(editingOption: Self.elevenPlus, setting: Self.quoted(0.48, at: "2026-09-30T21:05:00+00:00"))
        let input = try XCTUnwrap(A.input(try F.liveEvent(), markets: after, host: host,
                                          selectedMilestoneID: Self.elevenPlus))
        let at = "2026-09-30T21:05:00+00:00".asDate!
        let detail = "Recorded \(G.clockWords(at, host: host.page)) · Kalshi"
        XCTAssertEqual(try Self.row(input, Self.elevenPlus).current, .recorded(TotalMilestoneObservation10868(
            probability: 0.48, text: formatProbability(0.48), timeText: G.timeWords(at, host: host.page),
            accessibilityDetail: detail), movement: nil))
        XCTAssertNil(try Self.row(input, Self.elevenPlus).before, "a quote is never the pregame pin")
        XCTAssertEqual(input.timing?.lines, ["Pregame chance: Pregame chance unavailable", "Recorded in-game: \(detail)"])

        // A quote observed before the start is never the in-game chance.
        let before = try F.markets(editingOption: Self.elevenPlus, setting: Self.quoted(0.48, at: "2026-09-30T20:50:00+00:00"))
        let early = try XCTUnwrap(A.input(try F.liveEvent(), markets: before, host: host))
        XCTAssertEqual(try Self.row(early, Self.elevenPlus).current, .unavailable("In-game chance unavailable"))

        // CONSTRUCTED: `liveEvent` with `status` `suspended`: no in-game chance.
        let suspended = try XCTUnwrap(A.input(try F.liveEvent(["status": "suspended"]), markets: after, host: host))
        XCTAssertEqual(try Self.row(suspended, Self.elevenPlus).current, .unavailable("In-game chance unavailable"))

        // A reached line says so, whatever its quote.
        let reached = try XCTUnwrap(A.input(try F.liveEvent(), markets: after, host: host, selectedMilestoneID: Self.tenPlus))
        XCTAssertEqual(try Self.row(reached, Self.tenPlus).current, .reached("Reached so far"))
        XCTAssertEqual(reached.timing?.lines, ["Pregame chance: Pregame chance unavailable", "Actual so far: Reached so far"])
    }

    /// CONSTRUCTED: 11+ given an available `pregame_reading` (0.47, 20:55:00Z,
    /// `pregame_pin`, naming its own one contributor 244311422).
    func testDuringPlayThePregameChanceIsTheProducersPinSavedBeforeFirstPitch() throws {
        let markets = try F.markets(editingOption: Self.elevenPlus, setting: [
            "pregame_reading": ["state": "available", "reason": NSNull(), "probability": 0.47,
                                "observed_at": "2026-09-30T20:55:00+00:00", "basis": "pregame_pin",
                                "outcome_id": 244311422] as [String: Any],
        ])
        let host = F.milestoneHost(F.liveNow)
        let input = try XCTUnwrap(A.input(try F.liveEvent(), markets: markets, host: host))
        let at = "2026-09-30T20:55:00+00:00".asDate!
        XCTAssertEqual(try Self.row(input, Self.elevenPlus).before, TotalMilestoneObservation10868(
            probability: 0.47, text: formatProbability(0.47), timeText: G.timeWords(at, host: host.page),
            accessibilityDetail: "Saved before first pitch \(G.clockWords(at, host: host.page)) · Kalshi"))
        XCTAssertEqual(input.selectedMilestoneID, Self.elevenPlus)

        // The same pin is not read before first pitch: there the quote is the chance.
        let before = try XCTUnwrap(A.input(try F.beforeEvent(), markets: markets, host: F.milestoneHost(F.beforeNow)))
        XCTAssertNil(try Self.row(before, Self.elevenPlus).before)
    }
}
