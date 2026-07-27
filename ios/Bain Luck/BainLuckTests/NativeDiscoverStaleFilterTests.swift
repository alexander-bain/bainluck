import XCTest
@testable import Bain_Luck

/// L2-191 — native Discover must never refill with settled cards. These tests
/// pin the pure staleness gate (`DiscoverView.isStaleItem` / `eligibleItems`)
/// that backs the "settled means settled" rule: every terminal/date/extreme
/// class is dropped, and an all-stale payload collapses to `[]` (no restoration
/// path) so the view falls to its graceful end state instead of resurrecting
/// resolved markets or minting a guess slot from them.
///
/// SwiftUI bodies aren't unit-rendered here, so these verify the exact contract
/// the view relies on. `now` is injected for determinism (gotcha #44).
final class NativeDiscoverStaleFilterTests: XCTestCase {

    // Fixed reference instant so date-relative fixtures never straddle a
    // real-world boundary between runs.
    private let now = ISO8601DateFormatter().date(from: "2026-07-27T12:00:00Z")!

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func item(_ json: String) throws -> FeedItem {
        try decoder().decode(FeedItem.self, from: Data(json.utf8))
    }

    /// Build a futures feed item. `movement`/`resolutionDate` are raw JSON
    /// literals (`"null"` or a quoted value) so callers can exercise absence.
    private func futures(
        id: Int = 1,
        status: String = "open",
        probability: Double? = 0.55,
        movement: String = "0.02",
        resolutionDate: String = "null"
    ) throws -> FeedItem {
        let outcomes: String
        if let probability {
            outcomes = """
            "top_outcomes": [{"id": \(id * 10), "name": "Team A", "probability": \(probability), "rank": 1, "movement": \(movement)}],
            """
        } else {
            outcomes = "\"top_outcomes\": [],"
        }
        return try item("""
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Who wins market \(id)?",
            "llm_sport_category": "politics",
            "source": "kalshi",
            "status": "\(status)",
            "resolution_date": \(resolutionDate),
            \(outcomes)
            "outcome_count": 1
          }
        }
        """)
    }

    /// Build an event feed item.
    private func event(
        id: Int = 100,
        status: String = "scheduled",
        commenceTime: String = "null"
    ) throws -> FeedItem {
        try item("""
        {
          "type": "event",
          "score": 90,
          "data": {
            "id": \(id),
            "home_team": "Home",
            "away_team": "Away",
            "status": "\(status)",
            "commence_time": \(commenceTime)
          }
        }
        """)
    }

    // MARK: - Futures: terminal / date

    func testFreshFuturesIsEligible() throws {
        XCTAssertFalse(DiscoverView.isStaleItem(try futures(), now: now))
    }

    func testResolvedFuturesIsStale() throws {
        XCTAssertTrue(DiscoverView.isStaleItem(try futures(status: "resolved"), now: now))
    }

    func testClosedFuturesIsStale() throws {
        XCTAssertTrue(DiscoverView.isStaleItem(try futures(status: "closed"), now: now))
    }

    func testPastResolutionFuturesIsStale() throws {
        // status still "open" (Kalshi settled markets linger as open, gotcha #33)
        // but the resolution date has passed → result-first, stale.
        XCTAssertTrue(DiscoverView.isStaleItem(
            try futures(resolutionDate: "\"2026-07-01T00:00:00Z\""), now: now))
    }

    func testFutureResolutionFuturesIsEligible() throws {
        XCTAssertFalse(DiscoverView.isStaleItem(
            try futures(resolutionDate: "\"2026-12-01T00:00:00Z\""), now: now))
    }

    // MARK: - Futures: extreme / near-decided probability

    func testExtremeHighProbabilityIsStale() throws {
        XCTAssertTrue(DiscoverView.isStaleItem(try futures(probability: 0.99), now: now))
    }

    func testExtremeLowProbabilityIsStale() throws {
        XCTAssertTrue(DiscoverView.isStaleItem(try futures(probability: 0.01), now: now))
    }

