import XCTest
@testable import Bain_Luck

/// native/006 — the Sports main request reports WHICH SERVER CACHE ARM it hit.
///
/// Why this exists: latency measured the `mode=sports` floor at 38ms on a server
/// cache hit and 861ms on a miss, and 47% of real `/api/feed` requests miss. The
/// native Sports rails reported `data_ready_ms` with no arm attached, so five cold
/// launches that read 330 / 337 / 328 / 960 / 1399 ms were indistinguishable from a
/// client that had become four times slower. These guard the two decisions that make
/// the new `sports_feed_network` rail honest.
final class SportsFeedNetworkTraceTests: XCTestCase {

    // MARK: - The arm a response actually claims

    func testServerArmIsReportedVerbatim() {
        // The three values `feed.py` emits. Passed through unchanged so a new
        // server-side arm needs no client release to become readable.
        XCTAssertEqual(APIClient.RequestTrace.arm(fromHeader: "hit"), "hit")
        XCTAssertEqual(APIClient.RequestTrace.arm(fromHeader: "stale_hit"), "stale_hit")
        XCTAssertEqual(APIClient.RequestTrace.arm(fromHeader: "miss"), "miss")
    }

    func testAbsentHeaderIsUnknownAndNeverMiss() {
        // The defect this forecloses: defaulting an absent header to `miss` would
        // make every non-feed surface, and every response from a proxy that strips
        // the header, inflate the miss rate — a cache-hit number that reads as
        // measurement but is arithmetic on an assumption.
        XCTAssertEqual(APIClient.RequestTrace.arm(fromHeader: nil), "unknown")
        XCTAssertNotEqual(APIClient.RequestTrace.arm(fromHeader: nil), "miss")
    }

    func testBlankHeaderIsUnknown() {
        // An empty or whitespace header value is a header that said nothing.
        XCTAssertEqual(APIClient.RequestTrace.arm(fromHeader: ""), "unknown")
        XCTAssertEqual(APIClient.RequestTrace.arm(fromHeader: "  "), "unknown")
    }

    func testClientTTLIsDistinctFromEveryServerArm() {
        // A call served from the in-memory TTL cache never left the device, so it
        // reports nothing about the server. It must not be collapsed into `hit`:
        // doing so would let a tab-switch storm look like server cache health.
        let ttl = APIClient.RequestTrace.clientTTL
        XCTAssertEqual(ttl, "client_ttl")
        for serverArm in ["hit", "stale_hit", "miss", "unknown"] {
            XCTAssertNotEqual(ttl, serverArm)
        }
    }

    // MARK: - The rail survives the privacy contract

    func testSportsFeedNetworkEventIsAllowlisted() {
        // Red before the allowlist entry: `sanitize` fails closed on an unknown
        // event NAME, so the whole rail would have been silently dropped and the
        // arm would never reach GA4 — the instrument would look wired and report
        // nothing, which is the failure mode worth a test.
        XCTAssertNotNil(
            AnalyticsPrivacy.sanitize(event: "sports_feed_network", parameters: nil),
            "the rail's event name must be registered or every packet is dropped")
    }

    func testEveryTraceFieldSurvivesSanitization() {
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "sports_feed_network",
                parameters: [
                    "cache_status": "miss",
                    "backend_elapsed_ms": 861.0,
                    "auth_ready_ms": 0.01,
                    "network_ms": 1270.0,
                    "decode_ms": 24.4,
                    "response_bytes": 95581,
                    "app_build": "1.0 (7)",
                    "surface": "sports",
                ]
            )
        )
        XCTAssertEqual(params.count, 8, "every field the rail emits reaches the sink")
        XCTAssertEqual(params["cache_status"] as? String, "miss",
                       "the arm is the one field the rail exists for")
        XCTAssertEqual(params["backend_elapsed_ms"] as? Double, 861.0)
        XCTAssertEqual(params["surface"] as? String, "sports")
    }

    func testTraceCarriesNoIdentifiers() {
        // The rail is built from response headers and clocks only. If a future
        // edit adds a URL or a session to it, the hard-drop list catches it here
        // rather than in a privacy review after the packets have shipped.
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "sports_feed_network",
                parameters: [
                    "cache_status": "hit",
                    "url": "https://api.bainluck.com/api/feed?mode=sports",
                    "token": "abc123",
                ]
            )
        )
        XCTAssertNil(params["url"])
        XCTAssertNil(params["token"])
        XCTAssertEqual(params["cache_status"] as? String, "hit")
    }
}
