/**
 * Google Analytics 4 Event Types for Bain Luck
 *
 * Taxonomy Hierarchy:
 * - Category: High-level grouping (navigation, filter, event_interaction, etc.)
 * - Action: What happened (view, click, change, etc.)
 * - Parameters: Rich context about the event
 *
 * @see https://developers.google.com/analytics/devguides/collection/ga4/reference/events
 */

// ============================================================================
// User Properties (set once per session/user change)
// ============================================================================

export interface UserProperties {
  /** Internal user ID - enables cross-platform tracking */
  user_id?: string;
  /** Current authentication state */
  login_status: 'anonymous' | 'logged_out' | 'logged_in';
  /** Platform identifier */
  platform: 'web' | 'ios' | 'android';
  /** User's preferred sport (derived from behavior) */
  preferred_sport?: string;
  /** Account type if applicable */
  account_type?: 'free' | 'premium';
}

// ============================================================================
// Consent State
// ============================================================================

export type ConsentState = 'granted' | 'denied';

export interface ConsentSettings {
  analytics_storage: ConsentState;
  ad_storage: ConsentState;
  ad_user_data: ConsentState;
  ad_personalization: ConsentState;
}

// ============================================================================
// Navigation Events
// ============================================================================

export interface PageViewParams {
  page_type: 'home' | 'event_detail' | 'sport' | 'error'
    | 'pulse' | 'pulse_hof' | 'about' | 'models'
    | 'futures' | 'futures_detail' | 'market_moves' | 'oscars'
    | 'search' | 'my_stuff' | 'preferences' | 'onboarding'
    | 'share' | 'golf' | 'golf_tournament' | 'category' | 'category_index' | 'admin_taxonomy' | 'admin_matching' | 'explore'
    | 'march_madness' | 'march_madness_picks' | 'playoff_grid' | 'oscars_pool'
    | 'leagues_index' | 'admin_dashboard' | 'admin_eval' | 'admin_discover_quality'
    | 'masters_live'
    | 'sport_hub' | 'sport_league' | 'sport_event'
    | 'wrestlemania'
    | 'weather'
    | 'economics'
    | 'politics'
    | 'team'
    | 'discover'
    | 'entertainment'
    | 'privacy'
    | 'prediction_stats'
    | 'bug_reports';
  page_path: string;
  page_title: string;
  /** For event_detail pages */
  event_id?: number;
  sport?: string;
  league?: string;
  event_status?: 'scheduled' | 'live' | 'completed' | 'closed';
  /** Referrer info */
  referrer?: string;
  /** Internal navigation source */
  navigation_source?: 'direct' | 'internal' | 'external';
}

export interface NavigationClickParams {
  click_type: 'logo' | 'back' | 'footer_link' | 'search_typeahead' | 'nav_tab';
  from_page: string;
  to_page: string;
}

// ============================================================================
// Filter Events
// ============================================================================

export interface FilterCategoryParams {
  action: 'select' | 'deselect';
  category: string;
  category_tier: 1 | 2 | 3;
  previous_category?: string | null;
  /** How many events are in this category */
  event_count?: number;
}

export interface FilterLeagueParams {
  action: 'select' | 'deselect';
  league: string;
  league_display_name: string;
  category: string;
  league_tier: 1 | 2 | 3;
  previous_league?: string | null;
}

export interface FilterViewModeParams {
  mode: 'smart' | 'time' | 'closeness';
  previous_mode: 'smart' | 'time' | 'closeness';
}

export interface FilterMoreSportsParams {
  expanded: boolean;
  visible_categories: string[];
}

// ============================================================================
// Event Interaction Events
// ============================================================================

export interface EventCardClickParams {
  event_id: number;
  sport: string;
  league: string;
  league_tier: 1 | 2 | 3;
  home_team: string;
  away_team: string;
  status: 'scheduled' | 'live' | 'completed' | 'closed';
  home_probability: number | null;
  away_probability: number | null;
  /** Is this a close game (<10% difference)? */
  is_close_game: boolean;
  /** Is this game currently live? */
  is_live: boolean;
  /** Where on the page was this card? */
  source_section: 'featured' | 'feed' | 'sport_category' | 'recently_finished' | 'archived' | 'search_results' | 'pinned' | 'my_stuff';
  /** Position in the list (0-indexed) */
  position_index: number;
  /** Time until game starts (minutes, negative if started) */
  minutes_to_start: number;
}

