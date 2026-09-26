import Foundation

// MARK: - Search Response

/// Search results response containing teams, events, futures, and facets.
nonisolated struct SearchResponse: Decodable, Sendable {
    let query: String
    let teams: [SearchTeam]?
    /// Tournament/ceremony concepts the server derived from the matched markets
    /// (#999 L2-65). Optional because it post-dates this model and an older
    /// cached payload has no such key.
    let eventConcepts: [SearchEventConcept]?
    let results: [SearchEvent]
    let futures: [SearchFuturesMarket]
    /// Server-composed topical families (#993 L2-41/42) — the grouping that turns
    /// ten sibling rows into one answer. See `SearchFuturesFamily`.
    let futuresFamilies: [SearchFuturesFamily]?
    let pagination: SearchPagination?
    let sports: [SportFacet]?
    let filters: SearchFilters?
    let didYouMean: String?
    /// The stages `/api/events/search` could not finish (#1740 site 2).
    ///
    /// The route carries a 20,000 ms deadline and sheds stages rather than
    /// erroring when it runs out, naming each one it dropped here. ADDITIVE on
    /// the wire — `**({"degraded": degraded} if degraded else {})` at the payload
    /// site — so an absent key, and an empty list, both mean the answer really
    /// was complete. A list of stage names, NOT a boolean: `["futures"]`,
    /// `["teams", "event_count"]`.
    ///
    /// Undecoded until now, which is the whole defect: the phone saw six empty
    /// collections and printed "No results found for X" — an assertion about what
    /// exists, made from a request we abandoned. See `SearchAnswerState`.
    ///
    /// The stage names are for US, not for the reader: nothing built from this
    /// puts a stage name on screen (notice 34).
    let degraded: [String]?
}

/// A tournament, ceremony or race the query names, derived server-side from the
/// winner-field markets that matched (#999 L2-65).
///
/// `marketId` is the market it was DERIVED FROM, not a separate thing — which is
/// why `SearchGrouping.novelConcepts` exists. See the note there.
nonisolated struct SearchEventConcept: Decodable, Identifiable, Sendable {
    /// Canonical `event:<domain>:<slug>`.
    let key: String
    let name: String
    let domain: String?
    let marketId: Int?

    var id: String { key }
}

/// One server-composed family of related markets.
///
/// The server groups by story key or query-named entity, ranks the members, and
/// hands back a `headline` plus up to four `members`. A family forms only at two
/// or more members, so a lone market never arrives wrapped in group chrome.
///
/// Two counts, and they mean different things:
///  - `memberCount` is the TRUE family size (19 for Grand Slam Tennis today).
///  - `moreCount` is a promise about THIS PAGE: how many further members the
///    response also ships in the flat `futures` list, i.e. how many are drawn
///    BELOW this card. It is deliberately not `memberCount - shown` (#2646);
///    that read once printed "+6 more markets below" above a page with one.
nonisolated struct SearchFuturesFamily: Decodable, Identifiable, Sendable {
    let familyKey: String
    let label: String
    let headline: SearchFuturesMarket
    let members: [SearchFuturesMarket]
    let moreCount: Int?
    let memberCount: Int?

    var id: String { familyKey }
}

