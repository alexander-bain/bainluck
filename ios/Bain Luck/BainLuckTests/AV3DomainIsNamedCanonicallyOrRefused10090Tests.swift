import XCTest
@testable import Bain_Luck

/// #10090 / #11564 — the v3 reader's durable domain primitives
/// (`PreviewAuthorityV3`, `JSONDuplicateKeys`), before any envelope is decoded.
/// The invalid incarnations and the maximum are the shared contract fixture's
/// (`docs/contracts/dnpl-authority-v3.examples.json`, draft R1 d19c2f89).
final class AV3DomainIsNamedCanonicallyOrRefused10090Tests: XCTestCase {
    private let one = "11111111-1111-4111-8111-111111111111"
    private let two = "22222222-2222-4222-8222-222222222222"

    func testOnlyACanonicalInRangeDecimalStringIsAnIncarnation() {
        for bad in ["0", "01", "-1", "1.0", "1e3", " 1", "9007199254740992",
                    "", "+1", "1 ", "99999999999999999", "１"] {
            XCTAssertNil(PreviewAuthorityV3.incarnation(bad), bad)
        }
        XCTAssertEqual(PreviewAuthorityV3.incarnation("1"), 1)
        XCTAssertEqual(PreviewAuthorityV3.incarnation("9007199254740991"), PreviewAuthorityV3.maxIncarnation)
        XCTAssertNil(PreviewAuthorityV3(incarnation: "01", namespace: one))
    }

    func testAJSONNumberIsNeverAnIncarnation() {
        struct Packet: Decodable { let incarnation: String }
        for number in ["0", "1"] {
            XCTAssertNil(try? JSONDecoder().decode(Packet.self, from: Data(#"{"incarnation":\#(number)}"#.utf8)))
        }
    }

    func testANamespaceIsALowercaseCanonicalUUID() {
        XCTAssertTrue(PreviewAuthorityV3.isCanonicalUUID(one))
        for bad in ["11111111-1111-4111-8111-11111111111A", "111111111111-4111-8111-1111111111111",
                    "11111111-1111-4111-8111-11111111111", " 1111111-1111-4111-8111-111111111111",
                    "g1111111-1111-4111-8111-111111111111"] {
            XCTAssertFalse(PreviewAuthorityV3.isCanonicalUUID(bad), bad)
        }
        XCTAssertNil(PreviewAuthorityV3(incarnation: "1", namespace: one.uppercased()))
    }

    func testIncarnationOrdersAndTheNamespaceOnlyGuardsEquality() throws {
        let current = try XCTUnwrap(PreviewAuthorityV3(incarnation: "1", namespace: one))
        let contradiction = try XCTUnwrap(PreviewAuthorityV3(incarnation: "1", namespace: two))
        let newer = try XCTUnwrap(PreviewAuthorityV3(incarnation: "2", namespace: two))
        XCTAssertEqual(current.order(current), .same)
        XCTAssertEqual(current.order(newer), .newer)
        XCTAssertEqual(newer.order(current), .refused)
        XCTAssertEqual(current.order(contradiction), .refused)
    }

    func testADuplicateKeyAnywhereRefusesTheMessage() {
        func free(_ json: String) -> Bool { JSONDuplicateKeys.isFree(Data(json.utf8)) }
        XCTAssertTrue(free(#"{"a":1,"b":{"a":2},"c":[{"a":1},{"a":2}]}"#))
        XCTAssertFalse(free(#"{"a":1,"a":2}"#))
        XCTAssertFalse(free(#"{"a":1,"\u0061":2}"#))
        XCTAssertFalse(free(#"{"x":{"p":1,"q":"}","p":2}}"#))
        XCTAssertTrue(free(#"{"é":1,"e":2}"#))
        XCTAssertFalse(free(#"{"é":1,"é":2}"#))
        XCTAssertTrue(free(#"{"s":"a\"b","t":"\\"}"#))
    }

    func testMalformedOrOverDeepInputIsRefusedNotGuessed() {
        func free(_ json: String) -> Bool { JSONDuplicateKeys.isFree(Data(json.utf8)) }
        XCTAssertFalse(free(#"{"a":1"#))
        XCTAssertFalse(free(#"{"a":1}x"#))
        XCTAssertFalse(free(#"{"a":"\u00G1"}"#))
        XCTAssertFalse(free(#"{"a":"\u+061"}"#))
        XCTAssertFalse(free(String(repeating: "[", count: 40) + String(repeating: "]", count: 40)))
        XCTAssertTrue(free("  {}  "))
    }

    /// The fixture's folded blend, verbatim: every key unique.
    func testTheSharedFoldedBlendFixtureIsDuplicateFree() {
        let fixture = #"{"protocol": 3, "event_id": 42, "authority": {"incarnation": "1", "namespace": "11111111-1111-4111-8111-111111111111"}, "stream_session": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "frame": {"event_id": 42, "p": 0.6, "p_away": 0.4, "sport": "tennis_atp", "status": "live", "display_observed_at": "2026-10-25T17:00:00.000Z", "preview": {"kind": "blend", "folded_version": 2, "fold_session": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "fold_seq": 1, "base_fold_revision": {"42": 10, "43": 20}, "origin_authority": {"42": {"epoch": 2, "seq": 1, "state": "pending", "ttl_ms": 800}, "43": {"epoch": 3, "seq": 1, "state": "pending", "ttl_ms": 900}}, "ttl_ms": 800}}}"#
        XCTAssertTrue(JSONDuplicateKeys.isFree(Data(fixture.utf8)))
    }
}
