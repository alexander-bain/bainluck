import Foundation

// MARK: - API Errors

enum APIError: LocalizedError {
    case invalidURL
    case httpError(statusCode: Int, body: String?)
    case decodingError(underlying: Error)
    case networkError(underlying: Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .httpError(let code, _):
            if code == 503 { return "Server is temporarily unavailable. Pull to refresh." }
            if code >= 500 { return "Server error (\(code)). Try again in a moment." }
            return "Request failed (\(code))."
        case .decodingError:
            return "Couldn't read the response. Try again."
        case .networkError:
            return "No connection. Check your network and try again."
        }
    }

    var isCancellation: Bool {
        if case .networkError(let underlying) = self {
            let nsError = underlying as NSError
            return nsError.domain == NSURLErrorDomain && nsError.code == NSURLErrorCancelled
        }
        return false
    }
}

// MARK: - API Client

actor APIClient {
    static let shared = APIClient()

    private let baseURL = "https://api.bainluck.com"
    private let session: URLSession
    private let decoder: JSONDecoder

    /// In-memory response cache with TTL
    private var responseCache: [String: CacheEntry] = [:]

    private struct CacheEntry {
        let data: Data
        let timestamp: Date
    }

    /// Disk-backed last-good Discover feed cache (L2-197 / #1465). Persists the
    /// raw offset-0 `/api/feed` body so a repeat launch can render a first card
    /// immediately instead of blocking on the 9–13s cold server miss (#1459).
    private let feedCache = DiscoverFeedCache()

    /// Backend user id of the signed-in account, or nil when anonymous. Pushed by
    /// `AuthManager` on sign-in/out/restore; partitions the feed cache namespace.
    /// Seeded at init from the last-known persisted id so a returning signed-in
    /// user's cache namespace is ready BEFORE async session restore
    /// (`fetchProfile()`) completes — otherwise the first cold cache read lands in
    /// the anonymous namespace and misses the user's last-good feed (L2-206 Item 1).
    private var feedCacheUserId: String? = APIClient.persistedLastKnownUserId()

    /// UserDefaults key for the last-known signed-in backend user id. Stores ONLY
    /// the public user id (never a token/credential) — it merely tells the client
    /// which last-good cache file to read at cold launch; a valid session token is
    /// still required for every network call. Cleared on sign-out / failed restore.
    private static let lastKnownUserIdKey = "bainluck_last_known_user_id"

    /// The last-known signed-in user id from the previous session, or nil. Read at
    /// cold launch (by `APIClient` and `AuthManager`) so the feed-cache namespace is
    /// resolved before async session restore completes (L2-206 Item 1). Nonisolated
    /// static — a plain UserDefaults read, safe from any actor.
    static func persistedLastKnownUserId() -> String? {
        let id = UserDefaults.standard.string(forKey: lastKnownUserIdKey)
        return (id?.isEmpty == false) ? id : nil
    }

    /// Set by the auth module later. Returns a Firebase ID token or backend session token.
    var authTokenProvider: (() async -> String?)?

    /// Persistent session ID for anonymous prediction tracking
    private let sessionId: String = {
        let key = "bainluck_session_id"
        if let existing = UserDefaults.standard.string(forKey: key) {
            return existing
        }
        let id = UUID().uuidString
        UserDefaults.standard.set(id, forKey: key)
        return id
    }()

    /// Installs the auth token source used to attach Bearer credentials to API requests.
    func setAuthTokenProvider(_ provider: (() async -> String?)?) {
        authTokenProvider = provider
    }

    // MARK: - Discover Feed Cache Identity (#1465)

    /// Update the feed-cache identity when the signed-in account changes. On a
    /// real change (login, logout, account switch) every other namespace is
    /// evicted so no prior user's — or signed-out — last-good can surface under
    /// the new identity. Called by `AuthManager` whenever `user` changes.
    func setFeedCacheIdentity(userId: String?) {
        guard userId != feedCacheUserId else { return }
        feedCacheUserId = userId
        // Persist the new identity so the NEXT cold launch reads the correct cache
        // namespace before restore completes (L2-206 Item 1). Empty/nil → anonymous.
        if let userId, !userId.isEmpty {
            UserDefaults.standard.set(userId, forKey: Self.lastKnownUserIdKey)
        } else {
            UserDefaults.standard.removeObject(forKey: Self.lastKnownUserIdKey)
        }
        feedCache.evict(keepingOnly: currentFeedIdentity())
    }

    /// The current feed-cache namespace (signed-in user id, else anonymous session).
    private func currentFeedIdentity() -> String {
        DiscoverFeedCache.identity(userId: feedCacheUserId, sessionId: sessionId)
    }

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    // MARK: - Generic Fetch

    private func fetch<T: Decodable & Sendable>(
        _ path: String,
        query: [String: String] = [:],
        cacheTTL: TimeInterval? = nil
    ) async throws -> sending T {
        // Check cache
        let cacheKey: String?
        if let ttl = cacheTTL {
            let key = path + "?" + query.sorted(by: { $0.key < $1.key })
                .map { "\($0.key)=\($0.value)" }.joined(separator: "&")
            cacheKey = key
            if let entry = responseCache[key],
               Date().timeIntervalSince(entry.timestamp) < ttl {
                return try decoder.decode(T.self, from: entry.data)
            }
        } else {
            cacheKey = nil
        }

        var components = URLComponents(string: baseURL + path)
        if !query.isEmpty {
            components?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components?.url else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(sessionId, forHTTPHeaderField: "x-session-id")

        if let provider = authTokenProvider, let token = await provider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(underlying: error)
        }

        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: http.statusCode, body: body)
        }

        // Store in cache
        if let key = cacheKey {
            responseCache[key] = CacheEntry(data: data, timestamp: Date())
            cleanCacheIfNeeded()
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(underlying: error)
        }
    }

    /// Like `fetch`, but also returns the raw response bytes and a network/decode
    /// timing split (#1465). Used for the Discover feed so the offset-0 body can
    /// be persisted byte-for-byte as last-good and the cold-vs-warm cost measured.
    /// Intentionally bypasses the in-memory TTL cache (the feed always sends
    /// `cacheTTL: nil`) so the raw bytes are always the fresh server response.
    /// Milestone-attributed feed fetch (L2-201 / #1472). Beyond the raw bytes it
    /// returns a per-stage timing split — local auth-token resolution
    /// (`authReadyMs`), network round-trip (`networkMs`), payload decode
    /// (`decodeMs`) — plus the backend's own build time (`X-Feed-Elapsed-Ms`), the
    /// server cache status (`X-Feed-Cache`), and the response byte size, so one
    /// trace can attribute latency to auth vs network+backend vs decode rather
    /// than a single opaque total. Carries no PII, token, or payload text.
    private func fetchRaw<T: Decodable & Sendable>(
        _ path: String,
        query: [String: String] = [:]
    ) async throws -> (
        value: T, raw: Data,
        authReadyMs: Double, networkMs: Double, decodeMs: Double,
        backendElapsedMs: Double?, cacheStatus: String?, responseBytes: Int
    ) {
        var components = URLComponents(string: baseURL + path)
        if !query.isEmpty {
            components?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components?.url else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(sessionId, forHTTPHeaderField: "x-session-id")

        // Auth-ready milestone: the token provider is a local Keychain read (see
        // AuthManager), NOT a network refresh, so an anonymous fetch (nil
        // provider) waits on nothing and a signed-in fetch reuses the cached
        // credential. Measured so telemetry can prove that, not because it blocks.
        let authStart = Date()
        if let provider = authTokenProvider, let token = await provider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let authReadyMs = Date().timeIntervalSince(authStart) * 1000

        let netStart = Date()
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(underlying: error)
        }
        let networkMs = Date().timeIntervalSince(netStart) * 1000

        var backendElapsedMs: Double?
        var cacheStatus: String?
        if let http = response as? HTTPURLResponse {
            if !(200...299).contains(http.statusCode) {
                throw APIError.httpError(statusCode: http.statusCode, body: String(data: data, encoding: .utf8))
            }
            if let elapsed = http.value(forHTTPHeaderField: "X-Feed-Elapsed-Ms") {
                backendElapsedMs = Double(elapsed)
            }
            cacheStatus = http.value(forHTTPHeaderField: "X-Feed-Cache")
        }

        let decodeStart = Date()
        do {
            let value = try decoder.decode(T.self, from: data)
            let decodeMs = Date().timeIntervalSince(decodeStart) * 1000
            return (value, data, authReadyMs, networkMs, decodeMs, backendElapsedMs, cacheStatus, data.count)
        } catch {
            throw APIError.decodingError(underlying: error)
        }
    }

    // MARK: - Generic POST (Encodable body)

    private func postEncodable<B: Encodable & Sendable, T: Decodable & Sendable>(
        _ path: String,
        body: B,
        timeout: TimeInterval? = nil
    ) async throws -> sending T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(sessionId, forHTTPHeaderField: "x-session-id")
        if let timeout {
            request.timeoutInterval = timeout
        }

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        request.httpBody = try encoder.encode(body)

        if let provider = authTokenProvider, let token = await provider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(underlying: error)
        }

        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(underlying: error)
        }
    }

    // MARK: - Generic DELETE

    private func delete<T: Decodable & Sendable>(_ path: String, query: [String: String] = [:]) async throws -> sending T {
        var components = URLComponents(string: baseURL + path)
        if !query.isEmpty {
            components?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components?.url else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if let provider = authTokenProvider, let token = await provider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(underlying: error)
        }

        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(underlying: error)
        }
    }

    // MARK: - Generic PUT (Encodable body)

    private func putEncodable<B: Encodable & Sendable, T: Decodable & Sendable>(_ path: String, body: B) async throws -> sending T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        request.httpBody = try encoder.encode(body)

        if let provider = authTokenProvider, let token = await provider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(underlying: error)
        }

        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(underlying: error)
        }
    }

    // MARK: - Generic PATCH (Encodable body)

    private func patchEncodable<B: Encodable & Sendable, T: Decodable & Sendable>(_ path: String, body: B) async throws -> sending T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "PATCH"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        request.httpBody = try encoder.encode(body)

        if let provider = authTokenProvider, let token = await provider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(underlying: error)
        }

        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(underlying: error)
        }
    }

    // MARK: - Generic POST (Dictionary body)

    private func post<T: Decodable & Sendable>(_ path: String, body: [String: String?]) async throws -> sending T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        // Filter nil values and encode
        let filtered = body.compactMapValues { $0 }
        request.httpBody = try JSONSerialization.data(withJSONObject: filtered)

        if let provider = authTokenProvider, let token = await provider() {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(underlying: error)
        }

        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8)
            throw APIError.httpError(statusCode: http.statusCode, body: body)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(underlying: error)
        }
    }

    // MARK: - Cache Cleanup

    private func cleanCacheIfNeeded() {
        guard responseCache.count > 100 else { return }
        let now = Date()
        responseCache = responseCache.filter { now.timeIntervalSince($0.value.timestamp) < 300 }
    }

    // MARK: - Feed

    /// Fetches the main Discover feed with optional sport, tag, and content-type filters.
    ///
    /// `mode` selects the backend feed contract (L2-207 / #1480): pass `"sports"`
    /// for the native Sports tab's fast path (`_score_sports_mode_futures` — a
    /// single top-sports-futures query, skipping the ~10-query editorial Discover
    /// pipeline). When nil, an unparameterized main-feed request is normalized to
    /// Discover server-side (`feed.py` Discover-default guard). Only the
    /// backend's allowlisted values are meaningful; any other string falls through
    /// to the server's default handling.
    func fetchFeed(
        sport: String? = nil,
        limit: Int = 50,
        offset: Int = 0,
        myTeamsOnly: Bool = false,
        includeFutures: Bool = true,
        includeEvents: Bool = true,
        eventPct: Double? = nil,
        mode: String? = nil,
        tags: [String]? = nil,
        cacheTTL: TimeInterval? = 30
    ) async throws -> FeedResponse {
        var q: [String: String] = [
            "limit": "\(limit)",
            "offset": "\(offset)",
        ]
        if let sport { q["sport"] = sport }
        if myTeamsOnly { q["my_teams_only"] = "true" }
        if !includeFutures { q["include_futures"] = "false" }
        if !includeEvents { q["include_events"] = "false" }
        if let eventPct { q["event_pct"] = String(eventPct) }
        if let mode { q["mode"] = mode }
        if let tags, !tags.isEmpty,
           let data = try? JSONSerialization.data(withJSONObject: tags),
           let str = String(data: data, encoding: .utf8) {
            q["tags"] = str
        }
        return try await fetch("/api/feed", query: q, cacheTTL: cacheTTL)
    }

    /// Fetch the offset-0 Discover feed AND persist its raw body as last-good for
    /// the current identity (#1465). The stale-while-revalidate path in
    /// `DiscoverViewModel` reads this back on the next cold launch to render a
    /// first card immediately. Only the offset-0 page is cached — pagination
    /// pages are transient. Persistence and network telemetry are best-effort and
    /// never block or fail the fetch. Non-offset-0 calls fall through to `fetchFeed`.
    func fetchFeedPersistingLastGood(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        guard offset == 0 else {
            return try await fetchFeed(limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL)
        }

        var q: [String: String] = ["limit": "\(limit)", "offset": "0"]
        if let eventPct { q["event_pct"] = String(eventPct) }

        // Capture the identity at fetch time so a mid-flight account switch cannot
        // cause this response to be written under the WRONG namespace (L2-206 Item 2).
        let identityAtFetch = currentFeedIdentity()

        let result: (
            value: FeedResponse, raw: Data,
            authReadyMs: Double, networkMs: Double, decodeMs: Double,
            backendElapsedMs: Double?, cacheStatus: String?, responseBytes: Int
        ) = try await fetchRaw("/api/feed", query: q)

        // Persist last-good OFF the first-card path (L2-206 Item 2): the decoded
        // value returns immediately so the view publishes a first card without
        // waiting on file I/O. This unstructured `Task` inherits the APIClient
        // actor's isolation, so it runs AFTER this method returns (never blocking
        // the caller) and serializes with `setFeedCacheIdentity`'s eviction: the
        // identity re-check plus eviction-on-switch guarantees a superseded
        // identity's bytes never persist (either the guard fails, or a later evict
        // removes them). Store time is reported for observability only.
        let raw = result.raw
        let net = result
        Task {
            let storeMs: Double?
            if identityAtFetch == currentFeedIdentity() {
                let t0 = Date()
                feedCache.store(rawBody: raw, identity: identityAtFetch, storedAt: Date())
                storeMs = Date().timeIntervalSince(t0) * 1000
            } else {
                storeMs = nil
            }
            AnalyticsService.trackDiscoverFeedNetwork(
                networkMs: net.networkMs,
                decodeMs: net.decodeMs,
                itemCount: net.value.items.count,
                authReadyMs: net.authReadyMs,
                backendElapsedMs: net.backendElapsedMs,
                responseBytes: net.responseBytes,
                cacheStatus: net.cacheStatus,
                cacheStoreMs: storeMs
            )
        }
        return result.value
    }

    /// Read the last-good Discover payload for the current identity (#1465), or
    /// nil when none exists. Fails closed on any corrupt/foreign entry.
    func loadLastGoodFeed() -> CachedDiscoverFeed? {
        feedCache.load(identity: currentFeedIdentity())
    }

    // MARK: - Grouped Futures Feed

    /// Fetches grouped futures cards for deduplicated market browsing.
    func fetchGroupedFeed(limit: Int = 20, offset: Int = 0) async throws -> GroupedFeedResponse {
        let q: [String: String] = [
            "limit": "\(limit)",
            "offset": "\(offset)",
        ]
        return try await fetch("/api/futures/grouped-feed", query: q, cacheTTL: 60)
    }

    // MARK: - Event Detail

    /// Fetches a game or event detail page by backend event ID.
    func fetchEvent(id: Int) async throws -> EventDetail {
        return try await fetch("/api/events/\(id)", cacheTTL: 15)
    }

    /// Fetches cached line movement analysis and explanation for an event.
    func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse {
        return try await fetch("/api/events/\(eventId)/line-movement", cacheTTL: 900)
    }

    // MARK: - Event History

    /// Fetches win-probability history for an event over the requested trailing window.
    func fetchEventHistory(id: Int, hours: Int = 24) async throws -> EventHistoryResponse {
        return try await fetch("/api/events/\(id)/history", query: ["hours": "\(hours)"], cacheTTL: 60)
    }

    // MARK: - Related Futures

    /// Fetches season futures and related markets attached to an event detail page.
    func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
        return try await fetch("/api/events/\(eventId)/related-futures", cacheTTL: 60)
    }

    // MARK: - Team Progression (Championship Path)

    /// Fetches championship-path progression data for teams in a specific event.
    func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse {
        return try await fetch("/api/events/\(eventId)/team-progression", cacheTTL: 120)
    }

    // MARK: - Game Markets (Player Props, Spreads, Totals)

    /// Fetches linked prediction markets, props, spreads, and totals for an event.
    func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse {
        return try await fetch("/api/events/\(eventId)/game-markets", cacheTTL: 60)
    }

    // MARK: - Search

    /// Searches event pages by text query, with optional sport scoping and pagination.
    func fetchSearch(query: String, sport: String? = nil, page: Int = 1) async throws -> SearchResponse {
        var q: [String: String] = ["q": query, "page": "\(page)"]
        if let sport { q["sport"] = sport }
        return try await fetch("/api/events/search", query: q)
    }

    // MARK: - Typeahead

    /// Fetches lightweight search suggestions for the current query text.
    func fetchTypeahead(query: String) async throws -> TypeaheadResponse {
        return try await fetch("/api/events/typeahead", query: ["q": query])
    }

    /// Fetches cached trending search suggestions for the search UI.
    func fetchTrendingSearches() async throws -> TrendingSearchesResponse {
        return try await fetch("/api/events/search/trending", cacheTTL: 300)
    }

    // MARK: - Team Page

    /// Fetches the team page summary, events, and market context by team slug.
    func fetchTeamPage(slug: String) async throws -> TeamPageResponse {
        return try await fetch("/api/teams/\(slug)")
    }

    // MARK: - Futures Detail

    /// Fetches a futures market detail page by backend market ID.
    func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail {
        return try await fetch("/api/futures/\(id)")
    }

    /// Fetches outcome probability history for a futures market.
    func fetchProbabilityTimeline(marketId: Int, top: Int = 50, hours: Int = 168) async throws -> ProbabilityTimelineResponse {
        return try await fetch("/api/futures/\(marketId)/probability-timeline", query: [
            "top": "\(top)",
            "hours": "\(hours)",
        ])
    }

    // MARK: - EI Rankings

    /// Fetches event importance rankings, optionally scoped to one sport.
    func fetchEIRankings(sport: String? = nil, limit: Int = 25) async throws -> EIRankingsResponse {
        var q: [String: String] = ["limit": "\(limit)"]
        if let sport { q["sport"] = sport }
        return try await fetch("/api/events/ei-rankings", query: q)
    }

    // MARK: - Faceted Search

    /// Fetches browseable event results filtered by tags and date range.
    func fetchFacetedEvents(tags: [String] = [], page: Int = 1, days: Int = 14) async throws -> FacetedEventsResponse {
        var q: [String: String] = [
            "page": "\(page)",
            "per_page": "20",
            "days": "\(days)",
        ]
        if !tags.isEmpty, let json = try? JSONSerialization.data(withJSONObject: tags),
           let str = String(data: json, encoding: .utf8) {
            q["tags"] = str
        }
        return try await fetch("/api/events/faceted", query: q, cacheTTL: 30)
    }

    /// Fetches browseable futures results filtered by tags, with optional sort order.
    func fetchFacetedFutures(tags: [String] = [], page: Int = 1, search: String? = nil, sort: String? = nil) async throws -> FacetedFuturesResponse {
        var q: [String: String] = [
            "page": "\(page)",
            "per_page": "20",
        ]
        if !tags.isEmpty, let json = try? JSONSerialization.data(withJSONObject: tags),
           let str = String(data: json, encoding: .utf8) {
            q["tags"] = str
        }
        if let search, !search.isEmpty {
            q["q"] = search
        }
        if let sort, !sort.isEmpty {
            q["sort"] = sort
        }
        return try await fetch("/api/futures/faceted", query: q, cacheTTL: 30)
    }

    /// Fetches futures markets with the biggest probability changes in the last N hours.
    func fetchFuturesMovers(hours: Int = 24, limit: Int = 10) async throws -> FuturesMoversResponse {
        return try await fetch("/api/futures/movers", query: [
            "hours": "\(hours)",
            "limit": "\(limit)",
        ], cacheTTL: 60)
    }

    // MARK: - Auth

    /// Exchanges an Apple identity token for a Bain Luck backend session.
    func signInWithApple(idToken: String, firstName: String?, lastName: String?) async throws -> AppleAuthResponse {
        return try await post("/api/auth/apple", body: [
            "id_token": idToken,
            "first_name": firstName,
            "last_name": lastName,
        ])
    }

    // MARK: - Weather

    /// Fetches featured weather prediction markets for the weather dashboard.
    func fetchWeatherFeatured() async throws -> [WeatherFeaturedItem] {
        return try await fetch("/api/weather/featured", cacheTTL: 120)
    }

    /// Fetches supported cities and regions for weather market browsing.
    func fetchWeatherCities() async throws -> [WeatherCity] {
        return try await fetch("/api/weather/cities", cacheTTL: 120)
    }

    // MARK: - Economics

    /// Fetches grouped economics markets for the economics dashboard.
    func fetchEconomics() async throws -> EconomicsResponse {
        return try await fetch("/api/economics", cacheTTL: 120)
    }

    // MARK: - Politics

    /// Fetches grouped politics markets for the politics dashboard.
    func fetchPolitics() async throws -> PoliticsResponse {
        return try await fetch("/api/politics", cacheTTL: 120)
    }

    // MARK: - Entertainment

    /// Fetches grouped entertainment markets for the entertainment dashboard.
    func fetchEntertainment() async throws -> EntertainmentResponse {
        return try await fetch("/api/entertainment", cacheTTL: 120)
    }

    // MARK: - League Markets

    /// Fetches league-level futures, standings, and market sections by sport key.
    func fetchLeagueMarkets(sportKey: String) async throws -> LeagueMarketsResponse {
        return try await fetch("/api/leagues/\(sportKey)", cacheTTL: 120)
    }

    // MARK: - Auth

    /// Exchanges a Google access token for a Bain Luck backend session.
    func signInWithGoogle(accessToken: String) async throws -> AppleAuthResponse {
        return try await post("/api/auth/google-access-token", body: [
            "access_token": accessToken,
        ])
    }

    /// Fetches the currently authenticated user's profile.
    func fetchProfile() async throws -> AuthUser {
        return try await fetch("/api/auth/me")
    }

    /// Checks whether the current session is authenticated.
    func fetchAuthStatus() async throws -> AuthStatusResponse {
        return try await fetch("/api/auth/status")
    }

    /// Deletes the currently authenticated user's account and all associated data.
    func deleteAccount() async throws -> [String: String] {
        return try await delete("/api/auth/me")
    }

    // MARK: - Onboarding

    /// Searches teams near a location during onboarding.
    func searchTeamsByLocation(query: String) async throws -> [TeamSearchResult] {
        return try await fetch("/api/me/teams/by-location", query: ["q": query])
    }

    /// Searches teams by name during onboarding and preference editing.
    func searchTeams(query: String) async throws -> [TeamSearchResult] {
        return try await fetch("/api/me/teams/search", query: ["q": query])
    }

    /// Submits onboarding preferences and favorite teams for the current user.
    func submitOnboarding(_ submission: OnboardingSubmission) async throws -> OnboardingResponse {
        return try await postEncodable("/api/me/onboarding", body: submission)
    }

    // MARK: - Preferences

    /// Fetches saved user preferences, favorite teams, and sport affinities.
    func fetchPreferences() async throws -> PreferencesResponse {
        return try await fetch("/api/me/preferences")
    }

    /// Removes a favorite-team relation from the current user's preferences.
    func removeFavorite(teamId: Int, relationType: String) async throws -> StatusResponse {
        return try await delete("/api/me/favorites/\(teamId)", query: ["relation_type": relationType])
    }

    /// Updates per-sport affinity weights used for personalization.
    func updateSportAffinities(_ affinities: [String: Double]) async throws -> StatusResponse {
        let body = SportAffinitiesUpdate(sportAffinities: affinities)
        return try await putEncodable("/api/me/preferences/sport-affinities", body: body)
    }

    /// Updates the authenticated user's Morning Digest push preference.
    func updatePushPreferences(morningDigest: Bool) async throws -> UpdatePushPreferencesResponse {
        let body = UpdatePushPreferencesRequest(morningDigest: morningDigest)
        return try await patchEncodable("/api/me/preferences/push", body: body)
    }

    // MARK: - Pins

    /// Fetches the current user's pinned events and futures.
    func fetchPins() async throws -> PinsResponse {
        return try await fetch("/api/me/pins")
    }

    // MARK: - Team Futures

    /// Fetches futures related to the current user's favorite teams.
    func fetchMyTeamFutures(limit: Int = 100) async throws -> TeamFuturesResponse {
        return try await fetch("/api/me/team-futures", query: ["limit": "\(limit)"], cacheTTL: 300)
    }

    // MARK: - Championship Grids

    /// Fetches a championship-grid page by playoff or league slug.
    func fetchChampionshipGrid(slug: String) async throws -> ChampionshipGridResponse {
        return try await fetch("/api/playoffs/\(slug)", cacheTTL: 300)
    }

    // MARK: - Golf

    /// Fetches golf landing-page markets and tournament summaries.
    func fetchGolfLanding() async throws -> GolfLandingResponse {
        return try await fetch("/api/golf", cacheTTL: 120)
    }

    /// Fetches the live golf leaderboard and win probabilities for a tour.
    func fetchGolfLeaderboard(tour: String = "pga") async throws -> GolfLeaderboardResponse {
        return try await fetch("/api/golf/leaderboard", query: ["tour": tour], cacheTTL: 30)
    }

    /// Pins an event or futures market for the current user.
    func addPin(type: String, id: Int) async throws -> StatusResponse {
        return try await postEncodable("/api/me/pins", body: PinRequest(pinType: type, targetId: id))
    }

    /// Removes an event or futures-market pin for the current user.
    func removePin(type: String, id: Int) async throws -> StatusResponse {
        return try await delete("/api/me/pins/\(type)/\(id)")
    }

    // MARK: - Predictions

    /// Submits a Higher/Lower prediction for a Discover market.
    func submitPrediction(_ body: PredictionRequest) async throws -> StatusResponse {
        return try await postEncodable("/api/predictions", body: body)
    }

    /// Fetches summary prediction stats for the current session or user.
    func fetchPredictionStats() async throws -> PredictionStats {
        return try await fetch("/api/predictions/stats")
    }

    /// Fetches detailed prediction performance stats for the stats screen.
    func fetchDetailedPredictionStats() async throws -> DetailedPredictionStats {
        return try await fetch("/api/predictions/detailed-stats")
    }

    /// Fetches recently resolved predictions for result review.
    func fetchResolutions() async throws -> ResolutionsResponse {
        return try await fetch("/api/predictions/resolutions")
    }

    /// Records a Discover card interaction for feed personalization.
    func recordDiscoverInteraction(_ event: DiscoverInteractionEvent) async throws -> StatusResponse {
        return try await postEncodable("/api/feed/interactions", body: DiscoverInteractionRequest(interactions: [event]))
    }

    // MARK: - Admin Discover Labeling

    /// Fetches the admin Discover labeling queue used by native labeling tools.
    /// When `reviewer` is "native" and the request carries a Bearer token, the
    /// server resolves the reviewer to the authenticated admin's email so
    /// reviewed state persists across devices.
    func fetchDiscoverLabelingFeed(reviewer: String = "native", secret: String? = nil, offset: Int = 0, limit: Int = 100) async throws -> DiscoverLabelingFeedResponse {
        var query = [
            "limit": String(limit),
            "offset": String(offset),
            "reviewer": reviewer,
            "reviewed_surface": "native_discover",
        ]
        if let secret, !secret.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            query["secret"] = secret
        }
        return try await fetch(
            "/api/admin/ranking-judgments/candidates",
            query: query,
            cacheTTL: nil
        )
    }

    /// Records a native admin ranking judgment for one Discover card.
    func submitRankingJudgment(_ body: RankingJudgmentRequest) async throws -> RankingJudgmentResponse {
        return try await postEncodable("/api/admin/ranking-judgments", body: body)
    }

    // MARK: - Bug Reports

    /// Uploads a rage-shake bug report with screenshot and app state.
    func submitBugReport(_ body: BugReportSubmission) async throws -> BugReportResponse {
        return try await postEncodable("/api/feedback/bug-report", body: body, timeout: 120)
    }

    // MARK: - Calibration

    /// Fetches public calibration buckets and error metrics.
    func fetchCalibration() async throws -> CalibrationData {
        return try await fetch("/api/calibration", cacheTTL: 300)
    }

    // MARK: - Friend Challenges

    /// Fetches a friend challenge by share code.
    func fetchChallenge(code: String) async throws -> ChallengeResponse {
        return try await fetch("/api/challenges/\(code)")
    }

    /// Accepts a friend challenge with the user's Higher/Lower guess.
    func acceptChallenge(code: String, guess: String) async throws -> AcceptChallengeResponse {
        return try await postEncodable("/api/challenges/\(code)/accept", body: AcceptChallengeRequest(guess: guess))
    }

    // MARK: - Notifications

    /// Registers an APNs device token for push notifications.
    func registerDeviceToken(deviceToken: String, platform: String, userId: Int?) async throws -> NotificationRegisterResponse {
        var body: [String: String?] = [
            "device_token": deviceToken,
            "platform": platform,
            "session_id": sessionId,
        ]
        if let userId {
            body["user_id"] = String(userId)
        }
        return try await post("/api/notifications/register", body: body)
    }
}
