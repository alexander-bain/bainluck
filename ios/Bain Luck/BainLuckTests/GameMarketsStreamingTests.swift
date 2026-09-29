import XCTest
@testable import Bain_Luck

@MainActor
final class GameMarketsStreamingTests: XCTestCase {
    private let t0 = "2030-01-01T00:00:00.000001Z"
    private let t1 = "2030-01-01T00:00:00.000002Z"
    private let t2 = "2030-01-01T00:00:00.000003Z"

    private func body(_ x: Double? = 0.4, _ y: Double? = 0.6,
                      xClock: String? = "2030-01-01T00:00:00.000001Z",
                      yClock: String? = "2030-01-01T00:00:00.000001Z",
                      status: String = "scheduled", score: Int? = nil,
                      verdict: Bool? = nil, verdictFirstOnly: Bool = false, includeX: Bool = true,
                      marketIDs: [Int] = [7]) throws -> GameMarketsResponse {
        func null(_ value: Any?) -> Any { value ?? NSNull() }
        func row(_ name: String, _ id: Int, _ price: Double?) -> [String: Any] {
            ["market_name": "Spread", "outcome_name": name, "probability": null(price),
             "source": "kalshi", "_market_id": 7, "contributor_outcome_ids": [id],
             "is_winner": null(verdictFirstOnly && id != 1 ? nil : verdict)]
        }
        let dict: [String: Any] = ["event_id": 12, "status": status, "home_score": null(score),
            "away_score": null(score), "stream_market_ids": marketIDs,
            "spreads": (includeX ? [row("X", 1, x)] : []) + [row("Y", 2, y)],
            "outcome_market_ids": ["1": 7, "2": 7],
            "outcome_revision_at": ["1": null(xClock), "2": null(yClock)],
            "outcome_observed_at": ["1": NSNull(), "2": "2029-12-31T00:00:00Z"]]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func adopt(_ next: GameMarketsResponse, _ held: GameMarketsResponse?,
                       _ fence: inout GameMarketsPriceReconciliation.Fence) -> GameMarketsResponse {
        GameMarketsPriceReconciliation.adopting(next, over: held, fence: &fence)
    }

    func testAdditiveIdentityAndClocksDecodeWithoutInventingObservation() throws {
        let value = try body()
        XCTAssertEqual(value.spreads?.first?._marketId, 7)
        XCTAssertEqual(value.spreads?.first?.contributorOutcomeIds, [1])
        XCTAssertEqual(value.outcomeRevisionAt?["1"] ?? nil, t0)
        XCTAssertNil(value.outcomeObservedAt?["1"] ?? nil)
        XCTAssertEqual(value.outcomeObservedAt?["2"] ?? nil, "2029-12-31T00:00:00Z")
    }

    func testWholeNormalizedVectorAdoptsAndNeverSplicesOlderSibling() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        let changed = adopt(try body(0.5, 0.5, xClock: t1), held, &fence)
        XCTAssertEqual(changed.spreads?.map(\.probability), [0.5, 0.5])
        let stale = adopt(try body(0.9, 0.1, xClock: t2,
            yClock: "2029-12-31T00:00:00Z"), changed, &fence)
        XCTAssertEqual(stale, changed)
        XCTAssertEqual(adopt(try body(0.9, 0.1, xClock: t1), changed, &fence), changed)
    }

    func testEqualUnknownWithdrawalAndSiblingAdvanceCannotResurrect() throws {
        for clock in [t0, nil] {
            var fence = GameMarketsPriceReconciliation.Fence()
            let held = adopt(try body(), nil, &fence)
            let cleared = adopt(try body(nil, 1, xClock: clock), held, &fence)
            XCTAssertNil(cleared.spreads?.first?.probability)
            let cached = adopt(try body(0.3, 0.7, yClock: t1), cleared, &fence)
            XCTAssertNil(cached.spreads?.first?.probability)
            let restored = adopt(try body(0.3, 0.7, xClock: t1, yClock: t1), cached, &fence)
            XCTAssertEqual(restored.spreads?.first?.probability, 0.3)
        }
    }

