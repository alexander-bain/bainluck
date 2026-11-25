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

import { createHash } from 'node:crypto';
import {
  _resetBrowserQuerySaltForTests,
  sanitizeEvent,
  scrubString,
  sha256Hex,
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

  it('does NOT redact a phone-SHAPED value with too few digits (L2-220)', () => {
    // The build tag "1.4.2 (231)" is phone-shaped but carries only 6 digits.
    // Shape-only matching rewrote it to "[redacted-phone])", which would have
    // destroyed build attribution on every My Stuff latency packet. Redaction
    // now needs >=7 real digits — the same rule L2-219 gave the native rail.
    expect(scrubString('1.4.2 (231)')).toBe('1.4.2 (231)');
    expect(scrubString('build 1.4.2 (231)')).toBe('build 1.4.2 (231)');
    // A version with a long build number IS 7+ digits and still redacts —
    // the guard is digit-count, not an exemption for anything version-shaped.
    expect(scrubString('12.34.56 (7890)')).toContain('[redacted-phone]');
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

// ============================================================================
// Per-browser keyed SHA-256 hash & consent-gated salt persistence (Decision 404: B)
// ============================================================================

describe('sha256Hex — synchronous FIPS 180-4 SHA-256 known-answer vectors', () => {
  it('matches NIST empty-string and "abc" known-answer vectors', () => {
    expect(sha256Hex('')).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    );
    expect(sha256Hex('abc')).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });

  it('matches Node crypto SHA-256 across multi-block, exact-block-boundary, and non-ASCII UTF-8 inputs', () => {
    const vectors = [
      'abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq', // 56 bytes -> 2 blocks
      'a'.repeat(130),
      'São Paulo café 🏆 2026',
    ];
    for (const v of vectors) {
      expect(sha256Hex(v)).toBe(createHash('sha256').update(v, 'utf8').digest('hex'));
    }
  });

  it('matches Node crypto even via the pure-JS UTF-8 encoder fallback (TextEncoder absent)', () => {
    const originalTextEncoder = globalThis.TextEncoder;
    // @ts-expect-error testing non-TextEncoder runtime fallback
    delete globalThis.TextEncoder;
    try {
      const sample = 'São Paulo café 🏆 2026';
      expect(sha256Hex(sample)).toBe(createHash('sha256').update(sample, 'utf8').digest('hex'));
    } finally {
      globalThis.TextEncoder = originalTextEncoder;
    }
  });
});

describe('hashQuery — Decision 404: B per-browser keyed SHA-256 (Allow-only storage)', () => {
  const CONSENT_STORAGE_KEY = 'bainluck_consent';
  const SALT_STORAGE_KEY = 'bainluck_search_hash_salt_v1';
  const FIXED_SALT_1 = '00112233445566778899aabbccddeeff';
  const FIXED_SALT_2 = 'ffeeddccbbaa99887766554433221100';
  const ORIGINAL_WINDOW = (globalThis as { window?: unknown }).window;

  function installMockLocalStorage(initial?: Record<string, string>): Map<string, string> {
    const store = new Map<string, string>(Object.entries(initial ?? {}));
    (globalThis as { window?: unknown }).window = {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => {
          store.set(k, v);
        },
      },
    };
    return store;
  }

  beforeEach(() => {
    _resetBrowserQuerySaltForTests();
  });

  afterEach(() => {
    _resetBrowserQuerySaltForTests();
    if (ORIGINAL_WINDOW === undefined) {
      delete (globalThis as { window?: unknown }).window;
    } else {
      (globalThis as { window?: unknown }).window = ORIGINAL_WINDOW;
    }
  });

  it('matches externally computed SHA-256(salt + NUL + normalized query) cut to 64 bits', () => {
    installMockLocalStorage({
      [CONSENT_STORAGE_KEY]: 'all',
      [SALT_STORAGE_KEY]: FIXED_SALT_1,
    });
    const out = hashQuery('Lakers');
    const external = createHash('sha256')
      .update(`${FIXED_SALT_1}\u0000lakers`, 'utf8')
      .digest('hex')
      .slice(0, 16);
    expect(out).toBe('b8f6a9534f94cb9c');
    expect(out).toBe(external);
  });

  it('produces unrelated 64-bit hashes sharing no prefix for the same query under two salts', () => {
    installMockLocalStorage({
      [CONSENT_STORAGE_KEY]: 'all',
      [SALT_STORAGE_KEY]: FIXED_SALT_1,
    });
    const h1 = hashQuery('lakers');
    expect(h1).toBe('b8f6a9534f94cb9c');

    _resetBrowserQuerySaltForTests();
    installMockLocalStorage({
      [CONSENT_STORAGE_KEY]: 'all',
      [SALT_STORAGE_KEY]: FIXED_SALT_2,
    });
    const h2 = hashQuery('lakers');
    expect(h2).toBe('1219761f75e13cc9');
    expect(h1.slice(0, 4)).not.toBe(h2.slice(0, 4));

    _resetBrowserQuerySaltForTests();
    installMockLocalStorage({ [CONSENT_STORAGE_KEY]: 'all' });
    const rand1 = hashQuery('lakers');
    _resetBrowserQuerySaltForTests();
    installMockLocalStorage({ [CONSENT_STORAGE_KEY]: 'all' });
    const rand2 = hashQuery('lakers');
    expect(rand1).toMatch(/^[0-9a-f]{16}$/);
    expect(rand2).toMatch(/^[0-9a-f]{16}$/);
    expect(rand1.slice(0, 4)).not.toBe(rand2.slice(0, 4));
  });

  it('writes NO salt to localStorage when consent is unset or declined (181-C)', () => {
    for (const initialConsent of [undefined, 'none']) {
      _resetBrowserQuerySaltForTests();
      const setItemSpy = jest.fn();
      const store = new Map<string, string>(
        initialConsent ? [[CONSENT_STORAGE_KEY, initialConsent]] : [],
      );
      (globalThis as { window?: unknown }).window = {
        localStorage: {
          getItem: (k: string) => store.get(k) ?? null,
          setItem: (k: string, v: string) => {
            setItemSpy(k, v);
            store.set(k, v);
          },
        },
      };

      const first = hashQuery('lakers');
      expect(first).toMatch(/^[0-9a-f]{16}$/);
      // Stable within the same page without writing to localStorage.
      expect(hashQuery('LAKERS')).toBe(first);
      expect(setItemSpy).not.toHaveBeenCalled();
      expect(store.has(SALT_STORAGE_KEY)).toBe(false);

      // Reload starts fresh when unconsented.
      _resetBrowserQuerySaltForTests();
      const reloaded = hashQuery('lakers');
      expect(reloaded).not.toBe(first);
      expect(setItemSpy).not.toHaveBeenCalled();
      expect(store.has(SALT_STORAGE_KEY)).toBe(false);
    }
  });

  it('persists one random salt in localStorage when consent is "all" or "analytics" and survives reload', () => {
    for (const consentLevel of ['all', 'analytics'] as const) {
      _resetBrowserQuerySaltForTests();
      const store = installMockLocalStorage({ [CONSENT_STORAGE_KEY]: consentLevel });
      const first = hashQuery('lakers');
      const persisted = store.get(SALT_STORAGE_KEY);
      expect(persisted).toMatch(/^[0-9a-z]{12,64}$/);
      expect(first).toMatch(/^[0-9a-f]{16}$/);
      expect(hashQuery('lakers')).toBe(first);

      // Simulate reload in the same browser (module cache cleared, localStorage kept).
      _resetBrowserQuerySaltForTests();
      expect(hashQuery('lakers')).toBe(first);
      expect(store.get(SALT_STORAGE_KEY)).toBe(persisted);
    }
  });

  it('promotes the in-page salt into localStorage cleanly if the visitor later chooses Allow', () => {
    const store = installMockLocalStorage();
    const beforeAllow = hashQuery('lakers');
    expect(store.has(SALT_STORAGE_KEY)).toBe(false);

    store.set(CONSENT_STORAGE_KEY, 'all');
    const afterAllowSamePage = hashQuery('lakers');
    expect(afterAllowSamePage).toBe(beforeAllow);
    expect(store.get(SALT_STORAGE_KEY)).toMatch(/^[0-9a-z]{12,64}$/);

    _resetBrowserQuerySaltForTests();
    expect(hashQuery('lakers')).toBe(beforeAllow);
  });

  it('normalizes trim + case identically within one browser and never leaks salt or raw query', () => {
    const store = installMockLocalStorage({ [CONSENT_STORAGE_KEY]: 'all' });
    const canonical = hashQuery('Lakers');
    for (const variant of ['lakers', '  lakers  ', 'LAKERS', '\tLakers\n']) {
      expect(hashQuery(variant)).toBe(canonical);
    }
    const salt = store.get(SALT_STORAGE_KEY)!;
    const evt = sanitizeEvent('search_submit', { query: 'Lakers' });
    expect(evt).not.toBeNull();
    expect(evt!.params.query_hash).toBe(canonical);
    const serialized = JSON.stringify(evt);
    expect(serialized).not.toContain('Lakers');
    expect(serialized).not.toContain(salt);
  });

  it('falls back cleanly to an in-memory salt when localStorage throws', () => {
    (globalThis as { window?: unknown }).window = {
      localStorage: {
        getItem: () => {
          throw new Error('SecurityError');
        },
        setItem: () => {
          throw new Error('SecurityError');
        },
      },
    };
    const h = hashQuery('lakers');
    expect(h).toMatch(/^[0-9a-f]{16}$/);
    expect(hashQuery('LAKERS')).toBe(h);
  });
});
