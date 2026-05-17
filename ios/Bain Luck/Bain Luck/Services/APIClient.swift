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

    func setAuthTokenProvider(_ provider: (() async -> String?)?) {
        authTokenProvider = provider
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

    func fetchFeed(
        sport: String? = nil,
        limit: Int = 50,
        offset: Int = 0,
        myTeamsOnly: Bool = false,
        includeFutures: Bool = true,
        includeEvents: Bool = true,
        eventPct: Double? = nil,
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
        if let tags, !tags.isEmpty,
           let data = try? JSONSerialization.data(withJSONObject: tags),
           let str = String(data: data, encoding: .utf8) {
            q["tags"] = str
        }
        return try await fetch("/api/feed", query: q, cacheTTL: cacheTTL)
    }

    // MARK: - Grouped Futures Feed

    func fetchGroupedFeed(limit: Int = 20, offset: Int = 0) async throws -> GroupedFeedResponse {
        let q: [String: String] = [
            "limit": "\(limit)",
            "offset": "\(offset)",
        ]
        return try await fetch("/api/futures/grouped-feed", query: q, cacheTTL: 60)
    }

    // MARK: - Event Detail

    func fetchEvent(id: Int) async throws -> EventDetail {
        return try await fetch("/api/events/\(id)", cacheTTL: 15)
    }

    // MARK: - Event History

    func fetchEventHistory(id: Int, hours: Int = 24) async throws -> EventHistoryResponse {
        return try await fetch("/api/events/\(id)/history", query: ["hours": "\(hours)"], cacheTTL: 60)
    }

    // MARK: - Related Futures

    func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
        return try await fetch("/api/events/\(eventId)/related-futures", cacheTTL: 60)
    }

    // MARK: - Team Progression (Championship Path)

    func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse {
        return try await fetch("/api/events/\(eventId)/team-progression", cacheTTL: 120)
    }

    // MARK: - Game Markets (Player Props, Spreads, Totals)

    func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse {
        return try await fetch("/api/events/\(eventId)/game-markets", cacheTTL: 60)
    }

    // MARK: - Search

    func fetchSearch(query: String, sport: String? = nil, page: Int = 1) async throws -> SearchResponse {
        var q: [String: String] = ["q": query, "page": "\(page)"]
        if let sport { q["sport"] = sport }
        return try await fetch("/api/events/search", query: q)
    }

    // MARK: - Typeahead

    func fetchTypeahead(query: String) async throws -> TypeaheadResponse {
        return try await fetch("/api/events/typeahead", query: ["q": query])
    }

    func fetchTrendingSearches() async throws -> TrendingSearchesResponse {
        return try await fetch("/api/events/search/trending", cacheTTL: 300)
    }

    // MARK: - Team Page

    func fetchTeamPage(slug: String) async throws -> TeamPageResponse {
        return try await fetch("/api/teams/\(slug)")
    }

    // MARK: - Futures Detail

    func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail {
        return try await fetch("/api/futures/\(id)")
    }

    func fetchProbabilityTimeline(marketId: Int, top: Int = 50, hours: Int = 168) async throws -> ProbabilityTimelineResponse {
        return try await fetch("/api/futures/\(marketId)/probability-timeline", query: [
            "top": "\(top)",
            "hours": "\(hours)",
        ])
    }

    // MARK: - EI Rankings

    func fetchEIRankings(sport: String? = nil, limit: Int = 25) async throws -> EIRankingsResponse {
        var q: [String: String] = ["limit": "\(limit)"]
        if let sport { q["sport"] = sport }
        return try await fetch("/api/events/ei-rankings", query: q)
    }

    // MARK: - Faceted Search

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

    func fetchFacetedFutures(tags: [String] = [], page: Int = 1) async throws -> FacetedFuturesResponse {
        var q: [String: String] = [
            "page": "\(page)",
            "per_page": "20",
        ]
        if !tags.isEmpty, let json = try? JSONSerialization.data(withJSONObject: tags),
           let str = String(data: json, encoding: .utf8) {
            q["tags"] = str
        }
        return try await fetch("/api/futures/faceted", query: q, cacheTTL: 30)
    }

    // MARK: - Auth

    func signInWithApple(idToken: String, firstName: String?, lastName: String?) async throws -> AppleAuthResponse {
        return try await post("/api/auth/apple", body: [
            "id_token": idToken,
            "first_name": firstName,
            "last_name": lastName,
        ])
    }

    // MARK: - Weather

    func fetchWeatherFeatured() async throws -> [WeatherFeaturedItem] {
        return try await fetch("/api/weather/featured", cacheTTL: 120)
    }

    func fetchWeatherCities() async throws -> [WeatherCity] {
        return try await fetch("/api/weather/cities", cacheTTL: 120)
    }

    // MARK: - Economics

    func fetchEconomics() async throws -> EconomicsResponse {
        return try await fetch("/api/economics", cacheTTL: 120)
    }

    // MARK: - Politics

    func fetchPolitics() async throws -> PoliticsResponse {
        return try await fetch("/api/politics", cacheTTL: 120)
    }

    // MARK: - Entertainment

    func fetchEntertainment() async throws -> EntertainmentResponse {
        return try await fetch("/api/entertainment", cacheTTL: 120)
    }

    // MARK: - League Markets

    func fetchLeagueMarkets(sportKey: String) async throws -> LeagueMarketsResponse {
        return try await fetch("/api/leagues/\(sportKey)", cacheTTL: 120)
    }

    // MARK: - Auth

    func signInWithGoogle(accessToken: String) async throws -> AppleAuthResponse {
        return try await post("/api/auth/google-access-token", body: [
            "access_token": accessToken,
        ])
    }

    func fetchProfile() async throws -> AuthUser {
        return try await fetch("/api/auth/me")
    }

    func fetchAuthStatus() async throws -> AuthStatusResponse {
        return try await fetch("/api/auth/status")
    }

    // MARK: - Onboarding

    func searchTeamsByLocation(query: String) async throws -> [TeamSearchResult] {
        return try await fetch("/api/me/teams/by-location", query: ["q": query])
    }

    func searchTeams(query: String) async throws -> [TeamSearchResult] {
        return try await fetch("/api/me/teams/search", query: ["q": query])
    }

    func submitOnboarding(_ submission: OnboardingSubmission) async throws -> OnboardingResponse {
        return try await postEncodable("/api/me/onboarding", body: submission)
    }

    // MARK: - Preferences

    func fetchPreferences() async throws -> PreferencesResponse {
        return try await fetch("/api/me/preferences")
    }

    func removeFavorite(teamId: Int, relationType: String) async throws -> StatusResponse {
        return try await delete("/api/me/favorites/\(teamId)", query: ["relation_type": relationType])
    }

    func updateSportAffinities(_ affinities: [String: Double]) async throws -> StatusResponse {
        let body = SportAffinitiesUpdate(sportAffinities: affinities)
        return try await putEncodable("/api/me/preferences/sport-affinities", body: body)
    }

    // MARK: - Pins

    func fetchPins() async throws -> PinsResponse {
        return try await fetch("/api/me/pins")
    }

    // MARK: - Team Futures

    func fetchMyTeamFutures(limit: Int = 100) async throws -> TeamFuturesResponse {
        return try await fetch("/api/me/team-futures", query: ["limit": "\(limit)"], cacheTTL: 300)
    }

    // MARK: - Championship Grids

    func fetchChampionshipGrid(slug: String) async throws -> ChampionshipGridResponse {
        return try await fetch("/api/playoffs/\(slug)", cacheTTL: 300)
    }

    // MARK: - Golf

    func fetchGolfLanding() async throws -> GolfLandingResponse {
        return try await fetch("/api/golf", cacheTTL: 120)
    }

    func fetchGolfLeaderboard(tour: String = "pga") async throws -> GolfLeaderboardResponse {
        return try await fetch("/api/golf/leaderboard", query: ["tour": tour], cacheTTL: 30)
    }

    func addPin(type: String, id: Int) async throws -> StatusResponse {
        return try await postEncodable("/api/me/pins", body: PinRequest(pinType: type, targetId: id))
    }

    func removePin(type: String, id: Int) async throws -> StatusResponse {
        return try await delete("/api/me/pins/\(type)/\(id)")
    }

    // MARK: - Predictions

    func submitPrediction(_ body: PredictionRequest) async throws -> StatusResponse {
        return try await postEncodable("/api/predictions", body: body)
    }

    func fetchPredictionStats() async throws -> PredictionStats {
        return try await fetch("/api/predictions/stats")
    }

    func fetchDetailedPredictionStats() async throws -> DetailedPredictionStats {
        return try await fetch("/api/predictions/detailed-stats")
    }

    func fetchResolutions() async throws -> ResolutionsResponse {
        return try await fetch("/api/predictions/resolutions")
    }

    func recordDiscoverInteraction(_ event: DiscoverInteractionEvent) async throws -> StatusResponse {
        return try await postEncodable("/api/feed/interactions", body: DiscoverInteractionRequest(interactions: [event]))
    }

    // MARK: - Bug Reports

    func submitBugReport(_ body: BugReportSubmission) async throws -> BugReportResponse {
        return try await postEncodable("/api/feedback/bug-report", body: body, timeout: 120)
    }

    // MARK: - Calibration

    func fetchCalibration() async throws -> CalibrationData {
        return try await fetch("/api/calibration", cacheTTL: 300)
    }

    // MARK: - Friend Challenges

    func fetchChallenge(code: String) async throws -> ChallengeResponse {
        return try await fetch("/api/challenges/\(code)")
    }

    func acceptChallenge(code: String, guess: String) async throws -> AcceptChallengeResponse {
        return try await postEncodable("/api/challenges/\(code)/accept", body: AcceptChallengeRequest(guess: guess))
    }

    // MARK: - Notifications

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
