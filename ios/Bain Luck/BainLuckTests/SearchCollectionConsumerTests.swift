import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

/// Representative producer cards from the banked #9653 fixtures, placed into
/// a search envelope. These are contract specimens, not published/live data.
private enum SearchCollectionFixture {
    static func cards(_ name: String) throws -> [[String: Any]] {
        let data = try ContainerHubFixture.responseData(name)
        return (try JSONSerialization.jsonObject(with: data) as! [String: Any])["collections"] as! [[String: Any]]
    }

    static func decode(cards: Any? = nil, query: String = "NFL", mutate: ((inout [String: Any]) -> Void)? = nil) throws -> SearchResponse {
        var object: [String: Any] = ["query": query, "results": [], "futures": []]
        if let cards { object["collections"] = cards }
        mutate?(&object)
        return try decodeObject(object)
    }

    static func decodeObject(_ object: [String: Any]) throws -> SearchResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchResponse.self, from: JSONSerialization.data(withJSONObject: object))
    }
}

final class SearchCollectionConsumerTests: XCTestCase {
    func testAbsentNullAndEmptyCollectionsKeepOldServerBehavior() throws {
        for response in [
            try SearchCollectionFixture.decode(),
            try SearchCollectionFixture.decode(cards: NSNull()),
            try SearchCollectionFixture.decode(cards: []),
        ] {
            XCTAssertEqual(response.query, "NFL")
            XCTAssertTrue(SearchCollectionRows.entries(in: response).isEmpty)
        }
    }

    @MainActor
    func testValidNFLAndMLBProducerCardsKeepIdentityEditionCountsAndCanonicalRoutes() throws {
        let cards = try SearchCollectionFixture.cards("search_by_games") + SearchCollectionFixture.cards("browse_mlb")
        let response = try SearchCollectionFixture.decode(cards: cards)
        let entries = SearchCollectionRows.entries(in: response)
        XCTAssertEqual(entries.map(\.id), ["nfl-2026-week-5", "mlb-2026-postseason"])
        XCTAssertEqual(entries.map { $0.collection.name }, ["NFL 2026 · Week 5", "MLB 2026 · Postseason"])
        XCTAssertEqual(entries.map(\.subtitle), ["4 games · 1 question", "9 games · 6 questions"])
        XCTAssertEqual(entries.map { SearchCollectionRows.editionLabel(for: $0) }, ["NFL 2026 · Week 5", "MLB 2026 · Postseason"])
        XCTAssertEqual(entries.map(\.route), [
            .containerHub(slug: "nfl-2026-week-5", name: "NFL 2026 · Week 5"),
            .containerHub(slug: "mlb-2026-postseason", name: "MLB 2026 · Postseason"),
        ])
        XCTAssertEqual(entries.map { $0.collection.revision }, [4, 2])
    }

    func testMalformedOptionalFieldOrSiblingDoesNotEraseOrdinaryResults() throws {
        var object = try JSONSerialization.jsonObject(with: Data(SearchProdFixture.usOpenJSON.utf8)) as! [String: Any]
        let old = try SearchCollectionFixture.decodeObject(object)
        let mlb = try SearchCollectionFixture.cards("browse_mlb")
        for optional in ["wrong_type" as Any, ["not": "an array"] as Any,
                         [["id": "bad", "type": "collection"]] + mlb] {
            object["collections"] = optional
            let updated = try SearchCollectionFixture.decodeObject(object)
            XCTAssertEqual(updated.futures.map(\.id), old.futures.map(\.id))
            XCTAssertEqual(updated.futuresFamilies?.map(\.familyKey), old.futuresFamilies?.map(\.familyKey))
            XCTAssertEqual(updated.eventConcepts?.map(\.key), old.eventConcepts?.map(\.key))
            XCTAssertEqual(updated.pagination?.totalResults, old.pagination?.totalResults)
        }
        XCTAssertEqual(SearchCollectionRows.entries(in: try SearchCollectionFixture.decodeObject(object)).map(\.id), ["mlb-2026-postseason"])
    }

    func testWithdrawnUnpublishedUnknownAndUnsupportedCollectionRowsFailClosed() throws {
        let source = try XCTUnwrap(SearchCollectionFixture.cards("browse_mlb").first)
        for state in ["unpublished", "withdrawn", "revoked", "new_state"] {
            var card = source
            card["state"] = state
            let response = try SearchCollectionFixture.decode(cards: [card])
            XCTAssertTrue(SearchCollectionRows.entries(in: response).isEmpty, state)
        }
        var unknown = source
        unknown["type"] = "future_kind"
        XCTAssertTrue(SearchCollectionRows.entries(in: try SearchCollectionFixture.decode(cards: [unknown])).isEmpty)
    }

    func testMismatchedEditionSlugDestinationAndMissingRevisionAreRefused() throws {
        let source = try XCTUnwrap(SearchCollectionFixture.cards("browse_mlb").first)
        let mutations: [(inout [String: Any]) -> Void] = [
            { $0["edition"] = ["kind": "mlb_postseason", "league": "mlb", "season": 2025] },
            { $0["edition"] = ["kind": "nfl_week", "league": "nfl", "season": 2026, "stage": "Regular Season", "week": 5] },
            { $0["edition"] = ["kind": "unknown", "league": "mlb", "season": 2026] },
            { $0["edition"] = ["kind": "mlb_postseason", "league": "nba", "season": 2026] },
            { $0["slug"] = "mlb-2026-postseason/other" },
            { $0["destination"] = ["kind": "container", "slug": "mlb-2026-postseason", "api": "/api/containers/nfl-2026-week-5"] },
            { $0.removeValue(forKey: "revision") },
            { $0["game_count"] = 0; $0["question_count"] = 0 },
        ]
        for mutation in mutations {
            var card = source
            mutation(&card)
            let response = try SearchCollectionFixture.decode(cards: [card])
            XCTAssertTrue(SearchCollectionRows.entries(in: response).isEmpty)
        }
    }

