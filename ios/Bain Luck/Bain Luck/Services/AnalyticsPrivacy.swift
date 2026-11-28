import CryptoKit
import Foundation
import Security

/// Device-only backing store for the on-device search hash secret (`404: B`).
protocol SearchHashKeyStorage {
    func load() -> Data?
    @discardableResult
    func save(_ key: Data) -> Bool
    func delete()
}

struct SearchHashKeychainStorage: SearchHashKeyStorage {
    static let service = "com.bainluck.analytics.search-hash"
    static let account = "bainluck_search_hash_secret_v1"

    static var baseQuery: [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
    }

    static func saveAttributes(for key: Data) -> [String: Any] {
        var attrs = baseQuery
        attrs[kSecValueData as String] = key
        attrs[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return attrs
    }

    func load() -> Data? {
        var query = Self.baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data, data.count == 32 else {
            return nil
        }
        return data
    }

    @discardableResult
    func save(_ key: Data) -> Bool {
        SecItemDelete(Self.baseQuery as CFDictionary)
        let status = SecItemAdd(Self.saveAttributes(for: key) as CFDictionary, nil)
        return status == errSecSuccess
    }

    func delete() {
        SecItemDelete(Self.baseQuery as CFDictionary)
    }
}

final class SearchHashSecretStore: @unchecked Sendable {
    static let shared = SearchHashSecretStore()

    private let lock = NSLock()
    private var cachedPersistedKey: Data?
    private var ephemeralKey: Data?
    private let storage: any SearchHashKeyStorage
    private let isConsentGranted: () -> Bool
    private let randomKeyProvider: () -> Data

    init(
        storage: any SearchHashKeyStorage = SearchHashKeychainStorage(),
        isConsentGranted: @escaping () -> Bool = { TelemetryConsent.shared.isGranted },
        randomKeyProvider: @escaping () -> Data = SearchHashSecretStore.generateRandomKey
    ) {
        self.storage = storage
        self.isConsentGranted = isConsentGranted
        self.randomKeyProvider = randomKeyProvider
    }

    static func generateRandomKey() -> Data {
        var bytes = [UInt8](repeating: 0, count: 32)
        if SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess {
            return Data(bytes)
        }
        return SymmetricKey(size: .bits256).withUnsafeBytes { Data($0) }
    }

    func currentKey() -> Data {
        // Evaluate consent before taking `lock` so lock ordering stays acyclic.
        let consented = isConsentGranted()
        lock.lock()
        defer { lock.unlock() }

        if consented {
            if let cachedPersistedKey {
                return cachedPersistedKey
            }
            if let existing = storage.load() {
                cachedPersistedKey = existing
                return existing
            }
            let generated = randomKeyProvider()
            _ = storage.save(generated)
            cachedPersistedKey = generated
            return generated
        }

        if let ephemeralKey {
            return ephemeralKey
        }
        let generated = randomKeyProvider()
        ephemeralKey = generated
        return generated
    }

    func reset() {
        lock.lock()
        cachedPersistedKey = nil
        ephemeralKey = nil
        lock.unlock()
        storage.delete()
    }
}

/// The native analytics privacy boundary (L2-219, Item 2 / #1453, updated for 404: B).
///
/// BEFORE: `AnalyticsService.trackSearch` sent the user's RAW search text as
/// Firebase's `search_term`, and `trackSearchResultClick` sent it again as
/// `query`. Anything a user typed — an email, a phone number, a pasted URL or
/// token — went to Firebase verbatim and was retained there.
///
/// NOW: every native event passes through `sanitize` before it reaches
/// Firebase. Raw query text is replaced with bounded, keyed HMAC metadata,
/// and only allowlisted parameter keys survive — so a new caller cannot leak a
/// raw field by forgetting to think about it. The boundary is enforced by
/// omission (unknown keys are dropped), not by a denylist we would have to keep
/// ahead of.
///
/// Per Ruling `404: B`, `query_hash` uses CryptoKit `HMAC<SHA256>` with a random
/// 256-bit key held strictly on this device (`ThisDeviceOnly` Keychain when
/// telemetry consent is granted, ephemeral in-memory otherwise), truncated to
/// 64 bits (16 lowercase hex chars). Queries remain joinable within one device
/// while never leaving the device or exposing dictionary lookups across users.
enum AnalyticsPrivacy {
    // MARK: - Bounds

    /// Upper bound on a reported query length. An outlier length is itself a
    /// fingerprint, so it is clamped rather than reported faithfully.
    static let maxQueryLength = 200
    /// Upper bound on a reported word count, for the same reason.
    static let maxQueryWordCount = 50
    /// Upper bound on any free-form string parameter that survives the allowlist.
    static let maxStringLength = 100

    // MARK: - Query → bounded metadata

