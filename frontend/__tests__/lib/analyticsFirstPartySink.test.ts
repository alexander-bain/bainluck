/**
 * LAT-P232 (#2751) — the felt number gets a transport this lane can read.
 *
 * `first_card_ms` is computed on every screen arrival and thrown away, because
 * its only transport is gtag and this lane holds no GA credential. These tests
 * pin the mirror that gives it a first-party sink, and — more importantly — pin
 * the three properties that make it NOT new collection:
 *
 *   1. it forwards only the three performance event names;
 *   2. it fires only for a reader who has granted consent, on the same packet
 *      gtag receives, AFTER the sanitizer;
 *   3. a revoke inside the coalescing window drops what is queued.
 *
 * If any of those three stops holding, the privacy claim in
 * `app/utils/client_timing_contract.py` becomes false and this stops being
 * Stage 1.
 *
 * No jsdom in this repo, so this drives the real modules against a fake
 * window/document/gtag/fetch, exactly as `analyticsTelemetryRevoke.test.ts` does.
 */

export {}; // ensure module scope

type GtagCall = unknown[];
type Posted = { url: string; init: Record<string, unknown> };

interface Harness {
  core: typeof import('@/lib/analytics/core');
  consent: typeof import('@/lib/analytics/telemetryConsent');
  revoke: typeof import('@/lib/analytics/telemetryRevoke');
  sink: typeof import('@/lib/analytics/firstPartySink');
  gtagCalls: GtagCall[];
  posts: Posted[];
  timers: Array<() => void>;
  runTimers: () => void;
  bodies: () => Array<{ events: Array<{ name: string; params: Record<string, unknown> }> }>;
  allPacketNames: () => string[];
}

const ORIGINAL_GA = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
const ORIGINAL_API = process.env.NEXT_PUBLIC_API_URL;

function setup(opts: { stored?: 'all' | 'analytics' | 'none' } = {}): Harness {
  const { stored } = opts;
  jest.resetModules();
  process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST232';
  process.env.NEXT_PUBLIC_API_URL = 'https://api.test';

  const store: Record<string, string> = {};
  if (stored) store['bainluck_consent'] = stored;

  const gtagCalls: GtagCall[] = [];
  const posts: Posted[] = [];
  const timers: Array<() => void> = [];

  const listeners: Record<string, Array<() => void>> = {};
  const addListener = (name: string, fn: () => void) => {
    (listeners[name] ||= []).push(fn);
  };

  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag: (...args: unknown[]) => gtagCalls.push(args),
    navigator: { userAgent: 'node' },
    location: { href: 'http://localhost/', pathname: '/' },
    addEventListener: addListener,
  };
  (global as unknown as { localStorage: unknown }).localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
  };
  (global as unknown as { document: unknown }).document = {
    title: 'T',
    referrer: '',
    visibilityState: 'visible',
    addEventListener: addListener,
  };

  // Deterministic timers: the sink coalesces on a setTimeout, and a real one
  // would make every assertion below a race.
  (global as unknown as { setTimeout: unknown }).setTimeout = (fn: () => void) => {
    timers.push(fn);
    return timers.length;
  };
  (global as unknown as { clearTimeout: unknown }).clearTimeout = (id: number) => {
    if (typeof id === 'number' && timers[id - 1]) timers[id - 1] = () => {};
  };

  (global as unknown as { fetch: unknown }).fetch = (
    url: string,
    init: Record<string, unknown>,
  ) => {
    posts.push({ url, init });
    return Promise.resolve({ ok: true });
  };

  const core = require('@/lib/analytics/core') as Harness['core'];
  const consent = require('@/lib/analytics/telemetryConsent') as Harness['consent'];
  const revoke = require('@/lib/analytics/telemetryRevoke') as Harness['revoke'];
  const sink = require('@/lib/analytics/firstPartySink') as Harness['sink'];

  const h: Harness = {
    core,
    consent,
    revoke,
    sink,
    gtagCalls,
    posts,
    timers,
    runTimers: () => {
      const pending = timers.splice(0, timers.length);
      pending.forEach((fn) => fn());
    },
    bodies: () =>
      posts.map((p) => JSON.parse(p.init.body as string)),
    allPacketNames: () =>
      h.bodies().flatMap((b) => b.events.map((e) => e.name)),
  };
  return h;
}

