/**
 * L2-222 Item 2 (#1453) — the telemetry boundary rejects SHAPES, not just keys.
 *
 * The key allowlist answers "may this field be sent at all". It says nothing
 * about what is inside the field, and the scrubber only recursed into strings
 * and top-level string array members — everything else was returned verbatim.
 * So an allowlisted key carrying the wrong shape walked straight through:
 *
 *   context:   { email: 'a@b.com', token: 'eyJ…' }   → forwarded whole
 *   event_ids: [{ user_id: 'uid' }]                  → forwarded whole
 *   chip_tags: [['nested', 'a@b.com']]               → nested array, untouched
 *
 * None of these are shapes GA4 can even represent, so nothing legitimate is
 * lost by refusing them — and refusing is the only way the boundary's promise
 * ("no PII leaves here") survives a caller passing the wrong thing.
 *
 * The rule is positive: retain event-valid primitives and bounded arrays of
 * primitives; drop everything else. These fixtures pin BOTH directions — the
 * hostile shapes fail closed AND the real payloads the app sends are intact.
 */

import { sanitizeEvent, scrubString } from '@/lib/analytics/sanitize';

const has = (o: Record<string, unknown>, k: string) => Object.hasOwn(o, k);

// ============================================================================
// Fail closed
// ============================================================================

describe('plain objects under an allowlisted key are dropped', () => {
  it('drops a nested PII object under `context`', () => {
    const out = sanitizeEvent('api_error', {
      error_type: 'network',
      context: { email: 'alex@example.com', token: 'eyJhbGciOiJIUzI1NiJ9.abc.def' },
    });
    expect(out).not.toBeNull();
    expect(has(out!.params, 'context')).toBe(false);
    // The sibling primitive survives — the drop is per-field, not per-event.
    expect(out!.params.error_type).toBe('network');
    expect(JSON.stringify(out!.params)).not.toContain('alex@example.com');
    expect(JSON.stringify(out!.params)).not.toContain('eyJhbGciOiJIUzI1NiJ9');
  });

  it('drops a nested object even when its contents look harmless', () => {
    const out = sanitizeEvent('section_toggle', {
      section_type: 'props',
      item_name: { first: 'a', second: 'b' },
    });
    expect(has(out!.params, 'item_name')).toBe(false);
  });

  it('drops null, Date, Map and function values', () => {
    const out = sanitizeEvent('api_error', {
      error_type: 'network',
      endpoint: null,
      timestamp: new Date('2026-07-31T00:00:00Z'),
      context: new Map([['a', 'b']]),
      error_message: () => 'boom',
    } as unknown as Record<string, unknown>);
    for (const k of ['endpoint', 'timestamp', 'context', 'error_message']) {
      expect(has(out!.params, k)).toBe(false);
    }
  });

  it('drops non-finite numbers', () => {
    const out = sanitizeEvent('chart_view', {
      chart_type: 'probability',
      data_points_count: NaN,
      data_span_hours: Infinity,
      has_data: true,
    } as unknown as Record<string, unknown>);
    expect(has(out!.params, 'data_points_count')).toBe(false);
    expect(has(out!.params, 'data_span_hours')).toBe(false);
    expect(out!.params.has_data).toBe(true);
  });
});

describe('arrays must be flat and primitive', () => {
  it('drops an array containing an object', () => {
    const out = sanitizeEvent('event_card_impression', {
      event_ids: [1, 2, { user_id: 'uid-9' }],
    } as unknown as Record<string, unknown>);
    expect(has(out!.params, 'event_ids')).toBe(false);
    expect(JSON.stringify(out!.params)).not.toContain('uid-9');
  });

  it('drops a NESTED array', () => {
    const out = sanitizeEvent('feed_filter_chip', {
      chip_label: 'Politics',
      chip_tags: [['nested', 'alex@example.com']],
    } as unknown as Record<string, unknown>);
    expect(has(out!.params, 'chip_tags')).toBe(false);
    expect(out!.params.chip_label).toBe('Politics');
  });

  it('drops the WHOLE array rather than filtering it', () => {
    // A partially-retained id list silently changes what the parameter means.
    const out = sanitizeEvent('event_card_impression', {
      event_ids: [1, 2, 3, null],
    } as unknown as Record<string, unknown>);
    expect(has(out!.params, 'event_ids')).toBe(false);
  });

  it('caps a long primitive array at 50 members', () => {
    const out = sanitizeEvent('event_card_impression', {
      event_ids: Array.from({ length: 300 }, (_, i) => i),
    });
    expect((out!.params.event_ids as number[]).length).toBe(50);
  });

  it('scrubs PII inside a retained primitive array', () => {
    const out = sanitizeEvent('feed_filter_chip', {
      chip_label: 'x',
      chip_tags: ['ok', 'alex@example.com'],
    });
    expect(out!.params.chip_tags).toEqual(['ok', '[redacted-email]']);
  });
});

