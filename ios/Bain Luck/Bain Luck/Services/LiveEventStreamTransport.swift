import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "liveStream")

/// The real SSE connection behind `LiveStreamController` (#2687).
///
/// Apple ships no `EventSource`, so the wire format is parsed here: a line
/// reader over `URLSession.bytes(for:)`, accumulating `event:` and `data:` lines
/// and dispatching a complete frame on the blank line that ends it.
///
/// WHAT IT DELIBERATELY DOES NOT DO — retry, back off, decide when to give up,
/// or interpret `reconnect`. All of that is `LiveStreamController`'s, and the
/// separation is the point: the lifecycle is the part that had two P1 defects on
/// web (CERT-717) and the part a test must be able to drive without a socket.
/// This class is transport only.
///
/// THE ONE JUDGEMENT IT DOES MAKE is what "closed for good" means, because the
/// controller asks it (`isClosed`) before deciding whether an error is a blip.
/// A `URLSession` byte stream does not retry by itself, so once its task has
/// ended this connection is over — unlike a browser `EventSource`, which
/// reconnects underneath you. The controller's blip branch is therefore
/// unreachable from this transport today, and that is stated rather than
/// pruned: the branch belongs to the shared lifecycle, and a future transport
/// that does retry would need it.
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

    var isClosed: Bool { closed }

    init(eventId: Int, baseURL: String = "https://api.bainluck.com", session: URLSession? = nil) throws {
        guard let url = URL(string: "\(baseURL)/api/events/\(eventId)/stream") else {
            throw URLError(.badURL)
        }
        self.url = url
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

    /// Open the connection and pump frames until it ends or is cancelled.
    func connect() {
        guard task == nil, !closed else { return }
        task = Task { [weak self] in
            guard let self else { return }
            await self.pump()
        }
    }

    // MARK: - Internals

    private func emit(_ event: String, _ data: String) {
        for handler in handlers[event] ?? [] { handler(data) }
    }

    private func pump() async {
        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        // A cached SSE response is not a thing, and a proxy that buffers one
        // would deliver the whole match at once, at the end.
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")

        do {
            let (bytes, response) = try await session.bytes(for: request)
            if let http = response as? HTTPURLResponse, http.statusCode != 200 {
                // 409 / 503 / 404 are refusals with meaning. Report and stop —
                // the controller will not reopen on an error, only on an
                // explicit `reconnect` frame from a stream that was working.
                logger.info("live stream refused: \(http.statusCode) for \(self.url.path)")
                closed = true
                emit("error", "")
                return
            }

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
            // Byte-at-a-time is fine here: a busy market pushes a frame every
            // few seconds, and correctness on the frame boundary is the whole
            // feature.
            var parser = SSEFrameParser()
            var line: [UInt8] = []
            for try await byte in bytes {
                if Task.isCancelled || closed { return }
                guard byte == 0x0A else {           // not "\n"
                    line.append(byte)
                    continue
                }
                if line.last == 0x0D { line.removeLast() }   // a CRLF sender
                let text = String(decoding: line, as: UTF8.self)
                line.removeAll(keepingCapacity: true)
                if let frame = parser.feed(text) {
                    emit(frame.event, frame.data)
                }
            }

            // The byte stream ended without the server saying `closed` or
            // `reconnect`. That is a dead transport, not a rollover.
            if !closed {
                closed = true
                emit("error", "")
            }
        } catch {
            if Task.isCancelled || closed { return }
            logger.info("live stream ended: \(error.localizedDescription)")
            closed = true
            emit("error", "")
        }
    }
}
