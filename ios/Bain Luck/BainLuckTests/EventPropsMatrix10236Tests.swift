import XCTest
@testable import Bain_Luck

/// #10236 — the During player matrix: decode, layout, selection, words and the
/// #9524 price fences, driven from the producer's own route output.
///
/// FIXTURE: `Fixtures/game-markets-10236-during-matrix.route.json` is the body
/// `events_route._build_game_markets` returned at master `c093c90087` from the
/// producer test's route harness (`tests/test_event_props_matrix_10236.py::_page`,
/// a live Yankees–Padres game on a mocked session) with three extra markets:
/// Kalshi Total Bases (Judge 2+, Soto 2+, Soto 3+ unpriced), Polymarket
/// `Juan Soto: Hits O/U 1.5` and a lone `Fernando Tatis Jr.: Hits O/U 1.5`
/// Under. It is the real serializer's spelling, not production prices —
/// production did not yet carry the key when this was written (`/health`
/// `ae6da3e9`). Cases that need a state the harness cannot produce (an
/// unavailable quote, a result) edit one row of that body and say so.
@MainActor
final class EventPropsMatrix10236Tests: XCTestCase {
    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10236-during-matrix.route.json")
    private static let legacyURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("event-14780549-game-markets-9585-bears-eagles.20260928.json")

    private let judge2 = "s:aaron judge|hits|full_game|ge:2|over"
    private let judge4 = "s:aaron judge|hits|full_game|ge:4|over"
    private let t0 = "2030-01-01T00:00:00.000001Z"
    private let t1 = "2030-01-01T00:00:00.000002Z"
    private let t2 = "2030-01-01T00:00:00.000003Z"

