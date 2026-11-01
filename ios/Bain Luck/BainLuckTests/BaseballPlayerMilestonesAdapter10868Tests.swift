import XCTest
@testable import Bain_Luck

/// #10868 — the live MLB player home-run and strikeout milestones
/// (`BaseballPlayerMilestonesAdapter10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// EVERY HR/K INPUT HERE IS CONSTRUCTED. No genuine live HR/K body is retained
/// (M1): the only real MLB bodies are FINAL captures, and their
/// `during_player_props` is null. So the During rows are built below in the
/// producer's `10236.v1` spelling (the route-harness body
/// `game-markets-10236-during-matrix.route.json` is the shape reference; it
/// carries no HR/K rows). Their subjects reuse the retained game's player
/// names. Their ids (90_0xx markets, 900_xxx outcomes), quotes, pins, deltas,
/// states and clocks are all CONSTRUCTED. The page event is
/// `BaseballRetained10868.liveEvent`, itself a CONSTRUCTED live edit of the
/// real final. The reader clock `now` is CONSTRUCTED: 40 minutes after the
/// listed start. Only the retained FINAL bodies are real, and they are used
/// only to show that nothing is built from them.
@MainActor
enum BaseballLivePlayers10868 {
    typealias F = BaseballRetained10868

    /// CONSTRUCTED reader clock: 21:40:00Z, 40 minutes after first pitch.
    static let now = F.start.addingTimeInterval(40 * 60)
    /// CONSTRUCTED quote clock: two minutes before `now`.
    static let quoteAt = "2026-09-30T21:38:00+00:00"
    /// CONSTRUCTED stored-pin clock: before first pitch.
    static let pinAt = "2026-09-30T20:47:36+00:00"

    static let benintendi = "andrew benintendi"
    static let cam = "cam smith"
    static let brown = "hunter brown"

    static var host: BaseballPlayerMilestonesAdapter10868.Host {
        BaseballPlayerMilestonesAdapter10868.Host(now: now, calendar: F.pacific, locale: F.locale)
    }

    /// The producer's question key for an over, at-least row.
    static func key(_ subject: String, _ stat: String, _ count: Int) -> String {
        "s:\(subject)|\(stat)|full_game|ge:\(count)|over"
    }

    /// CONSTRUCTED `current`.
    static func quoted(_ probability: Any, at: Any? = nil, state: String = "quoted") -> [String: Any] {
        ["state": state, "probability": probability, "basis": "single_source", "observed_at": at ?? quoteAt]
    }

    /// CONSTRUCTED `comparison` with a stored pin.
    static func pinned(_ probability: Any, at: Any? = nil, basis: String = "pregame_pin",
                       state: String = "comparable", delta: Any = NSNull()) -> [String: Any] {
        ["state": state, "reason": NSNull(), "delta_points": delta,
         "baseline": ["probability": probability, "observed_at": at ?? pinAt, "basis": basis] as [String: Any]]
    }

    /// CONSTRUCTED `comparison` with no pin.
    static let unpinned: [String: Any] = [
        "state": "unavailable", "reason": "no_pregame_pin", "baseline": NSNull(), "delta_points": NSNull(),
    ]

    /// One CONSTRUCTED During row with one Kalshi contributor whose raw leg is
    /// the current quote.
    static func row(_ subject: String, _ label: String, stat: String = "home_runs", count: Int,
                    current: [String: Any], comparison: Any = NSNull(), market: Int, outcome: Int,
                    period: String = "full_game", kind: String = "count_at_least", side: String = "over",
                    subjectKind: Any = "player", questionKey: String? = nil,
                    result: Any = NSNull()) -> [String: Any] {
        let atLeast = kind == "count_at_least"
        return [
            "question_key": questionKey
                ?? "s:\(subject)|\(stat)|\(period)|\(atLeast ? "ge" : "le"):\(count)|\(side)",
            "subject": ["key": subject, "label": label, "kind": subjectKind] as [String: Any],
            "stat_key": stat,
            "period_key": period,
            "predicate": ["kind": kind, "count": count, "side": side,
                          "label": atLeast ? "\(count)+" : "\(count) or fewer"] as [String: Any],
            "complement_question_key": NSNull(),
            "current": current,
            "contributors": [[
                "source": "kalshi", "market_id": market, "outcome_id": outcome,
                "outcome_name": "\(label): \(count)+", "side": side, "period_key": period,
                "probability": current["probability"] ?? NSNull(),
                "observed_at": current["observed_at"] ?? NSNull(),
            ] as [String: Any]],
            "comparison": comparison,
            "result": result,
            "_market_id": market,
            "_market_ids": [market],
            "contributor_outcome_ids": [outcome],
        ]
    }

