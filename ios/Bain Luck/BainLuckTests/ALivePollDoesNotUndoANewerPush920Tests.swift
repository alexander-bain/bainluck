import XCTest
@testable import Bain_Luck

@MainActor
final class ALivePollDoesNotUndoANewerPush920Tests: XCTestCase {
    private func event(
        p: String = "0.40", status: String = "live", score: Int = 2,
        sources: String = #""kalshi":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"}"#
    ) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Red Sox","away_team":"Cubs","status":"\(status)",
         "home_score":\(score),"away_score":1,
         "current_odds":{"home_probability":\(p),"away_probability":0.60,
           "home_rendered_percent":40,"away_rendered_percent":60,
           "captured_at":"2026-09-25T19:00:00Z"},
         "win_probability_sources":{\(sources)}}
        """.utf8))
    }

    private func frame(source: String = "kalshi", stamp: String? = "2026-09-25T17:00:05Z", p: Double? = 0.55) -> LiveStreamFrame {
        LiveStreamFrame(eventId: 4242, p: p, source: source, sourceValue: p,
                        updatedAt: stamp, status: "live")
    }

    func testOlderSourceClockKeepsPushButAdoptsScoreAndClearsOldRounding() throws {
        let result = LiveEventPriceReconciliation.applying(frame(), to: try event(score: 3), delivering: true)
        XCTAssertEqual(result.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(result.currentOdds?.awayProbability ?? 0, 0.45, accuracy: 0.00001)
        XCTAssertEqual(result.homeScore, 3)
        XCTAssertNil(result.currentOdds?.homeRenderedPercent)
        XCTAssertNil(result.currentOdds?.awayRenderedPercent)
    }

    func testLaterCachedResponseStillCannotUndoThePush() throws {
        let cached = try event()
        for _ in 0..<2 {
            XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: cached, delivering: true).currentOdds?.homeProbability, 0.55)
        }
    }

    func testEquallyNewAndNewerSourceResponseWins() throws {
        for stamp in ["2026-09-25T17:00:05Z", "2026-09-25T17:00:06Z"] {
            let fresh = try event(p: "0.62", sources: "\"kalshi\":{\"value\":0.62,\"updated_at\":\"\(stamp)\"}")
            XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: fresh, delivering: true).currentOdds?.homeProbability, 0.62)
        }
    }

    func testAnotherSourceCanAdvanceTheServedBlend() throws {
        let fresh = try event(p: "0.62", sources: #""kalshi":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"},"polymarket":{"value":0.8,"updated_at":"2026-09-25T17:00:06Z"}"#)
        XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: fresh, delivering: true).currentOdds?.homeProbability, 0.62)
    }

    func testNoPushAndPollingFallbackAdoptTheResponse() throws {
        let polled = try event()
        XCTAssertEqual(LiveEventPriceReconciliation.applying(nil, to: polled, delivering: true).currentOdds?.homeProbability, 0.4)
        XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: polled, delivering: false).currentOdds?.homeProbability, 0.4)
    }

    func testFinalAndSuspendedResponsesRemainAuthoritative() throws {
        for status in ["final", "completed", "suspended"] {
            let result = LiveEventPriceReconciliation.applying(frame(), to: try event(p: "1", status: status, score: 4), delivering: true)
            XCTAssertEqual(result.status, status)
            XCTAssertEqual(result.homeScore, 4)
            XCTAssertEqual(result.currentOdds?.homeProbability, 1)
        }
    }

    func testWithheldProbabilityAndRemovedSourceAreNotResurrected() throws {
        let withheld = try event(p: "null")
        XCTAssertNil(LiveEventPriceReconciliation.applying(frame(), to: withheld, delivering: true).currentOdds?.homeProbability)
        let removed = try event(sources: #""polymarket":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"}"#)
        XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: removed, delivering: true).currentOdds?.homeProbability, 0.4)
    }

    func testMissingAndMalformedClocksDoNotInventAnOrdering() throws {
        for sources in [#""kalshi":0.4"#, #""kalshi":{"value":0.4}"#, #""kalshi":{"value":0.4,"updated_at":"invalid"}"#, #""kalshi":{"value":0.4,"updated_at":123}"#] {
            let result = LiveEventPriceReconciliation.applying(frame(), to: try event(sources: sources), delivering: true)
            XCTAssertEqual(result.currentOdds?.homeProbability, 0.4)
        }
        XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(stamp: nil), to: try event(), delivering: true).currentOdds?.homeProbability, 0.4)
    }

    func testUnknownSourceClockCannotBeHiddenByAnOldSibling() throws {
        for name in ["kalshi", "future_venue"] {
            let polled = try event(sources: "\"\(name)\":{\"value\":0.4},\"polymarket\":{\"value\":0.3,\"updated_at\":\"2026-09-25T17:00:00Z\"}")
            XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(source: "polymarket"), to: polled, delivering: true).currentOdds?.homeProbability, 0.4)
        }
    }

    func testBookCountIsNotAClockedProbabilitySource() throws {
        let polled = try event(sources: #""kalshi":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"},"betting_book_count":{"value":10}"#)
        XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(), to: polled, delivering: true).currentOdds?.homeProbability, 0.55)
    }

    func testInvalidOrUnrelatedFrameCannotChangeAResponse() throws {
        for p in [Double.nan, Double.infinity, -0.01, 1.01] {
            XCTAssertEqual(LiveEventPriceReconciliation.applying(frame(p: p), to: try event(), delivering: true).currentOdds?.homeProbability, 0.4)
        }
        let other = LiveStreamFrame(eventId: 99, p: 0.55, source: "kalshi", sourceValue: 0.55,
                                    updatedAt: "2026-09-25T17:00:05Z", status: "live")
        XCTAssertEqual(LiveEventPriceReconciliation.applying(other, to: try event(), delivering: true).currentOdds?.homeProbability, 0.4)
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for handler in handlers[event] ?? [] { handler(raw) } }
    }

    private actor HeldClient: EventDetailProviding {
        struct Declined: Error {}
        let initial: EventDetail
        var stale: EventDetail
        var calls = 0
        var held: CheckedContinuation<EventDetail, Never>?
        init(initial: EventDetail, stale: EventDetail) { self.initial = initial; self.stale = stale }
        func fetchEvent(id: Int) async throws -> EventDetail {
            calls += 1
            if calls == 1 { return initial }
            if calls > 2 { return stale }
            return await withCheckedContinuation { held = $0 }
        }
        func setResponse(_ response: EventDetail) { stale = response }
        var hasHeldRequest: Bool { held != nil }
        func release() { held?.resume(returning: stale); held = nil }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Declined() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Declined() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Declined() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Declined() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Declined() }
    }

    /// Real controller -> view model -> delayed REST completion, not only the
    /// pure rule. The score adopts the response while hero and chart keep 55%.
    func testSlowRestAndFollowingCachedRestKeepHeroAndChartTogether() async throws {
        let client = HeldClient(initial: try event(), stale: try event(score: 3))
        let handle = Handle()
        let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        let pending = Task { @MainActor in await vm.load() }
        while !(await client.hasHeldRequest) { await Task.yield() }
        handle.fire("probability", #"{"event_id":4242,"p":0.55,"source":"kalshi","source_value":0.55,"updated_at":"2026-09-25T17:00:05Z","status":"live"}"#)
        await client.release()
        await pending.value
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(vm.event?.homeScore, 3)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.55)
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.55)
        handle.fire("error")
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.4, "polling fallback must recover even if push ends")
    }
    func testOlderPushCannotSplitHeroFromChartButCanReportFinal() async throws {
        let client = HeldClient(initial: try event(), stale: try event())
        let handle = Handle()
        let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        handle.fire("probability", #"{"event_id":4242,"p":0.55,"source":"kalshi","source_value":0.55,"updated_at":"2026-09-25T17:00:05Z","status":"live"}"#)
        handle.fire("probability", #"{"event_id":4242,"p":0.30,"source":"kalshi","source_value":0.30,"updated_at":"2026-09-25T17:00:05Z","status":"live"}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55, "an equal stamp cannot replace the plotted reading")
        handle.fire("probability", #"{"event_id":4242,"p":0.30,"source":"kalshi","source_value":0.30,"updated_at":"2026-09-25T17:00:04Z","status":"final"}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.55)
        XCTAssertEqual(vm.event?.status, "final")
    }

    func testNewerRestRetiresPushAndRejectsAnOlderFollowingPush() async throws {
        let fresh = try event(p: "0.62", sources: #""kalshi":{"value":0.62,"updated_at":"2026-09-25T17:00:10Z"}"#)
        let client = HeldClient(initial: try event(), stale: fresh)
        let handle = Handle()
        let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        defer { vm.stopRefresh() }
        await vm.load()
        handle.fire("open")
        handle.fire("probability", #"{"event_id":4242,"p":0.55,"source":"kalshi","source_value":0.55,"updated_at":"2026-09-25T17:00:05Z","status":"live"}"#)
        let pending = Task { @MainActor in await vm.load() }
        while !(await client.hasHeldRequest) { await Task.yield() }
        await client.release()
        await pending.value
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.62)
        handle.fire("probability", #"{"event_id":4242,"p":0.56,"source":"kalshi","source_value":0.56,"updated_at":"2026-09-25T17:00:06Z","status":"live"}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.62)
        await client.setResponse(try event())
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.4, "do not resurrect the retired 55% push; ordinary REST precedence is unchanged")
        handle.fire("probability", #"{"event_id":4242,"p":0.56,"source":"kalshi","source_value":0.56,"updated_at":"2026-09-25T17:00:06Z","status":"live"}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.4, "older REST does not lower the known replay watermark")
        await client.setResponse(try event(p: "0.45", sources: #""kalshi":{"value":0.45}"#))
        await vm.load()
        handle.fire("probability", #"{"event_id":4242,"p":0.56,"source":"kalshi","source_value":0.56,"updated_at":"2026-09-25T17:00:06Z","status":"live"}"#)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.45, "unknown clocks do not erase the known replay watermark")
    }

}
