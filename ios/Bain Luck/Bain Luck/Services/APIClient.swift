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
}
