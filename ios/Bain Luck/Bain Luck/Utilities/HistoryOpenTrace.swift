import Foundation
import os

/// #10090 — one instrumented cold open of an event page's win-probability
/// chart.
///
/// The page starts the 168 h history alongside the detail and releases its
/// loading frame before awaiting it; a chart that mounts before that history
/// lands has no `preloadedHistory` and asks for the same payload itself. The
/// generic fetch caches only completed responses, so both asks can be on the
/// wire at once. Whether that happens, and which part of a slow open is
/// transport and which is adoption or rendering, is what this records:
///
/// - each history ask, tagged by owner (`page` / `chart`) and per-owner
///   generation, at START and at completion, with the existing
///   `APIClient.RequestTrace` (auth / network / decode / bytes / cache arm);
/// - the page's detail adoption and history adoption;
/// - the chart's own load, its adoption of a page payload, and the first
///   chart-content build that has points to draw.
///
/// Off unless the rig passes `-launch_trace_history YES`. Records timings,
/// sizes and status words only — never a token, header or body.
nonisolated enum HistoryOpenTrace {
    static let key = "launch_trace_history"

    static let enabled: Bool = UserDefaults.standard.bool(forKey: key)

    /// Who is asking. Set by the caller around its own request and read by
    /// `APIClient.fetchEventHistory`, so the shared fetch seam (and the page's
    /// provider protocol) needs no new parameter.
    @TaskLocal static var owner: String?

    struct Attempt: Sendable {
        let label: String
        let started: Date
    }

    private static let logger = Logger(subsystem: "com.bainluck", category: "historyOpenTrace")
    private static let lock = NSLock()
    nonisolated(unsafe) private static var generations: [String: Int] = [:]

    static var fileURL: URL? {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first?
            .appendingPathComponent("history-open-trace.log")
    }

    static func requestStarted(eventId: Int, hours: Int) -> Attempt {
        let who = owner ?? "unowned"
        let generation: Int = lock.withLock {
            let next = (generations[who] ?? 0) + 1
            generations[who] = next
            return next
        }
        let label = "\(who)#\(generation)"
        write("history.request.start owner=\(label) event=\(eventId) hours=\(hours)")
        return Attempt(label: label, started: Date())
    }

    static func requestFinished(_ attempt: Attempt, _ trace: APIClient.RequestTrace) {
        let total = Date().timeIntervalSince(attempt.started) * 1000
        write(
            "history.request.end owner=\(attempt.label) total_ms=\(ms(total))"
            + " cache=\(trace.cacheStatus) auth_ms=\(ms(trace.authReadyMs))"
            + " network_ms=\(ms(trace.networkMs)) decode_ms=\(ms(trace.decodeMs))"
            + " bytes=\(trace.responseBytes)"
            + " backend_ms=\(trace.backendElapsedMs.map { ms($0) } ?? "nil")")
    }

    static func requestFailed(_ attempt: Attempt, _ error: Error) {
        let total = Date().timeIntervalSince(attempt.started) * 1000
        write("history.request.fail owner=\(attempt.label) total_ms=\(ms(total)) error=\(type(of: error))")
    }

    static func mark(_ event: String, eventId: Int, _ detail: String = "") {
        guard enabled else { return }
        write("\(event) event=\(eventId)" + (detail.isEmpty ? "" : " \(detail)"))
    }

    private static func ms(_ value: Double) -> String { String(format: "%.1f", value) }

    private static func write(_ message: String) {
        let stamp = String(format: "%.3f", Date().timeIntervalSince1970)
        let line = "\(stamp) \(message)"
        logger.notice("\(line, privacy: .public)")
        guard let url = fileURL, let data = (line + "\n").data(using: .utf8) else { return }
        lock.withLock {
            if let handle = try? FileHandle(forWritingTo: url) {
                defer { try? handle.close() }
                _ = try? handle.seekToEnd()
                try? handle.write(contentsOf: data)
            } else {
                try? data.write(to: url)
            }
        }
    }
}
