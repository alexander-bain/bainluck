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
    // L2-225 — terminal lifecycle authority. The widget decoded NONE of these, so
    // it had no way to tell a settled market from a live one and rendered whatever
    // carried a leader price. Decoded from `status` / `resolution_date` /
    // `resolved` / `winner` via the client's `.convertFromSnakeCase`.
    let status: String?
    let resolutionDate: String?
    let resolved: Bool?
    let winner: String?
}

// MARK: - Widget lifecycle gate (L2-225)

/// "Is this market over?" for the widget extension, mirroring the main app's
/// `FeedLifecycle.futuresIsSettled` and web's `_futuresIsSettled` authority list.
///
/// The widget is the surface where this matters most and was missing entirely: the
/// main app hides a settled card (`DiscoverView.isStaleItem`) and web labels it, but
/// `fetchDiscoverItems` admitted anything with a leader probability — and a widget
/// timeline is cached for hours, so a settled market would sit on the home screen
/// showing a live-looking number and a movement delta long after every other surface
/// had moved on ("settled means settled").
///
/// Lives here rather than in `WidgetAPIClient` because this file is a member of the
/// test bundle (L2-182's target-membership exception), so the predicate is directly
/// exercisable; the client is not.
enum WidgetLifecycle {
    static let settledStatuses: Set<String> = [
        "resolved", "closed", "settled", "finalized", "final",
    ]

    /// Tolerant by construction: an unknown/missing status is NOT terminal. Unknown
    /// authority stays unknown and the card surfaces (the L2-214 rule) — only
    /// positive evidence settles it. Probability is never evidence.
    static func isSettled(_ d: WidgetFuturesData, now: Date = Date()) -> Bool {
        if d.resolved == true { return true }
        if let winner = d.winner?.trimmingCharacters(in: .whitespacesAndNewlines),
           !winner.isEmpty { return true }
        if settledStatuses.contains((d.status ?? "").lowercased()) { return true }
        if let raw = d.resolutionDate, let date = widgetISODate(raw), date < now {
            return true
        }
        return false
    }

    /// ISO8601 with or without fractional seconds — the widget has no access to the
    /// main app's `String.asDate`, so the same two-formatter shape is repeated here.
    static func widgetISODate(_ raw: String) -> Date? {
        isoFrac.date(from: raw) ?? isoPlain.date(from: raw)
    }

    private static let isoFrac: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let isoPlain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()
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
