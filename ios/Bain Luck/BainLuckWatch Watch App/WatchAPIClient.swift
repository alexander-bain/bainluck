import Foundation

actor WatchAPIClient {
    static let shared = WatchAPIClient()

    private let baseURL = "https://api.bainluck.com"
    private let session: URLSession
    private let decoder: JSONDecoder

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
        config.timeoutIntervalForRequest = 10
        config.waitsForConnectivity = true
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    func fetchFeed(limit: Int = 20) async throws -> FeedResponse {
        let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&event_pct=0.3")!
        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WatchAPIError.httpError
        }
        return try decoder.decode(FeedResponse.self, from: data)
    }

    func submitPrediction(
        marketId: Int,
        guess: String,
        threshold: Int,
        actualProbability: Double,
        correct: Bool,
        category: String?
    ) async throws {
        let url = URL(string: "\(baseURL)/api/predictions")!
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
        var url = URLComponents(string: "\(baseURL)/api/predictions/stats")!
        url.queryItems = [URLQueryItem(name: "session_id", value: sessionId)]
        var request = URLRequest(url: url.url!)
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

    var errorDescription: String? { "Request failed" }
}
