import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "liveEventStream")

/// One pushed live update. Mirrors `app/utils/live_push.build_frame` on the server.
///
/// `probability` is the AGGREGATE — the number the hero renders — not the single
/// source that happened to move. Publishing the moved source's own price would
/// put a second, disagreeing number on screen, which is what the standing "the
/// blend is the product" ruling forbids.
nonisolated struct LiveFrame: Decodable, Sendable {
    let eventId: Int
    let probability: Double?
    let source: String?
    let sourceValue: Double?
    /// The STAMPED write time, so an age counts from when the data was true
    /// rather than from when the packet arrived.
    let updatedAt: String?
    let status: String?

    enum CodingKeys: String, CodingKey {
        case eventId = "event_id"
        case probability = "p"
        case source
        case sourceValue = "source_value"
        case updatedAt = "updated_at"
        case status
    }
}

/// live/034 S3 — the iOS half of the SSE live push.
///
/// Ruling (RULINGS-BATCH-2026-08-30, LIVE UPDATES): push for LIVE events only;
/// web and iOS subscribe; non-live keeps polling.
///
/// Today `EventDetailViewModel` polls every 30 s on a live event, and each tick
/// refetches FIVE endpoints. This replaces that with one long-lived connection
/// carrying just the number — fresher on screen and dramatically less work.
///
/// THE RULE THIS TYPE EXISTS TO ENFORCE, same as the web client's: a push path
/// that dies must degrade to polling, never to a frozen number. Every exit —
/// refused, errored, ended, or *silently* dead — finishes the stream, and the
/// caller's `for await` loop falls through to resume polling. The silent case
/// is the dangerous one: a connection that is open but delivering nothing looks
/// exactly like a quiet market and would otherwise hold a stale number on
/// screen indefinitely.
nonisolated final class LiveEventStream: Sendable {
    /// Three missed 20 s heartbeats. Long enough that a hiccup does not flap
    /// between push and poll, short enough that a dead stream cannot hold a
    /// stale number for longer than the 30 s poll it replaced.
    static let silenceTimeout: TimeInterval = 60

    private static let baseURL = "https://api.bainluck.com"

    /// Frames for one event, until the stream ends.
    ///
    /// An `AsyncStream` rather than callbacks, deliberately: a closure-based API
    /// would have to be `@Sendable` and would capture the non-Sendable view
    /// model across an isolation boundary. Here the caller consumes frames
    /// inside its own `@MainActor` context, so `self` never crosses at all —
    /// and cancelling the consuming task is what tears the connection down.
    static func frames(eventId: Int) -> AsyncStream<LiveFrame> {
        AsyncStream { continuation in
            let work = Task {
                defer { continuation.finish() }
                await consume(eventId: eventId, continuation: continuation)
            }
            continuation.onTermination = { _ in work.cancel() }
        }
    }

    private static func consume(
        eventId: Int,
        continuation: AsyncStream<LiveFrame>.Continuation
    ) async {
        guard let url = URL(string: "\(baseURL)/api/events/\(eventId)/stream") else { return }

        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        // The default 60 s resource timeout would guillotine a healthy stream on
        // a quiet market. The silence watchdog below bounds this connection
        // instead, because it can tell "no data" apart from "no server".
        request.timeoutInterval = .infinity

        do {
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            guard let http = response as? HTTPURLResponse else { return }
            // 409 = not live (poll instead), 503 = at capacity, 404 = gone.
            // All of them mean the same thing here: do not stream.
            guard http.statusCode == 200 else {
                logger.info("stream refused for \(eventId): \(http.statusCode)")
                return
            }

            var lastMessage = Date()
            var eventName = ""
            var dataBuffer = ""

            for try await line in bytes.lines {
                if Task.isCancelled { return }

                // The watchdog. Checked per line rather than on a separate timer
                // so it cannot outlive the stream it is guarding.
                if Date().timeIntervalSince(lastMessage) > silenceTimeout {
                    logger.info("stream for \(eventId) went silent; falling back to polling")
                    return
                }

                if line.isEmpty {
                    // A blank line DISPATCHES the accumulated event. This is the
                    // whole SSE framing contract; without it the bytes look
                    // correct and nothing is ever delivered.
                    let name = eventName
                    let payload = dataBuffer
                    eventName = ""
                    dataBuffer = ""
                    lastMessage = Date()
                    guard !payload.isEmpty else { continue }

                    switch name {
                    case "probability":
                        // One malformed frame must never end a working stream.
                        if let frame = decode(payload) { continuation.yield(frame) }
                    case "closed", "reconnect":
                        // The match ended, or the server hit its ceiling and
                        // wants us back. Either way stop, and let the caller
                        // resume polling; it refetches once when the loop falls
                        // through, which settles a just-finished match on its
                        // final number.
                        return
                    default:
                        // `open` and `heartbeat` carry no number. They still
                        // rearmed the watchdog above, which is their job.
                        break
                    }
                    continue
                }

                // A comment. Kept for robustness against intermediaries that
                // inject one, even though our server sends a named heartbeat.
                if line.hasPrefix(":") {
                    lastMessage = Date()
                    continue
                }
                if line.hasPrefix("event:") {
                    eventName = String(line.dropFirst(6)).trimmingCharacters(in: .whitespaces)
                } else if line.hasPrefix("data:") {
                    dataBuffer += String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                }
                // `retry:` and `id:` are ignored deliberately — reconnect is the
                // caller's decision, not the wire's.
            }
        } catch {
            if !Task.isCancelled {
                logger.info("stream for \(eventId) ended: \(error.localizedDescription)")
            }
        }
    }

    static func decode(_ payload: String) -> LiveFrame? {
        guard let data = payload.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(LiveFrame.self, from: data)
    }
}
