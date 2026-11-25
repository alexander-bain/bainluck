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

import { GA_CONFIG, getStoredConsent } from './config';
import type { AnalyticsEventName } from './types';

// ============================================================================
// Event-name allowlist
// ============================================================================

/**
 * Every registered event name, as a Record keyed by `AnalyticsEventName`.
 *
 * The Record shape is the point: TypeScript REQUIRES every key of
 * `AnalyticsEventMap` to appear here, so adding an event to the taxonomy
 * without registering it fails `tsc` instead of failing silently in production.
 *
 * That guard exists because the silent mode is genuinely invisible. L2-217
 * shipped `my_stuff_load` into `AnalyticsEventMap` and emitted it through
 * `trackEvent`, but never added it to this list — so every My Stuff latency
 * packet was dropped here, at the last boundary before `gtag`, for the entire
 * time the surface was live. Its own suite could not catch it: that test mocks
 * `@/lib/analytics` wholesale, so the sanitizer never ran (L2-220 Item 1).
 */
const EVENT_NAME_REGISTRY: Record<AnalyticsEventName, true> = {
  page_view: true,
  navigation_click: true,
  filter_category: true,
  filter_league: true,
  filter_view_mode: true,
  filter_more_sports: true,
  event_card_click: true,
  event_card_impression: true,
  event_detail_view: true,
  bookmaker_hover: true,
  section_toggle: true,
  chart_time_range: true,
  chart_data_hover: true,
  chart_view: true,
  scroll_depth: true,
  time_on_page: true,
  session_engagement: true,
  api_error: true,
  retry_click: true,
  stale_data_view: true,
  search_submit: true,
  answer_visible_typeahead: true,
  onboarding_step: true,
  onboarding_complete: true,
  feed_filter_chip: true,
  progression_sort: true,
  progression_stage_click: true,
  sign_up: true,
  login: true,
  logout: true,
  futures_card_click: true,
  concept_card_click: true,
  futures_detail_view: true,
  onboarding_start: true,
  onboarding_skip: true,
  search_result_click: true,
  return_visit: true,
  grid_cell_click: true,
  player_prop_click: true,
  market_map_interact: true,
  share: true,
  share_scorecard: true,
  shared_link_open: true,
  prediction_submit: true,
  feed_card_impression: true,
  feed_card_action: true,
  feed_refresh: true,
  feed_card_suppressed: true,
  theme_bundle_expand: true,
  streak_continued: true,
  challenge_completed: true,
  search_opened: true,
  destination_engaged: true,
  eval_verdict: true,
  eval_promote_toggle: true,
  team_cluster_verdict: true,
  friend_challenge_view: true,
  friend_challenge_accept: true,
  friend_challenge_share: true,
  feed_telemetry: true,
  web_vital: true,
  my_stuff_load: true,
  screen_timing: true,
  session_open: true,
  feed_exit: true,
  search_no_results: true,
};

/**
 * Every registered event name. Derived from `EVENT_NAME_REGISTRY` so the set
 * and the taxonomy cannot drift; an unregistered name is dropped at runtime.
 */
export const KNOWN_EVENT_NAMES: ReadonlySet<AnalyticsEventName> = new Set<AnalyticsEventName>(
  Object.keys(EVENT_NAME_REGISTRY) as AnalyticsEventName[],
);

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
  // Discover Stats scorecard share (L2-220) — aggregate, identity-free.
  'accuracy_percent',
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
  // ==========================================================================
  // Launch instrumentation (Queue 310).
  //
  // ⚠️ READ THIS BEFORE ADDING AN EVENT ANYWHERE. The event-NAME registry above
  // is type-derived (`Record<AnalyticsEventName, true>`), so a name that is in
  // the taxonomy but not registered fails `tsc`. THIS SET IS NOT. It is a plain
  // hand-maintained `Set<string>` with no link to `types.ts`, so a parameter
  // that is declared, emitted, and never added here is dropped silently right
  // here — the exact L2-217 failure mode, one level down, still unguarded.
  // Every new param needs a line below AND a fixture asserting it survives.
  // ==========================================================================
  // session_open (`session_number` is already allowlisted above, under return-visit)
  'is_first_session',
  'first_seen_date',
  // feed_exit (`dwell_ms` is already allowlisted above, under search/funnel).
  // `max_scroll_depth` is a free integer and distinct from `depth_percent`,
  // which is the scroll-MILESTONE enum (25/50/75/90/100).
  'last_position',
  'visible_count',
  'max_scroll_depth',
  'terminal_state',
  // feed_card_action / feed_card_impression — canonical market shape.
  'market_type',
  // search_no_results carries only `query` (→ query_hash, above) + results_count.
]);

