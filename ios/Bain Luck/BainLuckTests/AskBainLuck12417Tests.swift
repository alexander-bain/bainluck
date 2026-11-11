import XCTest
@testable import Bain_Luck

/// #12417 — "Ask Bain Luck", then the reader's own words, answered through the
/// app's search (Alex, Wed Nov 11: Siri and Spotlight are an extension of search).
final class AskBainLuck12417Tests: XCTestCase {

    // MARK: - The spoken framing, dropped before search

    /// The phrasings measured against live search on Wed Nov 11: the framing
    /// that found nothing is gone, and the name is left for search to resolve.
    func testTheFramingAroundANameIsDropped() {
        XCTAssertEqual(SpokenRequest12417.queries(from: "What does Bain Luck say about the Celtics tonight?"),
                       ["celtics tonight", "celtics"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "Will the Patriots win this weekend"),
                       ["patriots win this weekend", "patriots"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "chances the Lakers win"), ["lakers win", "lakers"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "Who’s favored in the Kentucky governor race?"),
                       ["kentucky governor race", "kentucky governor"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "celtics game"), ["celtics game", "celtics"])
    }

    func testANameAloneIsSearchedAsSpokenOnce() {
        XCTAssertEqual(SpokenRequest12417.queries(from: "  Patriots  "), ["patriots"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "super bowl"), ["super bowl"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "games tonight"), ["games tonight", "games"])
    }

    func testFramingIsOnlyEverAWholeWord() {
        XCTAssertEqual(SpokenRequest12417.queries(from: "Dodgers"), ["dodgers"], "\"do\" is not the start of Dodgers")
        XCTAssertEqual(SpokenRequest12417.queries(from: "Islanders"), ["islanders"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "Theo Von"), ["theo von"])
        XCTAssertEqual(SpokenRequest12417.queries(from: "Winnipeg"), ["winnipeg"], "a trailing \"win\" is a whole word")
    }

    func testNothingButFramingSearchesNothing() {
        XCTAssertEqual(SpokenRequest12417.queries(from: "what are the chances?"), [])
        XCTAssertEqual(SpokenRequest12417.queries(from: "   "), [])
        XCTAssertEqual(SpokenRequest12417.emptyReply, "Say a team, a game or a market, and Bain Luck will look it up.")
        XCTAssertEqual(SpokenRequest12417.notFoundReply("kentucky governor race"),
                       "Bain Luck didn't find a game or market for “kentucky governor race”.")
    }

    // MARK: - What one search answer does

    private func game(_ id: Int) -> GameOrMarketEntity10873 {
        GameOrMarketEntity10873(kind: .game, recordID: id, title: "Game \(id)", detail: nil)
    }

    func testAnExactAnswerIsAnsweredAtOnce() {
        guard case .answer(let entity) = AskChoice12417.decide(.game(game(1))) else { return XCTFail("game") }
        XCTAssertEqual(entity.recordID, 1)
        let market = GameOrMarketEntity10873(kind: .market, recordID: 9, title: "M", detail: nil)
        guard case .answer = AskChoice12417.decide(.market(market)) else { return XCTFail("market") }
    }

    func testAListOffersAHandfulAndNeverSpeaksTheFirstAsTheAnswer() {
        guard case .ask(let options) = AskChoice12417.decide(.list((1...20).map(game))) else { return XCTFail("list") }
        XCTAssertEqual(options.map(\.recordID), [1, 2, 3, 4, 5])
        guard case .ask = AskChoice12417.decide(.set([game(1), game(2)])) else { return XCTFail("set") }
    }

    func testALoneRowIsTheOnlyChoiceAndNoRowIsNotFound() {
        guard case .answer(let only) = AskChoice12417.decide(.list([game(7)])) else { return XCTFail("one") }
        XCTAssertEqual(only.recordID, 7)
        guard case .none = AskChoice12417.decide(.list([])) else { return XCTFail("none") }
    }

    // MARK: - One search, one answer, no second resolver

    func testTheIntentReadsTheSearchAnswerAndTheSameProbabilityAnswer() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Intents/AskBainLuck12417.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("APIClient.shared.fetchSearch(query: query)"), "the Search tab's request")
        XCTAssertTrue(source.contains("SearchAnswerPlan12417.plan(for: response)"), "read as Get Probability reads it")
        XCTAssertTrue(source.contains("GetProbabilityIntent10873.answer(subject: subject"), "the same spoken answer")
        for other in ["response.teams", "response.collections", "fetchEvents(", "fetchFutures("] {
            XCTAssertFalse(source.contains(other), "no resolver of its own: \(other)")
        }
    }

    func testSiriListensForAskBainLuck() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Intents/BainLuckIntents10873.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        let shortcut = try XCTUnwrap(source.range(of: "intent: AskBainLuckIntent12417()"))
        let phrases = String(source[shortcut.upperBound...].prefix(400))
        for phrase in ["\"Ask \\(.applicationName)\"", "\"What does \\(.applicationName) say\""] {
            XCTAssertTrue(phrases.contains(phrase), phrase)
        }
        XCTAssertFalse(phrases.lowercased().contains("question"), "a market is not a \"question\" (#11547)")
    }
}
