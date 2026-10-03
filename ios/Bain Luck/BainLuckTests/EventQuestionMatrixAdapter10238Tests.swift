import XCTest
@testable import Bain_Luck

/// Adapter tests use the published producer's route harness, with explicit
/// mutations for refused/missing/invalid cases. They do not certify current
/// provider labels, transport adoption, a mounted view or runtime focus.
@MainActor
final class EventQuestionMatrixAdapter10238Tests: XCTestCase {
    private let countKey = "q:count|points|game|full_game|ge:211"

    private func fixture(_ scope: QuestionMatrixScope) throws -> EventQuestionMatrix {
        let name = scope == .game
            ? "game-markets-10238-question-matrix.route-harness.json"
            : "related-futures-10238-series-matrix.route-harness.json"
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures").appendingPathComponent(name)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        return try decode(try XCTUnwrap(body[scope == .game ? "game_question_matrix" : "series_question_matrix"] as? [String: Any]))
    }

    private func decode(_ body: [String: Any]) throws -> EventQuestionMatrix {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventQuestionMatrix.self, from: JSONSerialization.data(withJSONObject: body))
    }

    private func row(_ matrix: EventQuestionMatrix, _ key: String, scope: QuestionMatrixScope = .game) throws -> EventQuestionMatrixAdapter.Row {
        try XCTUnwrap(EventQuestionMatrixAdapter.rows(in: matrix, scope: scope).first { $0.id.questionKey == key })
    }

    private func detail(_ selection: QuestionMatrixSelection, _ matrix: EventQuestionMatrix) throws -> EventQuestionMatrixAdapter.Detail {
        guard case .available(let detail) = EventQuestionMatrixAdapter.detail(for: selection, in: matrix) else {
            XCTFail("exact served selection must resolve")
            throw NSError(domain: "Adapter10238", code: 1)
        }
        return detail
    }

    private func replacing(_ option: QuestionMatrixOption, value: Double?, state: String = "quoted",
                           result: QuestionMatrixResult? = nil,
                           comparison: QuestionMatrixComparison? = nil) -> QuestionMatrixOption {
        QuestionMatrixOption(optionKey: option.optionKey, label: option.label, side: option.side,
            marketIds: option.marketIds, contributorOutcomeIds: option.contributorOutcomeIds,
            published: QuestionMatrixPublished(value: value, valueState: state, basis: option.published.basis,
                source: option.published.source, observedAt: option.published.observedAt),
            sourceEvidence: option.sourceEvidence, result: result, comparison: comparison)
    }

    func testPublishedZeroIsAQuoteAndRefusedNonfiniteOrOutOfRangeNeverBecomeQuotes() throws {
        var matrix = try fixture(.game)
        let index = try XCTUnwrap(matrix.questions.firstIndex { $0.questionKey == "m:108" })
        let zero = try row(matrix, "m:108").options.first { $0.label == "Tie" }
        XCTAssertEqual(zero?.value, .quoted(0))
        let original = matrix.questions[index].options[0]
        for value in [Double.nan, Double.infinity, -Double.infinity, -0.1, 1.1] {
            matrix.questions[index].options[0] = replacing(original, value: value)
            XCTAssertEqual(try row(matrix, "m:108").options[0].value, .unavailable)
        }
        matrix.questions[index].options[0] = replacing(original, value: 0.7, state: "refused")
        let refused = try detail(try row(matrix, "m:108").options[0].selection, matrix)
        XCTAssertEqual(refused.option.value, .unavailable)
        XCTAssertTrue(refused.sources.allSatisfy { $0.probability == nil }, "raw evidence cannot revive a refused quote")
    }

    func testSeriesKeepsPublished70And29AndRaw99SumWithoutNormalization() throws {
        let matrix = try fixture(.series)
        let winner = try row(matrix, "m:900", scope: .series)
        XCTAssertEqual(winner.options.map(\.value), [.quoted(0.7), .quoted(0.29)])
        XCTAssertEqual(winner.sourceTotals.first?.rawSum, 0.99)
        XCTAssertEqual(try detail(winner.options[0].selection, matrix).sources.first?.probability, 0.7)
        XCTAssertEqual(try detail(winner.options[1].selection, matrix).sources.first?.probability, 0.29)
        XCTAssertEqual(winner.options.map(\.label), ["Boston Red Sox", "New York Yankees"])
    }

    func testPublishedMainAndHistoricalUnderLabelAreNotReinterpretedAsRawOrComplement() throws {
        let matrix = try fixture(.game)
        let count = try row(matrix, countKey)
        let served = try XCTUnwrap(matrix.question(countKey))
        XCTAssertEqual(count.kind, .countThreshold)
        XCTAssertEqual(count.label, served.label)
        // This is the historical harness label, not endorsement of today's
        // upstream label carriage. The adapter must not parse it into a side.
        XCTAssertEqual(count.options[0].label, "Under 210.5")
        XCTAssertEqual(count.options[0].value, .quoted(0.52))
        let selected = try detail(count.options[0].selection, matrix)
        XCTAssertEqual(selected.sources.first?.side, served.options[0].sourceEvidence?.first?.legSide)
        XCTAssertEqual(selected.sources.first?.probability, served.options[0].sourceEvidence?.first?.rawProbability)
        XCTAssertEqual(count.options.count, served.options.count)
        let binary = try row(matrix, "m:106")
        XCTAssertEqual(binary.options.count, 1)
        XCTAssertEqual(binary.options[0].label, "Yes")
        XCTAssertEqual(binary.options[0].value, .quoted(0.7), "no derived No/30% option")
    }

    func testExactSourceDisappearanceNeverFallsBackToOtherContributorOrOtherScope() throws {
        var matrix = try fixture(.series)
        let winner = try row(matrix, "m:900", scope: .series)
        let selection = QuestionMatrixSelection(scope: .series, questionKey: "m:900", optionKey: winner.options[0].selection.optionKey, outcomeId: 901)
        XCTAssertEqual(try detail(selection, matrix).selectedSource?.outcomeID, 901)
        matrix.questions[0].options[0].sourceEvidence = [QuestionMatrixSourceEvidence(source: "polymarket", marketId: 999, outcomeId: 999, legSide: "home", rawProbability: 0.8, observedAt: nil)]
        XCTAssertEqual(EventQuestionMatrixAdapter.detail(for: selection, in: matrix), .unavailable(.sourceGone))
        matrix.questions[0].options.removeFirst()
        XCTAssertEqual(EventQuestionMatrixAdapter.detail(for: selection, in: matrix), .unavailable(.optionGone))
        matrix.questions.removeAll()
        XCTAssertEqual(EventQuestionMatrixAdapter.detail(for: selection, in: matrix), .unavailable(.questionGone))
        XCTAssertEqual(EventQuestionMatrixAdapter.detail(for: selection, in: try fixture(.game)), .unavailable(.wrongScope))
    }

    func testGameSettledDoesNotRewriteTheSeparateOpenSeriesLifecycle() throws {
        var game = try fixture(.game)
        game.questions[0].lifecycle = QuestionMatrixLifecycle(state: "settled", marketStatus: "closed")
        game.questions[0].options[0] = replacing(game.questions[0].options[0], value: nil, state: "result", result: QuestionMatrixResult(state: "won", evidenceKind: "resolved"))
        XCTAssertEqual(try row(game, countKey).options[0].value, .won)
        let series = try row(try fixture(.series), "m:900", scope: .series)
        XCTAssertEqual(series.lifecycle?.state, "open")
        XCTAssertEqual(series.options[0].value, .quoted(0.7))
    }

    func testTypedKindsAndServedMetadataArePreservedWithoutParsingLabels() throws {
        let matrix = try fixture(.game)
        for question in matrix.questions {
            let presentation = try row(matrix, question.questionKey)
            XCTAssertEqual(presentation.kind, question.columnKind)
            XCTAssertEqual(presentation.label, question.label)
            XCTAssertEqual(presentation.quantity, question.quantity)
            XCTAssertEqual(presentation.period, question.period)
            XCTAssertEqual(presentation.subject, question.subject)
            XCTAssertEqual(presentation.predicate, question.predicate)
            XCTAssertEqual(presentation.options.map(\.side), question.options.map(\.side))
        }
        for kind in ["rank_predicate", "signed_handicap", "count_threshold", "unknown_future_kind"] {
            let body: [String: Any] = ["display_scope": "game", "questions": [["question_key": "opaque", "kind": kind, "label": "Under +3.5 category is not a parser instruction", "typing": ["state": "typed"], "options": []]]]
            let only = try XCTUnwrap(EventQuestionMatrixAdapter.rows(in: try decode(body), scope: .game).first)
            XCTAssertEqual(only.kind, QuestionMatrixKind(rawValue: kind) ?? .namedOptions)
            XCTAssertEqual(only.label, "Under +3.5 category is not a parser instruction")
            XCTAssertNil(only.predicate)
            XCTAssertNil(only.quantity)
            XCTAssertTrue(only.options.isEmpty)
        }
    }

    func testMissingDisclosureUsesServedMissingIdentityAndCountsNotInventedPrices() throws {
        var matrix = try fixture(.game)
        let index = try XCTUnwrap(matrix.questions.firstIndex { $0.questionKey == countKey })
        matrix.questions[index].complete = false
        matrix.questions[index].optionCounts = QuestionMatrixOptionCounts(declared: 2, loaded: 2, returned: 1, missingIdentified: 0)
        XCTAssertFalse(try row(matrix, countKey).offersMoreOptions, "typed incomplete is not proof of a missing leg")
        matrix.questions[index].missingOptions = [QuestionMatrixMissingOption(optionKey: "missing", outcomeId: 42, label: "Exact omitted leg", side: "under", valueState: "unpriced")]
        matrix.questions[index].optionCounts = QuestionMatrixOptionCounts(declared: 2, loaded: 2, returned: 1, missingIdentified: 1)
        let shown = try row(matrix, countKey)
        XCTAssertTrue(shown.offersMoreOptions)
        XCTAssertEqual(shown.optionCounts?.missingIdentified, 1)
        XCTAssertEqual(shown.missingOptions.first?.label, "Exact omitted leg")
        XCTAssertEqual(shown.options.count, 1, "missing disclosure never manufactures a priced option")
        XCTAssertEqual(shown.complete, false)
    }

    func testUnblendedRawEvidenceStaysSeparateFromAnUnavailableMainAndResultsAreNotQuotes() throws {
        var matrix = try fixture(.game)
        let index = try XCTUnwrap(matrix.questions.firstIndex { $0.questionKey == countKey })
        let original = matrix.questions[index].options[0]
        matrix.questions[index].options[0] = replacing(original, value: nil, state: "unblended_equivalents")
        matrix.questions[index].options[0].sourceEvidence = [
            QuestionMatrixSourceEvidence(source: "kalshi", marketId: 1, outcomeId: 2, legSide: "over", rawProbability: 0.7, observedAt: nil),
            QuestionMatrixSourceEvidence(source: "polymarket", marketId: 3, outcomeId: 4, legSide: "under", rawProbability: 0.29, observedAt: nil)
        ]
        let selection = try row(matrix, countKey).options[0].selection
        let raw = try detail(selection, matrix)
        XCTAssertEqual(raw.option.value, .unavailable)
        XCTAssertEqual(raw.sources.map(\.probability), [0.7, 0.29])
        XCTAssertEqual(raw.sources.map(\.side), ["over", "under"])
        XCTAssertNil(raw.comparison)
        for (state, expected) in [("won", EventQuestionMatrixAdapter.Value.won), ("lost", .lost), ("unknown", .unavailable)] {
            matrix.questions[index].options[0] = replacing(original, value: 0.7, state: "result", result: QuestionMatrixResult(state: state, evidenceKind: "resolved"))
            let result = try detail(selection, matrix)
            XCTAssertEqual(result.option.value, expected)
            XCTAssertTrue(result.sources.allSatisfy { $0.probability == nil })
        }
    }

    func testComparisonIsPairedWithOwnLatestAndNotCarriedIntoRawSourceSelection() throws {
        var matrix = try fixture(.game)
        let index = try XCTUnwrap(matrix.questions.firstIndex { $0.questionKey == countKey })
        let original = matrix.questions[index].options[0]
        let comparison = QuestionMatrixComparison(state: "comparable", reason: nil,
            baseline: QuestionMatrixBaseline(probability: 0.4, observedAt: "2026-10-03T10:00:00Z", basis: "pregame_pin"),
            latest: QuestionMatrixLatest(probability: 0.6, observedAt: "2026-10-03T11:00:00Z"), deltaPoints: 20)
        matrix.questions[index].options[0] = replacing(original, value: 0.52, comparison: comparison)
        let selection = try row(matrix, countKey).options[0].selection
        let shown = try detail(selection, matrix)
        XCTAssertEqual(shown.option.value, .quoted(0.52))
        XCTAssertEqual(shown.comparison?.latest, 0.6)
        XCTAssertEqual(shown.comparison?.points, 20)
        XCTAssertEqual(shown.comparison?.caption, "since the saved pregame price")
        // A rejected main quote cannot gain a comparison merely because its
        // value_state string still says quoted.
        for invalid in [nil, Double.nan, Double.infinity, -0.1, 1.1] as [Double?] {
            matrix.questions[index].options[0] = replacing(original, value: invalid, comparison: comparison)
            XCTAssertNil(try detail(selection, matrix).comparison)
        }
        matrix.questions[index].options[0] = replacing(original, value: 0.52, comparison: comparison)
        let rawID = try XCTUnwrap(original.sourceEvidence?.first?.outcomeId)
        let raw = QuestionMatrixSelection(scope: .game, questionKey: countKey, optionKey: original.optionKey, outcomeId: rawID)
        XCTAssertNil(try detail(raw, matrix).comparison)
        matrix.questions[index].options[0] = replacing(original, value: 0.52, comparison: QuestionMatrixComparison(state: "comparable", reason: nil, baseline: comparison.baseline, latest: QuestionMatrixLatest(probability: .infinity, observedAt: "stamp"), deltaPoints: 20))
        XCTAssertNil(try detail(selection, matrix).comparison)
    }
}
