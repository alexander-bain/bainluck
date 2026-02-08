/**
 * TypeScript types for OddsTracker frontend
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

export interface GEIComponents {
  win_probability_volatility: number;
  late_game_uncertainty: number;
  expectation_deviation: number;
  comeback_factor: number;
  overtime_bonus: number;
}

export interface ExcitementData {
  raw_gei: number;
  percentile_global: number | null;
  percentile_sport: number | null;
  label: string;
  emoji: string;
  components?: GEIComponents;
}

export interface PulseComponents {
  heart_rate: number;
  amplitude: number;
  arrhythmia: number;
  vitals: number;
  time_weight: number;
  lead_changes: number;
}

export interface PulseData {
  score: number;           // 1-100 (percentile when available, raw otherwise)
  raw_score?: number;      // 1-100 raw score before percentile mapping
  status: string;          // 'racing' | 'strong' | 'steady' | 'weak' | 'flatline'
  label: string;           // 'Must-Watch', 'Exciting', etc.
  emoji: string;           // 🫀 💓 💗 🩺 📉
  components?: PulseComponents;
}

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
  excitement?: ExcitementData;
  pulse?: PulseData;
  espn?: ESPNData;
  home_team_data?: TeamData;
  away_team_data?: TeamData;
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
  excitement?: ExcitementData;
  pulse?: PulseData;
}

export interface OddsHistoryPoint {
  timestamp: string;
  home_probability: number | null;
  away_probability: number | null;
  over_under: number | null;
  projected_home_score: number | null;
  projected_away_score: number | null;
  bookmaker: string;
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
  points: number;
  espn_snapshot_count?: number;
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
  created_at: string | null;
  updated_at: string | null;
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
}

export interface FuturesHistoryResponse {
  market_id: number;
  market_name: string;
  hours: number;
  outcomes: FuturesOutcomeHistory[];
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

// Pulse rankings types
export interface RankedEvent extends Event {
  rank: number;
}

export interface PulseRankingsResponse {
  highest: RankedEvent[];
  lowest: RankedEvent[];
  filters: {
    sport: string | null;
    limit: number;
  };
}

// Player prop types
export interface PropBet {
  player: string;
  type: string;
  market_key: string;
  line: number | null;
  over_probability?: number;
  under_probability?: number;
  over_odds?: number;
  under_odds?: number;
  probability?: number;       // For yes/no props (anytime TD, first TD)
  american_odds?: number;     // For yes/no props
  bookmaker_count?: number;
}

export interface PropCategory {
  category: string;
  props: PropBet[];
}

export interface EventPropsResponse {
  event_id: number;
  home_team: string;
  away_team: string;
  categories: PropCategory[];
  total_props: number;
}

// Super Bowl commercial types
export interface Commercial {
  rank: number;
  video_id: string;
  title: string;
  brand: string;
  thumbnail: string;
  view_count: number;
  view_count_display: string;
  like_count: number;
  published_at: string;
  youtube_url: string;
}

export interface CommercialLeaderboardResponse {
  query: string;
  total: number;
  commercials: Commercial[];
}

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
