import Foundation
import os.log

private let logger = Logger(subsystem: "com.bainluck.watch", category: "API")

actor WatchAPIClient {
    static let shared = WatchAPIClient()

    private let baseURL = "https://api.bainluck.com"
    private let session: URLSession
    private let decoder: JSONDecoder

    private var cachedFeed: WatchFeedResponse?
    private var cachedAt: Date?
    private let cacheTTL: TimeInterval = 20

    private let sessionId: String = {
        let key = "bainluck_watch_session_id"
        if let existing = UserDefaults.standard.string(forKey: key) {
            return existing
        }
        let id = "watch_" + UUID().uuidString
        UserDefaults.standard.set(id, forKey: key)
        return id
    }()

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.waitsForConnectivity = true
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    func fetchFeed(limit: Int = 5, forceRefresh: Bool = false) async throws -> WatchFeedResponse {
        if !forceRefresh, let cached = cachedFeed, let at = cachedAt,
           Date().timeIntervalSince(at) < cacheTTL {
            logger.info("Returning cached feed (\(cached.items.count) items, \(Int(Date().timeIntervalSince(at)))s old)")
            return cached
        }

        guard let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&event_pct=0.3") else {
            logger.error("Invalid feed URL for limit=\(limit)")
            throw WatchAPIError.invalidURL
        }
        logger.info("Fetching feed limit=\(limit), forceRefresh=\(forceRefresh)")
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(from: url)
        } catch {
            logger.error("Network failed: \(error.localizedDescription)")
            throw error
        }
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? -1
            logger.error("HTTP error: status \(code)")
            throw WatchAPIError.httpError
        }
        logger.info("Feed response: \(http.statusCode), \(data.count) bytes")
        do {
            let feed = try decoder.decode(WatchFeedResponse.self, from: data)
            logger.info("Decoded \(feed.items.count) items")
            cachedFeed = feed
            cachedAt = Date()
            return feed
        } catch {
            logger.error("Decode failed: \(error.localizedDescription)")
            throw error
        }
    }

    var lastFetchTime: Date? { cachedAt }

    /// Fetches the my-teams feed (events for the user's followed teams). Requires
    /// a Bearer token — the backend hard-gates `my_teams_only` on the authenticated
    /// user and returns empty for anonymous callers. Returns nil when signed out so
    /// the caller can render the graceful signed-out state without a wasted request.
    func fetchMyTeamsFeed(limit: Int = 6) async throws -> WatchFeedResponse? {
        guard let token = WatchAuthStore.shared.token else { return nil }

        guard let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&my_teams_only=true&include_futures=false") else {
            throw WatchAPIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.setValue(sessionId, forHTTPHeaderField: "x-session-id")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? -1
            logger.error("My-teams feed HTTP error: status \(code)")
            throw WatchAPIError.httpError
        }
        return try decoder.decode(WatchFeedResponse.self, from: data)
    }

    func submitPrediction(
        marketId: Int,
        guess: String,
        threshold: Int,
        actualProbability: Double,
        correct: Bool,
        category: String?
    ) async throws {
        guard let url = URL(string: "\(baseURL)/api/predictions") else {
            throw WatchAPIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(sessionId, forHTTPHeaderField: "x-session-id")

        let body = PredictionRequest(
            marketId: marketId,
            guess: guess,
            threshold: threshold,
            actualProbability: actualProbability,
            correct: correct,
            category: category
        )
        request.httpBody = try JSONEncoder().encode(body)

        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WatchAPIError.httpError
        }
    }

    func fetchPredictionStats() async throws -> PredictionStats {
        guard var url = URLComponents(string: "\(baseURL)/api/predictions/stats") else {
            throw WatchAPIError.invalidURL
        }
        url.queryItems = [URLQueryItem(name: "session_id", value: sessionId)]
        guard let finalURL = url.url else {
            throw WatchAPIError.invalidURL
        }
        var request = URLRequest(url: finalURL)
        request.setValue(sessionId, forHTTPHeaderField: "x-session-id")

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WatchAPIError.httpError
        }
        return try decoder.decode(PredictionStats.self, from: data)
    }
}

enum WatchAPIError: LocalizedError {
    case httpError
    case invalidURL

    var errorDescription: String? {
        switch self {
        case .httpError: "Request failed"
        case .invalidURL: "Invalid URL"
        }
    }
}
