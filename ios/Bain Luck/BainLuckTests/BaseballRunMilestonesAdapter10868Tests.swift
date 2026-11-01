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
///
/// A milestone's Details (`milestones`, `details`) are pinned the same way.
/// Before first pitch and during play exist here only as CONSTRUCTED phases of
/// the retained event (`beforeEvent`, `liveEvent`), so every Details test is
/// CONSTRUCTED at the event, and each says whether its markets are the
/// retained body verbatim or a named one-option edit. The retained body is a
/// FINAL capture: its venue results are passed through as the plain original
/// says them, never asserted as a pregame or in-game truth, and its terminal
/// evidence legs are never an open quote.
@MainActor
final class BaseballRunMilestonesAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias A = BaseballRunMilestonesAdapter10868
    private typealias G = BaseballGamePageAdapter10868
    private typealias S = BaseballTotalsStory10868

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

    // MARK: - Details helpers

    /// The 12+ (Over 11.5) option.
    private static let twelvePlus = "o:244311421"
    /// 11+'s original identity in the retained matrix: the final run-line
    /// card's own (`MLBOriginal11284.option`).
    private static let elevenPlusOriginal = "mlb-o:15321836:q:q:count|runs|game|full_game|ge:11|o:244311422"
    /// CONSTRUCTED clocks: a quote one minute before the 20:59 reader, a quote
    /// five minutes after the listed start, and the stored pin's own clock.
    private static let quoteAt = "2026-09-30T20:58:00+00:00"
    private static let liveQuoteAt = "2026-09-30T21:05:00+00:00"
    private static let pinAt = "2026-09-30T20:55:00+00:00"

    /// CONSTRUCTED: 11+'s stored producer pin (0.47, `pregame_pin`, naming its
    /// own one contributor 244311422), as in the test above.
    private static let pin: [String: Any] = [
        "pregame_reading": ["state": "available", "reason": NSNull(), "probability": 0.47,
                            "observed_at": pinAt, "basis": "pregame_pin", "outcome_id": 244311422] as [String: Any],
    ]

    private static func fields(_ original: MLBOriginal11284) -> [MLBOriginal11284.Field] {
        original.sections.flatMap(\.fields)
    }

    private static func value(_ label: String, in original: MLBOriginal11284) -> [String] {
        fields(original).filter { $0.label == label }.map(\.value)
    }

    private static func field(_ label: String, _ value: String) -> MLBOriginal11284.Field {
        MLBOriginal11284.Field(label: label, value: value)
    }

    /// A tap as the host resolves it: the page's drawn card is this result's
    /// card, in `phase`, on the retained event.
    private static func tap(_ id: String, _ milestones: A.Milestones?,
                            phase: BaseballEventPagePhase10868) -> MLBOriginal11284? {
        A.details(id, totals: milestones.map { S.milestones($0.input) }, phase: phase,
                  milestones: milestones, eventID: F.eventID)
    }

    /// The final run-line card's own original for `id`, default label.
    private static func plain(_ markets: GameMarketsResponse, _ id: String) throws -> MLBOriginal11284 {
        let card = try XCTUnwrap(MLBTotalsCard11284.build(markets.gameQuestionMatrix, actualTotal: nil, eventID: F.eventID))
        return try XCTUnwrap(card.lines.first { $0.optionKey == id }?.original)
    }

    /// Test arithmetic only: `original` with the pin's label put back to the
    /// default, to show that label is the ONLY difference.
    private static func defaultLabelled(_ original: MLBOriginal11284) -> MLBOriginal11284 {
        MLBOriginal11284(id: original.id, title: original.title, sections: original.sections.map { section in
            MLBOriginal11284.Section(title: section.title, fields: section.fields.map {
                $0.label == A.Words.pinLabel ? MLBOriginal11284.Field(label: "Pregame chance", value: $0.value) : $0
            })
        })
    }

    // MARK: - Details: identity (R1–R8)

    /// R1. RETAINED markets; CONSTRUCTED phase (`beforeEvent`).
    func testEachDrawnMilestoneKeepsTheExactOriginalItsRunLineWasBuiltWithAndOnlyThePinIsNamedApart() throws {
        let markets = try F.markets()
        let built = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: markets, host: F.milestoneHost(F.beforeNow)))
        let named = try XCTUnwrap(MLBTotalsCard11284.build(markets.gameQuestionMatrix, actualTotal: nil,
                                                           eventID: F.eventID, pinLabel: A.Words.pinLabel))
        let plain = try XCTUnwrap(MLBTotalsCard11284.build(markets.gameQuestionMatrix, actualTotal: nil, eventID: F.eventID))

        XCTAssertEqual(A.Words.pinLabel, "Recorded pregame reference")
        XCTAssertEqual(built.eventID, F.eventID)
        XCTAssertEqual(built.origins.map(\.milestoneID), built.input.milestones.map(\.id), "one per drawn row, in its order")
        XCTAssertEqual(built.origins.map(\.original), named.lines.map(\.original), "the builder's own originals, kept")
        XCTAssertEqual(built.origins.map(\.original.id), plain.lines.map(\.original.id), "the final run-line card's identities")
        for (origin, line) in zip(built.origins, plain.lines) {
            XCTAssertEqual(Self.value(A.Words.pinLabel, in: origin.original), ["Unavailable"], origin.milestoneID)
            XCTAssertEqual(Self.value("Pregame chance", in: origin.original), [],
                           "\(origin.milestoneID): the stored pin is never called the pregame chance")
            XCTAssertEqual(Self.defaultLabelled(origin.original), line.original, "only the pin's label differs")
        }

        let details = try XCTUnwrap(Self.tap(Self.elevenPlus, built, phase: .before))
        let origin = try XCTUnwrap(built.origins.first { $0.milestoneID == Self.elevenPlus })
        XCTAssertEqual(details.id, Self.elevenPlusOriginal)
        XCTAssertEqual(details.id, origin.original.id)
        XCTAssertEqual(details.title, origin.original.title)
        XCTAssertEqual(Array(details.sections.dropFirst()), origin.original.sections, "then the original's sections, verbatim")
        XCTAssertEqual(details.sections.first, MLBOriginal11284.Section(
            title: "11+ runs", fields: [Self.field("Pregame chance", "Pregame chance unavailable")]),
                       "first the card's own reading of that row: here its absence words")
    }

    /// R2. RETAINED markets; CONSTRUCTED phases.
    func testTheCardAndItsOriginalsAreOneResultBeforeAndDuringPlayAndNoneAfterTheFinal() throws {
        let markets = try F.markets()
        let beforeEvent = try F.beforeEvent()
        let liveEvent = try F.liveEvent()
        let phases: [(EventDetail, Date)] = [(beforeEvent, F.beforeNow), (liveEvent, F.liveNow)]
        for (event, now) in phases {
            for held in [nil, Self.elevenPlus] as [String?] {
                let host = F.milestoneHost(now)
                let built = try XCTUnwrap(A.milestones(event, markets: markets, host: host, selectedMilestoneID: held))
                XCTAssertEqual(built.input, A.input(event, markets: markets, host: host, selectedMilestoneID: held),
                               "the card is exactly what it was")
                XCTAssertEqual(built.origins.map(\.milestoneID), built.input.milestones.map(\.id))
                XCTAssertEqual(built.eventID, F.eventID)
            }
        }
        XCTAssertNil(A.milestones(try F.finalEvent(), markets: markets, host: F.milestoneHost(F.finalNow)),
                     "after the final the run lines are the final targets card, with its own Details")

        // During play the same originals; the first section adds the row's in-game state.
        let before = try XCTUnwrap(A.milestones(beforeEvent, markets: markets, host: F.milestoneHost(F.beforeNow)))
        let live = try XCTUnwrap(A.milestones(liveEvent, markets: markets, host: F.milestoneHost(F.liveNow)))
        XCTAssertEqual(live.origins, before.origins)
        XCTAssertEqual(Self.tap(Self.elevenPlus, live, phase: .live)?.sections.first?.fields, [
            Self.field("Pregame chance", "Pregame chance unavailable"),
            Self.field("In-game chance", "In-game chance unavailable"),
        ])
        XCTAssertEqual(Self.tap(Self.tenPlus, live, phase: .live)?.sections.first?.fields, [
            Self.field("Pregame chance", "Pregame chance unavailable"),
            Self.field("Actual so far", "Reached so far"),
        ], "3 + 7 runs so far: performance, never a chance and never a settlement")
    }

    /// R3. CONSTRUCTED: 12+'s `option_key` set to 11+'s, so the matrix
    /// carries it twice; then CONSTRUCTED values repeating a drawn row or an
    /// original of the retained result.
    func testAMilestoneIdCarriedTwiceOpensNothingAndItsNeighboursStillDo() throws {
        let host = F.milestoneHost(F.beforeNow)
        let twice = try F.markets(editingOption: Self.twelvePlus, setting: ["option_key": Self.elevenPlus])
        let built = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: twice, host: host))
        XCTAssertEqual(built.input.milestones.count, 11, "both lines are dropped, never guessed between")
        XCTAssertFalse(built.input.milestones.contains { $0.id == Self.elevenPlus })
        XCTAssertNil(Self.tap(Self.elevenPlus, built, phase: .before))
        XCTAssertEqual(Self.tap(Self.tenPlus, built, phase: .before)?.id,
                       built.origins.first { $0.milestoneID == Self.tenPlus }?.original.id)

        let clean = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: try F.markets(), host: host))
        let input = clean.input
        let row = try Self.row(input, Self.tenPlus)
        let origin = try XCTUnwrap(clean.origins.first { $0.milestoneID == Self.tenPlus })
        let rowTwice = TotalMilestoneInput10868(
            phase: input.phase, eyebrow: input.eyebrow, title: input.title, chartTitle: input.chartTitle,
            quantityAxisTitle: input.quantityAxisTitle, milestones: input.milestones + [row],
            selectedMilestoneID: input.selectedMilestoneID, actual: input.actual, projection: input.projection,
            quantityDomain: input.quantityDomain, quantityTicks: input.quantityTicks, chanceTicks: input.chanceTicks,
            timing: input.timing, markStyle: input.markStyle)
        XCTAssertNil(Self.tap(Self.tenPlus, A.Milestones(eventID: F.eventID, input: rowTwice, origins: clean.origins),
                              phase: .before), "a row drawn twice")
        let originTwice = A.Milestones(eventID: F.eventID, input: input, origins: clean.origins + [origin])
        XCTAssertNil(Self.tap(Self.tenPlus, originTwice, phase: .before), "an original kept twice")
        XCTAssertNotNil(Self.tap(Self.elevenPlus, originTwice, phase: .before), "only the repeated id refuses")
    }

    /// R4. RETAINED markets; CONSTRUCTED phase, and `beforeEvent` with only
    /// `id` changed.
    func testAnotherEventsTapOrResultOpensNothing() throws {
        let markets = try F.markets()
        let host = F.milestoneHost(F.beforeNow)
        XCTAssertNil(A.milestones(try F.beforeEvent(["id": 1]), markets: markets, host: host),
                     "`/game-markets` for another event is no result")
        let built = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: markets, host: host))
        let drawn = S.milestones(built.input)
        XCTAssertNotNil(A.details(Self.elevenPlus, totals: drawn, phase: .before, milestones: built, eventID: F.eventID))
        XCTAssertNil(A.details(Self.elevenPlus, totals: drawn, phase: .before, milestones: built, eventID: 1))
        let elsewhere = A.Milestones(eventID: 1, input: built.input, origins: built.origins)
        XCTAssertNil(A.details(Self.elevenPlus, totals: drawn, phase: .before, milestones: elsewhere, eventID: F.eventID))
    }

    /// R5. CONSTRUCTED: 11+'s one Over option re-sided `under`, so the app no
    /// longer admits that line (the production admission's own rule).
    func testARemovedMilestoneOrAStalePassOpensNothing() throws {
        let host = F.milestoneHost(F.beforeNow)
        let old = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: try F.markets(), host: host))
        let new = try XCTUnwrap(A.milestones(
            try F.beforeEvent(), markets: try F.markets(editingOption: Self.elevenPlus, setting: ["side": "under"]),
            host: host))
        XCTAssertEqual(new.input.milestones.count, 12)
        XCTAssertFalse(new.input.milestones.contains { $0.id == Self.elevenPlus })
        XCTAssertNil(Self.tap(Self.elevenPlus, new, phase: .before), "removed: nothing, never a neighbour")
        XCTAssertNotNil(Self.tap(Self.tenPlus, new, phase: .before))

        // A card drawn from one pass never resolves against another pass's originals.
        XCTAssertNil(A.details(Self.tenPlus, totals: S.milestones(new.input), phase: .before, milestones: old,
                               eventID: F.eventID))
        XCTAssertNil(A.details(Self.tenPlus, totals: S.milestones(old.input), phase: .before, milestones: new,
                               eventID: F.eventID))
    }

    /// R6. CONSTRUCTED: 11+'s `option_key` replaced by `o:999`.
    func testAReplacedMilestoneOpensOnlyUnderItsNewIdentity() throws {
        let replaced = try XCTUnwrap(A.milestones(
            try F.beforeEvent(), markets: try F.markets(editingOption: Self.elevenPlus, setting: ["option_key": "o:999"]),
            host: F.milestoneHost(F.beforeNow)))
        XCTAssertNil(Self.tap(Self.elevenPlus, replaced, phase: .before), "the old id opens nothing")
        let details = try XCTUnwrap(Self.tap("o:999", replaced, phase: .before))
        XCTAssertEqual(details.id, "mlb-o:15321836:q:q:count|runs|game|full_game|ge:11|o:999")
        XCTAssertEqual(details.sections.first?.title, "11+ runs")
    }

    /// R7. RETAINED: all thirteen originals share one market title.
    /// CONSTRUCTED: 11+'s `label` set to 10+'s served words.
    func testSharedTitlesAndLabelsNeverDecideWhichOriginalOpens() throws {
        let host = F.milestoneHost(F.beforeNow)
        let built = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: try F.markets(), host: host))
        XCTAssertEqual(Set(built.origins.map(\.original.title)), ["Chicago White Sox vs Houston: Total Runs"])
        XCTAssertEqual(Set(built.origins.map(\.original.id)).count, 13)
        for origin in built.origins {
            XCTAssertEqual(Self.tap(origin.milestoneID, built, phase: .before)?.id, origin.original.id)
        }

        let relabelled = try XCTUnwrap(A.milestones(
            try F.beforeEvent(),
            markets: try F.markets(editingOption: Self.elevenPlus, setting: ["label": "Over 9.5 runs scored"]),
            host: host))
        let eleven = try XCTUnwrap(Self.tap(Self.elevenPlus, relabelled, phase: .before))
        let ten = try XCTUnwrap(Self.tap(Self.tenPlus, relabelled, phase: .before))
        XCTAssertEqual(Self.value("Original side", in: eleven), ["Over 9.5 runs scored"])
        XCTAssertEqual(Self.value("Original side", in: eleven), Self.value("Original side", in: ten), "the same words")
        XCTAssertEqual(eleven.id, Self.elevenPlusOriginal, "its own original all the same")
        XCTAssertNotEqual(eleven.id, ten.id)
    }

    /// R8. RETAINED markets; CONSTRUCTED phases.
    func testAFinalRunLineIdAnotherPhaseOrNoCardOpensNothing() throws {
        let markets = try F.markets()
        let before = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: markets, host: F.milestoneHost(F.beforeNow)))
        let drawn = S.milestones(before.input)
        XCTAssertNil(A.details(Self.elevenPlusOriginal, totals: drawn, phase: .before, milestones: before,
                               eventID: F.eventID), "a final run line's id is not a milestone's")
        XCTAssertNil(A.details("", totals: drawn, phase: .before, milestones: before, eventID: F.eventID))
        XCTAssertNil(A.details(Self.elevenPlus, totals: drawn, phase: .live, milestones: before, eventID: F.eventID))
        XCTAssertNil(A.details(Self.elevenPlus, totals: drawn, phase: .final, milestones: before, eventID: F.eventID))
        XCTAssertNil(A.details(Self.elevenPlus, totals: nil, phase: .before, milestones: before, eventID: F.eventID))
        XCTAssertNil(A.details(Self.elevenPlus, totals: drawn, phase: .before, milestones: nil, eventID: F.eventID))

        let live = try XCTUnwrap(A.milestones(try F.liveEvent(), markets: markets, host: F.milestoneHost(F.liveNow)))
        XCTAssertNil(A.details(Self.elevenPlus, totals: S.milestones(live.input), phase: .before, milestones: live,
                               eventID: F.eventID))
        XCTAssertNotNil(A.details(Self.elevenPlus, totals: S.milestones(live.input), phase: .live, milestones: live,
                                  eventID: F.eventID))
    }

    // MARK: - Details: the card's reading and the stored pin (C1–C4)

    /// C1. CONSTRUCTED: before first pitch, 11+'s `published` a Kalshi quote of
    /// 0.48 at 20:58:00Z; no stored pin.
    func testC1BeforeFirstPitchDetailsFirstSayTheCardsQuoteAndThePinStaysUnavailable() throws {
        let markets = try F.markets(editingOption: Self.elevenPlus, setting: Self.quoted(0.48, at: Self.quoteAt))
        let host = F.milestoneHost(F.beforeNow)
        let built = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: markets, host: host))
        let details = try XCTUnwrap(Self.tap(Self.elevenPlus, built, phase: .before))
        let clock = G.clockWords(try XCTUnwrap(Self.quoteAt.asDate), host: host.page)
        let shown = "\(formatProbability(0.48)) · Recorded \(clock) · Kalshi"

        XCTAssertEqual(details.sections.first, MLBOriginal11284.Section(
            title: "11+ runs", fields: [Self.field("Pregame chance", shown)]))
        XCTAssertEqual(Self.value("Pregame chance", in: details), [shown], "said once, as the card's")
        let row = try Self.row(built.input, Self.elevenPlus)
        XCTAssertEqual(row.before?.text, formatProbability(0.48), "the very figure the card drew")
        XCTAssertEqual(built.input.timing?.lines, ["Pregame chance: Recorded \(clock) · Kalshi"],
                       "with the clock its own timing line says")
        XCTAssertEqual(Self.value(A.Words.pinLabel, in: details), ["Unavailable"],
                       "no stored pin: the quote is never put in its place")
        XCTAssertFalse(Self.fields(details).contains { $0.label.hasPrefix("Last recorded") },
                       "the capture's terminal 0.0 leg is not an open quote")
        XCTAssertEqual(Self.value("Venue result", in: details),
                       Self.value("Venue result", in: try Self.plain(markets, Self.elevenPlus)),
                       "the venue's field as the plain original says it; nothing inferred")
    }

    /// C2. CONSTRUCTED: before first pitch, 11+ given a stored pin (0.47,
    /// 20:55:00Z); its `published` stays the retained `result` — no quote.
    func testC2AStoredPinNeverFillsAMissingCardChance() throws {
        let markets = try F.markets(editingOption: Self.elevenPlus, setting: Self.pin)
        let built = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: markets, host: F.milestoneHost(F.beforeNow)))
        let details = try XCTUnwrap(Self.tap(Self.elevenPlus, built, phase: .before))
        let stamp = try XCTUnwrap(SourceAge.preciseStamp(Self.pinAt))

        XCTAssertNil(try Self.row(built.input, Self.elevenPlus).before, "the card shows no pregame chance")
        XCTAssertEqual(details.sections.first, MLBOriginal11284.Section(
            title: "11+ runs", fields: [Self.field("Pregame chance", "Pregame chance unavailable")]),
                       "the card's missing reading stays missing")
        XCTAssertEqual(Self.value(A.Words.pinLabel, in: details), ["\(formatProbability(0.47)) · \(stamp)"],
                       "the stored pin, under its own name and stamp")
        XCTAssertEqual(Self.value("Pregame chance", in: details), ["Pregame chance unavailable"])
    }

    /// C3. CONSTRUCTED: before first pitch, 11+ given BOTH a Kalshi quote of
    /// 0.52 at 20:58:00Z and a stored pin of 0.47 at 20:55:00Z.
    func testC3BothReadingsKeepTheirOwnLabelsFiguresAndStamps() throws {
        let markets = try F.markets(editingOption: Self.elevenPlus,
                                    setting: Self.quoted(0.52, at: Self.quoteAt).merging(Self.pin) { _, new in new })
        let host = F.milestoneHost(F.beforeNow)
        let built = try XCTUnwrap(A.milestones(try F.beforeEvent(), markets: markets, host: host))
        let details = try XCTUnwrap(Self.tap(Self.elevenPlus, built, phase: .before))
        let clock = G.clockWords(try XCTUnwrap(Self.quoteAt.asDate), host: host.page)
        let stamp = try XCTUnwrap(SourceAge.preciseStamp(Self.pinAt))
        let card = "\(formatProbability(0.52)) · Recorded \(clock) · Kalshi"
        let stored = "\(formatProbability(0.47)) · \(stamp)"

        XCTAssertEqual(details.sections.first?.fields, [Self.field("Pregame chance", card)])
        XCTAssertEqual(Self.value(A.Words.pinLabel, in: details), [stored])
        XCTAssertNotEqual(card, stored, "two readings, never called one")
        XCTAssertEqual(Self.value("Pregame chance", in: details), [card], "the pin's figure is never the card's label")
        XCTAssertFalse(Self.fields(details).contains { $0.label.hasPrefix("Last recorded") })
    }

    /// C4. CONSTRUCTED: during play (reader at 21:10:00Z), 11+ given a Kalshi
    /// quote of 0.48 at 21:05:00Z and a stored pin of 0.47 at 20:55:00Z.
    func testC4DuringPlayDetailsSayTheSamePassesPinAndInGameChanceAndEachRowsOwnWords() throws {
        let now = F.start.addingTimeInterval(10 * 60)
        let host = F.milestoneHost(now)
        let markets = try F.markets(editingOption: Self.elevenPlus,
                                    setting: Self.quoted(0.48, at: Self.liveQuoteAt).merging(Self.pin) { _, new in new })
        let built = try XCTUnwrap(A.milestones(try F.liveEvent(), markets: markets, host: host,
                                               selectedMilestoneID: Self.elevenPlus))
        let details = try XCTUnwrap(Self.tap(Self.elevenPlus, built, phase: .live))
        let savedClock = G.clockWords(try XCTUnwrap(Self.pinAt.asDate), host: host.page)
        let recordedClock = G.clockWords(try XCTUnwrap(Self.liveQuoteAt.asDate), host: host.page)
        let stamp = try XCTUnwrap(SourceAge.preciseStamp(Self.pinAt))
        let saved = "\(formatProbability(0.47)) · Saved before first pitch \(savedClock) · Kalshi"
        let recorded = "\(formatProbability(0.48)) · Recorded \(recordedClock) · Kalshi"

        XCTAssertEqual(details.sections.first, MLBOriginal11284.Section(title: "11+ runs", fields: [
            Self.field("Pregame chance", saved), Self.field("Recorded in-game", recorded),
        ]))
        // The same Built: the row and the timing line the card drew say the same readings.
        let row = try Self.row(built.input, Self.elevenPlus)
        XCTAssertEqual(row.before?.text, formatProbability(0.47))
        XCTAssertEqual(built.input.timing?.lines, ["Pregame chance: Saved before first pitch \(savedClock) · Kalshi",
                                                   "Recorded in-game: Recorded \(recordedClock) · Kalshi"])
        XCTAssertEqual(Self.value(A.Words.pinLabel, in: details),
                       ["\(formatProbability(0.47)) · \(stamp)"],
                       "the same stored pin, named apart")
        XCTAssertFalse(Self.fields(details).contains { $0.label.hasPrefix("Last recorded") },
                       "the capture's terminal 0.0 leg is not an open quote")

        // Its neighbours in the same pass: reached, and a slot's own words.
        XCTAssertEqual(Self.tap(Self.tenPlus, built, phase: .live)?.sections.first, MLBOriginal11284.Section(
            title: "10+ runs", fields: [Self.field("Pregame chance", "Pregame chance unavailable"),
                                        Self.field("Actual so far", "Reached so far")]))
        XCTAssertEqual(Self.tap(Self.twelvePlus, built, phase: .live)?.sections.first, MLBOriginal11284.Section(
            title: "12+ runs", fields: [Self.field("Pregame chance", "Pregame chance unavailable"),
                                        Self.field("In-game chance", "In-game chance unavailable")]))
    }
}