    func testNearDecidedWithoutMovementIsStale() throws {
        XCTAssertTrue(DiscoverView.isStaleItem(
            try futures(probability: 0.92, movement: "null"), now: now))
    }

    func testNearDecidedWithMovementIsEligible() throws {
        // A ≥0.90 leader that is still MOVING is a live story, not rot.
        XCTAssertFalse(DiscoverView.isStaleItem(
            try futures(probability: 0.92, movement: "0.03"), now: now))
    }

    // MARK: - Events: expired FINAL

    func testFreshEventIsEligible() throws {
        XCTAssertFalse(DiscoverView.isStaleItem(
            try event(status: "scheduled", commenceTime: "\"2026-07-28T00:00:00Z\""), now: now))
    }

    func testExpiredFinalGameIsStale() throws {
        // Completed and commenced >8h ago → an old FINAL, stale.
        XCTAssertTrue(DiscoverView.isStaleItem(
            try event(status: "completed", commenceTime: "\"2026-07-27T00:00:00Z\""), now: now))
    }

    func testRecentFinalGameIsEligible() throws {
        // Completed but commenced only 3h ago → still a fresh result window.
        XCTAssertFalse(DiscoverView.isStaleItem(
            try event(status: "completed", commenceTime: "\"2026-07-27T09:00:00Z\""), now: now))
    }

    // MARK: - eligibleItems: no all-stale restoration path (Item 1)

    func testAllStalePayloadCollapsesToEmpty() throws {
        let allStale = [
            try futures(id: 1, status: "resolved"),
            try futures(id: 2, status: "closed"),
            try futures(id: 3, probability: 0.99),
            try event(id: 100, status: "completed", commenceTime: "\"2026-07-27T00:00:00Z\""),
        ]
        // The removed fallback would have returned the full set here — the whole
        // point of L2-191 is that it now returns [] so the view shows an honest
        // end state and never mints a guess slot from settled cards.
        XCTAssertTrue(DiscoverView.eligibleItems(allStale, now: now).isEmpty)
    }

    func testMixedPayloadKeepsOnlyEligible() throws {
        let mixed = [
            try futures(id: 1),                                  // fresh
            try futures(id: 2, status: "resolved"),             // drop
            try futures(id: 3, resolutionDate: "\"2026-07-01T00:00:00Z\""), // drop (past)
            try futures(id: 4, probability: 0.99),              // drop (extreme)
            try event(id: 100, status: "scheduled",
                      commenceTime: "\"2026-07-28T00:00:00Z\""), // fresh
            try event(id: 101, status: "completed",
                      commenceTime: "\"2026-07-27T00:00:00Z\""), // drop (old FINAL)
        ]
        let kept = DiscoverView.eligibleItems(mixed, now: now)
        XCTAssertEqual(kept.map(\.id), ["futures-1", "event-100"])
    }

    func testEmptyInputStaysEmpty() throws {
        XCTAssertTrue(DiscoverView.eligibleItems([], now: now).isEmpty)
    }

    // MARK: - Bundles: recursive lifecycle admission (L2-192 Item 1 / C26 P1)

    /// Raw JSON for a single futures child, so bundle fixtures can embed a
    /// mixed set of eligible/stale children (a bundle FeedItem has no top-level
    /// event/futures, so `isStaleItem` alone never inspects its children).
    private func futuresChildJSON(
        id: Int,
        status: String = "open",
        probability: Double? = 0.55,
        movement: String = "0.02",
        resolutionDate: String = "null",
        category: String = "economics"
    ) -> String {
        let outcomes: String
        if let probability {
            outcomes = """
            "top_outcomes": [{"id": \(id * 10), "name": "Team A", "probability": \(probability), "rank": 1, "movement": \(movement)}],
            """
        } else {
            outcomes = "\"top_outcomes\": [],"
        }
        return """
        {
          "type": "futures",
          "score": 90,
          "data": {
            "id": \(id),
            "name": "Who wins market \(id)?",
            "llm_sport_category": "\(category)",
            "source": "kalshi",
            "status": "\(status)",
            "resolution_date": \(resolutionDate),
            \(outcomes)
            "outcome_count": 1
          }
        }
        """
    }

