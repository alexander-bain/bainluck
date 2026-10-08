import XCTest
@testable import Bain_Luck

@MainActor
final class FuturesStreamingTests: XCTestCase {
    private func detail(_ x: Double? = 0.31, _ y: Double? = 0.22,
                        xClock: String? = "2030-01-01T00:00:00Z",
                        yClock: String? = "2030-01-01T00:00:00Z",
                        status: String = "open", source: String = "kalshi",
                        winner: Bool? = nil, mutuallyExclusive: Bool = false) throws -> FuturesMarketDetail {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        func string(_ value: String?) -> String { value.map { "\"\($0)\"" } ?? "null" }
        return try d.decode(FuturesMarketDetail.self, from: Data("""
        {"id":7,"name":"Held prop","status":"\(status)","source":"\(source)","mutually_exclusive":\(mutuallyExclusive),
         "outcomes":[{"id":1,"name":"X","probability":\(x.map(String.init(describing:)) ?? "null"),"last_updated":\(string(xClock)),"is_winner":\(winner.map(String.init) ?? "null")},
                     {"id":2,"name":"Y","probability":\(y.map(String.init(describing:)) ?? "null"),"last_updated":\(string(yClock))}]}
        """.utf8))
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ callback: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(callback)
        }
        func close() { isClosed = true }
        func fire(_ event: String, _ data: String = "") { handlers[event]?.forEach { $0(data) } }
        func invalidate() { fire("market", #"{"market_id":7,"invalidation":true,"terminal":false}"#) }
    }

    @MainActor
    private final class Client: FuturesDetailProviding {
        var response: FuturesMarketDetail
        var beforeResponse: (() async -> Void)?
        var count = 0
        var failNext = false
        init(_ response: FuturesMarketDetail) { self.response = response }
        func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail {
            count += 1
            if failNext { failNext = false; throw URLError(.networkConnectionLost) }
            let result = response
            if let beforeResponse { await beforeResponse() }
            return result
        }
    }

    private func settle(_ condition: () -> Bool) async {
        for _ in 0..<300 where !condition() { await Task.yield() }
    }

    func testNormalizedFieldAdoptsOneDivisorAndRejectsAnyStaleSibling() throws {
        let initial = try detail(0.3, 0.7, mutuallyExclusive: true)
        var fences: [Int: FuturesPriceReconciliation.Withdrawal] = [:]
        let next = try detail(0.4, 0.6, xClock: "2030-01-01T00:00:02Z", mutuallyExclusive: true)
        let accepted = FuturesPriceReconciliation.adopting(next, over: initial, withdrawals: &fences)
        XCTAssertEqual(accepted.outcomes.map(\.probability), [0.4, 0.6])
        let mixed = try detail(0.5, 0.5, xClock: "2030-01-01T00:00:03Z",
            yClock: "2029-12-31T23:59:59Z", mutuallyExclusive: true)
        XCTAssertEqual(FuturesPriceReconciliation.adopting(mixed, over: accepted,
            withdrawals: &fences).outcomes.map(\.probability), [0.4, 0.6])
        let withdrawn = try detail(nil, 1, xClock: "2030-01-01T00:00:02Z", mutuallyExclusive: true)
        XCTAssertEqual(FuturesPriceReconciliation.adopting(withdrawn, over: accepted,
            withdrawals: &fences).outcomes.map(\.probability), [nil, 1])
    }

    func testMicrosecondObservationChangesRemainOrdered() throws {
        let old = try detail(xClock: "2030-01-01T00:00:00.000001Z")
        let new = try detail(0.4, xClock: "2030-01-01T00:00:00.000002Z")
        let accepted = FuturesPriceReconciliation.adopting(new, over: old)
        XCTAssertEqual(accepted.outcomes[0].probability, 0.4)
        XCTAssertEqual(FuturesPriceReconciliation.adopting(old, over: accepted).outcomes[0].probability, 0.4)
    }

    func testEachOutcomeMustAdvanceOnItsOwnClock() throws {
        let held = try detail()
        let incoming = try detail(0.34, 0.20, xClock: "2030-01-01T00:00:02Z", yClock: "2029-12-31T23:59:59Z")
        let result = FuturesPriceReconciliation.adopting(incoming, over: held)
        XCTAssertEqual(result.outcomes[0].probability, 0.34)
        XCTAssertEqual(result.outcomes[1].probability, 0.22, "new X cannot launder old Y")
        let unknown = try detail(0.9, 0.1, xClock: nil, yClock: nil)
        let preserved = FuturesPriceReconciliation.adopting(unknown, over: result)
        XCTAssertEqual(preserved.outcomes.map(\.probability), result.outcomes.map(\.probability))
        let equalClockChange = try detail(0.9, 0.1)
        XCTAssertEqual(FuturesPriceReconciliation.adopting(equalClockChange, over: held).outcomes[0].probability, 0.31)
    }


    func testWithdrawalClearsEqualOrUnknownClockAndCannotBeResurrectedByCachedPrice() throws {
        for clock in ["2030-01-01T00:00:00Z", nil] {
            let held = try detail()
            var fences: [Int: FuturesPriceReconciliation.Withdrawal] = [:]
            let withdrawn = FuturesPriceReconciliation.adopting(try detail(nil, xClock: clock),
                over: held, withdrawals: &fences)
            XCTAssertNil(withdrawn.outcomes[0].probability)
            XCTAssertEqual(withdrawn.outcomes[0].lastUpdated, clock, "do not manufacture a wire clock")
            let cached = FuturesPriceReconciliation.adopting(held, over: withdrawn, withdrawals: &fences)
            XCTAssertNil(cached.outcomes[0].probability)
            let unknown = FuturesPriceReconciliation.adopting(try detail(0.7, xClock: nil),
                over: cached, withdrawals: &fences)
            XCTAssertNil(unknown.outcomes[0].probability)
            let fresh = FuturesPriceReconciliation.adopting(
                try detail(0.4, xClock: "2030-01-01T00:00:01Z"), over: unknown, withdrawals: &fences)
            XCTAssertEqual(fresh.outcomes[0].probability, 0.4)
            XCTAssertNil(fences[1])
        }
    }

    func testInitiallyWithheldUnknownQuoteRequiresDatedRestoration() throws {
        var fences: [Int: FuturesPriceReconciliation.Withdrawal] = [:]
        let initial = FuturesPriceReconciliation.adopting(try detail(nil, xClock: nil),
            over: nil, withdrawals: &fences)
        let cached = FuturesPriceReconciliation.adopting(try detail(0.7, xClock: nil),
            over: initial, withdrawals: &fences)
        XCTAssertNil(cached.outcomes[0].probability)
        let fresh = FuturesPriceReconciliation.adopting(try detail(0.4),
            over: cached, withdrawals: &fences)
        XCTAssertEqual(fresh.outcomes[0].probability, 0.4)
    }

    func testStrictlyOlderWithdrawalCannotHideNewerQuote() throws {
        var fences: [Int: FuturesPriceReconciliation.Withdrawal] = [:]
        let result = FuturesPriceReconciliation.adopting(
            try detail(nil, xClock: "2029-12-31T23:59:59Z"), over: try detail(), withdrawals: &fences)
        XCTAssertEqual(result.outcomes[0].probability, 0.31)
        XCTAssertNil(fences[1])
    }

    func testStaleLegCannotWearDifferentProviderOrUndoSettlement() throws {
        let held = try detail()
        let switched = try detail(0.34, 0.20, xClock: "2030-01-01T00:00:02Z", yClock: nil, source: "polymarket")
        let result = FuturesPriceReconciliation.adopting(switched, over: held)
        XCTAssertEqual(result.source, "kalshi")
        XCTAssertEqual(result.outcomes[0].probability, 0.31)
        let settled = try detail(1, 0, status: "resolved", winner: true)
        let resolved = FuturesPriceReconciliation.adopting(settled, over: held)
        XCTAssertTrue(FuturesPriceReconciliation.isSettled(resolved))
        XCTAssertEqual(FuturesPriceReconciliation.adopting(held, over: resolved).outcomes[0].isWinner, true)
    }

    func testGenuineInvalidationUpdatesHeldDetailAndHeartbeatCreatesNoActivity() async throws {
        let client = Client(try detail()), handle = Handle()
        let vm = FuturesDetailViewModel(marketId: 7, client: client, makeStreamHandle: { _ in handle }, minimumRefreshInterval: 0)
        defer { vm.setVisible(false) }
        await vm.load()
        vm.setVisible(true)
        handle.fire("heartbeat")
        XCTAssertEqual(client.count, 1)
        XCTAssertEqual(vm.chartRefreshToken, 0)
        client.response = try detail(0.34, 0.20, xClock: "2030-01-01T00:00:02Z", yClock: "2030-01-01T00:00:02Z")
        handle.invalidate()
        await settle { vm.chartRefreshToken == 1 }
        XCTAssertEqual(vm.market?.outcomes[0].probability, 0.34)
        XCTAssertFalse(vm.loading)
        let generation = vm.chartRefreshToken
        handle.invalidate()
        await settle { client.count == 3 }
        XCTAssertEqual(vm.chartRefreshToken, generation, "same observed body is not fresh price activity")
        vm.setVisible(false)
        client.response = try detail(0.9, 0.1, xClock: "2030-01-01T00:00:04Z")
        handle.invalidate()
        await Task.yield()
        XCTAssertEqual(vm.market?.outcomes[0].probability, 0.34)
        XCTAssertTrue(handle.isClosed)
    }

    private actor Pause {
        var waiting: CheckedContinuation<Void, Never>?
        var credits = 0
        func sleep(_ seconds: TimeInterval) async {
            if credits > 0 { credits -= 1; return }
            await withCheckedContinuation { waiting = $0 }
        }
        func release() {
            if let waiting { self.waiting = nil; waiting.resume() } else { credits += 1 }
        }
    }

    func testFailedLastInvalidationRetriesDespiteHealthyHeartbeats() async throws {
        let client = Client(try detail()), handle = Handle(), pause = Pause()
        let vm = FuturesDetailViewModel(marketId: 7, client: client, makeStreamHandle: { _ in handle }, minimumRefreshInterval: 0,
            sleep: { await pause.sleep($0) })
        await vm.load()
        vm.setVisible(true)
        handle.fire("open")
        await settle { client.count == 2 }
        client.failNext = true
        handle.invalidate()
        await settle { vm.error != nil }
        XCTAssertTrue(vm.streamConnected)
        handle.fire("heartbeat")
        client.response = try detail(0.34, 0.20, xClock: "2030-01-01T00:00:02Z", yClock: "2030-01-01T00:00:02Z")
        await pause.release()
        await settle { vm.market?.outcomes.first?.probability == 0.34 }
        XCTAssertEqual(vm.market?.outcomes.first?.probability, 0.34)
        XCTAssertNil(vm.error)
        vm.setVisible(false)
        await pause.release()
    }

    func testInvalidationDuringRequestGetsOneTrailingFetch() async throws {
        let client = Client(try detail()), handle = Handle()
        let vm = FuturesDetailViewModel(marketId: 7, client: client, makeStreamHandle: { _ in handle }, minimumRefreshInterval: 0)
        defer { vm.setVisible(false) }
        await vm.load()
        vm.setVisible(true)
        var waiting: CheckedContinuation<Void, Never>?
        client.beforeResponse = { await withCheckedContinuation { waiting = $0 } }
        client.response = try detail(0.34, 0.20, xClock: "2030-01-01T00:00:02Z", yClock: "2030-01-01T00:00:02Z")
        handle.invalidate()
        await settle { waiting != nil }
        client.response = try detail(0.38, 0.18, xClock: "2030-01-01T00:00:03Z", yClock: "2030-01-01T00:00:03Z")
        for _ in 0..<10 { handle.invalidate() }
        client.beforeResponse = nil
        waiting?.resume()
        await settle { vm.market?.outcomes.first?.probability == 0.38 }
        XCTAssertEqual(vm.market?.outcomes.first?.probability, 0.38)
        XCTAssertEqual(client.count, 3, "one initial, one held, one trailing read")
    }

    func testOlderOverlappingLoadAndHiddenResponseCannotLand() async throws {
        let client = Client(try detail()), handle = Handle()
        let vm = FuturesDetailViewModel(marketId: 7, client: client, makeStreamHandle: { _ in handle }, minimumRefreshInterval: 0)
        var waiting: CheckedContinuation<Void, Never>?
        client.beforeResponse = { await withCheckedContinuation { waiting = $0 } }
        let old = Task { await vm.load() }
        await settle { waiting != nil }
        client.beforeResponse = nil
        client.response = try detail(0.34, 0.20, xClock: "2030-01-01T00:00:02Z", yClock: "2030-01-01T00:00:02Z")
        await vm.load()
        waiting?.resume()
        await old.value
        XCTAssertEqual(vm.market?.outcomes.first?.probability, 0.34)
        vm.setVisible(true)
        waiting = nil
        client.beforeResponse = { await withCheckedContinuation { waiting = $0 } }
        handle.invalidate()
        await settle { waiting != nil }
        vm.setVisible(false)
        waiting?.resume()
        await Task.yield()
        XCTAssertEqual(vm.market?.outcomes.first?.probability, 0.34)
    }


    func testAutomaticRefreshWaitsTwoSecondsAndCoalescesBurst() async throws {
        let client = Client(try detail()), handle = Handle(), pause = Pause()
        var clock: TimeInterval = 100
        let vm = FuturesDetailViewModel(marketId: 7, client: client,
            makeStreamHandle: { _ in handle }, now: { clock },
            refreshSleep: { await pause.sleep($0) })
        await vm.load()
        vm.setVisible(true)
        handle.invalidate()
        await settle { client.count == 2 }
        clock = 101
        for _ in 0..<20 { handle.invalidate() }
        for _ in 0..<30 { await Task.yield() }
        XCTAssertEqual(client.count, 2, "burst cannot dispatch at round-trip speed")
        clock = 102
        await pause.release()
        await settle { client.count == 3 }
        XCTAssertEqual(client.count, 3, "one delayed request covers the whole waiting burst")
        vm.setVisible(false)
        await pause.release()
    }

    func testTimelineRetryOnlyForTransientFailures() {
        XCTAssertEqual(FuturesPriceReadCooldown.timelineRetrySeconds(for:
            .networkError(underlying: URLError(.networkConnectionLost))), 60)
        XCTAssertEqual(FuturesPriceReadCooldown.timelineRetrySeconds(for:
            .httpError(statusCode: 503, body: nil)), 60)
        XCTAssertEqual(FuturesPriceReadCooldown.timelineRetrySeconds(for:
            .httpError(statusCode: 429, body: #"{"retry_after":123}"#)), 123)
        XCTAssertNil(FuturesPriceReadCooldown.timelineRetrySeconds(for:
            .networkError(underlying: URLError(.cancelled))))
        XCTAssertNil(FuturesPriceReadCooldown.timelineRetrySeconds(for:
            .httpError(statusCode: 404, body: nil)))
        XCTAssertNil(FuturesPriceReadCooldown.timelineRetrySeconds(for:
            .decodingError(underlying: URLError(.cannotDecodeContentData))))
    }

    func testRateLimitCooldownUsesServerSecondsAndMalformedFallback() {
        XCTAssertEqual(FuturesPriceReadCooldown.seconds(for:
            APIError.httpError(statusCode: 429, body: #"{"retry_after":123}"#)), 123)
        XCTAssertEqual(FuturesPriceReadCooldown.seconds(for:
            APIError.httpError(statusCode: 429, body: #"{"retry_after":"75"}"#)), 75)
        XCTAssertEqual(FuturesPriceReadCooldown.seconds(for:
            APIError.httpError(statusCode: 429, body: #"{"retry_after":-1}"#)), 60)
        XCTAssertNil(FuturesPriceReadCooldown.seconds(for:
            APIError.httpError(statusCode: 503, body: nil)))
    }

    func testRefusalRetriesBoundedlyAndUnrelatedMarketNeverRefreshes() {
        var clock: TimeInterval = 100
        var invalidations = 0, connections = 0
        let first = Handle(), second = Handle()
        let subscription = MarketStreamSubscription(makeHandle: { _ in
            connections += 1
            return connections == 1 ? first : second
        }, onInvalidate: { _ in invalidations += 1 }, now: { clock })
        subscription.start(ids: [7])
        first.fire("market", #"{"market_id":99,"invalidation":true,"terminal":false}"#)
        XCTAssertEqual(invalidations, 0)
        first.isClosed = true
        first.fire("error")
        clock = 159
        subscription.tick()
        XCTAssertEqual(connections, 1)
        XCTAssertEqual(invalidations, 0)
        clock = 160
        subscription.tick()
        XCTAssertEqual(connections, 2)
        second.fire("open")
        XCTAssertEqual(invalidations, 1)
        subscription.stop()
    }

    func testSharedSubscriptionRecoversQuietWireAndFencesRetiredCallbacks() {
        var clock: TimeInterval = 100
        var calls: [[Int]] = [], connections = 0
        let one = Handle(), two = Handle()
        let subscription = MarketStreamSubscription(makeHandle: { _ in
            connections += 1
            return connections == 1 ? one : two
        }, onInvalidate: { calls.append($0) }, now: { clock })
        subscription.start(ids: [7, 8])
        one.fire("open")
        XCTAssertEqual(calls, [[7, 8]])
        one.fire("heartbeat")
        XCTAssertEqual(calls.count, 1)
        clock = 166
        subscription.tick()
        XCTAssertTrue(one.isClosed)
        clock = 171
        subscription.tick()
        XCTAssertEqual(connections, 2)
        one.invalidate()
        XCTAssertEqual(calls.count, 1)
        two.fire("open")
        XCTAssertEqual(calls.count, 2)
        subscription.stop()
        two.invalidate()
        XCTAssertEqual(calls.count, 2)
    }

    // #10740: the shared hub can restore its Redis subscription without
    // replacing this socket; frames published in the gap are lost.
    func testResyncReconcilesOneMarketWithoutAnotherQuote() {
        var clock: TimeInterval = 100
        var calls: [[Int]] = [], connections = 0
        let handle = Handle()
        let subscription = MarketStreamSubscription(makeHandle: { _ in
            connections += 1
            return handle
        }, onInvalidate: { calls.append($0) }, now: { clock })
        subscription.start(ids: [7])
        clock = 160
        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(calls, [[7]])
        clock = 166
        subscription.tick()
        XCTAssertFalse(handle.isClosed, "a recovery frame is wire activity")
        XCTAssertEqual(connections, 1)
        subscription.stop()
    }

    func testResyncDeduplicatesGenerationsAndReadsOnlyRemainingMarkets() {
        var calls: [[Int]] = []
        let handle = Handle()
        let subscription = MarketStreamSubscription(makeHandle: { _ in handle },
            onInvalidate: { calls.append($0) }, now: { 100 })
        subscription.start(ids: [7, 8])
        handle.fire("market", #"{"market_id":7,"invalidation":true,"terminal":true}"#)
        calls = []
        handle.fire("resync", #"{"generation":2}"#)
        handle.fire("resync", #"{"generation":2}"#)
        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(calls, [[8]])
        handle.fire("resync", #"{"generation":3}"#)
        XCTAssertEqual(calls, [[8], [8]])
        handle.fire("market", #"{"market_id":8,"invalidation":true,"terminal":true}"#)
        calls = []
        handle.fire("resync", #"{"generation":4}"#)
        XCTAssertEqual(calls, [], "recovery never re-reads a final market")
        XCTAssertFalse(handle.isClosed)
        subscription.stop()
    }

    func testResyncRefusesInvalidGenerationWithoutAdvancingComparison() {
        let refused = ["", "not json", "1", "[1]", "{}", #"{"generation":null}"#,
            #"{"generation":true}"#, #"{"generation":false}"#, #"{"generation":"1"}"#,
            #"{"generation":0}"#, #"{"generation":-1}"#, #"{"generation":1.5}"#,
            #"{"generation":9007199254740992}"#, #"{"generation":1e300}"#,
            #"{"generation":[]}"#, #"{"generation":{}}"#]
        for raw in refused {
            var calls: [[Int]] = []
            let handle = Handle()
            let subscription = MarketStreamSubscription(makeHandle: { _ in handle },
                onInvalidate: { calls.append($0) }, now: { 100 })
            subscription.start(ids: [7])
            handle.fire("resync", raw)
            XCTAssertEqual(calls, [], raw)
            handle.fire("resync", #"{"generation":1}"#)
            XCTAssertEqual(calls, [[7]], raw)
            subscription.stop()
        }
    }

    func testResyncFencesOldAndStoppedHandlesAndNewHandleResetsComparison() {
        var clock: TimeInterval = 100
        var calls: [[Int]] = [], connections = 0
        let one = Handle(), two = Handle()
        let subscription = MarketStreamSubscription(makeHandle: { _ in
            connections += 1
            return connections == 1 ? one : two
        }, onInvalidate: { calls.append($0) }, now: { clock })
        subscription.start(ids: [7])
        one.fire("resync", #"{"generation":8}"#)
        one.fire("reconnect")
        clock = 105
        subscription.tick()
        XCTAssertEqual(connections, 2)
        calls = []
        one.fire("resync", #"{"generation":9}"#)
        XCTAssertEqual(calls, [])
        two.fire("resync", #"{"generation":1}"#)
        XCTAssertEqual(calls, [[7]], "a new hub connection may begin at 1")
        subscription.stop()
        two.fire("resync", #"{"generation":2}"#)
        XCTAssertEqual(calls, [[7]])
    }
}