/// Event result returned by search endpoints.
nonisolated struct SearchEvent: Decodable, Identifiable, Sendable {
    let id: Int
    let externalId: String?
    let sport: String?
    let homeTeam: String
    let awayTeam: String
    let commenceTime: String?
    /// #8841 — the server's word that `commenceTime` is a PLACEHOLDER the venue
    /// has not announced (StatPal lists MLB postseason games on the hour before
    /// MLB sets a time; the Red Sox @ Yankees Wild Card games sat at 20:00Z and
    /// printed "Sep 29 1:00 PM"). The day is real, the clock is not. Optional
    /// because an older server or cache omits it; absent reads as `false` — read
    /// it as `startIsTbd == true`, never as a third state.
    let startIsTbd: Bool?
    let status: String?
    let homeScore: Int?
    let awayScore: Int?
    let metadata: EventMetadata?
    let espn: ESPNData?
    let winProbabilitySources: [String: WinProbSource]?
    let ei: EIData?
    let pulse: EIData?
    let currentOdds: CurrentOdds?
    let bookmakerOdds: [BookmakerOdds]?
    let highlight: Highlight?
    let openingOdds: OpeningOdds?
    /// The server's blended price for the HOME side, and its complement for the
    /// away side (`routes/events.py` serves `hero_probability` from
    /// `home_probability` and `hero_probability_away` from `away_probability`).
    ///
    /// #4967 — search serves these on rows that carry no `current_odds` at all,
    /// and the model did not name them, so `Decodable` dropped them in silence
    /// and the row drew no percentage. Named here as two plain optionals: the
    /// struct has no `CodingKeys` and the client decodes with
    /// `.convertFromSnakeCase`, so naming them IS the decode.
    let heroProbability: Double?
    let heroProbabilityAway: Double?

    /// The TEAM-PAGE rails' own probability pair, and the two orientation fields
    /// that come with them (`routes/teams.py::_format_event_brief`).
    ///
    /// #6444 — **this is #4967 exactly, one route over.** That fix named the two
    /// fields `/api/events` serves; the team brief serves two *differently named*
    /// ones and kept the bug. Its whole key set is
    ///
    ///     id · home_team · away_team · home_score · away_score · status
    ///     commence_time · sport_key · is_home · opponent · win_probability
    ///     pregame_win_probability · completed_at
    ///
    /// — no `current_odds`, no `hero_probability` — so the row that drew a
    /// percentage only from `currentOdds?.homeProbability` could never bind, and
    /// every Upcoming row on every team page drew no number at all, including a
    /// game an hour from first pitch. Measured on production 2026-09-15:
    /// `/api/teams/boston-red-sox-mlb` served a number on 8 of the 10 rows Alex
    /// saw blank.
    ///
    /// **`winProbability` is already THIS PAGE'S TEAM's number.** The server
    /// applies the away complement itself (`teams.py:559`) off the two-way
    /// normalised blend, so a client complement would be the #5363 defect
    /// re-introduced rather than avoided: do not take `1 −` it, and do not put it
    /// through `DrawPricedWinner`, whose input was the raw three-way book price
    /// this route does not serve. Cross-checked on a draw-priced league: Arsenal
    /// away at Brighton serves `win_probability` 0.730 beside a
    /// `pregame_win_probability` of 0.737 — the complement of the blend and the
    /// stored away column, two independent derivations, agreeing.
    ///
    /// 🔴 **`winProbability` IS NOT A RESULT.** On a settled row it is the last
    /// mid-game blend, frozen where capture stopped, and it contradicts the event
    /// page one tap away: measured 2026-09-15, 15309637 reads 0.079 here and
    /// `hero_probability: 0.0, source: "settled"` there; 15311111 reads 0.999
    /// against 1.0; 15312924 reads 0.036 against 0.0. A settled row prints
    /// `pregameWinProbability` as the call we made, which is what the web card
    /// does and why its docstring refuses the current number. ``TeamGameRow``
    /// owns that rule so no second surface has to rediscover it.
    let winProbability: Double?
    let pregameWinProbability: Double?
    /// Served orientation. Preferred over comparing `homeTeam` to the page's team
    /// name: one name variant flips the row to the wrong side silently, and the
    /// payload states the answer outright.
    let isHome: Bool?
    let opponent: String?
}

/// Futures market result returned by search endpoints.
nonisolated struct SearchFuturesMarket: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let sport: String?
    let sportName: String?
    let category: String?
    let llmSportCategory: String?
    let status: String?
    let source: String?
    let resolutionDate: String?
    let topOutcomes: [SearchFuturesOutcome]?
    let outcomeCount: Int?
    let updatedAt: String?
}

/// Top outcome for a futures market search result.
nonisolated struct SearchFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let americanOdds: Int?
    let rank: Int?
    let movement: Double?
    /// #8640: the leg's grade and who wrote it (latency's #8648). Read only
    /// through `OutcomeVerdict` — `is_winner` alone is not a grade. `var` with a
    /// default so the memberwise init keeps its old shape; `Decodable` still
    /// reads both keys.
    var isWinner: Bool? = nil
    var resolutionSource: String? = nil

    /// Has the venue already called this leg, as the row may say it?
    func verdict(in market: SearchFuturesMarket) -> OutcomeVerdict? {
        OutcomeVerdict.verdict(
            isWinner: isWinner,
            resolutionSource: resolutionSource,
            marketResolved: market.status == "resolved"
        )
    }
}

/// Pagination metadata for search results.
nonisolated struct SearchPagination: Decodable, Sendable {
    let page: Int
    let perPage: Int
    let totalResults: Int
    let totalPages: Int
    let hasNext: Bool
    let hasPrev: Bool
}

/// Sport facet count returned with search filters.
nonisolated struct SportFacet: Decodable, Sendable {
    let key: String
    let name: String
    let count: Int
}

/// Filters applied to a search request.
nonisolated struct SearchFilters: Decodable, Sendable {
    let sport: String?
    let daysBack: Int?
    let includeUpcoming: Bool?
}

// MARK: - Faceted Events Response

/// Paginated event results with facet counts for browse views.
nonisolated struct FacetedEventsResponse: Decodable, Sendable {
    let total: Int
    let page: Int
    let perPage: Int
    let filters: [String]
    let events: [FeedEventData]
    let facets: [String: [FacetTag]]
}

