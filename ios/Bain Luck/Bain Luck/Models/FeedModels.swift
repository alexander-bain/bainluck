import Foundation

// MARK: - Feed Response

nonisolated struct FeedResponse: Decodable, Sendable {
    let items: [FeedItem]
    let total: Int
    let limit: Int
    let offset: Int
    let hasMore: Bool

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        total = try c.decodeIfPresent(Int.self, forKey: .total) ?? 0
        limit = try c.decodeIfPresent(Int.self, forKey: .limit) ?? 50
        offset = try c.decodeIfPresent(Int.self, forKey: .offset) ?? 0
        hasMore = try c.decodeIfPresent(Bool.self, forKey: .hasMore) ?? false

        // Decode items individually — skip any that fail rather than crashing the whole feed
        var itemsContainer = try c.nestedUnkeyedContainer(forKey: .items)
        var decoded: [FeedItem] = []
        while !itemsContainer.isAtEnd {
            if let item = try? itemsContainer.decode(FeedItem.self) {
                decoded.append(item)
            } else {
                _ = try? itemsContainer.decode(AnyCodable.self)
            }
        }
        items = decoded
    }

    private enum CodingKeys: String, CodingKey {
        case items, total, limit, offset, hasMore
    }
}

// MARK: - Feed Item (Polymorphic)

nonisolated struct FeedItem: Decodable, Identifiable, Sendable {
    let type: String
    let score: Int
    let reason: String?
    let headline: String?

    // One of these will be populated based on `type`
    let event: FeedEventData?
    let futures: FeedFuturesData?

    // Personalization fields
    let personalized: Bool?
    let baseScore: Int?
    let multiplier: Double?
    let personalizationReasons: [String]?

    var id: String {
        if let e = event { return "event-\(e.id)" }
        if let f = futures { return "futures-\(f.id)" }
        return UUID().uuidString
    }

    enum CodingKeys: String, CodingKey {
        case type, score, reason, headline, data
        case personalized, baseScore, multiplier, personalizationReasons
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(String.self, forKey: .type)
        score = try c.decodeIfPresent(Int.self, forKey: .score) ?? 0
        reason = try c.decodeIfPresent(String.self, forKey: .reason)
        headline = try c.decodeIfPresent(String.self, forKey: .headline)
        personalized = try c.decodeIfPresent(Bool.self, forKey: .personalized)
        baseScore = try c.decodeIfPresent(Int.self, forKey: .baseScore)
        multiplier = try c.decodeIfPresent(Double.self, forKey: .multiplier)
        personalizationReasons = try c.decodeIfPresent([String].self, forKey: .personalizationReasons)

        if type == "event" {
            event = try c.decodeIfPresent(FeedEventData.self, forKey: .data)
            futures = nil
        } else {
            futures = try c.decodeIfPresent(FeedFuturesData.self, forKey: .data)
            event = nil
        }
    }
}

// MARK: - Feed Event Data

nonisolated struct FeedEventData: Decodable, Identifiable, Sendable {
    let id: Int
    let externalId: String?
    let sport: String?
    let sportName: String?
    let homeTeam: String
    let awayTeam: String
    let commenceTime: String?
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    let currentOdds: CurrentOdds?
    let openingOdds: OpeningOdds?
    let highlight: Highlight?
    let homeTeamData: TeamData?
    let awayTeamData: TeamData?
    let metadata: EventMetadata?
    let espn: ESPNData?
    let ei: EIData?
    let pulse: EIData?
    let winProbabilitySources: [String: WinProbSource]?
}

// MARK: - Feed Futures Data

nonisolated struct FeedFuturesData: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let sport: String?
    let sportName: String?
    let llmSportCategory: String?
    let source: String?
    let sourceCount: Int?
    let marketTier: Int?
    let status: String?
    let resolutionDate: String?
    let topOutcomes: [FeedFuturesOutcome]?
    let outcomeCount: Int?
    let canonicalMarketKey: String?
    let imageUrl: String?
    let hookDescription: String?
}

nonisolated struct FeedFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let rank: Int?
    let movement: Double?
}

// MARK: - Pins Response

nonisolated struct PinsResponse: Decodable, Sendable {
    let events: [Int]
    let futures: [Int]
}

// MARK: - Pin Request Body

nonisolated struct PinRequest: Encodable, Sendable {
    let pinType: String
    let targetId: Int
}

// MARK: - Grouped Feed Response

nonisolated struct GroupedFeedResponse: Decodable, Sendable {
    let feed: [GroupedFeedItem]
    let total: Int
    let limit: Int
    let offset: Int
}

// MARK: - Grouped Feed Item (Polymorphic)

nonisolated struct GroupedFeedItem: Decodable, Identifiable, Sendable {
    let type: String
    let groupKey: String
    
    // Player stat props
    let playerName: String?
    let statCategory: String?
    let lines: [StatPropLine]?
    let marketCount: Int?
    let espnPlayerId: String?
    let sportKey: String?
    let eventMatchup: String?
    let eventTime: String?
    
    // Playoff progression
    let entityName: String?
    let stages: [ProgressionStage]?
    let logoUrl: String?
    let teamColors: TeamColors?
    
    var id: String { groupKey }
}

// MARK: - Stat Prop Line

nonisolated struct StatPropLine: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double
    let thresholdValue: Int
    let thresholdDirection: String
    let source: String?
}

// MARK: - Progression Stage

nonisolated struct ProgressionStage: Decodable, Identifiable, Sendable {
    let id: Int
    let label: String
    let probability: Double?
    let status: String?
}

// MARK: - Team Colors

nonisolated struct TeamColors: Decodable, Sendable {
    let primary: String?
    let secondary: String?
}
