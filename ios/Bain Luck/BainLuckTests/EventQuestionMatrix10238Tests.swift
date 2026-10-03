import XCTest
@testable import Bain_Luck

/// #10238 — the Game / Series question matrix consumer: decode, column kinds,
/// published value rules, selection identity and the #9524 price fences.
///
/// FIXTURES ARE SYNTHETIC, IN THE FROZEN SPELLING. No producer exists yet
/// (contract `10238.v1` is contract-only), so
/// `Fixtures/game-markets-10238-question-matrix.synthetic.json` and
/// `Fixtures/related-futures-10238-series-matrix.synthetic.json` are written
/// from the contract's §3/§4 examples and §9 cases, not captured from a route.
/// When the producer lands, a route-harness body replaces them.
@MainActor
final class EventQuestionMatrix10238Tests: XCTestCase {
    private static func fixture(_ name: String) -> URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures").appendingPathComponent(name)
    }
    private static let gameURL = fixture("game-markets-10238-question-matrix.synthetic.json")
    private static let seriesURL = fixture("related-futures-10238-series-matrix.synthetic.json")

    private let runs8 = "q:count|runs|game|full_game|ge:8"
    private let homeSpread = "q:handicap|points|home|half_1|-3.5"
    private let awaySpread = "q:handicap|points|away|half_1|+3.5"
    private let t1 = "2030-01-01T00:00:00.000001Z"
    private let t2 = "2030-01-01T00:00:00.000002Z"

    private func object(_ url: URL) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ dict: [String: Any]) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func game(_ dict: [String: Any]? = nil) throws -> GameMarketsResponse {
        try decode(GameMarketsResponse.self, dict ?? object(Self.gameURL))
    }

    private func matrix(_ dict: [String: Any]? = nil) throws -> EventQuestionMatrix {
        try XCTUnwrap(try game(dict).gameQuestionMatrix)
    }

    private func question(_ matrix: EventQuestionMatrix, _ key: String) throws -> QuestionMatrixQuestion {
        try XCTUnwrap(matrix.question(key))
    }

    /// The specimen with one game question edited in place.
    private func editing(_ key: String, revision: String? = nil,
                         _ edit: (inout [String: Any]) -> Void) throws -> [String: Any] {
        var dict = try object(Self.gameURL)
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let index = try XCTUnwrap(questions.firstIndex { $0["question_key"] as? String == key })
        edit(&questions[index])
        matrix["questions"] = questions
        dict["game_question_matrix"] = matrix
        if let revision {
            var clocks = try XCTUnwrap(dict["outcome_revision_at"] as? [String: Any])
            for id in clocks.keys { clocks[id] = revision }
            dict["outcome_revision_at"] = clocks
        }
        return dict
    }

    /// The same option served twice with different values — a conflict.
    private func duplicatingFirstOption(of key: String, in dict: [String: Any],
                                        value: Double) throws -> [String: Any] {
        var dict = dict
        var matrix = try XCTUnwrap(dict["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let index = try XCTUnwrap(questions.firstIndex { $0["question_key"] as? String == key })
        var options = try XCTUnwrap(questions[index]["options"] as? [[String: Any]])
        var twin = options[0]
        var published = try XCTUnwrap(twin["published"] as? [String: Any])
        published["value"] = value
        twin["published"] = published
        options.append(twin)
        questions[index]["options"] = options
        matrix["questions"] = questions
        dict["game_question_matrix"] = matrix
        return dict
    }

    private func setFirstOption(_ question: inout [String: Any], value: Double) {
        var options = question["options"] as? [[String: Any]] ?? []
        var published = options[0]["published"] as? [String: Any] ?? [:]
        published["value"] = value
        options[0]["published"] = published
        var evidence = options[0]["source_evidence"] as? [[String: Any]] ?? []
        if !evidence.isEmpty { evidence[0]["raw_probability"] = value }
        options[0]["source_evidence"] = evidence
        question["options"] = options
    }

    // MARK: - Decode

    func testTheGameBodyDecodesEveryReadableQuestionAndSkipsOnlyTheMalformedOne() throws {
        let m = try matrix()
        XCTAssertEqual(m.contract, "10238.v1")
        XCTAssertEqual(m.displayScope, "game")
        XCTAssertEqual(m.questions.count, 9)
        XCTAssertEqual(m.droppedQuestions, 1, "the question with no options is skipped alone")
        XCTAssertNil(m.question("m:71099"))
        XCTAssertEqual(m.coverage?.scope, "rows_served_by_this_response")
        XCTAssertEqual(m.questions.first?.questionKey, runs8, "server order is kept")

        let count = try question(m, runs8)
        XCTAssertEqual(count.label, "8+ runs")
        XCTAssertEqual(count.quantity?.plural, "runs")
        XCTAssertEqual(count.period?.key, "full_game")
        XCTAssertEqual(count.predicate?.bound, 8)
        XCTAssertEqual(count.predicate?.line, 7.5)
        let option = try XCTUnwrap(count.option("o:72012"))
        XCTAssertEqual(option.contributorOutcomeIds, [72012])
        XCTAssertEqual(option.sourceEvidence?.first?.legSide, "over")

        let home = try question(m, homeSpread)
        XCTAssertEqual(home.complementQuestionKey, awaySpread, "the complement is the server's, never derived")
        XCTAssertEqual(home.label, "Alpha City -3.5 points · 1st half")
    }

    func testAnAbsentNullOrUnreadableMatrixDecodesNilAndNeverTakesTheLegacyArraysDown() throws {
        var dict = try object(Self.gameURL)
        dict.removeValue(forKey: "game_question_matrix")
        XCTAssertNil(try game(dict).gameQuestionMatrix, "older servers omit the key")
        dict["game_question_matrix"] = NSNull()
        XCTAssertNil(try game(dict).gameQuestionMatrix)

        let brokenValues: [Any] = ["10238.v1", 7, ["questions": "not an array"]]
        for broken in brokenValues {
            dict["game_question_matrix"] = broken
            let body = try game(dict)
            XCTAssertEqual(body.totals?.first?.overProbability, 0.6, "legacy totals survive \(broken)")
            XCTAssertEqual(body.periodMarkets?.count, 2)
            if let matrix = body.gameQuestionMatrix {
                XCTAssertTrue(matrix.questions.isEmpty, "a readable shell with unreadable questions holds none")
            }
        }
    }

    // MARK: - Kinds

    func testOnlyATypedKindEntersASpecialisedColumn() throws {
        let m = try matrix()
        XCTAssertEqual(try question(m, runs8).columnKind, .countThreshold)
        XCTAssertEqual(try question(m, homeSpread).columnKind, .signedHandicap)
        XCTAssertEqual(try question(m, "m:71004").columnKind, .namedOptions)
        XCTAssertEqual(try question(m, "m:71020").columnKind, .namedOptions,
                       "a typed kind the server also marked untyped fails closed")
        XCTAssertEqual(try question(m, "m:71021").columnKind, .namedOptions,
                       "a kind this build does not know keeps its served labels")
    }

    // MARK: - Published value

    func testAFiniteZeroIsAQuoteAndEveryNonQuotedStateShowsNoNumber() throws {
        let m = try matrix()
        let threeWay = try question(m, "m:71003")
        XCTAssertEqual(threeWay.option("o:72007")?.published.quotedValue, 0.0, "finite 0 is real (F1)")
        XCTAssertEqual(threeWay.options.map(\.side), ["home", "draw", "away"])
        XCTAssertEqual(threeWay.complete, true)

        let equivalents = try XCTUnwrap(try question(m, "q:count|goals|game|full_game|ge:3").options.first)
        XCTAssertEqual(equivalents.published.valueState, "unblended_equivalents")
        XCTAssertNil(equivalents.published.quotedValue)
        XCTAssertEqual(equivalents.sourceEvidence?.compactMap(\.rawProbability), [0.55, 0.47],
                       "every row's raw stays visible; the phone never blends")

        let edited = try editing(runs8) { question in
            var options = question["options"] as? [[String: Any]] ?? []
            options[0]["published"] = ["value": 1.4, "value_state": "quoted", "basis": "published_source_display"]
            question["options"] = options
        }
        XCTAssertNil(try question(try matrix(edited), runs8).options[0].published.quotedValue,
                     "an out-of-range value is no chance")

        for state in ["refused", "unpriced", "result", "unblended_equivalents", "some_future_state"] {
            let notQuoted = try editing(runs8) { question in
                var options = question["options"] as? [[String: Any]] ?? []
                options[0]["published"] = ["value": 0.6, "value_state": state, "basis": "unknown"]
                question["options"] = options
            }
            XCTAssertNil(try question(try matrix(notQuoted), runs8).options[0].published.quotedValue,
                         "the state decides, not the presence of a number: \(state)")
        }
    }

    func testDisplayValueAndRawEvidenceAreBothKeptAndTheServerOwnsTheSum() throws {
        let field = try question(try matrix(), "m:71004")
        XCTAssertEqual(field.options.compactMap(\.published.quotedValue), [0.5392, 0.2451, 0.2157])
        XCTAssertEqual(field.options.compactMap { $0.sourceEvidence?.first?.rawProbability }, [0.55, 0.25, 0.22])
        XCTAssertEqual(field.sourceTotals?.first?.rawSum, 1.02)
    }

    func testMissingLegsCarryIdentityButNoPrice() throws {
        let binary = try question(try matrix(), "m:71001")
        XCTAssertEqual(binary.options.map(\.optionKey), ["o:72001"])
        XCTAssertEqual(binary.missingOptions?.map(\.optionKey), ["o:72002"])
        XCTAssertEqual(binary.missingOptions?.first?.valueState, "unpriced")
        XCTAssertEqual(binary.complete, false)
        XCTAssertEqual(binary.optionCounts?.loaded, 2)
    }

    // MARK: - Comparison (R5)

    func testADeltaIsShownOnlyBesideLatestWhenTheServerSaysComparable() throws {
        let m = try matrix()
        let comparison = try XCTUnwrap(try question(m, homeSpread).options[0].comparison)
        let shown = try XCTUnwrap(comparison.shownDelta)
        XCTAssertEqual(shown.points, 12.0)
        XCTAssertEqual(shown.latest.probability, 0.52)
        XCTAssertEqual(QuestionMatrixComparison.caption, "since the saved pregame price")
        XCTAssertNil(try question(m, runs8).options[0].comparison?.shownDelta, "no_pregame_pin")

        let noLatest = try editing(homeSpread) { question in
            var options = question["options"] as? [[String: Any]] ?? []
            var comparison = options[0]["comparison"] as? [String: Any] ?? [:]
            comparison["latest"] = NSNull()
            options[0]["comparison"] = comparison
            question["options"] = options
        }
        XCTAssertNil(try question(try matrix(noLatest), homeSpread).options[0].comparison?.shownDelta,
                     "a delta never sits beside the published value")
    }

    // MARK: - Series

    func testAFinishedGameLeavesTheOpenSeriesOpenAndAResultIsNotAQuote() throws {
        let body = try decode(RelatedFuturesResponse.self, object(Self.seriesURL))
        XCTAssertEqual(body.eventStatus, "final")
        XCTAssertEqual(body.seriesMarkets?.count, 2, "legacy series cards decode unchanged")
        let series = try XCTUnwrap(body.seriesQuestionMatrix)
        XCTAssertEqual(series.displayScope, "series")
        XCTAssertEqual(series.seriesMarketsCount?.returned, 2)

        let winner = try question(series, "m:71008")
        XCTAssertEqual(winner.lifecycle?.state, "open")
        XCTAssertEqual(winner.options.compactMap(\.published.quotedValue), [0.70, 0.29], "never 70/30")
        XCTAssertTrue(winner.options.allSatisfy { $0.comparison?.reason == "series_baseline_unsupported" })
        XCTAssertTrue(winner.options.allSatisfy { $0.published.observedAt == nil }, "U2: no Series clock")

        let exact = try question(series, "m:71009")
        let lost = try XCTUnwrap(exact.option("o:72015"))
        XCTAssertEqual(lost.result?.isWinner, false)
        XCTAssertNil(lost.published.quotedValue)
        XCTAssertNil(exact.option("o:72016")?.result?.isWinner, "an open sibling stays open")
        let refused = try XCTUnwrap(exact.option("o:72017"))
        XCTAssertEqual(refused.published.valueState, "refused")
        XCTAssertEqual(refused.sourceEvidence, [])
        XCTAssertEqual(exact.complete, false)

        var dict = try object(Self.seriesURL)
        dict.removeValue(forKey: "series_question_matrix")
        XCTAssertNil(try decode(RelatedFuturesResponse.self, dict).seriesQuestionMatrix)
        dict["series_question_matrix"] = "garbage"
        XCTAssertNil(try decode(RelatedFuturesResponse.self, dict).seriesQuestionMatrix)
    }

    func testResultStatesMapToAGradeOnlyForWonAndLost() {
        func grade(_ state: String) -> Bool? { QuestionMatrixResult(state: state, evidenceKind: nil).isWinner }
        XCTAssertEqual(grade("won"), true)
        XCTAssertEqual(grade("lost"), false)
        XCTAssertNil(grade("void"), "reserved; decoders accept it as no grade")
        XCTAssertNil(grade("unknown"))
        XCTAssertNil(grade("open"))
    }

    // MARK: - Selection (§11, R6)

    func testASelectionResolvesByKeysAndBecomesUnavailableInsteadOfJumping() throws {
        let m = try matrix()
        let pick = QuestionMatrixSelection(scope: .game, questionKey: "m:71003", optionKey: "o:72006")
        guard case .available(let q, let option, .none) = pick.resolve(in: m) else { return XCTFail("available") }
        XCTAssertEqual(q.questionKey, "m:71003")
        XCTAssertEqual(option.label, "Draw")

        let withSource = QuestionMatrixSelection(scope: .game, questionKey: "q:count|goals|game|full_game|ge:3",
                                                 optionKey: "o:72031+72041", outcomeId: 72041)
        guard case .available(_, _, let evidence?) = withSource.resolve(in: m) else { return XCTFail("source") }
        XCTAssertEqual(evidence.source, "polymarket")

        var gone = m
        gone.questions.removeAll { $0.questionKey == "m:71003" }
        XCTAssertEqual(pick.resolve(in: gone), .unavailable(.questionGone), "never a sibling question")
        XCTAssertEqual(QuestionMatrixSelection(scope: .game, questionKey: "m:71001", optionKey: "o:72002")
            .resolve(in: m), .unavailable(.optionGone), "a missing leg is not selectable")
        XCTAssertEqual(QuestionMatrixSelection(scope: .game, questionKey: runs8, optionKey: "o:72012", outcomeId: 99)
            .resolve(in: m), .unavailable(.sourceGone), "never another source")
        XCTAssertEqual(pick.resolve(in: nil), .unavailable(.noMatrix))

        let series = try XCTUnwrap(try decode(RelatedFuturesResponse.self, object(Self.seriesURL)).seriesQuestionMatrix)
        XCTAssertEqual(QuestionMatrixSelection(scope: .game, questionKey: "m:71008", optionKey: "o:72013")
            .resolve(in: series), .unavailable(.wrongScope), "a Game pick is never read from the Series matrix")
    }

    func testTheTwoScopesNeverShareASectionKey() {
        XCTAssertEqual(QuestionMatrixScope.game.sectionKey("m:1"), "gameQuestions:m:1")
        XCTAssertEqual(QuestionMatrixScope.series.sectionKey("m:1"), "seriesQuestions:m:1")
        for prefix in ["props:", "duringProps:", "other:", "matchups:", "totals:"] {
            XCTAssertFalse(QuestionMatrixScope.game.sectionKey("x").hasPrefix(prefix))
            XCTAssertFalse(QuestionMatrixScope.series.sectionKey("x").hasPrefix(prefix))
        }
    }

    // MARK: - #9524 fences

    func testEveryReturnedOptionIsAFencedRowInItsOwnSection() throws {
        let rows = GameMarketsPriceReconciliation.rows(try game())
        let matrixRows = rows.filter { $0.key.hasPrefix("gameQuestions:") }
        XCTAssertEqual(matrixRows.count, 13)
        let count = try XCTUnwrap(matrixRows.first { $0.key == "gameQuestions:\(runs8):o:72012" })
        XCTAssertEqual(count.prices, [0.6, 0.6], "published value and the contributor's raw leg")
        XCTAssertEqual(count.contributors, ["72012"])
        XCTAssertEqual(count.markets, [71005])
        let refused = try XCTUnwrap(matrixRows.first { $0.key.hasSuffix(":o:72031+72041") })
        XCTAssertFalse(refused.priced, "an unblended pair publishes no price")
        XCTAssertTrue(rows.contains { $0.key.hasPrefix("totals:") }, "the legacy row stays its own row")
    }

    func testAMatrixPriceThatMovesWithoutItsClockIsHeldAndMovesWithIt() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let first = try game()
        let shown = GameMarketsPriceReconciliation.adopting(first, over: nil, fence: &fence)

        let stale = try game(try editing(runs8) { setFirstOption(&$0, value: 0.65) })
        let held = GameMarketsPriceReconciliation.adopting(stale, over: shown, fence: &fence)
        XCTAssertEqual(held.gameQuestionMatrix?.question(runs8)?.options[0].published.value, 0.6,
                       "a moved price with no newer clock is refused")

        let fresh = try game(try editing(runs8, revision: t2) { setFirstOption(&$0, value: 0.65) })
        let next = GameMarketsPriceReconciliation.adopting(fresh, over: held, fence: &fence)
        XCTAssertEqual(next.gameQuestionMatrix?.question(runs8)?.options[0].published.value, 0.65)
    }

    func testAConflictingQuestionIsHeldWholeAndItsSiblingsStillMove() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let shown = GameMarketsPriceReconciliation.adopting(try game(), over: nil, fence: &fence)

        var dict = try editing(homeSpread, revision: t2) { setFirstOption(&$0, value: 0.55) }
        dict = try duplicatingFirstOption(of: runs8, in: dict, value: 0.9)
        let next = GameMarketsPriceReconciliation.adopting(try game(dict), over: shown, fence: &fence)
        let count = try XCTUnwrap(next.gameQuestionMatrix?.question(runs8))
        XCTAssertEqual(count.options.map(\.published.value), [0.6], "the held verified question, never the conflict")
        XCTAssertEqual(next.gameQuestionMatrix?.question(homeSpread)?.options[0].published.value, 0.55,
                       "an unrelated question still advances")

        var cold = GameMarketsPriceReconciliation.Fence()
        let firstSight = GameMarketsPriceReconciliation.adopting(try game(dict), over: nil, fence: &cold)
        XCTAssertNil(firstSight.gameQuestionMatrix?.question(runs8), "nothing verified to show: withheld")
        XCTAssertNotNil(firstSight.gameQuestionMatrix?.question(homeSpread))
    }
}