/**
 * Events with an EXACT key allowlist — nothing outside the listed keys may ride
 * along, including keys that are globally allowlisted for other events.
 *
 * The global `ALLOWED_PARAM_KEYS` is a UNION across the whole taxonomy, so it
 * can only answer "is this key legitimate SOMEWHERE". For an event whose
 * contract is "carries no content", that is not enough: `item_name`,
 * `headline` and `category` are all perfectly legal keys elsewhere, so a caller
 * adding one to a content-free event would sail through. This map is how a
 * per-event contract is actually enforced rather than merely documented.
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
  // My Stuff first-card latency packet (L2-217 / C88). Treated as a perf event
  // rather than widening the global param allowlist by ~10 latency-only keys:
  // the C88 privacy contract already says a packet carries ONLY durations,
  // counts, a coarse cache label, a build tag and a bounded outcome class, so
  // the exact-key form is both narrower and a closer match to the contract.
  my_stuff_load: new Set([
    'stage',
    'auth_ready_ms',
    'network_ms',
    'backend_elapsed_ms',
    'decode_ms',
    'required_data_ready_ms',
    'first_render_ms',
    'cache_outcome',
    'cache_age_seconds',
    'item_count',
    'app_build',
    'surface',
    'outcome_class',
  ]),
  // latency/121 — the felt number. Exact-key form for the same reason
  // `my_stuff_load` uses one: the contract is "durations, counts and bounded
  // enums, nothing else", and the global allowlist can only say a key is legal
  // SOMEWHERE. `surface` and `card_count` are both legal elsewhere and carry
  // content there; here they may not.
  //
  // ⚠️ The enrichment keys are deliberately NOT included. This packet must be
  // poolable across web and native into one p50/p95 table, and a web-only
  // `session_id`/`platform` pair would make the two halves differently shaped.
  // `device_class` carries the distinction that actually matters.
  screen_timing: new Set([
    'surface',
    'entry',
    'shell_ms',
    'first_card_ms',
    'fold_ms',
    'interactive_ms',
    'card_count',
    'device_class',
    'network_class',
    'app_build',
    'outcome_class',
  ]),
  // Queue 310 — `feed_exit` is declared content-free BY CONSTRUCTION, so it is
  // enforced here rather than trusted to callers. Positions, counts, a
  // duration, one enum. No item id, market text, headline or category, ever.
  //
  // Unlike the perf events above this one KEEPS the enrichment keys: the
  // session-death packet is only useful joined to the session that died, and
  // `session_id` here is the coarse client session-start marker, never a
  // server/anon session id or a user id.
  feed_exit: new Set([
    ...ENRICHMENT_KEYS,
    'last_position',
    'visible_count',
    'max_scroll_depth',
    'dwell_ms',
    'terminal_state',
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
// A phone-SHAPED run: digits split by spaces/dashes/parens/dots. Shape alone is
// not enough to redact — see MIN_PHONE_DIGITS.
const PHONE_RE = /(?:\+?\d[\d\s().-]{7,}\d)/g;
/**
 * How many REAL digits a phone-shaped run needs before it is redacted.
 *
 * Shape-only matching destroys legitimate values. The build tag "1.4.2 (231)"
 * is phone-shaped but carries just 6 digits, and was being rewritten to
 * "[redacted-phone])" — which would have silently wrecked build attribution on
 * every My Stuff latency packet. That defect could not be seen until L2-220
 * registered `my_stuff_load` in the name allowlist, because until then the
 * event was dropped before it ever reached the scrubber.
 *
 * This is the same >=7-digit rule L2-219 applied to the native rail after the
 * identical trap bit there (`AnalyticsPrivacy`), so the two rails now agree.
 */
const MIN_PHONE_DIGITS = 7;

/**
 * An ISO 8601 date or date-time: `2026-07-31`, `2026-07-31T20:15:00.000Z`,
 * `2026-07-31 20:15`, with or without an offset.
 */
const ISO_DATE_RE =
  /\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?/g;

/**
 * Placeholder delimiter: NUL. The placeholder has to be something a real
 * analytics string cannot contain — a readable sentinel like " a " would be
 * matched inside ordinary prose ("the bad cabbage") and eaten on restore.
 */