function grant(h: Harness): void {
  h.core.initializeAnalytics();
  h.consent.initTelemetryConsent();
}

/**
 * Typed as the real `ScreenTimingParams` rather than an inferred literal, so
 * this fixture cannot drift into a shape the app never actually emits — a test
 * that passes on a packet the taxonomy would reject proves nothing.
 */
const SCREEN_TIMING: import('@/lib/analytics/types').ScreenTimingParams = {
  surface: 'discover',
  entry: 'cold',
  shell_ms: 210,
  first_card_ms: 1480,
  fold_ms: 1900,
  interactive_ms: 2300,
  card_count: 12,
  device_class: 'phone',
  network_class: '4g',
  app_build: 'abc1234',
  outcome_class: 'ok',
};

afterEach(() => {
  if (ORIGINAL_GA === undefined) delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  else process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = ORIGINAL_GA;
  if (ORIGINAL_API === undefined) delete process.env.NEXT_PUBLIC_API_URL;
  else process.env.NEXT_PUBLIC_API_URL = ORIGINAL_API;
});

// ============================================================================
// The ship: the needle reaches a sink we can read
// ============================================================================

describe('the felt number reaches a first-party sink', () => {
  it('mirrors first_card_ms to the ingest endpoint', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);

    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    h.runTimers();

    expect(h.posts).toHaveLength(1);
    expect(h.posts[0].url).toBe('https://api.test/api/telemetry/client-timing');

    const body = h.bodies()[0];
    expect(body.events).toHaveLength(1);
    expect(body.events[0].name).toBe('screen_timing');
    expect(body.events[0].params.first_card_ms).toBe(1480);
  });

  it('sends the SANITIZED packet — the same object gtag got, not the raw params', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);

    h.core.trackEvent(
      'screen_timing',
      { ...SCREEN_TIMING, sneaky_extra: 'should-never-appear' } as never,
      { immediate: true },
    );
    h.runTimers();

    const mirrored = h.bodies()[0].events[0].params;
    const toGtag = h.gtagCalls.find((c) => c[0] === 'event' && c[1] === 'screen_timing');
    expect(toGtag).toBeDefined();
    expect(mirrored).toEqual(toGtag![2]);
    expect(mirrored).not.toHaveProperty('sneaky_extra');
  });

  it('strips the enrichment keys, so no session marker reaches the sink', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);

    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    h.runTimers();

    const params = h.bodies()[0].events[0].params;
    expect(params).not.toHaveProperty('session_id');
    expect(params).not.toHaveProperty('platform');
    expect(params).not.toHaveProperty('event_timestamp');
  });
});

// ============================================================================
// Not new collection
// ============================================================================

describe('the mirror collects nothing that GA is not already getting', () => {
  it('sends NOTHING when consent was never granted', () => {
    const h = setup({ stored: 'none' });
    grant(h);

    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    h.runTimers();

    expect(h.gtagCalls.filter((c) => c[0] === 'event')).toHaveLength(0);
    expect(h.posts).toHaveLength(0);
  });

  it('sends nothing after a revoke, even though window.fetch still exists', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);
    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    h.runTimers();
    expect(h.posts).toHaveLength(1);

    h.revoke.applyTelemetryChange('none', { reload: () => {}, gaConfigured: true });

    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    h.runTimers();
    expect(h.posts).toHaveLength(1); // still just the pre-revoke one
  });

  it('DROPS a packet queued before a revoke that lands inside the flush window', () => {
    // The queue can hold a packet for FLUSH_DELAY_MS. That window is exactly
    // the gap a revoke has to win, and it is the one this mirror ADDS — gtag
    // received its copy synchronously, so only the mirror can be caught here.
    const h = setup({ stored: 'analytics' });
    grant(h);

    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    expect(h.sink.pendingFirstPartyMirrorCount()).toBe(1);
    expect(h.posts).toHaveLength(0); // still coalescing

    h.revoke.applyTelemetryChange('none', { reload: () => {}, gaConfigured: true });

    expect(h.sink.pendingFirstPartyMirrorCount()).toBe(0);
    h.runTimers();
    expect(h.posts).toHaveLength(0);
  });

  it('does not send cookies with the beacon', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);
    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    h.runTimers();
    expect(h.posts[0].init.credentials).toBe('omit');
    expect(h.posts[0].init.keepalive).toBe(true);
  });
});