export interface EventCardImpressionParams {
  /** Batch of event IDs that were viewed */
  event_ids: number[];
  source_section: 'featured' | 'sport_category' | 'recently_finished' | 'archived' | 'pinned';
  /** Viewport info */
  viewport_position: 'above_fold' | 'below_fold';
}

export interface EventDetailViewParams {
  event_id: number;
  sport: string;
  league: string;
  home_team: string;
  away_team: string;
  status: 'scheduled' | 'live' | 'completed' | 'closed';
  home_probability: number | null;
  away_probability: number | null;
  is_close_game: boolean;
  is_live: boolean;
  /** Is the data stale? */
  is_stale: boolean;
  is_needs_review: boolean;
  /** Number of bookmakers with data */
  bookmaker_count: number;
  /** Time until/since game start */
  minutes_to_start: number;
  /** Did user come from card click or direct link? */
  entry_method: 'card_click' | 'direct' | 'back_navigation';
}

export interface BookmakerHoverParams {
  event_id: number;
  bookmaker: string;
  home_probability: number | null;
  away_probability: number | null;
  is_divergent: boolean;
  is_stale: boolean;
}

// ============================================================================
// Section Events
// ============================================================================

export interface SectionToggleParams {
  action: 'expand' | 'collapse';
  section_type: 'sport_category' | 'league' | 'featured' | 'recently_finished' | 'archived' | 'more_sports';
  section_name: string;
  /** For sport categories or leagues */
  sport_category?: string;
  /** Number of items in the section */
  item_count?: number;
}

// ============================================================================
// Chart Events
// ============================================================================

export interface ChartTimeRangeParams {
  chart_type: 'probability_trend' | 'projected_score' | 'actual_score';
  event_id: number;
  range: 'all' | '24h' | '12h' | '6h' | '3h' | '1h' | 'live';
  previous_range: 'all' | '24h' | '12h' | '6h' | '3h' | '1h' | 'live';
  /** Did this range have data? */
  has_data: boolean;
  data_points_count: number;
}

export interface ChartDataPointHoverParams {
  chart_type: 'probability_trend' | 'projected_score' | 'actual_score';
  event_id: number;
  timestamp: string;
  /** The values at this point */
  home_value: number | null;
  away_value: number | null;
  /** Which bookmaker (if showing individual lines) */
  bookmaker?: string;
}

export interface ChartViewParams {
  chart_type: 'probability_trend' | 'projected_score' | 'actual_score';
  event_id: number;
  has_data: boolean;
  data_points_count: number;
  bookmaker_count: number;
  /** Time span of data in hours */
  data_span_hours: number;
}

// ============================================================================
// Engagement Events
// ============================================================================

export interface ScrollDepthParams {
  page_type: 'home' | 'event_detail' | 'sport' | 'error'
    | 'pulse' | 'pulse_hof' | 'about' | 'models'
    | 'futures' | 'futures_detail' | 'market_moves' | 'oscars'
    | 'search' | 'my_stuff' | 'preferences' | 'onboarding'
    | 'share' | 'golf' | 'golf_tournament' | 'category' | 'category_index' | 'admin_taxonomy' | 'admin_matching' | 'explore'
    | 'march_madness' | 'march_madness_picks' | 'playoff_grid' | 'oscars_pool'
    | 'leagues_index' | 'admin_dashboard' | 'admin_eval' | 'admin_discover_quality'
    | 'masters_live'
    | 'sport_hub' | 'sport_league' | 'sport_event'
    | 'wrestlemania'
    | 'weather'
    | 'economics'
    | 'politics'
    | 'team'
    | 'discover'
    | 'entertainment'
    | 'privacy'
    | 'prediction_stats'
    | 'bug_reports';
  depth_percent: 25 | 50 | 75 | 90 | 100;
  /** Page path for context */
  page_path: string;
  /** For event pages */
  event_id?: number;
}

