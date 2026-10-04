import XCTest
@testable import Bain_Luck

/// #10237 — the After player grid: decode, layout, the final count once per
/// player, the server's comparison drawn verbatim, the page's phase and the
/// #9524 price fences, driven from the producer's own route output.
///
/// FIXTURE: `Fixtures/game-markets-10237-after.route.json` is the body
/// `events_route._build_game_markets` returned at master `56ea1dcd96` from the
/// producer test's route harness (`tests/test_prop_expectation_actual_10237.py::_page`,
/// a finished Yankees–Red Sox game on a mocked session): Kalshi's Home Runs
/// ladder (Rice 1+ pinned 0.31, Rice 2+ pinned 0.02, Judge 1+ with no pin) and
/// Polymarket's `Ben Rice: Home Runs O/U 1.5` pair (Over pinned 0.04). ESPN's
/// final box has Rice at 2 home runs and no Judge. It is the real serializer's
/// spelling, not production values; cases that need another state edit one
/// actual or question of that body and say so.
@MainActor
final class PropExpectationActual10237Tests: XCTestCase {
    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10237-after.route.json")

    private let rice1 = "s:ben rice|home_runs|full_game|ge:1|over"
    private let rice2 = "s:ben rice|home_runs|full_game|ge:2|over"
    private let judge1 = "s:aaron judge|home_runs|full_game|ge:1|over"
    private let riceHR = "s:ben rice|home_runs|full_game"
    private let judgeHR = "s:aaron judge|home_runs|full_game"

