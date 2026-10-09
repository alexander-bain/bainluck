import XCTest
@testable import Bain_Luck

/// #1886 — the fixture-from-production harness, made permanent.
///
/// `FeedResponse` decodes items through a deliberately tolerant skip loop so one
/// malformed card cannot blank the whole feed. That tolerance is correct and it
/// is also why this bug lived: a card the decoder cannot read is dropped with no
/// error, no log, and no gap the reader can see. **The only way to notice is to
/// count.** Six curated theme cards were invisible on iOS for as long as the
/// bundle branch was missing, and every bundle test in the suite passed
/// throughout, because every one of them was written against the same imaginary
/// wire shape the decoder expected.
///
/// So these assertions compare the decode against the SERVED count recorded at
/// capture time, never against the payload's own decoded length — a skip loop
/// that ate an element agrees with itself perfectly.
final class DiscoverFeedProdDecodeTests: XCTestCase {

    private func decodeFixture() throws -> FeedResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let data = try XCTUnwrap(DiscoverFeedProdFixture.json.data(using: .utf8))
        return try decoder.decode(FeedResponse.self, from: data)
    }

    /// The headline assertion: a real production page loses NOTHING in decode.
    ///
    /// **This test fails on the old decoder** — it dropped all 5 bundle cards and
    /// would decode 25 of 30.
    func testProductionFeedPageDecodesWithZeroDroppedItems() throws {
        let response = try decodeFixture()
        XCTAssertEqual(
            response.items.count,
            DiscoverFeedProdFixture.servedItemCount,
            """
            A production feed page lost items in decode. The count gap IS the bug \
            class — FeedResponse's skip loop drops unreadable cards silently, so \
            nothing else will tell you. Find the type whose branch is missing.
            """
        )
    }

    /// The specific cards #1886 was filed for.
    func testEveryBundleCardInTheProductionPageDecodes() throws {
        let response = try decodeFixture()
        let bundles = response.items.compactMap(\.bundle)

        XCTAssertEqual(
            bundles.count,
            DiscoverFeedProdFixture.servedBundleHeadlines.count,
            "every served bundle card must decode — 0 of these rendered before #1886"
        )
        XCTAssertEqual(bundles.map(\.id), DiscoverFeedProdFixture.servedBundleIDs)
        XCTAssertEqual(bundles.map(\.title), DiscoverFeedProdFixture.servedBundleHeadlines)
        XCTAssertEqual(
            bundles.map(\.items.count),
            DiscoverFeedProdFixture.servedBundleChildCounts,
            "a bundle that decodes but loses its children is still a broken card"
        )
    }

    /// A bundle whose children silently vanished would still satisfy the count
    /// assertions above at the bundle level, so pin the children's own decode.
    func testBundleChildrenDecodeAsRealFuturesCards() throws {
        let response = try decodeFixture()
        let children = response.items.compactMap(\.bundle).flatMap(\.items)

        XCTAssertEqual(
            children.count,
            DiscoverFeedProdFixture.servedBundleChildCounts.reduce(0, +)
        )
        XCTAssertTrue(
            children.allSatisfy { $0.futures != nil },
            "every bundle child in this page is a futures card and must decode as one"
        )
        XCTAssertTrue(
            children.allSatisfy { $0.futures?.name.isEmpty == false },
            "children carry their market names, not empty placeholder shells"
        )
    }

    /// Gotcha #43 — the other direction. The bundle branch must not have cost the
    /// far more common futures card, which is 25 of these 30.
    func testNonBundleCardsInTheProductionPageStillDecode() throws {
        let response = try decodeFixture()
        let futures = response.items.filter { $0.type == "futures" }

        XCTAssertEqual(futures.count, 25, "the served futures census for this page")
        XCTAssertTrue(
            futures.allSatisfy { $0.futures != nil && $0.bundle == nil },
            "a futures card decodes as futures and does not acquire a bundle"
        )
    }

    /// Identity: bundles reach `FeedItem.id` for the first time now that they
    /// decode at all. Two theme cards must never collide into one row.
    func testDecodedItemIdentitiesAreUnique() throws {
        let response = try decodeFixture()
        let ids = response.items.map(\.id)
        XCTAssertEqual(
            Set(ids).count,
            ids.count,
            "duplicate FeedItem.id collapses cards in any ForEach that renders them"
        )
        XCTAssertTrue(
            response.items.compactMap(\.bundle).allSatisfy { b in
                ids.contains("bundle-\(b.id)")
            },
            "a bundle's identity is its server id, not its headline"
        )
    }

    /// The envelope around the items must survive too — a page that decodes its
    /// cards but loses `has_more` stops pagination dead.
    func testProductionEnvelopeDecodes() throws {
        let response = try decodeFixture()
        XCTAssertEqual(response.total, 95)
        XCTAssertEqual(response.limit, 30)
        XCTAssertEqual(response.offset, 0)
        XCTAssertTrue(response.hasMore)
        XCTAssertEqual(response.cache?.status, "miss")
        XCTAssertFalse(response.isUnavailable)
        XCTAssertFalse(response.isDegradedBuild)
    }
}