const MASK_DELIM = '\u0000';
/** Digit-free placeholder body, so a mask can never itself look phone-shaped. */
function encodeMaskIndex(n: number): string {
  return String(n).replace(/\d/g, (d) => String.fromCharCode(97 + Number(d)));
}
function decodeMaskIndex(s: string): number {
  return Number(s.replace(/[a-j]/g, (c) => String(c.charCodeAt(0) - 97)));
}

/**
 * Redact phone-SHAPED runs, but never at the cost of a legitimate value.
 *
 * The digit-count floor (`MIN_PHONE_DIGITS`) saved the "1.4.2 (231)" build tag.
 * It does NOT save a date: `2026-07-31` is phone-shaped and carries 8 real
 * digits, so it cleared the bar and every `event_timestamp` — which
 * `trackEvent` attaches to EVERY non-performance event — was leaving as
 * `"[redacted-phone]T20:15:00.000Z"`. Silent, universal, and invisible without
 * a fixture that asserts a timestamp survives.
 *
 * This is the third appearance of one trap: shape is not identity. L2-219 hit
 * it on the native rail, L2-220 on the web build tag, L2-221 on the browser
 * rail's own evidence timestamps — and the web scrubber, the oldest of the
 * three, still had it. So ISO tokens are masked out before the phone pass and
 * restored after, rather than the pattern being loosened (which would start
 * letting real phone numbers through).
 */
function redactPhoneLike(value: string): string {
  const masked: string[] = [];
  const withPlaceholders = value.replace(ISO_DATE_RE, (m) => {
    masked.push(m);
    return `${MASK_DELIM}${encodeMaskIndex(masked.length - 1)}${MASK_DELIM}`;
  });

  const scrubbed = withPlaceholders.replace(PHONE_RE, (match) => {
    const digitCount = (match.match(/\d/g) ?? []).length;
    return digitCount >= MIN_PHONE_DIGITS ? '[redacted-phone]' : match;
  });

  // Restore. An unknown index (only reachable if the input already contained a
  // NUL) leaves the placeholder text alone rather than deleting content.
  return scrubbed.replace(
    new RegExp(`${MASK_DELIM}([a-j]+)${MASK_DELIM}`, 'g'),
    (whole, idx: string) => masked[decodeMaskIndex(idx)] ?? whole,
  );
}

/**
 * Redact PII-shaped substrings from a free-form string and bound its length.
 * Order matters: emails and URLs before the token/phone catch-alls.
 */
export function scrubString(value: string): string {
  let out = redactPhoneLike(
    value
      .replace(EMAIL_RE, '[redacted-email]')
      .replace(URL_RE, '[redacted-url]')
      .replace(TOKEN_RE, '[redacted-token]'),
  );
  if (out.length > MAX_STRING_LEN) {
    out = out.slice(0, MAX_STRING_LEN);
  }
  return out;
}

// ============================================================================
// Shape enforcement
// ============================================================================

/**
 * Maximum members retained from a primitive array. GA4 flattens arrays into a
 * bounded string anyway; the cap is here so an unexpectedly large array can't
 * itself become a fingerprint or blow the parameter size limit.
 */
const MAX_ARRAY_LEN = 50;

/**
 * The ONLY value shapes a GA4 event parameter may carry: a string, a finite
 * number, or a boolean.
 *
 * `null`/`undefined` are not "valid" here — they are simply dropped, since an
 * absent parameter and a null one mean the same thing downstream and the null
 * only costs payload.
 */
function isEventPrimitive(value: unknown): value is string | number | boolean {
  const t = typeof value;
  if (t === 'string' || t === 'boolean') return true;
  return t === 'number' && Number.isFinite(value as number);
}

/**
 * Coerce an allowlisted value to a safe SHAPE, or drop it (L2-222 Item 2).
 *
 * The key allowlist answers "may this field be sent at all"; it says nothing
 * about what is *inside* the field. That gap was real: `context` and `item_name`
 * are allowlisted keys, so `context: { email: 'a@b.com', token: '…' }` was
 * forwarded to `gtag` as a whole object — untouched, because the old scrubber
 * only recursed into strings and arrays and returned everything else verbatim.
 * `event_ids: [{ user: … }]` had the same hole one level down: an array member
 * that was not a string was passed straight through.
 *
 * So the rule is now positive rather than subtractive — retain only what is
 * provably an event-valid primitive, or a bounded array of them:
 *  - primitives are kept (strings scrubbed and truncated);
 *  - a flat array of primitives is kept, scrubbed element-wise and capped;
 *  - a nested array, an array containing any non-primitive, and ANY plain
 *    object (including `null`) are dropped entirely.
 *
 * Dropping the whole array rather than filtering it is deliberate: a partially
 * retained array silently changes the meaning of the parameter (a count, an id
 * list), and the caller shape is wrong either way — better to lose the field
 * than to ship a quietly incorrect one.
 */
