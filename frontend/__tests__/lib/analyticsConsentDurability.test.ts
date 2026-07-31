/**
 * L2-222 Item 1 (#1453) — consent that is DURABLE, SYNCHRONIZED, and enforced
 * at execution time.
 *
 * L2-219/L2-220 made every provider mount through one gate and made a revoke
 * truthful on the page you are looking at. Three holes survived, and each one
 * has the same shape: the code checked something at the wrong moment.
 *
 *   1. **The write was never verified.** `storeConsent` swallowed every
 *      failure, so a no-op localStorage looked exactly like a successful save —
 *      and the revoke path would then hard-reload into the OLD grant, silently
 *      re-enabling what the user just switched off.
 *   2. **The gate was read when an event was QUEUED, not when it was SENT.**
 *      `requestIdleCallback` can fire 2s later; a revoke inside that window lost.
 *   3. **Identity writes skipped the gate entirely.** `setUserId` /
 *      `setUserProperties` are the most identifying calls the rail makes and
 *      were the only ones consent could not stop.
 *
 * Plus the cross-tab case, which had no handling at all: two tabs share one
 * store, so revoking in tab B left tab A running every provider.
 *
 * No jsdom in this repo, so these drive the real modules against a fake
 * window/gtag/localStorage with injected timers and reload spies.
 */

export {}; // ensure module scope

type GtagCall = unknown[];

interface StorageBehavior {
  /** `setItem` throws (Safari private mode / quota). */
  throwOnSet?: boolean;
  /** `setItem` silently does nothing (a shim). */
  noopSet?: boolean;
  /** `getItem` throws. */
  throwOnGet?: boolean;
  /** What `getItem` returns instead of the real store, if anything. */
  readbackOverride?: () => string | null;
}

interface Harness {
  consent: typeof import('@/lib/analytics/telemetryConsent');
  revoke: typeof import('@/lib/analytics/telemetryRevoke');
  core: typeof import('@/lib/analytics/core');
  calls: GtagCall[];
  store: Record<string, string>;
  reloads: number;
  reload: () => void;
  eventCalls: () => GtagCall[];
  /** Run every pending idle callback, oldest first. */
  runIdle: () => void;
  pendingIdle: () => number;
}

const ORIGINAL_ENV = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;

