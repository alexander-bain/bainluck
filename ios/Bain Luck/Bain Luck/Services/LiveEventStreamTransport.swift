import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "liveStream")

/// The real SSE connection behind `LiveStreamController` (#2687).
///
/// Apple ships no `EventSource`, so the wire format is parsed here: a line
/// reader over `URLSession.bytes(for:)`, accumulating `event:` and `data:` lines
/// and dispatching a complete frame on the blank line that ends it.
///
/// WHAT IT DELIBERATELY DOES NOT DO — decide when to give up, back off, or
/// interpret `reconnect`. All of that is `LiveStreamController`'s, and the
/// separation is the point: the lifecycle is the part that had two P1 defects on
/// web (CERT-717) and the part a test must be able to drive without a socket.
///
/// WHAT IT DOES DO, BECAUSE `EventSource` DOES (#920): a connection that DROPS —
/// the byte stream ends, or the network errors, with no `closed`/`reconnect`
/// frame — is retried after `retryDelay`, and `isConnecting` reads true until
/// the next 200. ONE EXCEPTION (#10090): the FIRST failure of a run waits only
/// `firstRetryDelay`. A run starts at `connect()` and again after a connection
/// that stayed up at least `retryDelay`; every later failure in it waits the full
/// `retryDelay`. A release that ends a healthy stream otherwise cost five seconds
/// of quotes (revs 1871–1875, 2026-10-12): the server replays only the latest
/// frame on connect, never the ones published while the page was waiting. And a
/// page's first connection that answered 200 with zero bytes (event 15329925,
/// 2026-10-14, the server's first Redis SUBSCRIBE reset) waited the same five
/// seconds for its first streamed probability.
///
/// The controller's lifecycle is a port of web's, and web's assumes a transport
/// that reconnects underneath it: the browser does exactly this, which is why a
/// release that restarts the web dyno costs a web reader a few seconds of push. This transport used to call that same cut closed-for-
/// good, the controller's `stop()` is terminal, and a phone page polled for the
/// rest of the match (native/319, release v5007). The controller still owns the
/// ending: it retires a transport that stays silent past `retryGiveUp`, and its
/// `close()` cancels a retry mid-wait.
///
/// HTTP STATUS IS A REFUSAL, NOT A RETRY. 409 (event not live), 503 (at
/// capacity) and 404 are the server saying no. The transport reports the error
/// once, the controller stops, and the caller polls. Hammering an endpoint that
/// has already refused is the failure this avoids.
/// The SSE wire format, as a pure line-fed state machine.
///
/// Lifted out of the connection for the same reason `LiveStreamController` is
/// lifted out of the hook: this is LOGIC, and logic welded to a socket cannot be
/// proved without one. A parser that dropped the `event:` name, or ate the
/// leading space after a colon, or fired on a `retry:` line, would produce a
/// stream that "connects" and delivers nothing — and no integration test short
/// of a live match would catch it.
nonisolated struct SSEFrameParser {
    private var eventName = "message"
    private var data = ""

    /// Feed one line. Returns a completed frame on the blank line that ends one.
    mutating func feed(_ line: String) -> (event: String, data: String)? {
        if line.isEmpty {
            // A blank line terminates one SSE frame. A frame with neither a name
            // nor a payload is the keep-alive shape and carries nothing.
            let done = (!data.isEmpty || eventName != "message")
                ? (event: eventName, data: data)
                : nil
            eventName = "message"
            data = ""
            return done
        }
        // A comment line. The server sends none today, but the format allows
        // them and treating one as a field would corrupt the frame around it.
        if line.hasPrefix(":") { return nil }

        guard let colon = line.firstIndex(of: ":") else { return nil }
        let field = String(line[line.startIndex..<colon])
        var value = String(line[line.index(after: colon)...])
        // Exactly ONE leading space is part of the framing, not the value. Any
        // beyond it belong to the payload.
        if value.hasPrefix(" ") { value.removeFirst() }

        switch field {
        case "event":
            eventName = value
        case "data":
            // Multi-line `data:` is concatenated with newlines, per the spec.
            // The server sends one line today; a JSON payload that ever grew a
            // newline would otherwise silently lose half of itself.
            data = data.isEmpty ? value : data + "\n" + value
        default:
            // `retry:` is the browser's reconnect hint, and `id:` is resumption
            // state neither side uses. Read and ignored: `LiveStreamController`
            // owns reconnection, and two things deciding it is worse than one.
            break
        }
        return nil
    }
}

