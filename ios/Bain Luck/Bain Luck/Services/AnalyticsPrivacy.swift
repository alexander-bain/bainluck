import Foundation

/// The native analytics privacy boundary (L2-219, Item 2 / #1453).
///
/// BEFORE: `AnalyticsService.trackSearch` sent the user's RAW search text as
/// Firebase's `search_term`, and `trackSearchResultClick` sent it again as
/// `query`. Anything a user typed — an email, a phone number, a pasted URL or
/// token — went to Firebase verbatim and was retained there. The web rail had
/// already closed this hole (`lib/analytics/sanitize.ts`); native had not.
///
/// NOW: every native event passes through `sanitize` before it reaches
/// Firebase. Raw query text is replaced with bounded, non-reversible metadata,
/// and only allowlisted parameter keys survive — so a new caller cannot leak a
/// raw field by forgetting to think about it. The boundary is enforced by
/// omission (unknown keys are dropped), not by a denylist we would have to keep
/// ahead of.
///
/// The hash is deliberately bit-identical to the web implementation
/// (`hashQuery` in `lib/analytics/sanitize.ts`): FNV-1a over UTF-16 code units
/// of the trimmed, lowercased text, rendered base36. The same query typed on
/// web and on iOS therefore produces the same `query_hash`, which is what makes
/// the search funnel joinable across surfaces without ever sending the text.
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

    /// Stable, non-reversible 32-bit FNV-1a hash of the normalized query,
    /// base36. Not cryptographic — it exists to bucket and join, not to secure.
    ///
    /// Normalization (trim + lowercase) and the UTF-16 iteration order match the
    /// web implementation exactly; changing either silently breaks cross-surface
    /// joins, so `AnalyticsPrivacyTests` pins known values.
    static func hashQuery(_ raw: String) -> String {
        let normalized = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        var hash: UInt32 = 0x811c_9dc5
        for unit in normalized.utf16 {
            hash ^= UInt32(unit)
            hash = hash &* 0x0100_0193
        }
        return String(hash, radix: 36)
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
        // Screens / navigation
        "screen_view", "navigation_click", "return_visit",
        // Events + futures
        "event_card_click", "event_detail_view", "chart_time_range", "futures_detail_view",
        // Search
        "search", "search_result_click",
        // Auth
        "login", "sign_up", "logout",
        // Onboarding
        "onboarding_start", "onboarding_step", "onboarding_complete", "onboarding_skip",
        // Discover
        "feed_card_impression", "feed_card_action", "filter_category",
        "discover_tuning_reset", "feed_card_suppressed", "prediction_submit",
        // Latency rails
        "discover_feed_cache", "discover_feed_first_render", "discover_feed_network",
        "sports_feed_stage", "sports_feed_first_render",
        "my_stuff_load", "my_stuff_first_render",
    ]

    /// Keys that must NEVER reach Firebase, even if some caller adds them. Raw
    /// `query`/`search_term` are listed here and handled by transformation
    /// instead; the rest are pure drops.
    static let hardDropKeys: Set<String> = [
        "query", "search_term", "q", "text", "raw_query",
        "email", "user_email", "username", "name", "full_name",
        "token", "id_token", "access_token", "auth", "authorization", "password",
        "url", "link", "href", "referrer", "path",
        "phone", "address", "ip", "latitude", "longitude",
    ]

    /// Every parameter key permitted to reach Firebase. Anything outside this
    /// set is dropped, including keys not yet imagined — that is the point.
    static let allowedParameterKeys: Set<String> = [
        // Derived query metadata (replaces raw text)
        "query_hash", "query_length", "query_word_count",
        // Screens / navigation
        "screen_name", "page_type", "click_type", "from_page", "to_page",
        "days_since_last", "session_number",
        // Entities (opaque ids and categorical labels — joinable, not personal)
        "event_id", "market_id", "item_id", "item_type", "result_type", "result_id",
        "sport", "category", "status", "entry_method", "range", "surface", "source",
        // Auth / onboarding
        "method", "step", "step_name", "teams_count",
        "last_step_completed", "last_step_name",
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
            if let string = value as? String {
                out[key] = scrub(string)
            } else {
                out[key] = value
            }
        }

        return out
    }
}
