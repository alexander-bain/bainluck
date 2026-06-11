import Foundation

// MARK: - Feed Response

/// Empty decode target used to skip malformed feed items without failing the whole response.
private nonisolated struct SkipOne: Decodable, Sendable {}

/// Paginated Discover feed response containing event and futures cards.
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

        var itemsContainer = try c.nestedUnkeyedContainer(forKey: .items)
        var decoded: [FeedItem] = []
        while !itemsContainer.isAtEnd {
            if let item = try? itemsContainer.decode(FeedItem.self) {
                decoded.append(item)
            } else {
                _ = try? itemsContainer.decode(SkipOne.self)
            }
        }
        items = decoded
    }

    private enum CodingKeys: String, CodingKey {
        case items, total, limit, offset, hasMore
    }
}

// MARK: - Discover Interaction Capture

/// Batched request body for sending Discover feed interaction events.
nonisolated struct DiscoverInteractionRequest: Encodable, Sendable {
    let interactions: [DiscoverInteractionEvent]
}

/// Analytics-style interaction event captured from a Discover feed card.
nonisolated struct DiscoverInteractionEvent: Encodable, Sendable {
    let action: String
    let itemType: String
    let itemId: String
    let category: String
    let itemName: String?
    let score: Int?
    let rank: Int?
    let surface: String
    let source: String?
}

// MARK: - Feed Item (Polymorphic)

/// Polymorphic feed card wrapper for either a sports event or a futures market.
nonisolated struct FeedBundle: Decodable, Sendable {
    let id: String
    let title: String
    let items: [FeedItem]
    let kind: String?
    let comparisonTheme: String?

    enum CodingKeys: String, CodingKey {
        case id, title, items, kind, comparisonTheme
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? UUID().uuidString
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        items = try c.decodeIfPresent([FeedItem].self, forKey: .items) ?? []
        kind = try c.decodeIfPresent(String.self, forKey: .kind)
        comparisonTheme = try c.decodeIfPresent(String.self, forKey: .comparisonTheme)
    }
}

nonisolated struct FeedItem: Decodable, Identifiable, Sendable {
    let type: String
    let score: Int
    let reason: String?
    let headline: String?
    let contextSummary: String?

    // One of these will be populated based on `type`
    let event: FeedEventData?
    let futures: FeedFuturesData?
    let tournament: FeedTournamentData?
    let bundle: FeedBundle?

    // Personalization fields
    let personalized: Bool?
    let baseScore: Int?
    let multiplier: Double?
    let personalizationReasons: [String]?

    var id: String {
        if let e = event { return "event-\(e.id)" }
        if let f = futures { return "futures-\(f.id)" }
        if let t = tournament { return "tournament-\(t.key)" }
        return [
            "feed",
            type,
            headline,
            contextSummary,
            reason,
            String(score)
        ]
        .compactMap { Self.stableFeedIdentityComponent($0) }
        .joined(separator: "-")
    }

    private static func stableFeedIdentityComponent(_ value: String?) -> String? {
        value?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
            .joined(separator: "-")
    }

    enum CodingKeys: String, CodingKey {
        case type, score, reason, headline, contextSummary, data, bundle
        case personalized, baseScore, multiplier, personalizationReasons
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(String.self, forKey: .type)
        score = try c.decodeIfPresent(Int.self, forKey: .score) ?? 0
        reason = try c.decodeIfPresent(String.self, forKey: .reason)
        headline = try c.decodeIfPresent(String.self, forKey: .headline)
        contextSummary = try c.decodeIfPresent(String.self, forKey: .contextSummary)
        personalized = try c.decodeIfPresent(Bool.self, forKey: .personalized)
        baseScore = try c.decodeIfPresent(Int.self, forKey: .baseScore)
        multiplier = try c.decodeIfPresent(Double.self, forKey: .multiplier)
        personalizationReasons = try c.decodeIfPresent([String].self, forKey: .personalizationReasons)
        bundle = try c.decodeIfPresent(FeedBundle.self, forKey: .bundle)

        if type == "event" {
            event = try c.decodeIfPresent(FeedEventData.self, forKey: .data)
            futures = nil
            tournament = nil
        } else if type == "tournament" {
            tournament = try c.decodeIfPresent(FeedTournamentData.self, forKey: .data)
            event = nil
            futures = nil
        } else {
            futures = try c.decodeIfPresent(FeedFuturesData.self, forKey: .data)
            event = nil
            tournament = nil
        }
    }
}

// MARK: - Feed Event Data

/// Event payload embedded inside an event-type feed card.
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

