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
