/**
 * TypeScript types for Bain Luck frontend
 */

import type { ConfidenceSignals } from "@/lib/confidence";
// The props section is shared with the tournament hub's match rows — one
// definition of a prop card, not a second copy that agrees today (UX-P152).
import type { MatchProp } from "@/lib/matchDetail";

export interface Sport {
  id: number;
  key: string;
  name: string;
  group: string | null;
}

export interface CurrentOdds {
  bookmaker?: string;
  captured_at: string;
  home_moneyline?: number | null;
  away_moneyline?: number | null;
  home_probability: number | null; // 0.0-1.0
  away_probability: number | null; // 0.0-1.0
  // UX-P114: the whole percents the card PRINTS for the two probabilities above.
  // A game card draws both sides at once and the feed derives away as `1 - home`,
  // so rounding them independently printed 101 whenever the blend landed on a
  // half-percent (34 of 414 live/upcoming events, 2026-08-21). The decision is made
  // once on the server because four surfaces draw this strip; optional here, and
  // every consumer must fall back to `renderedDuelPercents`, because a cached or
  // pre-deploy payload will not carry it. See contracts/rendered_percent.json.
  home_rendered_percent?: number | null;
  away_rendered_percent?: number | null;
  spread: number | null;
  home_spread?: number | null;
  over_under: number | null;
  projected_home_score: number | null;
  projected_away_score: number | null;
  bookmaker_count?: number;
  source?: string;
  // #1854 (UX-P077): `probability_range` was declared here and rendered by
  // nothing. The backend served the SPORTSBOOK min/max beside a hero that is the
  // multi-source blend, so the number this type describes sat outside its own
  // stated range (measured: 0.2813 in 0.6117–0.626). Declaring an unrendered
  // field is what made it a trap — the next person to reach for it would have
  // drawn a hero outside its envelope with every reason to trust the payload.
  // The field is gone from both hero payloads; the type goes with it.
}

export interface HighlightFlags {
  is_live: boolean;
  is_close_matchup: boolean;
  is_blowout: boolean;
  favorite_switched: boolean;
  probability_swing: "major" | "minor" | "stable";
  score_swing: "major" | "minor" | "stable";
  is_starting_soon: boolean;
  is_recently_finished: boolean;
  is_upset: boolean;
  league_tier: number;
}

export interface Highlight {
  score: number;
  reasons: string[];
  label: string | null;
  should_feature: boolean;
  flags: HighlightFlags;
}

export interface OpeningOdds {
  home_probability: number;
  away_probability: number | null;
  spread: number | null;
  over_under: number | null;
  favorite: "home" | "away" | "even" | null;
}

export interface EIMetadata {
  // New EI format
  raw_ei?: number;
  lead_changes: number;
  comeback_factor?: number;
  snapshot_count?: number;
  // Old Pulse format (backward compatibility for pre-migration events)
  heart_rate?: number;
  amplitude?: number;
  arrhythmia?: number;
  vitals?: number;
  time_weight?: number;
}

export interface EIData {
  score: number;           // 1-100 (percentile when available, raw otherwise)
  raw_score?: number;      // 1-100 raw score before percentile mapping
  status: string;          // 'incredible' | 'exciting' | 'competitive' | 'quiet' | 'flat'
  label: string;           // 'Must-Watch', 'Exciting', etc.
  emoji: string;           // 🔥 ⚡ 💪 😐 💤
  metadata?: EIMetadata;
}

// Backward compatibility aliases
export type GEIComponents = EIMetadata;
export type ExcitementData = EIData;
export type PulseComponents = EIMetadata;
export type PulseData = EIData;

export interface ESPNData {
  espn_id?: string;
  game_clock?: string;
  period?: string;
  broadcast?: string;
  win_probability?: number;  // 0.0-1.0, home team
}

export interface TeamData {
  primary_color: string | null;    // Hex e.g. "#552583"
  secondary_color: string | null;
  logo_small: string | null;       // Small logo URL
  logo_large: string | null;       // Large logo URL
  record: string | null;           // e.g. "34-18"
  standings?: {
    wins?: number;
    losses?: number;
    pct?: string;
    conf_rank?: number;
    div_rank?: number;
    conference?: string;
    division?: string;
    games_behind?: number;
  } | null;
  season_stats?: Record<string, number | string> | null;
  abbreviation?: string | null;
}

export interface Event {
  id: number;
  external_id: string;
  sport: string | null;
  home_team: string;
  away_team: string;
  commence_time: string;
  // Authoritative finished-event date; prefer over commence_time for FINAL cards
  // to avoid rendering a stale/future date beside a Final badge (Queue #189 §B).
  completed_at?: string | null;
  status: "scheduled" | "live" | "completed" | "closed";
  home_score: number | null;
  away_score: number | null;
  current_odds?: CurrentOdds;
  bookmaker_odds?: BookmakerOddsDetail[];
  highlight?: Highlight;
  opening_odds?: OpeningOdds;
  event_tags?: string[];
  ei?: EIData;
  /** @deprecated Use `ei` instead */
  excitement?: EIData;
  /** @deprecated Use `ei` instead */
  pulse?: EIData;
  espn?: ESPNData;
  home_team_data?: TeamData;
  away_team_data?: TeamData;
  win_probability_sources?: Record<string, { value: number; display_name: string; type: string; color: string }>;
  standings_context?: {
    home?: string;   // e.g. "34-18, 2nd East"
    away?: string;   // e.g. "28-24, 7th West"
    stakes?: string; // e.g. "Division rivals — 2 games apart"
  } | null;
}

export interface EventsResponse {
  events: Event[];
  count: number;
}

export interface BookmakerOddsDetail {
  bookmaker: string;
  home_moneyline: number | null;
  away_moneyline: number | null;
  home_probability: number | null;
  away_probability: number | null;
  captured_at: string; // When this bookmaker last updated their odds
  spread?: number | null;
  over_under?: number | null;
  projected_home_score?: number | null;
  projected_away_score?: number | null;
}

export interface LeagueContextData {
  league_slug: string;
  league_name: string;
  columns: { key: string; label: string }[];
  league_page_url: string;
  home_team?: {
    cells: Record<string, number>;
    changes_24h: Record<string, number>;
    record?: string | null;
    conference?: string | null;
    sources_available?: string[];
  };
  away_team?: {
    cells: Record<string, number>;
    changes_24h: Record<string, number>;
    record?: string | null;
    conference?: string | null;
    sources_available?: string[];
  };
}

export interface EventDetailResponse extends Event {
  current_odds?: CurrentOdds;
  /**
   * THE ONE BLEND (standing ruling #1) — the single probability every surface
   * shows for this event. The backend computes it with
   * `compute_aggregate_probability(event)`, the exact same call that produces
   * the Discover card's `current_odds.home_probability` (routes/feed.py:4592)
   * and, on a live game, the pinned right edge of `aggregate_line`. Bind the
   * hero to THIS rather than re-deriving a number per surface: that is what
   * card == hero == chart means in practice (UX-P003).
   */
  hero_probability?: number;
  hero_probability_away?: number;
  /** "blend" when the aggregate exists, "opening" when only the opening line does. */
  hero_probability_source?: "blend" | "opening";
  bookmaker_odds?: BookmakerOddsDetail[];
  ei?: EIData;
  /** @deprecated Use `ei` instead */
  excitement?: EIData;
  /** @deprecated Use `ei` instead */
  pulse?: EIData;
  league_context?: LeagueContextData;
  sport_key?: string;
  box_score_data?: Record<string, unknown>;
}

export interface OddsHistoryPoint {
  timestamp: string;
  home_probability: number | null;
  away_probability: number | null;
  over_under: number | null;
  projected_home_score: number | null;
  projected_away_score: number | null;
  bookmaker: string;
  bookmaker_count?: number; // Number of bookmakers in the aggregate
  // Deduplication fields - for drawing flat lines between data points
  valid_until?: string; // If set, value was constant from timestamp to valid_until
  reading_count?: number; // How many times this value was confirmed
}

