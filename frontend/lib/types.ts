/**
 * TypeScript types for Bain Luck frontend
 */

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
  spread: number | null;
  over_under: number | null;
  projected_home_score: number | null;
  projected_away_score: number | null;
  bookmaker_count?: number;
  source?: string;
  probability_range?: {
    min: number | null;
    max: number | null;
  };
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

export interface EventDetailResponse extends Event {
  current_odds?: CurrentOdds;
  bookmaker_odds?: BookmakerOddsDetail[];
  ei?: EIData;
  /** @deprecated Use `ei` instead */
  excitement?: EIData;
  /** @deprecated Use `ei` instead */
  pulse?: EIData;
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
  outcomes: FuturesOutcomeHistory[];
  /** Round/phase boundaries for chart reference lines (from DataGolf round_history) */
  round_boundaries?: { timestamp: string; label: string }[] | null;
  /** Live leaderboard data (from DataGolf metadata) */
  leaderboard?: DataGolfLeaderboardEntry[] | null;
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
  matched_player?: {
    name: string;
    espn_id?: string;
    headshot?: string;
  };
  team_logo?: string;
}

export interface RelatedFuturesResponse {
  event_id: number;
  home_team: string;
  away_team: string;
  home_team_futures: RelatedFuture[];
  away_team_futures: RelatedFuture[];
  total_count: number;
  summary: string | null;
  event_status?: string;
  box_score?: Record<string, Record<string, number>> | null;
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

export interface SearchResponse {
  results: Event[];
  futures: FuturesMarket[];
  pagination: SearchPagination;
  sports: SearchSportFacet[];
  query: string;
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

// ============================================================================
// Oscars types
// ============================================================================

export interface OscarsNominee {
  name: string;
  probability: number;
  american_odds: number | null;
  opening_probability: number | null;
  movement_24h: number | null;
  rank: number;
  sources: Record<string, number>;
  is_winner: boolean;
  last_updated: string | null;
}

export interface OscarsCategory {
  key: string;
  name: string;
  ceremony_order: number;
  is_major: boolean;
  market_ids: number[];
  nominees: OscarsNominee[];
}

export interface OscarsTriviaMarket {
  id: number;
  name: string;
  source: string | null;
  top_outcomes: {
    name: string;
    probability: number | null;
    american_odds: number | null;
  }[];
}

export interface OscarsResponse {
  ceremony_date: string;
  ceremony_status: "pre" | "live" | "post";
  categories: OscarsCategory[];
  trivia: OscarsTriviaMarket[];
  total_categories: number;
  biggest_movers: OscarsBiggestMover[];
  film_nominations: OscarsFilmData[];
  llm_previews: Record<string, string>;
}

export interface OscarsFilmData {
  film_name: string;
  nominations: { category_key: string; category_name: string; probability: number; rank: number }[];
  total_nominations: number;
  expected_wins: number;
}

export interface OscarsBiggestMover {
  name: string;
  category_key: string;
  category_name: string;
  movement_24h: number;
  probability: number;
}

// Oscars Pool types
export interface OscarsPoolPick {
  category_key: string;
  nominee_name: string;
  probability_at_pick: number;
  is_confidence_pick: boolean;
  is_correct: boolean | null;
  points_earned: number | null;
}

export interface OscarsPoolMember {
  id: number;
  display_name: string;
  avatar_emoji: string;
  is_current_user: boolean;
  picks: OscarsPoolPick[];
  bonus_picks: OscarsPoolPick[];
  total_points: number;
  correct_count: number;
  picks_submitted: number;
  bonus_submitted: number;
  boldness: number;
  rank?: number;
}

export interface OscarsPoolBonusMarket {
  key: string;
  question: string;
  options: string[];
  points_value: number;
  emoji: string;
}

export interface OscarsPoolResponse {
  pool_name: string;
  pool_code: string;
  ceremony_year: number;
  picks_locked: boolean;
  created_by: string;
  member_count: number;
  current_member_id: number | null;
  members: OscarsPoolMember[];
  leaderboard: OscarsPoolMember[];
  results: Record<string, string>;
  categories_revealed: number;
  bonus_revealed: number;
  total_categories: number;
  bonus_markets: OscarsPoolBonusMarket[];
  avatar_options: string[];
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
    bookmaker_count?: number;
    source?: string;  // "aggregate" when computed from non-sportsbook sources
  };
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
  outcome_count: number;
  canonical_market_key: string | null;
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
}

export interface FeedItem {
  type: "event" | "futures" | "tournament";
  score: number;
  reason: string;
  headline: string | null;
  data: FeedEventData | FeedFuturesData | FeedTournamentData;
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
  canonical_market_key?: string | null;
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
  evolution_market_id: number | null;
  biggest_movers: GolfMover[];
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
  status: Record<string, "clinched" | "eliminated" | null>;
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
}

export interface ChampionshipGridCellSource {
  source: string;
  probability: number;
}

export interface ChampionshipGridCell {
  merged_probability: number;
  sources: ChampionshipGridCellSource[];
  trend_24h: number | null;
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
