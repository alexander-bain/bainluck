import Foundation

// MARK: - Feed Response

/// Empty decode target used to skip malformed feed items without failing the whole response.
private nonisolated struct SkipOne: Decodable, Sendable {}

/// The backend's bounded, identity-free feed cache metadata (L2-238).
///
/// Every `/api/feed` return path emits this via `build_feed_cache_metadata`.
/// Only `status` is guaranteed; the rest are conditional, so all of it decodes
/// tolerantly — a malformed object must never fail the whole feed.
nonisolated struct FeedCacheMetadata: Decodable, Sendable {
    let status: String?
    let ttlSeconds: Int?
    let staleTtlSeconds: Int?
    let reason: String?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        ttlSeconds = try? c.decodeIfPresent(Int.self, forKey: .ttlSeconds)
        staleTtlSeconds = try? c.decodeIfPresent(Int.self, forKey: .staleTtlSeconds)
        reason = try? c.decodeIfPresent(String.self, forKey: .reason)
    }

    private enum CodingKeys: String, CodingKey {
        case status, ttlSeconds, staleTtlSeconds, reason
    }
}

/// Paginated Discover feed response containing event and futures cards.
nonisolated struct FeedResponse: Decodable, Sendable {
    let items: [FeedItem]
    let total: Int
    let limit: Int
    let offset: Int
    let hasMore: Bool
    /// L2-238: bounded cache metadata. Nil on a pre-metadata payload.
    let cache: FeedCacheMetadata?
    /// L2-238: present ONLY when the build was not complete.
    let buildQuality: String?
    let degradedReason: String?

    /// The cache status the backend uses for the truthful no-data terminal.
    static let unavailableCacheStatus = "unavailable"
    /// The build quality the backend reports for a whole, publishable build.
    static let completeBuildQuality = "complete"

    /// L2-238: the backend explicitly typed this response UNAVAILABLE — a
    /// singleflight waiter ran out of budget with no last-good to serve, so the
    /// body carries `items: []` / `has_more: false` while knowing NOTHING about
    /// the feed. It is a transient, retryable terminal, not an exhausted feed.
    ///
    /// Deliberately keyed on the exact status and nothing else. A `last_good`
    /// payload can carry `reason: "redis_unavailable"` while serving real cards;
    /// matching on the reason would blank a working feed. An absent or malformed
    /// `cache` reads as available, so an older backend stays compatible and no
    /// missing metadata can fabricate this state.
    var isUnavailable: Bool {
        cache?.status == Self.unavailableCacheStatus
    }

    /// L2-238: the backend flagged this as a degraded/partial build. It refuses
    /// to publish such a build as shared truth server-side; an EMPTY one must not
    /// be allowed to blank an already-rendered generation client-side either.
    var isDegradedBuild: Bool {
        guard let quality = buildQuality, !quality.isEmpty else { return false }
        return quality != Self.completeBuildQuality
    }

    /// L2-238: whether this payload may replace/extend what is already rendered.
    /// Genuine exhaustion (a COMPLETE build with no items) still applies — that
    /// is the one empty response that honestly means "all caught up".
    func mayReplaceRendered(hasRenderedItems: Bool) -> Bool {
        if isUnavailable { return false }
        if isDegradedBuild, items.isEmpty, hasRenderedItems { return false }
        return true
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        total = try c.decodeIfPresent(Int.self, forKey: .total) ?? 0
        limit = try c.decodeIfPresent(Int.self, forKey: .limit) ?? 50
        offset = try c.decodeIfPresent(Int.self, forKey: .offset) ?? 0
        hasMore = try c.decodeIfPresent(Bool.self, forKey: .hasMore) ?? false
        // Tolerant: malformed metadata degrades to "no metadata", never to a
        // decode failure that would take the whole feed down with it.
        cache = try? c.decodeIfPresent(FeedCacheMetadata.self, forKey: .cache)
        buildQuality = try? c.decodeIfPresent(String.self, forKey: .buildQuality)
        degradedReason = try? c.decodeIfPresent(String.self, forKey: .degradedReason)

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
        case items, total, limit, offset, hasMore, cache, buildQuality, degradedReason
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

    /// Memberwise init so a sanitized bundle can be rebuilt with a lifecycle-
    /// admitted child list while preserving identity, title, kind, and comparison
    /// theme (C29 P2 — see `withItems`).
    init(id: String, title: String, items: [FeedItem], kind: String?, comparisonTheme: String?) {
        self.id = id
        self.title = title
        self.items = items
        self.kind = kind
        self.comparisonTheme = comparisonTheme
    }

    /// Rebuild the bundle with a new child list, preserving all other metadata
    /// (C29 P2). Used to carry ONLY lifecycle-eligible children through category
    /// derivation, cooldown, interleaving, grouping, rendering, and analytics so
    /// every consumer derives its primary/category from the first ELIGIBLE child,
    /// never a stale raw first child.
    func withItems(_ newItems: [FeedItem]) -> FeedBundle {
        FeedBundle(id: id, title: title, items: newItems, kind: kind, comparisonTheme: comparisonTheme)
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
    let concept: FeedConceptData?
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
        if let c = concept { return "concept-\(c.key)" }
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
            concept = nil
        } else if type == "tournament" {
            tournament = try c.decodeIfPresent(FeedTournamentData.self, forKey: .data)
            event = nil
            futures = nil
            concept = nil
        } else if type == "concept" {
            // L2-179: event-concept marquee cards (Tour de France, World Cup, UFC
            // cards) carry a `data` shape with NO `id`/`name`-as-Int — decoding it
            // as FeedFuturesData throws, and the FeedResponse skip loop then silently
            // discarded EVERY concept card. That is why the native marquee never
            // appeared on device. Decode the real concept payload instead.
            concept = try c.decodeIfPresent(FeedConceptData.self, forKey: .data)
            event = nil
            futures = nil
            tournament = nil
        } else {
            futures = try c.decodeIfPresent(FeedFuturesData.self, forKey: .data)
            event = nil
            tournament = nil
            concept = nil
        }
    }

    /// Memberwise init supporting `withBundle` (C29 P2). All fields are copied
    /// verbatim; only bundle sanitization uses it today.
    init(
        type: String,
        score: Int,
        reason: String?,
        headline: String?,
        contextSummary: String?,
        event: FeedEventData?,
        futures: FeedFuturesData?,
        tournament: FeedTournamentData?,
        concept: FeedConceptData?,
        bundle: FeedBundle?,
        personalized: Bool?,
        baseScore: Int?,
        multiplier: Double?,
        personalizationReasons: [String]?
    ) {
        self.type = type
        self.score = score
        self.reason = reason
        self.headline = headline
        self.contextSummary = contextSummary
        self.event = event
        self.futures = futures
        self.tournament = tournament
        self.concept = concept
        self.bundle = bundle
        self.personalized = personalized
        self.baseScore = baseScore
        self.multiplier = multiplier
        self.personalizationReasons = personalizationReasons
    }

    /// Return a copy of this feed item carrying a sanitized bundle (C29 P2). Only
    /// the bundle child list changes; type/score/headline/personalization and the
    /// bundle's own identity/title/kind/theme are preserved so grouping, rendering,
    /// and analytics stay stable.
    func withBundle(_ newBundle: FeedBundle) -> FeedItem {
        FeedItem(
            type: type,
            score: score,
            reason: reason,
            headline: headline,
            contextSummary: contextSummary,
            event: event,
            futures: futures,
            tournament: tournament,
            concept: concept,
            bundle: newBundle,
            personalized: personalized,
            baseScore: baseScore,
            multiplier: multiplier,
            personalizationReasons: personalizationReasons
        )
    }
}