    /// Raw JSON for a single event child (used to embed a stale sports game
    /// inside a mixed bundle for the C29 composition tests).
    private func eventChildJSON(
        id: Int,
        sport: String,
        status: String,
        commenceTime: String
    ) -> String {
        """
        {
          "type": "event",
          "score": 90,
          "data": {
            "id": \(id),
            "sport": "\(sport)",
            "home_team": "Home",
            "away_team": "Away",
            "status": "\(status)",
            "commence_time": \(commenceTime)
          }
        }
        """
    }

    /// A full bundle FeedItem wrapping the given raw child JSON strings.
    private func bundleItem(
        id: String = "b1",
        title: String = "Compare IPOs",
        kind: String = "comparison",
        theme: String = "ipo_valuation",
        children: [String]
    ) throws -> FeedItem {
        try item("""
        {
          "type": "bundle",
          "score": 95,
          "bundle": {
            "id": "\(id)",
            "title": "\(title)",
            "kind": "\(kind)",
            "comparison_theme": "\(theme)",
            "items": [\(children.joined(separator: ","))]
          }
        }
        """)
    }

    private func bundle(
        id: String = "b1",
        title: String = "Compare IPOs",
        kind: String = "comparison",
        theme: String = "ipo_valuation",
        children: [String]
    ) throws -> FeedBundle {
        let item = try item("""
        {
          "type": "bundle",
          "score": 95,
          "bundle": {
            "id": "\(id)",
            "title": "\(title)",
            "kind": "\(kind)",
            "comparison_theme": "\(theme)",
            "items": [\(children.joined(separator: ","))]
          }
        }
        """)
        return try XCTUnwrap(item.bundle)
    }

    func testBundleKeepsOnlyEligibleChildren() throws {
        let b = try bundle(children: [
            futuresChildJSON(id: 1),                                        // fresh
            futuresChildJSON(id: 2, status: "resolved"),                    // drop
            futuresChildJSON(id: 3, resolutionDate: "\"2026-07-01T00:00:00Z\""), // drop (past)
            futuresChildJSON(id: 4, probability: 0.99),                     // drop (extreme)
            futuresChildJSON(id: 5),                                        // fresh
        ])
        let kept = DiscoverView.eligibleBundleItems(b, now: now)
        XCTAssertEqual(kept.map(\.id), ["futures-1", "futures-5"])
    }

    func testAllStaleBundleCollapsesToEmpty() throws {
        let b = try bundle(children: [
            futuresChildJSON(id: 1, status: "resolved"),
            futuresChildJSON(id: 2, status: "closed"),
            futuresChildJSON(id: 3, probability: 0.01),
        ])
        // An all-stale bundle yields [] so groupedItems drops the whole card —
        // no stale comparison renders ("settled means settled").
        XCTAssertTrue(DiscoverView.eligibleBundleItems(b, now: now).isEmpty)
    }

    func testAllEligibleBundleIsUnchanged() throws {
        let b = try bundle(children: [
            futuresChildJSON(id: 1),
            futuresChildJSON(id: 2, probability: 0.60),
            futuresChildJSON(id: 3, resolutionDate: "\"2026-12-01T00:00:00Z\""),
        ])
        let kept = DiscoverView.eligibleBundleItems(b, now: now)
        XCTAssertEqual(kept.map(\.id), ["futures-1", "futures-2", "futures-3"])
    }

    func testEmptyBundleStaysEmpty() throws {
        let b = try bundle(children: [])
        XCTAssertTrue(DiscoverView.eligibleBundleItems(b, now: now).isEmpty)
    }

    // MARK: - Bundle sanitization BEFORE composition (C29 P2)

