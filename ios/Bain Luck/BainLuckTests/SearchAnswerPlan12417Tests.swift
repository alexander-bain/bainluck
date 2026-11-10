import XCTest
@testable import Bain_Luck

/// #12417 — Siri's "Get Probability" and Spotlight read the server's `answer`
/// (search answer contract v0, #12290). Tested against the reader walk's 37
/// searches (`evals/reader-walk/queries/search-v1.json`, PR #12541), each with
/// the answer the contract says it returns and the plan the app should make.
final class SearchAnswerPlan12417Tests: XCTestCase {

    private struct Fixture: Decodable {
        struct Row: Decodable {
            let q: String
            let plan: String
            let entities: [String]
        }
        let rows: [Row]
    }

    private static func fixtureData() throws -> Data {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures12417/reader-walk-37.json")
        return try Data(contentsOf: url)
    }

    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    /// Each row's `response`, decoded the way the app decodes search.
    private static func responses() throws -> [SearchResponse] {
        let data = try fixtureData()
        let raw = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let rows = try XCTUnwrap(raw["rows"] as? [[String: Any]])
        return try rows.map { row in
            let response = try JSONSerialization.data(withJSONObject: try XCTUnwrap(row["response"]))
            return try decoder().decode(SearchResponse.self, from: response)
        }
    }

    func testAllThirtySevenSearchesGetThePlanTheirAnswerCallsFor() throws {
        let fixture = try Self.decoder().decode(Fixture.self, from: Self.fixtureData())
        let responses = try Self.responses()
        XCTAssertEqual(fixture.rows.count, 37)
        for (row, response) in zip(fixture.rows, responses) {
            let plan = SearchAnswerPlan12417.plan(for: response)
            XCTAssertEqual(plan.name, row.plan, "\"\(row.q)\"")
            XCTAssertEqual(plan.entities.map(\.id), row.entities, "\"\(row.q)\"")
        }
    }

    func testAGameOrAnOutcomeIsOneEntitySoSiriAnswersAtOnce() throws {
        let responses = try Self.responses()
        let fixture = try Self.decoder().decode(Fixture.self, from: Self.fixtureData())
        for (row, response) in zip(fixture.rows, responses) where row.plan == "game" || row.plan == "outcome" {
            XCTAssertEqual(SearchAnswerPlan12417.plan(for: response).entities.count, 1, "\"\(row.q)\"")
        }
        let patriots = try XCTUnwrap(zip(fixture.rows, responses).first { $0.0.q == "patriots super bowl" }?.1)
        let entity = try XCTUnwrap(SearchAnswerPlan12417.plan(for: patriots).entities.first)
        XCTAssertEqual(entity.kind, .market)
        XCTAssertEqual(entity.recordID, 501)
        XCTAssertEqual(entity.outcomeID, 7001, "the named outcome rides the entity, so nothing asks \"Which outcome?\"")
        XCTAssertEqual(entity.title, "New England Patriots · NFL Super Bowl Winner")
    }

    func testOnlyAWholeMarketLeavesTheOutcomeToTheReader() throws {
        let responses = try Self.responses()
        let fixture = try Self.decoder().decode(Fixture.self, from: Self.fixtureData())
        for (row, response) in zip(fixture.rows, responses) where row.plan == "market" {
            let entity = try XCTUnwrap(SearchAnswerPlan12417.plan(for: response).entities.first, row.q)
            XCTAssertNil(entity.outcomeID, "\"\(row.q)\": a whole market asks \"Which outcome?\"")
        }
    }

    func testASetIsAShortList() throws {
        let responses = try Self.responses()
        let fixture = try Self.decoder().decode(Fixture.self, from: Self.fixtureData())
        let weekTen = try XCTUnwrap(zip(fixture.rows, responses).first { $0.0.q == "nfl week 10" }?.1)
        XCTAssertEqual(weekTen.answer?.set?.items.count, 14)
        XCTAssertEqual(SearchAnswerPlan12417.plan(for: weekTen).entities.count, SearchAnswerPlan12417.setLimit)
    }