function setup(
  opts: {
    stored?: 'all' | 'analytics' | 'none';
    configured?: boolean;
    storage?: StorageBehavior;
  } = {},
): Harness {
  const { stored, configured = true, storage = {} } = opts;
  jest.resetModules();
  if (configured) {
    process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST123';
  } else {
    delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  }

  const store: Record<string, string> = {};
  if (stored) store['bainluck_consent'] = stored;
  const calls: GtagCall[] = [];

  // A controllable idle queue, so "revoked before the idle callback ran" is a
  // deterministic assertion rather than a race.
  const idleQueue = new Map<number, () => void>();
  let nextIdleHandle = 1;

  (global as unknown as { window: unknown }).window = {
    dataLayer: [],
    gtag: (...args: unknown[]) => calls.push(args),
    navigator: { userAgent: 'node' },
    location: { href: 'http://localhost/', pathname: '/' },
    cancelIdleCallback: (h: number) => idleQueue.delete(h),
  };
  (global as unknown as { requestIdleCallback: unknown }).requestIdleCallback = (
    fn: () => void,
  ) => {
    const handle = nextIdleHandle++;
    idleQueue.set(handle, fn);
    return handle;
  };
  (global as unknown as { cancelIdleCallback: unknown }).cancelIdleCallback = (h: number) =>
    idleQueue.delete(h);

  (global as unknown as { localStorage: unknown }).localStorage = {
    getItem: (k: string) => {
      if (storage.throwOnGet) throw new Error('storage read blocked');
      if (storage.readbackOverride && k === 'bainluck_consent') {
        return storage.readbackOverride();
      }
      return k in store ? store[k] : null;
    },
    setItem: (k: string, v: string) => {
      if (storage.throwOnSet) throw new Error('QuotaExceededError');
      if (storage.noopSet) return;
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
  };
  (global as unknown as { document: unknown }).document = { title: 'T', referrer: '' };

  const core = require('@/lib/analytics/core') as Harness['core'];
  const consent = require('@/lib/analytics/telemetryConsent') as Harness['consent'];
  const revoke = require('@/lib/analytics/telemetryRevoke') as Harness['revoke'];

  const h: Harness = {
    consent,
    revoke,
    core,
    calls,
    store,
    reloads: 0,
    reload: () => {
      h.reloads += 1;
    },
    eventCalls: () => calls.filter((c) => c[0] === 'event'),
    runIdle: () => {
      for (const fn of Array.from(idleQueue.values())) fn();
      idleQueue.clear();
    },
    pendingIdle: () => idleQueue.size,
  };
  core.initializeAnalytics();
  return h;
}

afterEach(() => {
  if (ORIGINAL_ENV === undefined) delete process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  else process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = ORIGINAL_ENV;
  delete (global as unknown as { window?: unknown }).window;
  delete (global as unknown as { localStorage?: unknown }).localStorage;
  delete (global as unknown as { document?: unknown }).document;
  delete (global as unknown as { requestIdleCallback?: unknown }).requestIdleCallback;
  delete (global as unknown as { cancelIdleCallback?: unknown }).cancelIdleCallback;
});

// ============================================================================
// 1. Verified persistence — no claim without an exact readback
// ============================================================================

describe('durable consent: only claim saved after exact readback', () => {
  it('reports saved when the value reads back exactly', () => {
    const h = setup();
    expect(h.consent.setTelemetryConsent('analytics')).toBe('saved');
    expect(h.consent.getConsentPersistence()).toBe('saved');
    expect(h.store['bainluck_consent']).toBe('analytics');
  });

  it('reports unavailable when setItem THROWS (private mode / quota)', () => {
    const h = setup({ storage: { throwOnSet: true } });
    expect(h.consent.setTelemetryConsent('none')).toBe('unavailable');
    expect(h.consent.getConsentPersistence()).toBe('unavailable');
  });

  it('reports unavailable when setItem is a silent NO-OP', () => {
    // The dangerous case: no throw, nothing stored. Indistinguishable from
    // success without a readback — which is exactly why we do one.
    const h = setup({ storage: { noopSet: true } });
    expect(h.consent.setTelemetryConsent('none')).toBe('unavailable');
    expect(h.store['bainluck_consent']).toBeUndefined();
  });

  it('reports unavailable when the readback returns a STALE prior value', () => {
    const h = setup({
      stored: 'all',
      storage: { noopSet: true, readbackOverride: () => 'all' },
    });
    // Writing 'none' "succeeds" and reads back 'all' — a lie that only an exact
    // comparison catches. A `!== null` check would have passed here.
    expect(h.consent.setTelemetryConsent('none')).toBe('unavailable');
  });

  it('reports unavailable when the readback itself throws', () => {
    const h = setup({ storage: { throwOnGet: true } });
    expect(h.consent.setTelemetryConsent('none')).toBe('unavailable');
  });

  it('applies the denial in-memory even when it cannot be persisted', () => {
    // A browser that will not remember a denial must still honour it NOW.
    const h = setup({ storage: { throwOnSet: true } });
    h.consent.setTelemetryConsent('none');
    expect(h.core.isConsentGranted()).toBe(false);
    expect(h.consent.getTelemetryDecision()).toEqual({
      googleAnalytics: false,
      vercelAnalytics: false,
      speedInsights: false,
      webVitals: false,
    });
  });

  it('a choice hydrated OUT of storage is durable by definition', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    expect(h.consent.getConsentPersistence()).toBe('saved');
  });

  it('persistence is unknown before any explicit choice', () => {
    const h = setup();
    h.consent.initTelemetryConsent();
    expect(h.consent.getConsentPersistence()).toBe('unknown');
  });
});

