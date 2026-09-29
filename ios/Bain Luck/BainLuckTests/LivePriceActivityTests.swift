import XCTest
@testable import Bain_Luck

@MainActor
final class LivePriceActivityTests: XCTestCase {
    private static let bothSources = #""kalshi":{"value":0.8,"updated_at":"2026-09-25T17:00:00Z"},"polymarket":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"}"#
    private static let polymarketOnly = #""polymarket":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"}"#

    private func event(
        p: Double = 0.6, heroP: Double? = nil, source: String = "blend", status: String = "live",
        sport: String = "baseball_mlb", score: Int = 2, away: String? = nil, revision: String? = #"{"4242":10}"#,
        observedAt: String = "2026-09-25T17:00:00Z", sources: String = bothSources
    ) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Red Sox","away_team":"Cubs","sport":"\(sport)","status":"\(status)",
         "home_score":\(score),"away_score":1,
         "current_odds":{"home_probability":\(p),"away_probability":\(away ?? String(1 - p)),
           "home_rendered_percent":\(Int((p * 100).rounded())),"away_rendered_percent":\(Int(((1 - p) * 100).rounded()))},
         "hero_probability":\(heroP ?? p),"hero_probability_source":"\(source)",
         "hero_probability_observed_at":"\(observedAt)",
         "blend_fold_revision":\(revision ?? "null"),
         "win_probability_sources":{\(sources)}}
        """.utf8))
    }

    private func pairedHistory(p: Double = 0.52, revision: String = #"{"4242":21,"999":5}"#) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Red Sox","away_team":"Cubs","history":[],
         "aggregate_line":[{"timestamp":"2026-09-25T17:10:00Z","home_probability":\(p)}],
         "blend_edge_fold_revision":\(revision),"blend_edge_observed_at":"2026-09-25T17:10:00Z"}
        """.utf8))
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func push(p: Double, at: String, rev: String?, source: String = "polymarket", status: String = "live") {
            fire("probability", """
            {"event_id":4242,"p":\(p),"source":"\(source)","source_value":0.4,"updated_at":"\(at)","status":"\(status)","rev":\(rev ?? "null")}
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
        private(set) var eventFetches = 0
        private(set) var activeEventReads = 0
        private(set) var peakEventReads = 0
        private(set) var eventResponses = 0
        private(set) var eventFailures = 0
        private(set) var historyFetches = 0
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail {
            eventFetches += 1
            activeEventReads += 1
            peakEventReads = max(peakEventReads, activeEventReads)
            defer { activeEventReads -= 1 }
            let result = response
            if let beforeEventResponse { await beforeEventResponse() }
            if failEvent { eventFailures += 1; throw Missing() }
            eventResponses += 1
            return result
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            historyFetches += 1
            guard let historyResponse else { throw Missing() }
            return historyResponse
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private func model(_ client: Client, _ handle: Handle) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
    }

    private func settle(until condition: () -> Bool) async {
        for _ in 0..<200 where !condition() { await Task.yield() }
    }

    func testEligibleNonLivePagesStreamHeroSourceAndChartWithoutChangingSportsStatus() async throws {
        for status in ["scheduled", "suspended"] {
            let client = Client(try event(status: status))
            let handle = Handle(), vm = model(client, handle)
            await vm.load()
            XCTAssertFalse(handle.handlers.isEmpty, "the initial load must connect")
            XCTAssertNil(vm.priceActivity)
            handle.fire("open")
            XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
            handle.push(p: 0.55, at: "2026-09-25T17:10:00Z", rev: #"{"4242":11}"#, status: status)
            XCTAssertEqual(vm.event?.status, status)
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
            XCTAssertEqual(vm.event?.winProbabilitySources?["polymarket"]?.updatedAt, "2026-09-25T17:10:00Z")
            XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.55)
            XCTAssertEqual(vm.event.flatMap { LiveEdgeReading.current(in: $0) }?.homeProbability, 0.55)
            XCTAssertEqual(vm.priceActivity?.sequence, 1)
            XCTAssertEqual(vm.liveUpdateStatus, .live)

            // A cached poll cannot undo the newly received price or its source.
            await vm.load()
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
            XCTAssertEqual(vm.event?.status, status)
            XCTAssertEqual(vm.priceActivity?.sequence, 1)
            handle.push(p: 0.9, at: "2026-09-25T17:30:00Z", rev: #"{"4242":10}"#, status: status)
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
            XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.55)
            XCTAssertEqual(vm.event.flatMap { LiveEdgeReading.current(in: $0) }?.homeProbability, 0.55)
            XCTAssertEqual(vm.priceActivity?.sequence, 1)
            vm.stopRefresh()
        }
    }

    func testSubsequentAdoptionStartsEligibleStreamAndFinalStopsIt() async throws {
        let client = Client(try event(status: "postponed"))
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load()
        XCTAssertTrue(handle.handlers.isEmpty)
        client.response = try event(status: "scheduled")
        await vm.load()
        XCTAssertFalse(handle.handlers.isEmpty)
        client.response = try event(p: 1, source: "final_result", status: "completed")
        await vm.load()
        XCTAssertTrue(handle.isClosed)
        XCTAssertEqual(vm.liveUpdateStatus, .hidden)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 1)
    }

    func testNonLiveRefusalKeepsPollingAndRetriesOnlyAfterEligibleReadAndInterval() async throws {
        for status in ["scheduled", "suspended"] {
            let client = Client(try event(status: status))
            var clock: TimeInterval = 1_790_355_605
            var opened = 0
            let first = Handle(), second = Handle()
            let vm = EventDetailViewModel(eventId: 4242, client: client,
                makeStreamHandle: { _ in opened += 1; return opened == 1 ? first : second },
                now: { clock }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
            await vm.load()
            first.fire("open")
            first.isClosed = true
            first.fire("error")
            XCTAssertEqual(vm.liveUpdateStatus, .autoRefresh)
            XCTAssertTrue(vm.isAutoRefreshing)
            await vm.load()
            XCTAssertEqual(opened, 1)
            clock += EventRefreshPlan.livePollInterval
            await vm.load()
            XCTAssertEqual(opened, 2)
            XCTAssertEqual(vm.event?.status, status)
            vm.stopRefresh()
        }
    }

    func testScheduledOpeningHeroRefetchesAuthoritativePairBeforeTakingStreamPrice() async throws {
        let client = Client(try event(source: "opening", status: "scheduled"))
        client.historyResponse = try pairedHistory(p: 0.52, revision: #"{"4242":11,"999":5}"#)
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        client.response = try event(p: 0.52, status: "scheduled", revision: #"{"4242":11,"999":5}"#)
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":11}"#, status: "scheduled")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, "raw frame is not an opening quote")
        XCTAssertTrue(vm.liveBlend.isEmpty)
        XCTAssertFalse(vm.streamHasPushedPrice)
        await settle { vm.event?.heroProbabilitySource == "blend" }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertEqual(vm.event?.status, "scheduled")
        XCTAssertEqual(vm.priceActivity?.homeLabel, "52%")
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.priceActivity?.sequence, 1)
        // Once the authoritative pair is a single-row blend, normal frames
        // can land directly again; folded vectors still require their pair.
        client.response = try event(p: 0.52, status: "scheduled", revision: #"{"4242":11}"#)
        await vm.load()
        handle.push(p: 0.53, at: "2026-09-25T17:11:00Z", rev: #"{"4242":12}"#, status: "scheduled")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.53)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.53)
    }

    func testOpeningInvalidationWithoutPriceAdoptsAuthoritativeBlend() async throws {
        let client = Client(try event(source: "opening", status: "suspended"))
        client.historyResponse = try pairedHistory(p: 0.52, revision: #"{"4242":11,"999":5}"#)
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        client.response = try event(p: 0.52, status: "suspended", revision: #"{"4242":11,"999":5}"#)
        handle.fire("probability", #"{"event_id":4242,"p":null,"status":"suspended","rev":{"4242":11}}"#)
        await settle { vm.event?.heroProbabilitySource == "blend" }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertEqual(vm.priceActivity?.sequence, 1)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.event?.status, "suspended")
    }

    /// The #9501 contributor invalidation exactly as `_fold_invalidation` emits
    /// it: no `status` key, null price/source, rev keyed by the ORIGIN event.
    /// Absent status must not promote or close the page; the paired refetch
    /// whose fold covers the origin row earns the one receipt.
    func testAbsentStatusContributorInvalidationAdoptsFoldWithoutChangingPhase() async throws {
        for status in ["scheduled", "suspended"] {
            let client = Client(try event(source: "opening", status: status))
            client.historyResponse = try pairedHistory(p: 0.52, revision: #"{"4242":11,"999":6}"#)
            let handle = Handle(), vm = model(client, handle)
            defer { vm.stopRefresh() }
            await vm.load()
            handle.fire("open")
            client.response = try event(p: 0.52, status: status, revision: #"{"4242":11,"999":6}"#)
            handle.fire("probability", #"{"event_id":4242,"origin_event_id":999,"invalidation":true,"p":null,"source":null,"source_value":null,"updated_at":"2026-09-25T17:10:00Z","rev":{"999":6}}"#)
            await settle { vm.event?.heroProbabilitySource == "blend" }
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52, status)
            XCTAssertEqual(vm.priceActivity?.sequence, 1, status)
            XCTAssertEqual(vm.event?.status, status, "absent frame status never changes the sports phase")
        }
    }

    func testOnlyAcceptedNewerPricesCreateLocalReceipts() async throws {
        let client = Client(try event(p: 0.6))
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load()
        XCTAssertNil(vm.priceActivity, "initial load is not a live update")
        handle.fire("open"); handle.fire("heartbeat")
        await vm.load()
        XCTAssertNil(vm.priceActivity, "open, heartbeat and cache-identical reload earn nothing")
        handle.push(p: 0.55, at: "2026-09-25T17:10:00Z", rev: #"{"4242":11}"#)
        let first = try XCTUnwrap(vm.priceActivity)
        XCTAssertEqual(first.sequence, 1)
        XCTAssertEqual(first.receivedAt, Date(timeIntervalSince1970: 1_790_355_605))
        XCTAssertEqual(first.homeProbability, 0.55)
        XCTAssertEqual(first.previousHomeLabel, "60%")
        XCTAssertEqual(first.homeLabel, "55%")
        XCTAssertEqual(first.homeDelta, -5)
        XCTAssertEqual(first.awayDelta, 5)
        XCTAssertTrue(first.displayedValueChanged)
        handle.push(p: 0.9, at: "2026-09-25T17:30:00Z", rev: #"{"4242":10}"#)
        XCTAssertEqual(vm.priceActivity, first, "old revision with a later clock is still old")
        handle.push(p: 0.551, at: "2026-09-25T17:11:00Z", rev: #"{"4242":12}"#)
        XCTAssertEqual(vm.priceActivity?.sequence, 2)
        XCTAssertFalse(try XCTUnwrap(vm.priceActivity).displayedValueChanged,
                       "a new observation whose printed 55/45 did not change refreshes the tooltip only")
        XCTAssertEqual(vm.priceActivity?.homeDelta, 0)
    }

    func testFoldAdoptionRecordsThePrintedBlendNotRawIncomingRow() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        client.historyResponse = try pairedHistory()
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        client.response = try event(p: 0.52, revision: #"{"4242":21,"999":5}"#)
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        XCTAssertNil(vm.priceActivity)
        await settle { vm.priceActivity != nil }
        XCTAssertEqual(vm.priceActivity?.homeLabel, "52%")
        XCTAssertEqual(vm.priceActivity?.previousHomeLabel, "60%")
        XCTAssertEqual(vm.priceActivity?.sequence, 1)
    }

    func testStaleInFlightFoldReadCannotDuplicateAnIndependentPollReceipt() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        client.historyResponse = try pairedHistory()
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        var pending: CheckedContinuation<Void, Never>?
        client.beforeEventResponse = { await withCheckedContinuation { pending = $0 } }
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        await settle { pending != nil }
        XCTAssertNotNil(pending)
        client.beforeEventResponse = nil
        client.response = try event(p: 0.52, revision: #"{"4242":21,"999":5}"#)
        await vm.load()
        let receipt = try XCTUnwrap(vm.priceActivity)
        let responses = client.eventResponses
        pending?.resume()
        await settle { client.eventResponses > responses }
        XCTAssertEqual(vm.priceActivity, receipt)
        XCTAssertEqual(receipt.sequence, 1)
        XCTAssertFalse(vm.streamHasPushedPrice, "ordinary poll receipt is not a stream claim")
    }

    func testOutdatedConnectionReadCannotEarnAFreshReceipt() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        client.historyResponse = try pairedHistory()
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        var pending: CheckedContinuation<Void, Never>?
        client.beforeEventResponse = { await withCheckedContinuation { pending = $0 } }
        client.response = try event(p: 0.52, revision: #"{"4242":21,"999":5}"#)
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        await settle { pending != nil }
        handle.fire("error"); handle.fire("open")
        pending?.resume()
        await settle { vm.event?.currentOdds?.homeProbability == 0.52 }
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertNil(vm.priceActivity)
        XCTAssertFalse(vm.streamHasPushedPrice)
    }

    private actor RefetchSleeper {
        var shortWait: TimeInterval?
        var pending: CheckedContinuation<Void, Never>?
        func sleep(_ seconds: TimeInterval) async {
            guard seconds < 2 else {
                try? await Task.sleep(for: .seconds(60))
                return
            }
            shortWait = seconds
            await withCheckedContinuation { pending = $0 }
        }
        func release() { pending?.resume(); pending = nil }
    }

    func testBurstAndSlowPairKeepOneReaderAndDeliverLatestWithinOneSecondWindow() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        client.historyResponse = try pairedHistory(p: 0.6, revision: #"{"4242":20,"999":5}"#)
        let handle = Handle(), sleeper = RefetchSleeper()
        var clock: TimeInterval = 1_790_355_605
        let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { clock }, sleep: { await sleeper.sleep($0) })
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        var pending: CheckedContinuation<Void, Never>?
        client.beforeEventResponse = { await withCheckedContinuation { pending = $0 } }
        client.response = try event(p: 0.52, revision: #"{"4242":21,"999":5}"#)
        client.historyResponse = try pairedHistory()
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        await settle { pending != nil }
        XCTAssertEqual(client.eventFetches, 2, "First invalidation starts immediately")
        for _ in 0..<30 {
            handle.push(p: 0.8, at: "2026-09-25T17:11:00Z", rev: #"{"4242":22}"#)
        }
        XCTAssertEqual(client.eventFetches, 2, "A slow request absorbs the burst without overlap")
        clock += 0.25
        client.beforeEventResponse = nil
        pending?.resume()
        for _ in 0..<200 {
            if await sleeper.shortWait != nil { break }
            await Task.yield()
        }
        let wait = await sleeper.shortWait
        XCTAssertEqual(wait, 0.75, "Trailing request waits only the rest of one second")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        client.response = try event(p: 0.48, revision: #"{"4242":22,"999":5}"#)
        client.historyResponse = try pairedHistory(p: 0.48, revision: #"{"4242":22,"999":5}"#)
        for _ in 0..<30 {
            handle.push(p: 0.8, at: "2026-09-25T17:11:00Z", rev: #"{"4242":22}"#)
        }
        XCTAssertEqual(client.eventFetches, 2, "More invalidations share the already scheduled trailing read")
        clock += 0.75
        await sleeper.release()
        await settle { vm.event?.currentOdds?.homeProbability == 0.48 }
        XCTAssertEqual(client.eventFetches, 3, "Sixty invalidations need one active and one trailing pair")
        XCTAssertEqual(client.peakEventReads, 1)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.48)
        XCTAssertEqual(vm.priceActivity?.sequence, 2)
    }

    func testRetiredConnectionFailureCannotDarkenItsSuccessor() async throws {
        let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
        client.historyResponse = try pairedHistory()
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        var pending: CheckedContinuation<Void, Never>?
        client.beforeEventResponse = { await withCheckedContinuation { pending = $0 } }
        client.failEvent = true
        handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
        await settle { pending != nil }
        XCTAssertNotNil(pending)
        handle.fire("error"); handle.fire("open")
        handle.push(p: 0.9, at: "2026-09-25T17:11:00Z", rev: #"{"4242":22}"#)
        XCTAssertTrue(vm.streamDelivering)
        pending?.resume()
        await settle { client.eventFailures == 1 }
        // Let the failed async child return to the pair's catch handler.
        for _ in 0..<20 { await Task.yield() }
        XCTAssertFalse(vm.pricePairRefreshFailed, "A retired read cannot mark the new connection broken")
        XCTAssertEqual(vm.liveUpdateStatus, .awaitingUpdate)
        XCTAssertNil(vm.priceActivity, "Neither the failed read nor the unaccepted raw frame earns a receipt")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6)
    }

    func testUnchangedFailedAndClocklessReadsDoNotClaimNewPrices() async throws {
        for fails in [false, true] {
            let client = Client(try event(p: 0.6, revision: #"{"4242":20,"999":5}"#))
            let handle = Handle(), vm = model(client, handle)
            await vm.load(); handle.fire("open")
            client.failEvent = fails
            let responses = client.eventFetches
            handle.push(p: 0.9, at: "2026-09-25T17:10:00Z", rev: #"{"4242":21}"#)
            await settle { client.eventFetches > responses }
            XCTAssertNil(vm.priceActivity)
            vm.stopRefresh()
        }
        let client = Client(try event(p: 0.6, revision: nil))
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        handle.push(p: 0.7, at: "unknown", rev: nil)
        XCTAssertNil(vm.priceActivity, "an unknown observation clock cannot prove a newer receipt")
    }

    func testCensoredPercentLabelsDoNotInventMotionOrNumericDeltas() async throws {
        let client = Client(try event(p: 0.001))
        let handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        handle.push(p: 0.009, at: "2026-09-25T17:10:00Z", rev: #"{"4242":11}"#)
        let receipt = try XCTUnwrap(vm.priceActivity)
        XCTAssertEqual(receipt.homeLabel, "<1%")
        XCTAssertEqual(receipt.awayLabel, ">99%")
        XCTAssertFalse(receipt.displayedValueChanged)
        XCTAssertNil(receipt.homeDelta)
        XCTAssertNil(receipt.awayDelta)
    }

    func testDrawSportWithholdsAwayAndUsesPlainHomeRounding() throws {
        let value = try event(p: 0.565, sport: "soccer_epl")
        let labels = LivePriceActivity.displayedLabels(in: value)
        XCTAssertEqual(labels.home, formatProbability(0.565))
        XCTAssertNil(labels.away)
    }
}
