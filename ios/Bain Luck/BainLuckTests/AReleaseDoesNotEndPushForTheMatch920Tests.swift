import XCTest
@testable import Bain_Luck

/// #836/#837/#920 — a release that cuts the live stream must cost the phone a
/// few seconds of push, not push for the rest of the match.
///
/// THE SPECIMEN (native/319, production, release v5007): the web dyno restarted,
/// every open stream ended with no `reconnect` frame, and the phone page fell
/// back to polling for 3 min+ with no return to push. The transport called the
/// cut closed-for-good, the controller's `stop()` is terminal, and the view
/// model only builds a controller when it has none — so nothing ever reopened.
/// Web recovers from the same cut because `EventSource` retries by itself; the
/// controller is a port of web's and assumed that transport.
///
/// TWO HALVES, BOTH DIRECTIONS (gotcha #43). The transport half runs a REAL
/// `URLSession` byte stream over a stubbed `URLProtocol`: a drop is retried, a
/// refusal is not. The controller half proves a retrying transport is waited
/// for, a half-open one is still retired, and the wait is bounded.
@MainActor
final class AReleaseDoesNotEndPushForTheMatch920Tests: XCTestCase {

    // MARK: - Controller half

    @MainActor private final class FakeHandle: LiveStreamHandle {
        private var handlers: [String: [@MainActor (String) -> Void]] = [:]
        private(set) var closeCount = 0
        var isClosed = false
        var isConnecting = false

        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            handlers[event, default: []].append(handler)
        }

        func close() {
            closeCount += 1
            isClosed = true
        }

