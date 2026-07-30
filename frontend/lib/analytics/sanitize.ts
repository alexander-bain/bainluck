/**
 * Central event sanitation boundary (L2-190, Item 3).
 *
 * ONE typed choke point that every analytics event passes through before it
 * reaches `gtag`. It exists so that no matter what a caller hands `trackEvent`,
 * the payload that leaves the browser cannot carry personally-identifying or
 * free-form text.
 *
 * What it enforces:
 *  1. **Unknown event names are rejected** — an event whose name is not in the
 *     registered taxonomy (`KNOWN_EVENT_NAMES`) is dropped entirely.
 *  2. **Unknown parameters are rejected** — only keys in the global
 *     `ALLOWED_PARAM_KEYS` union survive; anything else (including a key named
 *     `user_id`, `email`, `token`, …) is stripped.
 *  3. **Raw search queries become bounded metadata** — a `query` param is
 *     replaced with a non-reversible `query_hash` (for funnel joinability),
 *     `query_length`, and `query_word_count`. The raw text never leaves.
 *  4. **Free-form / PII-shaped values are removed** — `referrer` and `url`
 *     params are dropped; every retained string value is run through a scrubber
 *     that redacts emails, phone-like runs, URLs, and token-shaped strings, and
 *     truncates to a bounded length.
 *  5. **Performance events are strict** — `feed_telemetry` and `web_vital` are
 *     restricted to their exact declared keys (no session/user/timestamp
 *     enrichment leaks into them).
 *
 * Everything here is pure and best-effort: a malformed input degrades to a
 * dropped key, never a throw.
 */

import type { AnalyticsEventName } from './types';

// ============================================================================
// Event-name allowlist
// ============================================================================

/**
 * Every registered event name. Mirrors the keys of `AnalyticsEventMap`
 * (`types.ts`). Adding a new event means adding it here too — the
 * `analyticsSanitize` test guards that the two stay in sync for a representative
 * set, and an unregistered name is silently dropped at runtime.
 */
export const KNOWN_EVENT_NAMES: ReadonlySet<AnalyticsEventName> = new Set<AnalyticsEventName>([
  // Navigation
  'page_view',
  'navigation_click',
  // Filters
  'filter_category',
  'filter_league',
  'filter_view_mode',
  'filter_more_sports',
  // Event interactions
  'event_card_click',
  'event_card_impression',
  'event_detail_view',
  'bookmaker_hover',
  // Sections
  'section_toggle',
  // Charts
  'chart_time_range',
  'chart_data_hover',
  'chart_view',
  // Engagement
  'scroll_depth',
  'time_on_page',
  'session_engagement',
  // Errors
  'api_error',
  'retry_click',
  'stale_data_view',
  // Search
  'search_submit',
  'answer_visible_typeahead',
  // Onboarding
  'onboarding_step',
  'onboarding_complete',
  // Feed filter chips
  'feed_filter_chip',
  // Progression table
  'progression_sort',
  'progression_stage_click',
  // Account
  'sign_up',
  'login',
  'logout',
  // Futures
  'futures_card_click',
  'concept_card_click',
  'futures_detail_view',
  // Funnel & retention
  'onboarding_start',
  'onboarding_skip',
  'search_result_click',
  'return_visit',
  // Content interaction
  'grid_cell_click',
  'player_prop_click',
  'market_map_interact',
  'share',
  'shared_link_open',
  'prediction_submit',
  'feed_card_impression',
  'feed_card_action',
  'feed_refresh',
  'feed_card_suppressed',
  'theme_bundle_expand',
  // Funnel events
  'streak_continued',
  'challenge_completed',
  'search_opened',
  'destination_engaged',
  // Cockpit
  'eval_verdict',
  'eval_promote_toggle',
  // Admin taxonomy
  'team_cluster_verdict',
  // Friend challenge
  'friend_challenge_view',
  'friend_challenge_accept',
  'friend_challenge_share',
  // Performance / observability (L2-189)
  'feed_telemetry',
  'web_vital',
]);

// ============================================================================
// Parameter allowlist
// ============================================================================

/**
 * Common enrichment keys `trackEvent` attaches to (non-performance) events.
 * `session_id` here is a CLIENT session-start timestamp (a coarse grouping
 * marker), never the server/anon session id or a user id — those never reach an
 * event. Performance events strip even these (see PERF_EVENT_KEYS).
 */
const ENRICHMENT_KEYS = ['event_timestamp', 'session_id', 'platform'] as const;

/** Derived, bounded replacements for a raw `query`. */
const QUERY_DERIVED_KEYS = ['query_hash', 'query_length', 'query_word_count'] as const;

