import XCTest
@testable import Bain_Luck

/// #10298 — Lions–Packers in search showed two favourites: the game card's
/// "Lions 56%" and, as a family headline, Polymarket's listing 61040985 as
/// "Packers 53%" (its legs are a winner and a spread, so naming a leader from
/// them is a guess). Beside its own game the listing reads "N questions on
/// this game" (#10089).
///
/// FIXTURES: the production bodies of `/api/events/search?q=lions` and
/// `/api/events/typeahead?q=lions%20packers` read 2026-10-03 08:0xZ (`/health`
/// c093c900), with `related_game_listing: {event_id: 14780566,
/// question_count: 2}` added to market 61040985 everywhere it appears — the
/// flat futures row, the family headline, the typeahead row — exactly where
/// latency's producer (PR #10299 `f32bde3b46`, not yet on production) stamps
/// it. Every other byte is as served.
@MainActor
final class SearchRelatedGameListing10298Tests: XCTestCase {
    private static let fixtures = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
    private static let listingId = 61040985

    private func decode<T: Decodable>(_ type: T.Type, _ name: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(contentsOf: Self.fixtures.appendingPathComponent(name)))
    }

    func testTheListingDecodesOnTheFlatRowAndTheFamilyHeadlineTheReaderSees() throws {
        let body = try decode(SearchResponse.self, "search-lions-10298.20261003.stamped.json")
        let flat = try XCTUnwrap(body.futures.first { $0.id == Self.listingId })
        XCTAssertEqual(flat.relatedGameListing, RelatedGameListing(eventId: 14780566, questionCount: 2))
        // The leader the row used to print is still served — the phone must
        // choose the link over it, not lose it from the payload.
        XCTAssertEqual(flat.topOutcomes?.first?.name, "Packers")

        let family = try XCTUnwrap(body.futuresFamilies?.first { $0.headline.id == Self.listingId })
        XCTAssertEqual(family.headline.relatedGameListing?.label, "2 questions on this game")
        XCTAssertTrue(family.members.allSatisfy { $0.relatedGameListing == nil }, "only the listing itself changes")
        XCTAssertEqual(body.futures.filter { $0.relatedGameListing != nil }.map(\.id), [Self.listingId])
    }

    func testTheTypeaheadRowDecodesItAndOtherRowsStayAsServed() throws {
        let body = try decode(TypeaheadResponse.self, "typeahead-lions-packers-10298.20261003.stamped.json")
        let rows = body.suggestions
        XCTAssertEqual(rows.first { $0.marketId == Self.listingId }?.relatedGameListing?.questionCount, 2)
        XCTAssertNil(rows.first { $0.marketId == 129037 }?.relatedGameListing, "NFL: 2027 Champion is not a game listing")
    }

    func testAbsentKeyDecodesNilSoTodaysRowIsUnchanged() throws {
        let json = #"{"id": 1, "name": "Packers vs. Lions", "top_outcomes": [{"name": "Packers", "probability": 0.53}], "outcome_count": 2}"#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let market = try decoder.decode(SearchFuturesMarket.self, from: Data(json.utf8))
        XCTAssertNil(market.relatedGameListing)
    }

    func testTheLabelCountsQuestions() {
        XCTAssertEqual(RelatedGameListing(eventId: 1, questionCount: 1).label, "1 question on this game")
        XCTAssertEqual(RelatedGameListing(eventId: 1, questionCount: 14).label, "14 questions on this game")
    }

    /// Both search rows and the dropdown row ask for the listing BEFORE any
    /// leader or percentage, so a stamped row can never print a favourite.
    func testEveryRowChecksTheListingBeforeItsLeader() throws {
        let source = try String(contentsOf: URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/SearchView.swift"), encoding: .utf8)
        func body(of signature: String) throws -> Substring {
            let start = try XCTUnwrap(source.range(of: signature))
            return source[start.lowerBound...].prefix(2500)
        }
        let family = try body(of: "private func searchFamilyRow(")
        let familyListing = try XCTUnwrap(family.range(of: "market.relatedGameListing"))
        let familyLeader = try XCTUnwrap(family.range(of: "SearchGrouping.leaderOutcome(market)"))
        XCTAssertLessThan(familyListing.lowerBound, familyLeader.lowerBound)

        let flat = try body(of: "private func searchFuturesRow(")
        let flatListing = try XCTUnwrap(flat.range(of: "market.relatedGameListing"))
        let flatLeader = try XCTUnwrap(flat.range(of: "market.topOutcomes?.first"))
        XCTAssertLessThan(flatListing.lowerBound, flatLeader.lowerBound)

        let typeahead = try XCTUnwrap(source.range(of: "suggestion.relatedGameListing"))
        let typeLabel = try XCTUnwrap(source.range(of: "suggestion.marketTypeLabel"))
        XCTAssertLessThan(typeahead.lowerBound, typeLabel.lowerBound)
    }
}
