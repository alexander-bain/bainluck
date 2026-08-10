import XCTest

@testable import Bain_Luck

/// Queue 311 Item A4 (#1159) — `push_opened` survives the privacy boundary.
///
/// The trap this pins is specific and quiet: `AnalyticsPrivacy.sanitize` drops
/// any unregistered event name by returning nil, and drops any unregistered
/// parameter key by omission. Neither drop logs, throws, or fails a build.
///
/// So emitting `push_opened` without ALSO registering it and `payload_id` would
/// have shipped a funnel that reads exactly zero opens forever, with every test
/// that merely called the tracker passing. These tests assert the boundary's
/// output rather than the tracker's invocation, because the boundary is where
/// the event actually lives or dies.
final class PushOpenedBoundaryTests: XCTestCase {

    func testPushOpenedIsARegisteredEvent() {
        let sanitized = AnalyticsPrivacy.sanitize(
            event: "push_opened",
            parameters: ["payload_id": "digest-20260810", "surface": "digest"]
        )
        XCTAssertNotNil(sanitized, "push_opened must be registered or every open is silently dropped")
    }

    func testPayloadIdSurvivesTheBoundary() {
        let sanitized = AnalyticsPrivacy.sanitize(
            event: "push_opened",
            parameters: ["payload_id": "digest-20260810", "surface": "digest"]
        )
        let params = try! XCTUnwrap(sanitized)

        // Without this key the client event cannot be joined to the server's
        // `push_sent`, which leaves two unrelated counts instead of a rate.
        XCTAssertEqual(params["payload_id"] as? String, "digest-20260810")
        XCTAssertEqual(params["surface"] as? String, "digest")
    }

    func testPayloadIdIsNotMistakenForAnIdentifierAndRedacted() {
        // REGRESSION. `scrub` replaces digit runs of 7+ digits with `[number]`,
        // and a campaign id is `digest-YYYYMMDD` — eight consecutive digits. On
        // first run this test FAILED with `digest-[number]`: the join key was
        // being destroyed at the boundary, so the funnel would have reported
        // zero opens forever with nothing erroring. Same shape as the incident
        // that once turned the `app_build` tag into `[number]`.
        let sanitized = AnalyticsPrivacy.sanitize(
            event: "push_opened",
            parameters: ["payload_id": "digest-20260810"]
        )
        let params = try! XCTUnwrap(sanitized)

        XCTAssertEqual(
            params["payload_id"] as? String,
            "digest-20260810",
            "the campaign id must arrive intact — a redacted join key joins nothing"
        )
    }

    func testMalformedPayloadIdIsDroppedRatherThanPassedThrough() {
        // The exemption is a SHAPE guard, not a trust exemption. Free text under
        // this key must not ride out unscrubbed just because the key is allowed.
        for bad in [
            "alex@example.com",
            "Will the Fed cut rates in September?",
            "digest-2026",           // wrong date width
            "DIGEST-20260810",       // wrong case
            "../../etc/passwd",
        ] {
            let params = AnalyticsPrivacy.sanitize(
                event: "push_opened",
                parameters: ["payload_id": bad]
            )
            XCTAssertNil(
                params?["payload_id"],
                "a non-campaign-shaped payload_id must be dropped, got \(bad)"
            )
        }
    }

    func testOtherSurfacesCampaignIdsAlsoSurvive() {
        // The pattern is not hardcoded to "digest" — a future campaign surface
        // should not silently lose its join key.
        let params = AnalyticsPrivacy.sanitize(
            event: "push_opened",
            parameters: ["payload_id": "big_moves-20261231", "surface": "big_moves"]
        )
        XCTAssertEqual(params?["payload_id"] as? String, "big_moves-20261231")
    }

    func testUnregisteredKeysOnPushOpenedStillFailClosed() {
        // Registering the event must not widen what the event may carry.
        let sanitized = AnalyticsPrivacy.sanitize(
            event: "push_opened",
            parameters: [
                "payload_id": "digest-20260810",
                "user_email": "alex@example.com",
                "market_name": "Will the Fed cut rates?",
            ]
        )
        let params = try! XCTUnwrap(sanitized)

        XCTAssertNil(params["user_email"])
        XCTAssertNil(params["market_name"])
        XCTAssertEqual(params.count, 1)
    }
}
