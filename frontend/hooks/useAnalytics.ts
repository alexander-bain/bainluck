'use client';

import { useCallback, useRef } from 'react';
import { useAnalyticsContext } from '@/components/Analytics';
import {
  debounce,
  calculateMinutesToStart,
  isCloseGame as checkCloseGame,
  GA_CONFIG,
} from '@/lib/analytics';
import type {
  EventCardClickParams,
  FilterCategoryParams,
  FilterLeagueParams,
  FilterViewModeParams,
  SectionToggleParams,
  ChartTimeRangeParams,
  ChartDataPointHoverParams,
  BookmakerHoverParams,
  ApiErrorParams,
} from '@/lib/analytics';
import type { Event } from '@/lib/types';

// Re-export page tracking hooks
export { usePageTracking } from './usePageTracking';
export { useScrollDepth } from './useScrollDepth';
export { useEngagementTime } from './useEngagementTime';

/**
 * Main analytics hook for tracking user interactions
 *
 * Provides convenient methods for common tracking patterns
 * with proper debouncing and batching.
 */
export function useAnalytics() {
  const context = useAnalyticsContext();
  const { track, recordEvent, recordFilter, recordChart } = context;

  // =========================================================================
  // Event Card Tracking
  // =========================================================================

  /**
   * Track when user clicks on an event card
   */
  const trackEventCardClick = useCallback(
    (
      event: Event,
      sourceSection: EventCardClickParams['source_section'],
      positionIndex: number
    ) => {
      const leagueTier = getLeagueTier(event.sport);

      track('event_card_click', {
        event_id: event.id,
        sport: event.sport || 'unknown',
        league: event.sport || 'unknown',
        league_tier: leagueTier,
        home_team: event.home_team,
        away_team: event.away_team,
        status: event.status,
        home_probability: event.current_odds?.home_probability ?? null,
        away_probability: event.current_odds?.away_probability ?? null,
        is_close_game: checkCloseGame(event.current_odds?.home_probability),
        is_live: event.status === 'live',
        source_section: sourceSection,
        position_index: positionIndex,
        minutes_to_start: calculateMinutesToStart(event.commence_time),
      });

      // Record for session stats
      recordEvent(event.id, event.sport || undefined);
    },
    [track, recordEvent]
  );

  // =========================================================================
  // Filter Tracking
  // =========================================================================

  /**
   * Track category filter changes
   */
  const trackCategoryFilter = useCallback(
    (
      category: string | null,
      action: 'select' | 'deselect',
      previousCategory: string | null,
      eventCount?: number
    ) => {
      const categoryTier = category ? getCategoryTier(category) : 1;

      track('filter_category', {
        action,
        category: category || 'all',
        category_tier: categoryTier,
        previous_category: previousCategory,
        event_count: eventCount,
      });

      recordFilter();
    },
    [track, recordFilter]
  );

  /**
   * Track league filter changes
   */
  const trackLeagueFilter = useCallback(
    (
      league: string | null,
      action: 'select' | 'deselect',
      category: string,
      previousLeague: string | null
    ) => {
      const leagueTier = league ? getLeagueTier(league) : 1;

      track('filter_league', {
        action,
        league: league || 'all',
        league_display_name: league || 'All',
        category,
        league_tier: leagueTier,
        previous_league: previousLeague,
      });

      recordFilter();
    },
    [track, recordFilter]
  );

  /**
   * Track view mode changes
   */
  const trackViewModeChange = useCallback(
    (mode: FilterViewModeParams['mode'], previousMode: FilterViewModeParams['mode']) => {
      track('filter_view_mode', {
        mode,
        previous_mode: previousMode,
      });

      recordFilter();
    },
    [track, recordFilter]
  );

  /**
   * Track more sports toggle
   */
  const trackMoreSportsToggle = useCallback(
    (expanded: boolean, visibleCategories: string[]) => {
      track('filter_more_sports', {
        expanded,
        visible_categories: visibleCategories,
      });
    },
    [track]
  );

  // =========================================================================
  // Section Tracking
  // =========================================================================

  /**
   * Track section expand/collapse
   */
  const trackSectionToggle = useCallback(
    (
      action: 'expand' | 'collapse',
      sectionType: SectionToggleParams['section_type'],
      sectionName: string,
      sportCategory?: string,
      itemCount?: number
    ) => {
      track('section_toggle', {
        action,
        section_type: sectionType,
        section_name: sectionName,
        sport_category: sportCategory,
        item_count: itemCount,
      });
    },
    [track]
  );

  // =========================================================================
  // Chart Tracking
  // =========================================================================

  /**
   * Track chart time range changes
   */
  const trackChartTimeRange = useCallback(
    (
      chartType: ChartTimeRangeParams['chart_type'],
      eventId: number,
      range: ChartTimeRangeParams['range'],
      previousRange: ChartTimeRangeParams['range'],
      hasData: boolean,
      dataPointsCount: number
    ) => {
      track('chart_time_range', {
        chart_type: chartType,
        event_id: eventId,
        range,
        previous_range: previousRange,
        has_data: hasData,
        data_points_count: dataPointsCount,
      });

      recordChart();
    },
    [track, recordChart]
  );

  /**
   * Debounced chart data point hover tracking
   */
  const trackChartDataHoverRef = useRef(
    debounce(
      (params: ChartDataPointHoverParams) => {
        track('chart_data_hover', params);
      },
      GA_CONFIG.DEBOUNCE.HOVER
    )
  );

  const trackChartDataHover = useCallback(
    (params: ChartDataPointHoverParams) => {
      trackChartDataHoverRef.current(params);
    },
    []
  );

  // =========================================================================
  // Bookmaker Tracking
  // =========================================================================

  /**
   * Debounced bookmaker hover tracking
   */
  const trackBookmakerHoverRef = useRef(
    debounce(
      (params: BookmakerHoverParams) => {
        track('bookmaker_hover', params);
      },
      GA_CONFIG.DEBOUNCE.HOVER
    )
  );

  const trackBookmakerHover = useCallback(
    (params: BookmakerHoverParams) => {
      trackBookmakerHoverRef.current(params);
    },
    []
  );

  // =========================================================================
  // Error Tracking
  // =========================================================================

  /**
   * Track API errors
   */
  const trackApiError = useCallback(
    (params: ApiErrorParams) => {
      track('api_error', params);
    },
    [track]
  );

  /**
   * Track retry clicks
   */
  const trackRetryClick = useCallback(
    (errorType: 'api' | 'network' | 'load', context: string, retryCount: number) => {
      track('retry_click', {
        error_type: errorType,
        context,
        retry_count: retryCount,
      });
    },
    [track]
  );

  /**
   * Track stale data views
   */
  const trackStaleDataView = useCallback(
    (eventId: number, staleMinutes: number, isLive: boolean, dataType: 'odds' | 'score' | 'status') => {
      track('stale_data_view', {
        event_id: eventId,
        stale_minutes: staleMinutes,
        is_live: isLive,
        data_type: dataType,
      });
    },
    [track]
  );

  // =========================================================================
  // Navigation Tracking
  // =========================================================================

  /**
   * Track navigation clicks (logo, back, etc.)
   */
  const trackNavigationClick = useCallback(
    (clickType: 'logo' | 'back' | 'footer_link', fromPage: string, toPage: string) => {
      track('navigation_click', {
        click_type: clickType,
        from_page: fromPage,
        to_page: toPage,
      });
    },
    [track]
  );

  return {
    // Raw tracking (from context)
    track,
    recordEvent,
    recordFilter,
    recordChart,

    // Event card
    trackEventCardClick,

    // Filters
    trackCategoryFilter,
    trackLeagueFilter,
    trackViewModeChange,
    trackMoreSportsToggle,

    // Sections
    trackSectionToggle,

    // Charts
    trackChartTimeRange,
    trackChartDataHover,

    // Bookmakers
    trackBookmakerHover,

    // Errors
    trackApiError,
    trackRetryClick,
    trackStaleDataView,

    // Navigation
    trackNavigationClick,
  };
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get tier for a league (1 = major, 2 = mid, 3 = minor)
 */
function getLeagueTier(sport: string | null): 1 | 2 | 3 {
  if (!sport) return 3;

  const majorLeagues = [
    'americanfootball_nfl',
    'basketball_nba',
    'baseball_mlb',
    'icehockey_nhl',
    'soccer_epl',
    'soccer_usa_mls',
  ];

  const midLeagues = [
    'americanfootball_ncaaf',
    'basketball_ncaab',
    'soccer_spain_la_liga',
    'soccer_germany_bundesliga',
    'soccer_italy_serie_a',
    'soccer_france_ligue_one',
  ];

  if (majorLeagues.some((l) => sport.includes(l) || sport === l)) return 1;
  if (midLeagues.some((l) => sport.includes(l) || sport === l)) return 2;
  return 3;
}

/**
 * Get tier for a category
 */
function getCategoryTier(category: string): 1 | 2 | 3 {
  const tier1 = ['football', 'basketball', 'baseball'];
  const tier2 = ['hockey', 'soccer', 'mma', 'boxing'];

  if (tier1.includes(category)) return 1;
  if (tier2.includes(category)) return 2;
  return 3;
}

export default useAnalytics;
