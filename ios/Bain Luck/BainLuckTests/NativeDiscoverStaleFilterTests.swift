import XCTest
@testable import Bain_Luck

/// L2-191 — native Discover must never refill with settled cards. These tests
/// pin the pure staleness gate (`DiscoverView.isStaleItem` / `eligibleItems`)
/// that backs the "settled means settled" rule: every AUTHORITATIVE terminal/date
/// class is dropped, and an all-stale payload collapses to `[]` (no restoration
/// path) so the view falls to its graceful end state instead of resurrecting
/// resolved markets or minting a guess slot from them. L2-214: probability alone
/// NEVER settles a card — a near-certain but OPEN market still surfaces.
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

    // MARK: - Futures: probability alone NEVER settles a card (L2-214)

    func testExtremeHighProbabilityStillEligible() throws {
        // 0.99 but OPEN with no terminal/date evidence → still a valid prediction.
        // Price is not settlement authority (L2-214).
        XCTAssertFalse(DiscoverView.isStaleItem(try futures(probability: 0.99), now: now))
    }

    func testExtremeLowProbabilityStillEligible() throws {
        XCTAssertFalse(DiscoverView.isStaleItem(try futures(probability: 0.01), now: now))
    }

    func testNearDecidedWithoutMovementStillEligible() throws {
        // Previously hidden as "effectively resolved" from price alone; the client
        // no longer infers settlement — only authoritative status/date does.
        XCTAssertFalse(DiscoverView.isStaleItem(
            try futures(probability: 0.92, movement: "null"), now: now))
    }

    func testNearCertainButResolvedIsStale() throws {
        // Authoritative status STILL settles it, independent of probability.
        XCTAssertTrue(DiscoverView.isStaleItem(
            try futures(status: "resolved", probability: 0.99), now: now))
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
            try futures(id: 3, resolutionDate: "\"2026-07-01T00:00:00Z\""), // past resolution (authoritative)
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
            try futures(id: 4, probability: 0.99),              // KEEP — near-certain but OPEN (L2-214: price never settles)
            try event(id: 100, status: "scheduled",
                      commenceTime: "\"2026-07-28T00:00:00Z\""), // fresh
            try event(id: 101, status: "completed",
                      commenceTime: "\"2026-07-27T00:00:00Z\""), // drop (old FINAL)
        ]
        let kept = DiscoverView.eligibleItems(mixed, now: now)
        XCTAssertEqual(kept.map(\.id), ["futures-1", "futures-4", "event-100"])
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
          "data": {
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
          "data": {
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
            futuresChildJSON(id: 4, probability: 0.99),                     // KEEP — open, price never settles (L2-214)
            futuresChildJSON(id: 5),                                        // fresh
        ])
        let kept = DiscoverView.eligibleBundleItems(b, now: now)
        XCTAssertEqual(kept.map(\.id), ["futures-1", "futures-4", "futures-5"])
    }

    func testAllStaleBundleCollapsesToEmpty() throws {
        let b = try bundle(children: [
            futuresChildJSON(id: 1, status: "resolved"),
            futuresChildJSON(id: 2, status: "closed"),
            futuresChildJSON(id: 3, resolutionDate: "\"2026-07-01T00:00:00Z\""), // past resolution (authoritative)
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

    // MARK: - Events: `scheduled` past its kickoff grace (#10094)

    /// A quoted ISO stamp `offset` seconds from the fixed `now` (negative = past),
    /// so every boundary below is offset from one injected instant (gotcha #44).
    private func stamp(_ offset: TimeInterval) -> String {
        "\"\(ISO8601DateFormatter().string(from: now.addingTimeInterval(offset)))\""
    }

    private let hour: TimeInterval = 3600

    /// One event card with the fields the Discover gate reads. Every value is a
    /// raw JSON literal so a caller can exercise ABSENCE (`null`) as its own fact.
    private func game(
        id: Int = 200,
        status: String = "\"scheduled\"",
        commenceTime: String = "null",
        endedAt: String = "null",
        startIsTbd: String = "null",
        marqueeFinal: String = "null"
    ) throws -> FeedItem {
        try item("""
        {
          "type": "event",
          "score": 90,
          "data": {
            "id": \(id),
            "sport": "baseball_mlb",
            "home_team": "Kansas City Royals",
            "away_team": "Chicago White Sox",
            "status": \(status),
            "commence_time": \(commenceTime),
            "ended_at": \(endedAt),
            "start_is_tbd": \(startIsTbd),
            "discover_marquee_final": \(marqueeFinal)
          }
        }
        """)
    }

    func testTheCachedWhiteSoxCardAWeekPastKickoffIsWithheld() throws {
        // The Sep 23 disk deck's row: event 15314409, `scheduled`, first pitch
        // Sep 24 18:10Z, painted on Oct 1 as "White Sox vs Royals".
        let cached = try game(id: 15314409, commenceTime: stamp(-7 * 24 * hour))
        XCTAssertTrue(DiscoverView.isStaleItem(cached, now: now))
        XCTAssertTrue(DiscoverView.eligibleItems([cached], now: now).isEmpty)
    }

    func testTheGraceBoundaryIsStrictSoExactlyTwoHoursStillShows() throws {
        XCTAssertEqual(FeedLifecycle.scheduledKickoffGrace, 2 * hour)
        XCTAssertFalse(DiscoverView.isStaleItem(
            try game(commenceTime: stamp(-2 * hour)), now: now))
        XCTAssertTrue(DiscoverView.isStaleItem(
            try game(commenceTime: stamp(-2 * hour - 1)), now: now))
    }

    func testAFutureOrJustStartedScheduledGameStays() throws {
        XCTAssertFalse(DiscoverView.isStaleItem(try game(commenceTime: stamp(3 * hour)), now: now))
        XCTAssertFalse(DiscoverView.isStaleItem(try game(commenceTime: stamp(-1 * hour)), now: now))
    }

    func testOnlyScheduledIsWithheldByKickoffAge() throws {
        // A genuinely live game is never dropped for how long ago it started, and
        // neither is any status this rule has no reading for.
        for status in ["\"live\"", "\"suspended\"", "\"postponed\"", "\"\"", "null"] {
            XCTAssertFalse(
                DiscoverView.isStaleItem(
                    try game(status: status, commenceTime: stamp(-7 * 24 * hour)), now: now),
                "\(status) a week past kickoff must not be withheld by kickoff age"
            )
        }
    }

    func testAnAbsentOrUnreadableKickoffKeepsTheCard() throws {
        XCTAssertFalse(DiscoverView.isStaleItem(try game(commenceTime: "null"), now: now))
        XCTAssertFalse(DiscoverView.isStaleItem(
            try game(commenceTime: "\"not a date\""), now: now))
    }

    func testAPlaceholderKickoffKeepsItsWholeDay() throws {
        // #8841: the server's word that the clock is StatPal's placeholder. The
        // real first pitch can be hours after it, so 2h would drop a game that has
        // not started; the card lapses only once the day itself is gone.
        XCTAssertEqual(FeedLifecycle.placeholderKickoffGrace, 24 * hour)
        XCTAssertFalse(DiscoverView.isStaleItem(
            try game(commenceTime: stamp(-5 * hour), startIsTbd: "true"), now: now))
        XCTAssertFalse(DiscoverView.isStaleItem(
            try game(commenceTime: stamp(-24 * hour), startIsTbd: "true"), now: now))
        XCTAssertTrue(DiscoverView.isStaleItem(
            try game(commenceTime: stamp(-24 * hour - 1), startIsTbd: "true"), now: now))
        // `false` and absent read alike: the ordinary 2h grace.
        XCTAssertTrue(DiscoverView.isStaleItem(
            try game(commenceTime: stamp(-5 * hour), startIsTbd: "false"), now: now))
    }

    func testFinishedGamesKeepTheirOwnWindowsUnchanged() throws {
        let completed = "\"completed\""
        // Ordinary 8h from the whistle, strict.
        XCTAssertFalse(DiscoverView.isStaleItem(
            try game(status: completed, commenceTime: stamp(-11 * hour), endedAt: stamp(-8 * hour)), now: now))
        XCTAssertTrue(DiscoverView.isStaleItem(
            try game(status: completed, commenceTime: stamp(-11 * hour), endedAt: stamp(-8 * hour - 1)), now: now))
        // The whistle outranks the kickoff; the kickoff is only the fallback.
        XCTAssertFalse(DiscoverView.isStaleItem(
            try game(status: completed, commenceTime: stamp(-30 * hour), endedAt: stamp(-1 * hour)), now: now))
        XCTAssertTrue(DiscoverView.isStaleItem(
            try game(status: "\"closed\"", commenceTime: stamp(-9 * hour)), now: now))
        // A marquee final Discover kept on purpose: 14h.
        XCTAssertFalse(DiscoverView.isStaleItem(
            try game(status: completed, endedAt: stamp(-14 * hour), marqueeFinal: "true"), now: now))
        XCTAssertTrue(DiscoverView.isStaleItem(
            try game(status: completed, endedAt: stamp(-14 * hour - 1), marqueeFinal: "true"), now: now))
    }

    func testTheSharedFinishedPredicateIsNotWidened() throws {
        // The Sports tab reads `finishedEventIsExpired` too; this rule lives beside
        // it, so a lapsed `scheduled` card is still "not finished" there.
        let lapsed = try XCTUnwrap(try game(commenceTime: stamp(-7 * 24 * hour)).event)
        XCTAssertFalse(FeedLifecycle.finishedEventIsExpired(lapsed, now: now))
        XCTAssertTrue(FeedLifecycle.scheduledKickoffHasLapsed(lapsed, now: now))
        XCTAssertEqual(lapsed.status, "scheduled", "the gate reads the card; it never rewrites it")
    }

    func testAMixedDeckLosesOnlyTheLapsedGame() throws {
        let deck = [
            try futures(id: 1),
            try game(id: 201, commenceTime: stamp(-7 * 24 * hour)),          // drop
            try game(id: 202, commenceTime: stamp(4 * hour)),                // keep
            try game(id: 203, status: "\"live\"", commenceTime: stamp(-3 * hour)), // keep
            try game(id: 204, commenceTime: stamp(-90 * 60)),                // keep, inside grace
        ]
        XCTAssertEqual(DiscoverView.eligibleItems(deck, now: now).map(\.id),
                       ["futures-1", "event-202", "event-203", "event-204"])
    }

    func testAnAllLapsedDeckIsEmptyWithNoRestoration() throws {
        let deck = [
            try game(id: 201, commenceTime: stamp(-7 * 24 * hour)),
            try game(id: 202, commenceTime: stamp(-3 * hour)),
        ]
        XCTAssertTrue(DiscoverView.eligibleItems(deck, now: now).isEmpty)
        XCTAssertEqual(
            DiscoverView.undismissedEligibleCount(in: deck, dismissedAt: [:], now: now), 0)
    }

    func testALapsedGameInsideABundleIsDroppedBeforeComposition() throws {
        let b = try bundleItem(children: [
            eventChildJSON(id: 300, sport: "baseball_mlb", status: "scheduled",
                           commenceTime: stamp(-7 * 24 * hour)),
            futuresChildJSON(id: 6, category: "politics"),
        ])
        let sanitized = DiscoverView.sanitizedFeedItems([b], now: now)
        XCTAssertEqual(try XCTUnwrap(sanitized.first?.bundle).items.map(\.id), ["futures-6"])
    }
}