    private func specimen() throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
    }

    private func decode(_ dict: [String: Any]) throws -> GameMarketsResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    /// The specimen with one During row edited in place.
    private func editing(_ key: String, _ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        var dict = try specimen()
        var during = try XCTUnwrap(dict["during_player_props"] as? [String: Any])
        var rows = try XCTUnwrap(during["rows"] as? [[String: Any]])
        let index = try XCTUnwrap(rows.firstIndex { $0["question_key"] as? String == key })
        edit(&rows[index])
        during["rows"] = rows
        dict["during_player_props"] = during
        return dict
    }

    private func props(_ dict: [String: Any]) throws -> DuringPlayerProps {
        try XCTUnwrap(try decode(dict).duringPlayerProps)
    }

    private func row(_ props: DuringPlayerProps, _ key: String) throws -> DuringPropRow {
        try XCTUnwrap(props.rows.first { $0.questionKey == key })
    }

    // MARK: - Decode

    func testTheRouteBodyDecodesEveryRowAndAnOlderBodyDecodesNil() throws {
        let during = try props(try specimen())
        XCTAssertEqual(during.contract, "10236.v1")
        XCTAssertEqual(during.stats.map(\.statKey), ["hits", "total_bases"])
        XCTAssertEqual(during.rows.count, 12)
        XCTAssertEqual(during.coverage?.subjects, 3)
        let blend = try row(during, judge2)
        XCTAssertEqual(blend.current.basis, "blend_mean")
        XCTAssertEqual(blend.contributors.map(\.source), ["kalshi", "polymarket"])
        XCTAssertEqual(blend.contributorOutcomeIds, [5012, 5021])
        XCTAssertEqual(blend._marketIds, [501, 502])

        let legacy = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.legacyURL)) as? [String: Any])
        let old = try decode(legacy)
        XCTAssertNil(old.duringPlayerProps, "absent key keeps the old card")
        XCTAssertEqual(old.playerProps?.count, 860)

        var null = try specimen()
        null["during_player_props"] = NSNull()
        XCTAssertNil(try decode(null).duringPlayerProps)
    }

    // MARK: - Layout

    func testHitsGridHasEveryThresholdColumnStablePlayersAndEmptySlots() throws {
        let grid = try XCTUnwrap(EventPropsMatrixLayout.grid(try props(try specimen()), statKey: "hits"))
        XCTAssertEqual(grid.columns, [1, 2, 3, 4])
        XCTAssertEqual(grid.players.map(\.label), ["Aaron Judge", "Juan Soto"], "server order, not price")
        XCTAssertEqual(grid.players[0].cells.keys.sorted(), [1, 2, 3, 4])
        XCTAssertEqual(grid.players[1].cells.keys.sorted(), [1, 2])
        XCTAssertNil(grid.players[1].cells[3], "Soto 3+ is not offered: an empty slot, never a borrowed price")
        // Three players (Tatis has only an under row) — a player with two
        // markets is still one player. Seven questions, not the ten rows: six
        // drawn cells plus Tatis's unplaced under; the three unders paired
        // behind a drawn over are those questions' other sides.
        XCTAssertEqual(grid.playerCount, 3)
        XCTAssertEqual(grid.questionCount, 7)
        XCTAssertEqual(grid.unavailableCount, 0)
        XCTAssertEqual(grid.unplaced.map(\.questionKey), ["s:fernando tatis jr|hits|full_game|le:1|under"])
    }

    func testUnderRowsLiveBehindTheirServerPairedOverCellOnly() throws {
        let during = try props(try specimen())
        let other = EventPropsMatrixLayout.otherSide(of: try row(during, judge2), in: during)
        XCTAssertEqual(other?.questionKey, "s:aaron judge|hits|full_game|le:1|under")
        XCTAssertEqual(other?.current.quotedProbability, 0.5)
        XCTAssertNil(EventPropsMatrixLayout.otherSide(of: try row(during, judge4), in: during))
    }

    func testAFiniteZeroIsAQuoteAndKeepsItsPrecisionInDetail() throws {
        let zero = try row(try props(try specimen()), judge4)
        XCTAssertEqual(zero.current.quotedProbability, 0.0)
        XCTAssertEqual(EventPropsMatrixLayout.cellText(zero), "<1%")
        XCTAssertEqual(EventPropsMatrixLayout.exactPercent(zero.current.quotedProbability), "0.0%")
    }

    func testUnavailableNonFiniteAndOutOfRangeNeverGainAChance() throws {
        let dict = try editing(judge2) {
            $0["current"] = ["state": "unavailable", "probability": NSNull(), "basis": NSNull(), "observed_at": NSNull()]
        }
        let during = try props(dict)
        let gone = try row(during, judge2)
        XCTAssertNil(gone.current.quotedProbability)
        XCTAssertEqual(EventPropsMatrixLayout.cellText(gone), "\u{2014}")
        XCTAssertNil(EventPropsMatrixLayout.changeText(gone), "its comparable delta is not shown without a quote")
        XCTAssertTrue(EventPropsMatrixLayout.accessibilityLabel(gone, stat: during.stats.first).hasSuffix("no current price"))
        XCTAssertEqual(EventPropsMatrixLayout.grid(during, statKey: "hits")?.unavailableCount, 1)

        for bad in [Double.nan, .infinity, 1.5, -0.1] {
            XCTAssertNil(DuringPropCurrent(state: "quoted", probability: bad, basis: nil, observedAt: nil).quotedProbability)
        }
        XCTAssertNil(DuringPropCurrent(state: "mystery", probability: 0.4, basis: nil, observedAt: nil).quotedProbability)
    }

    func testAnActualOnlyRowShowsTheServersGradeAndNoChance() throws {
        let dict = try editing(judge2) {
            $0["current"] = ["state": "actual_only", "probability": NSNull(), "basis": NSNull(), "observed_at": NSNull()]
            $0["result"] = ["actual": 2, "hit": true]
        }
        let graded = try row(try props(dict), judge2)
        XCTAssertNil(graded.current.quotedProbability)
        XCTAssertEqual(EventPropsMatrixLayout.cellText(graded), "Hit")
        XCTAssertNil(EventPropsMatrixLayout.changeText(graded))
        XCTAssertEqual(EventPropsMatrixLayout.grid(try props(dict), statKey: "hits")?.unavailableCount, 0)
    }

    // MARK: - Change since pregame

    func testChangeIsTheServersComparableDeltaInWholePointsAndNeverAFalseZero() throws {
        let during = try props(try specimen())
        XCTAssertEqual(EventPropsMatrixLayout.changeText(try row(during, "s:aaron judge|hits|full_game|ge:1|over")), "+17%")
        XCTAssertEqual(EventPropsMatrixLayout.changeText(try row(during, judge2)), "+10%")
        XCTAssertEqual(EventPropsMatrixLayout.changeText(try row(during, judge4)), "\u{2212}2%")
        // No pregame pin: no change, even though both numbers exist elsewhere.
        XCTAssertNil(EventPropsMatrixLayout.changeText(try row(during, "s:juan soto|hits|full_game|ge:1|over")))
        XCTAssertTrue(try XCTUnwrap(EventPropsMatrixLayout.grid(during, statKey: "hits")).showsChange)
        XCTAssertFalse(try XCTUnwrap(EventPropsMatrixLayout.grid(during, statKey: "total_bases")).showsChange)

        let small = try props(try editing(judge2) {
            var c = $0["comparison"] as? [String: Any] ?? [:]
            c["delta_points"] = 0.6
            $0["comparison"] = c
        })
        XCTAssertNil(EventPropsMatrixLayout.changeText(try row(small, judge2)), "under one point prints nothing, not 0%")
    }

    // MARK: - Words

    func testQuestionAndSpokenLabelsUseTheServersPredicateAndUnits() throws {
        let during = try props(try specimen())
        let hits = during.stats.first
        XCTAssertEqual(EventPropsMatrixLayout.question(try row(during, "s:aaron judge|hits|full_game|ge:1|over"), stat: hits), "1+ hit")
        XCTAssertEqual(EventPropsMatrixLayout.question(try row(during, judge2), stat: hits), "2+ hits")
        XCTAssertEqual(EventPropsMatrixLayout.question(try row(during, "s:juan soto|hits|full_game|le:0|under"), stat: hits), "0 or fewer hits")
        XCTAssertEqual(EventPropsMatrixLayout.accessibilityLabel(try row(during, judge2), stat: hits),
                       "Aaron Judge, 2 or more hits, 48 percent, up 10 points since pregame")
        XCTAssertEqual(EventPropsMatrixLayout.accessibilityLabel(try row(during, judge4), stat: hits),
                       "Aaron Judge, 4 or more hits, under 1 percent, down 2 points since pregame")
        XCTAssertEqual(EventPropsMatrixLayout.basisText(try row(during, judge2)), "Average of Kalshi and Polymarket")
        XCTAssertEqual(EventPropsMatrixLayout.basisText(try row(during, judge4)), "Kalshi")
    }

    // MARK: - Selection

    func testSelectionKeepsItsStatAndQuestionAndNeverJumpsToASibling() throws {
        let during = try props(try specimen())
        var selection = EventPropsMatrixSelection()
        XCTAssertEqual(selection.resolvedStat(in: during), "hits", "server's first stat by default")
        selection.statKey = "total_bases"
        selection.openQuestion = .init(try row(during, judge2))
        XCTAssertEqual(EventPropsMatrixSelection.resolve(try XCTUnwrap(selection.openQuestion), in: during)?.questionKey, judge2)

        // A newer payload without that question: the detail reads unavailable,
        // and neither Judge 3+ nor Soto 2+ takes its place.
        var dict = try specimen()
        var block = try XCTUnwrap(dict["during_player_props"] as? [String: Any])
        block["rows"] = try XCTUnwrap(block["rows"] as? [[String: Any]]).filter { $0["question_key"] as? String != judge2 }
        block["stats"] = try XCTUnwrap(block["stats"] as? [[String: Any]]).filter { $0["stat_key"] as? String == "hits" }
        dict["during_player_props"] = block
        let newer = try props(dict)
        XCTAssertNil(EventPropsMatrixSelection.resolve(try XCTUnwrap(selection.openQuestion), in: newer))
        XCTAssertEqual(selection.resolvedStat(in: newer), "total_bases", "a chosen stat that leaves stays chosen")
        XCTAssertNil(EventPropsMatrixLayout.grid(newer, statKey: "total_bases"))
    }

    // MARK: - #9524 fences

    /// The specimen with every contributor bound and clocked, and the Judge
    /// 2+ blend (contributors 5012/5021 on markets 501/502) set as given.
    private func read(blend: Double = 0.48, clock: String? = nil, state: String = "quoted") throws -> GameMarketsResponse {
        var dict = try editing(judge2) {
            var current = $0["current"] as? [String: Any] ?? [:]
            current["state"] = state
            current["probability"] = state == "quoted" ? blend as Any : NSNull()
            $0["current"] = current
        }
        let bindings = try XCTUnwrap(dict["outcome_market_ids"] as? [String: Any])
        var revisions: [String: String] = [:]
        for id in bindings.keys { revisions[id] = t0 }
        if let clock { revisions["5012"] = clock; revisions["5021"] = clock }
        dict["outcome_revision_at"] = revisions
        return try decode(dict)
    }

    private func blend(_ body: GameMarketsResponse) -> Double? {
        body.duringPlayerProps?.rows.first { $0.questionKey == judge2 }?.current.quotedProbability
    }

    func testDuringRowsAreTheirOwnSectionWithUniqueIdentities() throws {
        let rows = GameMarketsPriceReconciliation.rows(try read())
        let during = rows.filter { $0.key.hasPrefix("duringProps:") }
        XCTAssertEqual(during.count, 12)
        let identity = GameMarketsPriceReconciliation.identified(rows)
        XCTAssertTrue(identity.ambiguous.isEmpty)
        XCTAssertEqual(identity.rows.count, rows.count)
        // 5012 is in both arrays and neither row absorbs the other.
        XCTAssertTrue(rows.contains { $0.key.hasPrefix("props:") && $0.contributors.contains("5012") })
        XCTAssertTrue(during.contains { $0.contributors == ["5012", "5021"] })
    }

    func testANewerQuoteAdoptsAndAnOlderOneCannotUndoIt() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        var shown = GameMarketsPriceReconciliation.adopting(try read(), over: nil, fence: &fence)
        XCTAssertEqual(blend(shown), 0.48)

        shown = GameMarketsPriceReconciliation.adopting(try read(blend: 0.55, clock: t2), over: shown, fence: &fence)
        XCTAssertEqual(blend(shown), 0.55, "a changed quote on its own advancing clock is adopted")

        shown = GameMarketsPriceReconciliation.adopting(try read(blend: 0.48, clock: t1), over: shown, fence: &fence)
        XCTAssertEqual(blend(shown), 0.55, "an older reading never visibly undoes the newer one")
    }

    func testAChangedQuoteWithNoAdvancingClockIsHeld() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let first = GameMarketsPriceReconciliation.adopting(try read(), over: nil, fence: &fence)
        let shown = GameMarketsPriceReconciliation.adopting(try read(blend: 0.61), over: first, fence: &fence)
        XCTAssertEqual(blend(shown), 0.48)
    }

    func testAWithdrawnQuoteIsNotRestoredWithoutANewerClock() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        var shown = GameMarketsPriceReconciliation.adopting(try read(), over: nil, fence: &fence)
        shown = GameMarketsPriceReconciliation.adopting(try read(state: "unavailable"), over: shown, fence: &fence)
        XCTAssertNil(blend(shown), "an unavailable question publishes no chance")

        let stale = GameMarketsPriceReconciliation.adopting(try read(blend: 0.48), over: shown, fence: &fence)
        XCTAssertNil(blend(stale), "restoring the old quote needs a newer clock")
        let fresh = GameMarketsPriceReconciliation.adopting(try read(blend: 0.5, clock: t2), over: shown, fence: &fence)
        XCTAssertEqual(blend(fresh), 0.5)
    }

    func testTwoConflictingRowsForOneQuestionAreWithheldNotGuessed() throws {
        var dict = try specimen()
        var block = try XCTUnwrap(dict["during_player_props"] as? [String: Any])
        var rows = try XCTUnwrap(block["rows"] as? [[String: Any]])
        var twin = try XCTUnwrap(rows.first { $0["question_key"] as? String == judge2 })
        var current = try XCTUnwrap(twin["current"] as? [String: Any])
        current["probability"] = 0.9
        twin["current"] = current
        rows.append(twin)
        block["rows"] = rows
        dict["during_player_props"] = block
        var fence = GameMarketsPriceReconciliation.Fence()
        let shown = GameMarketsPriceReconciliation.adopting(try decode(dict), over: nil, fence: &fence)
        let kept = try XCTUnwrap(shown.duringPlayerProps).rows
        XCTAssertFalse(kept.contains { $0.questionKey == judge2 }, "no verified copy exists, so neither is shown")
        XCTAssertEqual(kept.count, 11, "every other question survives")
    }
}
