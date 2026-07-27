/**
 * L2-190 Item 3 — central event parameter allowlist / sanitation boundary.
 *
 * Proves the single boundary before `gtag`:
 *  - rejects unknown event names and unknown parameters,
 *  - strips emails / phones / URLs / tokens / raw queries / free text,
 *  - reduces a raw search query to bounded, joinable, non-PII metadata,
 *  - keeps approved categorical / numeric fields intact,
 *  - and never lets user/session/token/market payload into perf events.
 */

import {
  sanitizeEvent,
  scrubString,
  hashQuery,
  queryMetadata,
  KNOWN_EVENT_NAMES,
  ALLOWED_PARAM_KEYS,
} from '@/lib/analytics/sanitize';

describe('sanitizeEvent — event-name allowlist', () => {
  it('drops unknown event names entirely', () => {
    expect(sanitizeEvent('totally_made_up', { foo: 1 })).toBeNull();
    expect(sanitizeEvent('', {})).toBeNull();
  });

  it('accepts a registered event name', () => {
    const out = sanitizeEvent('search_submit', { results_count: 3, futures_count: 1, surface: 'search' });
    expect(out).not.toBeNull();
    expect(out!.name).toBe('search_submit');
  });
});

describe('sanitizeEvent — unknown parameter rejection', () => {
  it('drops params that are not in the allowlist', () => {
    const out = sanitizeEvent('search_submit', {
      results_count: 5,
      // none of these are allowed:
      user_id: 'firebase-abc123',
      email: 'a@b.com',
      secret_token: 'xyz',
      arbitrary_free_text: 'hello there',
    } as Record<string, unknown>);
    expect(out).not.toBeNull();
    expect(out!.params).toHaveProperty('results_count', 5);
    expect(out!.params).not.toHaveProperty('user_id');
    expect(out!.params).not.toHaveProperty('email');
    expect(out!.params).not.toHaveProperty('secret_token');
    expect(out!.params).not.toHaveProperty('arbitrary_free_text');
  });

  it('drops hard-deny keys even if they were allowlisted-looking', () => {
    const out = sanitizeEvent('page_view', {
      page_type: 'search',
      page_path: '/search',
      page_title: 'Search',
      referrer: 'https://google.com/search?q=my+secret+query',
      url: 'https://bainluck.com/x?token=abc',
    } as Record<string, unknown>);
    expect(out!.params).toHaveProperty('page_path', '/search');
    expect(out!.params).not.toHaveProperty('referrer');
    expect(out!.params).not.toHaveProperty('url');
  });
});

describe('sanitizeEvent — raw query → bounded metadata', () => {
  it('replaces raw query with hash/length/word_count and never the raw text', () => {
    const out = sanitizeEvent('search_submit', {
      query: 'Lakers vs Celtics tonight',
      results_count: 8,
      futures_count: 2,
      surface: 'search',
    } as Record<string, unknown>);
    expect(out!.params).not.toHaveProperty('query');
    expect(out!.params).toHaveProperty('query_hash');
    expect(out!.params).toHaveProperty('query_length', 25);
    expect(out!.params).toHaveProperty('query_word_count', 4);
    // Raw text must not appear anywhere in the serialized payload.
    expect(JSON.stringify(out!.params)).not.toContain('Lakers');
  });

  it('is joinable: the same query yields the same hash across events', () => {
    const submit = sanitizeEvent('search_submit', { query: 'Fed rate cut odds', results_count: 1, futures_count: 1, surface: 'search' } as Record<string, unknown>);
    const click = sanitizeEvent('search_result_click', { query: 'Fed rate cut odds', result_type: 'futures', result_id: 42, position: 0, surface: 'search' } as Record<string, unknown>);
    const dest = sanitizeEvent('destination_engaged', { query: 'Fed rate cut odds', result_type: 'futures', result_id: 42, rank: 0, dwell_ms: 5000, surface: 'search' } as Record<string, unknown>);
    expect(submit!.params.query_hash).toBe(click!.params.query_hash);
    expect(click!.params.query_hash).toBe(dest!.params.query_hash);
  });

  it('hashing normalizes case/whitespace but differs for different queries', () => {
    expect(hashQuery('  Lakers Celtics  ')).toBe(hashQuery('lakers celtics'));
    expect(hashQuery('lakers')).not.toBe(hashQuery('celtics'));
  });

  it('queryMetadata bounds an outlier-length query', () => {
    const md = queryMetadata('x'.repeat(5000));
    expect(md.query_length).toBe(200);
    expect(md.query_word_count).toBe(1);
  });
});

