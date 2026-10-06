import Foundation

#if DEBUG
import CoreFoundation
import OSLog
#endif

/// A finite, explicitly enabled local diagnostic for the existing Sports load
/// milestones. It never changes analytics consent or sends anything to Firebase.
/// Release builds have no recorder, logger, or enablement path.
nonisolated enum SportsLoadLocalTrace {
    static func capture(_ name: String, _ parameters: [String: Any]? = nil) {
        #if DEBUG
        recorder.capture(name, parameters)
        #endif
    }

    #if DEBUG
    private static let logger = Logger(
        subsystem: "com.bainluck.diagnostics", category: "SportsLoadTrace")
    private static let recorder = SportsLoadLocalTraceRecorder(
        enabled: ProcessInfo.processInfo.arguments.contains("-BLUITestSportsLocalTrace"),
        emit: { line in
            SportsLoadLocalTrace.logger.notice("BL_SPORTS_LOCAL_TRACE \(line, privacy: .public)")
        })
    #endif
}

#if DEBUG
/// Only the three existing timing events are admitted. Their global analytics
/// allowlist is intentionally NOT reused: it permits identifiers and free text
/// that do not belong in a pre-consent local diagnostic.
///
/// A sequence is an emission order, not a request/load identity. A capture with
/// overlapping main requests must not be treated as one matched timing chain.
nonisolated final class SportsLoadLocalTraceRecorder: @unchecked Sendable {
    private let enabled: Bool
    private let limit: Int
    private let uptime: @Sendable () -> Double
    private let emit: @Sendable (String) -> Void
    private let lock = NSLock()
    private var emitted = 0
    private var truncated = false

    init(
        enabled: Bool,
        limit: Int = 24,
        uptime: @escaping @Sendable () -> Double = { ProcessInfo.processInfo.systemUptime },
        emit: @escaping @Sendable (String) -> Void
    ) {
        self.enabled = enabled
        self.limit = max(0, min(limit, 24))
        self.uptime = uptime
        self.emit = emit
    }

    func capture(_ name: String, _ parameters: [String: Any]?) {
        guard enabled, var payload = Self.payload(name, parameters ?? [:]) else { return }
        lock.lock()
        defer { lock.unlock() }
        guard !truncated else { return }
        let now = uptime()
        guard now.isFinite, now >= 0 else { return }
        if emitted >= limit {
            payload = ["event": "sports_trace_truncated"]
            truncated = true
        } else {
            emitted += 1
        }
        payload["sequence"] = truncated ? emitted + 1 : emitted
        payload["uptime_s"] = now
        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
              let line = String(data: data, encoding: .utf8) else { return }
        // Synchronous emission under the lock preserves sequence/log order.
        // The production sink is only OSLog; injected test sinks must not reenter.
        emit(line)
    }

    private static func payload(_ name: String, _ values: [String: Any]) -> [String: Any]? {
        var result: [String: Any] = ["event": name]
        switch name {
        case "sports_feed_network":
            for field in ["auth_ready_ms", "network_ms", "decode_ms", "backend_elapsed_ms"] {
                guard let value = number(values[field]),
                      value >= 0 || (field == "backend_elapsed_ms" && value == -1) else { return nil }
                result[field] = value
            }
            guard let bytes = count(values["response_bytes"]) else { return nil }
            result["response_bytes"] = bytes
            let arm = values["cache_status"] as? String ?? "unknown"
            let knownArms = ["hit", "stale_hit", "miss", "client_ttl", "coalesced", "unknown"]
            result["cache_status"] = knownArms.contains(arm) ? arm : "unknown"
        case "sports_feed_stage":
            guard let stage = values["stage"] as? String,
                  ["sports_main", "sports_events_backfill", "sports_grouped"].contains(stage),
                  let elapsed = number(values["data_ready_ms"]), elapsed >= 0,
                  let items = count(values["item_count"]),
                  let success = boolean(values["success"]) else { return nil }
            result["stage"] = stage
            result["data_ready_ms"] = elapsed
            result["item_count"] = items
            result["success"] = success
        case "sports_feed_first_render":
            guard let elapsed = number(values["first_render_ms"]), elapsed >= 0,
                  let items = count(values["item_count"]) else { return nil }
            result["first_render_ms"] = elapsed
            result["item_count"] = items
        default:
            return nil
        }
        return result
    }

    private static func number(_ value: Any?) -> Double? {
        guard let value = value as? NSNumber,
              CFGetTypeID(value) != CFBooleanGetTypeID(), value.doubleValue.isFinite else { return nil }
        return value.doubleValue
    }

    private static func count(_ value: Any?) -> Int? {
        guard let value = number(value), value >= 0,
              value < Double(Int.max), value.rounded(.towardZero) == value else { return nil }
        return Int(value)
    }

    private static func boolean(_ value: Any?) -> Bool? {
        guard let value = value as? NSNumber,
              CFGetTypeID(value) == CFBooleanGetTypeID() else { return nil }
        return value.boolValue
    }
}
#endif
