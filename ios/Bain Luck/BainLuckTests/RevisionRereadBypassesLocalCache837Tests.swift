import XCTest
import Foundation
@testable import Bain_Luck

/// A stream revision asks for a newer pair, not the same 15s/60s device cache.
/// Real APIClient + real URLSession dispatch; only the HTTP server is stubbed.
@MainActor
final class RevisionRereadBypassesLocalCache837Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var revision = 10
        nonisolated(unsafe) private static var captured: [URLRequest] = []

        static func reset() {
            lock.lock(); defer { lock.unlock() }
            revision = 10; captured = []
        }
        static func advance() {
            lock.lock(); defer { lock.unlock() }
            revision = 11
        }
        static func requests(ending suffix: String) -> [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured.filter { $0.url?.path.hasSuffix(suffix) == true }
        }
        private static func response(to request: URLRequest) -> (Int, Data) {
            lock.lock(); defer { lock.unlock() }
            captured.append(request)
            let p = revision == 10 ? 0.60 : 0.55
            let vector = "{\"4242\":\(revision),\"999\":5}"
            let date = revision == 10 ? "2026-09-27T17:00:00Z" : "2026-09-27T17:00:01Z"
            let body: String
            if request.url?.path == "/api/events/4242" {
                body = """
                {"id":4242,"home_team":"Home","away_team":"Away","sport":"baseball_mlb","status":"live",
                 "current_odds":{"home_probability":\(p),"away_probability":\(1-p)},
                 "hero_probability":\(p),"hero_probability_source":"blend",
                 "hero_probability_observed_at":"\(date)","blend_fold_revision":\(vector),
                 "win_probability_sources":{"polymarket":{"value":\(p),"updated_at":"\(date)"}}}
                """
            } else if request.url?.path == "/api/events/4242/history" {
                body = """
                {"event_id":4242,"home_team":"Home","away_team":"Away","status":"live","history":[],
                 "aggregate_line":[{"timestamp":"\(date)","home_probability":\(p)}],
                 "blend_edge_fold_revision":\(vector),"blend_edge_observed_at":"\(date)"}
                """
            } else { return (404, Data("{}".utf8)) }
            return (200, Data(body.utf8))
        }
        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            let (status, data) = Self.response(to: request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json", "Cache-Control": "max-age=60"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .allowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private final class Handle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var handlers: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) { handlers[event, default: []].append(handler) }
        func close() { isClosed = true }
        func fire(_ event: String, _ text: String = "") { for handler in handlers[event] ?? [] { handler(text) } }
        func pushNewRevision() {
            fire("probability", #"{"event_id":4242,"p":0.9,"source":"polymarket","source_value":0.55,"updated_at":"2026-09-27T17:00:01Z","status":"live","rev":{"4242":11}}"#)
        }
    }

    private func client() -> APIClient {
        Origin.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = URLCache(memoryCapacity: 1_000_000, diskCapacity: 0, diskPath: nil)
        return APIClient(session: URLSession(configuration: configuration))
    }
    private func model(_ client: APIClient, handle: Handle) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle },
            sleep: { _ in try? await Task.sleep(for: .seconds(60)) })
    }
    private func awaitReread() async throws {
        // Bounded transport completion; old cached implementation never reaches Origin again.
        for _ in 0..<100 {
            if Origin.requests(ending: "/4242").count >= 2 && Origin.requests(ending: "/history").count >= 2 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        try await Task.sleep(for: .milliseconds(30))
    }

    func testRevisionTriggerBypassesWarmAPICacheAndRefreshesPair() async throws {
        let api = client(), handle = Handle(), vm = model(api, handle: handle)
        defer { vm.stopRefresh() }
        await vm.load()
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.60)
        XCTAssertNil(vm.priceActivity)
        handle.fire("open")
        Origin.advance()
        // Ordinary reads intentionally remain cached; advancing Origin is not enough.
        let cached = try await api.fetchEvent(id: 4242)
        let cachedHistory = try await api.fetchEventHistory(id: 4242, hours: 168)
        XCTAssertEqual(cached.currentOdds?.homeProbability, 0.60)
        XCTAssertEqual(cachedHistory.aggregateLine?.last?.homeProbability, 0.60)
        XCTAssertEqual(Origin.requests(ending: "/4242").count, 1)
        XCTAssertEqual(Origin.requests(ending: "/history").count, 1)
        XCTAssertNil(Origin.requests(ending: "/4242").first?.url?.query)
        XCTAssertFalse(Origin.requests(ending: "/history").first?.url?.query?.contains("fresh") ?? false)

        handle.pushNewRevision()
        try await awaitReread()
        XCTAssertEqual(Origin.requests(ending: "/4242").count, 2, "a revision-triggered read must leave the device")
        XCTAssertEqual(Origin.requests(ending: "/history").count, 2, "history must not wait for its 60-second TTL")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.55)
        XCTAssertTrue(vm.streamHasPushedPrice)
        XCTAssertEqual(vm.priceActivity?.homeLabel, "55%")
        for request in Origin.requests(ending: "/4242").dropFirst() + Origin.requests(ending: "/history").dropFirst() {
            XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-cache")
            let query = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)?.queryItems ?? []
            XCTAssertEqual(query.first { $0.name == "fresh" }?.value, "true")
            if request.url?.path.hasSuffix("/history") == true {
                XCTAssertEqual(query.first { $0.name == "hours" }?.value, "168")
            }
        }
        // Fresh responses replace cached bytes, without disabling subsequent normal caching.
        let latest = try await api.fetchEvent(id: 4242)
        let latestHistory = try await api.fetchEventHistory(id: 4242, hours: 168)
        XCTAssertEqual(latest.currentOdds?.homeProbability, 0.55)
        XCTAssertEqual(latestHistory.aggregateLine?.last?.homeProbability, 0.55)
        XCTAssertEqual(Origin.requests(ending: "/4242").count, 2)
        XCTAssertEqual(Origin.requests(ending: "/history").count, 2)
        XCTAssertEqual(EventDetailViewModel.revisionRefetchWindow, 1)
    }

    func testFreshRequestStillRefusesCachedOrOldBackendRevision() async throws {
        let api = client(), handle = Handle(), vm = model(api, handle: handle)
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        // Origin deliberately keeps rev10: native cache bypass is NOT backend cache bypass.
        handle.pushNewRevision()
        try await awaitReread()
        XCTAssertEqual(Origin.requests(ending: "/4242").count, 2)
        XCTAssertEqual(Origin.requests(ending: "/history").count, 2)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.60)
        XCTAssertFalse(vm.streamHasPushedPrice)
        XCTAssertNil(vm.priceActivity, "network response arrival alone earns no new-price receipt")
    }
}
