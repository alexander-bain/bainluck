import XCTest

/// L2-225 — the widget's terminal-lifecycle gate.
///
/// The gap this closes: `WidgetFuturesData` decoded a name, a category and a price
/// and nothing else — no `status`, no `resolution_date`, no `resolved`, no `winner`.
/// `WidgetAPIClient.fetchDiscoverItems` therefore admitted any card carrying a leader
/// probability, and a widget timeline is cached for hours, so a settled market could
/// sit on the home screen showing a live-looking number and a movement arrow long
/// after the app and the site had both moved on. The main app hides such a card
/// (`DiscoverView.isStaleItem`); the widget had no equivalent at all.
///
/// `WidgetFeedDecoding.swift` is compiled into this bundle via the L2-182 target
/// membership exception, so these run against the REAL decoder and the real
/// predicate, not a copy. (`WidgetAPIClient` itself is widget-target-only; its
/// one-line guard is compile-proven by the iOS build, not by these tests.)
final class WidgetDiscoverLifecycleTests: XCTestCase {

    private let now = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!
    private let past = "2026-07-20T00:00:00Z"
    private let future = "2026-08-20T00:00:00Z"

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func decodeDiscover(_ json: String) throws -> WidgetDiscoverFeedResponse {
        try decoder().decode(WidgetDiscoverFeedResponse.self, from: Data(json.utf8))
    }

    /// One futures card in the exact `/api/feed` shape the widget requests.
    private func card(
        id: Int = 1,
        status: String = "\"open\"",
        resolutionDate: String = "null",
        resolved: String = "null",
        winner: String = "null"
    ) -> String {
        """
        { "type": "futures", "headline": "Mover",
          "data": { "id": \(id), "name": "Market \(id)", "sport": null,
                    "llm_sport_category": "politics",
                    "status": \(status), "resolution_date": \(resolutionDate),
                    "resolved": \(resolved), "winner": \(winner),
                    "hook_description": null,
                    "top_outcomes": [{"name": "Team A", "probability": 0.62,
                                      "movement": 0.03}] } }
        """
    }

    private func decodeOne(_ cardJSON: String) throws -> WidgetFuturesData {
        let feed = try decodeDiscover("""
        { "items": [\(cardJSON)] }
        """)
        return try XCTUnwrap(feed.items.first?.data)
    }

    // MARK: - The fields exist at all now

    func testTerminalFieldsAreDecoded() throws {
        let data = try decodeOne(card(
            status: "\"resolved\"", resolutionDate: "\"\(past)\"",
            resolved: "true", winner: "\"Team A\""))
        XCTAssertEqual(data.status, "resolved")
        XCTAssertEqual(data.resolutionDate, past)
        XCTAssertEqual(data.resolved, true)
        XCTAssertEqual(data.winner, "Team A")
    }

    func testLegacyPayloadWithoutTerminalFieldsStillDecodesAndSurfaces() throws {
        // A response predating these keys must decode with nils and stay renderable —
        // unknown authority is not settlement.
        let feed = try decodeDiscover("""
        { "items": [
            { "type": "futures",
              "data": { "id": 5, "name": "Legacy", "llm_sport_category": "tech",
                        "top_outcomes": [{"name": "A", "probability": 0.5,
                                          "movement": null}] } } ] }
        """)
        let data = try XCTUnwrap(feed.items.first?.data)
        XCTAssertNil(data.status)
        XCTAssertNil(data.resolutionDate)
        XCTAssertFalse(WidgetLifecycle.isSettled(data, now: now))
    }

    // MARK: - The gate itself (all four authorities)

    func testOpenMarketWithFutureResolutionIsNotSettled() throws {
        XCTAssertFalse(
            WidgetLifecycle.isSettled(
                try decodeOne(card(resolutionDate: "\"\(future)\"")), now: now))
    }

    func testEveryTerminalStatusSettles() throws {
        for status in ["resolved", "closed", "settled", "finalized", "final", "FINAL"] {
            XCTAssertTrue(
                WidgetLifecycle.isSettled(
                    try decodeOne(card(status: "\"\(status)\"")), now: now),
                "status '\(status)' must settle a widget card")
        }
    }