    /// Keyed, non-reversible 64-bit truncated HMAC-SHA-256 of the normalized
    /// query, rendered as 16 lowercase hex characters (`404: B`).
    ///
    /// Uses a random 256-bit secret that never leaves the device (stored in
    /// device-only Keychain only after `"Allow"` consent, or ephemeral in memory
    /// when unconsented).
    static func hashQuery(_ raw: String) -> String {
        hashQuery(raw, keyData: SearchHashSecretStore.shared.currentKey())
    }

    static func hashQuery(_ raw: String, keyData: Data) -> String {
        let normalized = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let key = SymmetricKey(data: keyData)
        let mac = HMAC<SHA256>.authenticationCode(for: Data(normalized.utf8), using: key)
        return mac.prefix(8).map { String(format: "%02x", $0) }.joined()
    }

    /// Delete the persisted device-only search hash key and rotate any cached
    /// secret when analytics consent is declined or revoked (`404: B`).
    static func resetSearchHashSecret() {
        SearchHashSecretStore.shared.reset()
    }

    /// The bounded, non-PII replacement for a raw query: a joinable hash, a
    /// clamped length, and a clamped word count. The raw text never leaves.
    static func queryMetadata(_ raw: String) -> [String: Any] {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        let words = trimmed.isEmpty
            ? 0
            : trimmed.split(whereSeparator: { $0.isWhitespace }).count
        return [
            "query_hash": hashQuery(raw),
            // UTF-16 count matches the web's `String.length`, so the same query
            // reports the same length on both surfaces.
            "query_length": min(trimmed.utf16.count, maxQueryLength),
            "query_word_count": min(words, maxQueryWordCount),
        ]
    }

    // MARK: - Allowlists

    /// Every event name the app is permitted to emit. Unknown names are DROPPED
    /// (fail-closed): a new event must be registered here deliberately, which is
    /// the moment its parameters get privacy review.
    static let allowedEventNames: Set<String> = [
        // Watch diagnostics use the same consent/privacy emission boundary.
        "watch_app_open", "watch_app_background", "watch_action", "watch_refresh", "watch_reading",
        // Screens / navigation
        "screen_view", "navigation_click", "return_visit",
        "session_open", "shared_link_open",
        // Follow & pin (#13261)
        "follow_team", "pin_item",
        // Events + futures
        "event_card_click", "event_detail_view", "chart_time_range", "futures_detail_view",
        // Search
        "search", "search_result_click",
        // Auth
        "login", "sign_up", "logout", "auth_sign_in_failed",
        // Onboarding
        "onboarding_start", "onboarding_step", "onboarding_complete", "onboarding_skip",
        // Discover
        "feed_card_impression", "feed_card_action", "filter_category",
        "discover_tuning_reset", "feed_card_suppressed", "prediction_submit",
        // Latency rails
        "discover_feed_cache", "discover_feed_first_render", "discover_feed_network",
        "sports_feed_stage", "sports_feed_first_render", "sports_feed_network",
        "my_stuff_load", "my_stuff_first_render",
        // The felt number, every screen, same packet as the web (latency/121).
        // The three rails above it are per-surface and differently shaped; this
        // one is the table.
        "screen_timing",
        // Push (Queue 311 A4 / #1159) — the client half of the digest funnel.
        // The server emits `push_sent`; this is the open that joins to it.
        "push_opened",
        // Notifications, Live Activities & widgets (#13261 rows 11–13)
        "push_permission_result", "live_activity_action", "widget_open",
        // Set hubs & game-page interactions (#13261 rows 9 & 10)
        "collection_hub_action", "game_page_action",
    ]

    /// Keys that must NEVER reach Firebase, even if some caller adds them. Raw
    /// `query`/`search_term` are listed here and handled by transformation
    /// instead; the rest are pure drops.
    static let hardDropKeys: Set<String> = [
        "query", "search_term", "q", "text", "raw_query",
        "result_id",
        "email", "user_email", "username", "name", "full_name",
        "token", "id_token", "access_token", "auth", "authorization", "password",
        "url", "link", "href", "referrer", "path",
        "phone", "address", "ip", "latitude", "longitude",
        "error_description", "description", "message", "detail",
        "localized_description", "debug_description",
    ]

