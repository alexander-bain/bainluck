import XCTest
import Foundation
@testable import Bain_Luck

/// A failed authoritative read must not publish half a pair or a fresh receipt.
/// Real APIClient + real URLSession dispatch; only the HTTP server is stubbed.
@MainActor
final class InterruptedPricePairRecovery837Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var revision = 10
        nonisolated(unsafe) private static var failedSuffix: String?
        nonisolated(unsafe) private static var captured: [URLRequest] = []

        static func reset() {
            lock.lock(); defer { lock.unlock() }
            revision = 10; captured = []; failedSuffix = nil
        }
        static func advance() {
            lock.lock(); defer { lock.unlock() }
            revision += 1
        }
        static func fail(_ suffix: String?) {
            lock.lock(); defer { lock.unlock() }; failedSuffix = suffix
        }
        static func requests(ending suffix: String) -> [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured.filter { $0.url?.path.hasSuffix(suffix) == true }
        }
        private static func response(to request: URLRequest) -> (Int, Data) {
            lock.lock(); defer { lock.unlock() }
            captured.append(request)
            if let failedSuffix, request.url?.path.hasSuffix(failedSuffix) == true { return (503, Data("{}".utf8)) }
            let p = revision == 10 ? 0.60 : (revision == 11 ? 0.55 : 0.52)
            let vector = "{\"4242\":\(revision),\"999\":5}"
            let date = "2026-09-27T17:00:0\(revision - 10)Z"
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
        func pushNewRevision(_ revision: Int = 11) {
            fire("probability", "{\"event_id\":4242,\"p\":0.9,\"source\":\"polymarket\",\"source_value\":0.52,\"updated_at\":\"2026-09-27T17:00:0\(revision - 10)Z\",\"status\":\"live\",\"rev\":{\"4242\":\(revision)}}")
        }

    }

    private func client() -> APIClient {
        Origin.reset()
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = URLCache(memoryCapacity: 1_000_000, diskCapacity: 0, diskPath: nil)
        return APIClient(session: URLSession(configuration: configuration))
    }
    private var clock: TimeInterval = 1_800_000_000
    private func model(_ client: APIClient, handle: Handle) -> EventDetailViewModel {
        EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle }, now: { [weak self] in self?.clock ?? 0 },
            sleep: { _ in try? await Task.sleep(for: .seconds(60)) })
    }
    private func awaitRequests(_ count: Int) async throws {
        for _ in 0..<200 {
            if Origin.requests(ending: "/4242").count >= count && Origin.requests(ending: "/history").count >= count { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        try await Task.sleep(for: .milliseconds(40))
        XCTAssertEqual(Origin.requests(ending: "/4242").count, count)
        XCTAssertEqual(Origin.requests(ending: "/history").count, count)
    }
    private nonisolated final class Ticker: @unchecked Sendable {
        private let lock = NSLock()
        private var waiters: [CheckedContinuation<Void, Never>] = []
        private var open = false
        func sleep(_ seconds: TimeInterval) async {
            if lock.withLock({ open }) {
                try? await Task.sleep(for: .milliseconds(50))
                return
            }
            await withCheckedContinuation { continuation in
                lock.lock()
                if open { lock.unlock(); continuation.resume() }
                else { waiters.append(continuation); lock.unlock() }
            }
        }
        func openGate() {
            lock.lock(); open = true
            let parked = waiters; waiters.removeAll(); lock.unlock()
            for continuation in parked { continuation.resume() }
        }
    }
    private func exerciseFailure(_ suffix: String, recoverByPoll: Bool = false) async throws {
        let api = client(), handle = Handle(), ticker = Ticker()
        let vm = recoverByPoll
            ? EventDetailViewModel(eventId: 4242, client: api, makeStreamHandle: { _ in handle },
                  now: { [weak self] in self?.clock ?? 0 }, sleep: { await ticker.sleep($0) })
            : model(api, handle: handle)
        defer { ticker.openGate() }
        defer { vm.stopRefresh() }
        await vm.load(); handle.fire("open")
        Origin.advance(); handle.pushNewRevision(); try await awaitRequests(2)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55)
        let previous = try XCTUnwrap(vm.priceActivity)
        Origin.advance(); Origin.fail(suffix); clock += 6
        handle.pushNewRevision(12); try await awaitRequests(3)
        XCTAssertEqual(vm.liveUpdateStatus, .interrupted,
                       "A failed authoritative price pair must not keep claiming live delivery")
        XCTAssertEqual(vm.priceActivity?.sequence, previous.sequence,
                       "Failed pair cannot earn a new-price receipt")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.55,
                       "Keep the last accepted complete pair during outage")
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.55)
        XCTAssertEqual(vm.currentRefreshPlan, .poll(every: 30), "Failed price delivery keeps the attentive fallback")
        Origin.fail(nil); clock += 6
        if recoverByPoll { ticker.openGate() }
        else { handle.pushNewRevision(12) }
        try await awaitRequests(4)
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability, 0.52)
        XCTAssertEqual(vm.history?.aggregateLine?.last?.homeProbability, 0.52)
        XCTAssertEqual(vm.liveUpdateStatus, .live)
        XCTAssertEqual(vm.priceActivity?.sequence, previous.sequence + 1)
    }
    func testFailedDetailIsHonestAndRecoversOnNextFrameWithoutRelaunch() async throws {
        try await exerciseFailure("/4242")
    }
    func testRestoredQuietConnectionRecoversOnExistingPollWithoutAnotherFrame() async throws {
        try await exerciseFailure("/history", recoverByPoll: true)
    }
    func testFailedHistoryCannotEarnReceiptAndRecoversWithoutRelaunch() async throws {
        try await exerciseFailure("/history")
    }
}