export interface BookmakerHistoryPoint {
  timestamp: string;
  home_probability: number | null;
  away_probability: number | null;
  valid_until?: string; // If set, value was constant from timestamp to valid_until
  projected_home_score?: number | null;
  projected_away_score?: number | null;
}

export interface ScoreHistoryPoint {
  timestamp: string;
  home_score: number;
  away_score: number;
}

export interface ESPNHistoryPoint {
  timestamp: string;
  home_probability: number | null;
  away_probability: number | null;
  home_score: number | null;
  away_score: number | null;
  game_clock: string | null;
  period: string | null;
}

export interface WinProbHistoryPoint {
  timestamp: string;
  home_probability: number | null;
  away_probability: number | null;
  draw_probability?: number | null;
  game_state?: Record<string, unknown>;
}

export interface WinProbSourceMeta {
  display_name: string;
  type: "model" | "market";
  color: string;
  dash_pattern?: string | null;
  description?: string;
  methodology?: string;
  attribution_url?: string | null;
  attribution_name?: string | null;
  snapshot_count: number;
}

export interface EventHistoryResponse {
  event_id: number;
  home_team: string;
  away_team: string;
  completed_at?: string;
  history: OddsHistoryPoint[];
  bookmaker_history?: Record<string, BookmakerHistoryPoint[]>;
  score_history?: ScoreHistoryPoint[];
  espn_history?: ESPNHistoryPoint[];
  win_prob_history?: Record<string, WinProbHistoryPoint[]>;
  win_prob_sources?: Record<string, WinProbSourceMeta>;
  scoring_plays?: ScoringPlay[];
  period_markers?: Array<{ timestamp: string; period: string }>;
  aggregate_line?: Array<{ timestamp: string; home_probability: number }>;
  points: number;
  espn_snapshot_count?: number;
  pm_spread_data?: {
    implied_spreads: Record<string, {
      spread: number;
      confidence: number;
      contracts: Array<{ threshold: number; probability: number }>;
    }>;
    implied_totals: Record<string, {
      total: number;
      confidence: number;
      contracts: Array<{ threshold: number; probability: number }>;
    }>;
    projected_final?: {
      home_score: number;
      away_score: number;
      spread_source: string;
      total_source: string;
    };
  };
}

export interface ScoringPlay {
  timestamp: string;
  description: string;
  short_text?: string;
  team: string;
  type: string;
  home_score: number | null;
  away_score: number | null;
  period?: string | null;
  clock?: string | null;
}

/** Data emitted by OddsChart when the user hovers/scrubs */
export interface ActiveChartPoint {
  timestamp: string;
  homeProb: number;
  awayProb: number;
  homeScore?: number | null;
  awayScore?: number | null;
  period?: string | null;
  clock?: string | null;
  /** True when `clock` was carried forward from an earlier snapshot (gap-filled
   * minute) rather than observed at this point — render it as approximate (#925). */
  clockApprox?: boolean;
  scoringPlay?: ScoringPlay | null;
}

export interface SportsResponse {
  sports: Sport[];
}

export interface BookmakerOdds {
  key: string;
  home_moneyline: number | null;
  away_moneyline: number | null;
  home_probability: number | null;
  away_probability: number | null;
  spread: number | null;
  over_under: number | null;
}

export interface LiveOddsEvent {
  event_id: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  bookmakers: BookmakerOdds[];
}

export interface LiveOddsResponse {
  sport: string;
  events: LiveOddsEvent[];
  count: number;
}

// Futures/Outrights types
export interface FuturesOutcome {
  id: number;
  name: string;
  probability: number | null;
  american_odds: number | null;
  rank: number | null;
  rank_change_24h: number | null;
  probability_change_24h: number | null;
  movement: number | null; // alias for probability_change_24h in list view
  opening_probability: number | null;
  opening_american_odds: number | null;
  is_winner: boolean | null;
  last_updated: string | null;
}

export interface FuturesMarket {
  id: number;
  name: string;
  description: string | null;
  sport: string | null;
  sport_name: string | null;
  category: string | null;
  llm_sport_category: string | null;
  status: "open" | "resolved" | "closed";
  source: string | null;
  external_id: string | null;
  mutually_exclusive: boolean;
  commence_time: string | null;
  resolution_date: string | null;
  top_outcomes?: FuturesOutcome[];
  outcomes?: FuturesOutcome[];
  outcome_count: number;
  bookmakers?: string[];
  category_tags?: string[];
  created_at: string | null;
  updated_at: string | null;
  source_count?: number;
  group_id?: string | null;
  canonical_market_key?: string | null;
  hook_description?: string | null;
  image_url?: string | null;
  // B7 (L2-91): up-link mesh — the richer event-concept page + competition hub this
  // market belongs to (null where no mapping exists). Server-derived so links resolve.
  event_concept_key?: string | null;
  hub_slug?: string | null;
  // L2-94: mesh fallbacks below the hub — themed section page (politics/economics/
  // weather/entertainment) then a hub-less sport's sport page (soccer, …).
  category_page?: string | null;
  sport_page_key?: string | null;
}

// ---------------------------------------------------------------------------
// Futures group (cross-source comparison + threshold variants)
// ---------------------------------------------------------------------------

export interface FuturesGroupSourceMarket {
  id: number;
  name: string;
  source: string;
  external_id: string | null;
  status: string;
  outcome_count: number;
  group_type: string | null;
  group_position: number | null;
  canonical_market_key: string | null;
  outcomes: {
    id: number;
    name: string;
    probability: number | null;
    american_odds?: number | null;
    source: string;
  }[];
}

export interface FuturesGroupThresholdOutcome {
  outcome_id: number;
  name: string;
  probability: number | null;
  threshold_value: number;
  threshold_unit: string;
  threshold_direction: string;
  source: string;
}

export interface FuturesGroupResponse {
  group_id: string;
  group_title: string;
  group_type: string | null;
  market_count: number;
  markets: FuturesGroupSourceMarket[];
  threshold_groups: Record<string, FuturesGroupThresholdOutcome[]>;
  sources: string[];
}

export interface FuturesGroupSummary {
  group_id: string;
  group_type: string | null;
  market_count: number;
  representative_name: string;
  representative_id: number;
  sources: string[];
  last_updated: string | null;
}

export interface FuturesGroupsListResponse {
  total: number;
  offset: number;
  limit: number;
  groups: FuturesGroupSummary[];
}

// ── GROUPED FEED TYPES ──

export interface StatPropLine {
  id: number;
  name: string;
  probability: number | null;
  threshold_value: number;
  threshold_direction: string;
  source: string;
}

export interface StatPropFeedItem {
  type: "stat_prop";
  group_key: string;
  player_name: string;
  stat_category: string;
  lines: StatPropLine[];
  market_count: number;
  /** ESPN player ID for headshot lookup */
  espn_player_id?: string;
  /** Sport key for ESPN headshot path */
  sport_key?: string;
  /** Event matchup, e.g., "BOS @ MIA" */
  event_matchup?: string;
  /** Event start time (ISO string) */
  event_time?: string;
}

export interface PlayoffStage {
  id: number;
  name: string;
  stage_name: string;
  stage_order: number;
  probability: number | null;
  source: string;
}

export interface PlayoffProgressionFeedItem {
  type: "playoff_progression";
  group_key: string;
  entity_name: string;
  stages: PlayoffStage[];
  market_count: number;
}

export interface ThresholdPoint {
  id: number;
  name: string;
  probability: number | null;
  threshold_value: number;
  threshold_unit: string;
  threshold_direction: string;
}

export interface ThresholdFeedItem {
  type: "threshold";
  group_key: string;
  title: string;
  points: ThresholdPoint[];
  outcome_count: number;
}