@MainActor
final class LiveEventStreamTransport: LiveStreamHandle {

    private let url: URL
    private let session: URLSession
    private var task: Task<Void, Never>?
    private var handlers: [String: [@MainActor (String) -> Void]] = [:]
    private var closed = false
    private var connecting = true
    private let retryDelay: TimeInterval
    private let firstRetryDelay: TimeInterval

    /// The wait before re-opening a dropped connection. The server's own
    /// `retry:` field (`SSE_RETRY_MS`, 5000), which is what a browser waits.
    nonisolated static let defaultRetryDelay: TimeInterval = 5

    /// The wait before re-opening after the first failure of a run, plus up to
    /// the same again of jitter so every phone on a restarted dyno does not
    /// arrive in the same instant. Once per run: a second connection that answers
    /// 200 and ends at once is retried no faster than `retryDelay` — never a
    /// hammer. Only a connection that stayed up at least `retryDelay` starts a
    /// new run.
    nonisolated static let defaultFirstRetryDelay: TimeInterval = 0.25

    var isClosed: Bool { closed }
    /// `EventSource.readyState == CONNECTING`: before the first 200, and again
    /// from a drop until the retry's 200.
    var isConnecting: Bool { !closed && connecting }

    convenience init(
        eventId: Int,
        foldedPreviews: Bool = false,
        baseURL: String = "https://api.bainluck.com",
        session: URLSession? = nil,
        retryDelay: TimeInterval = LiveEventStreamTransport.defaultRetryDelay,
        firstRetryDelay: TimeInterval = LiveEventStreamTransport.defaultFirstRetryDelay
    ) throws {
        let capability = foldedPreviews ? "?preview_protocol=folded-v2" : ""
        guard let url = URL(string: "\(baseURL)/api/events/\(eventId)/stream\(capability)") else {
            throw URLError(.badURL)
        }
        self.init(url: url, session: session, retryDelay: retryDelay, firstRetryDelay: firstRetryDelay)
    }

