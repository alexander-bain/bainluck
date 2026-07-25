import Foundation

// MARK: - Widget feed decode adapter (extracted for testability)
//
// L2-182: these types were `private` inside `WidgetAPIClient.swift`, which made
// the production tolerant decoder impossible to exercise from a test. They are
// pure Foundation, so this file compiles into BOTH the widget extension (where
// `WidgetAPIClient` decodes with it) and the iOS test bundle (via a target
// membership exception) — the test can now decode `WidgetFeedResponse` /
// `WidgetDiscoverFeedResponse` directly and prove malformed items are skipped
// rather than tanking the whole response.

/// Empty decode target used to advance past a malformed feed item without
/// failing the whole response (mirrors the main app's `SkipOne`).
struct WidgetSkipOne: Decodable {}

enum WidgetItemsKey: String, CodingKey { case items }

/// Per-item tolerant array decode. L2-179: the widget previously decoded the
/// items array atomically, so a single concept/tournament card — whose `data`
/// shape matches neither WidgetEventData nor WidgetFuturesData — threw out of the
/// whole decode and took the ENTIRE widget down (all-or-nothing). Skip any item
/// that fails to decode instead, exactly as `FeedResponse` does in the main app.
func decodeTolerantWidgetItems<T: Decodable>(from decoder: Decoder) throws -> [WidgetFeedItem<T>] {
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

struct WidgetFeedResponse: Decodable {
    let items: [WidgetFeedItem<WidgetEventData>]

    init(from decoder: Decoder) throws {
        items = try decodeTolerantWidgetItems(from: decoder)
    }
}

struct WidgetDiscoverFeedResponse: Decodable {
    let items: [WidgetFeedItem<WidgetFuturesData>]

    init(from decoder: Decoder) throws {
        items = try decodeTolerantWidgetItems(from: decoder)
    }
}

struct WidgetFeedItem<T: Decodable>: Decodable {
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

struct WidgetEventData: Decodable {
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

struct WidgetFuturesData: Decodable {
    let id: Int
    let name: String
    let sport: String?
    let llmSportCategory: String?
    let topOutcomes: [WidgetOutcome]?
    let hookDescription: String?
}

struct WidgetCurrentOdds: Decodable {
    let homeProbability: Double?
}

struct WidgetTeamData: Decodable {
    let primaryColor: String?
    let abbreviation: String?
}

struct WidgetESPNData: Decodable {
    let gameClock: String?
    let period: String?
}

struct WidgetOutcome: Decodable {
    let name: String
    let probability: Double?
    let movement: Double?
}