    func testMalformedFirstCardAndDuplicatesKeepOneHealthyAnswerInServerOrder() throws {
        let nfl = try SearchCollectionFixture.cards("search_by_games")
        let mlb = try SearchCollectionFixture.cards("browse_mlb")
        let cards = [["type": "collection", "id": "bad"]] + mlb + nfl + mlb
        let response = try SearchCollectionFixture.decode(cards: cards)
        XCTAssertEqual(SearchCollectionRows.entries(in: response).map(\.id), ["mlb-2026-postseason", "nfl-2026-week-5"])
    }

    func testCollectionsOnlyAnswerCountsAsContentAndInvalidRowsDoNot() throws {
        let valid = try SearchCollectionFixture.decode(cards: SearchCollectionFixture.cards("browse_mlb"))
        let empty = try SearchCollectionFixture.decode()
        for (response, expected) in [(valid, SearchAnswerState.present), (empty, .empty)] {
            let state = SearchAnswerState.resolve(hasEvents: false, hasFutures: false, hasFamilies: false,
                hasConcepts: false, hasTeams: false,
                hasHubs: !SearchCollectionRows.entries(in: response).isEmpty, degraded: nil)
            XCTAssertEqual(state, expected)
        }
    }

    func testRequiredOrdinarySearchFieldsStillFailInsteadOfBeingRelaxed() throws {
        XCTAssertThrowsError(try SearchCollectionFixture.decode { $0.removeValue(forKey: "results") })
        XCTAssertThrowsError(try SearchCollectionFixture.decode { $0["futures"] = "bad" })
    }

    func testSearchViewUsesInPlaceNavigationAndCollectionAwareEmptyState() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let source = try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/SearchView.swift"), encoding: .utf8)
        let start = try XCTUnwrap(source.range(of: "let collectionEntries = SearchCollectionRows.entries(in: results)"))
        let end = try XCTUnwrap(source.range(of: "// Did you mean", range: start.upperBound..<source.endIndex))
        let section = String(source[start.lowerBound..<end.lowerBound])
        XCTAssertTrue(section.contains("if !collectionEntries.isEmpty"))
        XCTAssertTrue(section.contains("NavigationLink(value: entry.route)"))
        XCTAssertFalse(section.contains("viewModel.query ="))
        XCTAssertFalse(section.contains("fetchContainerDiscovery"))
        XCTAssertTrue(source.contains("hasHubs: !hubs.isEmpty || !collectionEntries.isEmpty"))
        XCTAssertTrue(source.contains(".navigationDestination(for: Route.self)"))
    }
}

private actor SearchCollectionTransport {
    let response: SearchResponse
    private(set) var calls: [(String, String?)] = []
    init(response: SearchResponse) { self.response = response }
    func fetch(_ query: String, sport: String?) -> SearchResponse {
        calls.append((query, sport))
        return response
    }
}

final class SearchCollectionViewModelTests: XCTestCase {
    @MainActor
    func testCanonicalHubPushAndBackKeepQueryFilterAndResultsWithoutAnotherSearch() async throws {
        let response = try SearchCollectionFixture.decode(cards: SearchCollectionFixture.cards("browse_mlb"), query: "Yankees")
        let transport = SearchCollectionTransport(response: response)
        let vm = SearchViewModel(searchFetch: { query, sport in await transport.fetch(query, sport: sport) })
        vm.query = "Yankees"
        vm.selectedSport = "baseball_mlb"
        await vm.search()
        let answer = try XCTUnwrap(vm.results)
        let entry = try XCTUnwrap(SearchCollectionRows.entries(in: answer).first)
        var path = NavigationPath()
        path.append(entry.route)
        vm.cancelInFlightWork() // Existing Search onDisappear behavior.
        path.removeLast() // Route recorder only; not a rendered/live journey.
        XCTAssertTrue(path.isEmpty)
        XCTAssertEqual(vm.query, "Yankees")
        XCTAssertEqual(vm.selectedSport, "baseball_mlb")
        XCTAssertEqual(vm.results?.query, "Yankees")
        XCTAssertEqual(SearchCollectionRows.entries(in: try XCTUnwrap(vm.results)).map(\.id), [entry.id])
        let calls = await transport.calls
        XCTAssertEqual(calls.count, 1)
        XCTAssertEqual(calls.first?.0, "Yankees")
        XCTAssertEqual(calls.first?.1, "baseball_mlb")
    }

    @MainActor
    func testExistingClearRemovesCollectionAnswerAlongWithOrdinaryResults() async throws {
        let response = try SearchCollectionFixture.decode(cards: SearchCollectionFixture.cards("search_by_games"))
        let vm = SearchViewModel(searchFetch: { _, _ in response })
        vm.query = "NFL"
        await vm.search()
        XCTAssertFalse(SearchCollectionRows.entries(in: try XCTUnwrap(vm.results)).isEmpty)
        vm.clear()
        XCTAssertEqual(vm.query, "")
        XCTAssertNil(vm.results)
        XCTAssertFalse(vm.loading)
    }
}
