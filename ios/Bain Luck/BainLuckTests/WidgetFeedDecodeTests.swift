import XCTest

/// L2-182: guards the widget's PRODUCTION tolerant feed decoder — the exact
/// `WidgetFeedResponse`/`WidgetDiscoverFeedResponse` types `WidgetAPIClient` uses,
/// not the main app's `FeedResponse`.
///
/// The regression (L2-179): the widget decoded the items array atomically, so a
/// single concept/tournament card whose `data` matched neither `WidgetEventData`
/// nor `WidgetFuturesData` threw out of the whole decode and blanked the ENTIRE
/// widget. `WidgetFeedDecoding.swift` is compiled into this test bundle via a
/// target membership exception, so these assertions run against the real decoder.
final class WidgetFeedDecodeTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func decodeEvents(_ json: String) throws -> WidgetFeedResponse {
        try decoder().decode(WidgetFeedResponse.self, from: Data(json.utf8))
    }

    private func decodeDiscover(_ json: String) throws -> WidgetDiscoverFeedResponse {
        try decoder().decode(WidgetDiscoverFeedResponse.self, from: Data(json.utf8))
    }

    // MARK: - Events feed: malformed concept/tournament between valid events

    func testEventFeedKeepsValidEventsAcrossMalformedCards() throws {
        // valid event -> malformed concept -> malformed tournament -> valid event.
        // The two events must survive as usable items; the middle cards drop.
        let feed = try decodeEvents("""
        {
          "items": [
            { "type": "event", "headline": "Live now",
              "data": { "id": 11, "home_team": "Celtics", "away_team": "Lakers",
                        "status": "live", "current_odds": { "home_probability": 0.62 } } },
            { "type": "concept",
              "data": { "key": "event:soccer:world-cup-2026", "name": "World Cup 2026" } },
            { "type": "tournament",
              "data": { "slug": "the-open", "rounds": [ { "n": 1 } ] } },
            { "type": "event",
              "data": { "id": 12, "home_team": "Heat", "away_team": "Knicks",
                        "status": "live", "current_odds": { "home_probability": 0.48 } } }
          ],
          "total": 4, "limit": 10, "offset": 0, "has_more": false
        }
        """)

        XCTAssertEqual(feed.items.count, 2, "only the two valid events survive")
        XCTAssertEqual(feed.items.compactMap { $0.data?.id }, [11, 12])
        XCTAssertEqual(feed.items.first?.headline, "Live now")
    }

    // MARK: - Discover feed: malformed concept/tournament between valid futures

    func testDiscoverFeedKeepsValidFuturesAcrossMalformedCards() throws {
        let feed = try decodeDiscover("""
        {
          "items": [
            { "type": "futures", "headline": "Mover",
              "data": { "id": 200, "name": "2026 NBA Champion",
                        "top_outcomes": [ { "name": "Celtics", "probability": 0.32 } ] } },
            { "type": "concept",
              "data": { "key": "event:cycling:tour-de-france-2026", "name": "Tour de France" } },
            { "type": "tournament", "data": { "slug": "masters", "field": 90 } },
            { "type": "futures",
              "data": { "id": 201, "name": "Next President",
                        "top_outcomes": [ { "name": "Candidate A", "probability": 0.45 } ] } }
          ],
          "total": 4, "limit": 10, "offset": 0, "has_more": false
        }
        """)

        XCTAssertEqual(feed.items.count, 2, "only the two valid futures survive")
        XCTAssertEqual(feed.items.compactMap { $0.data?.id }, [200, 201])
        XCTAssertEqual(feed.items.last?.data?.topOutcomes?.first?.name, "Candidate A")
    }

    // MARK: - A malformed outcome drops only its own item

    func testMalformedOutcomeDropsOnlyThatItem() throws {
        // The middle futures item has an outcome missing the required `name`, so
        // its `top_outcomes` decode throws and the item drops — its siblings must
        // remain.
        let feed = try decodeDiscover("""
        {
          "items": [
            { "type": "futures",
              "data": { "id": 1, "name": "Good A",
                        "top_outcomes": [ { "name": "Yes", "probability": 0.6 } ] } },
            { "type": "futures",
              "data": { "id": 2, "name": "Bad outcome",
                        "top_outcomes": [ { "probability": 0.5 } ] } },
            { "type": "futures",
              "data": { "id": 3, "name": "Good B",
                        "top_outcomes": [ { "name": "No", "probability": 0.4 } ] } }
          ],
          "total": 3, "limit": 10, "offset": 0, "has_more": false
        }
        """)

        XCTAssertEqual(feed.items.compactMap { $0.data?.id }, [1, 3], "only the bad-outcome item drops")
    }

    // MARK: - Null / absent data does not throw (item survives, data is nil)

    func testNullDataItemSurvivesWithNilData() throws {
        let feed = try decodeEvents("""
        {
          "items": [
            { "type": "event", "data": null },
            { "type": "event",
              "data": { "id": 5, "home_team": "A", "away_team": "B",
                        "status": "live", "current_odds": { "home_probability": 0.5 } } }
          ],
          "total": 2, "limit": 10, "offset": 0, "has_more": false
        }
        """)

        // Both items decode: the first with nil data (filtered downstream), the
        // second populated. The unkeyed loop must advance past every element.
        XCTAssertEqual(feed.items.count, 2)
        XCTAssertNil(feed.items.first?.data)
        XCTAssertEqual(feed.items.last?.data?.id, 5)
    }

    // MARK: - An all-malformed feed decodes to empty, never throws or hangs

    func testAllMalformedFeedDecodesToEmpty() throws {
        let feed = try decodeEvents("""
        {
          "items": [
            { "type": "concept", "data": { "key": "k1" } },
            { "type": "tournament", "data": { "slug": "s" } },
            { "type": "futures", "data": { "id": 9, "name": "F",
                        "top_outcomes": [ { "name": "Yes", "probability": 0.5 } ] } }
          ],
          "total": 3, "limit": 10, "offset": 0, "has_more": false
        }
        """)

        // None decode as WidgetEventData; the decoder yields an empty list rather
        // than throwing the whole response away or looping forever.
        XCTAssertTrue(feed.items.isEmpty)
    }
}
