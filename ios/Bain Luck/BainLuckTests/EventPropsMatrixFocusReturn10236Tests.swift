import XCTest
@testable import Bain_Luck

/// #10236 — where VoiceOver lands when the reader closes a During question's
/// detail, across the newer payloads that can arrive while it is open.
///
/// The destination is the opened question's keys (question / subject / stat),
/// never a price or an index: still drawn ⇒ that cell; removed, reclassified or
/// its statistic gone ⇒ the matrix header; the whole matrix withdrawn ⇒ the
/// page. Root's r2 counterexample is the first case: opening a question on the
/// DEFAULT statistic (no stat chip pressed) must pin that statistic, or a newer
/// payload that puts another stat first swaps the background and Close lands on
/// the header while the question is still there.
///
/// FIXTURE: the same producer route body as `EventPropsMatrix10236Tests`
/// (stats `hits`, `total_bases`); each case edits only what it names.
@MainActor
final class EventPropsMatrixFocusReturn10236Tests: XCTestCase {
    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10236-during-matrix.route.json")

    private let judge2 = "s:aaron judge|hits|full_game|ge:2|over"
    private let tatisUnder = "s:fernando tatis jr|hits|full_game|le:1|under"

    private func specimen() throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
    }

    /// The specimen's During block, edited.
    private func props(_ edit: (inout [String: Any]) throws -> Void = { _ in }) throws -> DuringPlayerProps {
        var dict = try specimen()
        var block = try XCTUnwrap(dict["during_player_props"] as? [String: Any])
        try edit(&block)
        dict["during_player_props"] = block
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let body = try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
        return try XCTUnwrap(body.duringPlayerProps)
    }

    private func rows(_ block: [String: Any]) throws -> [[String: Any]] {
        try XCTUnwrap(block["rows"] as? [[String: Any]])
    }

    private func row(_ props: DuringPlayerProps, _ key: String) throws -> DuringPropRow {
        try XCTUnwrap(props.rows.first { $0.questionKey == key })
    }

    private func focus(_ open: EventPropsMatrixSelection.OpenQuestion,
                       _ selection: EventPropsMatrixSelection,
                       _ props: DuringPlayerProps) -> EventPropsMatrixLayout.ReturnFocus {
        EventPropsMatrixLayout.returnFocus(after: open, selection: selection, in: props)
    }

    /// Opens `key` on the default statistic, exactly as a cell tap does.
    private func openOnDefaultStat(_ key: String) throws -> (EventPropsMatrixSelection, EventPropsMatrixSelection.OpenQuestion) {
        var selection = EventPropsMatrixSelection()
        XCTAssertNil(selection.statKey, "no stat chip pressed")
        let open = selection.open(try row(try props(), key))
        return (selection, open)
    }

    func testOpeningADefaultStatQuestionPinsThatStatAgainstAReorder() throws {
        let (selection, open) = try openOnDefaultStat(judge2)
        XCTAssertEqual(selection.statKey, "hits")
        XCTAssertEqual(selection.openQuestion, open)

        let reordered = try props { block in
            block["stats"] = try XCTUnwrap(block["stats"] as? [[String: Any]]).reversed()
        }
        XCTAssertEqual(reordered.stats.first?.statKey, "total_bases", "the newer payload leads with another stat")
        XCTAssertEqual(selection.resolvedStat(in: reordered), "hits", "the open question's stat stays on screen")
        XCTAssertEqual(focus(open, selection, reordered), .question(open))

        // CONTROL — the first proposal's state: the same question opened with
        // no pin. The reorder moves the background and Close falls to the
        // header although the question is still drawn. This arm must differ.
        var unpinned = EventPropsMatrixSelection()
        unpinned.openQuestion = open
        XCTAssertEqual(unpinned.resolvedStat(in: reordered), "total_bases")
        XCTAssertEqual(focus(open, unpinned, reordered), .header)
    }

    func testAStatThatLeavesKeepsItsEmptyStateAndFocusesTheHeaderNeverTheRemainingStat() throws {
        let (selection, open) = try openOnDefaultStat(judge2)
        let hitsGone = try props { block in
            block["stats"] = try XCTUnwrap(block["stats"] as? [[String: Any]]).filter { $0["stat_key"] as? String != "hits" }
            block["rows"] = try rows(block).filter { $0["stat_key"] as? String != "hits" }
        }
        XCTAssertFalse(hitsGone.rows.isEmpty, "the matrix itself is still drawn")
        XCTAssertEqual(selection.resolvedStat(in: hitsGone), "hits", "never switches to the remaining first stat")
        XCTAssertNil(EventPropsMatrixLayout.grid(hitsGone, statKey: "hits"))
        XCTAssertEqual(focus(open, selection, hitsGone), .header)
    }

    func testANewerPriceKeepsTheSameQuestionAsTheDestination() throws {
        let (selection, open) = try openOnDefaultStat(judge2)
        let newer = try props { block in
            var all = try rows(block)
            let i = try XCTUnwrap(all.firstIndex { $0["question_key"] as? String == judge2 })
            all[i]["current"] = ["state": "quoted", "probability": 0.61, "basis": "blend_mean",
                                 "observed_at": "2026-10-03T07:20:00+00:00"]
            block["rows"] = all
        }
        XCTAssertEqual(try row(newer, judge2).current.quotedProbability, 0.61)
        XCTAssertEqual(focus(open, selection, newer), .question(open))
    }

    func testAStillDrawnUnavailableQuestionKeepsFocus() throws {
        let (selection, open) = try openOnDefaultStat(judge2)
        let unavailable = try props { block in
            var all = try rows(block)
            let i = try XCTUnwrap(all.firstIndex { $0["question_key"] as? String == judge2 })
            all[i]["current"] = ["state": "unavailable", "probability": NSNull(), "basis": NSNull(), "observed_at": NSNull()]
            block["rows"] = all
        }
        XCTAssertNil(try row(unavailable, judge2).current.quotedProbability)
        XCTAssertEqual(focus(open, selection, unavailable), .question(open), "its own cell reads 'no current price'")
    }

    func testARemovedQuestionFocusesTheHeaderNotASibling() throws {
        let (selection, open) = try openOnDefaultStat(judge2)
        let removed = try props { block in
            block["rows"] = try rows(block).filter { $0["question_key"] as? String != judge2 }
        }
        XCTAssertNotNil(EventPropsMatrixLayout.grid(removed, statKey: "hits"), "Judge 1+/3+ and Soto still drawn")
        XCTAssertEqual(focus(open, selection, removed), .header)
    }

    func testAnUnderOnlyQuestionThatBecomesPairedFocusesTheHeaderNotItsHiddenSide() throws {
        let (selection, open) = try openOnDefaultStat(tatisUnder)
        XCTAssertEqual(focus(open, selection, try props()), .question(open), "listed unplaced, so drawn")

        let paired = try props { block in
            var all = try rows(block)
            var over = try XCTUnwrap(all.first { $0["question_key"] as? String == judge2 })
            over["question_key"] = "s:fernando tatis jr|hits|full_game|ge:2|over"
            over["subject"] = ["key": "fernando tatis jr", "kind": "player", "label": "Fernando Tatis Jr."]
            all.append(over)
            block["rows"] = all
        }
        let grid = try XCTUnwrap(EventPropsMatrixLayout.grid(paired, statKey: "hits"))
        XCTAssertFalse(grid.unplaced.contains { $0.questionKey == tatisUnder }, "now behind the over cell")
        XCTAssertNotNil(EventPropsMatrixSelection.resolve(open, in: paired), "the question still exists")
        XCTAssertEqual(focus(open, selection, paired), .header)
    }

    func testAWithdrawnMatrixHandsTheDestinationToThePage() throws {
        let (selection, open) = try openOnDefaultStat(judge2)
        let withdrawn = try props { block in block["rows"] = [[String: Any]]() }
        XCTAssertEqual(focus(open, selection, withdrawn), .matrixWithdrawn)

        // The page's stand-in payload after the key leaves entirely.
        let standIn = DuringPlayerProps(contract: nil, stats: [], rows: [], coverage: nil)
        XCTAssertEqual(focus(open, selection, standIn), .matrixWithdrawn)
    }
}