// MARK: - Feed Concept Data

/// Event-concept payload embedded inside a `concept`-type feed card — a marquee
/// hub (multi-day tournament / fight card / ceremony) that links to /event/{key}.
/// Probability-free: the card is a hub teaser, not a single market. Mirrors the
/// web `FeedConceptData` treatment (FeedCard.tsx `ConceptFeedCard`).
nonisolated struct FeedConceptData: Decodable, Identifiable, Sendable {
    let key: String
    let name: String
    let domain: String?
    let status: String?
    let startDate: String?
    let isMajor: Bool?
    let fightCount: Int?
    let entryCount: Int?
    let isMarquee: Bool?
    /// True only in the post-settlement T+36h WHAT-HIT window — the card renders
    /// "what happened" (winner/result) instead of the live/countdown framing.
    let marqueeWhathit: Bool?
    /// Graded champion, present only when a settled concept has an unambiguous
    /// crown. Never fabricated — render gracefully when absent.
    let winner: String?
    let resultSummary: String?

    var id: String { key }
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
    // #490 (L2-172 native half): confidence signal (1-3 bars). Decoded from
    // `confidence_tier`/`confidence_score` via the decoder's .convertFromSnakeCase.
    let confidenceTier: String?
    let confidenceScore: Double?
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
    // #490 (L2-172 native half): confidence signal (1-3 bars). Decoded from
    // `confidence_tier`/`confidence_score` via the decoder's .convertFromSnakeCase.
    let confidenceTier: String?
    let confidenceScore: Double?
    /// L2-225: authoritative settlement, sent by the backend on every effectively
    /// resolved futures card (`routes/feed.py` :6692–6694) and read by web as three
    /// of the four settlement authorities (`discover/utils.ts` `_futuresIsSettled`).
    /// The native model dropped all three, so both native lifecycle predicates could
    /// only ever consult `status`. Decoded from `resolved` / `winner` /
    /// `winner_opening_probability` via the decoder's `.convertFromSnakeCase`.
    let resolved: Bool?
    let winner: String?
    let winnerOpeningProbability: Double?
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
    /// #235 Item 4 / L2-159: calendar-flagged marquee tournament.
    let isMarquee: Bool?
    /// True only in the T+36h post-settlement WHAT-HIT window — the card leads with
    /// the result instead of a live leader line. L2-224: the backend has always sent
    /// this on every tournament card (`routes/feed.py` `_score_golf_tournaments`) and
    /// web has always read it (`FeedTournamentData.marquee_whathit`), but the native
    /// model dropped it — so a finished marquee rendered on iPhone with live framing
    /// and a "+Npp today" movement line. Decoded from `marquee_whathit` via the
    /// decoder's `.convertFromSnakeCase`.
    let marqueeWhathit: Bool?
}

