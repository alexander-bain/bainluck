/**
 * Queue 310 — launch instrumentation: the four events must actually LEAVE the
 * browser.
 *
 * These are param-level fixtures on purpose. The event-NAME registry in
 * `sanitize.ts` is type-derived (`Record<AnalyticsEventName, true>`), so a
 * missing name fails `tsc`; the PARAMETER allowlist is a hand-maintained
 * `Set<string>` with no type linkage, so a param that is declared, emitted, and
 * never allowlisted is dropped silently at the last boundary before `gtag`.
 * That is the L2-217 failure mode one level down, and a test that only asserts
 * the event name survives would sail straight past it.
 *
 * So: for every new key, assert the VALUE arrives.
 */

import {
  sanitizeEvent,
  KNOWN_EVENT_NAMES,
  ALLOWED_PARAM_KEYS,
} from '@/lib/analytics/sanitize';

describe('Queue 310 — event names are registered', () => {
  it.each(['session_open', 'feed_exit', 'search_no_results'])(
    'registers %s',
    (name) => {
      expect(KNOWN_EVENT_NAMES.has(name as never)).toBe(true);
      expect(sanitizeEvent(name, {})).not.toBeNull();
    },
  );

  it('does NOT register the GA4-reserved name `session_start`', () => {
    // GA4 collects `session_start` automatically and rejects custom sends of
    // it; our own admin funnel (`admin_analytics.py`) and the Power Users
    // audience (`setup_ga4.py`) both read it under that automatic meaning. If
    // this ever starts passing, we are double-counting visits.
    expect(KNOWN_EVENT_NAMES.has('session_start' as never)).toBe(false);
    expect(sanitizeEvent('session_start', { session_number: 2 })).toBeNull();
  });
});

describe('Queue 310 — every new param key survives the boundary', () => {
  it.each([
    'is_first_session',
    'first_seen_date',
    'last_position',
    'visible_count',
    'max_scroll_depth',
    'terminal_state',
    'market_type',
  ])('allowlists %s', (key) => {
    expect(ALLOWED_PARAM_KEYS.has(key)).toBe(true);
  });

  it('session_open keeps all three params intact', () => {
    const out = sanitizeEvent('session_open', {
      is_first_session: true,
      session_number: 1,
      first_seen_date: '2026-08-10',
    });
    expect(out!.params).toEqual({
      is_first_session: true,
      session_number: 1,
      first_seen_date: '2026-08-10',
    });
  });

  it('first_seen_date survives the phone scrubber VERBATIM', () => {
    // `2026-08-10` is phone-SHAPED and carries 8 real digits, so it clears the
    // >=7-digit floor. Without the ISO mask it would leave as
    // "[redacted-phone]" and the first-session cut would be silently unusable.
    // This trap has now bitten this scrubber three times (L2-219/220/221).
    const out = sanitizeEvent('session_open', {
      is_first_session: false,
      session_number: 4,
      first_seen_date: '2026-08-10',
    });
    expect(out!.params.first_seen_date).toBe('2026-08-10');
  });

  it('feed_exit keeps all five params intact', () => {
    const out = sanitizeEvent('feed_exit', {
      last_position: 11,
      visible_count: 12,
      max_scroll_depth: 87,
      dwell_ms: 42_000,
      terminal_state: 'mid_scroll',
    });
    expect(out!.params).toMatchObject({
      last_position: 11,
      visible_count: 12,
      max_scroll_depth: 87,
      dwell_ms: 42_000,
      terminal_state: 'mid_scroll',
    });
  });

  it.each(['end_of_feed', 'unavailable', 'mid_scroll', 'dismissed_last'])(
    'feed_exit carries terminal_state=%s',
    (state) => {
      const out = sanitizeEvent('feed_exit', { terminal_state: state });
      expect(out!.params.terminal_state).toBe(state);
    },
  );

  it.each(['claim', 'quantity', 'duel', 'field', 'container_member', 'unshaped'])(
    'feed_card_action carries market_type=%s',
    (shape) => {
      const out = sanitizeEvent('feed_card_action', {
        action: 'detail_click',
        content_type: 'futures',
        item_id: 1,
        category: 'politics',
        surface: 'discover',
        market_type: shape,
      });
      expect(out!.params.market_type).toBe(shape);
    },
  );

  it('feed_card_impression carries market_type too (the denominator)', () => {
    // The question is a RATE. A tap count with no impression count by shape
    // cannot answer "do quantity ladders out-tap fields".
    const out = sanitizeEvent('feed_card_impression', {
      content_type: 'futures',
      item_id: 7,
      category: 'economics',
      position: 3,
      score: 61,
      surface: 'discover',
      market_type: 'quantity',
    });
    expect(out!.params.market_type).toBe('quantity');
  });
});

describe('Queue 310 — content-free by construction', () => {
  it('search_no_results sends a joinable hash, never the raw query', () => {
    const out = sanitizeEvent('search_no_results', {
      query: 'when does lebron retire',
      results_count: 0,
      surface: 'search',
    });
    expect(out!.params.query).toBeUndefined();
    expect(out!.params.query_hash).toEqual(expect.any(String));
    expect(out!.params.results_count).toBe(0);
  });

  it('the search_no_results hash JOINS to search_submit for the same query', () => {
    // The whole reason the hash exists. If these ever diverge, the funnel
    // "searched -> got nothing -> left" cannot be assembled.
    const q = 'kalshi vs polymarket';
    const miss = sanitizeEvent('search_no_results', { query: q, results_count: 0 });
    const submit = sanitizeEvent('search_submit', { query: q, results_count: 0, futures_count: 0 });
    expect(miss!.params.query_hash).toBe(submit!.params.query_hash);
  });

  it('feed_exit cannot smuggle content even if a caller adds some', () => {
    const out = sanitizeEvent('feed_exit', {
      last_position: 3,
      visible_count: 4,
      max_scroll_depth: 50,
      dwell_ms: 1000,
      terminal_state: 'mid_scroll',
      // None of these are part of the event; all must be dropped.
      item_name: 'Will Iran close the Strait of Hormuz?',
      user_id: 'uid_123',
      email: 'a@b.com',
    } as Record<string, unknown>);
    expect(out!.params.item_name).toBeUndefined();
    expect(out!.params.user_id).toBeUndefined();
    expect(out!.params.email).toBeUndefined();
    expect(out!.params.terminal_state).toBe('mid_scroll');
  });

  it('still drops an unregistered param alongside the new ones', () => {
    const out = sanitizeEvent('session_open', {
      is_first_session: true,
      session_number: 1,
      first_seen_date: '2026-08-10',
      totally_new_key: 'nope',
    } as Record<string, unknown>);
    expect(out!.params.totally_new_key).toBeUndefined();
    expect(out!.params.is_first_session).toBe(true);
  });
});