    /// Every parameter key permitted to reach Firebase. Anything outside this
    /// set is dropped, including keys not yet imagined — that is the point.
    static let allowedParameterKeys: Set<String> = [
        // Derived query metadata (replaces raw text)
        "query_hash", "query_length", "query_word_count",
        // Screens / navigation
        "screen_name", "page_type", "click_type", "from_page", "to_page",
        "days_since_last", "session_number", "occurred_at_epoch",
        "is_first_session", "entry_type", "first_screen", "destination_type", "medium",
        // Follow & pin (#13261)
        "relation_type",
        // Entities (opaque ids and categorical labels — joinable, not personal)
        "event_id", "market_id", "item_id", "item_type", "result_type",
        "sport", "category", "status", "entry_method", "range", "surface", "source",
        // Auth / onboarding
        "method", "entry_point", "step", "step_name", "teams_count",
        "last_step_completed", "last_step_name",
        "error_domain", "error_code", "underlying_domain", "underlying_code",
        // Discover interaction
        "action", "position", "score", "results_count", "count",
        "affinity_count", "card_type", "suppression_reason",
        // Predictions
        "guess", "threshold", "actual_probability", "correct", "content_type",
        // Latency rails (L2-201 / L2-206 / L2-207 / L2-217)
        "outcome", "outcome_class", "stage", "success", "item_count",
        "cache_decode_ms", "network_ms", "decode_ms", "merge_ms", "data_ready_ms",
        "auth_ready_ms", "backend_elapsed_ms", "cache_store_ms", "cache_status",
        "cache_age_seconds", "cache_outcome", "required_data_ready_ms",
        "first_render_ms", "from_cache", "response_bytes", "app_build",
        // Screen timing (latency/121). Every one of these is a duration, a
        // count, or a bounded enum. `surface` is already allowed above and is a
        // screen slug, never an id. `entry` is cold|warm and `device_class` is
        // one of six coarse buckets — neither narrows to a person.
        "duration_ms", "transport_delay_ms",
        "entry", "shell_ms", "first_card_ms", "fold_ms", "interactive_ms",
        "card_count", "device_class", "network_class",
        // Notifications, Live Activities & widgets (#13261 rows 11–13)
        "destination_type", "widget_kind",
        // Push funnel join key (Queue 311 A4 / #1159). `payload_id` is a
        // CAMPAIGN id of the form `digest-YYYYMMDD` — a date and a surface
        // name. It identifies which send this open belongs to, not who opened
        // it: no user id, no device id, no market text. It passes the privacy
        // contract on its merits, which is worth stating rather than assuming,
        // because "id" in a key name is normally the reason to refuse.
        "payload_id",
        // Set hubs, game-page interactions & My Stuff pin presence (#13261 rows 9 & 10)
        "slug", "action_kind", "section", "has_pins", "state",
    ]

    // MARK: - Value scrubbing

    private static let emailPattern = try? NSRegularExpression(
        pattern: "[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", options: [.caseInsensitive]
    )
    private static let urlPattern = try? NSRegularExpression(
        pattern: "(https?://|www\\.)\\S+", options: [.caseInsensitive]
    )
    /// Phone / card / SSN-shaped digit runs. Deliberately does NOT treat `.` as
    /// a separator and is gated on a real digit count below — an early version
    /// that did both redacted the legitimate `app_build` tag `1.4.2 (231)` into
    /// `[number]`, silently destroying build attribution on every latency event.
    private static let longDigitsPattern = try? NSRegularExpression(
        pattern: "\\d[\\d\\-()\\s]{5,}\\d", options: []
    )

    /// Minimum count of ACTUAL digits before a run is treated as an identifier.
    /// A phone is 7+, a card 16, an SSN 9; a version string is not.
    private static let minRedactableDigits = 7

    /// A push campaign id: a lowercase surface name and a date, e.g.
    /// `digest-20260810`. Used to let `payload_id` through VERBATIM.
    ///
    /// It needs an exemption because a `YYYYMMDD` date is eight consecutive
    /// digits, which `scrub` correctly reads as identifier-shaped and rewrites
    /// to `[number]` — destroying the only thing that joins a client open to
    /// the server's `push_sent`. This is the `app_build` incident's exact shape
    /// (`1.4.2 (231)` once became `[number]`), caught this time by a test that
    /// asserted the value arrives intact rather than merely arrives.
    ///
    /// It is a SHAPE guard, not a trust exemption: a value that does not match
    /// this pattern is dropped rather than passed through unscrubbed, so a
    /// future caller cannot smuggle free text out under this key.
    private static let campaignIdPattern = try? NSRegularExpression(
        pattern: "^[a-z][a-z0-9_]{0,31}-\\d{8}$", options: []
    )

    /// Whether a string is a well-formed campaign id.
    static func isCampaignId(_ value: String) -> Bool {
        guard let campaignIdPattern else { return false }
        let range = NSRange(value.startIndex..., in: value)
        return campaignIdPattern.firstMatch(in: value, options: [], range: range) != nil
    }

    private static let slugPattern = try? NSRegularExpression(
        pattern: "^[a-z0-9][a-z0-9_-]{0,63}$", options: []
    )

