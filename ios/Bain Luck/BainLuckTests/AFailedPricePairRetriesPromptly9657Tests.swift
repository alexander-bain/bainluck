import XCTest
@testable import Bain_Luck

/// #9657 — a held event page recovers from a failed price pair in seconds,
/// not on the next poll slot.
///
/// Build 32, event 15320885: "Update interrupted" for 91 s with the stream up,
/// then a REST price ("Waiting for update"), then a pushed one. The only re-ask
/// of a failed detail + history pair was the refresh loop's next slot — 30 s
/// live, 60–300 s before play — so two more failures cost a minute and a half.
/// Now one retry task owns the re-ask on `EventRefreshPlan.pricePairRetryDelay`
/// (2, 4, 8, 16, then the live poll interval), and a read overtaken by a newer
/// accepted push no longer darkens the page.
@MainActor
final class AFailedPricePairRetriesPromptly9657Tests: XCTestCase {
    private func event(p: Double, revision: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Martin Tiffon","away_team":"Lokoli","status":"live",
         "current_odds":{"home_probability":\(p),"away_probability":\(1 - p)},
         "hero_probability":\(p),"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-09-29T16:33:00Z","blend_fold_revision":\(revision),
         "win_probability_sources":{"kalshi":{"value":\(p),"updated_at":"2026-09-29T16:33:00Z"}}}
        """.utf8))
    }

    private func history(p: Double, revision: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Martin Tiffon","away_team":"Lokoli","status":"live","history":[],
         "aggregate_line":[{"timestamp":"2026-09-29T16:33:00Z","home_probability":\(p)}],
         "blend_edge_pinned":true,"blend_edge_fold_revision":\(revision)}
        """.utf8))
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func push(p: Double, at: String, rev: String?) {
            fire("probability", """
            {"event_id":4242,"p":\(p),"source":"kalshi","source_value":\(p),"updated_at":"\(at)","status":"live","rev":\(rev ?? "null")}
            """)
        }
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Down: Error {}
        var response: EventDetail
        var historyResponse: EventHistoryResponse
        var failHistory = false
        var failEvent = false
        var beforeEventResponse: (() async -> Void)?
        private(set) var eventFetches = 0
        private(set) var historyFetches = 0
        init(_ response: EventDetail, _ history: EventHistoryResponse) {
            self.response = response; historyResponse = history
        }
        func fetchEvent(id: Int) async throws -> EventDetail {
            eventFetches += 1
            let result = response
            if let beforeEventResponse { await beforeEventResponse() }
            if failEvent { throw Down() }
            return result
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            historyFetches += 1
            if failHistory { throw Down() }
            return historyResponse
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Down() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Down() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Down() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Down() }
    }

    /// Every wait the page asks for, split by owner: the retry's backoff
    /// delays and the refresh loop's 30 s slot are parked until the test
    /// releases them; anything else (the 1 s re-read window) never returns.
    private actor Sleeper {
        private(set) var retryWaits: [TimeInterval] = []
        private var retries: [CheckedContinuation<Void, Never>] = []
        private var loops: [CheckedContinuation<Void, Never>] = []
        func sleep(_ seconds: TimeInterval) async {
            if EventRefreshPlan.pricePairRetryDelays.contains(seconds) {
                retryWaits.append(seconds)
                await withCheckedContinuation { retries.append($0) }
            } else if seconds == EventRefreshPlan.livePollInterval {
                await withCheckedContinuation { loops.append($0) }
            } else {
                try? await Task.sleep(for: .seconds(60))
            }
        }
        func releaseRetry() { let parked = retries; retries = []; parked.forEach { $0.resume() } }
        func releaseLoop() { let parked = loops; loops = []; parked.forEach { $0.resume() } }
        func releaseAll() { releaseRetry(); releaseLoop() }
    }

    private var clock: TimeInterval = 1_790_355_605

    private func page(_ client: Client, _ handle: Handle, _ sleeper: Sleeper) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
                             now: { [weak self] in self?.clock ?? 0 }, sleep: { await sleeper.sleep($0) })
    }

    private func settle(_ condition: () async -> Bool) async {
        for _ in 0..<400 {
            if await condition() { return }
            try? await Task.sleep(for: .milliseconds(5))
        }
    }

    /// A folded hero (two rows) cannot order a raw-row frame, so every frame
    /// asks for the authoritative pair — the path the build-32 page was on.
    private let folded20 = #"{"4242":20,"999":5}"#
    private let folded21 = #"{"4242":21,"999":5}"#

    private func failingPage() async throws -> (Client, Handle, Sleeper, EventDetailViewModel) {
        let client = Client(try event(p: 0.64, revision: folded20), try history(p: 0.64, revision: folded20))
        let handle = Handle(), sleeper = Sleeper()
        let vm = page(client, handle, sleeper)
        await vm.load(); handle.fire("open")
        client.failHistory = true
        clock += 10
        handle.push(p: 0.9, at: "2026-09-29T16:33:12Z", rev: #"{"4242":21}"#)
        await settle { vm.pricePairRefreshFailed }
        XCTAssertEqual(vm.liveUpdateStatus, .interrupted)
        return (client, handle, sleeper, vm)
    }

    func testTheRetryScheduleStartsInSecondsAndSettlesAtTheLivePollInterval() {
        XCTAssertEqual((1...6).map { EventRefreshPlan.pricePairRetryDelay(afterFailures: $0) }, [2, 4, 8, 16, 30, 30])
        XCTAssertEqual(EventRefreshPlan.pricePairRetryDelays.max(), 16)
        XCTAssertLessThan(EventRefreshPlan.pricePairRetryDelays.max() ?? .infinity, EventRefreshPlan.livePollInterval,
                          "the backoff settles at, never above, a streamless live page's own cadence")
    }

    func testAFailedPairIsAskedAgainAfterTwoSecondsAndRecoversWithoutAFrame() async throws {
        let (client, _, sleeper, vm) = try await failingPage()
        defer { vm.stopRefresh(); Task { await sleeper.releaseAll() } }
        await settle { await sleeper.retryWaits == [2] }
        let waits = await sleeper.retryWaits
        XCTAssertEqual(waits, [2], "the first re-ask is 2 s away, not the next 30 s poll slot")
        let pairsBefore = client.historyFetches

        client.failHistory = false
        client.response = try event(p: 0.60, revision: folded21)
        client.historyResponse = try history(p: 0.60, revision: folded21)
        clock += 2
        await sleeper.releaseRetry()
        await settle { !vm.pricePairRefreshFailed }

        XCTAssertFalse(vm.pricePairRefreshFailed)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.60)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.60, "value and chart recover together")
        XCTAssertEqual(client.historyFetches, pairsBefore + 1, "one retry is one pair")
        XCTAssertNotEqual(vm.liveUpdateStatus, .interrupted)
        let waitsAfter = await sleeper.retryWaits
        XCTAssertEqual(waitsAfter, [2], "a recovered page schedules no further retry")
    }

    func testConsecutiveFailuresBackOffAndARecoveryResetsTheSchedule() async throws {
        let (client, handle, sleeper, vm) = try await failingPage()
        defer { vm.stopRefresh(); Task { await sleeper.releaseAll() } }
        for expected in [[2.0], [2, 4], [2, 4, 8]] {
            await settle { await sleeper.retryWaits == expected }
            let waits = await sleeper.retryWaits
            XCTAssertEqual(waits, expected)
            XCTAssertEqual(vm.liveUpdateStatus, .interrupted, "a still-failing pair stays honest")
            if expected.count < 3 { clock += 10; await sleeper.releaseRetry() }
        }
        client.failHistory = false
        client.response = try event(p: 0.60, revision: folded21)
        client.historyResponse = try history(p: 0.60, revision: folded21)
        clock += 10
        await sleeper.releaseRetry()
        await settle { !vm.pricePairRefreshFailed }
        XCTAssertFalse(vm.pricePairRefreshFailed)

        client.failHistory = true
        clock += 10
        handle.push(p: 0.9, at: "2026-09-29T16:34:40Z", rev: #"{"4242":22}"#)
        await settle { await sleeper.retryWaits.count == 4 }
        let waits = await sleeper.retryWaits
        XCTAssertEqual(waits, [2, 4, 8, 2], "a fresh failure starts the backoff over")
    }

    func testTheRefreshLoopKeepsTheClockMovingAndLeavesThePairToTheRetry() async throws {
        let (client, _, sleeper, vm) = try await failingPage()
        defer { vm.stopRefresh(); Task { await sleeper.releaseAll() } }
        await settle { await sleeper.retryWaits == [2] }
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 30))
        let details = client.eventFetches, pairs = client.historyFetches
        clock += 30
        await sleeper.releaseLoop()
        await settle { client.eventFetches > details }
        try? await Task.sleep(for: .milliseconds(40))
        XCTAssertEqual(client.eventFetches, details + 1, "the slot re-reads game state")
        XCTAssertEqual(client.historyFetches, pairs, "the slot does not ask for a second pair beside the retry")
        XCTAssertEqual(vm.liveUpdateStatus, .interrupted, "a clock-only read cannot clear a failed pair")
    }

    func testAReadOvertakenByANewerAcceptedPushDoesNotClaimInterrupted() async throws {
        for overtaken in [true, false] {
            let oneRow20 = #"{"4242":20}"#
            let client = Client(try event(p: 0.64, revision: oneRow20), try history(p: 0.64, revision: oneRow20))
            let handle = Handle(), sleeper = Sleeper()
            let vm = page(client, handle, sleeper)
            await vm.load(); handle.fire("open")

            // An unversioned frame cannot be ordered against a one-row hero, so
            // it asks for the pair; that read stalls, then fails.
            var gate: CheckedContinuation<Void, Never>?
            client.beforeEventResponse = { await withCheckedContinuation { gate = $0 } }
            client.failEvent = true
            clock += 10
            handle.push(p: 0.9, at: "2026-09-29T16:33:12Z", rev: nil)
            await settle { gate != nil }
            XCTAssertNotNil(gate)

            if overtaken {
                // The same row's strictly newer write lands while the read waits.
                handle.push(p: 0.60, at: "2026-09-29T16:33:20Z", rev: #"{"4242":21}"#)
                XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.60)
                XCTAssertEqual(vm.liveUpdateStatus, .live)
            }
            client.beforeEventResponse = nil
            gate?.resume()
            // The chart's catch-up re-read that follows waits out the 1 s
            // window, which this sleeper never returns — only the stalled
            // read's verdict is under test here.
            await settle { overtaken || vm.pricePairRefreshFailed }
            try? await Task.sleep(for: .milliseconds(40))

            if overtaken {
                XCTAssertFalse(vm.pricePairRefreshFailed, "a failed read older than an accepted push cannot darken the page")
                XCTAssertEqual(vm.liveUpdateStatus, .live)
                XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.60)
                let waits = await sleeper.retryWaits
                XCTAssertEqual(waits, [], "nothing to retry")
            } else {
                XCTAssertTrue(vm.pricePairRefreshFailed, "control: the same failure with no newer push is still honest")
                XCTAssertEqual(vm.liveUpdateStatus, .interrupted)
                XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.64)
            }
            vm.stopRefresh()
            await sleeper.releaseAll()
        }
    }

    func testLeavingThePageCancelsTheRetryAndReturningReArmsIt() async throws {
        let (client, _, sleeper, vm) = try await failingPage()
        defer { vm.stopRefresh(); Task { await sleeper.releaseAll() } }
        await settle { await sleeper.retryWaits == [2] }
        vm.stopRefresh()
        let pairs = client.historyFetches
        clock += 10
        await sleeper.releaseRetry()
        try? await Task.sleep(for: .milliseconds(40))
        XCTAssertEqual(client.historyFetches, pairs, "a page that was left asks nothing")

        client.failHistory = false
        client.response = try event(p: 0.60, revision: folded21)
        client.historyResponse = try history(p: 0.60, revision: folded21)
        await vm.load()
        await settle { await sleeper.retryWaits == [2, 2] }
        // A load is not the pair: the failure stands until the pair recovers.
        XCTAssertTrue(vm.pricePairRefreshFailed)
        let waits = await sleeper.retryWaits
        XCTAssertEqual(waits, [2, 2], "returning with a failed pair re-arms its retry")
        clock += 10
        await sleeper.releaseRetry()
        await settle { !vm.pricePairRefreshFailed }
        XCTAssertFalse(vm.pricePairRefreshFailed)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.60)
    }
}