describe('durable consent: an unverifiable denial must NOT reload', () => {
  it('reloads a live→dead revoke when the denial verifiably persisted', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    const plan = h.revoke.applyTelemetryChange('none', { reload: h.reload });
    expect(plan.requiresReload).toBe(true);
    expect(plan.persistence).toBe('saved');
    expect(plan.reloaded).toBe(true);
    expect(h.reloads).toBe(1);
  });

  it('does NOT reload when the denial could not be persisted', () => {
    // Reloading here would re-read the stored GRANT and come back up with every
    // provider running — strictly worse than staying put with a closed gate.
    const h = setup({ stored: 'analytics', storage: { throwOnSet: true } });
    h.consent.initTelemetryConsent();
    const plan = h.revoke.applyTelemetryChange('none', { reload: h.reload });
    expect(plan.requiresReload).toBe(true);
    expect(plan.persistence).toBe('unavailable');
    expect(plan.reloaded).toBe(false);
    expect(h.reloads).toBe(0);
    // …and the in-document denial is still in force.
    expect(h.core.isConsentGranted()).toBe(false);
  });

  it('a grant never reloads, verified or not', () => {
    const h = setup({ storage: { noopSet: true } });
    h.consent.initTelemetryConsent();
    const plan = h.revoke.applyTelemetryChange('analytics', { reload: h.reload });
    expect(plan.reloaded).toBe(false);
    expect(h.reloads).toBe(0);
  });
});

// ============================================================================
// 2. Execution-time gate — admit, then revoke before the idle callback fires
// ============================================================================

describe('execution-time consent: deferred sends re-check the gate', () => {
  it('admit-then-revoke-before-idle emits NOTHING', () => {
    const h = setup();
    h.consent.setTelemetryConsent('analytics');
    const before = h.eventCalls().length;

    h.core.trackEvent('chart_view', { chart_type: 'probability', has_data: true });
    expect(h.core.pendingDeferredSendCount()).toBe(1);

    // The user revokes inside the idle window.
    h.consent.setTelemetryConsent('none');
    // Denial cancelled the pending send outright…
    expect(h.core.pendingDeferredSendCount()).toBe(0);

    // …and even if the environment runs it anyway, the in-callback re-check
    // refuses. Both guards are asserted, because cancelIdleCallback is not
    // universally available.
    h.runIdle();
    expect(h.eventCalls().length).toBe(before);
  });

  it('an event queued under a grant DOES send if consent still holds', () => {
    const h = setup();
    h.consent.setTelemetryConsent('analytics');
    const before = h.eventCalls().length;

    h.core.trackEvent('chart_view', { chart_type: 'probability', has_data: true });
    h.runIdle();
    expect(h.eventCalls().length).toBe(before + 1);
    expect(h.core.pendingDeferredSendCount()).toBe(0);
  });

  it('the pending set does not grow unbounded across a session', () => {
    const h = setup();
    h.consent.setTelemetryConsent('analytics');
    for (let i = 0; i < 5; i++) {
      h.core.trackEvent('chart_view', { chart_type: 'probability', has_data: true });
    }
    expect(h.core.pendingDeferredSendCount()).toBe(5);
    h.runIdle();
    expect(h.core.pendingDeferredSendCount()).toBe(0);
  });
});

// ============================================================================
// 3. Identity writes are gated, and cleared in the right order
// ============================================================================

