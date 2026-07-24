import XCTest
@testable import Bain_Luck

/// L2-179: guard tests for the native event-concept card rescue.
///
/// Before this fix, the FeedItem decoder had no `concept` branch — a `concept`
/// item fell into the `else` (futures) branch, `FeedFuturesData` (non-optional
/// `id`/`name`) threw, and the FeedResponse per-item skip loop then silently
/// discarded EVERY concept card. That is why the Tour de France / World Cup
/// marquee never appeared natively. These tests assert a concept item survives
/// the full feed decode with a populated `concept` payload.
///
/// NOTE: like FeedConfidenceTests, this file is not yet wired into an Xcode
/// unit-test bundle (see BainLuckTests/README.md); it runs as-is once one exists.
final class FeedConceptDecodeTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    // MARK: - Concept survives the full feed decode (the core regression)

    func testConceptItemSurvivesFeedResponseDecode() throws {
        let json = """
        {
          "items": [
            {
              "type": "concept", "score": 90,
              "headline": "Stage 12 today", "reason": "Live now",
              "data": {
                "key": "cycling:tour-de-france-2026",
                "name": "Tour de France 2026",
                "domain": "cycling", "status": "live",
                "start_date": "2026-07-04", "is_major": true, "is_marquee": true,
                "fight_count": 0, "entry_count": 184, "marquee_whathit": false
              }
            },
            { "type": "futures", "score": 50, "data": { "id": 7, "name": "Who wins?", "status": "open" } }
          ],
          "total": 2, "limit": 50, "offset": 0, "has_more": false
        }
        """
        let feed = try decoder().decode(FeedResponse.self, from: Data(json.utf8))
        // The concept item is NOT dropped — both items survive.
        XCTAssertEqual(feed.items.count, 2)

        let concept = try XCTUnwrap(feed.items.first { $0.type == "concept" })
        let data = try XCTUnwrap(concept.concept)
        XCTAssertEqual(data.key, "cycling:tour-de-france-2026")
        XCTAssertEqual(data.name, "Tour de France 2026")
        XCTAssertEqual(data.domain, "cycling")
        XCTAssertEqual(data.isMajor, true)
        XCTAssertEqual(data.isMarquee, true)
        XCTAssertEqual(data.entryCount, 184)
        // It must NOT be mis-decoded into the futures slot (the old drop path).
        XCTAssertNil(concept.futures)
        XCTAssertNil(concept.event)
        XCTAssertNil(concept.tournament)
        // Stable identity for the feed grid.
        XCTAssertEqual(concept.id, "concept-cycling:tour-de-france-2026")

        // The sibling futures item still decodes normally alongside it.
        let futures = try XCTUnwrap(feed.items.first { $0.type == "futures" })
        XCTAssertEqual(futures.futures?.id, 7)
        XCTAssertNil(futures.concept)
    }

    // MARK: - WHAT-HIT (settled) framing decodes

    func testSettledConceptDecodesWinnerAndResult() throws {
        let json = """
        {
          "type": "concept", "score": 88,
          "data": {
            "key": "cycling:tour-de-france-2026", "name": "Tour de France 2026",
            "domain": "cycling", "status": "settled", "marquee_whathit": true,
            "winner": "Tadej Pogačar", "result_summary": "4th career title"
          }
        }
        """
        let item = try decoder().decode(FeedItem.self, from: Data(json.utf8))
        let data = try XCTUnwrap(item.concept)
        XCTAssertEqual(data.marqueeWhathit, true)
        XCTAssertEqual(data.winner, "Tadej Pogačar")
        XCTAssertEqual(data.resultSummary, "4th career title")
    }

    // MARK: - Optional fields absent decode to nil (tolerance)

    func testConceptOptionalFieldsAbsentDecodeToNil() throws {
        let json = """
        { "type": "concept", "score": 10, "data": { "key": "k", "name": "Some Event" } }
        """
        let item = try decoder().decode(FeedItem.self, from: Data(json.utf8))
        let data = try XCTUnwrap(item.concept)
        XCTAssertEqual(data.key, "k")
        XCTAssertEqual(data.name, "Some Event")
        XCTAssertNil(data.winner)
        XCTAssertNil(data.marqueeWhathit)
        XCTAssertNil(data.isMajor)
    }
}