    func testInitialNullAndRemovedRowsRetainPrivateRestorationFence() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(nil, 1, xClock: nil), nil, &fence)
        XCTAssertNil(adopt(try body(0.3, 0.7, xClock: nil, yClock: t1), held, &fence).spreads?.first?.probability)
        let firstQuote = adopt(try body(0.3, 0.7, xClock: t1, yClock: t1), held, &fence)
        XCTAssertEqual(firstQuote.spreads?.first?.probability, 0.3)
        let removed = adopt(try body(yClock: t1, includeX: false), firstQuote, &fence)
        // This attempted removal has an older raw revision and is refused.
        XCTAssertEqual(removed, firstQuote)
        let removedFresh = adopt(try body(xClock: t1, yClock: t1, includeX: false), firstQuote, &fence)
        XCTAssertEqual(removedFresh.spreads?.count, 1)
        XCTAssertEqual(adopt(try body(0.3, 0.7, xClock: t1, yClock: t2), removedFresh, &fence).spreads?.count, 1)
    }

    func testFinalScoresAndKnownLoserGradeSurviveNewQuotes() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(status: "completed", score: 3, verdict: false), nil, &fence)
        XCTAssertEqual(adopt(try body(0.5, 0.5, xClock: t1, status: "completed", score: 3), held, &fence), held)
        XCTAssertEqual(adopt(try body(0.5, 0.5, xClock: t1, status: "completed", score: 2, verdict: false), held, &fence), held)
        XCTAssertEqual(adopt(try body(0.5, 0.5, xClock: t1, status: "live", score: 3, verdict: false), held, &fence), held)
    }

    func testNewTerminalGradeWithNullClockArrivesWithoutRelaxingOlderOrUngradedRows() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(), nil, &fence)
        let result = adopt(try body(0, 1, xClock: nil, status: "completed", score: 3,
            verdict: false, verdictFirstOnly: true), held, &fence)
        XCTAssertEqual(result.spreads?.first?.isWinner, false)
        XCTAssertEqual(result.spreads?.map(\.probability), [0, 1])
        XCTAssertNil(result.outcomeRevisionAt?["1"] ?? nil, "do not manufacture a terminal clock")

        var olderFence = GameMarketsPriceReconciliation.Fence()
        let olderHeld = adopt(try body(), nil, &olderFence)
        XCTAssertEqual(adopt(try body(0, 1, xClock: "2029-12-31T00:00:00Z", status: "completed", score: 3,
            verdict: false, verdictFirstOnly: true), olderHeld, &olderFence), olderHeld)
        XCTAssertEqual(adopt(try body(0, 1, xClock: nil, yClock: nil, status: "completed", score: 3,
            verdict: false, verdictFirstOnly: true), olderHeld, &olderFence), olderHeld,
            "a new grade cannot launder a missing ungraded sibling revision")
    }

    func testActualWithoutGradeCannotBypassMissingQuoteRevision() throws {
        func prop(actual: String, revision: String) throws -> GameMarketsResponse {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(GameMarketsResponse.self, from: Data("""
            {"event_id":12,"status":"completed","stream_market_ids":[7],
             "outcome_market_ids":{"1":7},"outcome_revision_at":{"1":\(revision)},
             "player_props":[{"market_name":"Prop","outcome_name":"Player","over_probability":0.6,
                "source":"kalshi","_market_id":7,"contributor_outcome_ids":[1],"actual":\(actual),"hit":null}]}
            """.utf8))
        }
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try prop(actual: "null", revision: "\"\(t0)\""), nil, &fence)
        let incoming = try prop(actual: "3", revision: "null")
        XCTAssertEqual(adopt(incoming, held, &fence), held,
            "actual without hit is not a verdict when the grading threshold is unavailable")
    }

    func testUnresolvedMarketKeepsUpdatingAfterSportFinal() throws {
        var fence = GameMarketsPriceReconciliation.Fence()
        let held = adopt(try body(status: "completed", score: 3), nil, &fence)
        let next = adopt(try body(0.5, 0.5, xClock: t1, status: "completed", score: 3), held, &fence)
        XCTAssertEqual(next.spreads?.map(\.probability), [0.5, 0.5])
        XCTAssertEqual(next.status, "completed")
        XCTAssertEqual(next.homeScore, 3)
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ callback: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(callback)
        }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { handlers[event]?.forEach { $0(raw) } }
        func invalidate() { fire("market", #"{"market_id":7,"invalidation":true,"terminal":false}"#) }
    }
    private final class Clock: @unchecked Sendable {
        var time: TimeInterval = 0
        var waits: [TimeInterval] = []
    }
    private actor Reader {
        var body: GameMarketsResponse
        var count = 0
        var fail = false
        var hold = false
        var continuation: CheckedContinuation<Void, Never>?
        init(_ body: GameMarketsResponse) { self.body = body }
        func read(_ id: Int) async throws -> GameMarketsResponse {
            count += 1
            if fail { fail = false; throw APIError.httpError(statusCode: 429, body: "{\"retry_after\":17}") }
            let value = body
            if hold { hold = false; await withCheckedContinuation { continuation = $0 } }
            return value
        }
        func armHold() { hold = true }
        func armFailure() { fail = true }
        func resume() { continuation?.resume(); continuation = nil }
    }
    private func settle(_ condition: () async -> Bool) async {
        for _ in 0..<500 {
            if await condition() { return }
            await Task.yield()
        }
    }

    func testPublicationBurstHasOneTrailingReadTwoSecondFloorAnd429Recovery() async throws {
        let reader = Reader(try body())
        let handle = Handle()
        let clock = Clock()
        var publishes = 0
        let delivery = GameMarketsPriceDelivery(eventID: 12, fetch: { try await reader.read($0) },
            publish: { _ in publishes += 1 }, makeHandle: { _ in handle }, now: { clock.time },
            sleep: { seconds in clock.waits.append(seconds); clock.time += seconds })
        delivery.setVisible(true)
        await delivery.load()
        await reader.armHold()
        handle.invalidate()
        await settle { await reader.count == 2 }
        for _ in 0..<20 { handle.invalidate() }
        await reader.resume()
        await settle { await reader.count == 3 && publishes == 3 }
        let count = await reader.count
        XCTAssertEqual(count, 3)
        XCTAssertTrue(clock.waits.allSatisfy { $0 >= 2 })
        await reader.armFailure()
        handle.invalidate()
        await settle { await reader.count == 5 }
        XCTAssertTrue(clock.waits.contains(17), "healthy wire cannot lose the failed last read")
        delivery.setVisible(false)
    }

    func testHiddenPageRejectsInflightAndRetiredSubscriptionCallbacks() async throws {
        let reader = Reader(try body(status: "completed", score: 3))
        let handle = Handle()
        let clock = Clock()
        var publishes = 0
        let delivery = GameMarketsPriceDelivery(eventID: 12, fetch: { try await reader.read($0) },
            publish: { _ in publishes += 1 }, makeHandle: { _ in handle }, now: { clock.time },
            sleep: { seconds in clock.time += seconds })
        delivery.setVisible(true)
        await delivery.load()
        XCTAssertFalse(handle.isClosed, "game final does not close still-open contracts")
        await reader.armHold()
        handle.invalidate()
        await settle { await reader.count == 2 }
        delivery.setVisible(false)
        await reader.resume()
        handle.invalidate()
        for _ in 0..<20 { await Task.yield() }
        XCTAssertEqual(publishes, 1)
        XCTAssertTrue(handle.isClosed)
    }

    func testMoreThanFiftyMarketsUseBoundedBatchesAndLastIDInvalidates() async throws {
        let reader = Reader(try body(marketIDs: Array(1...51)))
        var opened: [String: Handle] = [:]
        let clock = Clock()
        let delivery = GameMarketsPriceDelivery(eventID: 12, fetch: { try await reader.read($0) },
            publish: { _ in }, makeHandle: { ids in
                XCTAssertLessThanOrEqual(ids.count, 50)
                let handle = Handle()
                opened[ids.map(String.init).joined(separator: ",")] = handle
                return handle
            }, now: { clock.time }, sleep: { clock.time += $0 })
        delivery.setVisible(true)
        await delivery.load()
        XCTAssertEqual(opened.count, 2)
        XCTAssertEqual(delivery.value?.streamMarketIds?.count, 51)
        opened["51"]?.fire("market", #"{"market_id":51,"invalidation":true,"terminal":false}"#)
        await settle { await reader.count == 2 }
        let count = await reader.count
        XCTAssertEqual(count, 2, "the 51st contract uses the same coalesced authoritative reader")
        delivery.setVisible(false)
        XCTAssertTrue(opened.values.allSatisfy(\.isClosed))
    }

    func testHiddenInitialReadCanBecomeVisibleWithoutStrandingSchedulerOrParentLoad() async throws {
        let reader = Reader(try body())
        let handle = Handle()
        let clock = Clock()
        var publishes = 0
        var initialCompleted = false
        let delivery = GameMarketsPriceDelivery(eventID: 12, fetch: { try await reader.read($0) },
            publish: { _ in publishes += 1 }, makeHandle: { _ in handle }, now: { clock.time },
            sleep: { clock.time += $0 })
        await reader.armHold()
        let initial = Task { await delivery.load(); initialCompleted = true }
        await settle { await reader.count == 1 }
        delivery.setVisible(true)
        delivery.requestRefresh()
        await reader.armHold()
        await reader.resume()
        await settle { await reader.count == 2 && initialCompleted }
        XCTAssertTrue(initialCompleted, "initial load returns while its trailing read is still held")
        XCTAssertEqual(publishes, 1)
        await reader.resume()
        await settle { publishes == 2 }
        handle.invalidate()
        await settle { await reader.count == 3 }
        let count = await reader.count
        XCTAssertEqual(count, 3, "hidden-to-visible did not leave a retired task as owner")
        delivery.setVisible(false)
        await initial.value
    }

    func testLoadReturnsAfterFailedAttemptWhileCooldownRetryRemainsOwed() async throws {
        let reader = Reader(try body())
        await reader.armFailure()
        let clock = Clock()
        let delivery = GameMarketsPriceDelivery(eventID: 12, fetch: { try await reader.read($0) },
            publish: { _ in }, makeHandle: { _ in Handle() }, now: { clock.time },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        delivery.setVisible(true)
        await delivery.load()
        let count = await reader.count
        XCTAssertEqual(count, 1, "parent load is not held by the pending 429 retry")
        delivery.setVisible(false)
    }
}