    /// The CONSTRUCTED standard rows, in this producer order: Benintendi 1+
    /// (quote 0.12, pin 0.05, +7) and 2+ (quote 0.02, no pin), Cam Smith 1+
    /// (quote 0.09, pin 0.11, −2), Hunter Brown 4+ / 5+ / 6+ strikeouts
    /// (quotes 0.81 / 0.55 / 0.30; pins 0.62 / 0.41 / none).
    static func standardRows() -> [[String: Any]] {
        [
            row(benintendi, "Andrew Benintendi", count: 1, current: quoted(0.12),
                comparison: pinned(0.05, delta: 7.0), market: 90_011, outcome: 900_101),
            row(benintendi, "Andrew Benintendi", count: 2, current: quoted(0.02),
                comparison: unpinned, market: 90_012, outcome: 900_102),
            row(cam, "Cam Smith", count: 1, current: quoted(0.09),
                comparison: pinned(0.11, delta: -2.0), market: 90_021, outcome: 900_201),
            row(brown, "Hunter Brown", stat: "strikeouts", count: 4, current: quoted(0.81),
                comparison: pinned(0.62, delta: 19.0), market: 90_031, outcome: 900_304),
            row(brown, "Hunter Brown", stat: "strikeouts", count: 5, current: quoted(0.55),
                comparison: pinned(0.41, delta: 14.0), market: 90_031, outcome: 900_305),
            row(brown, "Hunter Brown", stat: "strikeouts", count: 6, current: quoted(0.30),
                comparison: unpinned, market: 90_031, outcome: 900_306),
        ]
    }

    static let stats: [[String: Any]] = [
        ["stat_key": "home_runs", "label": "Home Runs", "unit": "home runs", "unit_singular": "home run",
         "period_key": "full_game", "period_label": "Game", "predicate": "count_at_least"],
        ["stat_key": "strikeouts", "label": "Strikeouts", "unit": "strikeouts", "unit_singular": "strikeout",
         "period_key": "full_game", "period_label": "Game", "predicate": "count_at_least"],
    ]

    /// A CONSTRUCTED live `/game-markets` body whose only key of interest is
    /// `during_player_props`.
    static func markets(_ rows: [[String: Any]]? = nil, eventID: Int? = nil,
                        contract: Any = "10236.v1") throws -> GameMarketsResponse {
        let during: [String: Any] = ["contract": contract, "stats": stats, "rows": rows ?? standardRows(),
                                     "coverage": NSNull()]
        let body: [String: Any] = ["event_id": eventID ?? F.eventID, "status": "live", "during_player_props": during]
        return try F.decoder().decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: body))
    }

    /// The adapter on the CONSTRUCTED live event at `now`.
    static func players(_ stat: BaseballPlayerMilestonesAdapter10868.Stat,
                        rows: [[String: Any]]? = nil,
                        held: BaseballPlayerMilestonesAdapter10868.Held = .init()) throws
        -> BaseballPlayerMilestonesAdapter10868.Players? {
        BaseballPlayerMilestonesAdapter10868.players(
            try F.liveEvent(), markets: try markets(rows ?? standardRows()), stat: stat, host: host, held: held)
    }
}