function coerceParamValue(value: unknown): unknown {
  if (typeof value === 'string') return scrubString(value);
  if (isEventPrimitive(value)) return value;

  if (Array.isArray(value)) {
    // One non-primitive member (object, nested array, NaN, null) disqualifies
    // the whole array — see above.
    if (!value.every(isEventPrimitive)) return undefined;
    return value
      .slice(0, MAX_ARRAY_LEN)
      .map((v) => (typeof v === 'string' ? scrubString(v) : v));
  }

  // Plain objects, Dates, Maps, functions, symbols, bigints, null, NaN, ±∞.
  return undefined;
}

// ============================================================================
// Query → bounded metadata
// ============================================================================

const SEARCH_HASH_SALT_STORAGE_KEY = 'bainluck_search_hash_salt_v1';

let cachedBrowserQuerySalt: string | null = null;
let cachedSaltPersisted = false;

function hasSearchSaltStorageConsent(): boolean {
  const stored = getStoredConsent();
  if (stored === 'all' || stored === 'analytics') return true;
  if (stored === 'none') return false;
  // Jest tests or custom storage mocks may mount window.localStorage without global localStorage.
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      const fallback = window.localStorage.getItem(GA_CONFIG.CONSENT_STORAGE_KEY);
      return fallback === 'all' || fallback === 'analytics';
    }
  } catch {
    // localStorage unavailable: treat as denied for persistence.
  }
  return false;
}

function createBrowserHashSalt(): string {
  try {
    const webCrypto = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;
    if (webCrypto && typeof webCrypto.randomUUID === 'function') {
      return webCrypto.randomUUID().replace(/-/g, '');
    }
    if (webCrypto && typeof webCrypto.getRandomValues === 'function') {
      const bytes = new Uint8Array(16);
      webCrypto.getRandomValues(bytes);
      return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
    }
  } catch {
    // Fall through to non-crypto per-tab fallback below.
  }
  return `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 14)}`;
}

function getBrowserQuerySalt(): string {
  const canPersist = hasSearchSaltStorageConsent();
  if (canPersist) {
    if (cachedBrowserQuerySalt && cachedSaltPersisted) {
      return cachedBrowserQuerySalt;
    }
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const existing = window.localStorage.getItem(SEARCH_HASH_SALT_STORAGE_KEY);
        if (existing && /^[0-9a-z]{12,128}$/i.test(existing.trim())) {
          cachedBrowserQuerySalt = existing.trim().toLowerCase();
          cachedSaltPersisted = true;
          return cachedBrowserQuerySalt;
        }
        const saltToSave = cachedBrowserQuerySalt ?? createBrowserHashSalt();
        window.localStorage.setItem(SEARCH_HASH_SALT_STORAGE_KEY, saltToSave);
        cachedBrowserQuerySalt = saltToSave;
        cachedSaltPersisted = true;
        return saltToSave;
      }
    } catch {
      // localStorage disabled or quota-full: keep an ephemeral per-page salt.
    }
  }

  // Consent absent/declined (181-C) or storage unavailable: keep salt in memory for this page only.
  if (!cachedBrowserQuerySalt) {
    cachedBrowserQuerySalt = createBrowserHashSalt();
  }
  cachedSaltPersisted = false;
  return cachedBrowserQuerySalt;
}

/** Test-only reset for the cached per-browser search hash salt. */
export function _resetBrowserQuerySaltForTests(): void {
  cachedBrowserQuerySalt = null;
  cachedSaltPersisted = false;
}

const SHA256_K = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];

function encodeUtf8(input: string): Uint8Array {
  if (typeof TextEncoder !== 'undefined') {
    return new TextEncoder().encode(input);
  }
  const out: number[] = [];
  for (let i = 0; i < input.length; i++) {
    let code = input.charCodeAt(i);
    if (code < 0x80) {
      out.push(code);
    } else if (code < 0x800) {
      out.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
    } else if (code >= 0xd800 && code <= 0xdbff && i + 1 < input.length) {
      const next = input.charCodeAt(i + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        code = 0x10000 + ((code - 0xd800) << 10) + (next - 0xdc00);
        i++;
        out.push(
          0xf0 | (code >> 18),
          0x80 | ((code >> 12) & 0x3f),
          0x80 | ((code >> 6) & 0x3f),
          0x80 | (code & 0x3f),
        );
      } else {
        out.push(0xef, 0xbf, 0xbd);
      }
    } else {
      out.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
    }
  }
  return new Uint8Array(out);
}

