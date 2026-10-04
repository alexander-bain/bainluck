import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10238 — the event page mounts the sourced Game and Series questions
/// (#10396's `EventQuestionMatrixSection10238`) as two independent siblings.
///
/// The three things a reader would see go wrong, and the arm that catches each:
///   1. A finished or price-less Game hides an open Series — the Series section
///      must not sit inside any `if` on the page (static read of the mount).
///   2. Game questions drawn beside "no markets for this game" — the empty
///      note's predicate counts a drawn Game question, and never a Series one.
///   3. Every event page without questions grows a blank gap — a nil section
///      takes no room in the page's stack (hosted measurement).
@MainActor
final class EventQuestionMatrixMount10238Tests: XCTestCase {
    private static var testsDir: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent() }
    private static func fixture(_ name: String) -> URL {
        testsDir.appendingPathComponent("Fixtures").appendingPathComponent(name)
    }
    private static let gameURL = fixture("game-markets-10238-question-matrix.route-harness.json")
    private static let seriesURL = fixture("related-futures-10238-series-matrix.route-harness.json")

    private func object(_ url: URL) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ dict: [String: Any]) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func pageSource() throws -> String {
        try String(contentsOf: Self.testsDir.deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift"), encoding: .utf8)
    }

    /// The game-markets specimen with every legacy section emptied, so the
    /// only possible content is the question matrix.
    private func gameWithOnlyTheMatrix() throws -> [String: Any] {
        var dict = try object(Self.gameURL)
        for key in ["spreads", "totals", "team_totals", "period_markets", "player_props", "other"] {
            dict[key] = [Any]()
        }
        dict["open_winner_quote"] = NSNull()
        return dict
    }

    // MARK: 1 — mount shape

    func testGameAndSeriesAreTwoUngatedSiblingsOfThePage() throws {
        let lines = try pageSource().components(separatedBy: "\n")
        func line(_ needle: String) throws -> (index: Int, text: String) {
            let hits = lines.enumerated().filter { $0.element.contains(needle) }
            XCTAssertEqual(hits.count, 1, "\(needle) should be mounted exactly once")
            let hit = try XCTUnwrap(hits.first)
            return (hit.offset, hit.element)
        }
        func indent(_ text: String) -> Int { text.prefix { $0 == " " }.count }

        let game = try line("matrix: vm.gameMarkets?.gameQuestionMatrix, scope: .game)")
        let series = try line("matrix: vm.relatedFutures?.seriesQuestionMatrix, scope: .series)")
        // `RelatedFuturesView(` is drawn unconditionally at the page stack's own
        // level; a section indented deeper than it is inside some `if`.
        let anchor = try line("RelatedFuturesView(")
        let level = indent(anchor.text)
        for (name, hit) in [("Game", game), ("Series", series)] {
            let call = lines[hit.index - 1]
            XCTAssertEqual(call.trimmingCharacters(in: .whitespaces), "EventQuestionMatrixSection10238(",
                           "\(name) section is not a direct EventQuestionMatrixSection10238 call")
            XCTAssertEqual(indent(call), level,
                           "\(name) section is nested inside a condition; it must be a page sibling")
        }
        let note = try line("noGameMarketsNote(status: event.status)")
        XCTAssertLessThan(game.index, series.index)
        XCTAssertLessThan(series.index, note.index, "questions are drawn before the empty note")
        XCTAssertTrue(lines.contains { $0.contains("SeriesProbabilityView(") },
                      "the model-only series view is a different thing and stays")
    }

    // MARK: 2 — the empty note

    func testADrawnGameQuestionSilencesTheEmptyNote() throws {
        let only = try decode(GameMarketsResponse.self, gameWithOnlyTheMatrix())
        XCTAssertFalse(EventQuestionMatrixAdapter.rows(in: only.gameQuestionMatrix, scope: .game).isEmpty)
        XCTAssertTrue(EventDetailView.gameMarketsHaveContent(only),
                      "the page would print 'no markets' beside real Game questions")

        var bare = try gameWithOnlyTheMatrix()
        bare.removeValue(forKey: "game_question_matrix")
        XCTAssertFalse(EventDetailView.gameMarketsHaveContent(try decode(GameMarketsResponse.self, bare)),
                       "control: with nothing to draw the note must still show")
    }

    func testASeriesMatrixInTheGameSlotIsNotGameContent() throws {
        // A matrix scoped to Series draws nothing in the Game section, so it
        // must not hide the Game empty note either.
        var dict = try gameWithOnlyTheMatrix()
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        matrix["display_scope"] = "series"
        dict["game_question_matrix"] = matrix
        let gm = try decode(GameMarketsResponse.self, dict)
        XCTAssertNotNil(gm.gameQuestionMatrix)
        XCTAssertFalse(EventDetailView.gameMarketsHaveContent(gm))
    }

    // MARK: 4 — options a reader cannot tell apart

    func testAQuestionWhoseOptionsShareALabelIsNotDrawn() throws {
        // Production (event 15323083) served every Polymarket team total as
        // "Over" / "Over" with one shared result; drawn, it read "Over Won /
        // Over Won". The specimen's two-option question, relabelled the same way.
        var dict = try object(Self.gameURL)
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let index = try XCTUnwrap(questions.firstIndex { $0["question_key"] as? String == "m:104" })
        var options = try XCTUnwrap(questions[index]["options"] as? [[String: Any]])
        XCTAssertEqual(options.count, 2)
        let control = try decode(GameMarketsResponse.self, dict)
        XCTAssertTrue(EventQuestionMatrixAdapter.rows(in: control.gameQuestionMatrix, scope: .game)
            .contains { $0.id.questionKey == "m:104" }, "control: distinct labels are drawn")

        for i in options.indices { options[i]["label"] = i == 0 ? "Over" : "over " }
        questions[index]["options"] = options
        matrix["questions"] = questions
        dict["game_question_matrix"] = matrix
        let rows = EventQuestionMatrixAdapter.rows(
            in: try decode(GameMarketsResponse.self, dict).gameQuestionMatrix, scope: .game)
        XCTAssertFalse(rows.contains { $0.id.questionKey == "m:104" },
                       "two options both called Over were drawn")
        XCTAssertEqual(rows.count, EventQuestionMatrixAdapter.rows(in: control.gameQuestionMatrix, scope: .game).count - 1,
                       "the refusal took more than the one question")
    }

    // MARK: 5 — one series question, drawn once

    func testASeriesMarketThePageDrawsIsNotRepeatedInSeasonFutures() throws {
        // Production (event 15323083): the sourced "Series Winner" section and
        // the legacy Season Futures SERIES card printed the same market twice.
        // The ids come from the PAGE's payload (the one the section renders);
        // Season Futures refreshes its own copy, so the two can disagree.
        var dict = try object(Self.seriesURL)
        let child = try decode(RelatedFuturesResponse.self, dict)   // Season Futures' own copy
        XCTAssertEqual(child.seriesMarkets?.map(\.marketId), [900, 910])
        func legacy(page: RelatedFuturesResponse?) -> [Int] {
            RelatedFuturesView.seriesMarkets(
                child.seriesMarkets,
                notDrawnAbove: EventQuestionMatrixAdapter.drawnMarketIds(
                    in: page?.seriesQuestionMatrix, scope: .series)).map(\.marketId)
        }

        XCTAssertEqual(legacy(page: child), [], "matched payloads: a series market is drawn twice")

        // Page has no sourced Series (not loaded / withdrawn) while the child's
        // copy has one: nothing is drawn above, so the legacy card keeps both.
        XCTAssertEqual(legacy(page: nil), [900, 910],
                       "the only series card was hidden for a question the page is not drawing")
        var withdrawn = dict
        withdrawn.removeValue(forKey: "series_question_matrix")
        XCTAssertEqual(legacy(page: try decode(RelatedFuturesResponse.self, withdrawn)), [900, 910])

        // Page draws only m:900 → only 910 stays in the legacy card.
        var matrix = try XCTUnwrap(dict["series_question_matrix"] as? [String: Any])
        let questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        matrix["questions"] = questions.filter { $0["question_key"] as? String == "m:900" }
        dict["series_question_matrix"] = matrix
        XCTAssertEqual(legacy(page: try decode(RelatedFuturesResponse.self, dict)), [910])

        // A question the section refuses to draw does not count as drawn.
        var refused = try object(Self.seriesURL)
        var rm = try XCTUnwrap(refused["series_question_matrix"] as? [String: Any])
        var rq = try XCTUnwrap(rm["questions"] as? [[String: Any]])
        var options = try XCTUnwrap(rq[0]["options"] as? [[String: Any]])
        for i in options.indices { options[i]["label"] = "Over" }
        rq[0]["options"] = options
        rm["questions"] = rq
        refused["series_question_matrix"] = rm
        let page = try decode(RelatedFuturesResponse.self, refused)
        let refusedKey = try XCTUnwrap(rq[0]["question_key"] as? String)
        XCTAssertFalse(EventQuestionMatrixAdapter.rows(in: page.seriesQuestionMatrix, scope: .series)
            .contains { $0.id.questionKey == refusedKey })
        XCTAssertEqual(legacy(page: page).count, 1, "a refused question hid its legacy card")
    }

    func testThePageHandsSeasonFuturesTheIdsItsOwnSeriesSectionDraws() throws {
        let page = try pageSource().filter { !$0.isWhitespace }
        let call = try XCTUnwrap(page.range(of: "RelatedFuturesView("))
        let args = page[call.upperBound...].prefix(600)
        XCTAssertTrue(args.contains(
            "seriesMarketIdsDrawnAbove:EventQuestionMatrixAdapter.drawnMarketIds(in:vm.relatedFutures?.seriesQuestionMatrix,scope:.series)"),
            "Season Futures is not told what the page's Series section draws")
    }

    // MARK: 3 — rendered room

    private func height<V: View>(_ view: V) -> CGFloat {
        hostForMeasurement(view).sizeThatFits(in: CGSize(width: 390, height: CGFloat.greatestFiniteMagnitude)).height
    }

    private func page(game: EventQuestionMatrix?, series: EventQuestionMatrix?) -> some View {
        VStack(spacing: 12) {
            Color.red.frame(height: 10)
            EventQuestionMatrixSection10238(matrix: game, scope: .game)
            EventQuestionMatrixSection10238(matrix: series, scope: .series)
            Color.red.frame(height: 10)
        }
        .frame(width: 390)
    }

    func testAPageWithNoQuestionsGrowsNoGap() {
        let control = height(VStack(spacing: 12) {
            Color.red.frame(height: 10)
            Color.red.frame(height: 10)
        }.frame(width: 390))
        XCTAssertEqual(control, 32, accuracy: 0.5)
        XCTAssertEqual(height(page(game: nil, series: nil)), control, accuracy: 0.5,
                       "an event with no questions now carries blank space where they would be")
    }

    func testSeriesDrawsWhenGameIsAbsentAndGameDrawsAlone() throws {
        let series = try XCTUnwrap(try decode(RelatedFuturesResponse.self, object(Self.seriesURL)).seriesQuestionMatrix)
        let game = try XCTUnwrap(try decode(GameMarketsResponse.self, object(Self.gameURL)).gameQuestionMatrix)
        let empty = height(page(game: nil, series: nil))
        let seriesOnly = height(page(game: nil, series: series))
        let gameOnly = height(page(game: game, series: nil))
        XCTAssertGreaterThan(seriesOnly - empty, 100, "a Series-only page draws no Series questions")
        XCTAssertGreaterThan(gameOnly - empty, 100, "Game questions draw nothing")
        // Each matrix only draws in its own scope's section.
        XCTAssertEqual(height(page(game: series, series: game)), empty, accuracy: 0.5,
                       "a matrix drew in the other scope's section")
    }
}
