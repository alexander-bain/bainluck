import Security
import XCTest

@testable import Bain_Luck

/// L2-219 Item 2 (#1453, updated for 404: B) — the native analytics privacy boundary.
///
/// `AnalyticsService.trackSearch` used to send the user's RAW search text to
/// Firebase as `search_term`, and `trackSearchResultClick` sent it again as
/// `query`. These tests pin the replacement contract: raw text never survives
/// the boundary, the derived metadata is bounded and keyed with an on-device
/// HMAC-SHA-256 secret that never leaves the phone, and unknown keys/events fail closed.
final class AnalyticsPrivacyTests: XCTestCase {
    // MARK: - Raw text never survives

    func testSearchEventCarriesNoRawQuery() {
        let sanitized = AnalyticsPrivacy.sanitize(
            event: "search",
            parameters: ["search_term": "Lakers vs Celtics", "results_count": 12]
        )
        let params = try! XCTUnwrap(sanitized)

        XCTAssertNil(params["search_term"], "raw search_term must never reach Firebase")
        XCTAssertNil(params["query"])
        XCTAssertNotNil(params["query_hash"])
        XCTAssertEqual(params["query_length"] as? Int, 17)
        XCTAssertEqual(params["query_word_count"] as? Int, 3)
        XCTAssertEqual(params["results_count"] as? Int, 12, "approved telemetry survives")
    }

    func testResultClickCarriesNoRawQueryOrResultId() {
        let sanitized = AnalyticsPrivacy.sanitize(
            event: "search_result_click",
            parameters: [
                "query": "chiefs super bowl",
                "result_type": "futures",
                "result_id": "1234",
                "position": 2,
            ]
        )
        let params = try! XCTUnwrap(sanitized)

        XCTAssertNil(params["query"])
        XCTAssertNil(params["result_id"])
        XCTAssertNotNil(params["query_hash"])
        XCTAssertNotNil(params["query_length"])
        XCTAssertNotNil(params["query_word_count"])
        XCTAssertEqual(params["result_type"] as? String, "futures")
        XCTAssertEqual(params["position"] as? Int, 2)
    }

    // MARK: - PII fixtures

    func testPIIShapedQueriesLeakNothing() {
        let fixtures = [
            "alex@example.com",
            "my email is alex.bain+test@example.co.uk please",
            "+1 (415) 555-0134",
            "4111 1111 1111 1111",
            "https://bainluck.com/account?token=abc123",
            "www.example.com/reset/9f8e7d6c5b4a",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "ssn 123-45-6789",
        ]

        for raw in fixtures {
            let params = try! XCTUnwrap(
                AnalyticsPrivacy.sanitize(event: "search", parameters: ["search_term": raw])
            )
            let serialized = params.map { "\($0.key)=\($0.value)" }.joined(separator: "&")

            XCTAssertFalse(serialized.contains("@example"), "leaked email in: \(raw)")
            XCTAssertFalse(serialized.contains("555-0134"), "leaked phone in: \(raw)")
            XCTAssertFalse(serialized.contains("4111"), "leaked card digits in: \(raw)")
            XCTAssertFalse(serialized.contains("bainluck.com"), "leaked URL in: \(raw)")
            XCTAssertFalse(serialized.contains("eyJhbGci"), "leaked token in: \(raw)")
            XCTAssertFalse(serialized.contains("123-45-6789"), "leaked SSN in: \(raw)")
            // Only the three derived keys are present.
            XCTAssertEqual(Set(params.keys), ["query_hash", "query_length", "query_word_count"])
        }
    }

