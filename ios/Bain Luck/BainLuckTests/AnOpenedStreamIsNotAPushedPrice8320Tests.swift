import XCTest
@testable import Bain_Luck

/// #8320 — the live page's green dot claims a PUSHED PRICE, not an open socket.
///
/// native/319, on a Polymarket-only live match: the toolbar showed the push dot
/// for up to 90 seconds on a stream that had opened and pushed nothing. The
/// controller reports delivering on `open` (rightly for the poll it stands down:
/// a stream that has just opened has not failed yet), and the dot read that
/// same flag. The brief's rule: connection must never imply a fresh observation.
///
/// Driven through the real `LiveStreamController` + `EventDetailViewModel` with a
/// fake socket, then the page's own pure `refreshIndicator` — the path the
/// toolbar and the fullscreen chart both read. The 90-second data-silence arm
/// needs the controller's clock and is pinned in `LiveStreamControllerTests`;
/// it arrives here as the same "not delivering" callback the blip and the
/// rollover below send.
@MainActor
final class AnOpenedStreamIsNotAPushedPrice8320Tests: XCTestCase {

    // MARK: - Fakes (the LiveBlendCaptureTests920 rig)

    private final class FakeHandle: LiveStreamHandle, @unchecked Sendable {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        var isClosed = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        @MainActor func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    private struct LiveOnlyClient: EventDetailProviding {
        struct Declined: Error {}
        let event: EventDetail
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    private let anchor = Date(timeIntervalSince1970: 1_757_000_000)

    private func livePage() async throws -> (EventDetailViewModel, FakeHandle) {
        let handle = FakeHandle()
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let event = try decoder.decode(EventDetail.self, from: Data("""
        {
          "id": 4242, "home_team": "Royals", "away_team": "White Sox",
          "status": "live",
          "current_odds": {"home_probability": 0.40, "away_probability": 0.60}
        }
        """.utf8))
        let vm = EventDetailViewModel(
            eventId: 4242,
            client: LiveOnlyClient(event: event),
            makeStreamHandle: { _ in handle },
            now: { [anchor] in anchor.timeIntervalSince1970 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        return (vm, handle)
    }

    private func indicator(_ vm: EventDetailViewModel) -> EventDetailView.RefreshIndicator {
        EventDetailView.refreshIndicator(
            status: vm.event?.status,
            streamDelivering: vm.streamDelivering,
            pushedPrice: vm.streamHasPushedPrice)
    }

    private func price(_ p: Double?, stamp: String = "2026-09-24T01:00:00Z") -> String {
        let value = p.map { "\($0)" } ?? "null"
        return """
        {"event_id": 4242, "p": \(value), "source": "polymarket", "source_value": \(value), \
        "updated_at": "\(stamp)", "status": "live"}
        """
    }

    // MARK: - Initial connection

    /// THE DEFECT. Delivering is true (the poll stands down, unchanged) and the
    /// page still says only that it can refresh.
    func testAnOpenedStreamWithNoPriceIsStillPolled() async throws {
        let (vm, handle) = try await livePage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        XCTAssertTrue(vm.streamDelivering, "the controller's contract for the poll is unchanged")
        XCTAssertFalse(vm.streamHasPushedPrice)
        XCTAssertEqual(indicator(vm), .polling)
    }

    /// A heartbeat proves the server process is alive, not that a price moved.
    func testAHeartbeatIsNotAPrice() async throws {
        let (vm, handle) = try await livePage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("heartbeat")
        XCTAssertEqual(indicator(vm), .polling)
    }

    /// A frame with no `p` leaves the hero where it was, so it earns nothing.
    func testAFrameWithoutAPriceIsNotAPushedPrice() async throws {
        let (vm, handle) = try await livePage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("probability", price(nil))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.40)
        XCTAssertEqual(indicator(vm), .polling)
    }

    // MARK: - Accepted push

    /// The dot turns on with the price it claims, and the hero holds that price.
    func testTheFirstPushedPriceTurnsTheDotOn() async throws {
        let (vm, handle) = try await livePage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("probability", price(0.55))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(indicator(vm), .streaming)
    }

    /// An unchanged price is still a delivery: the dot stays, nothing flips.
    func testAnUnchangedPriceKeepsTheDotWithoutAChange() async throws {
        let (vm, handle) = try await livePage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("probability", price(0.55))
        handle.fire("probability", price(0.55))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(indicator(vm), .streaming)
    }

    // MARK: - Interruption and fallback

    /// A transport blip drops the page to polling, and the resumed stream must
    /// push a price again before the dot returns — an old price does not count.
    func testAnInterruptedStreamMustPushAgain() async throws {
        let (vm, handle) = try await livePage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("probability", price(0.55))
        XCTAssertEqual(indicator(vm), .streaming)

        handle.fire("error")
        XCTAssertFalse(vm.streamDelivering)
        XCTAssertFalse(vm.streamHasPushedPrice, "a fall back to polling forgets the old push")
        XCTAssertEqual(indicator(vm), .polling)

        // The resumed stream's first price is applied BEFORE the controller
        // reports delivering again; clearing on the way up would erase it.
        // A changed observation must carry a newer write time; reusing the
        // first frame's stamp tests a replay, not a newly pushed price (#920).
        handle.fire("probability", price(0.58, stamp: "2026-09-24T01:00:05Z"))
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.58)
        XCTAssertEqual(indicator(vm), .streaming)
    }

    /// The server's 15-minute rollover closes this socket; the next one starts
    /// from "no price yet".
    func testARolloverMustPushAgain() async throws {
        let (vm, handle) = try await livePage()
        defer { vm.stopRefresh() }
        handle.fire("open")
        handle.fire("probability", price(0.55))
        handle.fire("reconnect")
        XCTAssertFalse(vm.streamHasPushedPrice)
        XCTAssertEqual(indicator(vm), .polling)
    }

    /// Leaving the page tears the stream down and the claim with it.
    func testStoppingThePageClearsTheClaim() async throws {
        let (vm, handle) = try await livePage()
        handle.fire("open")
        handle.fire("probability", price(0.55))
        vm.stopRefresh()
        XCTAssertFalse(vm.streamHasPushedPrice)
        XCTAssertFalse(vm.streamDelivering)
    }
}
