import Foundation

// MARK: - Native Discover Labeling

nonisolated struct DiscoverLabelingFeedResponse: Decodable, Sendable {
    let feedRequestId: String?
    let debugItems: [DiscoverLabelingDebugItem]
    let total: Int
    let limit: Int
    let offset: Int
    let hasMore: Bool
    let reviewedFilter: DiscoverLabelingReviewedFilter?

    private enum CodingKeys: String, CodingKey {
        case feedRequestId, debugItems, items, total, totalAvailable, limit, offset, hasMore, reviewedFilter
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        feedRequestId = try container.decodeIfPresent(String.self, forKey: .feedRequestId)
        debugItems = try container.decodeIfPresent([DiscoverLabelingDebugItem].self, forKey: .debugItems)
            ?? container.decodeIfPresent([DiscoverLabelingDebugItem].self, forKey: .items)
            ?? []
        total = try container.decodeIfPresent(Int.self, forKey: .total)
            ?? container.decodeIfPresent(Int.self, forKey: .totalAvailable)
            ?? debugItems.count
        limit = try container.decodeIfPresent(Int.self, forKey: .limit) ?? debugItems.count
        offset = try container.decodeIfPresent(Int.self, forKey: .offset) ?? 0
        hasMore = try container.decodeIfPresent(Bool.self, forKey: .hasMore) ?? false
        reviewedFilter = try container.decodeIfPresent(DiscoverLabelingReviewedFilter.self, forKey: .reviewedFilter)
    }
}

nonisolated struct DiscoverLabelingReviewedFilter: Decodable, Sendable {
    let enabled: Bool
    let reviewer: String?
    let surface: String?
    let reviewedKeyCount: Int
    let filteredCount: Int
}

nonisolated struct DiscoverLabelingDebugItem: Decodable, Identifiable, Sendable {
    let rank: Int
    let type: String
    let id: Int?
    let score: Double
    let name: String
    let category: String
    let archetype: String?
    let source: String?
    let headline: String?
    let reason: String?
    let context: String?
    let hookDescription: String?
    let imageUrl: String?
    let hook: Bool?
    let image: Bool?
    let explanationOk: Bool?
    let qualityClass: String?
    let familyKey: String?
    let storyKey: String?
    let groupId: String?
    let renderedProbability: Double?
    let topOutcomes: [DiscoverLabelingOutcome]?
    let reasons: [String]?

    var stableId: String {
        "\(type)-\(id.map(String.init) ?? name)-\(rank)"
    }
}

nonisolated struct DiscoverLabelingOutcome: Codable, Sendable {
    let name: String?
    let probability: Double?
    let currentProbability: Double?
    let probabilityChange24h: Double?
}

nonisolated struct DiscoverLabelingCardSnapshot: Encodable, Sendable {
    let schemaVersion: String
    let batchId: String
    let feedRequestId: String?
    let rank: Int
    let itemType: String
    let itemId: Int?
    let marketId: Int?
    let eventId: Int?
    let name: String
    let source: String?
    let category: String
    let archetype: String?
    let qualityClass: String?
    let headline: String?
    let reason: String?
    let context: String?
    let hookDescription: String?
    let imageUrl: String?
    let storyKey: String?
    let familyKey: String?
    let groupId: String?
    let score: Double
    let renderedProbability: Double?
    let topOutcomes: [DiscoverLabelingOutcome]
    let reasons: [String]
    let hasHook: Bool
    let hasImage: Bool
    let explanationOk: Bool
}

nonisolated struct RankingJudgmentRequest: Encodable, Sendable {
    let secret: String?
    let surface: String
    let rankSeen: Int
    let itemType: String
    let marketId: Int?
    let eventId: Int?
    let marketName: String
    let label: String
    let reasonTags: [String]
    let betterThan: String?
    let worseThan: String?
    let notes: String?
    let scoreAtReview: Double
    let categoryAtReview: String
    let archetypeAtReview: String?
    let qualityClassAtReview: String?
    let headlineAtReview: String?
    let feedRequestId: String?
    let cardSnapshot: DiscoverLabelingCardSnapshot
    let reviewer: String
}

nonisolated struct RankingJudgmentResponse: Decodable, Sendable {
    let status: String
    let id: Int
    let label: String
}