function rotr(x: number, n: number): number {
  return (x >>> n) | (x << (32 - n));
}

/** Synchronous FIPS 180-4 SHA-256 digest (hex) over UTF-8 input. */
export function sha256Hex(input: string): string {
  const bytes = encodeUtf8(input);
  const paddedLen = Math.ceil((bytes.length + 9) / 64) * 64;
  const padded = new Uint8Array(paddedLen);
  padded.set(bytes);
  padded[bytes.length] = 0x80;

  const bitLen = bytes.length * 8;
  const hiBits = Math.floor(bitLen / 0x100000000);
  const loBits = bitLen >>> 0;
  const tail = paddedLen - 8;
  padded[tail] = (hiBits >>> 24) & 0xff;
  padded[tail + 1] = (hiBits >>> 16) & 0xff;
  padded[tail + 2] = (hiBits >>> 8) & 0xff;
  padded[tail + 3] = hiBits & 0xff;
  padded[tail + 4] = (loBits >>> 24) & 0xff;
  padded[tail + 5] = (loBits >>> 16) & 0xff;
  padded[tail + 6] = (loBits >>> 8) & 0xff;
  padded[tail + 7] = loBits & 0xff;

  let h0 = 0x6a09e667;
  let h1 = 0xbb67ae85;
  let h2 = 0x3c6ef372;
  let h3 = 0xa54ff53a;
  let h4 = 0x510e527f;
  let h5 = 0x9b05688c;
  let h6 = 0x1f83d9ab;
  let h7 = 0x5be0cd19;

  const w = new Int32Array(64);
  for (let offset = 0; offset < paddedLen; offset += 64) {
    for (let i = 0; i < 16; i++) {
      const idx = offset + i * 4;
      w[i] =
        (padded[idx] << 24) |
        (padded[idx + 1] << 16) |
        (padded[idx + 2] << 8) |
        padded[idx + 3];
    }
    for (let i = 16; i < 64; i++) {
      const w15 = w[i - 15];
      const w2 = w[i - 2];
      const s0 = rotr(w15, 7) ^ rotr(w15, 18) ^ (w15 >>> 3);
      const s1 = rotr(w2, 17) ^ rotr(w2, 19) ^ (w2 >>> 10);
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
    }

    let a = h0;
    let b = h1;
    let c = h2;
    let d = h3;
    let e = h4;
    let f = h5;
    let g = h6;
    let h = h7;

    for (let i = 0; i < 64; i++) {
      const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
      const ch = (e & f) ^ (~e & g);
      const temp1 = (h + s1 + ch + SHA256_K[i] + w[i]) | 0;
      const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) | 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) | 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) | 0;
    }

    h0 = (h0 + a) | 0;
    h1 = (h1 + b) | 0;
    h2 = (h2 + c) | 0;
    h3 = (h3 + d) | 0;
    h4 = (h4 + e) | 0;
    h5 = (h5 + f) | 0;
    h6 = (h6 + g) | 0;
    h7 = (h7 + h) | 0;
  }

  return [h0, h1, h2, h3, h4, h5, h6, h7]
    .map((word) => (word >>> 0).toString(16).padStart(8, '0'))
    .join('');
}

/**
 * Decision 404: B — SHA-256 cut to 64 bits (16 lowercase hex chars) over a
 * random 128-bit browser-scoped salt (`${salt}\u0000${norm}`). The salt is
 * persisted in `localStorage` only after an explicit Allow consent (`181-C`),
 * and stays in memory for the current page otherwise.
 */
export function hashQuery(raw: string): string {
  const norm = raw.trim().toLowerCase();
  const salt = getBrowserQuerySalt();
  return sha256Hex(`${salt}\u0000${norm}`).slice(0, 16);
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
      if (!perfKeys.has(key) || value === undefined) continue;
      const coerced = coerceParamValue(value);
      if (coerced !== undefined) out[key] = coerced;
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
    const coerced = coerceParamValue(value); // …then reject unknown SHAPES
    if (coerced !== undefined) out[key] = coerced;
  }

  return { name: eventName, params: out };
}
