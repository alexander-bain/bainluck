import Foundation

actor WatchAPIClient {
    static let shared = WatchAPIClient()

    private let baseURL = "https://api.bainluck.com"
    private let session: URLSession
    private let decoder: JSONDecoder

    private var cachedFeed: FeedResponse?
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
        config.timeoutIntervalForRequest = 30
        config.waitsForConnectivity = true
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    func fetchFeed(limit: Int = 20, forceRefresh: Bool = false) async throws -> FeedResponse {
        if !forceRefresh, let cached = cachedFeed, let at = cachedAt,
           Date().timeIntervalSince(at) < cacheTTL {
            return cached
        }

        guard let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&event_pct=0.3") else {
            throw WatchAPIError.invalidURL
        }
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WatchAPIError.httpError
        }
        let feed = try decoder.decode(FeedResponse.self, from: data)
        cachedFeed = feed
        cachedAt = Date()
        return feed
    }

    var lastFetchTime: Date? { cachedAt }

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