export interface UngroupedMarketFeedItem {
  type: "market";
  market: {
    id: number;
    name: string;
    source: string;
    category: string | null;
    sport: string | null;
    outcomes: {
      id: number;
      name: string;
      probability: number | null;
      american_odds?: number | null;
    }[];
  };
}

export type GroupedFeedItem =
  | StatPropFeedItem
  | PlayoffProgressionFeedItem
  | ThresholdFeedItem
  | UngroupedMarketFeedItem;

export interface GroupedFeedResponse {
  feed: GroupedFeedItem[];
  total_grouped: number;
  total_ungrouped: number;
  group_counts: {
    stat_prop: number;
    playoff_progression: number;
    threshold: number;
  };
}

export interface FuturesMarketsResponse {
  markets: FuturesMarket[];
  count: number;
}

export interface FuturesMarketDetailResponse extends FuturesMarket {
  outcomes: FuturesOutcome[];
  display_category?: string;
}

export interface FuturesHistoryPoint {
  timestamp: string;
  probability: number | null;
  american_odds: number | null;
  bookmaker: string;
}

export interface FuturesOutcomeHistory {
  outcome_id: number;
  name: string;
  history: FuturesHistoryPoint[];
  /** Whether this participant has been eliminated (probability stayed at ~0%) */
  eliminated?: boolean;
  /** ISO timestamp when the participant was first detected as eliminated */
  eliminated_at?: string | null;
}

export interface FuturesHistoryResponse {
  market_id: number;
  market_name: string;
  hours: number;
  /** Actual time window used (may be wider than `hours` if auto-extended for sparse data) */
  actual_hours?: number;
  outcomes: FuturesOutcomeHistory[];
  /** Round/phase boundaries for chart reference lines (from DataGolf round_history) */
  round_boundaries?: { timestamp: string; label: string }[] | null;
  /** Live leaderboard data (from DataGolf metadata) */
  leaderboard?: DataGolfLeaderboardEntry[] | null;
  /** Total data points across all outcomes (for sparse data detection) */
  total_data_points?: number;
  /** True if the backend auto-extended the time window beyond the requested hours */
  auto_extended?: boolean;
  /** True if fewer than 10 total data points (very sparse) */
  sparse?: boolean;
}

/** DataGolf leaderboard entry stored in FuturesMarket.metadata.leaderboard */
export interface DataGolfLeaderboardEntry {
  dg_id: number;
  name: string;
  position: string | null;
  total_score: number | null;
  today_score: number | null;
  thru: string | null;
  current_round: number | null;
}

export interface FuturesMover {
  outcome_id: number;
  name: string;
  market_id: number;
  market_name: string | null;
  current_probability: number | null;
  probability_change_24h: number | null;
  current_american_odds: number | null;
  rank: number | null;
  rank_change_24h: number | null;
}

export interface FuturesMoversResponse {
  movers: FuturesMover[];
  timeframe_hours: number;
}

// Related futures types
export interface RelatedFuture {
  market_id: number;
  market_name: string;
  clean_label?: string;
  display_category?: string;
  merge_group?: string | null;
  playoff_stage?: string | null;
  playoff_stage_type?: string | null;
  stage_order?: number | null;
  market_tier: number | null;
  category: string | null;
  source: string | null;
  outcome_id: number;
  outcome_name: string;
  probability: number | null;
  american_odds: number | null;
  probability_change_24h: number | null;
  opening_probability: number | null;
  rank: number | null;
  relevance_score: number;
  relevance_reason: string;
  last_updated: string | null;
  next_update_expected: string;
  resolution_date: string | null;
  bookmaker_count?: number;
  all_sources?: string[];
  // #1986: set when two sources answering ONE question were merged through the
  // standing blend into this single row. Distinct from bookmaker_count, which
  // counts books inside a single source's own aggregate.
  source_count?: number;
  matched_player?: {
    name: string;
    espn_id?: string;
    headshot?: string;
  };
  team_logo?: string;
}

export interface SeriesMarketOutcome {
  outcome_id: number;
  name: string;
  probability: number | null;
  probability_change_24h: number | null;
}

export interface SeriesMarket {
  market_id: number;
  market_name: string;
  source: string | null;
  status: string | null;
  resolution_date: string | null;
  outcomes: SeriesMarketOutcome[];
}

export interface RelatedFuturesResponse {
  event_id: number;
  home_team: string;
  away_team: string;
  home_team_futures: RelatedFuture[];
  away_team_futures: RelatedFuture[];
  series_markets: SeriesMarket[];
  total_count: number;
  summary: string | null;
  event_status?: string;
  box_score?: Record<string, Record<string, number>> | null;
  league_context?: LeagueContextData | null;
}

// EI (Excitement Index) rankings types
export interface RankedEvent extends Event {
  rank: number;
}

export interface EIRankingsResponse {
  highest: RankedEvent[];
  lowest: RankedEvent[];
  filters: {
    sport: string | null;
    limit: number;
  };
}

/** @deprecated Use EIRankingsResponse instead */
export type PulseRankingsResponse = EIRankingsResponse;

// Search types
export interface SearchPagination {
  total_results: number;
  page: number;
  per_page: number;
  total_pages: number;
  has_prev: boolean;
  has_next: boolean;
}

export interface SearchSportFacet {
  key: string;
  name: string;
  count: number;
}

export interface SearchTeam {
  id: number;
  name: string;
  slug: string | null;
  abbreviation: string | null;
  logo: string | null;
  record: string | null;
  sport_key: string | null;
}

/** #993 L2-41: a backend-composed topical family of related futures markets.
 *  headline/members reuse the formatted-market shape; members is capped at 4
 *  (the rest counted in more_count). */
export interface FuturesFamily {
  family_key: string;
  label: string;
  headline: FuturesMarket;
  members: FuturesMarket[];
  more_count: number;
  member_count: number;
}

// #999 L2-65: an event concept (tournament page) surfaced in search.
export interface SearchEventConcept {
  key: string;
  name: string;
  domain: string;
  market_id: number;
}

export interface SearchResponse {
  results: Event[];
  futures: FuturesMarket[];
  futures_families?: FuturesFamily[]; // #993: composed topical families (additive)
  event_concepts?: SearchEventConcept[]; // #999 L2-65: tournament pages, first-class
  teams: SearchTeam[];
  pagination: SearchPagination;
  sports: SearchSportFacet[];
  query: string;
  did_you_mean?: string;
  /** #2239: the stages `/api/events/search` had to shed against its 20,000 ms
   *  deadline. ADDITIVE — absent means a complete answer. Present means the
   *  empty sections below it are "we stopped early", not "nothing matched", and
   *  the page must not render an absence claim over them
   *  (`lib/searchAnswerState.ts`). The backend has published this since
   *  LAT-P002; nothing modelled it, so nothing read it. */
  degraded?: string[];
}

// Search suggestions (zero-state)
export interface SearchSuggestion {
  query: string;
  label: string;
  type: "event" | "futures";
  event_id?: number;
  market_id?: number;
}

export interface SearchSuggestionsResponse {
  suggestions: SearchSuggestion[];
}

// Onboarding & Preferences types
export interface TeamSearchResult {
  id: number;
  name: string;
  location: string | null;
  sport_key: string | null;
  logo_url: string | null;
  abbreviation: string | null;
}

export interface UserFavoriteItem {
  team_id: number;
  team_name: string;
  relation_type: "follow" | "local" | "alma_mater" | "rival";
  sport_key: string | null;
  logo_url: string | null;
  source: string;
}

export interface UserPreferencesResponse {
  home_location: string | null;
  sport_affinities: Record<string, number>;
  onboarding_completed: boolean;
  favorites: UserFavoriteItem[];
}

export interface OnboardingSubmission {
  home_location: string | null;
  local_teams: { team_id: number }[];
  follow_teams: { team_id: number }[];
  alma_mater_teams: { team_id: number }[];
  rival_teams: { team_id: number }[];
  sport_affinities: Record<string, number>;
  raw_inputs: Record<string, unknown>;
}