describe('identity writes are consent-gated', () => {
  const configCalls = (h: Harness) =>
    h.calls.filter((c) => c[0] === 'config' && typeof c[2] === 'object');
  const userIdWrites = (h: Harness) =>
    configCalls(h).filter((c) => 'user_id' in (c[2] as Record<string, unknown>));

  it('setUserId after a denial writes nothing', () => {
    const h = setup();
    h.consent.setTelemetryConsent('none');
    const before = userIdWrites(h).length;
    h.core.setUserId('firebase-uid-123');
    expect(userIdWrites(h).length).toBe(before);
    expect(h.core.getUserId()).toBeUndefined();
  });

  it('setUserProperties after a denial writes nothing', () => {
    const h = setup();
    h.consent.setTelemetryConsent('none');
    const before = h.calls.filter((c) => c[1] === 'user_properties').length;
    h.core.setUserProperties({ login_status: 'logged_in' });
    expect(h.calls.filter((c) => c[1] === 'user_properties').length).toBe(before);
  });

  it('setUserId works under a grant', () => {
    const h = setup();
    h.consent.setTelemetryConsent('analytics');
    h.core.setUserId('firebase-uid-123');
    const last = userIdWrites(h).pop() as GtagCall;
    expect((last[2] as Record<string, unknown>).user_id).toBe('firebase-uid-123');
  });

  it('CLEARING an id is always allowed — consent must not block removal', () => {
    const h = setup();
    h.consent.setTelemetryConsent('none');
    const before = userIdWrites(h).length;
    h.core.setUserId(undefined);
    const after = userIdWrites(h);
    expect(after.length).toBe(before + 1);
    expect((after[after.length - 1][2] as Record<string, unknown>).user_id).toBeNull();
  });

  it('a revoke clears a previously-set id, BEFORE the gate closes', () => {
    const h = setup();
    h.consent.setTelemetryConsent('analytics');
    h.core.setUserId('firebase-uid-123');

    const beforeIdx = h.calls.length;
    h.consent.setTelemetryConsent('none');

    const during = h.calls.slice(beforeIdx);
    const cleared = during.find(
      (c) =>
        c[0] === 'config' &&
        typeof c[2] === 'object' &&
        (c[2] as Record<string, unknown>).user_id === null,
    );
    expect(cleared).toBeDefined();
    expect(h.core.getUserId()).toBeUndefined();

    // Ordering: the identity clear precedes the Consent Mode denial push. A
    // clear issued after the gate closed would be refused, leaving the id
    // configured in gtag for the life of the document.
    const clearIdx = during.indexOf(cleared as GtagCall);
    const denyIdx = during.findIndex((c) => c[0] === 'consent' && c[1] === 'update');
    expect(clearIdx).toBeGreaterThanOrEqual(0);
    expect(denyIdx).toBeGreaterThanOrEqual(0);
    expect(clearIdx).toBeLessThan(denyIdx);
  });

  it('a denial with no id set does not push a pointless config', () => {
    const h = setup();
    const before = userIdWrites(h).length;
    h.consent.setTelemetryConsent('none');
    expect(userIdWrites(h).length).toBe(before);
  });
});

// ============================================================================
// 4. Cross-tab synchronization
// ============================================================================