export interface TimeOnPageParams {
  page_type: 'home' | 'event_detail' | 'sport' | 'error'
    | 'pulse' | 'pulse_hof' | 'about' | 'models'
    | 'futures' | 'futures_detail' | 'market_moves' | 'oscars'
    | 'search' | 'my_stuff' | 'preferences' | 'onboarding'
    | 'share' | 'golf' | 'golf_tournament' | 'category' | 'category_index' | 'admin_taxonomy' | 'admin_matching' | 'explore'
    | 'march_madness' | 'march_madness_picks' | 'playoff_grid' | 'oscars_pool'
    | 'leagues_index' | 'admin_dashboard' | 'admin_eval' | 'admin_discover_quality'
    | 'masters_live'
    | 'sport_hub' | 'sport_league' | 'sport_event'
    | 'wrestlemania'
    | 'weather'
    | 'economics'
    | 'politics'
    | 'team'
    | 'discover'
    | 'entertainment'
    | 'privacy'
    | 'prediction_stats'
    | 'bug_reports';
  seconds: number;
  page_path: string;
  event_id?: number;
  /** Was user actively engaged (not tabbed away)? */
  active_time_seconds: number;
}

export interface SessionEngagementParams {
  /** Total events viewed this session */
  events_viewed_count: number;
  /** Unique sports browsed */
  sports_browsed: string[];
  /** Total pages viewed */
  pages_viewed: number;
  /** Session duration in seconds */
  session_duration_seconds: number;
  /** Did user use filters? */
  used_filters: boolean;
  /** Did user view any charts? */
  viewed_charts: boolean;
}

// ============================================================================
// Error Events
// ============================================================================

export interface ApiErrorParams {
  error_type: 'network' | 'api' | 'timeout' | 'parse';
  endpoint: string;
  status_code?: number;
  error_message: string;
  /** Which page/component triggered this */
  context: string;
}

export interface RetryClickParams {
  error_type: 'api' | 'network' | 'load';
  context: string;
  retry_count: number;
}

export interface StaleDataViewParams {
  event_id: number;
  stale_minutes: number;
  is_live: boolean;
  data_type: 'odds' | 'score' | 'status';
}

// ============================================================================
// Account Events (for future auth integration)
// ============================================================================

export interface SignUpParams {
  method: 'google' | 'apple' | 'email';
}

export interface LoginParams {
  method: string;
  is_returning_user?: boolean;
}

export interface LogoutParams {
  session_duration_seconds?: number;
}

export interface FuturesCardClickParams {
  market_id: number;
  category: string;
  position_index: number;
  source_section: string;
}

export interface FuturesDetailViewParams {
  market_id: number;
  category: string;
  source_count: number;
}

// ============================================================================
// Phase 2: Funnel & Retention Events
// ============================================================================

export interface OnboardingStartParams {
  entry_point: string;
}

export interface OnboardingSkipParams {
  last_step_completed: number;
  last_step_name: string;
}

export interface SearchResultClickParams {
  query: string;
  result_type: 'event' | 'futures' | 'team';
  result_id: number | string;
  position: number;
}

export interface ReturnVisitParams {
  days_since_last: number;
  session_number: number;
}

// ============================================================================
// Phase 3: Content Interaction Events
// ============================================================================

export interface GridCellClickParams {
  sport: string;
  team: string;
  column: string;
  probability: number;
}

export interface PlayerPropClickParams {
  event_id: number;
  player_name: string;
  prop_type: string;
  threshold: number;
}

export interface MarketMapInteractParams {
  map_type: 'margin' | 'total';
  segment: 'full' | '1H' | '2H';
  action: 'ladder_click' | 'marker_hover';
}

export interface ShareParams {
  content_type: 'event' | 'futures' | 'grid';
  item_id: number | string;
  method: string;
  item_name?: string;
  source_section?: string;
  url?: string;
}

export interface SharedLinkOpenParams {
  content_type: 'event' | 'futures' | 'grid';
  item_id: number | string;
  source: string;
  medium?: string;
  campaign?: string;
}

export interface PredictionSubmitParams {
  market_id: number;
  guess: 'higher' | 'lower';
  threshold: number;
  actual_probability: number;
  correct: boolean;
  content_type: 'event' | 'futures';
  category: string;
  surface: 'discover' | 'challenge';
}

export interface FeedCardImpressionParams {
  content_type: 'event' | 'futures' | 'grid';
  item_id: number | string;
  category: string;
  position: number;
  score: number;
  item_name?: string;
  headline?: string;
  personalized?: boolean;
  surface: 'discover';
}

