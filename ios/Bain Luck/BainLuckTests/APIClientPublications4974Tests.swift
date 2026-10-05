import Foundation
import XCTest
@testable import Bain_Luck

/// #4974 — `APIClient.fetchEventPublications(id:)` carries
/// `GET /api/events/{id}/publications` to the iPhone chart and nothing more.
/// Real APIClient + real URLSession; only the server is stubbed, through a
/// test-local URLProtocol on an ephemeral session (no global registration, no
/// network). Eligibility of a decoded body is `PublicationJourney4974Tests`'.
@MainActor
final class APIClientPublications4974Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        enum Reply {
            case serve(status: Int, body: Data)
            case fail(URLError.Code)
            /// Never answers, so the request is in flight when the task is cancelled.
            case hold
        }

        private static let lock = NSLock()
        nonisolated(unsafe) private static var reply = Reply.hold
        nonisolated(unsafe) private static var captured: [URLRequest] = []
        nonisolated(unsafe) private static var stopped = 0

        static func reset(_ next: Reply) {
            lock.lock(); defer { lock.unlock() }
            reply = next; captured = []; stopped = 0
        }
        static func replace(_ next: Reply) {
            lock.lock(); defer { lock.unlock() }
            reply = next
        }
        static var requests: [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured
        }
        static var stopCount: Int {
            lock.lock(); defer { lock.unlock() }
            return stopped
        }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            Self.lock.lock()
            Self.captured.append(request)
            let next = Self.reply
            Self.lock.unlock()
            switch next {
            case .serve(let status, let body):
                // The route's real header: without the client's revalidation a
                // URLCache would answer the second read from the first body.
                let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
                    headerFields: ["Content-Type": "application/json", "Cache-Control": "public, max-age=60"])!
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .allowed)
                client?.urlProtocol(self, didLoad: body)
                client?.urlProtocolDidFinishLoading(self)
            case .fail(let code):
                client?.urlProtocol(self, didFailWithError: URLError(code))
            case .hold:
                break
            }
        }
        override func stopLoading() {
            Self.lock.lock(); defer { Self.lock.unlock() }
            Self.stopped += 1
        }
    }

    private func client(_ reply: Origin.Reply) -> APIClient {
        Origin.reset(reply)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = URLCache(memoryCapacity: 1_000_000, diskCapacity: 0, diskPath: nil)
        return APIClient(session: URLSession(configuration: configuration))
    }

    /// The served body, byte-for-byte the shape `publications_body` returns.
    private static func body(eventId: Int = 4242, truncated: Bool = false, vertices: String = "[]") -> Data {
        Data("""
        {"event_id":\(eventId),"schema_version":1,"time_basis":"recorded_at_insert_before_commit",\
        "truncated":\(truncated),"vertices":\(vertices)}
        """.utf8)
    }

    private static let recorded = """
    [{"rev":7,"t":"2026-10-03T23:41:07.123456+00:00","p":0.6125},\
    {"rev":4294967297,"t":"2026-10-03T23:41:09+00:00","p":0.0},\
    {"rev":9223372036854775807,"t":"2026-10-04T02:10:00.5+00:00","p":1.0}]
    """

    // MARK: - Request

    func testReadIsAGetOfTheEventsPublicationsPathWithTheAppHeaders() async throws {
        let api = client(.serve(status: 200, body: Self.body()))
        _ = try await api.fetchEventPublications(id: 4242)

        let request = try XCTUnwrap(Origin.requests.first)
        XCTAssertEqual(Origin.requests.count, 1)
        XCTAssertEqual(request.httpMethod, "GET")
        XCTAssertEqual(request.url?.scheme, "https")
        XCTAssertEqual(request.url?.host, "api.bainluck.com")
        XCTAssertEqual(request.url?.path, "/api/events/4242/publications")
        XCTAssertNil(request.url?.query, "no hours, no fresh: the route takes no query")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/json")
        let sessionId = try XCTUnwrap(UserDefaults.standard.string(forKey: APIClient.sessionIdDefaultsKey))
        XCTAssertFalse(sessionId.isEmpty)
        XCTAssertEqual(request.value(forHTTPHeaderField: "x-session-id"), sessionId)
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"), "anonymous reads carry no bearer")
    }

    func testSignedInReadCarriesTheSessionBearer() async throws {
        let api = client(.serve(status: 200, body: Self.body()))
        await api.setAuthTokenProvider { "token-4974" }
        _ = try await api.fetchEventPublications(id: 4242)
        XCTAssertEqual(Origin.requests.first?.value(forHTTPHeaderField: "Authorization"), "Bearer token-4974")
    }

    func testEveryReadRevalidatesPastTheDeviceCache() async throws {
        let api = client(.serve(status: 200, body: Self.body()))
        _ = try await api.fetchEventPublications(id: 4242)
        _ = try await api.fetchEventPublications(id: 4242)
        XCTAssertEqual(Origin.requests.count, 2)
        for request in Origin.requests {
            XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cache-Control"), "no-cache")
        }
    }

    func testRepeatedReadsEachReachTheServerAndReturnTheNewerBody() async throws {
        // Recording off, then the game's rows land: the second read must not be the first body.
        let api = client(.serve(status: 200, body: Self.body()))
        let before = try await api.fetchEventPublications(id: 4242)
        XCTAssertEqual(before.vertices, [])

        Origin.replace(.serve(status: 200, body: Self.body(vertices: Self.recorded)))
        let after = try await api.fetchEventPublications(id: 4242)
        XCTAssertEqual(after.vertices.count, 3)
        XCTAssertEqual(Origin.requests.count, 2, "no TTL and no URLCache hit: both reads leave the device")

        let sessionIds = Origin.requests.map { $0.value(forHTTPHeaderField: "x-session-id") }
        XCTAssertEqual(Set(sessionIds).count, 1, "one client, one session id")
    }

    func testEachEventIdReadsItsOwnPath() async throws {
        let api = client(.serve(status: 200, body: Self.body(eventId: 15313111)))
        let response = try await api.fetchEventPublications(id: 15313111)
        XCTAssertEqual(response.eventId, 15313111)
        XCTAssertEqual(Origin.requests.first?.url?.path, "/api/events/15313111/publications")
    }

    // MARK: - Body

    func testDecodesTheServedSnakeCaseBodyVerbatimWithInt64Revisions() async throws {
        let api = client(.serve(status: 200, body: Self.body(vertices: Self.recorded)))
        let response = try await api.fetchEventPublications(id: 4242)

        XCTAssertEqual(response.eventId, 4242)
        XCTAssertEqual(response.schemaVersion, 1)
        XCTAssertEqual(response.timeBasis, "recorded_at_insert_before_commit")
        XCTAssertFalse(response.truncated)
        XCTAssertEqual(response.vertices, [
            PublicationCheckpointVertex(rev: 7, t: "2026-10-03T23:41:07.123456+00:00", p: 0.6125),
            PublicationCheckpointVertex(rev: 4_294_967_297, t: "2026-10-03T23:41:09+00:00", p: 0.0),
            PublicationCheckpointVertex(rev: Int64.max, t: "2026-10-04T02:10:00.5+00:00", p: 1.0),
        ], "server order, rev past Int32 and at Int64.max exact, t untouched, p untouched")
    }

    func testRecordingOffIsAnEmptyBodyNotAnError() async throws {
        let api = client(.serve(status: 200, body: Self.body()))
        let off = try await api.fetchEventPublications(id: 4242)
        XCTAssertEqual(off.vertices, [])
        XCTAssertFalse(off.truncated)

        Origin.replace(.serve(status: 200, body: Self.body(truncated: true)))
        let capped = try await api.fetchEventPublications(id: 4242)
        XCTAssertEqual(capped.vertices, [])
        XCTAssertTrue(capped.truncated, "the cap flag rides through for adoption to read")
    }

    // MARK: - Errors

    func testNonSuccessStatusThrowsTheStatusAndTheBody() async throws {
        for (status, text) in [(404, #"{"detail":"Event not found"}"#), (500, "Internal Server Error"), (503, "")] {
            let api = client(.serve(status: status, body: Data(text.utf8)))
            do {
                _ = try await api.fetchEventPublications(id: 4242)
                XCTFail("\(status) must throw, never decode into an empty recording")
            } catch let error as APIError {
                guard case .httpError(let code, let body) = error else {
                    return XCTFail("\(status) became \(error)")
                }
                XCTAssertEqual(code, status)
                XCTAssertEqual(body, text)
                XCTAssertFalse(error.isCancellation)
            }
        }
    }

    func testUndecodableBodiesThrowDecodingError() async throws {
        let vertex = { (rev: String, p: String) in Self.body(vertices: #"[{"rev":\#(rev),"t":"2026-10-03T23:41:07+00:00","p":\#(p)}]"#) }
        let cases: [(String, Data)] = [
            ("empty body", Data()),
            ("html", Data("<html>bad gateway</html>".utf8)),
            ("missing vertices", Data(#"{"event_id":4242,"schema_version":1,"time_basis":"x","truncated":false}"#.utf8)),
            ("rev as string", vertex(#""7""#, "0.5")),
            ("fractional rev", vertex("7.5", "0.5")),
            ("rev past Int64", vertex("9223372036854775808", "0.5")),
            ("null p", vertex("7", "null")),
        ]
        for (name, data) in cases {
            let api = client(.serve(status: 200, body: data))
            do {
                _ = try await api.fetchEventPublications(id: 4242)
                XCTFail("\(name) must not decode")
            } catch let error as APIError {
                guard case .decodingError = error else { return XCTFail("\(name) became \(error)") }
            }
        }
    }

    func testCancelledReadIsRecognizedAsCancellation() async throws {
        let api = client(.hold)
        let task = Task { try await api.fetchEventPublications(id: 4242) }
        // Bounded: the loader thread, not this one, records the request.
        for _ in 0..<400 {
            if !Origin.requests.isEmpty { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertEqual(Origin.requests.count, 1, "the request must be in flight before the cancel")
        task.cancel()
        do {
            _ = try await task.value
            XCTFail("a cancelled read must throw")
        } catch let error as APIError {
            XCTAssertTrue(error.isCancellation, "got \(error)")
        }
        // stopLoading may land after the throw; wait for it the same bounded way.
        for _ in 0..<400 {
            if Origin.stopCount > 0 { break }
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertEqual(Origin.stopCount, 1, "the cancel reaches the transport")
    }

    func testOfflineIsANetworkErrorThatIsNotCancellation() async throws {
        let api = client(.fail(.notConnectedToInternet))
        do {
            _ = try await api.fetchEventPublications(id: 4242)
            XCTFail("offline must throw")
        } catch let error as APIError {
            guard case .networkError = error else { return XCTFail("offline became \(error)") }
            XCTAssertFalse(error.isCancellation, "only a cancel may be dropped silently")
        }
    }
}
