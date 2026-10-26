import XCTest
@testable import Bain_Luck

/// #10090 — the real `LiveEventStreamTransport` turns bytes into frames the same
/// way however the bytes are chunked, hands every frame to its handlers exactly
/// once, in order, on the main thread, and hands nothing on after it is closed.
///
/// The bytes travel over a real `URLSession` byte stream through a stubbed
/// `URLProtocol`, the `AReleaseDoesNotEndPushForTheMatch920Tests` seam. Those
/// tests already cover the drop, retry, refusal and close-during-wait
/// lifecycle; these cover frame assembly and delivery.
@MainActor
final class SSEFrameAssemblyOverTheRealTransport10090Tests: XCTestCase {

    /// Serves one scripted body per request in chunks of `chunkSize` bytes,
    /// `interval` apart, then finishes the load (`finish`) or leaves it open.
    private nonisolated final class ChunkedStream: URLProtocol, @unchecked Sendable {
        struct Reply { let body: Data; let chunkSize: Int; let interval: TimeInterval; let finish: Bool }
        private static let lock = NSLock()
        nonisolated(unsafe) private static var replies: [Reply] = []
        nonisolated(unsafe) private static var served = 0
        nonisolated(unsafe) private static var urls: [URL] = []
        private let queue = DispatchQueue(label: "chunked-stream")
        private var stopped = false

        static func script(_ r: [Reply]) { lock.lock(); replies = r; served = 0; urls = []; lock.unlock() }
        static var requests: Int { lock.lock(); defer { lock.unlock() }; return served }
        static var requestedURLs: [URL] { lock.lock(); defer { lock.unlock() }; return urls }
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
            Self.lock.lock()
            if let url = request.url { Self.urls.append(url) }
            Self.lock.unlock()
            let reply = Self.next()
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "text/event-stream"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            let chunks = stride(from: 0, to: reply.body.count, by: reply.chunkSize).map {
                reply.body.subdata(in: $0..<min($0 + reply.chunkSize, reply.body.count))
            }
            let start = DispatchTime.now()
            for (i, chunk) in chunks.enumerated() {
                queue.asyncAfter(deadline: start + reply.interval * Double(i)) { [self] in
                    guard !stopped else { return }
                    client?.urlProtocol(self, didLoad: chunk)
                }
            }
            if reply.finish {
                queue.asyncAfter(deadline: start + reply.interval * Double(chunks.count)) { [self] in
                    guard !stopped else { return }
                    client?.urlProtocolDidFinishLoading(self)
                }
            }
        }