    /// Reuse the same SSE transport for bounded market invalidation streams.
    /// The event initializer above retains its existing URL and behavior.
    init(url: URL, session: URLSession? = nil,
         retryDelay: TimeInterval = LiveEventStreamTransport.defaultRetryDelay,
         firstRetryDelay: TimeInterval = LiveEventStreamTransport.defaultFirstRetryDelay) {
        self.url = url
        self.retryDelay = retryDelay
        self.firstRetryDelay = min(firstRetryDelay, retryDelay)
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.default
            // NO RESOURCE TIMEOUT. A stream is supposed to stay open for its
            // full `SSE_MAX_CONNECTION_S` (900s); the app's default 60s resource
            // timeout would kill every connection at one minute and turn the
            // whole feature into a reconnect loop. The controller's own silence
            // watchdog is what detects a dead stream, and it can tell silence
            // from a healthy quiet market — a socket timeout cannot.
            config.timeoutIntervalForRequest = 0
            config.timeoutIntervalForResource = 0
            config.requestCachePolicy = .reloadIgnoringLocalCacheData
            self.session = URLSession(configuration: config)
        }
    }

    func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
        handlers[event, default: []].append(handler)
    }

    func close() {
        closed = true
        task?.cancel()
        task = nil
    }

    /// Open the connection and pump frames until it is refused, closed, or
    /// cancelled — re-opening after `firstRetryDelay` on the first failure of a
    /// run, and after `retryDelay` on every later one.
    func connect() {
        guard task == nil, !closed else { return }
        let delay = retryDelay
        let first = firstRetryDelay
        task = Task { [weak self] in
            // The first attempt starts a run, so its failure is the run's first.
            var quickRetryLeft = true
            // `self` is held only for the length of one connection, never across
            // the wait: an owner that walked away without `close()` leaves a
            // loop that ends at its next turn instead of retrying forever.
            while !Task.isCancelled {
                guard let outcome = await self?.pump(), case .dropped(let healthy) = outcome else { return }
                if healthy { quickRetryLeft = true }
                let wait = quickRetryLeft ? first * Double.random(in: 1...2) : delay
                quickRetryLeft = false
                try? await Task.sleep(nanoseconds: UInt64(wait * 1_000_000_000))
            }
        }
    }

    // MARK: - Internals

    private func emit(_ event: String, _ data: String) {
        for handler in handlers[event] ?? [] { handler(data) }
    }

    /// Reads the byte stream and assembles SSE frames OFF the main actor
    /// (`@concurrent`; this target's nonisolated async functions otherwise run
    /// on the caller's actor). Each complete frame is handed to `deliver` on
    /// main and awaited, so frames arrive in wire order and one at a time.
    /// Returns false when `deliver` declines a frame or the task is cancelled,
    /// true when the stream ends.
    @concurrent
    nonisolated private static func readFrames(
        from bytes: URLSession.AsyncBytes,
        deliver: @MainActor @Sendable (String, String) -> Bool
    ) async throws -> Bool {
        var parser = SSEFrameParser()
        var line: [UInt8] = []
        for try await byte in bytes {
            if Task.isCancelled { return false }
            guard byte == 0x0A else {           // not "\n"
                line.append(byte)
                continue
            }
            if line.last == 0x0D { line.removeLast() }   // a CRLF sender
            let text = String(decoding: line, as: UTF8.self)
            line.removeAll(keepingCapacity: true)
            if let frame = parser.feed(text), await !deliver(frame.event, frame.data) {
                return false
            }
        }
        return true
    }

    /// How one connection ended.
    private enum Outcome {
        /// The server answered with a non-200: final, the transport is closed.
        case refused
        /// The stream ended or the network failed, unasked: retry. `healthy`
        /// when it had answered 200 and stayed up at least `retryDelay`.
        case dropped(healthy: Bool)
        /// Closed or cancelled from this side.
        case ended
    }

    private func pump() async -> Outcome {
        connecting = true
        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        // A cached SSE response is not a thing, and a proxy that buffers one
        // would deliver the whole match at once, at the end.
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        // When this connection answered 200; nil until it does.
        var openedAt: TimeInterval?
        func healthy() -> Bool {
            openedAt.map { ProcessInfo.processInfo.systemUptime - $0 >= retryDelay } ?? false
        }

        do {
            let (bytes, response) = try await session.bytes(for: request)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                // 409 / 503 / 404 are refusals with meaning. Report and stop —
                // the controller will not reopen on an error, only on an
                // explicit `reconnect` frame from a stream that was working.
                logger.info("live stream refused: \(http.statusCode) for \(self.url.path)")
                closed = true
                emit("error", "")
                return .refused
            }
            connecting = false
            openedAt = ProcessInfo.processInfo.systemUptime

            // BYTES, NOT `bytes.lines`. MEASURED, not preferred:
            // `URLSession.AsyncBytes.lines` DROPS EMPTY LINES. The blank line is
            // the only thing that terminates an SSE frame, so a reader built on
            // `.lines` receives every `event:` and `data:` line, completes none
            // of them, and emits nothing — for the whole match. It connects, it
            // reports 200, the transport watchdog stays happy because bytes keep
            // arriving, and the user sees a frozen number behind a stream that
            // looks perfectly healthy. Caught end-to-end over a real socket; no
            // parser test could see it, because the parser is correct.
            //
            // Byte-at-a-time, off the main actor (#10090): the bytes are read and
            // the frames assembled there, so the page's own main-actor work no
            // longer shares an executor with the byte loop. Each COMPLETE frame
            // comes back to `emit` in order, and the next is not handed over
            // until it has run.
            let finished = try await Self.readFrames(from: bytes) { [self] event, data in
                // `close()` cancels this task, and a handler may have called it
                // for an earlier frame: nothing is handed on after either.
                if Task.isCancelled || closed { return false }
                emit(event, data)
                return true
            }
            if !finished { return .ended }

            // The byte stream ended without the server saying `closed` or
            // `reconnect` — a release restarting the dyno, or a router cut.
            // That is a dropped connection, not a refusal: retry, as a browser
            // would. `connecting` is set BEFORE the error is reported, so the
            // controller reads it as a blip (polling) and not a death.
            if Task.isCancelled || closed { return .ended }
            logger.info("live stream ended by the server, retrying: \(self.url.path)")
            connecting = true
            emit("error", "")
            return .dropped(healthy: healthy())
        } catch {
            if Task.isCancelled || closed { return .ended }
            logger.info("live stream dropped, retrying: \(error.localizedDescription)")
            connecting = true
            emit("error", "")
            return .dropped(healthy: healthy())
        }
    }
}
