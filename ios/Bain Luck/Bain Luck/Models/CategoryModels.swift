import Foundation

// MARK: - Shared Market Row (Politics + Entertainment)

/// Shared category market row used by politics and entertainment dashboards.
nonisolated struct CategoryMarketRow: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId ?? 0)-\(q)" }
    let q: String
    let prob: Double
    let src: String
    let marketId: Int?
    let topOutcomes: [CategoryOutcome]
    let outcomeCount: Int
}

/// Outcome probability embedded in a category market row.
///
/// **#888 — ONE TYPE, TWO SERVER VOCABULARIES, AND ONLY ONE OF THEM EVER
/// DECODED.** This struct was written for the politics/entertainment dashboards,
/// which serve the terse row shape (`q` / `prob` / `src`), and its outcomes
/// arrive as `{"name": …, "prob": …}`. `/api/leagues/{sport_key}` reuses the
/// same Swift type for `top_outcomes` and serves the VERBOSE shape:
/// `{"name": …, "probability": …, "opening_probability": …, "rank": …}`.
///
/// `probability` carries no underscore, so `.convertFromSnakeCase` leaves it
/// `probability`, which does not match `prob`. Measured against production
/// 2026-09-17 on the real NBA payload:
///
///     DecodingError.keyNotFound: Key 'prob' not found
///     Path: sections.awards[0].topOutcomes[0]
///
/// One throw at the first outcome of the first market fails the WHOLE
/// `LeagueMarketsResponse`, `LeagueGridViewModel.loadLeagueMarkets` swallows it
/// into a `logger.debug`, and `viewModel.leagueMarkets` stays nil — so the
/// league page has rendered **zero** market sections on every league, not a
/// reduced set. That is the complaint on #888 ("league buttons show only title
/// grids, no other content") in one line, and it sits UNDER the dead section
/// keys: with the keys repaired and this not, the page still draws nothing.
///
/// Both spellings are accepted rather than one being declared canonical. The
/// two endpoints are entitled to their own vocabularies, a client rename would
/// break the other one, and a server rename is not native's file to change.
///
/// ## THE TWO VOCABULARIES ALSO USE TWO SCALES, AND THE KEY IS WHAT SAYS WHICH
///
/// `prob` is a PERCENT and `probability` is a FRACTION. Measured 2026-09-17:
/// `/api/politics` serves 198 values spanning 0.0–98.0, `/api/leagues/…` serves
/// 445 spanning 0.0095–0.99. Every reader of this type — `PoliticsView`,
/// `LeagueGridView`, `SportCategoryView` — prints `Int(o.prob)%` and compares
/// against 50, so the type's invariant is PERCENT and the fraction is converted
/// here, once, where the key that identifies it is still in scope.
///
/// **A value-range heuristic would be wrong, not merely inelegant**: 36 of the
/// 198 politics values are ≤ 1.0 — genuine sub-1% candidates — and "looks like a
/// fraction" would silently divide them by a hundred. The SPELLING is the
/// signal; the magnitude is not.
///
/// Without the conversion the league page draws every market at **0%**
/// (`Int(0.43) == 0`), which is how the repaired sections first photographed:
/// present, populated, and every line reading zero.
nonisolated struct CategoryOutcome: Decodable, Sendable {
    let name: String
    /// Percent, 0–100. Both server spellings normalise to this.
    let prob: Double

    private enum CodingKeys: String, CodingKey {
        case name
        /// Politics/entertainment: already a percent.
        case prob
        /// `/api/leagues/{sport_key}`: the same number as a fraction of 1.
        case probability
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        name = try c.decode(String.self, forKey: .name)
        if let percent = try c.decodeIfPresent(Double.self, forKey: .prob) {
            prob = percent
        } else {
            // Not `try?` with a fallback of 0: an outcome with no probability at
            // all is not a 0% outcome, and drawing it as one would be a lie in
            // the one place this row exists to be honest. It throws, and the
            // lossy containers around it drop that single row.
            prob = try c.decode(Double.self, forKey: .probability) * 100
        }
    }

    init(name: String, prob: Double) {
        self.name = name
        self.prob = prob
    }
}

// MARK: - Source counts (shared)

/// Count of available markets by prediction market source.
nonisolated struct SourceCounts: Decodable, Sendable {
    let kalshi: Int
    let polymarket: Int
}

// MARK: - Politics

/// Politics dashboard response with themed sections and source comparison.
nonisolated struct PoliticsResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let themes: PoliticsThemes
    let crossSource: [CrossSourceMatch]?
    let bySource: SourceCounts
}

/// Theme buckets returned by the politics dashboard.
nonisolated struct PoliticsThemes: Decodable, Sendable {
    let presidential: PoliticsPresidential?
    let congressional: PoliticsCongressional?
    let gubernatorial: PoliticsSimple?
    let policy: PoliticsSimple?
    let scotus: PoliticsSimple?
    let international: PoliticsSimple?
    let other: PoliticsSimple?
}