/**
 * The union of every parameter key the taxonomy legitimately emits (from the
 * interfaces in `types.ts`), plus enrichment and the derived query keys.
 * Anything outside this set is dropped. `user_id`, `email`, raw `query`,
 * `referrer`, and `url` are intentionally ABSENT so they can never survive.
 */
export const ALLOWED_PARAM_KEYS: ReadonlySet<string> = new Set<string>([
  ...ENRICHMENT_KEYS,
  ...QUERY_DERIVED_KEYS,
  // Navigation / page
  'page_type',
  'page_path',
  'page_title',
  'event_id',
  'sport',
  'league',
  'event_status',
  'navigation_source',
  'click_type',
  'from_page',
  'to_page',
  // Filters
  'action',
  'category',
  'category_tier',
  'previous_category',
  'event_count',
  'league_display_name',
  'league_tier',
  'previous_league',
  'mode',
  'previous_mode',
  'expanded',
  'visible_categories',
  // Event cards / detail
  'event_ids',
  'home_team',
  'away_team',
  'status',
  'home_probability',
  'away_probability',
  'is_close_game',
  'is_live',
  'source_section',
  'position_index',
  'minutes_to_start',
  'viewport_position',
  'is_stale',
  'is_needs_review',
  'bookmaker_count',
  'entry_method',
  'bookmaker',
  'is_divergent',
  // Sections
  'section_type',
  'section_name',
  'sport_category',
  'item_count',
  // Empty-envelope suppression (L2-215 Item 1 / #1486) — identity-free
  'card_type',
  'suppression_reason',
  'count',
  // Charts
  'chart_type',
  'range',
  'previous_range',
  'has_data',
  'data_points_count',
  'timestamp',
  'home_value',
  'away_value',
  'data_span_hours',
  // Engagement
  'depth_percent',
  'seconds',
  'active_time_seconds',
  'events_viewed_count',
  'sports_browsed',
  'pages_viewed',
  'session_duration_seconds',
  'used_filters',
  'viewed_charts',
  // Errors
  'error_type',
  'endpoint',
  'status_code',
  'error_message',
  'context',
  'retry_count',
  'stale_minutes',
  'data_type',
  // Search / funnel
  'results_count',
  'futures_count',
  'result_type',
  'result_id',
  'position',
  'answers_shown',
  'has_query',
  'rank',
  'dwell_ms',
  // Onboarding
  'entry_point',
  'last_step_completed',
  'last_step_name',
  'step',
  'step_name',
  'selections_count',
  'total_teams',
  'total_sports',
  'total_rivals',
  // Feed filter chips
  'chip_label',
  'chip_tags',
  // Progression
  'stage_key',
  'stage_label',
  'direction',
  'market_id',
  // Account
  'method',
  'is_returning_user',
  // Futures
  'source_count',
  // Return visit
  'days_since_last',
  'session_number',
  // Content interaction
  'team',
  'column',
  'probability',
  'player_name',
  'prop_type',
  'threshold',
  'map_type',
  'segment',
  'content_type',
  'item_id',
  'item_name',
  'headline',
  'personalized',
  'source',
  'medium',
  'campaign',
  'guess',
  'actual_probability',
  'correct',
  'score',
  'trigger',
  'new_items_count',
  'story_key',
  'member_count',
  'enabled',
  'cluster_key',
  'followed_recommendation',
  'challenge_code',
  'accepted',
  // Funnel dimensions
  'shape',
  'archetype_state',
  'concept_slug',
  'card_angle',
  'surface',
  'streak_length',
  'challenge_type',
  'total_questions',
  'streak',
  'challenge_id',
  'verdict',
  'decision_id',
  'proposal',
  'applied',
  // Performance / observability
  'cohort',
  'cache_status',
  'backend_elapsed_ms',
  'duration_ms',
  'metric_name',
  'metric_value',
  'rating',
  'navigation_type',
]);

/**
 * Performance events get an EXACT key allowlist — no enrichment (session id,
 * timestamp, platform) and no other field may ride along. This is what
 * guarantees "no user/session/token/market payload enters performance events".
 */
const PERF_EVENT_KEYS: Record<string, ReadonlySet<string>> = {
  feed_telemetry: new Set([
    'endpoint',
    'cohort',
    'cache_status',
    'backend_elapsed_ms',
    'duration_ms',
  ]),
  web_vital: new Set([
    'metric_name',
    'metric_value',
    'rating',
    'navigation_type',
    'page_path',
  ]),
};

