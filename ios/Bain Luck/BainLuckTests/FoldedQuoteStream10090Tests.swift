import XCTest
@testable import Bain_Luck

/// #10090 — a folded hero (canonical + duplicate rows) refuses every raw-row
/// frame, so every move on a page like Celtics 15323012 (rows 15323012 and
/// 15326779) waited for a detail + history re-read. The server now follows a
/// pending raw frame with `folded_probability`: the authoritative full-fold
/// quote, or an explicit null. These pin the iPhone to that handshake.
@MainActor
final class FoldedQuoteStream10090Tests: XCTestCase {
    private static let both = #""kalshi":{"value":0.8,"updated_at":"2026-09-25T17:00:00Z"},"polymarket":{"value":0.4,"updated_at":"2026-09-25T17:00:00Z"}"#
    private static let folded = #"{"4242":20,"999":5}"#

    private func page(p: Double = 0.6, away: String? = nil, sport: String = "basketball_nba",
                      revision: String = folded) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"sport":"\(sport)","home_team":"Celtics","away_team":"Knicks","status":"live",
         "home_score":50,"away_score":48,
         "current_odds":{"home_probability":\(p),"away_probability":\(away ?? String(1 - p)),
           "home_rendered_percent":60,"away_rendered_percent":40},
         "hero_probability":\(p),"hero_probability_source":"blend",
         "hero_probability_observed_at":"2026-09-25T17:00:00Z",
         "blend_fold_revision":\(revision),"win_probability_sources":{\(Self.both)}}
        """.utf8))
    }

    private static func quote(p: Double = 0.52, away: String = "0.48", revision: String = #"{"4242":21,"999":5}"#,
                              at: String = "2026-09-25T17:10:00Z", sport: String = "basketball_nba",
                              status: String = "live") -> String {
        """
        {"event_id":4242,"hero_probability":\(p),"hero_probability_away":\(away),
         "hero_probability_source":"blend","hero_probability_observed_at":"\(at)",
         "blend_fold_revision":\(revision),
         "win_probability_sources":{"polymarket":{"value":\(p),"display_name":"Polymarket","type":"market","color":"#000","updated_at":"\(at)"},
                                    "betting_book_count":{"value":14,"display_name":"Books","type":"meta","color":"#000"}},
         "hero_sportsbook_count":null,"status":"\(status)","sport":"\(sport)","hero_settled_result":null}
        """
    }

    private static let raw = #""event_id":4242,"p":0.9,"source":"polymarket","source_value":0.9,"updated_at":"2026-09-25T17:10:00Z","status":"live","rev":{"4242":21}"#

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func pendingRaw() { fire("probability", "{\(FoldedQuoteStream10090Tests.raw),\"folded_quote_pending\":true}") }
        func result(_ quote: String) {
            fire("folded_probability", "{\(FoldedQuoteStream10090Tests.raw),\"folded_quote_pending\":false,\"folded_quote\":\(quote)}")
        }
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        var response: EventDetail
        var historyResponse: EventHistoryResponse?
        private(set) var eventFetches = 0
        private(set) var historyFetches = 0
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail { eventFetches += 1; return response }
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

    private func loaded(_ held: EventDetail, history: EventHistoryResponse? = nil) async -> (Client, Handle, EventDetailViewModel) {
        let client = Client(held), handle = Handle()
        client.historyResponse = history
        let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
        await vm.load(); handle.fire("open")
        return (client, handle, vm)
    }

    private func drain() async { for _ in 0..<200 { await Task.yield() } }

    // MARK: - Decode

    func testTheQuoteDecodesWithTheSportsbookCountAndABadQuoteNeverCostsTheFrame() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let good = try decoder.decode(LiveStreamFrame.self, from: Data(
            "{\(Self.raw),\"folded_quote_pending\":false,\"folded_quote\":\(Self.quote())}".utf8))
        XCTAssertEqual(good.foldedQuote?.quote?.heroProbability, 0.52)
        XCTAssertEqual(good.foldedQuote?.quote?.blendFoldRevision.rows, ["4242": 21, "999": 5])
        XCTAssertEqual(good.foldedQuotePending, false)
        XCTAssertFalse(good.foldedResult, "only the controller marks a result")
        for bad in [Self.quote(p: 1.5), Self.quote(revision: "{}"), Self.quote(at: "not a time"), "null"] {
            let frame = try decoder.decode(LiveStreamFrame.self, from: Data(
                "{\(Self.raw),\"folded_quote\":\(bad)}".utf8))
            XCTAssertNil(frame.foldedQuote?.quote, bad)
            XCTAssertEqual(frame.p, 0.9, "the raw half survives")
        }
    }

    // MARK: - The page

    func testAPendingRawWaitsAndTheNewerQuoteMovesHeroAndChartWithNoRestRead() async throws {
        let (client, handle, vm) = await loaded(try page())
        defer { vm.stopRefresh() }
        let fetches = client.eventFetches
        handle.pendingRaw()
        await drain()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, "a raw-row p is not the folded hero")
        XCTAssertEqual(client.eventFetches, fetches, "the promise holds the detail read back")

        handle.result(Self.quote())
        await drain()
        XCTAssertEqual(client.eventFetches, fetches)
        XCTAssertEqual(client.historyFetches, 1, "only the initial load read history")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertEqual(vm.event?.currentOdds?.awayProbability, 0.48)
        XCTAssertNil(vm.event?.currentOdds?.homeRenderedPercent)
        XCTAssertEqual(vm.event?.heroProbability, 0.52)
        XCTAssertEqual(vm.event?.heroProbabilityObservedAt, "2026-09-25T17:10:00Z")
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 21, "999": 5])
        XCTAssertNil(vm.event?.winProbabilitySources?["kalshi"], "the full rail replaces the held one")
        XCTAssertEqual(vm.event?.homeScore, 50, "score and clock stay as held")
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.52)
        XCTAssertEqual(vm.liveBlend.last?.date, "2026-09-25T17:10:00Z".asDate, "the chart point is the quote's own time")
        XCTAssertEqual(vm.liveUpdateStatus, .live)

        // A replayed same or older fold is held: no move, no read.
        let points = vm.liveBlend.count
        handle.pendingRaw()
        handle.result(Self.quote(p: 0.7, revision: #"{"4242":21,"999":5}"#))
        handle.pendingRaw()
        handle.result(Self.quote(p: 0.7, revision: #"{"4242":20,"999":5}"#))
        await drain()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertEqual(vm.liveBlend.count, points)
        XCTAssertEqual(client.eventFetches, fetches)
    }

    func testANullOrUnusableResultRunsTheExistingReadOnce() async throws {
        for result in ["null", Self.quote(revision: #"{"4242":21,"777":1}"#), Self.quote(sport: "soccer_epl")] {
            let (client, handle, vm) = await loaded(try page())
            let fetches = client.eventFetches
            handle.pendingRaw()
            handle.result(result)
            for _ in 0..<200 where client.eventFetches == fetches { await Task.yield() }
            XCTAssertEqual(client.eventFetches, fetches + 1, result)
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.6, result)
            vm.stopRefresh()
        }
    }

    func testADrawPricedQuoteKeepsTheAwaySideWithheld() async throws {
        let (_, handle, vm) = await loaded(try page(away: "null", sport: "soccer_epl"))
        defer { vm.stopRefresh() }
        handle.pendingRaw()
        handle.result(Self.quote(away: "null", sport: "soccer_epl"))
        await drain()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertNil(vm.event?.currentOdds?.awayProbability, "never an invented complement")
        XCTAssertNil(vm.event?.heroProbabilityAway)
    }

    func testAStalePollDoesNotRollTheAdoptedQuoteBack() async throws {
        let (client, handle, vm) = await loaded(try page())
        defer { vm.stopRefresh() }
        handle.pendingRaw()
        handle.result(Self.quote())
        await drain()
        client.response = try page(p: 0.6, revision: Self.folded)
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertEqual(vm.event?.blendFoldRevision?.revision?.rows, ["4242": 21, "999": 5])
    }

    private func history(edgeAt: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Celtics","away_team":"Knicks","status":"live","history":[],
         "aggregate_line":[{"timestamp":"\(edgeAt)","home_probability":0.6}],
         "blend_edge_pinned":true,"blend_edge_fold_revision":\(Self.folded)}
        """.utf8))
    }

    func testAnOlderClockRemovalAsksHistoryOnceAndAForwardQuoteAsksNothing() async throws {
        // Quote observed 17:10. A drawn edge at 17:05 is overtaken by the quote's
        // point; one at 17:11 (a removal left an older surviving quote) is not.
        for (edge, rereads) in [("2026-09-25T17:05:00Z", 0), ("2026-09-25T17:11:00Z", 1)] {
            let (client, handle, vm) = await loaded(try page(), history: try history(edgeAt: edge))
            let (events, histories) = (client.eventFetches, client.historyFetches)
            handle.pendingRaw()
            handle.result(Self.quote())
            for _ in 0..<200 where client.historyFetches == histories || client.eventFetches == events { await Task.yield() }
            XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52, edge)
            XCTAssertEqual(client.historyFetches, histories + rereads, edge)
            XCTAssertEqual(client.eventFetches, events + rereads, edge)
            vm.stopRefresh()
        }
    }

    // MARK: - Opt-in

    func testOnlyAnOptedInControllerHearsTheResult() {
        for optedIn in [false, true] {
            let handle = Handle()
            var frames: [LiveStreamFrame] = []
            let controller = LiveStreamController(open: { handle }, now: { 0 },
                onFrame: { frames.append($0) }, onDeliveringChange: { _ in },
                deliversFoldedQuotes: optedIn)
            controller.start()
            handle.pendingRaw()
            handle.result(Self.quote())
            XCTAssertEqual(frames.map(\.foldedResult), optedIn ? [false, true] : [false])
            XCTAssertEqual(frames.first?.foldedQuotePending, true)
            controller.stop()
        }
    }
}
