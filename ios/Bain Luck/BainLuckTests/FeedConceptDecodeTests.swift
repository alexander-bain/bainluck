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

    // MARK: - Mixed feed: every supported type survives; unknown/malformed skip

    /// L2-200: a mixed event/futures/tournament/concept/unknown feed must retain
    /// EVERY supported sibling and skip only the unsupported/malformed item, never
    /// wiping healthy neighbors (the per-item tolerance contract that the concept
    /// rescue relies on). The unknown `type` here carries a non-futures payload, so
    /// the decoder's futures fallback throws and `FeedResponse`'s skip loop drops
    /// just that one item.
    func testMixedFeedRetainsEverySupportedTypeAndSkipsUnknown() throws {
        let json = """
        {
          "items": [
            { "type": "event", "score": 80,
              "data": { "id": 11, "home_team": "Celtics", "away_team": "Lakers",
                        "status": "live", "current_odds": { "home_probability": 0.61 } } },
            { "type": "futures", "score": 70,
              "data": { "id": 22, "name": "2026 NBA Champion", "status": "open",
                        "top_outcomes": [ { "id": 1, "name": "Celtics", "probability": 0.3 } ] } },
            { "type": "tournament", "score": 65,
              "data": { "key": "golf:the-open-2026", "name": "The Open 2026" } },
            { "type": "concept", "score": 90,
              "data": { "key": "cycling:tour-de-france-2026", "name": "Tour de France 2026",
                        "domain": "cycling", "status": "live" } },
            { "type": "poll", "score": 40,
              "data": { "question": "Who is your favorite?", "options": ["A", "B"] } }
          ],
          "total": 5, "limit": 50, "offset": 0, "has_more": false
        }
        """
        let feed = try decoder().decode(FeedResponse.self, from: Data(json.utf8))

        // The four supported types all survive; only the unknown/malformed drops.
        XCTAssertEqual(feed.items.count, 4, "unknown `poll` with a non-futures payload is skipped")

        let event = try XCTUnwrap(feed.items.first { $0.type == "event" })
        XCTAssertEqual(event.event?.id, 11)
        XCTAssertNil(event.futures); XCTAssertNil(event.concept); XCTAssertNil(event.tournament)

        let futures = try XCTUnwrap(feed.items.first { $0.type == "futures" })
        XCTAssertEqual(futures.futures?.id, 22)
        XCTAssertNil(futures.concept)

        let tournament = try XCTUnwrap(feed.items.first { $0.type == "tournament" })
        XCTAssertEqual(tournament.tournament?.key, "golf:the-open-2026")
        XCTAssertNil(tournament.futures, "a tournament must not be mis-slotted as futures")

        let concept = try XCTUnwrap(feed.items.first { $0.type == "concept" })
        XCTAssertEqual(concept.concept?.key, "cycling:tour-de-france-2026")
        XCTAssertNil(concept.futures, "a concept must not be mis-slotted as futures")

        XCTAssertNil(feed.items.first { $0.type == "poll" }, "the unknown type is not retained")
    }

    /// An unknown type with NO `data` survives decode (empty shell, filtered at
    /// render) and must not take its siblings down with it.
    func testUnknownTypeWithoutDataDoesNotWipeSiblings() throws {
        let json = """
        {
          "items": [
            { "type": "spaceship", "score": 5 },
            { "type": "futures", "score": 50,
              "data": { "id": 7, "name": "Who wins?", "status": "open" } }
          ],
          "total": 2, "limit": 50, "offset": 0, "has_more": false
        }
        """
        let feed = try decoder().decode(FeedResponse.self, from: Data(json.utf8))
        // The futures sibling always survives; the unknown shell carries no payload.
        let futures = try XCTUnwrap(feed.items.first { $0.type == "futures" })
        XCTAssertEqual(futures.futures?.id, 7)
        let unknown = feed.items.first { $0.type == "spaceship" }
        if let unknown {
            XCTAssertNil(unknown.event); XCTAssertNil(unknown.futures)
            XCTAssertNil(unknown.concept); XCTAssertNil(unknown.tournament)
        }
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
