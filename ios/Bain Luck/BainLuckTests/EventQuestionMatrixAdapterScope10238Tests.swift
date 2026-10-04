import XCTest
@testable import Bain_Luck

/// #10238: `rows(in:scope:)` refuses a matrix or a question served for the
/// other scope. Mutants that delete either refusal survive the adapter suite,
/// so a Game read could otherwise draw Series rows (and the reverse).
@MainActor
final class EventQuestionMatrixAdapterScope10238Tests: XCTestCase {
    private func fixture(_ scope: QuestionMatrixScope) throws -> EventQuestionMatrix {
        let name = scope == .game
            ? "game-markets-10238-question-matrix.route-harness.json"
            : "related-futures-10238-series-matrix.route-harness.json"
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures").appendingPathComponent(name)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let matrix = try XCTUnwrap(body[scope == .game ? "game_question_matrix" : "series_question_matrix"] as? [String: Any])
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventQuestionMatrix.self, from: JSONSerialization.data(withJSONObject: matrix))
    }

    private func keys(_ matrix: EventQuestionMatrix, _ scope: QuestionMatrixScope) -> [String] {
        EventQuestionMatrixAdapter.rows(in: matrix, scope: scope).map(\.id.questionKey)
    }

    func testServedFixturesDrawOnlyUnderTheirOwnScope() throws {
        let game = try fixture(.game), series = try fixture(.series)
        XCTAssertEqual(keys(game, .game), game.questions.map(\.questionKey))
        XCTAssertFalse(game.questions.isEmpty)
        XCTAssertEqual(keys(game, .series), [])
        XCTAssertEqual(keys(series, .series), series.questions.map(\.questionKey))
        XCTAssertFalse(series.questions.isEmpty)
        XCTAssertEqual(keys(series, .game), [])
    }

    /// The matrix-level scope alone refuses, even when no question repeats it.
    func testMatrixScopeRefusesWhenQuestionsCarryNoScope() throws {
        var questions = try fixture(.game).questions
        for i in questions.indices { questions[i].displayScope = nil }
        let matrix = EventQuestionMatrix(displayScope: "game", questions: questions)
        XCTAssertEqual(keys(matrix, .game), questions.map(\.questionKey))
        XCTAssertEqual(keys(matrix, .series), [])
    }

    /// The question-level scope alone refuses that question and keeps its
    /// siblings in served order; an unscoped question stays.
    func testQuestionScopeRefusesOnlyTheOtherScopesQuestion() throws {
        var questions = try fixture(.game).questions
        XCTAssertGreaterThanOrEqual(questions.count, 3)
        questions[1].displayScope = "series"
        questions[2].displayScope = nil
        let matrix = EventQuestionMatrix(displayScope: nil, questions: questions)
        var expected = questions.map(\.questionKey)
        expected.remove(at: 1)
        XCTAssertEqual(keys(matrix, .game), expected)
        XCTAssertEqual(keys(matrix, .series), [questions[1].questionKey, questions[2].questionKey])
    }

    /// A contributor's raw leg outside 0...1 (or non-finite) is not shown as
    /// its quote in source detail, even under a quoted main; a valid one is.
    func testInvalidRawContributorProbabilityIsNotDisclosed() throws {
        var matrix = try fixture(.series)
        let index = try XCTUnwrap(matrix.questions.firstIndex { $0.questionKey == "m:900" })
        XCTAssertEqual(matrix.questions[index].options[0].published.valueState, "quoted")
        let raws: [Double] = [1.2, -0.1, .nan, .infinity, 0.55]
        matrix.questions[index].options[0].sourceEvidence = raws.enumerated().map { i, raw in
            QuestionMatrixSourceEvidence(source: "kalshi", marketId: 990 + i, outcomeId: 9900 + i,
                                         legSide: "home", rawProbability: raw, observedAt: nil)
        }
        let selection = QuestionMatrixSelection(scope: .series, questionKey: "m:900",
                                                optionKey: matrix.questions[index].options[0].optionKey)
        guard case .available(let detail) = EventQuestionMatrixAdapter.detail(for: selection, in: matrix) else {
            return XCTFail("exact served selection must resolve")
        }
        XCTAssertEqual(detail.sources.map(\.outcomeID), [9900, 9901, 9902, 9903, 9904])
        XCTAssertEqual(detail.sources.map(\.probability), [nil, nil, nil, nil, 0.55])
    }
}