// Unified Feed types
export interface FeedEventData {
  id: number;
  external_id: string;
  sport: string | null;
  sport_name: string | null;
  home_team: string;
  away_team: string;
  commence_time: string;
  status: "scheduled" | "live" | "completed" | "closed";
  home_score: number | null;
  away_score: number | null;
  current_odds?: {
    home_probability: number | null;
    away_probability: number | null;
    // UX-P114: the whole percents the card PRINTS for the two probabilities
    // above. The feed derives away as `1 - home`, so a game card draws an exact
    // complement pair — and rounding the two independently printed 101 whenever
    // the blend landed on a half-percent (34 of 414 live/upcoming events,
    // 2026-08-21). Decided once on the server because four surfaces draw this
    // strip. OPTIONAL, and every consumer falls back to `renderedDuelPercents`:
    // a Discover response is cached, so "the backend deployed it" is not "this
    // payload carries it".
    home_rendered_percent?: number | null;
    away_rendered_percent?: number | null;
    bookmaker_count?: number;
    source?: string;  // "aggregate" when computed from non-sportsbook sources
  };
  /**
   * UX-P042 (#1640) — the feed has always sent this; the type simply omitted it,
   * which hid the evidence behind `current_odds` from every client-side check.
   *
   * NOTE THE SHAPE DIFFERENCE, it is load-bearing: `/api/feed` sends BARE NUMBERS
   * (`{"mlb": 0.629}`) while `/api/events/*` and `/search` send decorated objects
   * (`{"polymarket": {"value": 0.5, ...}}`). `lib/probabilityEvidence.ts` reads both.
   */
  win_probability_sources?: Record<string, number | { value?: number | null }>;
  opening_odds?: {
    home_probability: number;
    away_probability: number | null;
    favorite: string | null;
  };
  home_team_data?: TeamData;
  away_team_data?: TeamData;
  highlight?: {
    label: string;
  };
  ei?: {
    score: number;
    label: string;
  };
  /** @deprecated Use `ei` instead */
  pulse?: {
    score: number;
    label: string;
  };
  event_tags?: string[];
  temporal_badge?: "Live" | "Closing Soon" | "New" | null;
  sport_label?: string | null;
  /** #490 — confidence signal (1-3 bars): how much we trust the probability. */
  confidence_tier?: "high" | "moderate" | "low" | null;
  confidence_score?: number | null;
  /** L2-172 — raw calibration-ready signals (not shown; for later calibration). */
  confidence_signals?: ConfidenceSignals | null;
  /** ESPN live game data */
  espn?: {
    game_clock?: string;
    period?: string;
    broadcast?: string;
  };
}

export interface FeedFuturesOutcome {
  id: number;
  name: string;
  probability: number | null;
  rank: number | null;
  movement: number | null;
  /**
   * The whole percent the SERVER rendered for this outcome (#2060/#2088), under
   * the card rule rather than one independent rounding per side. Annotated PER
   * OUTCOME rather than served as a card-level array because `FeedCard` re-orders
   * this list (`leaderFirstSlice`) before printing it — a positional array would
   * be mis-paired on exactly the cards where the stored rank disagrees with the
   * probability order. Optional only for a payload from a pre-#2088 backend.
   */
  rendered_percent?: number | null;
}

export interface FeedFuturesData {
  id: number;
  name: string;
  sport: string | null;
  sport_name: string | null;
  llm_sport_category: string | null;
  source: string | null;
  source_count: number;
  market_tier: number | null;
  status: string;
  resolution_date: string | null;
  top_outcomes: FeedFuturesOutcome[];
  /**
   * Why this card's printed percents do not total 100, or null if they do (#2088).
   *
   * The absence of the key and a served null are DIFFERENT facts and the card
   * treats them differently: absent means "pre-#2088 payload, derive it locally",
   * null means "the server checked and they total 100". Null for any arity other
   * than two, meaning "no claim about a total", never "checked and fine".
   */
  card_sum_reason?: string | null;
  outcome_count: number;
  canonical_market_key: string | null;
  /** Canonical market shape (`FuturesMarket.market_type`) — Queue 310. */
  market_type?: string | null;
  /** Cross-source grouping key; a shape signal for container members. */
  group_id?: string | null;
  image_url?: string | null;
  hook_description?: string | null;
  temporal_badge?: "Live" | "Closing Soon" | "New" | null;
  /** #490 — confidence signal (1-3 bars): how much we trust the probability. */
  confidence_tier?: "high" | "moderate" | "low" | null;
  confidence_score?: number | null;
  /** L2-172 — raw calibration-ready signals (not shown; for later calibration). */
  confidence_signals?: ConfidenceSignals | null;
  // Resolved market metadata (leader ≥97% with interesting journey)
  resolved?: boolean;
  winner?: string;
  winner_opening_probability?: number;
  matched_outcomes?: {
    name: string;
    probability: number | null;
    rank: number | null;
    movement: number | null;
  }[];
  market_tags?: string[];
}

export interface FeedTournamentData {
  key: string;
  name: string;
  slug?: string;
  tour?: string;
  tour_label?: string;
  is_major: boolean;
  venue?: string | null;
  location?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  schedule_status?: string | null;
  commence_time?: string | null;
  resolution_date?: string | null;
  golfers: {
    name: string;
    probability: number;
    rank: number;
    movement_24h: number | null;
  }[];
  market_ids: number[];
  source_count: number;
  // #235 Item 4 / L2-159: calendar-flagged marquee tournament. `marquee_whathit`
  // is true only in the T+36h post-settlement window — the card renders the
  // result-first ("what happened") framing instead of the live/upcoming one.
  is_marquee?: boolean;
  marquee_whathit?: boolean;
}

// Event-concept feed card (#999 B3 / L2-84) — a tournament/card (UFC 329, …)
// surfaced as a rankable candidate that links to /event/{key}.
export interface FeedConceptData {
  key: string;
  name: string;
  domain: string;
  status: string;
  start_date?: string | null;
  is_major: boolean;
  fight_count: number;
  entry_count?: number;
  // #235 Item 4 / L2-159: marquee-pin state. `marquee_whathit` is true only in
  // the T+36h post-settlement window — the card leads with THE RESULT.
  is_marquee?: boolean;
  marquee_whathit?: boolean;
  // Result fields, surfaced result-first when `marquee_whathit` is true and the
  // payload provides them ("where the payload provides it" — graceful/optional so
  // no winner is ever fabricated when the backend hasn't graded a champion yet).
  winner?: string | null;
  result_summary?: string | null;
  // #1882 / #1939: the favourite of an UNSETTLED concept, in the same shape as
  // `FeedTournamentData.golfers[0]`, so the concept card reuses the tournament
  // probability treatment rather than inventing a second one. Absent (not null)
  // when the backend found no usable field — presence IS the "has a leader" test.
  leader?: FeedConceptLeader | null;
}

// #1939: web's half of #1882. The backend has served this since #1882 and iOS has
// rendered it since; this surface had neither the field nor a branch, so its
// classifier dropped every live concept as `empty_concept` rather than ship a
// probability-free tile. Adding the type is the first of the three pieces that
// must land together (type → render → classifier) — see `ConceptCard.tsx` and
// `feedItemSuppressionReason`.
export interface FeedConceptLeader {
  name: string;
  probability: number;
  movement_24h?: number | null;
  // How many competitors the probability was chosen from. A 52% favourite in a
  // two-way fight and a 52% favourite in a 30-rider field are different facts,
  // so the card prints "of N" only when N > 2.
  field_size?: number | null;
}