    func testNullOrABestGuessFallsBackToTodaysList() throws {
        let responses = try Self.responses()
        let fixture = try Self.decoder().decode(Fixture.self, from: Self.fixtureData())
        let byQuery = Dictionary(uniqueKeysWithValues: zip(fixture.rows.map(\.q), responses))
        let giants = try XCTUnwrap(byQuery["giants"])
        XCTAssertNil(giants.answer)
        XCTAssertEqual(SearchAnswerPlan12417.plan(for: giants).entities.map(\.id),
                       GameOrMarketCatalog10873.listEntities(from: giants).map(\.id), "null is today's list, unchanged")
        let typo = try XCTUnwrap(byQuery["patroits"])
        XCTAssertEqual(typo.answer?.exact, false)
        let offered = SearchAnswerPlan12417.plan(for: typo).entities.map(\.id)
        XCTAssertEqual(offered.first, "game-\(typo.answer?.game?.id ?? -1)", "a guess goes first in the list")
        XCTAssertGreaterThan(offered.count, 1, "a guess is never offered alone, so Siri doesn't speak it as the answer")
    }

    // MARK: - Decoding the field

    private func response(answer: String) throws -> SearchResponse {
        let json = #"{"query":"x","results":[{"id":1,"home_team":"H","away_team":"A"}],"futures":[],"answer":"# + answer + "}"
        return try Self.decoder().decode(SearchResponse.self, from: Data(json.utf8))
    }

    func testAnOlderServerWithoutAnswerStillDecodes() throws {
        let json = #"{"query":"x","results":[],"futures":[]}"#
        XCTAssertNil(try Self.decoder().decode(SearchResponse.self, from: Data(json.utf8)).answer)
    }

    func testAnUnknownKindOrAMalformedAnswerReadsAsNoAnswer() throws {
        XCTAssertNil(try response(answer: #"{"kind":"player","exact":true}"#).answer)
        XCTAssertNil(try response(answer: #""celtics""#).answer)
        XCTAssertEqual(try SearchAnswerPlan12417.plan(for: response(answer: #"{"kind":"player","exact":true}"#)).name, "list")
    }

    func testAKindMissingItsObjectFallsBackToTodaysList() throws {
        let plan = SearchAnswerPlan12417.plan(for: try response(answer: #"{"kind":"game","exact":true}"#))
        XCTAssertEqual(plan.name, "list")
        XCTAssertEqual(plan.entities.map(\.id), ["game-1"])
    }

    func testAMarketSentAsAFamilyRowReadsItsHeadline() throws {
        let family = #"{"kind":"market","exact":true,"market":{"family_key":"f","label":"Super Bowl","headline":{"id":501,"name":"NFL Super Bowl Winner"},"members":[]}}"#
        XCTAssertEqual(try response(answer: family).answer?.market?.id, 501)
    }

    func testAnOmittedExactIsNotExact() throws {
        let plan = SearchAnswerPlan12417.plan(
            for: try response(answer: #"{"kind":"game","game":{"id":7,"home_team":"H","away_team":"A"}}"#))
        XCTAssertEqual(plan.name, "list", "an answer that doesn't say it's exact is a guess")
    }

    // MARK: - Identifiers and the intent

    func testANamedOutcomeHasItsOwnIdentifier() {
        XCTAssertEqual(GameOrMarketEntity10873.outcomeIdentifier(marketID: 501, outcomeID: 7001), "outcome-501-7001")
        XCTAssertEqual(GameOrMarketEntity10873.outcomeReference("outcome-501-7001")?.outcomeID, 7001)
        XCTAssertNil(GameOrMarketEntity10873.outcomeReference("market-501-7001"), "never read as an outcome entity's id")
        XCTAssertNil(GameOrMarketEntity10873.reference("outcome-501-7001"), "never read as a plain market")
        XCTAssertNil(GameOrMarketEntity10873.outcomeReference("outcome-501-07001"))
    }

    func testTheIntentAnswersANamedOutcomeWithoutAsking() throws {
        let source = try Self.source("Bain Luck/Intents/BainLuckIntents10873.swift").filter { !$0.isWhitespace }
        let answered = try XCTUnwrap(source.range(of: "ifletnamed=subject.outcomeID,market.outcomes.contains(where:{$0.id==named}){returnProbabilityAnswer10873.market(market,outcomeID:named,now:now)}"))
        let asked = try XCTUnwrap(source.range(of: "dialog:\"Whichoutcome?\""))
        XCTAssertLessThan(answered.lowerBound, asked.lowerBound, "the named outcome is answered before anything asks")
    }

    func testThePlanReadsTheAnswerAndNeverMakesOne() throws {
        let code = try Self.source("Bain Luck/Intents/SearchAnswerPlan12417.swift")
            .components(separatedBy: "\n").filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("///") }
            .joined(separator: "\n")
        for field in [".teams", ".collections", ".eventConcepts", ".collectionDiscovery", "fetchSearch"] {
            XCTAssertFalse(code.contains(field), "a second resolver reads `\(field)`; only the server's answer may decide")
        }
    }

    private static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