describe('cross-tab consent', () => {
  it('two-tab grant→revoke closes this tab and asks for a reload', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    expect(h.core.isConsentGranted()).toBe(true);

    // Tab B writes the denial; this tab sees a storage event.
    h.store['bainluck_consent'] = 'none';
    const outcome = h.consent.handleExternalConsentChange('bainluck_consent', 'none');

    expect(outcome).toBe('applied_requires_reload');
    // The gate closed IMMEDIATELY — it does not wait for the reload.
    expect(h.core.isConsentGranted()).toBe(false);
    expect(h.consent.getTelemetryConsent()).toBe('none');
  });

  it('adopts an external GRANT without a reload', () => {
    const h = setup({ stored: 'none' });
    h.consent.initTelemetryConsent();
    h.store['bainluck_consent'] = 'analytics';
    expect(h.consent.handleExternalConsentChange('bainluck_consent', 'analytics')).toBe(
      'applied',
    );
    expect(h.core.isConsentGranted()).toBe(true);
  });

  it('ignores a SAME-VALUE event — the loop guard', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    let notified = 0;
    h.consent.subscribeTelemetryConsent(() => {
      notified += 1;
    });
    expect(h.consent.handleExternalConsentChange('bainluck_consent', 'analytics')).toBe(
      'ignored',
    );
    expect(notified).toBe(0);
  });

  it('ignores an INVALID value rather than coercing it', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    for (const bad of ['yes', '', 'ALL', '{"level":"none"}', null]) {
      expect(h.consent.handleExternalConsentChange('bainluck_consent', bad)).toBe('ignored');
    }
    // Untouched: coercing garbage to a denial would flip a grant the user never
    // revoked; coercing it to a grant would be worse.
    expect(h.consent.getTelemetryConsent()).toBe('analytics');
    expect(h.core.isConsentGranted()).toBe(true);
  });

  it('ignores events for OTHER keys', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    expect(h.consent.handleExternalConsentChange('bainluck_last_visit', 'none')).toBe(
      'ignored',
    );
    expect(h.consent.getTelemetryConsent()).toBe('analytics');
  });

  it('never writes back to storage — nothing can ping-pong', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    let sets = 0;
    const real = (global as unknown as { localStorage: Storage }).localStorage;
    (global as unknown as { localStorage: unknown }).localStorage = {
      ...real,
      getItem: (k: string) => real.getItem(k),
      setItem: (k: string, v: string) => {
        sets += 1;
        real.setItem(k, v);
      },
    };
    h.store['bainluck_consent'] = 'none';
    h.consent.handleExternalConsentChange('bainluck_consent', 'none');
    expect(sets).toBe(0);
  });

  it('does NOT reload when the stored value does not confirm the denial', () => {
    // A storage event we cannot corroborate (raced write, cleared store): adopt
    // the denial in-memory, but do not reload onto an unconfirmed state.
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();
    // The event says 'none' but the store still says 'analytics'.
    const outcome = h.consent.handleExternalConsentChange('bainluck_consent', 'none');
    expect(outcome).toBe('applied');
    expect(h.core.isConsentGranted()).toBe(false);
  });

  it('the storage listener reloads exactly once and can be removed', () => {
    const h = setup({ stored: 'analytics' });
    h.consent.initTelemetryConsent();

    const handlers: Array<(e: StorageEvent) => void> = [];
    const stop = h.consent.startTelemetryConsentSync({
      addEventListener: (_t, fn) => handlers.push(fn),
      removeEventListener: (_t, fn) => {
        const i = handlers.indexOf(fn);
        if (i >= 0) handlers.splice(i, 1);
      },
      reload: h.reload,
    });

    h.store['bainluck_consent'] = 'none';
    handlers.forEach((fn) =>
      fn({ key: 'bainluck_consent', newValue: 'none' } as StorageEvent),
    );
    expect(h.reloads).toBe(1);

    // A repeat of the same event is now a no-op — no reload loop.
    handlers.forEach((fn) =>
      fn({ key: 'bainluck_consent', newValue: 'none' } as StorageEvent),
    );
    expect(h.reloads).toBe(1);

    stop();
    expect(handlers.length).toBe(0);
  });
});

// ============================================================================
// 5. Standing invariants this queue must not disturb
// ============================================================================

describe('invariants', () => {
  it('every ads state stays denied on every grant level', () => {
    for (const level of ['all', 'analytics', 'none'] as const) {
      const h = setup();
      h.consent.setTelemetryConsent(level);
      const updates = h.calls.filter((c) => c[0] === 'consent' && c[1] === 'update');
      expect(updates.length).toBeGreaterThan(0);
      for (const u of updates) {
        const s = u[2] as Record<string, string>;
        expect(s.ad_storage).toBe('denied');
        expect(s.ad_user_data).toBe('denied');
        expect(s.ad_personalization).toBe('denied');
      }
    }
  });

  it('a grant still flushes exactly one withheld page view', () => {
    const h = setup();
    h.core.trackPageView({ page_type: 'discover', page_path: '/', page_title: 'Home' });
    expect(h.core.peekWithheldPageView()).not.toBeNull();
    h.consent.setTelemetryConsent('analytics');
    const views = h
      .eventCalls()
      .filter((c) => c[1] === 'page_view');
    expect(views.length).toBe(1);
    expect(h.core.peekWithheldPageView()).toBeNull();
  });

  it('a denial discards the withheld page view', () => {
    const h = setup();
    h.core.trackPageView({ page_type: 'discover', page_path: '/', page_title: 'Home' });
    h.consent.setTelemetryConsent('none');
    expect(h.core.peekWithheldPageView()).toBeNull();
    expect(h.eventCalls().filter((c) => c[1] === 'page_view').length).toBe(0);
  });
});