/// Presidential market section with candidates and related markets.
nonisolated struct PoliticsPresidential: Decodable, Sendable {
    let count: Int
    let headlineQ: String?
    let candidates: [PoliticsCandidate]
    let hasDualSource: Bool?
    let kalshiMarketId: Int?
    let polyMarketId: Int?
    let sideMarkets: [CategoryMarketRow]?
}

/// Candidate probability row for presidential markets.
nonisolated struct PoliticsCandidate: Decodable, Identifiable, Sendable {
    var id: String { name }
    let name: String
    let party: String
    let kalshi: Double?
    let poly: Double?
    let merged: Double
    /// `change_7d`. `"7d".capitalized == "7D"`, so the key is `change7D`.
    /// See `TolerantNumeric`.
    @TolerantNumeric var change7d: Double?
    let history: [ProbPoint]?

    private enum CodingKeys: String, CodingKey {
        case name, party, kalshi, poly, merged
        case change7d = "change7D"
        case history
    }
}

/// Historical probability point for a politics candidate.
nonisolated struct ProbPoint: Decodable, Sendable {
    let t: String
    let p: Double
}

/// Congressional market section with chamber control context.
nonisolated struct PoliticsCongressional: Decodable, Sendable {
    let count: Int
    let markets: [CategoryMarketRow]?
    let chamberControl: ChamberControlData?
    let senateMap: [String: Double]?
}

/// Senate and House control probabilities.
nonisolated struct ChamberControlData: Decodable, Sendable {
    let senate: ChamberControl?
    let house: ChamberControl?
}

/// Party control probabilities for one chamber.
nonisolated struct ChamberControl: Decodable, Sendable {
    let gop: Double
    let dem: Double
    let marketId: Int?
}

/// Matched Kalshi and Polymarket rows for the same political question.
nonisolated struct CrossSourceMatch: Decodable, Identifiable, Sendable {
    var id: String { "\(kalshiMarketId)-\(polyMarketId)" }
    let q: String
    let kalshi: Double
    let poly: Double
    let delta: Double
    let category: String?
    let kalshiMarketId: Int
    let polyMarketId: Int
}

/// Simple politics theme containing a market count and rows.
nonisolated struct PoliticsSimple: Decodable, Sendable {
    let count: Int
    let markets: [CategoryMarketRow]?
}

// MARK: - Entertainment

/// Entertainment dashboard response with themed market sections.
nonisolated struct EntertainmentResponse: Decodable, Sendable {
    let totalMarkets: Int
    let updatedAt: String?
    let trending: [EntMarketRow]?
    let themes: EntThemes
    let culturalMoments: [EntMarketRow]?
    let bySource: SourceCounts
}

/// Theme buckets returned by the entertainment dashboard.
nonisolated struct EntThemes: Decodable, Sendable {
    let music: EntThemeMusic?
    let moviesTv: EntThemeMoviesTV?
    let techCulture: EntThemeTechCulture?
}

/// Entertainment market row with outcomes, media, and hook metadata.
nonisolated struct EntMarketRow: Decodable, Identifiable, Sendable {
    var id: String { "\(marketId)-\(q)" }
    let q: String
    let prob: Double
    let src: String
    let marketId: Int
    let externalId: String?
    let kind: String?
    let topOutcomes: [EntOutcome]
    let outcomeCount: Int
    /// `volume_24h`. See `TolerantNumeric`.
    @TolerantNumeric var volume24h: Int?
    let resolutionDate: String?
    let imageUrl: String?
    let hook: String?

    private enum CodingKeys: String, CodingKey {
        case q, prob, src, marketId, externalId, kind, topOutcomes, outcomeCount
        case volume24h = "volume24H"
        case resolutionDate, imageUrl, hook
    }
}

/// Outcome probability and movement for an entertainment market.
nonisolated struct EntOutcome: Decodable, Sendable {
    let name: String
    let prob: Double
    /// `delta_24h`. See `TolerantNumeric`.
    @TolerantNumeric var delta24h: Double?

    private enum CodingKeys: String, CodingKey {
        case name, prob
        case delta24h = "delta24H"
    }
}

/// Group of related entertainment threshold markets for one title or entity.
nonisolated struct EntThresholdGroup: Decodable, Identifiable, Sendable {
    var id: String { title }
    let title: String
    let imageUrl: String?
    let thresholds: [EntThreshold]
}

/// One threshold probability inside an entertainment threshold group.
nonisolated struct EntThreshold: Decodable, Sendable {
    let label: String
    let prob: Double
    let marketId: Int
}