    func testPastResolutionDateSettlesEvenWhenStatusIsOpen() throws {
        // The production shape: gotcha #33 leaves a settled Kalshi market at
        // status='open', so the date is the only honest signal.
        XCTAssertTrue(
            WidgetLifecycle.isSettled(
                try decodeOne(card(resolutionDate: "\"\(past)\"")), now: now))
    }

    func testResolvedFlagAndNamedWinnerSettle() throws {
        XCTAssertTrue(
            WidgetLifecycle.isSettled(try decodeOne(card(resolved: "true")), now: now))
        XCTAssertTrue(
            WidgetLifecycle.isSettled(
                try decodeOne(card(winner: "\"Team A\"")), now: now))
    }

    func testBlankOrFalseAuthorityDoesNotSettle() throws {
        XCTAssertFalse(
            WidgetLifecycle.isSettled(try decodeOne(card(resolved: "false")), now: now))
        XCTAssertFalse(
            WidgetLifecycle.isSettled(try decodeOne(card(winner: "\"  \"")), now: now))
        XCTAssertFalse(
            WidgetLifecycle.isSettled(try decodeOne(card(status: "\"open\"")), now: now))
    }

    func testUnparseableResolutionDateDoesNotSettle() throws {
        // A garbage date is unknown authority, not evidence of settlement.
        XCTAssertFalse(
            WidgetLifecycle.isSettled(
                try decodeOne(card(resolutionDate: "\"not-a-date\"")), now: now))
    }

    func testFractionalSecondsResolutionDateParses() throws {
        XCTAssertTrue(
            WidgetLifecycle.isSettled(
                try decodeOne(card(resolutionDate: "\"2026-07-20T00:00:00.123Z\"")),
                now: now))
    }

    // MARK: - The whole page: terminal cards drop, healthy siblings survive

    /// Mirrors `WidgetAPIClient.fetchDiscoverItems`' compactMap so the ordering and
    /// containment behaviour of the real client path is pinned here.
    private func admitted(_ feed: WidgetDiscoverFeedResponse) -> [Int] {
        feed.items.compactMap { item -> Int? in
            guard let futures = item.data,
                  !WidgetLifecycle.isSettled(futures, now: now),
                  let leader = futures.topOutcomes?.first,
                  leader.probability != nil else { return nil }
            return futures.id
        }
    }

    func testTerminalCardsAreDroppedAtEveryPositionAndSiblingsSurvive() throws {
        let settled = card(id: 99, status: "\"resolved\"")
        let openA = card(id: 1, resolutionDate: "\"\(future)\"")
        let openB = card(id: 2, resolutionDate: "\"\(future)\"")

        for (label, items) in [
            ("first", [settled, openA, openB]),
            ("middle", [openA, settled, openB]),
            ("last", [openA, openB, settled]),
        ] {
            let feed = try decodeDiscover("{ \"items\": [\(items.joined(separator: ","))] }")
            XCTAssertEqual(admitted(feed), [1, 2],
                           "terminal-\(label) must drop only itself, order preserved")
        }
    }

    func testAllTerminalPageYieldsNothingRatherThanStaleContent() throws {
        let feed = try decodeDiscover("""
        { "items": [\(card(id: 1, status: "\"resolved\"")),
                    \(card(id: 2, resolutionDate: "\"\(past)\"")),
                    \(card(id: 3, resolved: "true"))] }
        """)
        XCTAssertTrue(admitted(feed).isEmpty,
                      "settled means settled — no restoration path on the home screen")
    }

    func testMalformedCardBesideATerminalOneStillLosesOnlyItself() throws {
        let feed = try decodeDiscover("""
        { "items": [ null,
                     { "type": "concept", "data": { "key": "k", "name": "n" } },
                     \(card(id: 7, status: "\"closed\"")),
                     \(card(id: 8, resolutionDate: "\"\(future)\"")) ] }
        """)
        XCTAssertEqual(admitted(feed), [8])
    }
}
