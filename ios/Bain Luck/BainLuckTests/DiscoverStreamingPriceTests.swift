import XCTest
import Combine
@testable import Bain_Luck

@MainActor
final class DiscoverStreamingPriceTests: XCTestCase {
    private func decode<T: Decodable>(_ value: Any, as: T.Type) throws -> T {
        let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: JSONSerialization.data(withJSONObject: value))
    }

    private func market(_ id: Int = 1, p: Double = 0.4,
                        clocks: [String: String] = ["10": "2026-09-29T00:01:00Z", "20": "2026-09-29T00:01:00Z"],
                        leader: Int = 10, status: String = "open", group: String = "g") throws -> FeedItem {
        try decode(["type": "futures", "score": 90, "headline": "Original editorial",
                    "data": ["id": id, "name": "Market?", "source": "kalshi", "status": status,
                             "llm_sport_category": "economics", "group_id": group,
                             "canonical_market_key": "key", "outcome_observed_at": clocks,
                             "top_outcomes": [["id": leader, "name": "Leader", "probability": p,
                                               "price_observed_at": clocks[String(leader)] ?? ""]],
                             "outcome_count": 2]], as: FeedItem.self)
    }

    private func event(rev: Int?, clock: String?, p: Double = 0.5, status: String = "scheduled") throws -> FeedItem {
        var data: [String: Any] = ["id": 1, "home_team": "Home", "away_team": "Away",
                                  "status": status, "hero_probability_source": "blend",
                                  "current_odds": ["home_probability": p, "away_probability": 1-p]]
        if let rev { data["blend_fold_revision"] = ["1": rev] }
        if let clock { data["hero_probability_observed_at"] = clock }
        return try decode(["type": "event", "score": 90, "data": data], as: FeedItem.self)
    }

    func testNewFoldRevisionWinsDespiteOlderObservationClock() throws {
        XCTAssertTrue(DiscoverPriceRefresh.canAdopt(
            try event(rev: 3, clock: "2026-09-29T00:01:00Z", p: 0.7),
            over: try event(rev: 2, clock: "2026-09-29T00:02:00Z")))
    }

    func testFinalResultDoesNotNeedANewProbabilityRevisionOrFakeClock() throws {
        XCTAssertTrue(DiscoverPriceRefresh.canAdopt(
            try event(rev: 3, clock: nil, status: "completed"),
            over: try event(rev: 3, clock: "2026-09-29T00:01:00Z", status: "live")))
    }

    func testOlderOrMissingFoldCannotOverwriteNewerEvenWithLaterClock() throws {
        let held = try event(rev: 3, clock: "2026-09-29T00:01:00Z")
        for rev: Int? in [2, nil] {
            XCTAssertFalse(DiscoverPriceRefresh.canAdopt(
                try event(rev: rev, clock: "2026-09-29T00:02:00Z"), over: held))
        }
    }

    func testOneOutcomeRegressingIsNotHiddenByAnotherAdvancing() throws {
        let next = try market(p: 0.6, clocks: ["10": "2026-09-29T00:00:00Z", "20": "2026-09-29T00:03:00Z"])
        XCTAssertFalse(DiscoverPriceRefresh.canAdopt(next, over: try market()))
    }

    func testTopNMayChangeWithCompleteDominatingRawVector() throws {
        let next = try market(p: 0.7, clocks: ["10": "2026-09-29T00:01:00Z", "20": "2026-09-29T00:03:00Z"], leader: 20)
        XCTAssertTrue(DiscoverPriceRefresh.canAdopt(next, over: try market()))
    }

    func testDivisorChangeCanMoveEqualClockDisplayedLeg() throws {
        let next = try market(p: 0.6, clocks: ["10": "2026-09-29T00:01:00Z", "20": "2026-09-29T00:03:00Z"])
        XCTAssertTrue(DiscoverPriceRefresh.canAdopt(next, over: try market()))
    }

    func testUnknownOrEqualVectorCannotInventNewPrice() throws {
        XCTAssertFalse(DiscoverPriceRefresh.canAdopt(try market(p: 0.8), over: try market()))
        let unknown = try decode(["type": "futures", "data": ["id": 1, "name": "Market?", "source": "kalshi",
            "group_id": "g", "canonical_market_key": "key", "top_outcomes": [["id": 10, "name": "Leader", "probability": 0.8]]]], as: FeedItem.self)
        XCTAssertFalse(DiscoverPriceRefresh.canAdopt(unknown, over: try market()))
    }

    func testSettledStateAndSourceIdentityCannotRegress() throws {
        XCTAssertFalse(DiscoverPriceRefresh.canAdopt(try market(), over: try market(status: "closed")))
        XCTAssertFalse(DiscoverPriceRefresh.canAdopt(try market(group: "other"), over: try market()))
        XCTAssertFalse(DiscoverPriceRefresh.canAdopt(try event(rev: 4, clock: nil), over: try event(rev: 3, clock: nil, status: "completed")))
    }

    func testFreshUpdatePreservesMembershipOrderAndEditorials() throws {
        let held = try [market(1), market(2)]
        let next = try market(p: 0.8, clocks: ["10": "2026-09-29T00:02:00Z", "20": "2026-09-29T00:02:00Z"])
        var epochs: [String: Double] = [:]
        let response = DiscoverPriceCards(items: [try market(3), next], dispositions: ["futures-1": "updated", "futures-3": "updated"], builtAt: 100)
        let result = DiscoverPriceRefresh.apply(response, to: held, epochs: &epochs)
        XCTAssertEqual(result.map(\.id), held.map(\.id))
        XCTAssertEqual(result[0].futures?.topOutcomes?.first?.probability, 0.8)
        XCTAssertEqual(result[1].futures?.topOutcomes?.first?.probability, 0.4)
        XCTAssertEqual(result[0].headline, held[0].headline)
    }

    func testCachedFeedCannotRollBackAlreadyAcceptedPrices() throws {
        let old = try market()
        let new = try market(p: 0.8, clocks: ["10": "2026-09-29T00:02:00Z", "20": "2026-09-29T00:02:00Z"])
        var accepted = [new.id: new]
        let result = DiscoverPriceRefresh.retainingPrices([old, try market(2)], accepted: &accepted)
        XCTAssertEqual(result[0].futures?.topOutcomes?.first?.probability, 0.8)
        XCTAssertEqual(result.map(\.id), ["futures-1", "futures-2"])
    }

    func testNewerOrdinaryFeedAdoptionAdvancesTheRetainedFence() throws {
        let t1 = try market()
        let t2 = try market(p: 0.6, clocks: ["10": "2026-09-29T00:02:00Z", "20": "2026-09-29T00:02:00Z"])
        let t3 = try market(p: 0.8, clocks: ["10": "2026-09-29T00:03:00Z", "20": "2026-09-29T00:03:00Z"])
        var accepted = [t1.id: t1]
        _ = DiscoverPriceRefresh.retainingPrices([t3], accepted: &accepted)
        let result = DiscoverPriceRefresh.retainingPrices([t2], accepted: &accepted)
        XCTAssertEqual(result[0].futures?.topOutcomes?.first?.probability, 0.8)
    }

    func testExpiredPriceCanBeWithheldWithoutCachedFeedResurrectingIt() throws {
        let old = try event(rev: 3, clock: "2026-09-29T00:01:00Z")
        let withheld = try decode(["type": "event", "data": ["id": 1, "home_team": "Home", "away_team": "Away",
            "status": "scheduled", "blend_fold_revision": ["1": 3]]], as: FeedItem.self)
        var epochs: [String: Double] = [:]
        let result = DiscoverPriceRefresh.apply(DiscoverPriceCards(items: [withheld], dispositions: [old.id: "withheld"], builtAt: 100), to: [old], epochs: &epochs)
        XCTAssertNil(result[0].event?.currentOdds)
        var accepted = [old.id: result[0]]
        let reloaded = DiscoverPriceRefresh.retainingPrices([old], accepted: &accepted)
        XCTAssertNil(reloaded[0].event?.currentOdds)
    }

    func testUnresolvedOrOlderResponseDoesNotDeleteOrOverwriteCard() throws {
        let old = try market()
        let new = try market(p: 0.8, clocks: ["10": "2026-09-29T00:02:00Z", "20": "2026-09-29T00:02:00Z"])
        var epochs = [old.id: 100.0]
        for response in [DiscoverPriceCards(items: [new], dispositions: [old.id: "unresolved"], builtAt: 101),
                         DiscoverPriceCards(items: [new], dispositions: [old.id: "updated"], builtAt: 99)] {
            let result = DiscoverPriceRefresh.apply(response, to: [old], epochs: &epochs)
            XCTAssertEqual(result.count, 1)
            XCTAssertEqual(result[0].futures?.topOutcomes?.first?.probability, 0.4)
        }
    }

    func testBurstAndFiftyCardBatchesShareOneDispatchBudget() {
        var pacer = DiscoverPriceReadPacer()
        var dispatched = 0
        for tick in 0..<1000 {
            let now = Double(tick) / 1000
            if pacer.delay(at: now) == 0 {
                pacer.didDispatch(at: now)
                dispatched += 1
            }
        }
        XCTAssertEqual(dispatched, 1)
        XCTAssertEqual(pacer.delay(at: 1), 1)
        XCTAssertEqual(pacer.delay(at: 2), 0)
        pacer.didDispatch(at: 2)
        XCTAssertEqual(pacer.delay(at: 2), 2, "the next50-card batch has the same budget")
    }

    func testRateLimitBackoffSurvivesNewInvalidationsAndUsesSafeFallback() {
        var pacer = DiscoverPriceReadPacer()
        pacer.didDispatch(at: 100)
        XCTAssertTrue(pacer.observe(APIError.httpError(statusCode: 429, body: "{\"retry_after\":17}"), at: 101))
        XCTAssertEqual(pacer.delay(at: 110), 8)
        XCTAssertEqual(pacer.delay(at: 118), 0)
        XCTAssertTrue(pacer.observe(APIError.httpError(statusCode: 429, body: "malformed"), at: 118))
        XCTAssertEqual(pacer.delay(at: 120), 58)
        XCTAssertFalse(pacer.observe(APIError.httpError(statusCode: 503, body: nil), at: 121))
        XCTAssertEqual(pacer.delay(at: 120), 58)
    }

    private nonisolated final class Client: DiscoverFeedProviding, DiscoverPriceCardsProviding, @unchecked Sendable {
        let feed: FeedResponse
        private var next: DiscoverPriceCards
        private let lock = NSLock()
        init(feed: FeedResponse, next: DiscoverPriceCards) { self.feed = feed; self.next = next }
        func fetchDiscoverFeed(limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?) async throws -> FeedResponse { feed }
        func fetchDiscoverPriceCards(eventIds: [Int], marketIds: [Int]) async throws -> DiscoverPriceCards {
            lock.withLock { next }
        }
        func setNext(_ value: DiscoverPriceCards) { lock.withLock { next = value } }
    }

    private final class Handle: LiveStreamHandle {
        var handlers: [String: @MainActor (String) -> Void] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event] = handler }
        func close() { isClosed = true }
        func emit(_ event: String, _ data: String) { handlers[event]?(data) }
    }

    func testVisibleMarketPushRefreshesInPlaceAndDisappearanceStopsSocket() async throws {
        let old = try market()
        let fresh = try market(p: 0.8, clocks: ["10": "2026-09-29T00:02:00Z", "20": "2026-09-29T00:02:00Z"])
        let feed = try decode(["items": [["type": "futures", "score": 90, "data": ["id": 1,
            "name": "Market?", "source": "kalshi", "status": "open", "llm_sport_category": "economics",
            "group_id": "g", "canonical_market_key": "key", "outcome_count": 2,
            "outcome_observed_at": ["10": "2026-09-29T00:01:00Z", "20": "2026-09-29T00:01:00Z"],
            "top_outcomes": [["id": 10, "name": "Leader", "probability": 0.4,
                              "price_observed_at": "2026-09-29T00:01:00Z"]]]]],
            "total": 1, "limit": 50, "offset": 0, "has_more": false, "edition": "e"], as: FeedResponse.self)
        let client = Client(feed: feed, next: DiscoverPriceCards(items: [old], dispositions: [old.id: "updated"], builtAt: 100))
        let handle = Handle()
        let vm = DiscoverViewModel(client: client, priceClient: client, makePriceMarketHandle: { _ in handle }, lastGood: nil, telemetry: nil)
        await vm.load()
        vm.setPriceCardsVisible(owner: old.id, cards: [old], visible: true)
        vm.setPriceDeliveryActive(true)
        await vm.refreshPricesInPlace()
        client.setNext(DiscoverPriceCards(items: [fresh], dispositions: [old.id: "updated"], builtAt: 101))
        handle.emit("market", "{\"market_id\":1,\"invalidation\":true,\"terminal\":false}")
        // Await the observable publication, rather than treating one Task.yield as scheduling proof.
        let arrived = expectation(description: "push adopted")
        let observation = vm.$items.sink { items in
            if items.first?.futures?.topOutcomes?.first?.probability == 0.8 { arrived.fulfill() }
        }
        await fulfillment(of: [arrived], timeout: 6)
        observation.cancel()
        XCTAssertEqual(vm.items.map(\.id), [old.id])
        await vm.load() // the fake returns the OLD cached price body again
        XCTAssertEqual(vm.items.first?.futures?.topOutcomes?.first?.probability, 0.8)
        vm.setPriceCardsVisible(owner: old.id, cards: [], visible: false)
        XCTAssertTrue(handle.isClosed)
        vm.setPriceDeliveryActive(false)
    }
}
