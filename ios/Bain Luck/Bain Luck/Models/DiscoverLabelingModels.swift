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
    let stratum: String?
    let selectionReason: String?
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
    /// `card_fingerprint` — the server's opaque digest of the card THIS payload
    /// rendered (#1933). The app never computes it and never inspects it; it
    /// round-trips the string to `POST /api/admin/ranking-judgments`, where the
    /// card is re-derived from live rows and the judgment is refused with a 409
    /// if the question re-priced while it was on screen.
    ///
    /// Optional so an older server (or a payload from before the gate) decodes
    /// rather than throwing — but see `RankingJudgmentRequest.cardFingerprint`:
    /// this app always SENDS the key once it has one, and sending the key is
    /// what asks the server to gate.
    let cardFingerprint: String?

    var stableId: String {
        "\(type)-\(id.map(String.init) ?? name)-\(rank)"
    }
}

nonisolated struct DiscoverLabelingOutcome: Codable, Sendable {
    let name: String?
    let probability: Double?
    let currentProbability: Double?
    /// `probability_change_24h`. See `TolerantNumeric`.
    ///
    /// This is the one affected type with an encode path: it rides inside
    /// `DiscoverLabelingCardSnapshot` to `POST /api/admin/judgments`. That
    /// endpoint stores `top_outcomes` opaquely (`_normalize_card_snapshot`
    /// reads no inner key), so the encoded spelling is storage, not a contract —
    /// but it must round-trip back into this same property, which it does.
    @TolerantNumeric var probabilityChange24h: Double?

    private enum CodingKeys: String, CodingKey {
        case name, probability, currentProbability
        case probabilityChange24h = "probabilityChange24H"
    }
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
    /// Echoed verbatim from `DiscoverLabelingDebugItem.cardFingerprint`.
    ///
    /// ** SENDING THE KEY IS THE CAPABILITY DECLARATION, so it is NOT an
    /// Optional. ** The server distinguishes three things: key absent (a build
    /// that predates the gate — written unbound, stamped and counted), key
    /// present but empty (a gate-aware build that had no digest — refused, with
    /// "reload" as the remedy), and key present with a value (gated). Swift's
    /// synthesised `Encodable` emits `encodeIfPresent` for Optionals, which OMITS
    /// a nil key — so declaring this `String?` would make a gate-aware build
    /// indistinguishable from a pre-gate one on exactly the payloads where the
    /// digest is missing, i.e. the stale-read case the gate exists for.
    ///
    /// The caller passes `item.cardFingerprint ?? ""`. Empty is a real claim:
    /// "I honour the gate and I have nothing to bind."
    let cardFingerprint: String
}

nonisolated struct RankingJudgmentResponse: Decodable, Sendable {
    let status: String
    let id: Int
    let label: String
}
