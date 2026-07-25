import Foundation

// MARK: - Minimal API client for the widget extension
// Widgets cannot share code with the main app target directly,
// so this is a standalone lightweight client.

actor WidgetAPIClient {
    static let shared = WidgetAPIClient()

    private let baseURL = "https://api.bainluck.com"
    private let session: URLSession
    private let decoder: JSONDecoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
    }

    // MARK: - Fetch live games from the feed

    func fetchLiveGames(limit: Int = 10) async throws -> [WidgetGame] {
        guard let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&include_futures=false") else {
            throw WidgetAPIError.invalidURL
        }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WidgetAPIError.httpError
        }

        let feed = try decoder.decode(WidgetFeedResponse.self, from: data)

        return feed.items.compactMap { item -> WidgetGame? in
            guard let event = item.data,
                  event.status == "live",
                  let homeProbability = event.currentOdds?.homeProbability else {
                return nil
            }

            let awayProbability = 1.0 - homeProbability
            let homeAbbrev = event.homeTeamData?.abbreviation
                ?? String(event.homeTeam.split(separator: " ").last ?? "")
            let awayAbbrev = event.awayTeamData?.abbreviation
                ?? String(event.awayTeam.split(separator: " ").last ?? "")

            return WidgetGame(
                id: event.id,
                homeTeam: event.homeTeam,
                awayTeam: event.awayTeam,
                homeAbbrev: homeAbbrev,
                awayAbbrev: awayAbbrev,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                homeProb: Int((homeProbability * 100).rounded()),
                awayProb: Int((awayProbability * 100).rounded()),
                period: [event.espn?.period, event.espn?.gameClock]
                    .compactMap { $0 }
                    .filter { !$0.isEmpty }
                    .joined(separator: " "),
                sport: event.sportName ?? event.sport ?? "",
                homeColor: event.homeTeamData?.primaryColor,
                awayColor: event.awayTeamData?.primaryColor
            )
        }
    }

    // MARK: - Fetch top Discover items (futures markets)

    func fetchDiscoverItems(limit: Int = 10) async throws -> [WidgetDiscoverItem] {
        guard let url = URL(string: "\(baseURL)/api/feed?limit=\(limit)&include_events=false") else {
            throw WidgetAPIError.invalidURL
        }

        let (data, response) = try await session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw WidgetAPIError.httpError
        }

        let feed = try decoder.decode(WidgetDiscoverFeedResponse.self, from: data)

        return feed.items.compactMap { item -> WidgetDiscoverItem? in
            guard let futures = item.data,
                  let leader = futures.topOutcomes?.first,
                  let probability = leader.probability else {
                return nil
            }

            return WidgetDiscoverItem(
                id: futures.id,
                name: futures.name,
                category: futures.llmSportCategory ?? futures.sport ?? "Prediction",
                leader: leader.name,
                probability: Int((probability * 100).rounded()),
                movement: leader.movement.map { Int(($0 * 100).rounded()) },
                hookDescription: futures.hookDescription,
                headline: item.headline
            )
        }
    }
}

// MARK: - Error

enum WidgetAPIError: LocalizedError {
    case httpError
    case invalidURL

    var errorDescription: String? {
        switch self {
        case .httpError: return "Request failed"
        case .invalidURL: return "Invalid URL"
        }
    }
}

// The feed decode adapter (WidgetFeedResponse / WidgetDiscoverFeedResponse /
// WidgetFeedItem + payloads + the tolerant per-item decoder) lives in
// WidgetFeedDecoding.swift so it can be compiled into the test bundle and
// exercised directly (L2-182).
