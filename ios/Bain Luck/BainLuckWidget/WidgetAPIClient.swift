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

// MARK: - API Response Models (minimal, widget-only)

/// Empty decode target used to advance past a malformed feed item without
/// failing the whole response (mirrors the main app's `SkipOne`).
private struct WidgetSkipOne: Decodable {}

private enum WidgetItemsKey: String, CodingKey { case items }

/// Per-item tolerant array decode. L2-179: the widget previously decoded the
/// items array atomically, so a single concept/tournament card — whose `data`
/// shape matches neither WidgetEventData nor WidgetFuturesData — threw out of the
/// whole decode and took the ENTIRE widget down (all-or-nothing). Skip any item
/// that fails to decode instead, exactly as `FeedResponse` does in the main app.
private func decodeTolerantWidgetItems<T: Decodable>(from decoder: Decoder) throws -> [WidgetFeedItem<T>] {
    let c = try decoder.container(keyedBy: WidgetItemsKey.self)
    var itemsContainer = try c.nestedUnkeyedContainer(forKey: .items)
    var decoded: [WidgetFeedItem<T>] = []
    while !itemsContainer.isAtEnd {
        if let item = try? itemsContainer.decode(WidgetFeedItem<T>.self) {
            decoded.append(item)
        } else {
            _ = try? itemsContainer.decode(WidgetSkipOne.self)
        }
    }
    return decoded
}

private struct WidgetFeedResponse: Decodable {
    let items: [WidgetFeedItem<WidgetEventData>]

    init(from decoder: Decoder) throws {
        items = try decodeTolerantWidgetItems(from: decoder)
    }
}

private struct WidgetDiscoverFeedResponse: Decodable {
    let items: [WidgetFeedItem<WidgetFuturesData>]

    init(from decoder: Decoder) throws {
        items = try decodeTolerantWidgetItems(from: decoder)
    }
}

private struct WidgetFeedItem<T: Decodable>: Decodable {
    let type: String
    let headline: String?
    let data: T?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        headline = try container.decodeIfPresent(String.self, forKey: .headline)
        data = try container.decodeIfPresent(T.self, forKey: .data)
    }

    private enum CodingKeys: String, CodingKey {
        case type, headline, data
    }
}

private struct WidgetEventData: Decodable {
    let id: Int
    let sport: String?
    let sportName: String?
    let homeTeam: String
    let awayTeam: String
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    let currentOdds: WidgetCurrentOdds?
    let homeTeamData: WidgetTeamData?
    let awayTeamData: WidgetTeamData?
    let espn: WidgetESPNData?
}

private struct WidgetFuturesData: Decodable {
    let id: Int
    let name: String
    let sport: String?
    let llmSportCategory: String?
    let topOutcomes: [WidgetOutcome]?
    let hookDescription: String?
}

private struct WidgetCurrentOdds: Decodable {
    let homeProbability: Double?
}

private struct WidgetTeamData: Decodable {
    let primaryColor: String?
    let abbreviation: String?
}

private struct WidgetESPNData: Decodable {
    let gameClock: String?
    let period: String?
}

private struct WidgetOutcome: Decodable {
    let name: String
    let probability: Double?
    let movement: Double?
}
