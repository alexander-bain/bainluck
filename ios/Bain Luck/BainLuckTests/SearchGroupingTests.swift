import XCTest
@testable import Bain_Luck

/// #3124 — the grouped search answer.
///
/// Two halves, and the first is the one that matters: a `Decodable` that omits a
/// key does not fail, it silently yields a model with less in it. `SearchResponse`
/// dropped `event_concepts` and `futures_families` for as long as they have been
/// served and nothing anywhere went red. So these run the DECODER against the
/// verbatim production payload, not a hand-built model — a test that constructs
/// `SearchFuturesFamily` in Swift would have passed on the broken tree too.
final class SearchGroupingTests: XCTestCase {

    private func decodeFixture() throws -> SearchResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = Data(SearchProdFixture.usOpenJSON.utf8)
        return try decoder.decode(SearchResponse.self, from: data)
    }

    // MARK: - The keys arrive at all

    func testProductionPayloadDecodes() throws {
        let response = try decodeFixture()
        XCTAssertEqual(response.query, "US Open")
        XCTAssertEqual(response.futures.count, 10)
    }

    func testFuturesFamiliesIsDecodedAndNotDropped() throws {
        let families = try XCTUnwrap(decodeFixture().futuresFamilies)
        XCTAssertEqual(families.count, 1)

        let family = try XCTUnwrap(families.first)
        XCTAssertEqual(family.familyKey, "story:grand_slam_tennis")
        XCTAssertEqual(family.label, "Grand Slam Tennis")
        XCTAssertEqual(family.headline.id, 34_277_822)
        XCTAssertEqual(family.headline.name, "US Open Men's Singles Winner")
        XCTAssertEqual(family.members.count, 4)
        XCTAssertEqual(family.moreCount, 4)
        XCTAssertEqual(family.memberCount, 19)
    }

    func testHeadlineBoardIsDecodedWithItsRankedOutcomes() throws {
        let family = try XCTUnwrap(decodeFixture().futuresFamilies?.first)
        let board = try XCTUnwrap(family.headline.topOutcomes)

        // The board is the whole reason a family beats a row: the answer is on
        // the page, not one tap away.
        XCTAssertEqual(board.count, 5)
        XCTAssertEqual(board.first?.name, "Carlos Alcaraz")
        XCTAssertEqual(board.first?.probability ?? 0, 0.455, accuracy: 0.0001)
        XCTAssertEqual(family.headline.outcomeCount, 48)
    }

    func testEventConceptsAreDecodedAndNotDropped() throws {
        let concepts = try XCTUnwrap(decodeFixture().eventConcepts)
        XCTAssertEqual(concepts.count, 4)
        XCTAssertEqual(concepts.first?.key, "event:tennis:us-open-men-s-singles-winner")
        XCTAssertEqual(concepts.first?.name, "US Open Men's Singles")
        XCTAssertEqual(concepts.first?.domain, "tennis")
        XCTAssertEqual(concepts.first?.marketId, 34_277_822)
    }

    // MARK: - The ship: the same question stops appearing twice

    func testFamilyMarketsLeaveTheFlatList() throws {
        let response = try decodeFixture()
        let families = try XCTUnwrap(response.futuresFamilies)
        let flat = SearchGrouping.flatFutures(response.futures, families: families)

        // 10 flat rows in, 5 of them drawn inside the family card, 5 left below.
        XCTAssertEqual(response.futures.count, 10)
        XCTAssertEqual(flat.count, 5)
        XCTAssertEqual(flat.map(\.id), [7, 59_556_735, 59_556_738, 59_556_741, 59_556_742])
    }

    /// The user-visible claim, asserted as the property rather than as a count:
    /// no market id is drawn in two places on the page.
    func testNoMarketIsDrawnTwice() throws {
        let response = try decodeFixture()
        let families = try XCTUnwrap(response.futuresFamilies)
        let flat = SearchGrouping.flatFutures(response.futures, families: families)

        var drawn: [Int] = []
        for family in families {
            drawn.append(family.headline.id)
            drawn.append(contentsOf: family.members.map(\.id))
        }
        drawn.append(contentsOf: flat.map(\.id))
        drawn.append(contentsOf: SearchGrouping.novelConcepts(
            response.eventConcepts ?? [], families: families, flatFutures: flat
        ).compactMap(\.marketId))

        XCTAssertEqual(drawn.count, Set(drawn).count, "a market is drawn twice: \(drawn)")
    }

    /// The pre-fix page, pinned. Without the family the reader got these ten rows,
    /// and the first four are two questions written twice — which is what reads as
    /// a data bug in a result list.
    func testPreFixPageDrewTheSameQuestionTwicePerSource() throws {
        let response = try decodeFixture()
        let tierOne = response.futures.prefix(4).map(\.name)
        XCTAssertEqual(tierOne, [
            "US Open Men's Singles Winner",
            "2026 Women\u{2019}s US Open Winner (Tennis)",
            "2026 Men\u{2019}s US Open Winner (Tennis)",
            "US Open Women's Singles Winner",
        ])

        // All four land inside the one family, so the grouped page draws them as
        // one answer with three alternates rather than four peers.
        let families = try XCTUnwrap(response.futuresFamilies)
        let shown = SearchGrouping.shownIds(families)
        for market in response.futures.prefix(4) {
            XCTAssertTrue(shown.contains(market.id), "\(market.name) escaped its family")
        }
    }

    // MARK: - `moreCount` is a promise about THIS page

    func testMoreBelowCountsRowsTheFlatListActuallyDraws() throws {
        let response = try decodeFixture()
        let families = try XCTUnwrap(response.futuresFamilies)
        let family = try XCTUnwrap(families.first)
        let flat = SearchGrouping.flatFutures(response.futures, families: families)

        XCTAssertEqual(SearchGrouping.moreBelowLabel(family), "+4 more markets below")
        // The promise is keepable: 4 ≤ the 5 rows actually drawn below (#2646 is
        // the case where it was not, and printed "+6 more below" above one row).
        XCTAssertLessThanOrEqual(family.moreCount ?? 0, flat.count)
    }

    /// `memberCount` (19) must never reach the label. It counts members the
    /// payload does not carry, so promising them is promising rows that cannot
    /// exist on this page.
    func testMemberCountIsNeverThePromise() throws {
        let family = try XCTUnwrap(decodeFixture().futuresFamilies?.first)
        let label = try XCTUnwrap(SearchGrouping.moreBelowLabel(family))
        XCTAssertFalse(label.contains("19"))
        XCTAssertNotEqual(family.moreCount, family.memberCount)
    }

    func testNoMorePromiseWhenThereIsNothingBelow() {
        let family = makeFamily(moreCount: 0)
        XCTAssertNil(SearchGrouping.moreBelowLabel(family))
    }

    func testSingularMarketReadsAsOne() {
        XCTAssertEqual(SearchGrouping.moreBelowLabel(makeFamily(moreCount: 1)),
                       "+1 more market below")
    }

    // MARK: - Concepts: suppressed when they duplicate, drawn when they do not

    func testConceptsThatMirrorDrawnMarketsAreSuppressed() throws {
        let response = try decodeFixture()
        let families = try XCTUnwrap(response.futuresFamilies)
        let flat = SearchGrouping.flatFutures(response.futures, families: families)

        // All four US Open concepts point at markets the family already draws.
        // Rendering them would put the duplicate pair back one section higher.
        let novel = SearchGrouping.novelConcepts(
            response.eventConcepts ?? [], families: families, flatFutures: flat
        )
        XCTAssertTrue(novel.isEmpty, "drew \(novel.map(\.name)) that are already on the page")
    }

    func testAConceptWhoseMarketIsNowhereOnThePageIsDrawn() {
        let concept = SearchEventConcept(
            key: "event:tennis:wimbledon", name: "Wimbledon", domain: "tennis", marketId: 999
        )
        let novel = SearchGrouping.novelConcepts([concept], families: [], flatFutures: [])
        XCTAssertEqual(novel.map(\.key), ["event:tennis:wimbledon"])
    }

    /// Two sources deriving one concept is the normal case, and it is the shape
    /// this whole issue is about — so the concept section must not reproduce it.
    func testTwoConceptsOnOneMarketDrawOnce() {
        let a = SearchEventConcept(key: "event:tennis:a", name: "A", domain: "tennis", marketId: 999)
        let b = SearchEventConcept(key: "event:tennis:b", name: "B", domain: "tennis", marketId: 999)
        XCTAssertEqual(
            SearchGrouping.novelConcepts([a, b], families: [], flatFutures: []).count, 1
        )
    }

    /// iOS has no concept screen, so a market id is the only destination. A
    /// concept without one would be a row that goes nowhere.
    func testConceptWithNoMarketIsDropped() {
        let concept = SearchEventConcept(
            key: "event:golf:masters", name: "The Masters", domain: "golf", marketId: nil
        )
        XCTAssertTrue(SearchGrouping.novelConcepts([concept], families: [], flatFutures: []).isEmpty)
    }

    // MARK: - Leader pick

    func testLeaderIsTheFirstOutcomeCarryingAProbability() throws {
        let family = try XCTUnwrap(decodeFixture().futuresFamilies?.first)
        let leader = try XCTUnwrap(SearchGrouping.leaderOutcome(family.headline))
        XCTAssertEqual(leader.name, "Carlos Alcaraz")
    }

    func testAnUnpricedOutcomeIsSkippedRatherThanLed() {
        let market = makeMarket(id: 1, outcomes: [
            makeOutcome(id: 1, name: "No price", probability: nil),
            makeOutcome(id: 2, name: "Priced", probability: 0.4),
        ])
        XCTAssertEqual(SearchGrouping.leaderOutcome(market)?.name, "Priced")
    }

    func testABoardWithNoPricesHasNoLeader() {
        let market = makeMarket(id: 1, outcomes: [makeOutcome(id: 1, name: "x", probability: nil)])
        XCTAssertNil(SearchGrouping.leaderOutcome(market))
        // The row falls back to the outcome count rather than printing a blank —
        // "no price" is a state, not an absence (gotcha #53).
        XCTAssertEqual(market.outcomeCount, 1)
    }

    // MARK: - Degenerate payloads

    func testNoFamiliesLeavesTheFlatListExactlyAsServed() throws {
        let response = try decodeFixture()
        let flat = SearchGrouping.flatFutures(response.futures, families: [])
        XCTAssertEqual(flat.map(\.id), response.futures.map(\.id))
    }

    /// A family headline can be a market the shipped ten had no room for (measured
    /// live on "Alcaraz" and "Sabalenka"). Filtering must not assume the family's
    /// markets are a subset of the flat list.
    func testAFamilyHeadlineOutsideTheFlatListRemovesNothing() throws {
        let response = try decodeFixture()
        let outsider = makeFamily(moreCount: 0, headlineId: 424_242)
        let flat = SearchGrouping.flatFutures(response.futures, families: [outsider])
        XCTAssertEqual(flat.count, response.futures.count)
    }

    /// An older cached payload predates both keys. It must decode, not throw.
    func testPayloadWithNeitherKeyStillDecodes() throws {
        let json = #"""
        {"query": "x", "teams": [], "results": [], "futures": []}
        """#
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(SearchResponse.self, from: Data(json.utf8))
        XCTAssertNil(response.futuresFamilies)
        XCTAssertNil(response.eventConcepts)
        XCTAssertTrue(SearchGrouping.flatFutures(response.futures,
                                                 families: response.futuresFamilies ?? []).isEmpty)
    }

    // MARK: - Builders

    private func makeOutcome(id: Int, name: String, probability: Double?) -> SearchFuturesOutcome {
        SearchFuturesOutcome(id: id, name: name, probability: probability,
                             americanOdds: nil, rank: nil, movement: nil)
    }

    private func makeMarket(id: Int, outcomes: [SearchFuturesOutcome]) -> SearchFuturesMarket {
        SearchFuturesMarket(
            id: id, name: "Market \(id)", sport: nil, sportName: nil, category: nil,
            llmSportCategory: nil, status: "open", source: "kalshi", resolutionDate: nil,
            topOutcomes: outcomes, outcomeCount: outcomes.count, updatedAt: nil
        )
    }

    private func makeFamily(moreCount: Int, headlineId: Int = 1) -> SearchFuturesFamily {
        SearchFuturesFamily(
            familyKey: "story:test", label: "Test",
            headline: makeMarket(id: headlineId, outcomes: []),
            members: [], moreCount: moreCount, memberCount: 2
        )
    }
}