/// Futures-market payload embedded inside a futures-type feed card.
nonisolated struct FeedFuturesData: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let sport: String?
    let sportName: String?
    let llmSportCategory: String?
    let source: String?
    let sourceCount: Int?
    let sources: [String]?
    let marketTier: Int?
    let status: String?
    let resolutionDate: String?
    let topOutcomes: [FeedFuturesOutcome]?
    let outcomeCount: Int?
    let canonicalMarketKey: String?
    let groupId: String?
    let groupType: String?
    let imageUrl: String?
    let hookDescription: String?
    let matchedOutcomes: [MatchedOutcome]?
    let discoverCard: FeedDiscoverCard?
}

// MARK: - Discover Card Archetype

/// Structured card archetype attached to futures items in the Discover feed.
nonisolated struct FeedDiscoverCard: Decodable, Sendable {
    let suggestedFormat: String?
    let bundleCandidate: Bool?
    let comparisonTheme: String?
    let thresholdPoints: [FeedDiscoverThresholdPoint]?
    let distributionOutcomes: [FeedDiscoverDistributionOutcome]?
    let remainingOutcomeCount: Int?
    let qaSignals: [String]?
    let publicSourceDisagreement: Bool?
    let reasons: [String]?
}

/// Single threshold point for heatmap-style cards.
nonisolated struct FeedDiscoverThresholdPoint: Decodable, Identifiable, Sendable {
    let source: String?
    let label: String
    let value: Double?
    let unit: String?
    let direction: String?
    let probability: Double?
    let needsSiblingMarkets: Bool?

    var id: String { label }
}

/// Single outcome row for distribution-style cards.
nonisolated struct FeedDiscoverDistributionOutcome: Decodable, Sendable {
    let label: String
    let probability: Double?
    let movement: Double?
}

// MARK: - Feed Tournament Data

/// Tournament payload embedded inside a tournament-type feed card.
nonisolated struct FeedTournamentData: Decodable, Sendable {
    let key: String
    let name: String
    let slug: String?
    let tour: String?
    let tourLabel: String?
    let isMajor: Bool?
    let venue: String?
    let location: String?
    let startDate: String?
    let endDate: String?
    let scheduleStatus: String?
    let commenceTime: String?
    let resolutionDate: String?
    let golfers: [FeedTournamentGolfer]?
    let sourceCount: Int?
}

/// Golfer entry in a tournament feed card.
nonisolated struct FeedTournamentGolfer: Decodable, Identifiable, Sendable {
    let name: String
    let probability: Double
    let rank: Int
    let movement24h: Double?

    var id: String { name }
}

/// Outcome matched to the user's followed team (from my_teams_only feed).
nonisolated struct MatchedOutcome: Decodable, Identifiable, Sendable {
    let name: String
    let probability: Double?
    let rank: Int?
    let movement: Double?

    var id: String { name }
}

/// Top outcome summary shown on a futures feed card.
nonisolated struct FeedFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let rank: Int?
    let movement: Double?
}

// MARK: - Pins Response

/// Server response listing pinned event and futures identifiers.
nonisolated struct PinsResponse: Decodable, Sendable {
    let events: [Int]
    let futures: [Int]
}

// MARK: - Pin Request Body

/// Request body for pinning or unpinning an event or futures market.
nonisolated struct PinRequest: Encodable, Sendable {
    let pinType: String
    let targetId: Int

    enum CodingKeys: String, CodingKey {
        case pinType = "pin_type"
        case targetId = "target_id"
    }
}

// MARK: - Grouped Feed Response

/// Paginated response for grouped feed sections such as props and playoff paths.
nonisolated struct GroupedFeedResponse: Decodable, Sendable {
    let feed: [GroupedFeedItem]
    let total: Int
    let limit: Int
    let offset: Int
}

// MARK: - Grouped Feed Item (Polymorphic)

/// Grouped feed entry representing either related prop lines or progression stages.
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

/// Single threshold line within a grouped player-stat prop card.
nonisolated struct StatPropLine: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double
    let thresholdValue: Int
    let thresholdDirection: String
    let source: String?
}

// MARK: - Progression Stage

/// One stage in a playoff or season-progression probability ladder.
nonisolated struct ProgressionStage: Decodable, Identifiable, Sendable {
    let id: Int
    let label: String
    let probability: Double?
    let status: String?
}

// MARK: - Team Colors

/// Team color pair supplied for grouped progression cards.
nonisolated struct TeamColors: Decodable, Sendable {
    let primary: String?
    let secondary: String?
}
