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

    // MARK: - L2-224: the tournament WHAT-HIT client loss

    /// The backend sends `marquee_whathit` (and `is_marquee`) on EVERY tournament
    /// card — `routes/feed.py` `_score_golf_tournaments` sets them unconditionally —
    /// and web has always read them. `FeedTournamentData` decoded neither, so a
    /// finished marquee arrived on device indistinguishable from a live one.
    func testTournamentDecodesMarqueeWhatHitFields() throws {
        let json = """
        {
          "type": "tournament", "score": 88,
          "data": {
            "key": "golf:the-open-2026", "name": "The Open 2026",
            "tour": "pga", "tour_label": "PGA Tour", "is_major": true,
            "venue": "Royal Birkdale",
            "golfers": [ { "name": "Scottie Scheffler", "probability": 100.0, "rank": 1,
                           "movement_24h": 2.3 } ],
            "source_count": 2, "is_marquee": true, "marquee_whathit": true
          }
        }
        """
        let item = try decoder().decode(FeedItem.self, from: Data(json.utf8))
        let data = try XCTUnwrap(item.tournament)
        XCTAssertEqual(data.marqueeWhathit, true)
        XCTAssertEqual(data.isMarquee, true)
    }

    /// Absent fields stay nil — an ordinary live/upcoming tournament is unaffected.
    func testTournamentWithoutMarqueeFieldsDecodesToNil() throws {
        let json = """
        {
          "type": "tournament", "score": 40,
          "data": { "key": "golf:rsm-2026", "name": "RSM Classic",
                    "golfers": [ { "name": "A Player", "probability": 12.0, "rank": 1 } ] }
        }
        """
        let item = try decoder().decode(FeedItem.self, from: Data(json.utf8))
        let data = try XCTUnwrap(item.tournament)
        XCTAssertNil(data.marqueeWhathit)
        XCTAssertNil(data.isMarquee)
    }

    // MARK: - L2-224: the native suppression matrix (parity with web)

    // `DiscoverViewModel.suppressionReason` shipped in L2-215 with no native test at
    // all — web's rules were guarded by `feedEmptyEnvelope.test.tsx`, native's by
    // nothing. These lock the full matrix against
    // `frontend/components/discover/utils.ts` `feedItemSuppressionReason`.

    private func decodeItem(_ json: String) throws -> FeedItem {
        try decoder().decode(FeedItem.self, from: Data(json.utf8))
    }

    func testSuppressionKeepsEventAlways() throws {
        let item = try decodeItem("""
        { "type": "event", "score": 50,
          "data": { "id": 1, "home_team": "A", "away_team": "B", "status": "scheduled" } }
        """)
        XCTAssertNil(DiscoverViewModel.suppressionReason(item))
    }

    func testSuppressionDropsLiveConceptKeepsWhatHitConcept() throws {
        // The #1486 rule, and the reason a live Tour de France card does not appear
        // natively — a DELIBERATE fail-closed ruling in exact parity with web, not a
        // native decode defect.
        let live = try decodeItem("""
        { "type": "concept", "score": 90,
          "data": { "key": "cycling:tour-de-france-2026", "name": "Tour de France 2026",
                    "domain": "cycling", "status": "live", "marquee_whathit": false } }
        """)
        XCTAssertEqual(DiscoverViewModel.suppressionReason(live), "empty_concept")

        let settled = try decodeItem("""
        { "type": "concept", "score": 90,
          "data": { "key": "cycling:tour-de-france-2026", "name": "Tour de France 2026",
                    "domain": "cycling", "status": "settled", "marquee_whathit": true,
                    "winner": "Tadej Pogačar" } }
        """)
        XCTAssertNil(DiscoverViewModel.suppressionReason(settled))
    }

    func testSuppressionTournamentKeepsGolfersOrWhatHit() throws {
        let withGolfers = try decodeItem("""
        { "type": "tournament", "score": 60,
          "data": { "key": "golf:rsm-2026", "name": "RSM Classic",
                    "golfers": [ { "name": "A Player", "probability": 12.0, "rank": 1 } ] } }
        """)
        XCTAssertNil(DiscoverViewModel.suppressionReason(withGolfers))

        // The parity fix: web keeps a golfer-less settled marquee; native dropped it.
        let whatHitNoField = try decodeItem("""
        { "type": "tournament", "score": 60,
          "data": { "key": "golf:the-open-2026", "name": "The Open 2026",
                    "golfers": [], "marquee_whathit": true } }
        """)
        XCTAssertNil(DiscoverViewModel.suppressionReason(whatHitNoField),
                     "a settled marquee leads with its result even with an empty field")

        let empty = try decodeItem("""
        { "type": "tournament", "score": 60,
          "data": { "key": "golf:rsm-2026", "name": "RSM Classic", "golfers": [] } }
        """)
        XCTAssertEqual(DiscoverViewModel.suppressionReason(empty), "empty_tournament")
    }

    func testSuppressionFuturesNeedsOutcomesOrSettledStatus() throws {
        let withOutcomes = try decodeItem("""
        { "type": "futures", "score": 50,
          "data": { "id": 1, "name": "Q", "status": "open",
                    "top_outcomes": [ { "id": 1, "name": "Yes", "probability": 0.5 } ] } }
        """)
        XCTAssertNil(DiscoverViewModel.suppressionReason(withOutcomes))

        let settled = try decodeItem("""
        { "type": "futures", "score": 50,
          "data": { "id": 2, "name": "Q", "status": "resolved", "top_outcomes": [] } }
        """)
        XCTAssertNil(DiscoverViewModel.suppressionReason(settled))

        let empty = try decodeItem("""
        { "type": "futures", "score": 50,
          "data": { "id": 3, "name": "Q", "status": "open", "top_outcomes": [] } }
        """)
        XCTAssertEqual(DiscoverViewModel.suppressionReason(empty), "empty_futures")
    }

    func testSuppressionUnknownShapeFailsClosed() throws {
        let item = try decodeItem("""
        { "type": "spaceship", "score": 5 }
        """)
        XCTAssertEqual(DiscoverViewModel.suppressionReason(item), "unknown_type")
    }

    /// A malformed concept must lose ONLY itself: a mixed page keeps every healthy
    /// sibling, in the server's order, and the renderable set is unchanged apart
    /// from the dropped card.
    func testMalformedConceptLosesOnlyItselfAndOrderIsStable() throws {
        let json = """
        {
          "items": [
            { "type": "event", "score": 80,
              "data": { "id": 11, "home_team": "Celtics", "away_team": "Lakers", "status": "live" } },
            { "type": "concept", "score": 90, "data": [ "not", "an", "object" ] },
            { "type": "futures", "score": 70,
              "data": { "id": 22, "name": "2026 NBA Champion", "status": "open",
                        "top_outcomes": [ { "id": 1, "name": "Celtics", "probability": 0.3 } ] } },
            { "type": "concept", "score": 85,
              "data": { "key": "cycling:tdf-2026", "name": "Tour de France 2026",
                        "domain": "cycling", "status": "settled", "marquee_whathit": true,
                        "winner": "Tadej Pogačar" } }
          ],
          "total": 4, "limit": 50, "offset": 0, "has_more": false
        }
        """
        let feed = try decoder().decode(FeedResponse.self, from: Data(json.utf8))
        XCTAssertEqual(feed.items.map(\.id),
                       ["event-11", "futures-22", "concept-cycling:tdf-2026"],
                       "only the malformed concept drops; server order is preserved")

        let renderable = feed.items.filter { DiscoverViewModel.isRenderable($0) }
        XCTAssertEqual(renderable.map(\.id),
                       ["event-11", "futures-22", "concept-cycling:tdf-2026"])
    }
}