export interface FeedCardActionParams {
  action: 'detail_click' | 'dismiss' | 'like' | 'unlike' | 'share' | 'group_expand' | 'context_expand' | 'context_collapse' | 'challenge_start' | 'challenge_complete';
  content_type: 'event' | 'futures' | 'grid';
  item_id: number | string;
  category: string;
  position?: number;
  score?: number;
  item_name?: string;
  headline?: string;
  personalized?: boolean;
  surface: 'discover' | 'discover_guess';
}

export interface FeedRefreshParams {
  trigger: 'manual' | 'auto';
  new_items_count: number;
}

// ============================================================================
// Search Events
// ============================================================================

export interface SearchSubmitParams {
  query: string;
  results_count: number;
  futures_count: number;
}

// ============================================================================
// Onboarding Events
// ============================================================================

export interface OnboardingStepParams {
  step: number;
  step_name: 'location' | 'follow' | 'alma_maters' | 'interests' | 'rivals';
  selections_count: number;
}

export interface OnboardingCompleteParams {
  total_teams: number;
  total_sports: number;
  total_rivals: number;
}

// ============================================================================
// Feed Filter Chip Events
// ============================================================================

export interface FeedFilterChipParams {
  chip_label: string;
  chip_tags: string[];
  action: 'select' | 'deselect';
}

// ============================================================================
// Progression Table Events
// ============================================================================

export interface ProgressionSortParams {
  stage_key: string;
  stage_label: string;
  direction: 'asc' | 'desc';
  sport: string;
  page_type: string;
}

export interface ProgressionStageClickParams {
  stage_key: string;
  stage_label: string;
  market_id: number;
  sport: string;
  page_type: string;
}

// ============================================================================
// Event Map (all events with their parameters)
// ============================================================================

export interface AnalyticsEventMap {
  // Navigation
  page_view: PageViewParams;
  navigation_click: NavigationClickParams;

  // Filters
  filter_category: FilterCategoryParams;
  filter_league: FilterLeagueParams;
  filter_view_mode: FilterViewModeParams;
  filter_more_sports: FilterMoreSportsParams;

  // Event Interactions
  event_card_click: EventCardClickParams;
  event_card_impression: EventCardImpressionParams;
  event_detail_view: EventDetailViewParams;
  bookmaker_hover: BookmakerHoverParams;

  // Sections
  section_toggle: SectionToggleParams;

  // Charts
  chart_time_range: ChartTimeRangeParams;
  chart_data_hover: ChartDataPointHoverParams;
  chart_view: ChartViewParams;

  // Engagement
  scroll_depth: ScrollDepthParams;
  time_on_page: TimeOnPageParams;
  session_engagement: SessionEngagementParams;

  // Errors
  api_error: ApiErrorParams;
  retry_click: RetryClickParams;
  stale_data_view: StaleDataViewParams;

  // Search
  search_submit: SearchSubmitParams;

  // Onboarding
  onboarding_step: OnboardingStepParams;
  onboarding_complete: OnboardingCompleteParams;

  // Feed filter chips
  feed_filter_chip: FeedFilterChipParams;

  // Progression table
  progression_sort: ProgressionSortParams;
  progression_stage_click: ProgressionStageClickParams;

  // Account
  sign_up: SignUpParams;
  login: LoginParams;
  logout: LogoutParams;

  // Futures
  futures_card_click: FuturesCardClickParams;
  futures_detail_view: FuturesDetailViewParams;

  // Funnel & Retention (Phase 2)
  onboarding_start: OnboardingStartParams;
  onboarding_skip: OnboardingSkipParams;
  search_result_click: SearchResultClickParams;
  return_visit: ReturnVisitParams;

  // Content Interaction (Phase 3)
  grid_cell_click: GridCellClickParams;
  player_prop_click: PlayerPropClickParams;
  market_map_interact: MarketMapInteractParams;
  share: ShareParams;
  shared_link_open: SharedLinkOpenParams;
  prediction_submit: PredictionSubmitParams;
  feed_card_impression: FeedCardImpressionParams;
  feed_card_action: FeedCardActionParams;
  feed_refresh: FeedRefreshParams;
}

export type AnalyticsEventName = keyof AnalyticsEventMap;