@MainActor
final class BaseballPlayerMilestonesAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias L = BaseballLivePlayers10868
    private typealias A = BaseballPlayerMilestonesAdapter10868
    private typealias G = BaseballGamePageAdapter10868
    private typealias Field = MLBOriginal11284.Field
    private typealias Section = MLBOriginal11284.Section

    private static let b1 = L.key(L.benintendi, "home_runs", 1)
    private static let b2 = L.key(L.benintendi, "home_runs", 2)
    private static let c1 = L.key(L.cam, "home_runs", 1)
    private static let k4 = L.key(L.brown, "strikeouts", 4)
    private static let k5 = L.key(L.brown, "strikeouts", 5)
    private static let k6 = L.key(L.brown, "strikeouts", 6)

    private static func clock(_ stamp: String) -> String {
        G.clockWords(stamp.asDate!, host: L.host.page)
    }

    private static func milestone(_ players: A.Players, _ id: String) throws -> PlayerContributionMilestone10868 {
        try XCTUnwrap(players.input.milestones.first { $0.id == id })
    }

    private static func tap(_ id: String, _ players: A.Players?) -> MLBOriginal11284? {
        A.details(id, drawn: players?.input, phase: .live, players: players, eventID: F.eventID)
    }

    private static func fields(_ original: MLBOriginal11284) -> [Field] { original.sections.flatMap(\.fields) }

    // MARK: - T1 identity

    /// T1. CONSTRUCTED standard rows.
    func testT1EachStatGroupsPlayersByExactSubjectKeyInFirstSeenProducerOrder() throws {
        let hr = try XCTUnwrap(try L.players(.homeRuns))
        XCTAssertEqual(hr.eventID, F.eventID)
        XCTAssertEqual(hr.stat, .homeRuns)
        XCTAssertEqual(hr.input.phase, .during)
        XCTAssertEqual(hr.input.orientation, .columns)
        XCTAssertEqual(hr.input.eyebrow, "PLAYER HOME RUNS")
        XCTAssertEqual(hr.input.title, "Pregame and current home-run chances")
        XCTAssertNil(hr.input.definition)
        XCTAssertEqual(hr.input.chartTitle, "Chances · at least this many")
        XCTAssertEqual(hr.input.ticks.map(\.text), ["0%", "50%", "100%"])
        XCTAssertEqual(hr.input.chooser?.title, "Choose player · 2")
        XCTAssertEqual(hr.input.chooser?.choices.map(\.id), [L.benintendi, L.cam])
        XCTAssertEqual(hr.input.chooser?.choices.map(\.name), ["Andrew Benintendi", "Cam Smith"])
        XCTAssertEqual(hr.input.chooser?.choices.map(\.detail), [nil, nil], "no team is typed on a row")
        XCTAssertEqual(hr.input.player?.id, L.benintendi, "the first-seen player")
        XCTAssertEqual(hr.input.player?.name, "Andrew Benintendi")
        XCTAssertNil(hr.input.player?.team)
        XCTAssertEqual(hr.input.milestones.map(\.id), [Self.b1, Self.b2])
        XCTAssertEqual(hr.input.milestones.map(\.target), ["1+", "2+"])
        XCTAssertEqual(hr.input.milestones.map(\.title), ["1+ home run", "2+ home runs"])
        XCTAssertEqual(hr.origins.map(\.milestoneID), [Self.b1, Self.b2, Self.c1])
        XCTAssertEqual(hr.origins.map(\.playerKey), [L.benintendi, L.benintendi, L.cam])

        let k = try XCTUnwrap(try L.players(.strikeouts))
        XCTAssertEqual(k.input.player?.id, L.brown)
        XCTAssertNil(k.input.chooser, "one player: no chooser")
        XCTAssertEqual(k.input.milestones.map(\.id), [Self.k4, Self.k5, Self.k6])
        XCTAssertEqual(k.input.milestones.map(\.title), ["4+ strikeouts", "5+ strikeouts", "6+ strikeouts"])

        // CONSTRUCTED: the producer order reversed; and a second subject with the same label.
        let reversed = try XCTUnwrap(try L.players(.homeRuns, rows: Array(L.standardRows().reversed())))
        XCTAssertEqual(reversed.input.chooser?.choices.map(\.id), [L.cam, L.benintendi])
        XCTAssertEqual(reversed.input.milestones.map(\.id), [Self.c1], "Cam Smith is now first seen")
        let twin = L.row("andrew benintendi jr", "Andrew Benintendi", count: 1, current: L.quoted(0.04),
                         market: 90_013, outcome: 900_103)
        let twins = try XCTUnwrap(try L.players(.homeRuns, rows: L.standardRows() + [twin]))
        XCTAssertEqual(twins.input.chooser?.choices.map(\.id), [L.benintendi, L.cam, "andrew benintendi jr"],
                       "one label, two keys: two players, never merged by name")
    }

    /// T1. CONSTRUCTED refused rows beside the standard rows.
    func testT1OnlyFullGamePlayerAtLeastOverRowsOfTheStatAreAdmittedAndADuplicatedKeyIsDropped() throws {
        let refused = [
            L.row("houston astros", "Houston Astros", count: 1, current: L.quoted(0.6), market: 90_901,
                  outcome: 900_901, subjectKind: "team"),
            L.row("no kind", "No Kind", count: 1, current: L.quoted(0.1), market: 90_902, outcome: 900_902,
                  subjectKind: NSNull()),
            L.row(L.benintendi, "Andrew Benintendi", count: 0, current: L.quoted(0.88), market: 90_903,
                  outcome: 900_903, kind: "count_at_most", side: "under"),
            L.row(L.benintendi, "Andrew Benintendi", count: 1, current: L.quoted(0.07), market: 90_904,
                  outcome: 900_904, period: "first_5_innings"),
            L.row(L.benintendi, "Andrew Benintendi", stat: "hits", count: 1, current: L.quoted(0.7),
                  market: 90_905, outcome: 900_905),
            // The same question twice: an ambiguous origin, dropped entirely.
            L.row("jose abreu", "Jose Abreu", count: 1, current: L.quoted(0.1), market: 90_906, outcome: 900_906),
            L.row("jose abreu", "Jose Abreu", count: 1, current: L.quoted(0.2), market: 90_907, outcome: 900_907),
        ]
        let hr = try XCTUnwrap(try L.players(.homeRuns, rows: L.standardRows() + refused))
        XCTAssertEqual(hr.input.chooser?.choices.map(\.id), [L.benintendi, L.cam])
        XCTAssertEqual(hr.origins.map(\.milestoneID), [Self.b1, Self.b2, Self.c1])
        XCTAssertEqual(A.rows(try XCTUnwrap(try L.markets(L.standardRows() + refused).duringPlayerProps),
                              stat: .homeRuns).map(\.questionKey), [Self.b1, Self.b2, Self.c1])

        // CONSTRUCTED: Benintendi 1+ carried twice. Both go; 2+ stays.
        let doubled = L.standardRows() + [L.standardRows()[0]]
        let dropped = try XCTUnwrap(try L.players(.homeRuns, rows: doubled))
        XCTAssertEqual(dropped.input.milestones.map(\.id), [Self.b2])
        XCTAssertNil(Self.tap(Self.b1, dropped))
        XCTAssertNotNil(Self.tap(Self.b2, dropped))
    }

    // MARK: - T2 own body · T3 lifecycle

    /// T2. CONSTRUCTED bodies, and the RETAINED final body on the CONSTRUCTED live event.
    func testT2AnotherEventsBodyAnUnknownContractOrNoDuringRowsBuildsNoCard() throws {
        let host = L.host
        let event = try F.liveEvent()
        XCTAssertNil(A.players(event, markets: try L.markets(eventID: 1), stat: .homeRuns, host: host))
        XCTAssertNil(A.players(event, markets: try L.markets(contract: "10236.v2"), stat: .homeRuns, host: host))
        XCTAssertNil(A.players(event, markets: try L.markets(contract: NSNull()), stat: .homeRuns, host: host))
        XCTAssertNil(A.players(event, markets: try L.markets([]), stat: .homeRuns, host: host))
        XCTAssertNil(A.players(event, markets: nil, stat: .strikeouts, host: host))
        XCTAssertNil(A.players(event, markets: try F.markets(), stat: .homeRuns, host: host),
                     "the real final serves during_player_props null; nothing is built from its raw rows")
        XCTAssertNil(A.players(event, markets: try F.markets(), stat: .strikeouts, host: host))
    }

    /// T3. CONSTRUCTED rows on the CONSTRUCTED before event and the RETAINED final event.
    func testT3BeforeFirstPitchAndAfterTheFinalNoLiveCardIsBuilt() throws {
        let markets = try L.markets()
        XCTAssertNil(A.players(try F.beforeEvent(), markets: markets, stat: .homeRuns,
                               host: A.Host(now: F.beforeNow, calendar: F.pacific, locale: F.locale)),
                     "G1: no typed pregame player channel, so no pregame card is faked")
        XCTAssertNil(A.players(try F.finalEvent(), markets: markets, stat: .strikeouts,
                               host: A.Host(now: F.finalNow, calendar: F.pacific, locale: F.locale)))
        XCTAssertNotNil(A.players(try F.liveEvent(), markets: markets, stat: .strikeouts, host: L.host))
    }

    // MARK: - T4 pregame and current, each with its own clock

    /// T4. CONSTRUCTED pins.
    func testT4ThePregameChanceIsTheComparableStoredPinWithItsOwnClock() throws {
        let hr = try XCTUnwrap(try L.players(.homeRuns))
        XCTAssertEqual(try Self.milestone(hr, Self.b1).before, PlayerContributionObservation10868(
            probability: 0.05, text: formatProbability(0.05),
            accessibilityDetail: "Saved before first pitch \(Self.clock(L.pinAt))"))
        let unpinned = try Self.milestone(hr, Self.b2)
        XCTAssertNil(unpinned.before)
        XCTAssertEqual(unpinned.beforeMissing, "Pregame chance unavailable")

        // CONSTRUCTED: 1+'s comparison varied one key at a time. None is a pregame chance.
        let refused: [[String: Any]] = [
            L.pinned(0.05, basis: "opening_line", delta: 7.0),
            L.pinned(0.05, at: NSNull(), delta: 7.0),
            L.pinned(0.05, at: "not a time", delta: 7.0),
            L.pinned(0.05, state: "unavailable"),
            L.pinned(NSNull()),
            L.pinned(1.5),
        ]
        for comparison in refused {
            var rows = L.standardRows()
            rows[0]["comparison"] = comparison
            XCTAssertNil(try Self.milestone(try XCTUnwrap(try L.players(.homeRuns, rows: rows)), Self.b1).before,
                         "\(comparison)")
        }
    }

    /// T4. CONSTRUCTED quotes.
    func testT4TheCurrentChanceIsTheDuringRuleAloneWithItsOwnClockAndTheServersMovement() throws {
        let hr = try XCTUnwrap(try L.players(.homeRuns))
        let recorded = "Recorded \(Self.clock(L.quoteAt)) · Kalshi"
        XCTAssertEqual(try Self.milestone(hr, Self.b1).current, .recorded(PlayerContributionObservation10868(
            probability: 0.12, text: formatProbability(0.12), accessibilityDetail: recorded), movement: "+7%"))
        XCTAssertEqual(try Self.milestone(hr, Self.b2).current, .recorded(PlayerContributionObservation10868(
            probability: 0.02, text: formatProbability(0.02), accessibilityDetail: recorded), movement: nil),
                       "no comparable delta, no movement")
        let cam = try XCTUnwrap(try L.players(.homeRuns, held: .init(player: L.cam)))
        guard case .recorded(_, let movement) = try Self.milestone(cam, Self.c1).current else {
            return XCTFail("recorded")
        }
        XCTAssertEqual(movement, "\u{2212}2%")

        // CONSTRUCTED: a quote the server does not call quoted, or out of range, is no chance.
        for current in [L.quoted(0.3, state: "unavailable"), L.quoted(1.2), L.quoted(NSNull())] {
            var rows = L.standardRows()
            rows[0]["current"] = current
            XCTAssertEqual(try Self.milestone(try XCTUnwrap(try L.players(.homeRuns, rows: rows)), Self.b1).current,
                           .unavailable("In-game chance unavailable"), "\(current)")
        }
    }

    /// D4. CONSTRUCTED endpoint quotes.
    func testD4AQualifiedZeroOrOneIsAChanceOnTheCardAndInDetails() throws {
        for value in [0.0, 1.0] {
            var rows = L.standardRows()
            rows[0] = L.row(L.benintendi, "Andrew Benintendi", count: 1, current: L.quoted(value),
                            comparison: L.pinned(0.05), market: 90_011, outcome: 900_101)
            let hr = try XCTUnwrap(try L.players(.homeRuns, rows: rows))
            let card = try Self.milestone(hr, Self.b1)
            let shown = PlayerContributionObservation10868(
                probability: value, text: formatProbability(value),
                accessibilityDetail: "Recorded \(Self.clock(L.quoteAt)) · Kalshi")
            XCTAssertEqual(card.current, .recorded(shown, movement: nil), "\(value)")
            XCTAssertNil(card.progress)
            XCTAssertEqual(hr.input.player?.actual, .unavailable("Home run count unavailable"),
                           "an endpoint quote is not a count")
            let details = try XCTUnwrap(Self.tap(Self.b1, hr))
            XCTAssertEqual(details.sections.first?.fields[1],
                           Field(label: "Recorded in-game", value: "\(shown.text) · \(shown.accessibilityDetail)"))
            // The raw contributor leg keeps the final reader's strict helper, unchanged.
            XCTAssertEqual(details.sections[2].fields, [Field(label: "Kalshi · Andrew Benintendi: 1+",
                                                               value: "Unavailable")])
        }
    }

    /// D4. CONSTRUCTED undated quotes.
    func testD4AnUndatedQualifiedQuoteShowsWithTimeUnavailableAndNoAgeClaim() throws {
        for stamp in [NSNull(), "not a time"] as [Any] {
            var rows = L.standardRows()
            rows[0]["current"] = L.quoted(0.12, at: stamp)
            let hr = try XCTUnwrap(try L.players(.homeRuns, rows: rows))
            let card = try Self.milestone(hr, Self.b1)
            let shown = PlayerContributionObservation10868(
                probability: 0.12, text: formatProbability(0.12),
                accessibilityDetail: "Recorded · time unavailable · Kalshi")
            XCTAssertEqual(card.current, .recorded(shown, movement: "+7%"), "\(stamp)")
            XCTAssertEqual(hr.input.timing?.lines[1], "Recorded in-game: Recorded · time unavailable · Kalshi")
            XCTAssertEqual(try XCTUnwrap(Self.tap(Self.b1, hr)).sections.first?.fields[1].value,
                           "\(formatProbability(0.12)) · Recorded · time unavailable · Kalshi")
        }
    }

    /// D4. CONSTRUCTED stale and boundary clocks.
    func testD4ADatedStaleQuoteIsWithheldKeepsItsLastQuoteInDetailsAndAddsNoMovement() throws {
        var rows = L.standardRows()
        rows[0]["current"] = L.quoted(0.12, at: "2026-09-30T21:05:00+00:00")   // 35 minutes old
        let stale = try XCTUnwrap(try L.players(.homeRuns, rows: rows))
        XCTAssertEqual(try Self.milestone(stale, Self.b1).current, .withheld("No recent probability update"))
        let details = try XCTUnwrap(Self.tap(Self.b1, stale))
        XCTAssertEqual(details.sections.first?.fields, [
            Field(label: "Pregame chance",
                  value: "\(formatProbability(0.05)) · Saved before first pitch \(Self.clock(L.pinAt))"),
            Field(label: "In-game chance", value: "No recent probability update"),
            Field(label: "Last recorded in-game", value: "\(formatProbability(0.12)) · Recorded "
                  + "\(Self.clock("2026-09-30T21:05:00+00:00")) · Kalshi"),
            Field(label: "Count so far", value: "Home run count unavailable"),
        ], "inspectable, with no movement")

        // Exactly 30 minutes old is still current (strict `>`).
        rows[0]["current"] = L.quoted(0.12, at: "2026-09-30T21:10:00+00:00")
        let boundary = try XCTUnwrap(try L.players(.homeRuns, rows: rows))
        guard case .recorded = try Self.milestone(boundary, Self.b1).current else {
            return XCTFail("current at the boundary")
        }
    }

    // MARK: - T5 no count · T6 result separation

    /// T5/T6. CONSTRUCTED `actual_only` row carrying a served grade.
    func testT5T6NoCountProgressReachedOrResultIsEverInferredAndStrikeoutsStayGeneric() throws {
        var rows = L.standardRows()
        rows[0]["current"] = L.quoted(NSNull(), state: "actual_only")
        rows[0]["result"] = ["actual": 2, "hit": true, "is_winner": true,
                             "resolution_source": "api_settlement"] as [String: Any]
        let hr = try XCTUnwrap(try L.players(.homeRuns, rows: rows))
        let graded = try Self.milestone(hr, Self.b1)
        XCTAssertEqual(graded.current, .unavailable("In-game chance unavailable"))
        XCTAssertNil(graded.progress)
        XCTAssertEqual(graded.result, .unconfirmed("Result unavailable"))
        XCTAssertEqual(hr.input.player?.actual, .unavailable("Home run count unavailable"))
        let details = try XCTUnwrap(Self.tap(Self.b1, hr))
        for field in Self.fields(details) {
            XCTAssertFalse(["Won", "Lost", "Reached so far", "2"].contains(field.value), field.label)
            XCTAssertFalse(["Official final", "Final count", "Venue settlement"].contains(field.label))
        }

        let k = try XCTUnwrap(try L.players(.strikeouts))
        XCTAssertEqual(k.input.player?.actual, .unavailable("Strikeout count unavailable"))
        XCTAssertFalse(k.input.milestones.contains { if case .reached = $0.current { true } else { false } })
        let words = [k.input.eyebrow, k.input.title, k.input.definition, k.input.chartTitle].compactMap { $0 }
            + k.input.milestones.map(\.title) + k.origins.flatMap { Self.fields($0.original).map(\.label) }
        XCTAssertFalse(words.contains { $0.lowercased().contains("pitching") }, "generic strikeouts stay generic")
    }

    // MARK: - T7 Details

    /// T7. CONSTRUCTED standard rows.
    func testT7DetailsAreTheExactOriginalOfTheSamePassAndMirrorTheCard() throws {
        let hr = try XCTUnwrap(try L.players(.homeRuns))
        let card = try Self.milestone(hr, Self.b1)
        let details = try XCTUnwrap(Self.tap(Self.b1, hr))
        XCTAssertEqual(details, hr.origins.first { $0.milestoneID == Self.b1 }?.original)
        XCTAssertEqual(details.id, "mlb-o:15321836:during:\(Self.b1)")
        XCTAssertEqual(details.title, "Andrew Benintendi · 1+ home run")

        let before = try XCTUnwrap(card.before)
        guard case .recorded(let current, let movement) = card.current else { return XCTFail("recorded") }
        let change = try XCTUnwrap(movement)
        XCTAssertEqual(details.sections[0], Section(title: "1+ home run", fields: [
            Field(label: "Pregame chance", value: "\(before.text) · \(before.accessibilityDetail)"),
            Field(label: "Recorded in-game", value: "\(current.text) · \(current.accessibilityDetail)"),
            Field(label: "Change since pregame", value: change),
            Field(label: "Count so far", value: "Home run count unavailable"),
        ]), "first, exactly what the card shows")
        let pinStamp = try XCTUnwrap(SourceAge.preciseStamp(L.pinAt))
        let quoteStamp = try XCTUnwrap(SourceAge.preciseStamp(L.quoteAt))
        XCTAssertEqual(details.sections[1], Section(title: nil, fields: [
            Field(label: "Recorded pregame reference", value: "\(formatProbability(0.05)) · \(pinStamp)")]))
        XCTAssertEqual(details.sections[2], Section(title: "Sources", fields: [
            Field(label: "Kalshi · Andrew Benintendi: 1+", value: "\(formatProbability(0.12)) · \(quoteStamp)")]))
        XCTAssertEqual(details.sections[3], Section(title: nil, fields: [
            Field(label: "Market", value: "90011"), Field(label: "Outcome", value: "900101")]))
        XCTAssertEqual(hr.input.timing, PlayerContributionTiming10868(
            milestoneID: Self.b1, title: "Andrew Benintendi 1+ home run · chance timing",
            lines: ["Pregame chance: Saved before first pitch \(Self.clock(L.pinAt))",
                    "Recorded in-game: Recorded \(Self.clock(L.quoteAt)) · Kalshi",
                    "Count so far: Home run count unavailable"]))

        let unpinned = try XCTUnwrap(Self.tap(Self.b2, hr))
        XCTAssertEqual(unpinned.sections[0].fields.first, Field(label: "Pregame chance",
                                                                value: "Pregame chance unavailable"))
        XCTAssertEqual(unpinned.sections[1].fields, [Field(label: "Recorded pregame reference", value: "Unavailable")])
    }

    /// T7. CONSTRUCTED passes and values.
    func testT7UnknownForeignFinalOtherPlayerStaleDuplicateAndRemovedTapsOpenNothing() throws {
        let hr = try XCTUnwrap(try L.players(.homeRuns))
        let k = try XCTUnwrap(try L.players(.strikeouts))
        XCTAssertNil(Self.tap("unknown", hr))
        XCTAssertNil(Self.tap("mlb-o:15321836:after:\(Self.b1)", hr), "a final namespace")
        XCTAssertNil(Self.tap(Self.c1, hr), "another player's milestone is not drawn")
        XCTAssertNil(A.details(Self.b1, drawn: hr.input, phase: .final, players: hr, eventID: F.eventID))
        XCTAssertNil(A.details(Self.b1, drawn: hr.input, phase: .before, players: hr, eventID: F.eventID))
        XCTAssertNil(A.details(Self.b1, drawn: hr.input, phase: .live, players: hr, eventID: 1))
        XCTAssertNil(A.details(Self.b1, drawn: nil, phase: .live, players: hr, eventID: F.eventID))
        XCTAssertNil(A.details(Self.b1, drawn: hr.input, phase: .live, players: nil, eventID: F.eventID))
        XCTAssertNil(A.details(Self.b1, drawn: hr.input, phase: .live, players: k, eventID: F.eventID))

        // A card drawn from one pass never resolves against another pass's originals.
        var moved = L.standardRows()
        moved[0]["current"] = L.quoted(0.2)
        let next = try XCTUnwrap(try L.players(.homeRuns, rows: moved))
        XCTAssertNil(A.details(Self.b1, drawn: hr.input, phase: .live, players: next, eventID: F.eventID))
        XCTAssertNil(A.details(Self.b1, drawn: next.input, phase: .live, players: hr, eventID: F.eventID))

        // CONSTRUCTED values: an original kept twice.
        let origin = try XCTUnwrap(hr.origins.first)
        let twice = A.Players(eventID: F.eventID, stat: .homeRuns, input: hr.input, origins: hr.origins + [origin])
        XCTAssertNil(Self.tap(Self.b1, twice))
        XCTAssertNotNil(Self.tap(Self.b2, twice), "only the repeated id refuses")

        // CONSTRUCTED: 1+ removed from the next body.
        let removed = try XCTUnwrap(try L.players(.homeRuns, rows: Array(L.standardRows().dropFirst())))
        XCTAssertNil(Self.tap(Self.b1, removed))
        XCTAssertNotNil(Self.tap(Self.b2, removed))
    }

    /// T7. CONSTRUCTED: 1+ re-keyed with its option and quote unchanged.
    func testT7AReKeyedCurrentQuestionOpensItsFreshOriginalAndTheOldResultKeepsItsOwn() throws {
        let fresh = "s:andrew benintendi|home_runs|full_game|ge:1|over#rekeyed"
        let old = try XCTUnwrap(try L.players(.homeRuns))
        let opened = try XCTUnwrap(Self.tap(Self.b1, old))
        var rows = L.standardRows()
        rows[0]["question_key"] = fresh
        let new = try XCTUnwrap(try L.players(.homeRuns, rows: rows))

        let details = try XCTUnwrap(Self.tap(fresh, new), "a valid current milestone opens")
        XCTAssertEqual(details.id, "mlb-o:15321836:during:\(fresh)")
        XCTAssertNotEqual(details.id, opened.id, "the former original is not carried over")
        XCTAssertEqual(details.sections.first, opened.sections.first, "same option, same quote, same reading")
        XCTAssertNil(Self.tap(Self.b1, new))
        XCTAssertEqual(Self.tap(Self.b1, old), opened, "the old result keeps its own original")

        let held = try XCTUnwrap(try L.players(.homeRuns, rows: rows, held: .init(milestone: Self.b1)))
        XCTAssertEqual(held.input.selectedMilestoneID, Self.b1, "a held id is never substituted")
        XCTAssertEqual(held.input.selectionNotice, "Selected milestone unavailable.")
    }

    // MARK: - T9 selection

    /// T9. CONSTRUCTED standard rows.
    func testT9HeldIdsPassThroughDefaultsAreWithinThePlayerAndARemovedIdIsNeverSubstituted() throws {
        let hr = try XCTUnwrap(try L.players(.homeRuns))
        XCTAssertEqual(hr.input.selectedMilestoneID, PlayerPropsFamily.defaultTarget(
            probabilities: hr.input.milestones.map { $0.before?.probability }).map { hr.input.milestones[$0].id })
        let k = try XCTUnwrap(try L.players(.strikeouts))
        XCTAssertEqual(k.input.selectedMilestoneID, PlayerPropsFamily.defaultTarget(
            probabilities: k.input.milestones.map { $0.before?.probability }).map { k.input.milestones[$0].id })

        let cam = try XCTUnwrap(try L.players(.homeRuns, held: .init(player: L.cam)))
        XCTAssertEqual(cam.input.player?.id, L.cam)
        XCTAssertEqual(cam.input.selectedMilestoneID, Self.c1, "the default within the shown player only")
        XCTAssertEqual(cam.input.timing?.title, "Cam Smith 1+ home run · chance timing")
        XCTAssertEqual(cam.origins, hr.origins, "every player's originals, whichever is shown")

        let ghost = try XCTUnwrap(try L.players(.homeRuns, held: .init(player: "ghost")))
        XCTAssertNil(ghost.input.player)
        XCTAssertNil(ghost.input.selectedMilestoneID)
        XCTAssertNil(ghost.input.timing)
        XCTAssertEqual(ghost.input.selectionNotice, "Selected player unavailable.")
        XCTAssertEqual(ghost.input.chooser?.choices.map(\.id), [L.benintendi, L.cam], "the choices stay")
        XCTAssertNil(Self.tap(Self.b1, ghost))

        let gone = try XCTUnwrap(try L.players(.homeRuns, held: .init(player: L.benintendi, milestone: "gone")))
        XCTAssertEqual(gone.input.selection, .missing("gone"))
        XCTAssertEqual(gone.input.selectionNotice, "Selected milestone unavailable.")
        XCTAssertNil(gone.input.timing)
    }
}