// ============================================================================
// The name allowlist
// ============================================================================

describe('only the three performance events are mirrored', () => {
  it('mirrors screen_timing, feed_telemetry and web_vital', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);

    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    h.core.trackEvent(
      'feed_telemetry',
      { endpoint: '/api/feed', cohort: 'a', cache_status: 'miss', duration_ms: 300 } as never,
      { immediate: true },
    );
    h.core.trackEvent(
      'web_vital',
      { metric_name: 'LCP', metric_value: 2100, page_path: '/' } as never,
      { immediate: true },
    );
    h.runTimers();

    expect(new Set(h.allPacketNames())).toEqual(
      new Set(['screen_timing', 'feed_telemetry', 'web_vital']),
    );
  });

  it('does NOT mirror a content-carrying event, however legitimate', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);

    h.core.trackEvent(
      'chart_view',
      {
        chart_type: 'probability_trend',
        event_id: 42,
        has_data: true,
        data_points_count: 100,
        bookmaker_count: 5,
        data_span_hours: 24,
      },
      { immediate: true },
    );
    h.core.trackEvent('search_opened', { source: 'header' } as never, { immediate: true });
    h.runTimers();

    // gtag still got them — the mirror is narrower than the rail, by design.
    expect(h.gtagCalls.filter((c) => c[0] === 'event').length).toBeGreaterThan(0);
    expect(h.posts).toHaveLength(0);
  });

  it('does not mirror feed_exit, which keeps its session marker', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);
    h.core.trackEvent(
      'feed_exit',
      {
        last_position: 4,
        visible_count: 9,
        max_scroll_depth: 60,
        dwell_ms: 8000,
        terminal_state: 'hidden',
      } as never,
      { immediate: true },
    );
    h.runTimers();
    expect(h.posts).toHaveLength(0);
  });
});

// ============================================================================
// Batching — the mirror must not compete with the page for rate budget
// ============================================================================

describe('packets are coalesced into one request', () => {
  it('collapses a screen arrival into a single POST', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);

    h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    for (const metric of ['LCP', 'INP', 'CLS', 'TTFB', 'FCP']) {
      h.core.trackEvent(
        'web_vital',
        { metric_name: metric, metric_value: 10, page_path: '/' } as never,
        { immediate: true },
      );
    }
    h.runTimers();

    // Six packets, ONE request against the reader's 60/min budget.
    expect(h.posts).toHaveLength(1);
    expect(h.bodies()[0].events).toHaveLength(6);
  });

  it('flushes immediately at the batch cap rather than overflowing it', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);

    for (let i = 0; i < h.sink.MAX_BATCH; i += 1) {
      h.core.trackEvent('screen_timing', SCREEN_TIMING, { immediate: true });
    }

    // Sent without waiting for the timer, and never larger than the server's cap.
    expect(h.posts).toHaveLength(1);
    expect(h.bodies()[0].events).toHaveLength(h.sink.MAX_BATCH);
    expect(h.sink.pendingFirstPartyMirrorCount()).toBe(0);
  });

  it('never posts an empty batch', () => {
    const h = setup({ stored: 'analytics' });
    grant(h);
    h.sink.flushFirstPartySink();
    h.runTimers();
    expect(h.posts).toHaveLength(0);
  });
});