        func fire(_ event: String, _ data: String = "") {
            for h in handlers[event] ?? [] { h(data) }
        }
    }

    @MainActor private final class Rig {
        var clock: TimeInterval = 1_000
        var handles: [FakeHandle] = []
        var delivering: [Bool] = []
        private(set) var controller: LiveStreamController!
        var current: FakeHandle { handles.last! }

        init() {
            controller = LiveStreamController(
                open: { [self] in
                    let h = FakeHandle()
                    handles.append(h)
                    return h
                },
                now: { [self] in clock },
                onFrame: { _ in },
                onDeliveringChange: { [self] d in delivering.append(d) }
            )
            controller.start()
        }

        func advance(_ seconds: TimeInterval) {
            clock += seconds
            controller.tick()
        }

        /// What the transport does when a release cuts the socket: it is still
        /// retrying, so it reports a blip and reads `isConnecting`.
        func drop() {
            current.isConnecting = true
            current.fire("error")
        }
    }

    func test_a_dropped_stream_that_the_transport_retries_comes_back_to_push() {
        let rig = Rig()
        rig.current.fire("open")
        XCTAssertEqual(rig.delivering, [true])

        rig.drop()
        XCTAssertEqual(rig.delivering, [true, false], "the drop must hand the page back to polling")
        XCTAssertFalse(rig.controller.state.stopped, "a drop the transport is retrying is not terminal")
        XCTAssertEqual(rig.current.closeCount, 0, "closing the handle would cancel the retry")

        // The retry lands a few seconds later on the SAME handle.
        rig.advance(5)
        rig.current.isConnecting = false
        rig.current.fire("open")
        XCTAssertEqual(rig.delivering, [true, false, true], "push must come BACK after the release")
        XCTAssertEqual(rig.controller.state.connections, 1, "the transport reconnected, not the controller")
    }

    func test_a_retrying_transport_outlives_the_60s_silence_budget() {
        let rig = Rig()
        rig.current.fire("open")
        rig.drop()

        // A slow release: 2 minutes of silence while the transport keeps trying.
        for _ in 0..<24 { rig.advance(LiveStreamTiming.tickInterval) }
        XCTAssertFalse(rig.controller.state.stopped,
                       "retired at \(LiveStreamTiming.silenceTimeout)s — the pre-fix behaviour")

        rig.current.isConnecting = false
        rig.current.fire("open")
        XCTAssertEqual(rig.delivering.last, true)
    }

    func test_the_wait_for_a_retrying_transport_is_bounded() {
        let rig = Rig()
        rig.current.fire("open")
        rig.drop()

        rig.advance(LiveStreamTiming.retryGiveUp - 1)
        XCTAssertFalse(rig.controller.state.stopped)
        rig.advance(2)
        XCTAssertTrue(rig.controller.state.stopped, "an unreachable server must not be retried all evening")
        XCTAssertEqual(rig.current.closeCount, 1, "retiring must close the handle, which ends its retry loop")
        XCTAssertEqual(rig.delivering.last, false)
    }

    func test_an_open_but_silent_socket_is_still_retired_at_the_silence_budget() {
        let rig = Rig()
        rig.current.fire("open")
        // Nothing is retrying a half-open socket; it will not change on its own.
        rig.advance(LiveStreamTiming.silenceTimeout + 1)
        XCTAssertTrue(rig.controller.state.stopped)
        XCTAssertEqual(rig.delivering, [true, false])
    }

    func test_a_refusal_is_still_terminal() {
        let rig = Rig()
        rig.current.isClosed = true
        rig.current.fire("error")
        XCTAssertTrue(rig.controller.state.stopped)
    }

    // MARK: - Transport half (a real URLSession byte stream)

    /// Serves scripted responses to `/api/events/*/stream`, one per request.
    private nonisolated final class StubStream: URLProtocol, @unchecked Sendable {
        struct Reply { let status: Int; let body: String }
        private static let lock = NSLock()
        nonisolated(unsafe) private static var replies: [Reply] = []
        nonisolated(unsafe) private static var served = 0

        static func script(_ r: [Reply]) {
            lock.lock(); defer { lock.unlock() }
            replies = r
            served = 0
        }

        static var requests: Int {
            lock.lock(); defer { lock.unlock() }
            return served
        }

        private static func next() -> Reply {
            lock.lock(); defer { lock.unlock() }
            let r = replies[min(served, replies.count - 1)]
            served += 1
            return r
        }

        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasSuffix("/stream") == true
        }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let reply = Self.next()
            let response = HTTPURLResponse(
                url: request.url!, statusCode: reply.status, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "text/event-stream"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(reply.body.utf8))
            // Finishing the load IS the cut: the body ends with no `closed` or
            // `reconnect` frame, exactly what a dyno restart leaves the client.
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private static let openThenPrice = """
    retry: 5000

    event: open
    data: {"event_id": 1}

    event: probability
    data: {"event_id": 1, "p": 0.55, "source": "polymarket", "source_value": 0.55, "updated_at": "2026-09-24T08:20:07Z", "status": "live"}


    """

    private func stubbedSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubStream.self]
        return URLSession(configuration: config)
    }

    private func waitUntil(_ seconds: TimeInterval, _ done: () -> Bool) async {
        let deadline = Date().addingTimeInterval(seconds)
        while !done(), Date() < deadline {
            try? await Task.sleep(nanoseconds: 20_000_000)
        }
    }

    func test_the_transport_reopens_a_stream_that_ended_unasked() async throws {
        StubStream.script([
            .init(status: 200, body: Self.openThenPrice),
            .init(status: 200, body: Self.openThenPrice),
        ])
        let transport = try LiveEventStreamTransport(
            eventId: 1, baseURL: "https://stub.invalid", session: stubbedSession(), retryDelay: 0.05
        )
        var events: [String] = []
        var connectingAtError: [Bool] = []
        for name in ["open", "probability", "error"] {
            transport.on(name) { _ in
                events.append(name)
                if name == "error" { connectingAtError.append(transport.isConnecting) }
            }
        }
        transport.connect()
        await waitUntil(5) { events.filter { $0 == "open" }.count >= 2 }
        transport.close()

        XCTAssertGreaterThanOrEqual(StubStream.requests, 2, "the cut was never retried — push is gone for the match")
        XCTAssertEqual(Array(events.prefix(4)), ["open", "probability", "error", "open"])
        XCTAssertEqual(connectingAtError.first, true,
                       "the drop must read as CONNECTING, or the controller calls it a death")
        XCTAssertFalse(transport.isConnecting, "closed is not connecting")
    }

    func test_the_transport_does_not_retry_a_refusal() async throws {
        StubStream.script([.init(status: 409, body: "")])
        let transport = try LiveEventStreamTransport(
            eventId: 1, baseURL: "https://stub.invalid", session: stubbedSession(), retryDelay: 0.05
        )
        var errors = 0
        transport.on("error") { _ in errors += 1 }
        transport.connect()
        await waitUntil(5) { errors > 0 }
        // Ten retry delays: long enough that a retry, if there were one, lands.
        try? await Task.sleep(nanoseconds: 500_000_000)

        XCTAssertEqual(errors, 1)
        XCTAssertTrue(transport.isClosed, "a 409 is the server saying no")
        XCTAssertFalse(transport.isConnecting)
        XCTAssertEqual(StubStream.requests, 1, "a refused endpoint must not be hammered")
    }

    func test_close_during_the_retry_wait_ends_the_loop() async throws {
        StubStream.script([.init(status: 200, body: Self.openThenPrice)])
        let transport = try LiveEventStreamTransport(
            eventId: 1, baseURL: "https://stub.invalid", session: stubbedSession(), retryDelay: 0.3
        )
        var errored = false
        transport.on("error") { _ in errored = true }
        transport.connect()
        await waitUntil(5) { errored }
        transport.close()
        try? await Task.sleep(nanoseconds: 600_000_000)

        XCTAssertEqual(StubStream.requests, 1, "a closed transport reopened behind the controller's back")
    }
}
