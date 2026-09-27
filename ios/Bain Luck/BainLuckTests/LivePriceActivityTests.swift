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

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func push(p: Double, at: String, rev: String?, source: String = "polymarket") {
            fire("probability", """
            {"event_id":4242,"p":\(p),"source":"\(source)","source_value":0.4,"updated_at":"\(at)","status":"live","rev":\(rev ?? "null")}
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
        private(set) var eventResponses = 0
        private(set) var historyFetches = 0
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail {
            eventFetches += 1
            let result = response
            if let beforeEventResponse { await beforeEventResponse() }
            if failEvent { throw Missing() }
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
