import XCTest
import Foundation
@testable import Bain_Luck

/// #10090 — on a cold open the event page and its chart both asked for the same
/// 168h history ~0.3 s apart, and both reached the server (traced 03:29Z 10/5 on
/// KC–LV 14781710: two parallel cold reads, 4 s each, double the database work).
/// A history read now joins the one already on the wire; a reader that leaves
/// refuses the body without taking it away from a reader that stayed.
/// Real APIClient + real URLSession dispatch; only the HTTP server is stubbed,
/// and it holds every response until the test releases it.
final class APageAndItsChartShareOneHistoryRead10090Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var captured: [URLRequest] = []
        nonisolated(unsafe) private static var held: [Origin] = []
        nonisolated(unsafe) private static var status = 200

        static func reset(status: Int = 200) {
            lock.lock(); defer { lock.unlock() }
            captured = []; held = []; self.status = status
        }
        static func setStatus(_ value: Int) {
            lock.lock(); defer { lock.unlock() }
            status = value
        }
        static var requests: [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured
        }
        /// Answers every held request.
        static func release() {
            lock.lock()
            let waiting = held, code = status
            held = []
            lock.unlock()
            for origin in waiting { origin.answer(status: code) }
        }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            Self.lock.lock()
            Self.captured.append(request)
            Self.held.append(self)
            Self.lock.unlock()
        }
        override func stopLoading() {}

        private func answer(status: Int) {
            let hours = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?
                .queryItems?.first { $0.name == "hours" }?.value ?? "?"
            let isHistory = request.url?.path.hasSuffix("/history") == true
            let code = isHistory ? status : 404
            let body = code == 200 ? """
                {"event_id":4242,"home_team":"Home","away_team":"Away","status":"final","history":[],
                 "aggregate_line":[{"timestamp":"2026-10-05T03:00:00Z","home_probability":0.\(hours)}]}
                """ : "{}"
            let response = HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
    }

    override func setUp() {
        super.setUp()
        Origin.reset()
    }

    private func client() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = nil
        return APIClient(session: URLSession(configuration: configuration))
    }

    /// Waits until `count` requests have reached the server, then gives any
    /// further asker the same chance to arrive before answering.
    private func awaitRequests(_ count: Int) async throws {
        for _ in 0..<400 where Origin.requests.count < count {
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertGreaterThanOrEqual(Origin.requests.count, count, "the read never reached the stub server")
        try await Task.sleep(for: .milliseconds(150))
    }

    func testThePageAndTheChartAskingTogetherMakeOneServerRead() async throws {
        let api = client()
        async let page = api.fetchEventHistory(id: 4242, hours: 168)
        async let chart = api.fetchEventHistory(id: 4242, hours: 168)
        try await awaitRequests(1)
        XCTAssertEqual(Origin.requests.count, 1, "the second asker must join the read already on the wire")
        Origin.release()
        let (forPage, forChart) = try await (page, chart)
        XCTAssertEqual(forPage.aggregateLine?.last?.homeProbability, 0.168)
        XCTAssertEqual(forChart.aggregateLine?.last?.homeProbability, 0.168)
        XCTAssertEqual(Origin.requests.count, 1)

        // The finished read fills the ordinary TTL cache exactly as before.
        _ = try await api.fetchEventHistory(id: 4242, hours: 168)
        XCTAssertEqual(Origin.requests.count, 1)
    }

    func testAFreshReadNeverJoinsAnOrdinaryOne() async throws {
        let api = client()
        async let ordinary = api.fetchEventHistory(id: 4242, hours: 168)
        try await awaitRequests(1)
        async let fresh = api.fetchFreshEventHistory(id: 4242, hours: 168)
        try await awaitRequests(2)
        XCTAssertEqual(Origin.requests.count, 2, "a revalidation read exists to leave the device")
        Origin.release()
        _ = try await (ordinary, fresh)
        let freshQuery = Origin.requests.compactMap {
            URLComponents(url: $0.url!, resolvingAgainstBaseURL: false)?.queryItems?
                .first { $0.name == "fresh" }?.value
        }
        XCTAssertEqual(freshQuery, ["true"])
    }

    func testADifferentWindowIsADifferentRead() async throws {
        let api = client()
        async let week = api.fetchEventHistory(id: 4242, hours: 168)
        async let day = api.fetchEventHistory(id: 4242, hours: 24)
        try await awaitRequests(2)
        XCTAssertEqual(Origin.requests.count, 2)
        Origin.release()
        let (forWeek, forDay) = try await (week, day)
        XCTAssertEqual(forWeek.aggregateLine?.last?.homeProbability, 0.168)
        XCTAssertEqual(forDay.aggregateLine?.last?.homeProbability, 0.24)
    }

    func testAFailedSharedReadFailsBothAskersAndIsNotRemembered() async throws {
        Origin.reset(status: 503)
        let api = client()
        async let page = api.fetchEventHistory(id: 4242, hours: 168)
        async let chart = api.fetchEventHistory(id: 4242, hours: 168)
        try await awaitRequests(1)
        XCTAssertEqual(Origin.requests.count, 1)
        Origin.release()
        do {
            _ = try await page
            XCTFail("the page must see the server's refusal")
        } catch APIError.httpError(let code, _) {
            XCTAssertEqual(code, 503)
        }
        do {
            _ = try await chart
            XCTFail("the chart must see the server's refusal")
        } catch APIError.httpError(let code, _) {
            XCTAssertEqual(code, 503)
        }

        // The next ask goes back to the server instead of replaying the failure.
        Origin.setStatus(200)
        async let retry = api.fetchEventHistory(id: 4242, hours: 168)
        try await awaitRequests(2)
        Origin.release()
        let recovered = try await retry
        XCTAssertEqual(recovered.aggregateLine?.last?.homeProbability, 0.168)
        XCTAssertEqual(Origin.requests.count, 2)
    }

    // MARK: - A reader that leaves (independent review of f4c11baa99)

    private func read(_ api: APIClient, event: Int = 4242) -> Task<EventHistoryResponse, any Error> {
        Task { try await api.fetchEventHistory(id: event, hours: 168) }
    }

    private func assertRefusedAsCancelled(
        _ task: Task<EventHistoryResponse, any Error>, _ who: String,
        file: StaticString = #filePath, line: UInt = #line
    ) async {
        switch await task.result {
        case .success:
            XCTFail("the \(who) left but was handed the body", file: file, line: line)
        case .failure(APIError.networkError(let underlying)):
            XCTAssertEqual((underlying as? URLError)?.code, .cancelled,
                           "the \(who) must refuse the way a cancelled request always did", file: file, line: line)
        case .failure(let other):
            XCTFail("the \(who): \(other)", file: file, line: line)
        }
    }

    func testAJoinerThatLeavesRefusesWhileTheCreatorGetsTheBody() async throws {
        let api = client()
        let creator = read(api)
        try await awaitRequests(1)
        let joiner = read(api)
        try await Task.sleep(for: .milliseconds(150))
        joiner.cancel()
        Origin.release()
        let body = try await creator.value
        XCTAssertEqual(body.aggregateLine?.last?.homeProbability, 0.168)
        await assertRefusedAsCancelled(joiner, "joiner")
        XCTAssertEqual(Origin.requests.count, 1)
    }

    func testACreatorThatLeavesRefusesWhileTheJoinerGetsTheBody() async throws {
        let api = client()
        let creator = read(api)
        try await awaitRequests(1)
        let joiner = read(api)
        try await Task.sleep(for: .milliseconds(150))
        creator.cancel()
        try await Task.sleep(for: .milliseconds(50))
        XCTAssertEqual(Origin.requests.count, 1, "the creator leaving must not abort the joiner's transfer")
        Origin.release()
        let body = try await joiner.value
        XCTAssertEqual(body.aggregateLine?.last?.homeProbability, 0.168)
        await assertRefusedAsCancelled(creator, "creator")
        XCTAssertEqual(Origin.requests.count, 1)
    }

    /// Documented policy: when every reader leaves, the transfer settles and
    /// fills the ordinary TTL cache, and nothing stays pending.
    func testWhenEveryReaderLeavesTheBodyStillFillsTheCacheAndNothingStaysPending() async throws {
        let api = client()
        let first = read(api), second = read(api)
        try await awaitRequests(1)
        first.cancel(); second.cancel()
        Origin.release()
        await assertRefusedAsCancelled(first, "first reader")
        await assertRefusedAsCancelled(second, "second reader")
        let later = try await api.fetchEventHistory(id: 4242, hours: 168)
        XCTAssertEqual(later.aggregateLine?.last?.homeProbability, 0.168)
        XCTAssertEqual(Origin.requests.count, 1, "the settled body is the ordinary 60 s cache entry")
    }

    func testWhenEveryReaderLeavesAFailedReadIsNotRemembered() async throws {
        Origin.reset(status: 503)
        let api = client()
        let first = read(api), second = read(api)
        try await awaitRequests(1)
        first.cancel(); second.cancel()
        Origin.release()
        await assertRefusedAsCancelled(first, "first reader")
        await assertRefusedAsCancelled(second, "second reader")

        Origin.setStatus(200)
        let retry = read(api)
        try await awaitRequests(2)
        Origin.release()
        let body = try await retry.value
        XCTAssertEqual(body.aggregateLine?.last?.homeProbability, 0.168)
        XCTAssertEqual(Origin.requests.count, 2)
    }

    func testAnotherEventIsAnotherRead() async throws {
        let api = client()
        let one = read(api, event: 4242), other = read(api, event: 4243)
        try await awaitRequests(2)
        XCTAssertEqual(Origin.requests.count, 2)
        Origin.release()
        _ = try await (one.value, other.value)
        XCTAssertEqual(Set(Origin.requests.compactMap { $0.url?.path }),
                       ["/api/events/4242/history", "/api/events/4243/history"])
    }

    func testAnotherAccountNeverJoinsTheFirstAccountsRead() async throws {
        let persisted = APIClient.persistedLastKnownUserId()
        defer { APIClient.setPersistedLastKnownUserId(persisted) }
        let api = client()
        await api.setFeedCacheIdentity(userId: nil)
        let signedOut = read(api)
        try await awaitRequests(1)
        await api.setFeedCacheIdentity(userId: "user-10090")
        let signedIn = read(api)
        try await awaitRequests(2)
        XCTAssertEqual(Origin.requests.count, 2, "a read under another principal must leave the device")
        Origin.release()
        _ = try await (signedOut.value, signedIn.value)
    }

    func testOnlyHistoryReadsShare() async throws {
        let api = client()
        async let page = try? api.fetchEvent(id: 4242)
        async let again = try? api.fetchEvent(id: 4242)
        try await awaitRequests(2)
        XCTAssertEqual(Origin.requests.count, 2, "sharing is scoped to the history resource")
        Origin.release()
        _ = await (page, again)
    }
}