/// Golfer entry in a tournament feed card.
nonisolated struct FeedTournamentGolfer: Decodable, Identifiable, Sendable {
    let name: String
    let probability: Double
    let rank: Int
    let movement24h: Double?

    var id: String { name }

    /// L2-225 — `movement24h` had **never decoded**, on any build.
    ///
    /// The client decodes with `.convertFromSnakeCase`, whose conversion capitalises
    /// each component after an underscore via `String.capitalized`. `"24h".capitalized`
    /// is `"24H"` — the digit is not a letter, so the *next* character is treated as
    /// the word's first letter and uppercased. The backend's `movement_24h` therefore
    /// arrives as the key `movement24H`, which never matched the property, and the
    /// tournament card's "+2.3pp today" mover line has been silently nil since it was
    /// written. Found by the L2-225 render fixture, which rasterised a live card whose
    /// movement line simply was not there.
    ///
    /// The explicit key below is matched against the CONVERTED key, hence the capital
    /// `H`. It looks wrong and is correct; the alternative (renaming the property to
    /// `movement24H`) hides the hazard instead of labelling it.
    ///
    /// This is a CLASS, not an instance — every `…24h` / `…7d` property decoded with
    /// this strategy is affected. The rest are on non-Discover surfaces and are routed
    /// rather than swept here; see the L2-225 report.
    enum CodingKeys: String, CodingKey {
        case name, probability, rank
        case movement24h = "movement24H"
    }
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

// MARK: - Feed Lifecycle (shared terminal-state semantics)

/// The single native source of truth for "is this card over?", mirroring the web
/// semantic in `frontend/components/discover/utils.ts` field for field (L2-225).
///
/// It exists because the same question was being answered in three different
/// places with three different answers: `DiscoverView.isStaleItem` consulted two
/// of the four futures authorities and had **no** tournament branch at all, while
/// `DiscoverViewModel.futuresIsSettled` consulted only one. Pure and `now`-injectable
/// so fixtures are deterministic (gotcha #44).
///
/// The two consumers read this fact with OPPOSITE polarity, and that is correct:
/// the Discover stale gate DROPS a settled card ("settled means settled", L2-191,
/// no restoration path), while the empty-envelope classifier KEEPS one (a settled
/// card carries an authoritative result, so it is not an empty envelope). Both are
/// asking the same question; only their answers differ.
nonisolated enum FeedLifecycle {
    /// Terminal MARKET status tokens — the same list web uses (`_SETTLED_STATUSES`).
    /// Deliberately excludes `completed`: markets never carry it, and matching web
    /// token-for-token is the point of this set.
    static let settledStatuses: Set<String> = [
        "resolved", "closed", "settled", "finalized", "final",
    ]

    /// Terminal SCHEDULE/EVENT status tokens. Tournaments and concepts speak the
    /// schedule vocabulary, not the market one — `_filter_stale_tournaments`
    /// (`routes/golf.py`) keys on exactly `schedule_status == "completed"`, and event
    /// concepts use the same `completed`/`closed` pair events do. Keeping the two
    /// sets separate is why this is a superset rather than an edit to the one above.
    static let terminalScheduleStatuses: Set<String> =
        settledStatuses.union(["completed"])

    /// Grace after a tournament's `end_date` before it counts as over. Mirrors the
    /// backend's own `_filter_stale_tournaments` (`routes/golf.py`), which drops a
    /// tournament once `end_date.date() < now.date() - 1 day` — i.e. somewhere
    /// between 24h and 48h past the end date. 48h is chosen so the client gate can
    /// never be MORE aggressive than the producer: it is containment for a
    /// stale-served golf base (#1475's `last_good` tier serves a base filtered when
    /// it was built, not when it is read), never a second opinion about liveness.
    static let tournamentEndGrace: TimeInterval = 48 * 3600

    /// Mirrors web `_futuresIsSettled` (`discover/utils.ts`): resolved flag, named
    /// winner, terminal status, or a resolution date already in the past. That last
    /// one is the authority that actually fires in production — gotcha #33 means a
    /// settled Kalshi market keeps `status='open'` forever.
    static func futuresIsSettled(_ d: FeedFuturesData, now: Date = Date()) -> Bool {
        if d.resolved == true { return true }
        if let winner = d.winner?.trimmingCharacters(in: .whitespacesAndNewlines),
           !winner.isEmpty { return true }
        if settledStatuses.contains((d.status ?? "").lowercased()) { return true }
        if let raw = d.resolutionDate, let date = raw.asDate, date < now { return true }
        return false
    }

    /// A tournament is over when the schedule says so, or when its end date has been
    /// past for longer than the producer's own grace. The T+36h WHAT-HIT window is
    /// NOT terminal for this purpose: that card is deliberately pinned to lead with
    /// the result (#235 Item 4 / L2-224), so it must survive the gate to be shown.
    static func tournamentIsSettled(_ d: FeedTournamentData, now: Date = Date()) -> Bool {
        if d.marqueeWhathit == true { return false }
        if terminalScheduleStatuses.contains((d.scheduleStatus ?? "").lowercased()) {
            return true
        }
        if let raw = d.endDate, let date = raw.asDate,
           now.timeIntervalSince(date) > tournamentEndGrace { return true }
        return false
    }

    /// A concept hub is over when its status says so and it is outside the WHAT-HIT
    /// window. (The empty-envelope classifier already fails a non-WHAT-HIT concept
    /// closed, so this is coherence rather than a second drop path.)
    static func conceptIsSettled(_ d: FeedConceptData, now: Date = Date()) -> Bool {
        if d.marqueeWhathit == true { return false }
        return terminalScheduleStatuses.contains((d.status ?? "").lowercased())
    }
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