// Theme/comparison bundle: one feed slot that folds several same-theme markets
// into a single expandable card (geopolitics story clusters, comparison ranges).
export interface FeedBundleData {
  id: string;
  title: string;
  // "comparison" = numeric range heat-strip; "theme" = story/group cluster
  // (geopolitics story_key — slice 1; awards/competition group_id — slice 3).
  kind: "comparison" | "theme";
  comparison_theme?: string | null;
  story_key?: string | null;
  group_id?: string | null;
  item_count: number;
  member_ids: (number | string | null)[];
  // Member feed items, ranked — rendered as the mini-ranked-peek + on expand.
  items: FeedItem[];
  entities?: string[];
}

export interface FeedItem {
  type: "event" | "futures" | "tournament" | "bundle" | "concept";
  score: number;
  reason: string;
  headline: string | null;
  context_summary?: string | null;
  data:
    | FeedEventData
    | FeedFuturesData
    | FeedTournamentData
    | FeedBundleData
    | FeedConceptData;
  // Personalization fields (only present when authenticated + score was adjusted)
  personalized?: boolean;
  base_score?: number;
  multiplier?: number;
  personalization_reasons?: string[];
}

export interface FeedResponse {
  items: FeedItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  // L2-238: bounded cache / build-quality metadata. Optional — an older backend
  // omits them entirely, and `build_quality`/`degraded_reason` are only present
  // when the build was NOT complete. Decode via `lib/discover/feedAvailability`,
  // never by reading `cache.status` inline: `unavailable` is a retryable no-data
  // terminal, not an exhausted feed.
  cache?: {
    status: string;
    ttl_seconds?: number;
    stale_ttl_seconds?: number;
    reason?: string;
  };
  build_quality?: string;
  degraded_reason?: string | null;
  // Present when my_teams_only=true
  my_teams_only?: boolean;
  requires_auth?: boolean;
  matched_teams?: string[];
  // Present when user is authenticated
  personalized?: boolean;
  personalization?: {
    team_count: number;
    sport_affinities_count: number;
    pinned_events: number;
    pinned_futures: number;
  };
}

// Related events on futures detail pages
export interface RelatedEventLinkedTeam {
  side: "home" | "away";
  team_name: string;
  outcome_name: string;
  probability: number | null;
  american_odds: number | null;
  rank: number | null;
}

export interface RelatedEvent {
  event_id: number;
  home_team: string;
  away_team: string;
  commence_time: string;
  status: "scheduled" | "live" | "completed" | "closed";
  sport: string | null;
  home_score: number | null;
  away_score: number | null;
  linked_teams: RelatedEventLinkedTeam[];
}

export interface RelatedEventsResponse {
  market_id: number;
  market_name: string;
  events: RelatedEvent[];
  total_count?: number;
}

// Futures browse types (Search tab)
export interface FuturesBrowseItem {
  id: number;
  name: string;
  llm_sport_category: string | null;
  source: string | null;
  resolution_date: string | null;
  top_outcomes: {
    id: number;
    name: string;
    probability: number | null;
    movement: number | null;
  }[];
  outcome_count: number;
}

