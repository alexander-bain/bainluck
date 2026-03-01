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
        case .httpError(let code, let body):
            return "HTTP \(code): \(body ?? "No body")"
        case .decodingError(let err):
            return "Decoding failed: \(err.localizedDescription)"
        case .networkError(let err):
            return "Network error: \(err.localizedDescription)"
        }
    }
}

// MARK: - API Client

actor APIClient {
    static let shared = APIClient()

    private let baseURL = "https://api.bainluck.com"
    private let session: URLSession
    private let decoder: JSONDecoder

    /// Set by the auth module later. Returns a Firebase ID token or backend session token.
    var authTokenProvider: (() async -> String?)?

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

    private func fetch<T: Decodable & Sendable>(_ path: String, query: [String: String] = [:]) async throws -> sending T {
        var components = URLComponents(string: baseURL + path)
        if !query.isEmpty {
            components?.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = components?.url else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
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

    // MARK: - Generic POST (Encodable body)

    private func postEncodable<B: Encodable & Sendable, T: Decodable & Sendable>(_ path: String, body: B) async throws -> sending T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
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

    // MARK: - Feed

    func fetchFeed(
        sport: String? = nil,
        limit: Int = 200,
        offset: Int = 0,
        myTeamsOnly: Bool = false
    ) async throws -> FeedResponse {
        var q: [String: String] = [
            "limit": "\(limit)",
            "offset": "\(offset)",
        ]
        if let sport { q["sport"] = sport }
        if myTeamsOnly { q["my_teams_only"] = "true" }
        return try await fetch("/api/feed", query: q)
    }

    // MARK: - Event Detail

    func fetchEvent(id: Int) async throws -> EventDetail {
        return try await fetch("/api/events/\(id)")
    }

    // MARK: - Event History

    func fetchEventHistory(id: Int, hours: Int = 24) async throws -> EventHistoryResponse {
        return try await fetch("/api/events/\(id)/history", query: ["hours": "\(hours)"])
    }

    // MARK: - Related Futures

    func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
        return try await fetch("/api/events/\(eventId)/related-futures")
    }

    // MARK: - Line Movement

    func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse {
        return try await fetch("/api/events/\(eventId)/line-movement")
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

    // MARK: - Futures Detail

    func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail {
        return try await fetch("/api/futures/\(id)")
    }

    // MARK: - EI Rankings

    func fetchEIRankings(sport: String? = nil, limit: Int = 25) async throws -> EIRankingsResponse {
        var q: [String: String] = ["limit": "\(limit)"]
        if let sport { q["sport"] = sport }
        return try await fetch("/api/events/ei-rankings", query: q)
    }

    // MARK: - Auth

    func signInWithApple(idToken: String, firstName: String?, lastName: String?) async throws -> AppleAuthResponse {
        return try await post("/api/auth/apple", body: [
            "id_token": idToken,
            "first_name": firstName,
            "last_name": lastName,
        ])
    }

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

    func addPin(type: String, id: Int) async throws -> StatusResponse {
        return try await postEncodable("/api/me/pins", body: PinRequest(pinType: type, targetId: id))
    }

    func removePin(type: String, id: Int) async throws -> StatusResponse {
        return try await delete("/api/me/pins/\(type)/\(id)")
    }
}