    private func specimen() throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
    }

    private func decode(_ dict: [String: Any]) throws -> GameMarketsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func editing(_ list: String, _ key: String, _ keyField: String,
                         _ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        var dict = try specimen()
        var after = try XCTUnwrap(dict["after_player_props"] as? [String: Any])
        var rows = try XCTUnwrap(after[list] as? [[String: Any]])
        let index = try XCTUnwrap(rows.firstIndex { $0[keyField] as? String == key })
        edit(&rows[index])
        after[list] = rows
        dict["after_player_props"] = after
        return dict
    }

    private func editingActual(_ key: String, _ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        try editing("actuals", key, "actual_key", edit)
    }

    private func editingQuestion(_ key: String, _ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        try editing("questions", key, "question_key", edit)
    }

    private func props(_ dict: [String: Any]) throws -> AfterPlayerProps {
        try XCTUnwrap(try decode(dict).afterPlayerProps)
    }

    private func question(_ props: AfterPlayerProps, _ key: String) throws -> AfterPropQuestion {
        try XCTUnwrap(props.questions.first { $0.questionKey == key })
    }

    // MARK: - Decode

    func testTheRouteBodyDecodesEveryQuestionAndActual() throws {
        let response = try decode(try specimen())
        XCTAssertNil(response.duringPlayerProps, "the server sends During null beside a non-null After")
        let after = try XCTUnwrap(response.afterPlayerProps)
        XCTAssertTrue(after.isSupported)
        XCTAssertEqual(after.stats.map(\.statKey), ["home_runs"])
        XCTAssertEqual(after.stats.first?.unitSingular, "home run")
        XCTAssertEqual(after.stats.first?.unitPlural, "home runs")
        XCTAssertEqual(after.questions.map(\.questionKey), [judge1, rice1, rice2], "server order kept")
        XCTAssertEqual(after.actuals.map(\.actualKey), [judgeHR, riceHR])
        XCTAssertEqual(after.coverage?.final, 1)
        XCTAssertEqual(after.coverage?.unknown, 1)

        let blend = try question(after, rice2)
        XCTAssertEqual(blend.expectation.basis, "blend_mean")
        XCTAssertEqual(try XCTUnwrap(blend.expectation.savedProbability), 0.03, accuracy: 1e-9)
        XCTAssertEqual(blend.expectation.contributors.map(\.source), ["kalshi", "polymarket"])
        XCTAssertEqual(blend.contributorOutcomeIds, [5012, 5021])
        XCTAssertEqual(blend._marketIds, [501, 502])
        XCTAssertEqual(blend.comparison?.state, "reached")
        XCTAssertEqual(blend.venueGrade?.resolutionSource, "kalshi_settled")

        let rice = try XCTUnwrap(after.actual(for: blend))
        XCTAssertEqual(rice.finalCount, 2)
        XCTAssertEqual(rice.sourceLabel, "ESPN final statistic")
        XCTAssertNotNil(rice.recordVersion)
        let judge = try XCTUnwrap(after.actual(for: try question(after, judge1)))
        XCTAssertEqual(judge.state, "unknown")
        XCTAssertEqual(judge.reason, "player_not_in_box")
        XCTAssertNil(judge.finalCount, "a player missing from the box is never 0 and never DNP")
    }

    func testAbsentNullUnreadableAndUnknownContractAllKeepThePreviousCard() throws {
        var absent = try specimen()
        absent.removeValue(forKey: "after_player_props")
        XCTAssertNil(try decode(absent).afterPlayerProps)

        var null = try specimen()
        null["after_player_props"] = NSNull()
        XCTAssertNil(try decode(null).afterPlayerProps)

        // A shape the app cannot read drops only this key, never the page.
        var broken = try specimen()
        broken["after_player_props"] = ["contract": "10237.v1", "questions": "nope"]
        let page = try decode(broken)
        XCTAssertNil(page.afterPlayerProps)
        XCTAssertEqual(page.playerProps?.count, 5, "control: the rest of the page still decodes")

        var future = try specimen()
        var body = try XCTUnwrap(future["after_player_props"] as? [String: Any])
        body["contract"] = "10237.v2"
        future["after_player_props"] = body
        let decoded = try decode(future)
        XCTAssertNotNil(decoded.afterPlayerProps, "control: it decodes")
        XCTAssertNil(AfterPropsMatrixLayout.drawable(decoded.afterPlayerProps), "an unknown contract is not drawn")
        XCTAssertNotNil(AfterPropsMatrixLayout.drawable(try decode(try specimen()).afterPlayerProps))
    }

    // MARK: - Layout

    func testTheGridHasEveryThresholdColumnAndTheFinalCountOncePerPlayer() throws {
        let after = try props(try specimen())
        let grid = try XCTUnwrap(AfterPropsMatrixLayout.grid(after, statKey: "home_runs"))
        XCTAssertEqual(grid.columns, [1, 2])
        XCTAssertEqual(grid.players.map(\.label), ["Aaron Judge", "Ben Rice"], "server order, never re-ranked")
        XCTAssertEqual(grid.questionCount, 3)
        let rice = try XCTUnwrap(grid.players.last)
        XCTAssertEqual(rice.actual?.actualKey, riceHR)
        XCTAssertEqual(Set(rice.cells.keys), [1, 2])
        let judge = try XCTUnwrap(grid.players.first)
        XCTAssertNil(judge.cells[2], "not offered: an empty slot, never a borrowed question")
        // One actual per player row, never one per threshold.
        let keys = grid.players.compactMap { $0.actual?.actualKey }
        XCTAssertEqual(keys, [judgeHR, riceHR])
        XCTAssertEqual(Set(keys).count, keys.count)
        XCTAssertNil(AfterPropsMatrixLayout.grid(after, statKey: "hits"), "a stat with no questions draws nothing")
    }

    func testAnActualIsOnlyEverTheOneTheQuestionNames() throws {
        // The Rice actual's subject is edited to Judge's: neither question may
        // borrow it, and the Rice cells read unknown.
        let dict = try editingActual(riceHR) { $0["subject"] = ["key": "aaron judge", "label": "Aaron Judge", "kind": "player"] }
        let after = try props(dict)
        let rice2Q = try question(after, rice2)
        XCTAssertNil(after.actual(for: rice2Q))
        XCTAssertEqual(PropExpectationActualDisplay.mark(rice2Q, actual: after.actual(for: rice2Q)), .unknown)
        XCTAssertEqual(PropExpectationActualDisplay.mark(rice2Q, actual: after.actuals.first { $0.actualKey == judgeHR }),
                       .unknown, "an actual under another key is never this question's")
    }

    // MARK: - Words (Root's helper, Native's contract)

    func testTheComparisonIsTheServersWordNeverACountAgainstTheThreshold() throws {
        let after = try props(try specimen())
        let rice1Q = try question(after, rice1)
        let rice2Q = try question(after, rice2)
        XCTAssertEqual(PropExpectationActualDisplay.mark(rice2Q, actual: after.actual(for: rice2Q)), .reached)
        XCTAssertEqual(PropExpectationActualDisplay.mark(rice1Q, actual: after.actual(for: rice1Q)), .reached)

        // The count (2) still clears 2+, but the server says below: below it is.
        let edited = try props(try editingQuestion(rice2) { $0["comparison"] = ["state": "below", "reason": NSNull()] })
        let q = try question(edited, rice2)
        XCTAssertEqual(PropExpectationActualDisplay.mark(q, actual: edited.actual(for: q)), .below)
        XCTAssertEqual(PropExpectationActualDisplay.markText(.below), "Below")

        for state in ["unknown", "graded", ""] {
            let other = try props(try editingQuestion(rice2) { $0["comparison"] = ["state": state, "reason": NSNull()] })
            let oq = try question(other, rice2)
            XCTAssertEqual(PropExpectationActualDisplay.mark(oq, actual: other.actual(for: oq)), .unknown, state)
        }
        let none = try props(try editingQuestion(rice2) { $0["comparison"] = NSNull() })
        let nq = try question(none, rice2)
        XCTAssertEqual(PropExpectationActualDisplay.mark(nq, actual: none.actual(for: nq)), .unknown)
    }

    func testAVerifiedFinalZeroIsARealZeroAndUnitsFollowTheCount() throws {
        let stat = try XCTUnwrap(try props(try specimen()).stat("home_runs"))
        let zero = try props(try editingActual(riceHR) { $0["value"] = 0 })
        let shown = PropExpectationActualDisplay.actual(zero.actuals.first { $0.actualKey == riceHR }, stat: stat)
        XCTAssertEqual(shown.countText, "0 home runs")
        XCTAssertTrue(shown.isFinal)
        let one = try props(try editingActual(riceHR) { $0["value"] = 1 })
        XCTAssertEqual(PropExpectationActualDisplay.actual(one.actuals.first { $0.actualKey == riceHR }, stat: stat).countText,
                       "1 home run")
        let two = try props(try specimen())
        let real = PropExpectationActualDisplay.actual(two.actuals.first { $0.actualKey == riceHR }, stat: stat)
        XCTAssertEqual(real.countText, "2 home runs")
        XCTAssertEqual(real.sourceLabel, "ESPN final statistic")
    }

    func testPendingAndUnknownActualsShowNoCountAndNoResult() throws {
        let stat = try XCTUnwrap(try props(try specimen()).stat("home_runs"))
        // Pending with a stale value and a stale "reached" left on the question:
        // neither may surface.
        var dict = try editingActual(riceHR) { $0["state"] = "pending"; $0["reason"] = "provider_not_final" }
        let after = try props(dict)
        let pending = try XCTUnwrap(after.actuals.first { $0.actualKey == riceHR })
        XCTAssertNil(pending.finalCount)
        let shown = PropExpectationActualDisplay.actual(pending, stat: stat)
        XCTAssertNil(shown.countText)
        XCTAssertNil(shown.sourceLabel)
        XCTAssertFalse(shown.isFinal)
        XCTAssertEqual(shown.stateText, "Pending")
        let q = try question(after, rice2)
        XCTAssertEqual(PropExpectationActualDisplay.mark(q, actual: after.actual(for: q)), .unknown)

        dict = try specimen()
        let judge = try props(dict).actuals.first { $0.actualKey == judgeHR }
        let unknown = PropExpectationActualDisplay.actual(judge, stat: stat)
        XCTAssertNil(unknown.countText)
        XCTAssertEqual(unknown.stateText, "Unknown")
        XCTAssertFalse(unknown.stateText.localizedCaseInsensitiveContains("DNP"))
        XCTAssertFalse(unknown.stateText.contains("player_not_in_box"), "reason codes are never printed")

        let future = try props(try editingActual(riceHR) { $0["state"] = "not_applicable" })
        XCTAssertNil(future.actuals.first { $0.actualKey == riceHR }?.finalCount, "an unknown state is not final")
    }

    func testTheSavedChanceIsShownOnlyWhenAvailableAndTheActualStaysWithoutIt() throws {
        let after = try props(try specimen())
        let blend = PropExpectationActualDisplay.expectation(try question(after, rice2).expectation)
        XCTAssertEqual(blend.valueText, "3%")
        XCTAssertEqual(blend.label, "Saved pregame chance")
        XCTAssertEqual(blend.basisText, "Average of Kalshi and Polymarket")
        let single = PropExpectationActualDisplay.expectation(try question(after, rice1).expectation)
        XCTAssertEqual(single.valueText, "31%")
        XCTAssertEqual(single.basisText, "Kalshi")

        // Judge 1+ has no admitted pin: no chance, and no basis.
        let judgeQ = try question(after, judge1)
        XCTAssertEqual(judgeQ.expectation.state, "unavailable")
        let none = PropExpectationActualDisplay.expectation(judgeQ.expectation)
        XCTAssertNil(none.valueText)
        XCTAssertNil(none.basisText)

        // Unavailable expectation, final actual: the count and the server's
        // comparison still stand.
        let unpinned = try props(try editingQuestion(rice2) {
            var e = $0["expectation"] as? [String: Any] ?? [:]
            e["state"] = "unavailable"; e["probability"] = NSNull(); e["basis"] = NSNull(); e["contributors"] = []
            $0["expectation"] = e
        })
        let q = try question(unpinned, rice2)
        XCTAssertNil(PropExpectationActualDisplay.expectation(q.expectation).valueText)
        XCTAssertEqual(unpinned.actual(for: q)?.finalCount, 2)
        XCTAssertEqual(PropExpectationActualDisplay.mark(q, actual: unpinned.actual(for: q)), .reached)

        for bad: Any in [1.5, -0.1] {
            let odd = try props(try editingQuestion(rice2) {
                var e = $0["expectation"] as? [String: Any] ?? [:]
                e["probability"] = bad
                $0["expectation"] = e
            })
            XCTAssertNil(odd.questions.first { $0.questionKey == rice2 }?.expectation.savedProbability, "\(bad)")
        }
    }

    func testQuestionAndSpokenWordsUseTheServersLabelAndUnits() throws {
        let after = try props(try specimen())
        let stat = after.stat("home_runs")
        XCTAssertEqual(PropExpectationActualDisplay.question(try question(after, rice2), stat: stat), "2+ home runs")
        XCTAssertEqual(PropExpectationActualDisplay.question(try question(after, rice1), stat: stat), "1+ home run")
        let q = try question(after, rice2)
        let spoken = PropExpectationActualDisplay.accessibilityLabel(q, actual: after.actual(for: q), stat: stat)
        XCTAssertTrue(spoken.hasPrefix("Ben Rice"), spoken)
        XCTAssertTrue(spoken.localizedCaseInsensitiveContains("saved pregame chance"), spoken)
        XCTAssertTrue(spoken.localizedCaseInsensitiveContains("reached"), spoken)
        for code in ["player_not_in_box", "record_version", "kalshi_settled", "pregame_pin_5509"] {
            XCTAssertFalse(spoken.contains(code), code)
        }
    }

    // MARK: - Page

    func testTheOldCardKeepsOnlyThePropsTheAfterGridDoesNotDraw() throws {
        let page = try decode(try specimen())
        let legacy = page.playerProps ?? []
        XCTAssertEqual(legacy.count, 5, "control")
        let kept = AfterPropsMatrixLayout.untypedPlayerProps(legacy, typed: page.afterPlayerProps)
        XCTAssertEqual(kept.compactMap(\.contributorOutcomeIds), [[5022]], "only the untyped Under stays")
        var none = try specimen()
        none["after_player_props"] = NSNull()
        XCTAssertEqual(AfterPropsMatrixLayout.untypedPlayerProps(legacy, typed: try decode(none).afterPlayerProps).count, 5)
    }

    func testAPageWithOnlyAfterQuestionsHasContent() throws {
        var dict = try specimen()
        for key in ["player_props", "spreads", "totals", "team_totals", "period_markets", "other", "matchups"] {
            dict[key] = []
        }
        dict["game_question_matrix"] = NSNull()
        dict["open_winner_quote"] = NSNull()
        XCTAssertTrue(EventDetailView.gameMarketsHaveContent(try decode(dict)))
        dict["after_player_props"] = NSNull()
        XCTAssertFalse(EventDetailView.gameMarketsHaveContent(try decode(dict)), "control")
    }

    // MARK: - Fences

    func testAfterQuestionsAreTheirOwnSectionWithUniqueIdentities() throws {
        let rows = GameMarketsPriceReconciliation.rows(try decode(try specimen()))
        let after = rows.filter { $0.key.hasPrefix("afterProps:") }
        XCTAssertEqual(after.map(\.key), ["afterProps:\(judge1)", "afterProps:\(rice1)", "afterProps:\(rice2)"])
        let identified = GameMarketsPriceReconciliation.identified(rows)
        XCTAssertTrue(identified.ambiguous.isEmpty)
        let blend = try XCTUnwrap(after.last)
        XCTAssertNil(blend.verdict, "the comparison is never a fenced verdict")
        XCTAssertNil(blend.actual)
        XCTAssertEqual(blend.markets, [501, 502])
    }

    func testACorrectedFinalCountIsAdoptedNotHeld() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let first = GameMarketsPriceReconciliation.adopting(try decode(try specimen()), over: nil, fence: &fence)
        XCTAssertEqual(first.afterPlayerProps?.actuals.first { $0.actualKey == riceHR }?.finalCount, 2)
        // ESPN corrects 2 → 1: a new record version and the server's new word.
        var dict = try editingActual(riceHR) { $0["value"] = 1; $0["record_version"] = "corrected0000001" }
        var after = try XCTUnwrap(dict["after_player_props"] as? [String: Any])
        var questions = try XCTUnwrap(after["questions"] as? [[String: Any]])
        let index = try XCTUnwrap(questions.firstIndex { $0["question_key"] as? String == rice2 })
        questions[index]["comparison"] = ["state": "below", "reason": NSNull()]
        after["questions"] = questions
        dict["after_player_props"] = after
        let shown = GameMarketsPriceReconciliation.adopting(try decode(dict), over: first, fence: &fence)
        let corrected = try XCTUnwrap(shown.afterPlayerProps)
        XCTAssertEqual(corrected.actuals.first { $0.actualKey == riceHR }?.finalCount, 1)
        let q = try question(corrected, rice2)
        XCTAssertEqual(PropExpectationActualDisplay.mark(q, actual: corrected.actual(for: q)), .below)
        XCTAssertEqual(q.expectation.savedProbability, first.afterPlayerProps?.questions.first { $0.questionKey == rice2 }?
            .expectation.savedProbability, "the pregame pin does not move with the correction")
    }

    func testARefetchThatOnlyMovesCapturedAtChangesNoWord() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let first = GameMarketsPriceReconciliation.adopting(try decode(try specimen()), over: nil, fence: &fence)
        let refetch = try editingActual(riceHR) { $0["captured_at"] = "2030-01-01T00:00:00+00:00" }
        let shown = GameMarketsPriceReconciliation.adopting(try decode(refetch), over: first, fence: &fence)
        let before = try XCTUnwrap(first.afterPlayerProps)
        let after = try XCTUnwrap(shown.afterPlayerProps)
        let stat = after.stat("home_runs")
        for key in [rice1, rice2, judge1] {
            let b = try question(before, key), a = try question(after, key)
            XCTAssertEqual(PropExpectationActualDisplay.mark(a, actual: after.actual(for: a)),
                           PropExpectationActualDisplay.mark(b, actual: before.actual(for: b)))
            XCTAssertEqual(PropExpectationActualDisplay.actual(after.actual(for: a), stat: stat),
                           PropExpectationActualDisplay.actual(before.actual(for: b), stat: stat))
        }
    }

    func testAnotherEventsBodyNeverReplacesTheHeldAfterGrid() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let first = GameMarketsPriceReconciliation.adopting(try decode(try specimen()), over: nil, fence: &fence)
        var other = try editingActual(riceHR) { $0["value"] = 0 }
        other["event_id"] = (other["event_id"] as? Int ?? 0) + 1
        let shown = GameMarketsPriceReconciliation.adopting(try decode(other), over: first, fence: &fence)
        XCTAssertEqual(shown.afterPlayerProps?.actuals.first { $0.actualKey == riceHR }?.finalCount, 2)
    }
}