// MARK: - #5105: the seated-opening boundary survives tolerant decode

/// The boundary is stated in the SERVER's raw positions. The skip loop compacts
/// `items`, so a boundary read off the compacted index shifts by one for every
/// malformed opening row. These pin the three states the opt-in path relies on.
extension DiscoverFeedProdDecodeTests {

    private static func seatingDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private static func futuresRow(_ id: Int) -> String {
        """
        {"type":"futures","score":90,"data":{"id":\(id),"name":"Market \(id)?",
         "llm_sport_category":"economics","source":"kalshi","status":"open",
         "top_outcomes":[{"id":\(id * 10),"name":"A","probability":0.55,"rank":1,"movement":0.02}],"outcome_count":1}}
        """
    }

    private static let malformedRow = #"{"garbage": true, "score": 1}"#

    private func seatedPage(rows: [String], extra: String) throws -> FeedResponse {
        let json = """
        {"items":[\(rows.joined(separator: ","))],"total":9999,"limit":50,"offset":0,
         "has_more":true,"edition":"ed-1"\(extra)}
        """
        return try Self.seatingDecoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    /// E=3 with the second opening row malformed: two opening cards survive and
    /// the boundary follows them — not three cards (which would pull the first
    /// continuation card into the opening).
    func testMalformedOpeningRowKeepsTheBoundaryInRawPositions5105() throws {
        let page = try seatedPage(
            rows: [Self.futuresRow(1), Self.malformedRow, Self.futuresRow(3),
                   Self.futuresRow(4), Self.futuresRow(5)],
            extra: #","continuation_start":3,"edition_status":"pinned""#)

        XCTAssertEqual(page.items.count, 4)
        XCTAssertEqual(page.rawPositions, [0, 2, 3, 4])
        XCTAssertEqual(page.continuationStart, .at(3))
        XCTAssertEqual(page.openingItemCount, 2,
            "the heading follows the 2 surviving opening cards, never the compacted index 3")
        XCTAssertEqual(page.items.prefix(2).compactMap(\.futures?.id), [1, 3])
        XCTAssertEqual(page.editionStatus, FeedResponse.pinnedEditionStatus)
    }

    /// Zero is an answer (the continuation starts at the top); absence is not.
    func testZeroBoundaryIsDistinctFromAbsence5105() throws {
        let rows = [Self.futuresRow(1), Self.futuresRow(2)]
        let zero = try seatedPage(rows: rows, extra: #","continuation_start":0"#)
        let absent = try seatedPage(rows: rows, extra: "")
        let null = try seatedPage(rows: rows, extra: #","continuation_start":null"#)

        XCTAssertEqual(zero.continuationStart, .at(0))
        XCTAssertEqual(zero.openingItemCount, 0)
        XCTAssertEqual(absent.continuationStart, .absent)
        XCTAssertNil(absent.openingItemCount, "absent keeps the legacy single list")
        XCTAssertNil(absent.editionStatus)
        XCTAssertEqual(null.continuationStart, .absent)
    }

    /// A present-but-unusable boundary is never guessed into a position, and it
    /// never takes the feed down: every card still decodes.
    func testUnusableBoundaryIsInvalidAndTheFeedSurvives5105() throws {
        let rows = [Self.futuresRow(1), Self.futuresRow(2)]
        for extra in [#","continuation_start":-1"#, #","continuation_start":"3""#,
                      #","continuation_start":1.5"#, #","continuation_start":3"#] {
            let page = try seatedPage(rows: rows, extra: extra)
            XCTAssertEqual(page.continuationStart, .invalid, extra)
            XCTAssertNil(page.openingItemCount, extra)
            XCTAssertEqual(page.items.count, 2, extra)
        }
        // The page's own length is a valid boundary: every card is opening.
        let whole = try seatedPage(rows: rows, extra: #","continuation_start":2"#)
        XCTAssertEqual(whole.continuationStart, .at(2))
        XCTAssertEqual(whole.openingItemCount, 2)
    }

    /// The production capture predates #5105: it must read as absent, with raw
    /// positions that are simply 0..<n because nothing was dropped.
    func testProductionPageReadsAsLegacy5105() throws {
        let response = try decodeFixture()
        XCTAssertEqual(response.continuationStart, .absent)
        XCTAssertNil(response.editionStatus)
        XCTAssertEqual(response.rawPositions, Array(0..<response.items.count))
    }
}
