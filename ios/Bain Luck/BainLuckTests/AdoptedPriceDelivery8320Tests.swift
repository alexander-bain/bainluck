import XCTest
@testable import Bain_Luck

/// #10468 (parent #8320) — a held live page's "Live updates" claim is renewed
/// only by a price the page actually ADOPTED, never by a frame it refused.
///
/// The defect: `LiveStreamController` rearmed its 90-second delivery budget for
/// every DECODED frame, before `EventDetailViewModel.apply` had decided anything.
/// `apply` refuses the wrong event, an old or equal revision, an unusable or
/// missing price, and every raw frame on a folded hero — so a stream of refused
/// frames kept the page green and the poll switched off forever behind a price
/// that was not moving. Now the page acknowledges an adopted newer price (or a
/// successful authoritative pair its CURRENT connection asked for), and only
/// that renews delivery.
///
/// Driven through the real `EventDetailViewModel` + `LiveStreamController`, a
/// fake socket and a clock the test owns; `tickStream()` is the page's own tick.
/// Every clock step ends in a tick, so a stray real-time tick from the page's
/// loop can only repeat a verdict, never change one.
@MainActor
final class AdoptedPriceDelivery8320Tests: XCTestCase {

    // MARK: - Fakes

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ raw: String = "") {
            for h in handlers[event] ?? [] { h(raw) }
        }
        /// A `probability` frame. `p`/`at`/`rev` are written verbatim, so a
        /// test can send `null`, an out-of-range value or omit the clock.
        @MainActor func push(eventId: Int = 4242, p: String, at: String?, rev: String?) {
            let clock = at.map { #","updated_at":"\#($0)""# } ?? ""
            fire("probability", """
            {"event_id":\(eventId),"p":\(p),"source":"polymarket","source_value":0.4\(clock),\
            "status":"live","rev":\(rev ?? "null")}
            """)
        }
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        var response: EventDetail
        var historyResponse: EventHistoryResponse?
        var beforeEventResponse: (() async -> Void)?
        var failEvent = false
        private(set) var historyFetches = 0
        private(set) var freshEventFetches = 0
        private(set) var freshHistoryFetches = 0
        init(_ response: EventDetail, history: EventHistoryResponse? = nil) {
            self.response = response
            self.historyResponse = history
        }
        func fetchEvent(id: Int) async throws -> EventDetail {
            let result = response
            if let beforeEventResponse { await beforeEventResponse() }
            if failEvent { throw Missing() }
            return result
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            historyFetches += 1
            guard let historyResponse else { throw Missing() }
            return historyResponse
        }
        func fetchFreshEvent(id: Int) async throws -> EventDetail {
            freshEventFetches += 1
            return try await fetchEvent(id: id)
        }
        func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            freshHistoryFetches += 1
            return try await fetchEventHistory(id: id, hours: hours)
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class Clock { var t: TimeInterval = 1_790_355_605 }

    // MARK: - Fixtures

    private static let folded20 = #"{"4242":20,"999":5}"#
    private static let folded21 = #"{"4242":21,"999":5}"#

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    /// A live page. `source == "blend"` with a revision holds a live blend
    /// (`pairedFoldRevision`); `source == nil` is the timestamp-ordered page.
    private func event(p: Double, source: String? = "blend", revision: String? = nil) throws -> EventDetail {
        let hero = source.map { #""hero_probability":\#(p),"hero_probability_source":"\#($0)","hero_probability_observed_at":"2026-10-04T17:00:00Z","# } ?? ""
        return try decode(EventDetail.self, """
        {"id":4242,"home_team":"Red Sox","away_team":"Cubs","sport":"baseball_mlb","status":"live",
         "home_score":2,"away_score":1,\(hero)
         "current_odds":{"home_probability":\(p),"away_probability":\(1 - p)},
         "blend_fold_revision":\(revision ?? "null"),
         "win_probability_sources":{"polymarket":{"value":0.4,"updated_at":"2026-10-04T17:00:00Z"}}}
        """)
    }

    private func history(p: Double, revision: String) throws -> EventHistoryResponse {
        try decode(EventHistoryResponse.self, """
        {"event_id":4242,"home_team":"Red Sox","away_team":"Cubs","history":[],
         "aggregate_line":[{"timestamp":"2026-10-04T17:00:00Z","home_probability":\(p)}],
         "blend_edge_fold_revision":\(revision),"blend_edge_observed_at":"2026-10-04T17:00:00Z"}
        """)
    }

    private func page(_ client: Client) async -> (EventDetailViewModel, Handle, Clock) {
        let handle = Handle(), clock = Clock()
        let vm = EventDetailViewModel(
            eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { clock.t },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        handle.fire("open")
        return (vm, handle, clock)
    }

    /// Twenty seconds of a healthy socket: a heartbeat, whatever frames the
    /// step sends, then the page's own tick on the new clock.
    private func step(_ vm: EventDetailViewModel, _ handle: Handle, _ clock: Clock,
                      by seconds: TimeInterval = 20, frames: () -> Void = {}) {
        clock.t += seconds
        handle.fire("heartbeat")
        frames()
        vm.tickStream()
    }

    private func settle(_ condition: () -> Bool) async {
        for _ in 0..<400 where !condition() {
            await Task.yield()
            try? await Task.sleep(nanoseconds: 1_000_000)
        }
    }

    private func stamp(_ second: Int) -> String {
        String(format: "2026-10-04T17:%02d:%02dZ", second / 60, second % 60)
    }

    // MARK: - THE DEFECT

    /// One accepted price, then refused frames of every kind plus heartbeats
    /// past the EXISTING 90 s budget: the page falls back to polling, keeps the
    /// socket, and its accepted receipt does not move.
    func testRefusedFramesAndHeartbeatsPastTheBudgetHandThePageBackToPolling() async throws {
        let client = Client(try event(p: 0.60, revision: #"{"4242":10}"#))
        let (vm, handle, clock) = await page(client)
        defer { vm.stopRefresh() }
        let opened = clock.t

        handle.push(p: "0.61", at: stamp(1), rev: #"{"4242":11}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.61)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePushPollInterval))
        let receipt = try XCTUnwrap(vm.priceActivity)
        XCTAssertEqual(receipt.receivedAt, Date(timeIntervalSince1970: opened))

        var second = 1
        let refused = {
            second += 1
            handle.push(p: "0.70", at: self.stamp(second), rev: #"{"4242":11}"#)  // equal revision, newer clock
            handle.push(p: "0.71", at: self.stamp(second), rev: #"{"4242":10}"#)  // older revision
            handle.push(eventId: 9_999, p: "0.72", at: self.stamp(second), rev: #"{"4242":12}"#)  // wrong event
            handle.push(p: "1.5", at: self.stamp(second), rev: #"{"4242":12}"#)   // not a probability
            handle.push(p: "null", at: self.stamp(second), rev: #"{"4242":12}"#)  // no price
        }
        for _ in 0..<4 { step(vm, handle, clock, frames: refused) }          // +80
        XCTAssertTrue(vm.streamDelivering, "control: inside the budget the accepted price still stands")
        XCTAssertEqual(vm.liveUpdateStatus, .live)

        step(vm, handle, clock, frames: refused)                              // +100
        XCTAssertFalse(vm.streamDelivering, "refused frames renewed the delivery budget")
        XCTAssertFalse(vm.streamHasPushedPrice)
        XCTAssertEqual(vm.liveUpdateStatus, .autoRefresh)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePollInterval),
                       "polling must resume")
        XCTAssertEqual(vm.priceActivity, receipt, "a refused frame earned a receipt")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.61, "a refused frame moved the hero")
        XCTAssertFalse(handle.isClosed, "a quiet publisher keeps the socket for the next price")
    }

    /// A clockless unversioned frame keeps its legacy display — it still moves
    /// the hero — but proves no newer observation: no receipt, no green, and
    /// it cannot hold or restore delivery.
    func testAClocklessFrameMovesTheHeroButIsNotADelivery() async throws {
        let client = Client(try event(p: 0.54, source: nil))
        let (vm, handle, clock) = await page(client)
        defer { vm.stopRefresh() }

        handle.push(p: "0.55", at: stamp(1), rev: nil)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        let receipt = try XCTUnwrap(vm.priceActivity)

        let clockless = { handle.push(p: "0.56", at: nil, rev: nil) }
        for _ in 0..<5 { step(vm, handle, clock, frames: clockless) }        // +100
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.56, "legacy clockless display is unchanged")
        XCTAssertFalse(vm.streamDelivering, "a clockless frame renewed the delivery budget")
        XCTAssertEqual(vm.liveUpdateStatus, .autoRefresh)
        XCTAssertEqual(vm.priceActivity, receipt)

        handle.push(p: "0.55", at: nil, rev: nil)
        XCTAssertFalse(vm.streamDelivering, "a clockless frame took push back over")
        XCTAssertFalse(vm.streamHasPushedPrice, "a clockless frame turned the dot green")
    }

    // MARK: - Genuine observations still count

    /// A NEWER revision at the same value is a real observation: it renews the
    /// budget, earns a receipt, and recovers delivery after a fallback. A
    /// replay of the revision already held does none of those.
    func testANewerSameValuePriceRenewsAndRecoversDelivery() async throws {
        let client = Client(try event(p: 0.60, revision: #"{"4242":10}"#))
        let (vm, handle, clock) = await page(client)
        defer { vm.stopRefresh() }
        let opened = clock.t

        handle.push(p: "0.61", at: stamp(1), rev: #"{"4242":11}"#)
        step(vm, handle, clock, by: 60) {
            handle.push(p: "0.61", at: self.stamp(61), rev: #"{"4242":12}"#)
        }
        XCTAssertEqual(vm.priceActivity?.sequence, 2, "a newer same-value price is a receipt")
        XCTAssertEqual(vm.priceActivity?.receivedAt, Date(timeIntervalSince1970: opened + 60))

        for _ in 0..<4 { step(vm, handle, clock) }                            // +140
        XCTAssertTrue(vm.streamDelivering, "the same-value price at +60 renewed the budget")

        step(vm, handle, clock, by: 11)                                       // +151
        XCTAssertFalse(vm.streamDelivering)
        XCTAssertEqual(vm.liveUpdateStatus, .autoRefresh)

        handle.push(p: "0.61", at: stamp(151), rev: #"{"4242":12}"#)          // replay
        XCTAssertFalse(vm.streamDelivering, "a replayed revision took push back over")
        XCTAssertEqual(vm.priceActivity?.sequence, 2)

        handle.push(p: "0.61", at: stamp(152), rev: #"{"4242":13}"#)          // newer, same value
        XCTAssertTrue(vm.streamDelivering, "a newer adopted price must take push back over")
        XCTAssertTrue(vm.streamHasPushedPrice)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.priceActivity?.sequence, 3)
        XCTAssertEqual(vm.priceActivity?.receivedAt, Date(timeIntervalSince1970: opened + 151))
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: EventRefreshPlan.livePushPollInterval))
    }

    // MARK: - The authoritative pair

    func testResyncReadsTheFreshPairAndOnlyItsNewerPriceRecoversDelivery10090() async throws {
        let client = Client(try event(p: 0.60, revision: Self.folded20),
                            history: try history(p: 0.60, revision: Self.folded20))
        let (vm, handle, clock) = await page(client)
        defer { vm.stopRefresh() }
        for _ in 0..<5 { step(vm, handle, clock) }
        XCTAssertFalse(vm.streamDelivering)
        let detailReads = client.freshEventFetches, historyReads = client.freshHistoryFetches
        client.response = try event(p: 0.62, revision: Self.folded21)
        client.historyResponse = try history(p: 0.62, revision: Self.folded21)

        handle.fire("resync", #"{"generation":1}"#)
        XCTAssertFalse(vm.streamDelivering, "resync itself is not price delivery")
        XCTAssertNil(vm.priceActivity)
        await settle { vm.streamHasPushedPrice }
        XCTAssertEqual(client.freshEventFetches, detailReads + 1)
        XCTAssertEqual(client.freshHistoryFetches, historyReads + 1)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.62)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.62)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.priceActivity?.receivedAt, Date(timeIntervalSince1970: clock.t))
        XCTAssertFalse(handle.isClosed, "recovery uses the existing connection")
    }

    func testUnchangedOrFailedResyncKeepsLastGoodAndDoesNotRenewDelivery10090() async throws {
        for failed in [false, true] {
            let client = Client(try event(p: 0.60, revision: Self.folded20),
                                history: try history(p: 0.60, revision: Self.folded20))
            let (vm, handle, clock) = await page(client)
            defer { vm.stopRefresh() }
            let historyReads = client.freshHistoryFetches
            client.failEvent = failed
            step(vm, handle, clock, by: 60) { handle.fire("resync", #"{"generation":1}"#) }
            await settle { client.freshHistoryFetches > historyReads }
            if failed { await settle { vm.pricePairRefreshFailed } }
            for _ in 0..<20 { await Task.yield() }
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.60)
            XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.60)
            XCTAssertNil(vm.priceActivity, "unchanged/failed resync earned a price receipt")
            XCTAssertFalse(vm.streamHasPushedPrice)
            XCTAssertEqual(vm.pricePairRefreshFailed, failed)
            step(vm, handle, clock, by: 31)
            XCTAssertFalse(vm.streamDelivering, "resync or its unchanged/failed pair renewed delivery")
        }
    }

    func testResyncBurstDuringAPairOwesOnlyOneFreshTrailingPair10090() async throws {
        let client = Client(try event(p: 0.60, revision: Self.folded20),
                            history: try history(p: 0.60, revision: Self.folded20))
        let (vm, handle, clock) = await page(client)
        defer { vm.stopRefresh() }
        let detailReads = client.freshEventFetches, historyReads = client.freshHistoryFetches
        var gate: CheckedContinuation<Void, Never>?
        client.response = try event(p: 0.62, revision: Self.folded21)
        client.historyResponse = try history(p: 0.62, revision: Self.folded21)
        client.beforeEventResponse = { await withCheckedContinuation { gate = $0 } }
        handle.fire("resync", #"{"generation":1}"#)
        await settle { gate != nil && client.freshHistoryFetches == historyReads + 1 }
        XCTAssertNotNil(gate)
        for generation in 2...20 { handle.fire("resync", "{\"generation\":\(generation)}") }
        XCTAssertEqual(client.freshEventFetches, detailReads + 1, "resync launched parallel reads")
        XCTAssertEqual(client.freshHistoryFetches, historyReads + 1)
        client.response = try event(p: 0.64, revision: #"{"4242":22,"999":5}"#)
        client.historyResponse = try history(p: 0.64, revision: #"{"4242":22,"999":5}"#)
        client.beforeEventResponse = nil
        clock.t += 1 // The existing coalescer's one-second window has elapsed.
        gate?.resume()
        await settle { vm.event?.currentOdds?.homeProbability == 0.64 }
        for _ in 0..<20 { await Task.yield() }
        XCTAssertEqual(client.freshEventFetches, detailReads + 2)
        XCTAssertEqual(client.freshHistoryFetches, historyReads + 2)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.64)
        XCTAssertTrue(vm.streamHasPushedPrice)
    }

    func testResyncQueuedBeforeRetirementCannotEarnASuccessorsReceipt10090() async throws {
        let client = Client(try event(p: 0.60, revision: Self.folded20),
                            history: try history(p: 0.60, revision: Self.folded20))
        let handle = Handle(), clock = Clock()
        var pause: CheckedContinuation<Void, Never>?
        let vm = EventDetailViewModel(
            eventId: 4242, client: client, makeStreamHandle: { _ in handle }, now: { clock.t },
            sleep: { seconds in
                if seconds <= 1 { await withCheckedContinuation { pause = $0 } }
                else { try? await Task.sleep(nanoseconds: 60_000_000_000) }
            })
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        client.response = try event(p: 0.62, revision: Self.folded21)
        client.historyResponse = try history(p: 0.62, revision: Self.folded21)
        handle.fire("resync", #"{"generation":1}"#)
        await settle { vm.streamHasPushedPrice }
        for _ in 0..<20 { await Task.yield() }
        let receipt = try XCTUnwrap(vm.priceActivity)
        handle.fire("resync", #"{"generation":2}"#)
        await settle { pause != nil }
        XCTAssertNotNil(pause, "the second read was not queued inside the existing throttle")
        handle.fire("resync", #"{"generation":3}"#) // One pending invalidation, now retired too.
        handle.fire("error")
        client.response = try event(p: 0.64, revision: #"{"4242":22,"999":5}"#)
        client.historyResponse = try history(p: 0.64, revision: #"{"4242":22,"999":5}"#)
        clock.t += 1
        let detailReads = client.freshEventFetches
        pause?.resume()
        await settle { vm.event?.currentOdds?.homeProbability == 0.64 }
        for _ in 0..<20 { await Task.yield() }
        XCTAssertEqual(client.freshEventFetches, detailReads + 1, "retired pending resync launched another read")
        XCTAssertFalse(vm.streamDelivering)
        XCTAssertFalse(vm.streamHasPushedPrice)
        XCTAssertEqual(vm.priceActivity, receipt, "a queued retired resync earned a receipt")
    }

    /// A folded hero refuses every raw frame; the pair the CURRENT connection
    /// asks for is how it adopts. A newer pair after a fallback recovers
    /// delivery and renews the budget from the moment it landed.
    func testANewerPairForTheCurrentConnectionRecoversAFoldedHero() async throws {
        let client = Client(try event(p: 0.60, revision: Self.folded20),
                            history: try history(p: 0.60, revision: Self.folded20))
        let (vm, handle, clock) = await page(client)
        defer { vm.stopRefresh() }
        let opened = clock.t

        for _ in 0..<5 { step(vm, handle, clock) }                            // +100
        XCTAssertFalse(vm.streamDelivering)

        client.response = try event(p: 0.62, revision: Self.folded21)
        client.historyResponse = try history(p: 0.62, revision: Self.folded21)
        handle.push(p: "0.9", at: stamp(100), rev: #"{"4242":21}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.60, "a raw frame never lands on a folded hero")
        XCTAssertFalse(vm.streamDelivering, "the refused frame itself took push back over")

        await settle { vm.streamDelivering }
        XCTAssertTrue(vm.streamDelivering, "a newer current-connection pair must recover delivery")
        XCTAssertTrue(vm.streamHasPushedPrice)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.62)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.priceActivity?.receivedAt, Date(timeIntervalSince1970: opened + 100))

        step(vm, handle, clock, by: 85)                                       // 85 s after the pair
        XCTAssertTrue(vm.streamDelivering, "the pair renewed the budget when it landed")
        step(vm, handle, clock, by: 6)                                        // 91 s after the pair
        XCTAssertFalse(vm.streamDelivering)
    }

    /// The opening-hero half: a raw frame asks for the pair, and a pair whose
    /// revision COVERS that frame is the delivery.
    func testACoveringPairForAnOpeningHeroRenewsDelivery() async throws {
        let client = Client(try event(p: 0.60, source: "opening", revision: #"{"4242":10}"#))
        let (vm, handle, clock) = await page(client)
        defer { vm.stopRefresh() }

        client.response = try event(p: 0.52, revision: #"{"4242":11,"999":5}"#)
        client.historyResponse = try history(p: 0.52, revision: #"{"4242":11,"999":5}"#)
        step(vm, handle, clock, by: 60) {
            handle.push(p: "0.9", at: self.stamp(60), rev: #"{"4242":11}"#)
        }
        await settle { vm.streamHasPushedPrice }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertEqual(vm.liveUpdateStatus, .live)

        step(vm, handle, clock, by: 85)                                       // +145: 85 s after the pair
        XCTAssertTrue(vm.streamDelivering, "a covering pair renewed the budget")
        step(vm, handle, clock, by: 6)                                        // +151
        XCTAssertFalse(vm.streamDelivering)
    }

    private enum PairOutcome: CaseIterable { case retired, failed, unchanged }

    /// A pair whose connection has already fallen back, a pair that failed,
    /// and a pair that brought nothing newer are not deliveries — whatever
    /// the frame that asked for them.
    func testARetiredFailedOrUnchangedPairIsNotADelivery() async throws {
        for outcome in PairOutcome.allCases {
            let client = Client(try event(p: 0.60, revision: Self.folded20),
                                history: try history(p: 0.60, revision: Self.folded20))
            let (vm, handle, clock) = await page(client)
            let historyAtLoad = client.historyFetches
            var gate: CheckedContinuation<Void, Never>?

            switch outcome {
            case .retired:
                client.response = try event(p: 0.62, revision: Self.folded21)
                client.historyResponse = try history(p: 0.62, revision: Self.folded21)
                client.beforeEventResponse = { await withCheckedContinuation { gate = $0 } }
            case .failed:
                client.failEvent = true
            case .unchanged:
                break
            }
            step(vm, handle, clock, by: 60) {
                handle.push(p: "0.9", at: self.stamp(60), rev: #"{"4242":21}"#)
            }

            switch outcome {
            case .retired:
                await settle { gate != nil }
                XCTAssertNotNil(gate, "\(outcome): the pair never started")
                handle.fire("error")                      // a blip retires this connection
                XCTAssertFalse(vm.streamDelivering)
                client.beforeEventResponse = nil
                gate?.resume()
                await settle { vm.event?.currentOdds?.homeProbability == 0.62 }
                for _ in 0..<20 { await Task.yield() }
                XCTAssertFalse(vm.streamDelivering, "a retired connection's pair claimed delivery")
                XCTAssertFalse(vm.streamHasPushedPrice, "\(outcome)")
                XCTAssertNil(vm.priceActivity, "a retired connection's pair earned a receipt")
                XCTAssertEqual(vm.liveUpdateStatus, .autoRefresh, "\(outcome)")
            case .failed:
                await settle { vm.pricePairRefreshFailed }
                XCTAssertTrue(vm.pricePairRefreshFailed, "\(outcome): the pair never failed")
                XCTAssertEqual(vm.liveUpdateStatus, .interrupted)
                step(vm, handle, clock, by: 31)           // +91 since open
                XCTAssertFalse(vm.streamDelivering, "a failed pair, or its frame, renewed the budget")
                XCTAssertNil(vm.priceActivity, "\(outcome)")
            case .unchanged:
                await settle { client.historyFetches > historyAtLoad }
                for _ in 0..<20 { await Task.yield() }
                XCTAssertGreaterThan(client.historyFetches, historyAtLoad, "\(outcome): the pair never ran")
                XCTAssertFalse(vm.streamHasPushedPrice, "an unchanged pair turned the dot green")
                step(vm, handle, clock, by: 31)           // +91 since open
                XCTAssertFalse(vm.streamDelivering, "an unchanged pair, or its frame, renewed the budget")
                XCTAssertEqual(vm.liveUpdateStatus, .autoRefresh, "\(outcome)")
                XCTAssertNil(vm.priceActivity, "\(outcome)")
            }
            vm.stopRefresh()
        }
    }
}