/** Keys that are ALWAYS dropped even though a raw form might be handed in. */
const HARD_DROP_KEYS: ReadonlySet<string> = new Set([
  'query', // transformed to query_hash/length/word_count instead
  'referrer', // full referrer URL — navigation_source already captures intent
  'url', // may embed query strings / ids
  'user_id',
  'userId',
  'email',
  'token',
  'authorization',
  'cookie',
  'password',
  'secret',
]);

// ============================================================================
// Value scrubbing
// ============================================================================

const MAX_STRING_LEN = 120;

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const URL_RE = /\b(?:https?:\/\/|www\.)\S+/gi;
// A JWT, or any long opaque token-shaped run (>=24 url-safe chars, no spaces).
const TOKEN_RE = /\b(?:eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|[A-Za-z0-9_-]{24,})\b/g;
// A phone-like run: 8+ digits possibly split by spaces/dashes/parens/dots.
const PHONE_RE = /(?:\+?\d[\d\s().-]{7,}\d)/g;

/**
 * Redact PII-shaped substrings from a free-form string and bound its length.
 * Order matters: emails and URLs before the token/phone catch-alls.
 */
export function scrubString(value: string): string {
  let out = value
    .replace(EMAIL_RE, '[redacted-email]')
    .replace(URL_RE, '[redacted-url]')
    .replace(TOKEN_RE, '[redacted-token]')
    .replace(PHONE_RE, '[redacted-phone]');
  if (out.length > MAX_STRING_LEN) {
    out = out.slice(0, MAX_STRING_LEN);
  }
  return out;
}

/** Recursively scrub a value: strings redacted+truncated, arrays element-wise. */
function scrubValue(value: unknown): unknown {
  if (typeof value === 'string') return scrubString(value);
  if (Array.isArray(value)) {
    return value.map((v) => (typeof v === 'string' ? scrubString(v) : v));
  }
  return value;
}

// ============================================================================
// Query → bounded metadata
// ============================================================================

/**
 * Stable, non-reversible 32-bit hash (FNV-1a) of the normalized query, base36.
 * Lets the same query be joined across search_submit → result_click →
 * destination_engaged WITHOUT ever sending the raw text. Not cryptographic —
 * it exists to bucket/join, not to secure.
 */
export function hashQuery(raw: string): string {
  const norm = raw.trim().toLowerCase();
  let h = 0x811c9dc5;
  for (let i = 0; i < norm.length; i++) {
    h ^= norm.charCodeAt(i);
    // 32-bit FNV prime multiply
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}

/** Bounded, non-PII replacement fields for a raw `query`. */
export function queryMetadata(raw: string): {
  query_hash: string;
  query_length: number;
  query_word_count: number;
} {
  const trimmed = raw.trim();
  const words = trimmed.length === 0 ? 0 : trimmed.split(/\s+/).length;
  return {
    query_hash: hashQuery(raw),
    // Bound the length so an outlier can't itself become a fingerprint.
    query_length: Math.min(trimmed.length, 200),
    query_word_count: Math.min(words, 50),
  };
}

// ============================================================================
// The boundary
// ============================================================================

export interface SanitizedEvent {
  name: string;
  params: Record<string, unknown>;
}

/**
 * Sanitize an event just before it is handed to `gtag`. Returns `null` when the
 * event name is not registered (the event is dropped). Otherwise returns the
 * event with a param object containing ONLY allowlisted, scrubbed fields.
 */
export function sanitizeEvent(
  eventName: string,
  params: Record<string, unknown> | undefined | null,
): SanitizedEvent | null {
  if (!KNOWN_EVENT_NAMES.has(eventName as AnalyticsEventName)) {
    return null;
  }

  const input = params && typeof params === 'object' ? params : {};
  const out: Record<string, unknown> = {};

  // Performance events: exact-key allowlist, no enrichment, no transforms.
  const perfKeys = PERF_EVENT_KEYS[eventName];
  if (perfKeys) {
    for (const [key, value] of Object.entries(input)) {
      if (perfKeys.has(key) && value !== undefined) {
        out[key] = scrubValue(value);
      }
    }
    return { name: eventName, params: out };
  }

  // Raw query → bounded metadata (joinable, non-PII).
  if (typeof input.query === 'string') {
    Object.assign(out, queryMetadata(input.query));
  }

  for (const [key, value] of Object.entries(input)) {
    if (value === undefined) continue;
    if (HARD_DROP_KEYS.has(key)) continue; // includes raw `query`, handled above
    if (!ALLOWED_PARAM_KEYS.has(key)) continue; // reject unknown params
    out[key] = scrubValue(value);
  }

  return { name: eventName, params: out };
}