        override func stopLoading() { queue.async { [self] in stopped = true } }
    }

    private func session() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ChunkedStream.self]
        return URLSession(configuration: config)
    }

    private func waitUntil(_ seconds: TimeInterval, _ done: () -> Bool) async {
        let deadline = Date().addingTimeInterval(seconds)
        while !done(), Date() < deadline { try? await Task.sleep(nanoseconds: 10_000_000) }
    }

    private struct Delivery: Equatable { let event: String; let data: String }

    private static let names = ["open", "probability", "folded_probability", "resync", "heartbeat",
                                "closed", "reconnect", "error"]

    /// Records every handler call and whether it ran on the main thread.
    private func record(_ transport: LiveEventStreamTransport, into log: @escaping (Delivery, Bool) -> Void) {
        for name in Self.names {
            transport.on(name) { data in log(Delivery(event: name, data: data), Thread.isMainThread) }
        }
    }

    // MARK: - Assembly

    /// Every SSE shape the server sends or the format allows: the `retry:` hint,
    /// a comment, keep-alive blank lines, a CRLF frame, a heartbeat, multi-line
    /// data, a name with no data, and multi-byte UTF-8 that a one-byte chunking
    /// splits mid-character.
    private static let body = Data([
        "retry: 5000\n\n",
        ": a comment line\n\n",
        "event: open\ndata: {\"event_id\": 1}\n\n",
        "\n\n",
        "event: probability\r\ndata: {\"p\": 0.55, \"name\": \"Świątek — Zheng ✓\"}\r\n\r\n",
        "event: heartbeat\ndata: {}\n\n",
        "event: probability\ndata: line one\ndata:  line two keeps one space\n\n",
        "event: resync\n\n",
        "data: an unnamed frame\n\n",
        "event: probability\ndata: {\"p\": 0.56, \"emoji\": \"🎾\"}\n\n",
    ].joined().utf8)

    private static let expected: [Delivery] = [
        .init(event: "open", data: #"{"event_id": 1}"#),
        .init(event: "probability", data: #"{"p": 0.55, "name": "Świątek — Zheng ✓"}"#),
        .init(event: "heartbeat", data: "{}"),
        .init(event: "probability", data: "line one\n line two keeps one space"),
        .init(event: "resync", data: ""),
        // An unnamed frame is a `message`, which nothing here listens to.
        .init(event: "probability", data: #"{"p": 0.56, "emoji": "🎾"}"#),
        // The load finishing with no `closed` frame is a drop.
        .init(event: "error", data: ""),
    ]

    func testEveryChunkingOfTheSameBytesDeliversTheSameFramesOnceInOrderOnMain() async throws {
        for size in [1, 2, 3, 7, 64, Self.body.count] {
            ChunkedStream.script([.init(body: Self.body, chunkSize: size, interval: 0.001, finish: true)])
            // A long retry delay, so the drop is reported and nothing is reopened
            // inside the window.
            let transport = try LiveEventStreamTransport(eventId: 1, baseURL: "https://stub.invalid",
                                                         session: session(), retryDelay: 30)
            var got: [Delivery] = []
            var offMain = 0
            record(transport) { d, main in got.append(d); if !main { offMain += 1 } }
            transport.connect()
            await waitUntil(10) { got.last?.event == "error" }
            try? await Task.sleep(nanoseconds: 100_000_000)
            transport.close()

            XCTAssertEqual(got, Self.expected, "chunk size \(size)")
            XCTAssertEqual(offMain, 0, "chunk size \(size): a handler ran off the main thread")
            XCTAssertEqual(ChunkedStream.requests, 1, "chunk size \(size)")
        }
    }

    // MARK: - Delivery after close

    /// A `closed` frame closes the transport from inside its handler. The frames
    /// that arrived in the same chunk behind it are not delivered.
    func testAFrameWhoseHandlerClosesTheTransportIsTheLastOneDelivered() async throws {
        let body = Data([
            "event: open\ndata: {}\n\n",
            "event: closed\ndata: {}\n\n",
            "event: probability\ndata: {\"p\": 0.5}\n\n",
            "event: probability\ndata: {\"p\": 0.6}\n\n",
        ].joined().utf8)
        ChunkedStream.script([.init(body: body, chunkSize: body.count, interval: 0, finish: false)])
        let transport = try LiveEventStreamTransport(eventId: 1, baseURL: "https://stub.invalid",
                                                     session: session(), retryDelay: 30)
        var got: [String] = []
        record(transport) { d, _ in
            got.append(d.event)
            if d.event == "closed" { transport.close() }
        }
        transport.connect()
        await waitUntil(5) { got.contains("closed") }
        try? await Task.sleep(nanoseconds: 300_000_000)

        XCTAssertEqual(got, ["open", "closed"])
        XCTAssertTrue(transport.isClosed)
        XCTAssertEqual(ChunkedStream.requests, 1)
    }

    /// A transport closed mid-stream, as the controller closes the old one when
    /// it rolls over, hands its handlers nothing more. Its replacement on the same
    /// session gets its own stream from the start, once.
    func testAClosedTransportHandsNothingOnAndItsReplacementStartsClean() async throws {
        var body = Data("event: open\ndata: {}\n\n".utf8)
        for i in 0..<40 { body += Data("event: probability\ndata: {\"n\": \(i)}\n\n".utf8) }
        let frameBytes = Data("event: probability\ndata: {\"n\": 0}\n\n".utf8).count
        let reply = ChunkedStream.Reply(body: body, chunkSize: frameBytes, interval: 0.02, finish: false)
        ChunkedStream.script([reply, reply])
        let shared = session()

        let old = try LiveEventStreamTransport(eventId: 1, baseURL: "https://stub.invalid", session: shared, retryDelay: 30)
        var oldGot: [Delivery] = []
        record(old) { d, _ in oldGot.append(d) }
        old.connect()
        await waitUntil(5) { oldGot.filter { $0.event == "probability" }.count >= 3 }
        // `waitUntil` only stops waiting. Without this an old stream that never
        // delivered would pass every assertion below.
        XCTAssertGreaterThanOrEqual(oldGot.filter { $0.event == "probability" }.count, 3,
                                    "the old transport delivered frames before it was closed")
        old.close()
        let atClose = oldGot

        let replacement = try LiveEventStreamTransport(eventId: 1, baseURL: "https://stub.invalid",
                                                       session: shared, retryDelay: 30)
        var newGot: [Delivery] = []
        record(replacement) { d, _ in newGot.append(d) }
        replacement.connect()
        await waitUntil(5) { newGot.filter { $0.event == "probability" }.count >= 5 }
        try? await Task.sleep(nanoseconds: 300_000_000)
        replacement.close()
        // An empty replacement list would equal the empty sequence built from it.
        XCTAssertGreaterThanOrEqual(newGot.filter { $0.event == "probability" }.count, 5,
                                    "the replacement delivered frames of its own")

        XCTAssertEqual(oldGot, atClose, "the closed transport handed on frames after close()")
        XCTAssertFalse(oldGot.contains { $0.event == "error" }, "a close is not a drop")
        XCTAssertEqual(newGot.first?.event, "open")
        let numbers = newGot.filter { $0.event == "probability" }.map(\.data)
        XCTAssertEqual(numbers, (0..<numbers.count).map { #"{"n": \#($0)}"# },
                       "the replacement delivers its own frames from the first, once each, in order")
        XCTAssertEqual(ChunkedStream.requests, 2)
    }
    /// #11564: the page asks for v3 only — never the legacy folded-v2 previews.
    func testAuthorityV3CapabilityIsExplicitAndDefaultIsUnchanged() async throws {
        for enabled in [false, true] {
            ChunkedStream.script([.init(body: Data("event: heartbeat\ndata: {}\n\n".utf8),
                                        chunkSize: 64, interval: 0, finish: false)])
            let transport = try LiveEventStreamTransport(eventId: 4242, authorityPreviews: enabled,
                baseURL: "https://stub.invalid", session: session())
            transport.connect()
            await waitUntil(1) { !ChunkedStream.requestedURLs.isEmpty }
            transport.close()
            let url = try XCTUnwrap(ChunkedStream.requestedURLs.first)
            XCTAssertEqual(url.path, "/api/events/4242/stream")
            XCTAssertEqual(url.query, enabled ? "preview_protocol=authority-v3" : nil)
        }
    }

    /// #11564: a handler can read when its frame finished assembling, on the
    /// monotonic clock and before it ran — and only while it runs.
    func testAHandlerReadsItsFramesMonotonicReceipt() async throws {
        ChunkedStream.script([.init(body: Data("event: heartbeat\ndata: {}\n\n".utf8),
                                    chunkSize: 64, interval: 0, finish: false)])
        let transport = try LiveEventStreamTransport(eventId: 4242, authorityPreviews: true,
            baseURL: "https://stub.invalid", session: session())
        var receipts: [(TimeInterval?, TimeInterval)] = []
        transport.on("heartbeat") { _ in
            receipts.append((transport.frameReceivedAt, ProcessInfo.processInfo.systemUptime))
        }
        transport.connect()
        await waitUntil(1) { !receipts.isEmpty }
        transport.close()
        let (receipt, ran) = try XCTUnwrap(receipts.first)
        let at = try XCTUnwrap(receipt, "the frame being handled carries its receipt")
        XCTAssertLessThanOrEqual(at, ran, "taken before the handler ran")
        XCTAssertNil(transport.frameReceivedAt, "and cleared once it returned")
    }

}