export interface FuturesBrowseResponse {
  items: FuturesBrowseItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface FuturesCategoryItem {
  key: string;
  count: number;
}

export interface FuturesCategoriesResponse {
  categories: FuturesCategoryItem[];
  total: number;
}

// Team Futures types (My Stuff → "Your Teams' Odds")
export interface TeamFutureItem {
  outcome_id: number;
  outcome_name: string;
  market_id: number;
  market_name: string;
  market_tier: number | null;
  category: string | null;
  source: string | null;
  probability: number | null;
  probability_change_24h: number | null;
  rank: number | null;
  total_outcomes: number | null;
  resolution_date: string | null;
  /** L2-174 Item 3d — settled-WON grade. True only for the graded winner (Kalshi
   *  settled markets stay status='open', gotcha #33), so the row can carry the
   *  WHAT-HIT/settled label. Null/false = not a confirmed hit → framed as live. */
  is_winner?: boolean | null;
  canonical_market_key?: string | null;
  /** Season/year for display, e.g. "2025-26" or "2026" (BR52). */
  season_year?: string | null;
  matched_team: {
    id: number;
    name: string;
    logo_small: string | null;
    primary_color: string | null;
  };
}

export interface TeamFuturesResponse {
  items: TeamFutureItem[];
  team_ids: number[];
  total_count: number;
}

export interface SharedTeamFuturesResponse {
  items: TeamFutureItem[];
  teams: Array<{ id: number; name: string; logo_small: string | null; primary_color: string | null }>;
  total_count: number;
}

// ============================================================================
// Golf types
// ============================================================================

export interface GolfGolfer {
  name: string;
  probability: number;
  american_odds: number | null;
  opening_probability: number | null;
  movement_24h: number | null;
  rank: number;
  sources: Record<string, number>;
  // Placement probabilities (from DataGolf pre-tournament / non-winner markets)
  top_5_prob?: number | null;
  top_10_prob?: number | null;
  top_20_prob?: number | null;
  top_40_prob?: number | null;
  make_cut_prob?: number | null;
  round_leader_prob?: number | null;
}

export interface GolfH2HMatchup {
  market_id: number;
  source: string;
  golfer_a: { name: string; probability: number };
  golfer_b: { name: string; probability: number };
}

export interface GolfTournament {
  key: string;
  name: string;
  slug?: string;
  is_major: boolean;
  is_tour_event?: boolean;
  is_womens?: boolean;
  tour?: string;
  tour_label?: string;
  commence_time: string | null;
  resolution_date: string | null;
  start_date?: string | null;
  end_date?: string | null;
  venue?: string | null;
  location?: string | null;
  schedule_status?: string | null;
  market_ids: number[];
  market_names?: string[];
  market_sources?: string[];
  golfers: GolfGolfer[];
  prop_markets?: GolfPropMarket[];
}

export interface GolfPropMarket {
  name: string;
  source: string;
  outcomes: { name: string; probability: number }[];
}

export interface GolfMover {
  name: string;
  tournament_key: string;
  tournament_name: string;
  movement_24h: number;
  probability: number;
}

export interface GolfUpcomingEvent {
  id: number;
  name: string;
  commence_time: string | null;
  status: string;
}

export interface GolfCurrentEvent {
  key: string;
  name: string;
  slug?: string;
  resolution_date: string | null;
  start_date: string | null;
  end_date: string | null;
  venue: string | null;
  golfer_count: number;
  leader: string | null;
  leader_probability: number | null;
  top_golfers?: GolfGolfer[];
  market_ids?: number[];
}

export interface GolfResponse {
  tournaments: GolfTournament[];
  biggest_movers: GolfMover[];
  upcoming_events: GolfUpcomingEvent[];
  current_event: GolfCurrentEvent | null;
  pga_schedule: GolfScheduleEvent[] | null;
  total_tournaments: number;
  total_golfers: number;
}

export interface GolfScheduleEvent {
  name: string;
  key: string;
  start_date: string | null;
  end_date: string | null;
  venue: string;
  status: string;
  round: string;
}

// ============================================================================
// Golf Tournament Detail types
// ============================================================================

export interface GolfMarketGroup {
  type: string;
  label: string;
  market_ids: number[];
  market_names?: string[];
}

export interface GolfTournamentDetailResponse {
  tournament: {
    name: string;
    slug: string;
    key: string;
    is_major: boolean;
    is_womens: boolean;
    start_date: string | null;
    end_date: string | null;
    venue: string | null;
    location: string | null;
    schedule_status: string | null;
    commence_time: string | null;
    resolution_date: string | null;
  };
  golfers: GolfGolfer[];
  markets: GolfMarketGroup[];
  related_futures?: {
    market_id: number;
    market_name: string;
    source?: string;
    sources?: { source: string; market_id: number; probability: number | null }[];
    outcomes: {
      name: string;
      probability: number | null;
      american_odds: number | null;
      probability_change_24h: number | null;
    }[];
  }[];
  evolution_market_id: number | null;
  biggest_movers: GolfMover[];
  h2h_matchups?: GolfH2HMatchup[];
  // #951: per-round "Round N Top M Finishers" markets, grouped by round → tier.
  // L2-89: also carries "End of Round N Leader" fields (kind="leader"); `label`
  // is the pre-formatted card title ("Round Leader" / "Top N Finishers").
  round_top_groups?: {
    market_id: number;
    market_name: string;
    round: number | null;
    top_n: number | null;
    kind?: "top" | "leader";
    label?: string;
    source?: string;
    outcomes: { name: string; probability: number | null }[];
  }[];
}

// ============================================================================
// Golf Leaderboard types
// ============================================================================

export interface GolfLeaderboardPlayer {
  position: string;
  name: string;
  score: string;
  total_score_raw: number | null;
  today: string;
  today_raw: number | null;
  thru: string;
  hole: string;
  win_prob: number;
  win_prob_change: number | null;
  position_change: number | null;
  top_5_prob: number | null;
  top_10_prob: number | null;
  top_20_prob: number | null;
  make_cut_prob: number | null;
  current_round: number | null;
}

export interface GolfLeaderboardResponse {
  status: 'live' | 'no_event';
  event_name: string | null;
  current_round: number | null;
  last_updated: string | null;
  tour: string;
  player_count: number;
  has_snapshot: boolean;
  players: GolfLeaderboardPlayer[];
  message?: string;
}

// ============================================================================
// Tournament Progression types
// ============================================================================

export interface ProgressionStage {
  key: string;
  label: string;
  order: number;
  market_id: number | null;
  market_name: string | null;
  /** Derived (#927): championship-grid column where every team is decided (0/1);
   *  rendered de-emphasized as "decided" instead of live bars. */
  resolved?: boolean;
}

export interface ProgressionParticipant {
  name: string;
  team_id: number | null;
  logo_url: string | null;
  primary_color: string | null;
  conference: string | null;
  region: string | null;
  seed: number | null;
  record: string | null;
  probabilities: Record<string, number | null>;
  changes_24h: Record<string, number | null>;
  /** null = live/trading. "missing"/"unavailable" come from the championship
   *  grid register cutover (Q295) and render as an honest empty cell. */
  status: Record<string, "clinched" | "eliminated" | "missing" | "unavailable" | null>;
  /** Per-source probabilities for each stage (optional, from championship grid) */
  sources_data?: Record<string, { source: string; probability: number }[]>;
}

export interface ProgressionResponse {
  sport: string;
  tournament_name: string | null;
  stages: ProgressionStage[];
  participants: ProgressionParticipant[];
}

/** Playoff grid types (league-wide cross-source progression) */
export interface PlayoffGridStageSource {
  source: string;
  probability: number | null;
  market_id: number;
  change_24h: number | null;
}

export interface PlayoffGridStageData {
  sources: PlayoffGridStageSource[];
  probability: number | null;
  change_24h: number | null;
  status: "clinched" | "eliminated" | null;
  market_id: number | null;
}

export interface PlayoffGridTeam {
  name: string;
  team_id: number | null;
  logo_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  conference: string | null;
  division: string | null;
  record: string | null;
  stages: Record<string, PlayoffGridStageData>;
}

export interface PlayoffGridStage {
  key: string;
  label: string;
  order: number;
  market_count: number;
  sources: string[];
  market_ids: number[];
}

export interface PlayoffGridResponse {
  sport: string;
  league: string | null;
  season: string | null;
  stages: PlayoffGridStage[];
  teams: PlayoffGridTeam[];
  sources: string[];
}

/** Championship Grid types (new /api/playoffs/{league_slug} endpoint) */

export interface ChampionshipGridColumn {
  key: string;
  label: string;
  order: number;
  sequential: boolean;
  /** Primary market ID for this column (for evolution chart) */
  market_id?: number | null;
  /** All market IDs for this column (cross-source aggregation) */
  market_ids?: number[];
  /** Derived (#927): true when every team is decided (0/1) for this column, so
   *  it can be de-emphasized instead of rendered as live probability bars. */
  resolved?: boolean;
}

export interface ChampionshipGridCellSource {
  source: string;
  probability: number;
}

export interface ChampionshipGridCell {
  /** Null for every non-live cell: settled and missing cells carry a state,
   *  not a number (Q295 register cutover). */
  merged_probability: number | null;
  sources: ChampionshipGridCellSource[];
  trend_24h: number | null;
  is_minimum_tick?: boolean;
  /** Register-backed cell state — one of the C108 reader states
   *  (live / won / eliminated / missing / unavailable). Absent on
   *  pre-register cached payloads. Normalize via `lib/gridCellState`. */
  state?: string | null;
}

export interface ChampionshipGridTeam {
  name: string;
  short_name: string;
  team_id: number | null;
  logo_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  record: string | null;
  conference: string | null;
  division: string | null;
  region: string | null;
  seed: number | null;
  cells: Record<string, ChampionshipGridCell>;
}

export interface ChampionshipGridMover {
  name: string;
  short_name: string;
  team_id: number | null;
  column: string;
  change_24h: number;
  direction: "up" | "down";
  logo_url: string | null;
  primary_color: string | null;
}

export interface ChampionshipGridTrendChart {
  column: string;
  top: number;
  timeline: { timestamp: string; outcomes: Record<string, number> }[];
  outcomes?: {
    name: string;
    current_probability: number | null;
    primary_color?: string | null;
  }[];
}

export interface ChampionshipGridTournament {
  name: string;
  course: string;
  start_date: string;
  end_date: string;
  location: string;
  country: string;
  status: string;
  current_round: number | null;
}

/** A single golf tour event (returned in events array for multi-tour golf) */
export interface ChampionshipGridEvent {
  tour: string;
  tour_name: string;
  tournament: ChampionshipGridTournament;
  columns: ChampionshipGridColumn[];
  teams: ChampionshipGridTeam[];
  movers: ChampionshipGridMover[];
  trend_chart: ChampionshipGridTrendChart;
  team_count: number;
  field_count: number;
  sources_available: string[];
}

export interface ChampionshipGridResponse {
  league: string;
  name: string;
  season: string | null;
  columns: ChampionshipGridColumn[];
  teams: ChampionshipGridTeam[];
  grouped_teams: Record<string, ChampionshipGridTeam[]> | null;
  movers: ChampionshipGridMover[];
  trend_chart: ChampionshipGridTrendChart;
  team_count: number;
  last_updated: string;
  sources_available: string[];
  /** Championship column market ID for evolution chart */
  championship_market_id?: number | null;
  /** Golf-specific fields */
  tournament?: ChampionshipGridTournament | null;
  field_count?: number;
  source_of_truth?: string;
  /** Multi-tour golf events */
  events?: ChampionshipGridEvent[];
  /** #901: server returns {error:"timeout"} (HTTP 200) when the grid rebuild
   *  exceeds the 25s wait_for — the frontend must treat this as an error, not
   *  an empty/infinite-skeleton state. */
  error?: string;
}

/** Team Progression types (event detail → championship grid row) */
export interface TeamProgressionStage {
  key: string;
  label: string;
  probability: number | null;
  trend_24h: number | null;
  sources: ChampionshipGridCellSource[];
}

export interface TeamProgressionRow {
  name: string;
  short_name: string;
  team_id: number | null;
  logo_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  record: string | null;
  conference: string | null;
  stages: TeamProgressionStage[];
}

export interface TeamProgressionResponse {
  event_id: number;
  league: string | null;
  league_name?: string;
  grid_url?: string;
  columns?: { key: string; label: string; order: number }[];
  home_team: TeamProgressionRow | null;
  away_team: TeamProgressionRow | null;
}

/** Golf schedule types */
export interface GolfScheduleEvent {
  event_id: string;
  name: string;
  course: string | null;
  start_date: string | null;
  end_date: string | null;
  location: string | null;
  country: string | null;
  status: "current" | "upcoming" | "completed" | string;
  current_round: number | null;
  is_current: boolean;
}

export interface GolfScheduleTour {
  tour: string;
  tour_name: string;
  events: GolfScheduleEvent[];
  current_event_id: string | null;
}

export interface GolfScheduleResponse {
  tours: GolfScheduleTour[];
  last_updated: string;
}

/** Probability timeline types (for TournamentChart) */
export interface TimelineOutcomeMeta {
  id: number | null;
  name: string;
  current_probability: number | null;
  rank?: number | null;
  probability_change_24h?: number | null;
  opening_probability?: number | null;
  // Team enrichment
  team_id?: number | null;
  logo_small?: string | null;
  logo_large?: string | null;
  primary_color?: string | null;
  secondary_color?: string | null;
  abbreviation?: string | null;
  record?: string | null;
  location?: string | null;
  espn_id?: string | null;
}

export interface TimelineEntry {
  timestamp: string;
  outcomes: Record<string, number>;
}

export interface ProbabilityTimelineResponse {
  market_id: number;
  market_name: string;
  sport_category?: string | null;
  source?: string | null;
  /** Present when this is a cross-source merged timeline */
  canonical_key?: string | null;
  /** Sources contributing to the merged timeline */
  sources?: string[];
  hours: number;
  top: number;
  bucket_seconds: number;
  timeline: TimelineEntry[];
  outcomes: TimelineOutcomeMeta[];
}

// ============================================================================
// March Madness types
// ============================================================================

export interface MarchMadnessTeam {
  team_name: string;
  probability: number;
  movement_24h: number | null;
  opening_probability: number | null;
  sources: Record<string, number>;
  seed: number | null;
  region: string | null;
  is_eliminated: boolean;
  is_alma_mater: boolean;
  american_odds: string;
}

export interface BracketGame {
  event_id: number;
  round: string | null;
  region: string | null;
  home_team: string;
  away_team: string;
  seed_home: number | null;
  seed_away: number | null;
  score_home: number | null;
  score_away: number | null;
  status: string;
  commence_time: string | null;
  prob_home: number | null;
  prob_away: number | null;
  historical_upset_rate: number | null;
  seed_context: string | null;
  ei: number | null;
}

export interface MarchMadnessBracket {
  regions: string[];
  games: BracketGame[];
}

export interface MarchMadnessUpset {
  event_id: number;
  winner: string;
  loser: string;
  seed_winner: number;
  seed_loser: number;
  score: string;
  winner_pre_game_prob: number | null;
  historical_upset_rate: number | null;
  round: string | null;
}

export interface MarchMadnessCinderella {
  team_name: string;
  seed: number;
  region: string | null;
  title_odds: number;
  games_won: number;
  games_played: number;
}

export interface MarchMadnessMover {
  team_name: string;
  movement_24h: number;
  probability: number;
  seed: number | null;
}

export interface SeedHistoryEntry {
  higher_seed: number;
  lower_seed: number;
  matchups: number;
  higher_wins: number;
  upset_pct: number;
  label: string;
}

export interface NotableUpset {
  year: number;
  seed_winner: number;
  seed_loser: number;
  winner: string;
  loser: string;
  score: string;
  note: string;
}

export interface BracketBusterInsight {
  event_id: number | null;
  winner: string;
  loser: string;
  seed_winner: number | null;
  seed_loser: number | null;
  score: string;
  round: string | null;
  title_odds_before: number;
  title_odds_after: number;
  title_odds_delta: number;
  narrative: string | null;
}

export interface MarchMadnessResponse {
  tournament_type: 'mens' | 'womens';
  tournament_state: 'pre_selection' | 'pre_tournament' | 'in_progress' | 'completed';
  display_name: string;
  selection_sunday: string;
  championship_date: string;
  championship_odds: MarchMadnessTeam[];
  bracket: MarchMadnessBracket | null;
  live_games: BracketGame[];
  upsets: MarchMadnessUpset[];
  cinderellas: MarchMadnessCinderella[];
  biggest_movers: MarchMadnessMover[];
  seed_history: SeedHistoryEntry[];
  notable_upsets: NotableUpset[];
  alma_mater_teams: string[] | null;
  bracket_buster_insights: BracketBusterInsight[];
}

// ============================================================================
// Sport Hierarchy Types (for /sport/ page architecture)
// ============================================================================

export interface SportLeague {
  slug: string;
  name: string;
  sport_keys: string[];
  /**
   * Championship-grid slug, served from `SPORT_HIERARCHY` (UX-P062 / #1743).
   *
   * Register E5: this was a `GRID_SLUG_MAP` hardcoded inside the league page. Grid
   * slugs are register data — a copy in a page is a second register that drifts
   * the first time a grid is renamed. Absent for leagues with no grid.
   */
  grid_slug?: string | null;
}

export interface SportShowcaseEvent {
  name: string;
  type: string;
}

export interface SportHierarchy {
  slug: string;
  name: string;
  leagues: SportLeague[];
  showcase_events: SportShowcaseEvent[];
}

export interface SportHierarchyListResponse {
  sports: SportHierarchy[];
}

// #999 Event Concept Pages (slice 1) — generic envelope for /api/event/{key}.
export interface EventConceptCompetitor {
  name: string;
  probability: number | null;
  // L2-81: authoritative settled winner flag (from resolution). When the event is
  // settled the leaderboard renders the champion as "Won" instead of a stale %.
  won?: boolean | null;
  // L2-66 golf live-mode fields (present only when the tournament is in play):
  position?: string | null;      // leaderboard position, e.g. "T3"
  score_to_par?: number | null;  // total score to par (negative = under)
  today_score?: number | null;
  thru?: string | null;          // holes played this round, "F" = finished
  current_round?: number | null;
  prob_delta_live?: number | null; // L2-69: in-play win-prob move in POINTS ("who's charging")
  // L2-71: compact downsampled probability series (top competitors only), so the
  // leaderboard sparkline + race chart read from the envelope in one fetch.
  outcome_id?: number;
  history?: { timestamp: string; probability: number }[];
  // L2-130: entity linkage — national-team crest/identity for the winner-field
  // leaderboard (soccer World Cup). Present only where a competitor resolves to a
  // known team; absent (honest gap) otherwise.
  team?: EventConceptTeamRef | null;
  // #210: elimination FROM STRUCTURE — `{ out, round }` (settled knockout loss or
  // group non-advancer; price never decides). The legacy `boolean` shape may
  // still arrive from a pre-#210 cached envelope during rollout — consumers
  // (isEliminatedCompetitor) accept both.
  eliminated?: EventConceptElimination | boolean | null;
  [k: string]: unknown;
}

// #210: structure-based elimination envelope. `out` is the authoritative OUT
// signal; `round` is the round the competitor exited in (e.g. "Semifinal",
// "Group Stage"), or null when not derivable.
export interface EventConceptElimination {
  out: boolean;
  round?: string | null;
}

// L2-130: a resolved team-identity ref (crest + canonical name) carried on soccer
// winner-field competitors and matchup sides. All fields optional — a matchup side
// always has a `name`, but a crest only when the team resolves.
export interface EventConceptTeamRef {
  team_id?: number | null;
  name?: string | null;
  slug?: string | null;
  abbreviation?: string | null;
  logo?: string | null;
}

// L2-130: one side of a matchup (soccer duel child). Carries the team identity plus
// this side's blended win probability and (live/settled) score.
export interface EventConceptMatchupSide extends EventConceptTeamRef {
  probability?: number | null;
  score?: number | null;
}

export interface EventConceptSection {
  type: string;
  label: string;
  market_ids?: number[];
  market_names?: string[];
  [k: string]: unknown;
}

export interface EventConceptChild {
  // L2-130: matchup children (soccer games) come from the events table and carry
  // `event_id`, not `market_id` — so `market_id` is optional now.
  market_id?: number;
  market_name?: string;
  name?: string;
  probability?: number | null;
  settled?: boolean;
  // L2-175 Item 2b: the graded winner of a settled child (e.g. a completed Tour de
  // France stage). Emitted by the backend grading pass (#249 Item 4c). When present
  // (or a `settled` outcome carries `won:true`) the stage card renders the winner +
  // "Won" chip instead of two riders at 90%+ stale independent-binary prices.
  graded_winner?: string | null;
  outcomes?: { name: string; probability: number | null; won?: boolean | null }[];
  // L2-84: UFC cards tag children so the page splits fights (matchups rail) from
  // props (dedicated props section). Other domains leave these unset (all → rail).
  // L2-130: soccer bracket games tag `kind:"matchup"` and render as team duels.
  kind?: "fight" | "prop" | "matchup";
  prop_type?: "method" | "rounds" | "distance" | "occurrence" | string;
  // L2-130 matchup (soccer duel) fields — present only when kind === "matchup":
  event_id?: number;
  status?: string; // "live" | "scheduled" | "completed" | "closed"
  commence_time?: string | null;
  home?: EventConceptMatchupSide;
  away?: EventConceptMatchupSide;
  [k: string]: unknown;
}

export interface EventConceptResponse {
  event: {
    key: string;
    // L2-113: pretty, self-resolving URL slug (combat: headliner + date-token; golf:
    // the clean tournament slug). Absent on domains that haven't adopted it yet.
    slug?: string | null;
    domain: string;
    name: string | null;
    status: "upcoming" | "live" | "settled";
    start_date?: string | null;
    end_date?: string | null;
    venue?: string | null;
    location?: string | null;
    is_major?: boolean;
    // L2-66: freshness stamp for live-mode (ISO); null unless live data was fused.
    as_of?: string | null;
    live_mode?: string | null; // e.g. "golf_leaderboard"
  };
  primary: {
    kind: "winner_field" | "co_equal_list";
    label: string;
    competitors: EventConceptCompetitor[];
    evolution_market_id?: number | null;
  };
  sections: EventConceptSection[];
  children: EventConceptChild[];
  // L2-121: the shared PropsSection body (THE SCRIPT → THE DIVERGENCE) for the
  // FIELD hero — one mark per prop, each tracking its current-favorite outcome's
  // opening (`pregame_mark`) → current probability. Golf emits it today (empty
  // when settled or when no usable marks exist); domains that don't emit it fall
  // back to the plain props rendering. Same PropMark contract the DUEL page uses.
  props_script?: {
    key: string | number;
    market_id?: number;
    label: string;
    // Prop archetype (Alex's ruling, The Open 2026): the SHAPE decides the
    // visual — binary → divergence bar, ladder → QuantityGroup rungs, field →
    // named top-N mini-race (never a probability without a name). Absent on
    // domains that haven't adopted it (game props) → legacy row rendering.
    kind?: "binary" | "ladder" | "field" | null;
    // The bare question ("Top American Golfer") — the label may bake in the
    // favorite's name for legacy rendering.
    question?: string | null;
    // Top priced outcomes: field → top 3 by probability, ladder → its rungs,
    // binary → []. Probability-only ({name, probability, opening_probability}).
    outcomes?: {
      name: string | null;
      probability: number | null;
      opening_probability?: number | null;
    }[] | null;
    pregame_mark: number | null;
    current: number | null;
    graded_result?: "hit" | "miss" | "push" | null;
    graded_label?: string | null;
    // The Open 2026 p0 (settled-means-settled): a concluded round's leader prop
    // is graded even while the tournament is live. When true the mark renders as
    // WHAT HIT regardless of the section's overall state — never live odds for a
    // completed round.
    settled?: boolean | null;
    // L2-123 / #199: honest pending label for a family with no real price
    // ("Opens after Round N" / "No market yet") — no fabricated flat, never blank.
    pending_label?: string | null;
  }[];
  movers: { name?: string; change?: number | null; [k: string]: unknown }[];
  // Same-day live feature (2026-07-19): AI-generated live commentary box, present
  // ONLY on The Open Championship page while play is LIVE. Grounded strictly in
  // the leaderboard/win-probability numbers; absent (no box) otherwise or when
  // generation is unavailable — never a broken/empty box.
  commentary?: {
    text: string;
    generated_at?: string | null;
    as_of?: string | null;
  } | null;
  // UX-P065 (#1744 step 2a): the standing competition this page is an EDITION of.
  // Absent when the concept key maps to no register row, or when the register knows
  // the competition but has no edition to name (honest-empty, ruling 027).
  // Dates are absolute and the client computes any countdown — the envelope is
  // mirrored for up to 24h, so a server-side "in 240 days" would be wrong for most
  // of its life.
  competition?: {
    slug: string;
    name: string | null;
    domain?: string | null;
    next_edition?: CompetitionEdition | null;
    last_edition?: CompetitionEdition | null;
  } | null;
}

export interface CompetitionEdition {
  name: string | null;
  slug: string | null;
  // ⚠️ DECLARED, not guaranteed to resolve. Two edition keys in the calendar 404 in
  // production today (event:golf:masters-2027, event:golf:ryder-cup-2027) while their
  // year-less siblings serve. Do NOT turn this into a link without checking it first.
  concept_key: string | null;
  start: string | null; // ISO date (YYYY-MM-DD)
  end: string | null; // ISO date (YYYY-MM-DD)
}

/* ─── Tournament extensions on a standard event page (UX-P152) ───
 *
 * A tournament is a container for ordinary events (Alex, 2026-08-28), so a
 * tennis match renders on `/events/{id}` like any other game and the tournament
 * adds sections to it. This is what `GET /api/tournaments/by-event/{id}`
 * returns.
 *
 * `advancement` deliberately reuses the shape of the league grid's per-team
 * progression, so one component renders both. See
 * `components/event/AdvancementPath`.
 */

export interface TournamentAdvancementStage {
  key: string;
  /** "Quarter-finals" — the destination in words, from the register's column. */
  label: string;
  probability: number | null;
  /** `null` when nothing was measured twice — never a 0 standing in for it. */
  trend_24h: number | null;
  sources: { source: string; probability: number | null }[];
}

export interface TournamentAdvancementRow {
  name: string;
  short_name: string;
  team_id: number | null;
  logo_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  /** The one standing fact a draw holds about a player — "Seed 3". */
  record: string | null;
  conference: string | null;
  stages: TournamentAdvancementStage[];
}

export interface TournamentAdvancement {
  event_id: number;
  league: string | null;
  league_name?: string;
  grid_url?: string | null;
  columns?: { key: string; label: string; order: number }[];
  home_team: TournamentAdvancementRow | null;
  away_team: TournamentAdvancementRow | null;
  /** `event` when the two cards were ordered against the event row, else `register`. */
  side_order?: "event" | "register";
}

export interface EventTournamentResponse {
  event_id: number;
  /** `null` for almost every event on the site — the ordinary answer, not an error. */
  tournament: { slug: string; title: string; url: string } | null;
  /** Named, when there is one: `NOT_IN_REGISTER`, `REGISTER_MOVED`. */
  reason?: string;
  matchup_key?: string;
  round?: string | null;
  draw_label?: string | null;
  advancement?: TournamentAdvancement | null;
  props: MatchProp[];
  props_count: number;
  props_dropped: Record<string, number>;
  decided: boolean;
  /**
   * Where to watch, by region (UX-P154). The route has always returned it —
   * `"broadcasts": reg.broadcasts` — and nothing read it, because Alex's
   * ruling 7 put where-to-watch behind the match row's tap and the row owned
   * the drawer. UX-P154 deleted the drawer (the whole card is the link now), so
   * the ruling's "detail view" is this page and the field is finally consumed.
   */
  broadcasts?: { region: string; channels: string[]; note: string | null }[];
  generated_at?: string;
}