    /// Shape guard for collection slugs so multi-word hyphenated slugs longer than
    /// `tokenPattern`'s 24-char limit (e.g. `academy-awards-best-picture`) pass intact
    /// while unbroken 24+ char random tokens or strings with URLs/emails/spaces drop.
    static func isSafeSlug(_ value: String) -> Bool {
        guard let slugPattern else { return false }
        let range = NSRange(value.startIndex..., in: value)
        guard slugPattern.firstMatch(in: value, options: [], range: range) != nil else { return false }
        return value.count < 24 || value.contains("-") || value.contains("_")
    }

    private static let errorDomainPattern = try? NSRegularExpression(
        pattern: "^[A-Za-z0-9._-]{1,64}$", options: []
    )

    /// Shape guard for bounded error domains (`ASAuthorizationErrorDomain`, `apiError.httpError`,
    /// `NSURLErrorDomain`) before generic `scrub()` runs — generic `tokenPattern` treats any
    /// 24+ char dot-free string such as `"ASAuthorizationErrorDomain"` as a token (#13516).
    static func sanitizeErrorDomain(_ value: String) -> String {
        guard let errorDomainPattern else { return "other" }
        let range = NSRange(value.startIndex..., in: value)
        guard errorDomainPattern.firstMatch(in: value, options: [], range: range) != nil else {
            return "other"
        }
        let lower = value.lowercased()
        if lower.contains("token") || lower.contains("secret") || lower.contains("bearer") {
            return "other"
        }
        if value.filter(\.isNumber).count >= minRedactableDigits {
            return "other"
        }
        return value
    }
    private static let tokenPattern = try? NSRegularExpression(
        pattern: "[A-Za-z0-9_\\-]{24,}", options: []
    )

    /// Redact PII-shaped substrings from an allowlisted free-form string and
    /// bound its length. Defense in depth: the allowlist already excludes the
    /// fields where PII belongs, but a categorical field could still be handed
    /// user text by a future caller.
    static func scrub(_ value: String) -> String {
        var out = value
        for (pattern, token) in [
            (emailPattern, "[email]"),
            (urlPattern, "[url]"),
            (tokenPattern, "[token]"),
        ] {
            guard let pattern else { continue }
            out = pattern.stringByReplacingMatches(
                in: out,
                options: [],
                range: NSRange(out.startIndex..., in: out),
                withTemplate: token
            )
        }

        // Digit runs are replaced only when they carry enough digits to be an
        // identifier, so version/build strings survive intact. Applied
        // last-match-first so earlier ranges stay valid while mutating.
        if let longDigitsPattern {
            let matches = longDigitsPattern.matches(
                in: out, options: [], range: NSRange(out.startIndex..., in: out)
            )
            for match in matches.reversed() {
                guard let range = Range(match.range, in: out) else { continue }
                let digits = out[range].filter(\.isNumber).count
                guard digits >= minRedactableDigits else { continue }
                out.replaceSubrange(range, with: "[number]")
            }
        }

        if out.count > maxStringLength {
            out = String(out.prefix(maxStringLength))
        }
        return out
    }

    // MARK: - The boundary

    /// Sanitize an event immediately before it is handed to Firebase.
    ///
    /// Returns `nil` when the event name is not registered, in which case
    /// nothing is emitted at all. Otherwise returns only allowlisted, scrubbed
    /// parameters, with any raw `query`/`search_term` replaced by bounded
    /// metadata.
    static func sanitize(event name: String, parameters: [String: Any]?) -> [String: Any]? {
        guard allowedEventNames.contains(name) else { return nil }

        var out: [String: Any] = [:]
        let input = parameters ?? [:]

        // Raw query → bounded metadata (joinable, non-reversible). Checked under
        // both spellings because Firebase's own constant is `search_term`.
        for key in ["query", "search_term", "raw_query"] {
            if let raw = input[key] as? String {
                out.merge(queryMetadata(raw)) { current, _ in current }
                break
            }
        }

        for (key, value) in input {
            if hardDropKeys.contains(key) { continue }
            guard allowedParameterKeys.contains(key) else { continue }
            if key == "payload_id" {
                // Shape-checked rather than scrubbed: the campaign id must
                // arrive byte-identical to the server's or it joins nothing,
                // and `scrub` would rewrite its date to `[number]`. Anything
                // not matching the campaign shape is dropped outright.
                if let string = value as? String, isCampaignId(string) {
                    out[key] = string
                }
                continue
            }
            if key == "slug" {
                if let string = value as? String, isSafeSlug(string) {
                    out[key] = string
                }
                continue
            }
            if key == "error_domain" || key == "underlying_domain" {
                if let string = value as? String {
                    out[key] = sanitizeErrorDomain(string)
                }
                continue
            }
            if let string = value as? String {
                out[key] = scrub(string)
            } else {
                out[key] = value
            }
        }

        return out
    }
}
