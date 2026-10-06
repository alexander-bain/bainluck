import Foundation
import XCTest
@testable import Bain_Luck

#if DEBUG
/// #1459: local opt-in timing must stay useful without crossing telemetry consent.
final class SportsLoadLocalTrace1459Tests: XCTestCase {
    private final class Lines: @unchecked Sendable {
        private let lock = NSLock()
        private var values: [String] = []
        func append(_ value: String) { lock.lock(); defer { lock.unlock() }; values.append(value) }
        var snapshot: [String] { lock.lock(); defer { lock.unlock() }; return values }
    }

    private func recorder(_ lines: Lines, enabled: Bool = true, limit: Int = 24)
        -> SportsLoadLocalTraceRecorder {
        SportsLoadLocalTraceRecorder(enabled: enabled, limit: limit,
            uptime: { 123.5 }, emit: { lines.append($0) })
    }

    private var network: [String: Any] {
        ["cache_status": "miss", "backend_elapsed_ms": 861.0,
         "auth_ready_ms": 2.0, "network_ms": 1270.0, "decode_ms": 24.4,
         "response_bytes": 95581]
    }
    private var stage: [String: Any] {
        ["stage": "sports_main", "data_ready_ms": 1310.0,
         "item_count": 12, "success": true]
    }
    private var render: [String: Any] {
        ["first_render_ms": 1350.0, "item_count": 12]
    }
    private func packets(_ lines: Lines) throws -> [[String: Any]] {
        try lines.snapshot.map {
            try XCTUnwrap(JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any])
        }
    }

    func testDisabledAndUnrelatedEventsCannotCollect() {
        let off = Lines(), on = Lines()
        recorder(off, enabled: false).capture("sports_feed_network", network)
        let active = recorder(on)
        for name in ["search", "screen_timing", "event_card_click", "sports_trace_truncated", "unknown"] {
            active.capture(name, network)
        }
        active.capture("sports_feed_stage", nil)
        XCTAssertTrue(off.snapshot.isEmpty)
        XCTAssertTrue(on.snapshot.isEmpty)
    }

    func testAllThreePacketsKeepOnlyTheirTypedFields() throws {
        let lines = Lines(), active = recorder(lines)
        for (event, original) in [("sports_feed_network", network),
                                 ("sports_feed_stage", stage),
                                 ("sports_feed_first_render", render)] {
            var parameters = original
            // Several keys survive the global analytics schema; local capture must not retain them.
            for key in ["event_id", "market_id", "query_hash", "query", "token", "url",
                        "path", "email", "error", "app_build", "surface"] {
                parameters[key] = "alex@example.com Bearer PRIVATE https://example.com/secret"
            }
            active.capture(event, parameters)
        }
        let output = try packets(lines)
        XCTAssertEqual(output.count, 3)
        for (index, packet) in output.enumerated() {
            let expected = [Set(network.keys), Set(stage.keys), Set(render.keys)][index]
                .union(["event", "sequence", "uptime_s"])
            XCTAssertEqual(Set(packet.keys), expected)
            XCTAssertEqual((packet["sequence"] as? NSNumber)?.intValue, index + 1)
            XCTAssertEqual((packet["uptime_s"] as? NSNumber)?.doubleValue, 123.5)
        }
        XCTAssertFalse(lines.snapshot.joined().contains("PRIVATE"))
        XCTAssertFalse(lines.snapshot.joined().contains("example.com"))
    }

    func testCacheArmsAndMissingBackendSentinelStayHonest() throws {
        let lines = Lines(), active = recorder(lines)
        let arms = ["hit", "stale_hit", "miss", "client_ttl", "coalesced", "unknown"]
        for arm in arms {
            var value = network; value["cache_status"] = arm; value["backend_elapsed_ms"] = -1.0
            active.capture("sports_feed_network", value)
        }
        var attack = network; attack["cache_status"] = "alex@example.com Bearer PRIVATE"
        active.capture("sports_feed_network", attack)
        let output = try packets(lines)
        XCTAssertEqual(output.compactMap { $0["cache_status"] as? String }, arms + ["unknown"])
        for packet in output.prefix(arms.count) {
            XCTAssertEqual((packet["backend_elapsed_ms"] as? NSNumber)?.doubleValue, -1)
        }
        XCTAssertFalse(lines.snapshot.joined().contains("PRIVATE"))
    }

    func testBadStageAndMissingOrNonFiniteMetricsRejectWholePacket() {
        let lines = Lines(), active = recorder(lines)
        for key in network.keys where key != "cache_status" {
            var value = network; value.removeValue(forKey: key)
            active.capture("sports_feed_network", value)
        }
        for key in ["auth_ready_ms", "network_ms", "decode_ms", "backend_elapsed_ms"] {
            for bad in [Double.nan, Double.infinity, -2.0, "12", true] as [Any] {
                var value = network; value[key] = bad
                active.capture("sports_feed_network", value)
            }
        }
        for bad in [-1, 1.5, true, "10"] as [Any] {
            var value = network; value["response_bytes"] = bad
            active.capture("sports_feed_network", value)
            var first = render; first["item_count"] = bad
            active.capture("sports_feed_first_render", first)
        }
        for bad in ["PRIVATE", 1, true] as [Any] {
            var value = stage; value["stage"] = bad
            active.capture("sports_feed_stage", value)
        }
        for bad in ["true", 1, 0.0] as [Any] {
            var value = stage; value["success"] = bad
            active.capture("sports_feed_stage", value)
        }
        for bad in [Double.nan, Double.infinity, -1.0, "12", true] as [Any] {
            var value = stage; value["data_ready_ms"] = bad
            active.capture("sports_feed_stage", value)
            var first = render; first["first_render_ms"] = bad
            active.capture("sports_feed_first_render", first)
        }
        XCTAssertTrue(lines.snapshot.isEmpty)
    }

    func testStageKindsAndZeroCountsAreNotInventedFailures() throws {
        let lines = Lines(), active = recorder(lines)
        for kind in ["sports_main", "sports_events_backfill", "sports_grouped"] {
            var value = stage; value["stage"] = kind; value["item_count"] = 0; value["success"] = false
            active.capture("sports_feed_stage", value)
        }
        let output = try packets(lines)
        XCTAssertEqual(output.count, 3)
        XCTAssertEqual(output.compactMap { $0["stage"] as? String },
                       ["sports_main", "sports_events_backfill", "sports_grouped"])
        for packet in output {
            XCTAssertEqual((packet["item_count"] as? NSNumber)?.intValue, 0)
            XCTAssertEqual(packet["success"] as? Bool, false)
        }
    }

    func testInvalidPacketsDoNotConsumeCapAndTruncationIsTerminal() throws {
        let lines = Lines(), active = recorder(lines, limit: 2)
        active.capture("search", network)
        active.capture("sports_feed_stage", ["stage": "PRIVATE"])
        active.capture("sports_feed_network", network)
        active.capture("sports_feed_stage", stage)
        // Invalid packets after saturation must not fabricate the truncation marker.
        active.capture("screen_timing", render)
        XCTAssertEqual(lines.snapshot.count, 2)
        active.capture("sports_feed_first_render", render)
        for _ in 0..<10 { active.capture("sports_feed_network", network) }
        let output = try packets(lines)
        XCTAssertEqual(output.count, 3)
        XCTAssertEqual(output.last?["event"] as? String, "sports_trace_truncated")
        XCTAssertEqual((output.last?["sequence"] as? NSNumber)?.intValue, 3)
        XCTAssertEqual(Set(try XCTUnwrap(output.last).keys), ["event", "sequence", "uptime_s"])
    }

    func testLimitCannotBecomeAnUnboundedOrNegativeCollector() throws {
        for requested in [-10, 0, 99] {
            let lines = Lines(), active = recorder(lines, limit: requested)
            for _ in 0..<30 { active.capture("sports_feed_network", network) }
            let output = try packets(lines)
            let effective = max(0, min(requested, 24))
            XCTAssertEqual(output.count, effective + 1)
            XCTAssertEqual(output.last?["event"] as? String, "sports_trace_truncated")
            XCTAssertEqual((output.last?["sequence"] as? NSNumber)?.intValue, effective + 1)
        }
    }

    func testInvalidUptimeCannotProduceAFalseTimingPacket() {
        for bad in [Double.nan, Double.infinity, -1.0] {
            let lines = Lines()
            let active = SportsLoadLocalTraceRecorder(enabled: true,
                uptime: { bad }, emit: { lines.append($0) })
            active.capture("sports_feed_network", network)
            XCTAssertTrue(lines.snapshot.isEmpty)
        }
    }

    func testConcurrentCaptureIsBoundedOrderedAndParseable() throws {
        let lines = Lines(), active = recorder(lines, limit: 24)
        DispatchQueue.concurrentPerform(iterations: 200) { index in
            let value: [String: Any] = ["cache_status": "miss", "backend_elapsed_ms": 861.0,
                "auth_ready_ms": 2.0, "network_ms": 1270.0, "decode_ms": 24.4,
                "response_bytes": index]
            active.capture("sports_feed_network", value)
        }
        let output = try packets(lines)
        XCTAssertEqual(output.count, 25)
        XCTAssertEqual(output.compactMap { ($0["sequence"] as? NSNumber)?.intValue }, Array(1...25))
        XCTAssertEqual(output.filter { $0["event"] as? String == "sports_trace_truncated" }.count, 1)
        XCTAssertEqual(output.last?["event"] as? String, "sports_trace_truncated")
        let counts = output.prefix(24).compactMap { ($0["response_bytes"] as? NSNumber)?.intValue }
        XCTAssertEqual(counts.count, 24)
        XCTAssertEqual(Set(counts).count, 24)
    }
}
#endif