    /// `sanitizedFeedItems` is the carry-through representation `filteredItems`
    /// consumes BEFORE category derivation, cooldown, dismiss, interleave, and
    /// grouping — so these are composition-boundary assertions, not just
    /// helper-output ones: whatever the bundle looks like here is exactly what
    /// every downstream consumer sees.
    func testSanitizedBundleLeadsWithFirstEligibleChildCategory() throws {
        // Stale sports FIRST, eligible politics SECOND. Before C29, category /
        // cooldown / interleave read the raw first child (basketball) and could
        // suppress or mis-slot the card. After sanitization the bundle's first
        // child is the eligible politics market, so its derived category is
        // "politics".
        let b = try bundleItem(children: [
            // completed game commenced >8h ago → stale
            eventChildJSON(id: 100, sport: "basketball", status: "completed", commenceTime: "\"2026-07-27T00:00:00Z\""),
            futuresChildJSON(id: 5, category: "politics"),
        ])
        let sanitized = DiscoverView.sanitizedFeedItems([b], now: now)
        XCTAssertEqual(sanitized.count, 1, "bundle survives — it has an eligible child")
        let bundle = try XCTUnwrap(sanitized.first?.bundle)
        XCTAssertEqual(bundle.items.map(\.id), ["futures-5"], "stale sports dropped; eligible politics leads")
        XCTAssertEqual(bundle.items.first?.futures?.llmSportCategory, "politics",
                       "category derives from the first ELIGIBLE child, not stale basketball")
    }

    func testAllIneligibleBundleDroppedBeforeComposition() throws {
        // An all-stale bundle disappears in sanitization, before any category /
        // cooldown step — so it can never suppress or displace a neighbor card.
        let deadBundle = try bundleItem(id: "dead", children: [
            futuresChildJSON(id: 1, status: "resolved"),
            futuresChildJSON(id: 2, status: "closed"),
        ])
        let liveNeighbor = try futures(id: 9)  // ordinary fresh futures
        let sanitized = DiscoverView.sanitizedFeedItems([deadBundle, liveNeighbor], now: now)
        XCTAssertEqual(sanitized.count, 1, "dead bundle removed")
        XCTAssertEqual(sanitized.first?.futures?.id, 9, "neighbor survives untouched")
    }

    func testSanitizedBundlePreservesMetadataAndChildOrder() throws {
        let b = try bundleItem(id: "b1", title: "Compare IPOs", kind: "comparison", theme: "ipo_valuation", children: [
            futuresChildJSON(id: 1),
            futuresChildJSON(id: 2, status: "resolved"),   // drop
            futuresChildJSON(id: 3),
        ])
        let sanitized = DiscoverView.sanitizedFeedItems([b], now: now)
        let bundle = try XCTUnwrap(sanitized.first?.bundle)
        XCTAssertEqual(bundle.id, "b1")
        XCTAssertEqual(bundle.title, "Compare IPOs")
        XCTAssertEqual(bundle.kind, "comparison")
        XCTAssertEqual(bundle.comparisonTheme, "ipo_valuation")
        XCTAssertEqual(bundle.items.map(\.id), ["futures-1", "futures-3"],
                       "eligible child order preserved, stale removed")
    }

    func testSanitizationLeavesOrdinaryItemsToTheLaterStaleGate() throws {
        // sanitizedFeedItems admits only BUNDLE children; ordinary items (even
        // stale) pass through untouched and are gated later by eligibleItems in
        // filteredItems. This keeps bundle admission a pure, orthogonal step.
        let staleOrdinary = try futures(id: 7, status: "resolved")
        let sanitized = DiscoverView.sanitizedFeedItems([staleOrdinary], now: now)
        XCTAssertEqual(sanitized.map(\.id), ["futures-7"], "ordinary items pass through this step")
        XCTAssertTrue(DiscoverView.eligibleItems(sanitized, now: now).isEmpty,
                      "the later gate still removes the stale ordinary item")
    }
}
