import XCTest
@testable import Bain_Luck

/// Real VM/controller composition. The handle reproduces the transport contract:
/// every HTTP refusal closes it before emitting error. No fabricated price feed.
@MainActor
final class StreamRefusalRecovery9419Tests: XCTestCase {
    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var isConnecting = false
        var closeCount = 0
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true; closeCount += 1 }
        func fire(_ event: String, _ raw: String = "") {
            for handler in handlers[event] ?? [] { handler(raw) }
        }
        func refuse() { isClosed = true; fire("error") }
    }
    private final class Clock { var time: TimeInterval = 1_790_000_000 }
    private final class Client: EventDetailProviding, @unchecked Sendable {
        struct Declined: Error {}
        var status = "live"
        var failDetail = false
        func fetchEvent(id: Int) async throws -> EventDetail {
            if failDetail { throw Declined() }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(EventDetail.self, from: Data("""
            {"id":4242,"home_team":"Home","away_team":"Away","status":"\(status)",
             "commence_time":"2026-01-01T00:00:00Z",
             "current_odds":{"home_probability":0.4,"away_probability":0.6}}
            """.utf8))
        }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }
    private final class Rig {
        let clock = Clock()
        let client = Client()
        var handles: [Handle] = []
        lazy var vm = EventDetailViewModel(
            eventId: 4242, client: client,
            makeStreamHandle: { [unowned self] _ in
                XCTAssertTrue(self.handles.allSatisfy(\.isClosed), "no overlapping streams")
                let handle = Handle()
                self.handles.append(handle)
                return handle
            }, now: { [unowned self] in self.clock.time },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
    }

    func testRefusedLiveStreamRetriesOnlyAfterSuccessfulLiveDetailAndBoundedDelay() async throws {
        let r = Rig()
        defer { r.vm.stopRefresh() }
        await r.vm.load()
        let first = r.handles[0]
        first.refuse()
        XCTAssertFalse(r.vm.streamDelivering)
        for _ in 0..<5 { await r.vm.load() }
        XCTAssertEqual(r.handles.count, 1, "repeated loads must not cause a retry storm")
        r.clock.time += 29
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 1)
        r.clock.time += 1
        r.client.failDetail = true
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 1, "cached live state after failed detail cannot authorize retry")
        r.client.failDetail = false
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 2, "a later successful live detail must recover push")
        guard r.handles.count == 2 else { return }
        let second = r.handles[1]
        second.fire("open")
        second.fire("probability", """
        {"event_id":4242,"p":0.55,"source":"kalshi","source_value":0.55,
         "updated_at":"2026-09-28T17:00:00Z","status":"live"}
        """)
        XCTAssertTrue(r.vm.streamDelivering)
        XCTAssertEqual(r.vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(r.vm.liveBlend.last?.homeProbability, 0.55)
        second.refuse()
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 2)
        r.clock.time += 30
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 3, "each new refusal has its own bounded retry")
    }

    func testSuspendedOpensOneQuoteStreamAndLaterLiveDetailReusesIt() async {
        let r = Rig()
        defer { r.vm.stopRefresh() }
        r.client.status = "suspended"
        await r.vm.load()
        r.clock.time += 30
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 1)
        XCTAssertEqual(r.vm.event?.status, "suspended", "quote eligibility must not mark the sport live")
        r.client.status = "live"
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 1)
    }

    func testHealthyAndRecoveringStreamsAreNotReplacedByDetailPolls() async {
        let r = Rig()
        defer { r.vm.stopRefresh() }
        await r.vm.load()
        let first = r.handles[0]
        first.fire("open")
        r.clock.time += 120
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 1)
        first.isConnecting = true
        first.fire("error")
        r.clock.time += 30
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 1, "transport already retries this connection")
        XCTAssertFalse(first.isClosed)
    }

    func testSuspendedAfterRefusalRetriesBoundedlyButCompletedDoesNot() async {
        let r = Rig()
        defer { r.vm.stopRefresh() }
        await r.vm.load()
        r.handles[0].refuse()
        r.clock.time += 30
        r.client.status = "suspended"
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 2, "the admitted suspended contract recovers after its bounded refusal delay")
        XCTAssertEqual(r.vm.event?.status, "suspended")
        guard r.handles.count == 2 else { return }
        r.handles[1].refuse()
        r.clock.time += 30
        r.client.status = "completed"
        await r.vm.load()
        XCTAssertEqual(r.handles.count, 2, "terminal sport results stay off quote retry")
        XCTAssertEqual(r.vm.event?.status, "completed")
    }
}
