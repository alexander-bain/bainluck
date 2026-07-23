import Foundation

// MARK: - Watch-Specific Feed Models
//
// Simplified, maximally tolerant Decodable structs for the Watch app.
// Every non-essential field is optional so that API changes never cause
// a full decode failure — the Watch just gets nil for missing/changed fields.

// MARK: - Response

nonisolated struct WatchFeedResponse: Decodable, Sendable {
    let items: [WatchFeedItem]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        // Skip individual items that fail to decode rather than failing the whole response
        var itemsContainer = try c.nestedUnkeyedContainer(forKey: .items)
        var decoded: [WatchFeedItem] = []
        while !itemsContainer.isAtEnd {
            if let item = try? itemsContainer.decode(WatchFeedItem.self) {
                decoded.append(item)
            } else {
                // Advance past the bad element
                _ = try? itemsContainer.decode(WatchSkipOne.self)
            }
        }
        items = decoded
    }

    private enum CodingKeys: String, CodingKey {
        case items
    }
}

private nonisolated struct WatchSkipOne: Decodable, Sendable {}

// MARK: - Feed Item

nonisolated struct WatchFeedItem: Decodable, Identifiable, Sendable {
    let type: String
    let score: Int
    let headline: String?
    let contextSummary: String?
    let event: WatchFeedEvent?
    let futures: WatchFeedFutures?

    var id: String {
        if let e = event { return "event-\(e.id)" }
        if let f = futures { return "futures-\(f.id)" }
        return UUID().uuidString
    }

    enum CodingKeys: String, CodingKey {
        case type, score, headline, contextSummary, data
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = (try? c.decode(String.self, forKey: .type)) ?? "unknown"
        score = (try? c.decode(Int.self, forKey: .score)) ?? 0
        headline = try? c.decode(String.self, forKey: .headline)
        contextSummary = try? c.decode(String.self, forKey: .contextSummary)

        if type == "event" {
            event = try? c.decode(WatchFeedEvent.self, forKey: .data)
            futures = nil
        } else {
            futures = try? c.decode(WatchFeedFutures.self, forKey: .data)
            event = nil
        }
    }
}

// MARK: - Feed Event (minimal)

nonisolated struct WatchFeedEvent: Decodable, Identifiable, Sendable {
    let id: Int
    let homeTeam: String?
    let awayTeam: String?
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    let sport: String?
    let sportName: String?
    let commenceTime: String?
    let temporalBadge: String?
    let currentOdds: WatchCurrentOdds?
    let homeTeamData: WatchTeamData?
    let awayTeamData: WatchTeamData?
    let espn: WatchESPNData?

    var isLive: Bool { status == "live" }
    var isSettled: Bool { status == "completed" || status == "closed" }

    /// Short live-game clock string ("Q3 4:21" / "T7"), when available.
    var clockText: String? {
        let parts = [espn?.period, espn?.gameClock].compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " ")
    }

    /// Best-effort abbreviation for a side, falling back to the last name token.
    func homeAbbrev() -> String {
        homeTeamData?.abbreviation ?? String(homeTeam?.split(separator: " ").last ?? "")
    }

    func awayAbbrev() -> String {
        awayTeamData?.abbreviation ?? String(awayTeam?.split(separator: " ").last ?? "")
    }
}

nonisolated struct WatchCurrentOdds: Decodable, Sendable {
    let homeProbability: Double?
}

nonisolated struct WatchTeamData: Decodable, Sendable {
    let abbreviation: String?
    let primaryColor: String?
}

nonisolated struct WatchESPNData: Decodable, Sendable {
    let gameClock: String?
    let period: String?
}

// MARK: - Feed Futures (minimal)

nonisolated struct WatchFeedFutures: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let llmSportCategory: String?
    let topOutcomes: [WatchFeedOutcome]?
}

// MARK: - Feed Outcome

nonisolated struct WatchFeedOutcome: Decodable, Identifiable, Sendable {
    let name: String
    let probability: Double?
    let movement: Double?

    // Synthesize a stable id from name since the API may or may not include one
    var id: String { name }

    enum CodingKeys: String, CodingKey {
        case name, probability, movement
    }
}
