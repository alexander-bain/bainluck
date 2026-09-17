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
    /// #4110: which ordered list this response is. Changes iff ordered
    /// MEMBERSHIP changes — never on a price, probability, score or reason move.
    /// Absent is a real state, not a legacy shim: an older backend, and every
    /// empty refusal, deliberately carry no token so three different failures are
    /// not reconciled as one agreed ordering. See `DiscoverFeedReconcile`.
    let edition: String?

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
        // #4110: tolerant for the same reason as the three above — a malformed
        // token degrades to ABSENT, which `DiscoverFeedReconcile` reads as "the
        // server states no ordering opinion" and reconciles. The one thing it
        // must never do is take the whole feed down over a string.
        edition = try? c.decodeIfPresent(String.self, forKey: .edition)

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
        case edition
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
    // Personalized ranking metadata can contain decimals, including on bundle children.
    let baseScore: Double?
    let multiplier: Double?
    let personalizationReasons: [String]?

    var id: String {
        if let e = event { return "event-\(e.id)" }
        if let f = futures { return "futures-\(f.id)" }
        if let t = tournament { return "tournament-\(t.key)" }
        if let c = concept { return "concept-\(c.key)" }
        // #1886: bundles decode for the first time, so they reach this property for
        // the first time too. Use the server's bundle id — the same identity
        // `DiscoverViewModel.stableKey` and `DiscoverView` already derive — rather
        // than the headline-composed fallback below, which would collide for two
        // bundles sharing a title.
        if let b = bundle { return "bundle-\(b.id)" }
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
        case type, score, reason, headline, contextSummary, data
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
        baseScore = try c.decodeIfPresent(Double.self, forKey: .baseScore)
        multiplier = try c.decodeIfPresent(Double.self, forKey: .multiplier)
        personalizationReasons = try c.decodeIfPresent([String].self, forKey: .personalizationReasons)

        if type == "event" {
            event = try c.decodeIfPresent(FeedEventData.self, forKey: .data)
            futures = nil
            tournament = nil
            concept = nil
            bundle = nil
        } else if type == "tournament" {
            tournament = try c.decodeIfPresent(FeedTournamentData.self, forKey: .data)
            event = nil
            futures = nil
            concept = nil
            bundle = nil
        } else if type == "bundle" {
            // #1886: bundles arrive as `{"type":"bundle","data":{…}}` — MEASURED,
            // twice: 0 of 83 live items (2026-08-14) and 0 of 60 (2026-08-17)
            // carried a top-level `bundle` key, and all four backend emitters in
            // `app/utils/discover_bundles.py` serialise under `data`. The old
            // decoder read a `bundle` key no server has ever sent, so `bundle` was
            // ALWAYS nil, every bundle fell through to the `futures` branch below,
            // and decoding a bundle's `data` as `FeedFuturesData` threw on the
            // string `id` ("theme:story:us_2028_election:…" vs an Int). The
            // FeedResponse skip loop then ate the card: the six curated theme cards
            // ("2028 Election", "Fed & Rates", "Middle East"…) have never rendered.
            //
            // This is the L2-179 concept bug — see the branch directly below — in
            // its own neighbour. The concept case got a branch; the bundle case
            // never did, and the repaired copy is what hid the broken one.
            //
            // The fictional `bundle` key is DELETED rather than kept as a fallback:
            // a tolerated second wire shape is the same "two rules" defect the
            // cycle-80 classifier unification removed, and it is what let every
            // bundle fixture in the suite agree with the bug for so long.
            bundle = try c.decodeIfPresent(FeedBundle.self, forKey: .data)
            event = nil
            futures = nil
            tournament = nil
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
            bundle = nil
        } else {
            futures = try c.decodeIfPresent(FeedFuturesData.self, forKey: .data)
            event = nil
            tournament = nil
            concept = nil
            bundle = nil
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
        baseScore: Double?,
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
    /// ⚠️ ROUTING, NOT A CLAIM ABOUT THE SPORT. Every card the combat adapter
    /// emits carries `domain == "ufc"` — it is the adapter key, the URL segment
    /// and the gradient, never something a source said. Measured 2026-09-17:
    /// 8 of 8 concept cards on `GET /api/feed?limit=150` read `ufc`, including
    /// **Power Slap 23** (slap fighting) and Contender Series cards. Use
    /// ``sportLabel`` for anything a reader sees; use this only to route.
    let domain: String?
    /// What to CALL this card's sport — the only field here a source stands
    /// behind (#5603 / Brief 18). Absent, never blank, when the server has
    /// nothing to say. Values by evidence: `UFC` (a venue's own fight series, or
    /// every venue title names it), `Combat` (a venue title names another
    /// promotion), `MMA` (schedule rows only, no promoter named). Boxing is its
    /// own adapter and emits nothing here, as does every non-combat domain.
    let sportLabel: String?
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
    /// #1882: the favourite and its probability for a concept that is NOT settled.
    /// Mutually exclusive with `winner` by construction on the server — settled
    /// means settled, so a card with a result never also carries a live
    /// probability. Absent when the concept has no usable field, which is what
    /// keeps the honest-empty path (#1486) intact.
    let leader: FeedConceptLeader?

    var id: String { key }

    /// The sport chip a reader sees on a concept card.
    ///
    /// Mirrors web's `conceptDomainLabel` (`frontend/components/discover/utils.ts`)
    /// exactly, so the two surfaces cannot drift into labelling one card two ways.
    ///
    /// 🪤 **The fallback is the whole fix — it is NOT `sportLabel ?? domain`.**
    /// That spelling reinstates the defect for every payload without the field:
    /// every response served before the backend half released, every one sitting
    /// in a `URLCache`, and every device still running an older build. Those are
    /// exactly the cards nobody re-checks after the ship.
    ///
    /// So when the server has said nothing, `ufc` — the one mixed namespace —
    /// degrades to the honest **COMBAT** rather than asserting UFC. Power Slap
    /// and Contender Series cards ride that adapter, so `UFC` there is a claim no
    /// source made. Every other domain keeps the label it has always had: `boxing`
    /// is its own adapter and its own sport, so `BOXING` is true.
    ///
    /// A blank string falls through rather than winning, or the chip renders
    /// empty — the one outcome worse than either label.
    static func sportChip(sportLabel: String?, domain: String?) -> String {
        let declared = (sportLabel ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !declared.isEmpty { return declared.uppercased() }
        let routing = (domain ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if routing.lowercased() == "ufc" { return "COMBAT" }
        return routing.isEmpty ? "EVENT" : routing.uppercased()
    }

    /// This card's chip.
    var sportChip: String { Self.sportChip(sportLabel: sportLabel, domain: domain) }
}

/// #1882: the favourite of an unsettled concept. Deliberately the same shape as
/// `FeedTournamentGolfer` so the concept card can reuse the tournament hero
/// rather than inventing a second probability treatment.
nonisolated struct FeedConceptLeader: Decodable, Sendable {
    let name: String
    let probability: Double
    let movement24h: Double?
    /// How many competitors the probability was chosen from — a two-way fight and
    /// a 20-car field mean different things at the same number.
    let fieldSize: Int?

    /// The `…24h` decode hazard L2-225 documented on `FeedTournamentGolfer`, met
    /// again here. `.convertFromSnakeCase` capitalises each component after an
    /// underscore with `String.capitalized`, and `"24h".capitalized` is `"24H"` —
    /// the digit is not a letter, so the `h` is treated as the word's first
    /// letter. The server's `movement_24h` therefore arrives as `movement24H`.
    ///
    /// Worth noting how this was caught: the class was already written down, in
    /// the sibling struct 300 lines below, and it still cost a build — the test
    /// asserting a real movement value is what found it, not the reading. A
    /// documented hazard is not a solved one, which is exactly why L2-225 called
    /// it "a CLASS, not an instance".
    enum CodingKeys: String, CodingKey {
        case name, probability, fieldSize
        case movement24h = "movement24H"
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
    // #490 (L2-172 native half): confidence signal (1-3 bars). Decoded from
    // `confidence_tier`/`confidence_score` via the decoder's .convertFromSnakeCase.
    let confidenceTier: String?
    let confidenceScore: Double?
    /// Server-resolved participant imagery for INDIVIDUAL sports (#2919 /
    /// `utils/participant_images.py`), decoded from `home_image_url` /
    /// `away_image_url` / `home_flag_url` / `away_flag_url`. Every event carries
    /// all four keys and any of them may be null — deliberately, so "the server
    /// didn't say" and "there is no photo" cannot be confused. Team sports get
    /// nulls and keep their crests.
    ///
    /// The web has drawn these since 2026-09-03; the phone drew "A" and "Q" for
    /// the same match because these four keys were the only fields on the payload
    /// the native model did not decode.
    let homeImageUrl: String?
    let awayImageUrl: String?
    let homeFlagUrl: String?
    let awayFlagUrl: String?
    /// D109/#4676's whistle stamp, decoded from `ended_at`. The clock a finished
    /// card ages on (#4776 / #6440) — see `FeedLifecycle.finishedEventAgeAnchor`,
    /// which says why it is this field and not `commence_time`.
    ///
    /// OPTIONAL by the producer's own rule: absent on every unsettled row, and a
    /// cached payload can predate the stamp. NOT FOR DISPLAY — it is
    /// `completed_at` when StatPal reported no end, so it runs later than the
    /// true whistle by a variable margin and must never be printed as "ended at".
    let endedAt: String?
    /// Whether Discover kept this finished game on purpose — `discover_marquee_final`,
    /// stamped in `app/routes/feed.py` on finished event cards only, `false` as
    /// well as `true`. Absent means "this payload came from a surface that does
    /// not select marquee finals" (the Sports feed is one), which reads as the
    /// ordinary window. Never coalesce an absent flag into the long one.
    let discoverMarqueeFinal: Bool?
}

/// What a card should draw in one participant's avatar slot, and how.
nonisolated struct ParticipantAvatar: Sendable, Equatable {
    /// Nil hands the decision back to the view's own ladder (client-derived flag →
    /// ESPN-by-name → coloured initials), i.e. exactly the pre-#2919 behaviour.
    let url: String?
    /// True ONLY for a served headshot. A headshot is a portrait; a crest and a
    /// flag are not. Fitting a portrait into a square slot letterboxes it into a
    /// sliver about half the width of the crest beside it — measured on the
    /// simulator the first time faces landed, and the reason this flag follows
    /// what is actually being drawn rather than what the sport usually gets.
    let isPhotograph: Bool

    static let none = ParticipantAvatar(url: nil, isPhotograph: false)
}

extension FeedEventData {
    /// The avatar for one side, in the web's precedence (`FeedCard.tsx`:394-400):
    /// served headshot → served flag → the team crest this card already had.
    ///
    /// Ordered this way on purpose: a served flag beats a crest only because the
    /// server sends flags for individual sports alone, where there is no crest to
    /// displace. A team card is therefore unchanged by these keys.
    func avatar(home: Bool) -> ParticipantAvatar {
        let face = home ? homeImageUrl : awayImageUrl
        if let face, !face.isEmpty { return ParticipantAvatar(url: face, isPhotograph: true) }
        let flag = home ? homeFlagUrl : awayFlagUrl
        if let flag, !flag.isEmpty { return ParticipantAvatar(url: flag, isPhotograph: false) }
        let crest = home ? homeTeamData?.logoSmall : awayTeamData?.logoSmall
        return ParticipantAvatar(url: crest, isPhotograph: false)
    }
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
    /// #1885: the server's story family for this market ("story:russia_ukraine",
    /// "story:foreign_local_elections"), promoted out of the backend's internal
    /// `_quality_story_key` in `routes/feed.py`. Nil when the market belongs to no
    /// named family — which is the majority, and is exactly why the interleave
    /// must degrade to plain category rather than treat nil as a family of its
    /// own. Decoded from `story_key` via `.convertFromSnakeCase`.
    let storyKey: String?
    /// #6343: when the prices this card PRINTS were last seen — the oldest of the
    /// printed legs, computed by `_card_price_observed_at` (`routes/feed.py`) and
    /// served by both futures serializers since #5752. NOT `resolutionDate`, which
    /// is when the question gets answered; the two were confused on the US Open
    /// final page, where a card an hour stale sat under a hero stamped 20s.
    ///
    /// The native model dropped it, so no phone surface could render an age at all
    /// while the web marked the same cards `● 3d ago`. Decoded from
    /// `price_observed_at` via the decoder's `.convertFromSnakeCase`; rendered by
    /// `PriceAgeMarkView`, dated by `SourceAge`.
    let priceObservedAt: String?
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

    // MARK: - Finished games: how long a final may stay on a feed (#6440)

    /// Hours a finished game may still render before the client deletes it.
    /// Web's `COMPLETED_EVENT_MAX_AGE_HOURS` (`lib/discover/feedFreshness.ts`),
    /// pinned to it by `frontend/__tests__/lib/finishedCardAgeParity.test.ts`.
    static let completedEventMaxAgeHours: Double = 8

    /// The longer window for the one or two finished games Discover kept ON
    /// PURPOSE — web's `MARQUEE_FINAL_MAX_AGE_HOURS` (D118 = B, Alex, 2026-09-10).
    /// Eight hours from the whistle retired the NFL season opener at 4:26am
    /// Pacific; fourteen puts an 8:30pm final on the page with the morning coffee.
    /// It is scoped to the flagged cards because that is the promise Alex was
    /// given — widening the constant above would move `/sports`' window too.
    static let marqueeFinalMaxAgeHours: Double = 14

    /// How long THIS finished card may live. Mirrors web's
    /// `finishedEventMaxAgeHours`: `true` and nothing looser, because the
    /// expensive direction of the error is keeping a dead card.
    static func finishedEventMaxAgeHours(_ e: FeedEventData) -> Double {
        e.discoverMarqueeFinal == true ? marqueeFinalMaxAgeHours : completedEventMaxAgeHours
    }

    /// When that clock starts — the whistle, not the kickoff (#4776).
    ///
    /// Ageing from `commence_time` charges a finished card for its own duration:
    /// a measured median 2.26h across the 39 finished games served on 2026-09-10
    /// (2.78h MLB, 3.11h NFL), so the eight hours above were really 5.7. `ended_at`
    /// is optional — absent on unsettled rows, and a cached payload can predate it
    /// — so falling back to `commence_time` is the contract, not defensive dressing.
    static func finishedEventAgeAnchor(_ e: FeedEventData) -> Date? {
        if let raw = e.endedAt, let d = raw.asDate { return d }
        if let raw = e.commenceTime, let d = raw.asDate { return d }
        return nil
    }

    /// True when a client should delete this finished card before it paints — the
    /// single native answer to the question web answers in `isStale`'s event arm
    /// and the backend mirrors in `client_deletes_finished_card`.
    ///
    /// It exists because that one rule had three implementations and two of them
    /// were wrong (#6440): web ages a final out at 8h/14h from `ended_at`, native
    /// Discover aged it out at 8h from KICKOFF with no marquee exemption, and the
    /// native Sports tab had no age term at all — so the phone rendered finals that
    /// bainluck.com/sports deletes (four of them 17.3–20.2h old, 2026-09-15 22:06Z).
    ///
    /// Two details are load-bearing. The comparison is strict `>`, so a card at
    /// exactly the threshold is RENDERED. And an unreadable or absent anchor KEEPS
    /// the card: unknown age has never meant "old" here, matching web, where the
    /// same case yields `NaN > 8 === false`.
    static func finishedEventIsExpired(_ e: FeedEventData, now: Date = Date()) -> Bool {
        guard EventState.isFinished(e.status) else { return false }
        guard let anchor = finishedEventAgeAnchor(e) else { return false }
        return now.timeIntervalSince(anchor) > finishedEventMaxAgeHours(e) * 3600
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