/// Music-focused entertainment market groups.
nonisolated struct EntThemeMusic: Decodable, Sendable {
    let count: Int
    let spotifyRace: [EntMarketRow]?
    let billboardWatch: [EntMarketRow]?
    let billboardGroups: [EntThresholdGroup]?
    let albumDrops: [EntMarketRow]?
    let artistStreaming: [EntMarketRow]?
    let sideMarkets: [EntMarketRow]?
}

/// Movie and TV-focused entertainment market groups.
nonisolated struct EntThemeMoviesTV: Decodable, Sendable {
    let count: Int
    let rtGroups: [EntThresholdGroup]?
    let rtMarkets: [EntMarketRow]?
    let boxOfficeGroups: [EntThresholdGroup]?
    let boxOffice: [EntMarketRow]?
    let realityTv: [EntMarketRow]?
    let sideMarkets: [EntMarketRow]?
}

/// Tech and culture entertainment market group.
nonisolated struct EntThemeTechCulture: Decodable, Sendable {
    let count: Int
    let markets: [EntMarketRow]?
}

// MARK: - League Markets

/// League-level futures markets grouped into display sections.
///
/// **#888 — ONE BAD ROW MUST NOT COST THE WHOLE PAGE.** Every field of
/// `LeagueMarketItem` that matters is non-optional inside a non-optional array
/// inside a non-optional dictionary, so before this the first unreadable outcome
/// anywhere in the payload took all 64 of NBA's markets with it, silently (the
/// view model swallows the throw and leaves `leagueMarkets` nil). That is
/// gotcha #42 — "one bad item must never wipe a whole pass" — on the client,
/// and it is the same rule `CalibrationModels` already applies to its ~1,600
/// buckets. `LossyArray` is that shipped primitive, reused rather than
/// re-invented.
///
/// The drops are COUNTED, not silent. Nothing puts them on a reader's screen
/// (standing notice 34: no diagnostic prose on a page) — they exist so a test
/// and the view model's log can tell "the league served two markets" from "the
/// league served sixty-four and we could read two".
nonisolated struct LeagueMarketsResponse: Decodable, Sendable {
    let sportKey: String
    let sections: [String: [LeagueMarketItem]]
    let totalMarkets: Int
    /// Market rows the payload carried and this client could not read.
    let droppedMarkets: Int

    private enum CodingKeys: String, CodingKey {
        case sportKey, sections, totalMarkets
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sportKey = try c.decode(String.self, forKey: .sportKey)
        totalMarkets = try c.decode(Int.self, forKey: .totalMarkets)

        let lossy = try c.decode([String: LossyArray<LeagueMarketItem>].self, forKey: .sections)
        sections = lossy.mapValues(\.elements)
        droppedMarkets = lossy.values.reduce(0) { $0 + $1.dropped }
    }

    init(sportKey: String, sections: [String: [LeagueMarketItem]], totalMarkets: Int,
         droppedMarkets: Int = 0) {
        self.sportKey = sportKey
        self.sections = sections
        self.totalMarkets = totalMarkets
        self.droppedMarkets = droppedMarkets
    }
}

/// Single league market row in a league market section.
nonisolated struct LeagueMarketItem: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let source: String
    let marketTier: Int?
    let category: String?
    let resolutionDate: String?
    let outcomeCount: Int?
    let topOutcomes: [CategoryOutcome]?
    let section: String?

    private enum CodingKeys: String, CodingKey {
        case id, name, source, marketTier, category, resolutionDate, outcomeCount,
             topOutcomes, section
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        name = try c.decode(String.self, forKey: .name)
        source = try c.decode(String.self, forKey: .source)
        marketTier = try c.decodeIfPresent(Int.self, forKey: .marketTier)
        category = try c.decodeIfPresent(String.self, forKey: .category)
        resolutionDate = try c.decodeIfPresent(String.self, forKey: .resolutionDate)
        outcomeCount = try c.decodeIfPresent(Int.self, forKey: .outcomeCount)
        section = try c.decodeIfPresent(String.self, forKey: .section)

        // The market's NAME is the row; its top outcomes are the three lines
        // under it. An outcome this client cannot read costs that line, never
        // the row and never the page — the row still carries the market the
        // reader came for. `nil` and `[]` mean the same thing to the view, so
        // an absent key stays absent rather than becoming an empty array.
        topOutcomes = try c.decodeIfPresent(LossyArray<CategoryOutcome>.self,
                                            forKey: .topOutcomes)?.elements
    }

    init(id: Int, name: String, source: String, marketTier: Int? = nil, category: String? = nil,
         resolutionDate: String? = nil, outcomeCount: Int? = nil,
         topOutcomes: [CategoryOutcome]? = nil, section: String? = nil) {
        self.id = id
        self.name = name
        self.source = source
        self.marketTier = marketTier
        self.category = category
        self.resolutionDate = resolutionDate
        self.outcomeCount = outcomeCount
        self.topOutcomes = topOutcomes
        self.section = section
    }
}
