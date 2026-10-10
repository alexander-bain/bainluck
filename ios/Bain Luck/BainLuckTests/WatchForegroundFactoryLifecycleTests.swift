import Foundation
import XCTest
@testable import Bain_Luck

@MainActor final class WatchForegroundFactoryLifecycleTests: XCTestCase {
    /// Intercepts every request in this private session; no network or server.
    /// The actual URLSession AsyncBytes pump must run to deliver the frame.
    private nonisolated final class StreamOrigin: URLProtocol, @unchecked Sendable {
        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            guard request.url?.path == "/api/events/101/stream",
                  request.value(forHTTPHeaderField: "Accept") == "text/event-stream" else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL)); return
            }
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "text/event-stream"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            let frame = "event: probability\ndata: {\"event_id\":101,\"p\":0.63,\"status\":\"live\"}\n\n"
            client?.urlProtocol(self, didLoad: Data(frame.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() { }
    }

    func testMountedFactoryStartsTheRealTransportBytePump() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StreamOrigin.self]
        let session = URLSession(configuration: config)
        defer { session.invalidateAndCancel() }
        // Same factory as the mounted default opener. No manually connected
        // transport and no fake LiveStreamHandle can make this assertion pass.
        let handle = try WatchForegroundStreamFactory.open(eventID: 101, session: session)
        defer { handle.close() }
        let delivered = expectation(description: "Real factory connected and pumped SSE")
        handle.on("probability") { raw in
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            let frame = try? decoder.decode(LiveStreamFrame.self, from: Data(raw.utf8))
            XCTAssertEqual(frame?.eventId, 101)
            XCTAssertEqual(frame?.p, 0.63)
            delivered.fulfill()
        }
        await fulfillment(of: [delivered], timeout: 2)
    }

    private final class Handle: LiveStreamHandle {
        var isClosed = false
        var closes = 0
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }
        func close() { isClosed = true; closes += 1 }
        func fire(_ event: String, _ raw: String) { handlers[event]?.forEach { $0(raw) } }
    }
    private actor Details: WatchSelectedGameTransport {
        var values: [WatchSelectedGame]
        init(_ values: [WatchSelectedGame]) { self.values = values }
        func fetch(eventID: Int) async throws -> WatchSelectedGame {
            guard !values.isEmpty else { throw URLError(.badServerResponse) }
            return values.removeFirst()
        }
    }
    nonisolated private static func detail(status: String, revision: Any? = ["101": 8],
                                           priceClock: String = "2026-10-10T09:00:00Z",
                                           scoreClock: String = "2026-10-10T09:00:00Z") throws -> WatchSelectedGame {
        var json: [String: Any] = ["id": 101, "home_team": "Home", "away_team": "Away",
            "status": status, "sport": "soccer_epl", "hero_probability_source": "blend",
            "hero_probability": 0.60, "hero_probability_away": 0.30,
            "current_odds": ["draw_probability": 0.10],
            "hero_probability_observed_at": priceClock, "score_observed_at": scoreClock]
        if let revision { json["blend_fold_revision"] = revision }
        return try JSONDecoder().decode(WatchSelectedGame.self, from: JSONSerialization.data(withJSONObject: json))
    }

    func testActualDecoderAndStoreAdoptSuspensionWithoutFailureBackoff() async throws {
        let name = "watch-suspended-store-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        let live = try Self.detail(status: "live")
        let suspended = try Self.detail(status: "suspended", revision: ["101": 9])
        XCTAssertNotNil(live.blendRevision)
        XCTAssertNil(suspended.blendRevision, "Non-live price must not borrow a live blend vector")
        let store = WatchSelectedGameStore(transport: Details([live, suspended]), defaults: defaults)
        store.select(eventID: 101)
        await store.refresh()
        await store.refresh()
        XCTAssertEqual(store.game?.status, "suspended")
        XCTAssertEqual(store.successfulRefreshSequence, 2)
        XCTAssertNil(store.errorMessage)
        XCTAssertEqual(store.nextRefreshDelay, 300, "Use the existing non-live cadence, not failure backoff")
        XCTAssertEqual(store.game?.probabilityObservedAt, live.probabilityObservedAt)
        XCTAssertEqual(store.game?.scoreObservedAt, live.scoreObservedAt)
    }

    func testSuspensionStopsStreamPollsAndReopensOnlyAfterLiveReturns() async throws {
        let name = "watch-suspended-loop-\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: name))
        defer { defaults.removePersistentDomain(forName: name) }
        var clock = 1_000.0
        let details = Details([try Self.detail(status: "live"), try Self.detail(status: "suspended"),
                               try Self.detail(status: "live", revision: ["101": 9])])
        let store = WatchSelectedGameStore(transport: details, defaults: defaults, retryClock: { clock })
        store.select(eventID: 101)
        var handles: [Handle] = []
        var sleeps = 0
        var observedSuspension = false
        await store.runLiveForegroundRefresh(open: { _ in
            let handle = Handle(); handles.append(handle); return handle
        }, clock: { clock }, sleep: { seconds in
            sleeps += 1
            if sleeps > 10 { throw CancellationError() }
            if store.successfulRefreshSequence == 1, sleeps == 1 {
                handles.first?.fire("open", "")
                handles.first?.fire("probability", #"{"event_id":101,"p":0.6,"status":"suspended","rev":{"101":9}}"#)
            }
            if store.successfulRefreshSequence == 2 {
                observedSuspension = true
                XCTAssertEqual(store.game?.status, "suspended")
                XCTAssertEqual(handles.count, 1)
                XCTAssertTrue(handles[0].isClosed)
                XCTAssertNil(store.activeForegroundStream)
                XCTAssertEqual(store.nextRefreshDelay, 300)
                // Advance the injected monotonic clock; no real wait or extra socket.
                clock += store.foregroundPollDelay
            } else if store.successfulRefreshSequence == 3 {
                XCTAssertEqual(store.game?.status, "live")
                XCTAssertEqual(handles.count, 2)
                throw CancellationError()
            } else { clock += seconds }
        })
        XCTAssertTrue(observedSuspension)
        XCTAssertEqual(store.successfulRefreshSequence, 3)
        XCTAssertEqual(handles.count, 2)
        XCTAssertTrue(handles.allSatisfy(\.isClosed), "Suspension and final task departure close their own streams")
    }

    func testLifecycleAdmissionKeepsMalformedLiveClockAndTerminalGuards() throws {
        let live = try Self.detail(status: "live")
        let suspended = try Self.detail(status: "suspended")
        XCTAssertTrue(WatchSelectedGameStore.canAdopt(suspended, replacing: live))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.detail(status: "live", revision: nil), replacing: live))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.detail(status: "live", revision: ["101": "bad"]), replacing: live))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.detail(status: "", revision: nil), replacing: live))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.detail(status: "suspended",
            priceClock: "2026-10-10T08:00:00Z"), replacing: live))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(try Self.detail(status: "suspended",
            scoreClock: "2026-10-10T08:00:00Z"), replacing: live))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(suspended, replacing: try Self.detail(status: "final")))
        XCTAssertFalse(WatchSelectedGameStore.canAdopt(suspended, replacing: try Self.detail(status: "closed")))
        XCTAssertTrue(WatchSelectedGameStore.canAdopt(try Self.detail(status: "live", revision: ["101": 9]), replacing: suspended))
    }
}
