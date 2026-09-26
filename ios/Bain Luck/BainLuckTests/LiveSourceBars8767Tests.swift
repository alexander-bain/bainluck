import XCTest
@testable import Bain_Luck

@MainActor
final class LiveSourceBars8767Tests: XCTestCase {
    private let initialSources = #""kalshi":{"value":0.92,"updated_at":"2026-09-25T17:00:00Z","display_name":"Kalshi quote","type":"prediction_market","color":"green"},"polymarket":{"value":0.88,"updated_at":"2026-09-25T17:00:00Z","display_name":"Polymarket"},"betting_book_count":{"value":8}"#

    private func event(sources: String? = nil, status: String = "live", score: Int = 3) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"home_team":"Harvard","away_team":"Brown","status":"\(status)",
         "home_score":\(score),"away_score":1,"current_odds":{"home_probability":0.98,"away_probability":0.02},
         "win_probability_sources":{\(sources ?? initialSources)}}
        """.utf8))
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ raw: String = "") { for h in handlers[event] ?? [] { h(raw) } }
        func quote(_ source: String = "kalshi", value: String = "0.97", at: String = "2026-09-25T17:00:05Z", p: String = "0.99") {
            fire("probability", """
            {"event_id":4242,"p":\(p),"source":"\(source)","source_value":\(value),"updated_at":"\(at)","status":"live"}
            """)
        }
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        var response: EventDetail
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail { response }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private func model(_ client: Client, _ handle: Handle) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            now: { 1_790_355_605 }, sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) })
    }
    private func bar(_ vm: EventDetailViewModel, _ key: String) -> WinProbSourceCatalog.Entry? {
        WinProbSourceCatalog.entries(from: vm.event?.winProbabilitySources).first { $0.key == key }
    }

    func testActualExpandedBarPathUsesSourceQuoteNotBlendAndPreservesMetadataAndSibling() async throws {
        let client = Client(try event()), handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }; await vm.load(); handle.fire("open")
        handle.quote()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.99)
        XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.97)
        XCTAssertEqual(bar(vm, "polymarket")?.homeProbability, 0.88)
        XCTAssertEqual(bar(vm, "kalshi")?.label, "Kalshi quote")
        let source = vm.event?.winProbabilitySources?["kalshi"]
        XCTAssertEqual(source?.type, "prediction_market")
        XCTAssertEqual(source?.color, "green")
        XCTAssertEqual(source?.updatedAt, "2026-09-25T17:00:05Z")
        XCTAssertEqual(vm.event?.winProbabilitySources?["betting_book_count"]?.value?.doubleValue, 8)
    }

    func testEachSourceAdvancesIndependentlyOfTheNewerAggregateFrame() async throws {
        let client = Client(try event()), handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }; await vm.load(); handle.fire("open")
        handle.quote("polymarket", value: "0.96", at: "2026-09-25T17:00:20Z", p: "0.99")
        handle.quote("kalshi", value: "0.95", at: "2026-09-25T17:00:15Z", p: "0.91")
        XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.95)
        XCTAssertEqual(bar(vm, "polymarket")?.homeProbability, 0.96)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.99)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability, 0.99)
        // Both quoted sources survive a stale REST body, not just the last frame.
        await vm.load()
        XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.95)
        XCTAssertEqual(bar(vm, "polymarket")?.homeProbability, 0.96)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.99)
    }

    func testRetainedQuoteUsesRestMetadataAndScoreAndSurvivesTemporaryRecovery() async throws {
        let client = Client(try event()), handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }; await vm.load(); handle.fire("open"); handle.quote()
        client.response = try event(sources: initialSources.replacingOccurrences(of: "Kalshi quote", with: "Renamed venue"), score: 4)
        handle.fire("error")
        await vm.load()
        XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.97)
        XCTAssertEqual(bar(vm, "kalshi")?.label, "Renamed venue")
        XCTAssertEqual(vm.event?.homeScore, 4)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.99, "source overlay must run after the hero preservation decision")
    }

    func testOlderAndEqualPerSourceFramesCannotRollTheBarBack() async throws {
        let client = Client(try event()), handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }; await vm.load(); handle.fire("open"); handle.quote()
        for at in ["2026-09-25T17:00:04Z", "2026-09-25T17:00:05.000+00:00"] {
            handle.quote(value: "0.10", at: at)
            XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.97)
        }
    }

    func testMissingNullInvalidQuoteAndClockNeverUseAggregateAsSource() async throws {
        let client = Client(try event()), handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }; await vm.load(); handle.fire("open")
        for value in ["null", "-0.1", "1.1"] { handle.quote(value: value) }
        handle.quote(at: "invalid")
        handle.fire("probability", #"{"event_id":4242,"p":0.99,"source":"kalshi","updated_at":"2026-09-25T17:00:05Z","status":"live"}"#)
        handle.fire("probability", #"{"event_id":4242,"p":0.99,"source":"kalshi","source_value":0.97,"status":"live"}"#)
        XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.92)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.99)
    }

    func testRemovedNullAndUnknownClockRestSourcesRetireFramesWithoutResurrection() async throws {
        for sources in [#""polymarket":{"value":0.88,"updated_at":"2026-09-25T17:00:00Z"}"#,
                        #""kalshi":{"value":null,"updated_at":"2026-09-25T17:00:00Z"}"#,
                        #""kalshi":{"value":0.70}"#,
                        #""kalshi":{"value":0.70,"updated_at":"invalid"}"#] {
            let client = Client(try event()), handle = Handle(), vm = model(client, handle)
            await vm.load(); handle.fire("open"); handle.quote()
            client.response = try event(sources: sources); await vm.load()
            XCTAssertNotEqual(bar(vm, "kalshi")?.homeProbability, 0.97)
            client.response = try event(); await vm.load()
            XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.92)
            vm.stopRefresh()
        }
    }

    func testEquallyNewAndNewerRestQuoteWinsAndRetiresTheFrame() async throws {
        for at in ["2026-09-25T17:00:05Z", "2026-09-25T17:00:10Z"] {
            let client = Client(try event()), handle = Handle(), vm = model(client, handle)
            await vm.load(); handle.fire("open"); handle.quote()
            client.response = try event(sources: "\"kalshi\":{\"value\":0.96,\"updated_at\":\"\(at)\"}")
            await vm.load(); XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.96)
            client.response = try event(); await vm.load()
            XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.92, "retired pushed quote does not resurrect")
            vm.stopRefresh()
        }
    }

    func testTerminalRefusalAndFinishedRestDoNotRetainSourceQuotes() async throws {
        for status in ["live", "completed"] {
            let client = Client(try event()), handle = Handle(), vm = model(client, handle)
            await vm.load(); handle.fire("open"); handle.quote()
            if status == "live" { handle.fire("closed") }
            client.response = try event(status: status); await vm.load()
            XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.92)
            vm.stopRefresh()
        }
    }

    func testNewerRestThenOlderCacheCannotMakeAnOldSourceFrameNewAgain() async throws {
        let client = Client(try event()), handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }; await vm.load(); handle.fire("open"); handle.quote()
        client.response = try event(sources: #""kalshi":{"value":0.96,"updated_at":"2026-09-25T17:00:20Z"}"#)
        await vm.load()
        client.response = try event(); await vm.load()
        handle.quote(value: "0.11", at: "2026-09-25T17:00:10Z")
        XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.92, "an old cache does not reset the source acceptance watermark")
        handle.quote(value: "0.95", at: "2026-09-25T17:00:21Z")
        XCTAssertEqual(bar(vm, "kalshi")?.homeProbability, 0.95)
    }

    func testSourceAdmissionNeverInventsRowsOrUpdatesMetadataAsAQuote() async throws {
        let client = Client(try event()), handle = Handle(), vm = model(client, handle)
        defer { vm.stopRefresh() }; await vm.load(); handle.fire("open")
        for key in ["mlb", "unknown_venue", "final_result", "betting_book_count"] { handle.quote(key) }
        XCTAssertEqual(WinProbSourceCatalog.entries(from: vm.event?.winProbabilitySources).count, 2)
        XCTAssertEqual(vm.event?.winProbabilitySources?["betting_book_count"]?.value?.doubleValue, 8)
        XCTAssertNil(vm.event?.winProbabilitySources?["mlb"])
    }
}