    /// Regression: an early digit-redaction rule treated `.` as a phone
    /// separator and rewrote the legitimate `app_build` tag `1.4.2 (231)` as
    /// `[number]`, which would have destroyed build attribution on every
    /// latency event. Version-shaped strings must survive; real identifiers
    /// must not.
    func testVersionStringsSurviveDigitRedaction() {
        XCTAssertEqual(AnalyticsPrivacy.scrub("1.4.2 (231)"), "1.4.2 (231)")
        XCTAssertEqual(AnalyticsPrivacy.scrub("2.0.0 (1)"), "2.0.0 (1)")
        XCTAssertEqual(AnalyticsPrivacy.scrub("hit"), "hit")

        XCTAssertEqual(AnalyticsPrivacy.scrub("415-555-0134"), "[number]")
        XCTAssertEqual(AnalyticsPrivacy.scrub("4111 1111 1111 1111"), "[number]")
    }

    func testPIIInAnAllowlistedStringFieldIsRedacted() {
        // Defense in depth: a categorical field handed user text by a future caller.
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "onboarding_step",
                parameters: ["step": 2, "step_name": "contact alex@example.com now"]
            )
        )
        let stepName = try! XCTUnwrap(params["step_name"] as? String)
        XCTAssertFalse(stepName.contains("@example.com"))
        XCTAssertTrue(stepName.contains("[email]"))
    }

    // MARK: - Bounds

    func testLongQueryLengthAndWordCountAreClamped() {
        let long = String(repeating: "a", count: 5_000)
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(event: "search", parameters: ["search_term": long])
        )
        XCTAssertEqual(params["query_length"] as? Int, AnalyticsPrivacy.maxQueryLength)

        let manyWords = (0..<400).map(String.init).joined(separator: " ")
        let wordParams = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(event: "search", parameters: ["search_term": manyWords])
        )
        XCTAssertEqual(
            wordParams["query_word_count"] as? Int, AnalyticsPrivacy.maxQueryWordCount
        )
    }

    func testAllowlistedStringsAreLengthBounded() {
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "feed_card_action",
                parameters: ["action": String(repeating: "x", count: 900)]
            )
        )
        let action = try! XCTUnwrap(params["action"] as? String)
        XCTAssertLessThanOrEqual(action.count, AnalyticsPrivacy.maxStringLength)
    }

    func testUnicodeAndEmojiQueriesAreHandledWithoutLeaking() {
        for raw in ["¿quién gana el mundial?", "日本シリーズ 優勝", "🏈 chiefs 🏆"] {
            let params = try! XCTUnwrap(
                AnalyticsPrivacy.sanitize(event: "search", parameters: ["search_term": raw])
            )
            XCTAssertEqual(Set(params.keys), ["query_hash", "query_length", "query_word_count"])
            XCTAssertFalse((params["query_hash"] as? String ?? "").isEmpty)
        }
    }

    // MARK: - Normalization + joinability

    func testNormalizationEquivalence() {
        let canonical = AnalyticsPrivacy.hashQuery("Lakers")
        for variant in ["lakers", "  lakers  ", "LAKERS", "\tLakers\n"] {
            XCTAssertEqual(
                AnalyticsPrivacy.hashQuery(variant), canonical,
                "trim + lowercase must produce one identity for: \(variant)"
            )
        }
    }

    func testDifferentQueriesGetDifferentHashes() {
        XCTAssertNotEqual(
            AnalyticsPrivacy.hashQuery("lakers"), AnalyticsPrivacy.hashQuery("celtics")
        )
    }

    func testHashIsNotReversibleToLengthAndIsLowercaseHex16() {
        // A hash is fixed-width regardless of input size — it carries no length.
        let short = AnalyticsPrivacy.hashQuery("a")
        let long = AnalyticsPrivacy.hashQuery(String(repeating: "a", count: 4_000))
        let hexSet = CharacterSet(charactersIn: "0123456789abcdef")
        XCTAssertEqual(short.count, 16)
        XCTAssertEqual(long.count, 16)
        XCTAssertTrue(short.unicodeScalars.allSatisfy { hexSet.contains($0) })
        XCTAssertTrue(long.unicodeScalars.allSatisfy { hexSet.contains($0) })
    }

    /// Pins known CryptoKit HMAC-SHA-256 outputs (64-bit truncated lowercase hex)
    /// against independently computed RFC 2104 / FIPS 198 values (`404: B`), and
    /// verifies that two distinct random secrets share no prefix.
    func testHashUsesHMACSHA256AndTwoSecretsShareNoPrefix() {
        let keyA = Data(0..<32)
        let keyB = Data(1..<33)

        XCTAssertEqual(AnalyticsPrivacy.hashQuery("", keyData: keyA), "d38b42096d80f45f")
        XCTAssertEqual(AnalyticsPrivacy.hashQuery("abc", keyData: keyA), "f0133729c4163ded")
        XCTAssertEqual(AnalyticsPrivacy.hashQuery("lakers", keyData: keyA), "7e6e02b5482ef907")
        XCTAssertEqual(AnalyticsPrivacy.hashQuery("  Lakers vs Celtics ", keyData: keyA), "eeabfcfd619fe4fb")

        let hashA = AnalyticsPrivacy.hashQuery("lakers", keyData: keyA)
        let hashB = AnalyticsPrivacy.hashQuery("lakers", keyData: keyB)
        XCTAssertEqual(hashB, "3b64fbec21b566df")
        XCTAssertNotEqual(hashA.prefix(4), hashB.prefix(4))
    }

    func testKeychainStorageUsesThisDeviceOnlyAndNoSync() {
        let attrs = SearchHashKeychainStorage.saveAttributes(for: Data(repeating: 0xAB, count: 32))
        XCTAssertEqual(
            attrs[kSecAttrAccessible as String] as? String,
            kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly as String
        )
        XCTAssertNil(attrs[kSecAttrSynchronizable as String])
    }

    func testSearchHashSecretOnlyPersistsWithConsentAndResetsOnRevocation() {
        final class InMemoryKeyStorage: SearchHashKeyStorage {
            var storedKey: Data?
            var loadCount = 0
            var saveCount = 0
            var deleteCount = 0

            func load() -> Data? {
                loadCount += 1
                return storedKey
            }

            func save(_ key: Data) -> Bool {
                saveCount += 1
                storedKey = key
                return true
            }

            func delete() {
                deleteCount += 1
                storedKey = nil
            }
        }

        let storage = InMemoryKeyStorage()
        var consented = false
        let fixedKeys = [Data(repeating: 0x11, count: 32), Data(repeating: 0x22, count: 32), Data(repeating: 0x33, count: 32)]
        var nextKeyIndex = 0
        let store = SearchHashSecretStore(
            storage: storage,
            isConsentGranted: { consented },
            randomKeyProvider: {
                defer { nextKeyIndex += 1 }
                return fixedKeys[nextKeyIndex]
            }
        )

        // Unconsented: never reads or writes durable Keychain; holds ephemeral in memory only.
        let deniedFirst = AnalyticsPrivacy.hashQuery("lakers", keyData: store.currentKey())
        let deniedSecond = AnalyticsPrivacy.hashQuery("lakers", keyData: store.currentKey())
        XCTAssertEqual(deniedFirst, deniedSecond)
        XCTAssertEqual(storage.loadCount, 0)
        XCTAssertEqual(storage.saveCount, 0)
        XCTAssertNil(storage.storedKey)

        // Consented: creates and persists 256-bit key in device-only storage.
        consented = true
        let grantedKey = store.currentKey()
        XCTAssertEqual(grantedKey, Data(repeating: 0x22, count: 32))
        XCTAssertEqual(storage.saveCount, 1)
        XCTAssertEqual(storage.storedKey, grantedKey)
        let grantedHash = AnalyticsPrivacy.hashQuery("lakers", keyData: grantedKey)
        XCTAssertNotEqual(grantedHash, deniedFirst)

        // Revocation deletes persisted secret and rotates subsequent hashes.
        consented = false
        store.reset()
        XCTAssertEqual(storage.deleteCount, 1)
        XCTAssertNil(storage.storedKey)
        let afterResetHash = AnalyticsPrivacy.hashQuery("lakers", keyData: store.currentKey())
        XCTAssertNotEqual(afterResetHash, grantedHash)
        XCTAssertNotEqual(afterResetHash, deniedFirst)
    }

    func testResultClickJoinsBackToItsSearch() {
        let query = "who wins the open"
        let search = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(event: "search", parameters: ["search_term": query])
        )
        let click = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "search_result_click",
                parameters: ["query": query, "result_type": "event", "position": 1]
            )
        )
        XCTAssertEqual(
            search["query_hash"] as? String, click["query_hash"] as? String,
            "the funnel must remain joinable without the raw text"
        )
    }

    // MARK: - Fail-closed allowlists

    func testUnknownEventIsDropped() {
        XCTAssertNil(AnalyticsPrivacy.sanitize(event: "totally_new_event", parameters: ["a": 1]))
    }

    func testUnknownParameterKeysAreDropped() {
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "event_card_click",
                parameters: ["event_id": 5, "sport": "nba", "secret_note": "leak me"]
            )
        )
        XCTAssertNil(params["secret_note"])
        XCTAssertEqual(params["event_id"] as? Int, 5)
        XCTAssertEqual(params["sport"] as? String, "nba")
    }

    func testHardDropKeysNeverSurvive() {
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "event_card_click",
                parameters: [
                    "event_id": 5,
                    "email": "alex@example.com",
                    "token": "abc",
                    "url": "https://bainluck.com/x",
                    "password": "hunter2",
                ]
            )
        )
        for key in ["email", "token", "url", "password"] {
            XCTAssertNil(params[key], "\(key) must never reach Firebase")
        }
        XCTAssertEqual(params.count, 1)
    }

    // MARK: - Approved telemetry is preserved

    /// L2-217's My Stuff fields and the other latency rails must pass through
    /// untouched — the boundary is a privacy filter, not a telemetry rewrite.
    func testMyStuffAndLatencyFieldsSurvive() {
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "my_stuff_load",
                parameters: [
                    "stage": "required_data_ready",
                    "auth_ready_ms": 12.0,
                    "network_ms": 340.0,
                    "backend_elapsed_ms": -1,
                    "decode_ms": -1,
                    "required_data_ready_ms": 355.0,
                    "first_render_ms": -1,
                    "cache_outcome": "hit",
                    "cache_age_seconds": 42,
                    "item_count": 6,
                    "app_build": "1.4.2 (231)",
                    "surface": "my_stuff",
                    "outcome_class": "success",
                ]
            )
        )
        XCTAssertEqual(params.count, 13, "every approved My Stuff field survives")
        XCTAssertEqual(params["outcome_class"] as? String, "success")
        XCTAssertEqual(params["app_build"] as? String, "1.4.2 (231)")
        XCTAssertEqual(params["required_data_ready_ms"] as? Double, 355.0)
    }

    func testFeedSuppressionFieldsSurvive() {
        let params = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "feed_card_suppressed",
                parameters: [
                    "card_type": "concept",
                    "suppression_reason": "empty_envelope",
                    "count": 3,
                    "surface": "discover",
                ]
            )
        )
        XCTAssertEqual(params.count, 4)
        XCTAssertEqual(params["suppression_reason"] as? String, "empty_envelope")
    }

    func testScreenAndAuthEventsSurvive() {
        let screen = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(
                event: "screen_view",
                parameters: ["screen_name": "Discover", "page_type": "discover"]
            )
        )
        XCTAssertEqual(screen["screen_name"] as? String, "Discover")

        let login = try! XCTUnwrap(
            AnalyticsPrivacy.sanitize(event: "login", parameters: ["method": "apple"])
        )
        XCTAssertEqual(login["method"] as? String, "apple")
    }

    func testEventWithNoParametersIsStillAllowed() {
        let params = try! XCTUnwrap(AnalyticsPrivacy.sanitize(event: "logout", parameters: nil))
        XCTAssertTrue(params.isEmpty)
    }
}