// MARK: - Faceted Futures Response

/// Paginated futures market results with facet counts for browse views.
nonisolated struct FacetedFuturesResponse: Decodable, Sendable {
    let total: Int
    let page: Int
    let perPage: Int
    let filters: [String]
    let markets: [FacetedFuturesMarket]
    let facets: [String: [FacetTag]]
}

/// Futures market row returned by faceted browsing.
nonisolated struct FacetedFuturesMarket: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let llmSportCategory: String?
    let source: String?
    let resolutionDate: String?
    let marketTags: [String]?
    let topOutcomes: [FacetedFuturesOutcome]?
    let outcomeCount: Int?
    let imageUrl: String?
    let hookDescription: String?
}

/// Outcome row embedded in a faceted futures market.
nonisolated struct FacetedFuturesOutcome: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let probability: Double?
    let movement: Double?
}

/// Named facet value and count used by browse filters.
nonisolated struct FacetTag: Decodable, Sendable {
    let tag: String
    let count: Int
}

// MARK: - Futures Movers Response

/// Response from the /api/futures/movers endpoint.
nonisolated struct FuturesMoversResponse: Decodable, Sendable {
    let movers: [FuturesMover]
    let timeframeHours: Int
}

/// Single outcome with significant probability movement.
nonisolated struct FuturesMover: Decodable, Identifiable, Sendable {
    let outcomeId: Int
    let name: String
    let marketId: Int
    let marketName: String?
    let currentProbability: Double?
    /// `probability_change_24h` / `rank_change_24h`. See `TolerantNumeric`.
    @TolerantNumeric var probabilityChange24h: Double?
    let currentAmericanOdds: Int?
    let rank: Int?
    @TolerantNumeric var rankChange24h: Int?

    var id: Int { outcomeId }

    private enum CodingKeys: String, CodingKey {
        case outcomeId, name, marketId, marketName, currentProbability
        case probabilityChange24h = "probabilityChange24H"
        case currentAmericanOdds, rank
        case rankChange24h = "rankChange24H"
    }
}

// MARK: - Typeahead Response

/// Typeahead suggestion response for the active query.
nonisolated struct TypeaheadResponse: Decodable, Sendable {
    let suggestions: [TypeaheadSuggestion]
    let query: String
    let didYouMean: String?
}

/// Trending search queries for search discovery.
nonisolated struct TrendingSearchesResponse: Decodable, Sendable {
    let trending: [TrendingQuery]
}

/// Single trending query and its usage count.
nonisolated struct TrendingQuery: Decodable, Identifiable, Sendable {
    let query: String
    let count: Int
    var id: String { query }
}

/// Search typeahead suggestion for a team, event, or market.
nonisolated struct TypeaheadSuggestion: Decodable, Identifiable, Sendable {
    let type: String
    let text: String
    let abbreviation: String?
    let logo: String?
    let teamId: Int?
    let teamSlug: String?
    let sportKey: String?
    let eventId: Int?
    let status: String?
    let commenceTime: String?
    let marketId: Int?
    let marketTier: Int?
    let marketTypeLabel: String?

    var id: String { "\(type)-\(text)-\(marketId ?? teamId ?? eventId ?? 0)" }
}

/// Team result returned by search.
nonisolated struct SearchTeam: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let slug: String?
    let abbreviation: String?
    let logo: String?
    let record: String?
    let sportKey: String?
}

// MARK: - Team Page

/// Full team page response with games, futures, and championship path.
nonisolated struct TeamPageResponse: Decodable, Sendable {
    let team: TeamPageTeam
    let upcomingEvents: [SearchEvent]
    let recentEvents: [SearchEvent]
    let futures: [TeamFutureItem]
    let championshipPath: [ChampionshipPathEntry]
}

/// Team identity and display metadata for a team page.
nonisolated struct TeamPageTeam: Decodable, Sendable {
    let id: Int
    let slug: String
    let name: String
    let abbreviation: String?
    let sportKey: String?
    let sportName: String?
    let primaryColor: String?
    let secondaryColor: String?
    let logoSmall: String?
    let logoLarge: String?
    let record: String?
    let standings: [String: AnyCodable]?
}

// TeamFutureItem defined in FuturesModels.swift (shared with team page + futures browsing)

/// One stage in a team's championship path summary.
nonisolated struct ChampionshipPathEntry: Decodable, Identifiable, Sendable {
    let tier: Int
    let label: String
    let marketName: String
    let marketId: Int
    let probability: Double?
    let rank: Int?
    let movement: Double?

    var id: Int { tier }
}

// AnyCodable moved to CommonTypes.swift