describe('scrubString — PII redaction fixtures', () => {
  it('redacts emails', () => {
    expect(scrubString('contact me at jane.doe@example.com please')).toContain('[redacted-email]');
    expect(scrubString('jane.doe@example.com')).not.toContain('example.com');
  });

  it('redacts URLs', () => {
    expect(scrubString('see https://evil.test/path?token=1')).toContain('[redacted-url]');
    expect(scrubString('go to www.foo.com/bar')).toContain('[redacted-url]');
  });

  it('redacts token-shaped strings and JWTs', () => {
    expect(scrubString('Bearer eyJhbGci.OiJIUzI1NiIsInR5cCI6.IkpXVCJ9')).toContain('[redacted-token]');
    expect(scrubString('key=ABCDEFGHIJKLMNOPQRSTUVWX12345')).toContain('[redacted-token]');
  });

  it('redacts phone-like runs', () => {
    expect(scrubString('call +1 (415) 555-1234 now')).toContain('[redacted-phone]');
  });

  it('truncates overlong (non-token) strings to the bound', () => {
    // Short words separated by spaces so no token/phone pattern matches — only
    // the length bound applies.
    const long = 'ab '.repeat(100); // 300 chars, no 24+ char run
    expect(scrubString(long).length).toBe(120);
  });

  it('redacts a long unbroken run as a token (not just truncation)', () => {
    expect(scrubString('a'.repeat(500))).toBe('[redacted-token]');
  });

  it('leaves ordinary short categorical text intact', () => {
    expect(scrubString('discover')).toBe('discover');
    expect(scrubString('basketball_nba')).toBe('basketball_nba');
  });
});

describe('sanitizeEvent — approved fields survive; malformed handled', () => {
  it('keeps approved categorical + numeric fields', () => {
    const out = sanitizeEvent('feed_card_impression', {
      content_type: 'futures',
      item_id: 123,
      category: 'politics',
      position: 4,
      score: 87.5,
      personalized: true,
      surface: 'discover',
    } as Record<string, unknown>);
    expect(out!.params).toEqual(
      expect.objectContaining({
        content_type: 'futures',
        item_id: 123,
        category: 'politics',
        position: 4,
        score: 87.5,
        personalized: true,
        surface: 'discover',
      }),
    );
  });

  it('scrubs free-text headline/item_name but keeps them (content, not user input)', () => {
    const out = sanitizeEvent('feed_card_action', {
      action: 'detail_click',
      content_type: 'futures',
      item_id: 1,
      category: 'tech',
      item_name: 'Contact support@leak.com for info',
      surface: 'discover',
    } as Record<string, unknown>);
    expect(out!.params.item_name).toContain('[redacted-email]');
    expect(String(out!.params.item_name)).not.toContain('leak.com');
  });

  it('handles null/undefined params without throwing', () => {
    expect(sanitizeEvent('feed_refresh', null)).not.toBeNull();
    expect(sanitizeEvent('feed_refresh', undefined)).not.toBeNull();
    // undefined field values are dropped (not serialized as undefined)
    const out = sanitizeEvent('feed_refresh', { trigger: 'auto', new_items_count: undefined } as Record<string, unknown>);
    expect(out!.params).toHaveProperty('trigger', 'auto');
    expect(out!.params).not.toHaveProperty('new_items_count');
  });
});

describe('sanitizeEvent — performance events are strict (no leak)', () => {
  it('feed_telemetry keeps only its exact keys, strips enrichment/PII', () => {
    const out = sanitizeEvent('feed_telemetry', {
      endpoint: '/api/feed',
      cohort: 'shared_anon',
      cache_status: 'hit',
      backend_elapsed_ms: 120,
      duration_ms: 150,
      // things that must NOT ride along:
      session_id: '1699999999999',
      user_id: 'firebase-abc',
      platform: 'web',
      event_timestamp: '2026-07-27T00:00:00Z',
      items: [{ id: 1 }],
    } as Record<string, unknown>);
    expect(Object.keys(out!.params).sort()).toEqual(
      ['backend_elapsed_ms', 'cache_status', 'cohort', 'duration_ms', 'endpoint'].sort(),
    );
    for (const forbidden of ['session_id', 'user_id', 'platform', 'event_timestamp', 'items']) {
      expect(out!.params).not.toHaveProperty(forbidden);
    }
  });

  it('web_vital keeps only its exact keys', () => {
    const out = sanitizeEvent('web_vital', {
      metric_name: 'LCP',
      metric_value: 2400,
      rating: 'good',
      navigation_type: 'navigate',
      page_path: '/discover',
      session_id: 'x',
      user_id: 'y',
    } as Record<string, unknown>);
    expect(Object.keys(out!.params).sort()).toEqual(
      ['metric_name', 'metric_value', 'navigation_type', 'page_path', 'rating'].sort(),
    );
  });
});

describe('taxonomy integrity', () => {
  it('registers the perf + core funnel events', () => {
    for (const name of ['feed_telemetry', 'web_vital', 'page_view', 'search_submit', 'destination_engaged']) {
      expect(KNOWN_EVENT_NAMES.has(name as never)).toBe(true);
    }
  });

  it('registers every currently-emitted event name (no live event is silently dropped)', () => {
    // These are all emitted from app/components code today; the boundary must
    // let them through. Extend this list when adding a new tracked event.
    const emitted = [
      'theme_bundle_expand',
      'eval_promote_toggle',
      'team_cluster_verdict',
      'friend_challenge_view',
      'friend_challenge_accept',
      'friend_challenge_share',
    ];
    for (const name of emitted) {
      expect(KNOWN_EVENT_NAMES.has(name as never)).toBe(true);
    }
  });

  it('does not allowlist identity/PII param keys', () => {
    for (const k of ['user_id', 'email', 'query', 'referrer', 'url', 'token']) {
      expect(ALLOWED_PARAM_KEYS.has(k)).toBe(false);
    }
  });
});
