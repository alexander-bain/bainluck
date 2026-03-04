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
  aggregate_line?: Array<{ timestamp: string; home_probability: number }>;
  points: number;
  espn_snapshot_count?: number;
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
  matched_player?: {
    name: string;
    espn_id?: string;
    headshot?: string;
  };
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

export interface FeedItem {
  type: "event" | "futures";
  score: number;
  reason: string;
  headline: string | null;
  data: FeedEventData | FeedFuturesData;
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
  is_major: boolean;
  is_tour_event?: boolean;
  is_womens?: boolean;
  commence_time: string | null;
  resolution_date: string | null;
  start_date?: string | null;
  end_date?: string | null;
  venue?: string | null;
  schedule_status?: string | null;
  market_ids: number[];
  market_names?: string[];
  golfers: GolfGolfer[];
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
  record: string | null;
  probabilities: Record<string, number | null>;
  changes_24h: Record<string, number | null>;
  status: Record<string, "clinched" | "eliminated" | null>;
}

export interface ProgressionResponse {
  sport: string;
  stages: ProgressionStage[];
  participants: ProgressionParticipant[];
}