describe('performance events enforce shapes too', () => {
  it('drops a nested object under a My Stuff perf key', () => {
    const out = sanitizeEvent('my_stuff_load', {
      stage: 'first_card',
      surface: { url: 'https://bainluck.com/my-stuff?token=abc' },
      item_count: 13,
    } as unknown as Record<string, unknown>);
    expect(has(out!.params, 'surface')).toBe(false);
    expect(out!.params.item_count).toBe(13);
    expect(JSON.stringify(out!.params)).not.toContain('token=abc');
  });

  it('drops a nested object under a Web Vitals key', () => {
    const out = sanitizeEvent('web_vital', {
      metric_name: 'LCP',
      metric_value: 1234.5,
      rating: 'good',
      page_path: { raw: 'https://bainluck.com/e/1?email=a@b.com' },
    } as unknown as Record<string, unknown>);
    expect(has(out!.params, 'page_path')).toBe(false);
    expect(out!.params.metric_name).toBe('LCP');
    expect(JSON.stringify(out!.params)).not.toContain('a@b.com');
  });
});

// ============================================================================
// …while every real payload stays intact
// ============================================================================

describe('legitimate payloads are untouched', () => {
  it('event_ids: a flat number array survives', () => {
    const out = sanitizeEvent('event_card_impression', { event_ids: [11, 22, 33] });
    expect(out!.params.event_ids).toEqual([11, 22, 33]);
  });

  it('chip_tags: a flat string array survives', () => {
    const out = sanitizeEvent('feed_filter_chip', {
      chip_label: 'Politics',
      chip_tags: ['politics', 'elections'],
    });
    expect(out!.params.chip_tags).toEqual(['politics', 'elections']);
  });

  it('sports_browsed inside session_engagement survives', () => {
    const out = sanitizeEvent('session_engagement', {
      events_viewed_count: 4,
      sports_browsed: ['basketball_nba', 'baseball_mlb'],
      pages_viewed: 7,
      session_duration_seconds: 240,
      used_filters: true,
      viewed_charts: false,
    });
    expect(out!.params.sports_browsed).toEqual(['basketball_nba', 'baseball_mlb']);
    expect(out!.params.used_filters).toBe(true);
    expect(out!.params.viewed_charts).toBe(false); // `false` must not be dropped
  });

  it('the Discover Stats scorecard share survives', () => {
    const out = sanitizeEvent('share_scorecard', {
      method: 'native',
      accuracy_percent: 63,
      total_questions: 41,
      streak: 5,
      surface: 'discover_stats',
    });
    expect(out!.params).toEqual({
      method: 'native',
      accuracy_percent: 63,
      total_questions: 41,
      streak: 5,
      surface: 'discover_stats',
    });
  });

  it('a Web Vitals packet survives', () => {
    const out = sanitizeEvent('web_vital', {
      metric_name: 'CLS',
      metric_value: 0.04,
      rating: 'good',
      navigation_type: 'navigate',
      page_path: '/discover',
    });
    expect(out!.params).toEqual({
      metric_name: 'CLS',
      metric_value: 0.04,
      rating: 'good',
      navigation_type: 'navigate',
      page_path: '/discover',
    });
  });

  it('the full 13-field My Stuff latency packet survives, build tag included', () => {
    const packet = {
      stage: 'first_card',
      auth_ready_ms: 120,
      network_ms: 340,
      backend_elapsed_ms: 210,
      decode_ms: 12,
      required_data_ready_ms: 480,
      first_render_ms: 505,
      cache_outcome: 'miss',
      cache_age_seconds: 0,
      item_count: 13,
      app_build: '1.4.2 (231)',
      surface: 'web',
      outcome_class: 'ok',
    };
    const out = sanitizeEvent('my_stuff_load', packet);
    expect(Object.keys(out!.params).length).toBe(13);
    expect(out!.params).toEqual(packet);
    // The L2-219/L2-220 trap: a 6-digit build tag is phone-SHAPED but is not a
    // phone number, and must survive verbatim.
    expect(out!.params.app_build).toBe('1.4.2 (231)');
  });

  it('an ISO timestamp is not mistaken for a phone number', () => {
    const out = sanitizeEvent('chart_view', {
      chart_type: 'probability',
      has_data: true,
      event_timestamp: '2026-07-31T20:15:00.000Z',
    });
    expect(out!.params.event_timestamp).toBe('2026-07-31T20:15:00.000Z');
  });

  it('the ISO mask does not eat ordinary prose or drop real phone numbers', () => {
    // The mask has to be invisible: it must not disturb text that merely
    // contains lowercase letters, and it must not weaken the phone rule.
    expect(scrubString('the bad cabbage')).toBe('the bad cabbage');
    expect(scrubString('call 415 555 2671 now')).toBe('call [redacted-phone] now');
    expect(scrubString('on 2026-07-31 call 415 555 2671')).toBe(
      'on 2026-07-31 call [redacted-phone]',
    );
    // Several dates in one string restore in the right order.
    expect(scrubString('2026-07-31 to 2026-08-04')).toBe('2026-07-31 to 2026-08-04');
    // A bare date survives.
    expect(scrubString('2026-07-31')).toBe('2026-07-31');
  });

  it('a zero and an empty string are retained, not treated as absent', () => {
    const out = sanitizeEvent('scroll_depth', {
      depth_percent: 0,
      page_type: '',
    } as unknown as Record<string, unknown>);
    expect(out!.params.depth_percent).toBe(0);
    expect(out!.params.page_path).toBeUndefined();
    expect(out!.params.page_type).toBe('');
  });
});
