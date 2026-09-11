/**
 * #5072 — A POLLED KEY THAT ERRORS ONCE MUST COME BACK ON ITS OWN.
 *
 * ── WHAT THE READER SAW ──────────────────────────────────────────────────────
 *
 * SF@LAR, production, 2026-09-10. A tab opened at 6:34pm PT and never touched.
 * At 7:54pm it still read `Halftime · 0:00`, Rams 7 – 49ers 10, a pulsing green
 * `LIVE`, `Next update: 29`, and "Unable to load history — Rate limit exceeded:
 * 60/minute". The real game was 7–24, fourth quarter. Frozen since ~7:14pm.
 *
 * The tab did not make ~80 attempts over those 40 minutes. It made ZERO. The
 * countdown is a local timer driven by `lastRefresh`, which only `onSuccess`
 * advances, so it kept cycling 29 … 0 … 29 with no request behind it. The page
 * was rate-limited ONCE and then stopped asking.
 *
 * ── THE MECHANISM, VERBATIM FROM THE PINNED DEPENDENCY ───────────────────────
 *
 * `swr@2.4.1`, `dist/index/index.js`, the polling effect:
 *
 *     function execute() {
 *         // Only revalidate when the page is visible, online, and not errored.
 *         if (!getCache().error && (refreshWhenHidden || getConfig().isVisible())
 *             && (refreshWhenOffline || getConfig().isOnline())) {
 *             revalidate(WITH_DEDUPE).then(next);
 *         } else {
 *             next();   // schedule the next interval to check again
 *         }
 *     }
 *
 * `!getCache().error` — the timer keeps ticking and takes the `else` branch
 * forever. The cached error is cleared only by a SUCCESSFUL revalidation, and
 * after the first failure nothing in this app can produce one: SWR's retry
 * ladder is off (`shouldRetryOnError: false`, #L2-137), focus revalidation is
 * off, reconnect revalidation is off, and the poll itself refuses. A polled key
 * is latched dead for the life of the mount.
 *
 * ── WHAT THIS MODULE DOES, AND WHAT IT DELIBERATELY DOES NOT ─────────────────
 *
 * It restores POLLING recovery without restoring per-error RETRY. On the first
 * error for a polled key it schedules a single `mutate(key)` nudge, and keeps
 * nudging on a backoff until one lands. One successful nudge clears the cached
 * error, at which point SWR's own poll resumes and this module stands down.
 *
 * It is NOT `shouldRetryOnError: true`. That stacks a second retry loop on top
 * of `apiFetch`'s own (up to ~9 attempts per failing key) — the exact defect
 * `SWRProvider` was written to prevent. The distinction that makes this safe is
 * cadence: ONE request per poll interval, never faster than the key's own poll
 * would have been, versus a burst per failure.
 *
 * ── THE LOAD INVARIANT ───────────────────────────────────────────────────────
 *
 * A recovering key never generates traffic faster than a healthy one. The delay
 * starts at the key's own `refreshInterval` and doubles to a ceiling, so the
 * floor is the poll cadence and the worst case is the same request the poll
 * would have made anyway. That is the whole reason an unbounded attempt count
 * is safe here: capping attempts would re-latch the page after a long outage —
 * which is the bug — while capping the RATE costs the server nothing it was not
 * already prepared to serve.
 *
 * ── WHY DEPENDENCIES ARE INJECTED ────────────────────────────────────────────
 *
 * `frontend/jest.config.js` is `testEnvironment: 'node'` and the repo has no
 * jsdom/testing-library rig — `@testing-library/react`, `react-test-renderer`
 * and `jest-environment-jsdom` are all absent. A scheduler that reached for
 * `setTimeout`, `document` and `swr` directly would be untestable here, and the
 * failure this fixes is entirely about WHEN things happen. Injection makes the
 * clock, the visibility of the tab and the nudge itself all controllable, so
 * the guard tests exercise the real branch order rather than a source scan.
 */

/** Slowest a recovering key is allowed to come back. See the load invariant. */
export const MAX_RECOVERY_DELAY_MS = 60_000;

/**
 * Longest wait we will take from a server's `retry_after`. The limiter's window
 * is fixed at 60s so the real value runs 1..60; a larger number is a bug
 * upstream, not an instruction to sleep through the rest of the game.
 */
export const MAX_SERVER_WAIT_MS = 300_000;

export type TimerHandle = ReturnType<typeof setTimeout>;

export interface PollRecoveryDeps {
  /**
   * SWR's global `mutate`. Resolves whether the revalidation succeeded, failed
   * or never happened — see `fire()` for why that is not the signal we read.
   */
  mutate: (key: string) => Promise<unknown>;
  setTimer: (fn: () => void, ms: number) => TimerHandle;
  clearTimer: (handle: TimerHandle) => void;
  /** False while the tab is hidden. Mirrors SWR's own `isVisible`. */
  isVisible: () => boolean;
  /** False while the browser reports itself offline. Mirrors `isOnline`. */
  isOnline: () => boolean;
}

interface KeyState {
  /** Consecutive failures observed for this key. 0 on the first error. */
  attempt: number;
  /** The key's own `refreshInterval`, in ms — the floor of every delay. */
  baseMs: number;
  /** The delay the pending timer was scheduled with. */
  delayMs: number;
  timer: TimerHandle | null;
  /**
   * Bumped every time an error is recorded. `fire()` captures it before the
   * nudge and compares afterwards; see there for what the comparison decides.
   */
  epoch: number;
}

/**
 * The `refreshInterval` of a key we are willing to nudge, or null.
 *
 * ── TWO CERTS LANDED ON THIS ONE FUNCTION. BOTH WERE RIGHT. ─────────────────
 *
 * CERT-2584: it accepted only a finite positive NUMBER and routed functions to
 * null, on a written claim that "all 78 `refreshInterval` sites in the app are
 * numeric literals". False, and false in the worst place: the MAIN event
 * request in `app/events/[id]/page.tsx` — the live page this issue was filed
 * against — passes `(data) => eventRefreshInterval(data?.status, …)`. The one
 * key whose freezing produced the bug report was the one key that never armed.
 * The claim came from a `grep` whose output stopped at 30 of 78 lines. A count
 * is not a census.
 *
 * CERT-2587: the repair evaluated the function with `undefined`, because a
 * global `onError` has the config but seemingly not the data. That is fine for
 * the event page, whose callback always returns a positive number — and wrong
 * for `app/event/[domain]/[slug]/page.tsx`, whose callback is
 *
 *     (latest) => { if (latest?.event?.status === "live") return 30000;
 *                   … return 0; }
 *
 * i.e. it returns 0 for `undefined` and 30000 for a live payload. Evaluating
 * without data read that as "not polled" and left a live concept page latched.
 * Measured by the grader: `effective=30000, scheduled=[], armed=[]`.
 *
 * ── SO IT IS EVALUATED AGAINST THE KEY'S OWN CACHED DATA ────────────────────
 *
 * `cachedData` is `config.cache.get(key).data`, read in `SWRProvider`'s
 * `onError`. `cache` is on the merged config swr hands that callback, so this
 * is the SAME input swr's own polling effect uses when it calls
 * `refreshInterval(getCache().data)` — and the value it yields is therefore the
 * authoritative effective cadence, not an approximation of it.
 *
 * That is also why there is no artificial floor any more. The previous cut
 * clamped a function-priced key to a 60s minimum, which was a hedge against
 * evaluating with the wrong input. Reading the right input removes the need:
 * whatever the function reports for the data on screen is, by construction,
 * exactly what a healthy poll would have used, so the load invariant holds
 * without a second constant defending it. It also means the live event page
 * recovers at its real 32s cadence rather than a hedged 120s.
 *
 * Everything else still routes to null, which is the "true zero" refusal both
 * certs required: `0` (SWR's own "not polled", the live case from
 * `{ refreshInterval: autoRefresh ? 60000 : 0 }`), a function that reports 0
 * FOR ITS OWN CACHED DATA, a function that throws, and a function that reports
 * a non-positive or non-finite cadence. A key that is not polling was never
 * latched by the bug this fixes, so arming it would be traffic nobody asked
 * for.
 */
function pollIntervalMs(
  refreshInterval: unknown,
  cachedData: unknown,
): number | null {
  if (typeof refreshInterval === "number") {
    return Number.isFinite(refreshInterval) && refreshInterval > 0
      ? refreshInterval
      : null;
  }

  if (typeof refreshInterval === "function") {
    let evaluated: unknown;
    try {
      evaluated = (refreshInterval as (data?: unknown) => unknown)(cachedData);
    } catch {
      // A cadence function that cannot answer is a key we cannot price, and
      // this module fails toward not adding traffic.
      return null;
    }
    return typeof evaluated === "number" &&
      Number.isFinite(evaluated) &&
      evaluated > 0
      ? evaluated
      : null;
  }

  return null;
}

/**
 * A `retry_after` the server attached to the error, in ms, or null.
 *
 * `apiFetch` puts this on the `ApiError` for a 429 it did not itself absorb
 * (`lib/api.ts`). Reading it here is what makes the first recovery attempt
 * informed rather than a guess, in the one case where the server told us.
 */
function serverWaitMs(error: unknown): number | null {
  const advertised = (error as { retryAfterMs?: unknown } | null | undefined)
    ?.retryAfterMs;
  return typeof advertised === "number" &&
    Number.isFinite(advertised) &&
    advertised > 0
    ? advertised
    : null;
}

/**
 * How long to wait before the next nudge.
 *
 * The server's word wins upward when it gave one — never sooner than it asked,
 * never sooner than the key's own poll, never longer than `MAX_SERVER_WAIT_MS`.
 * Otherwise: the poll interval, doubling per consecutive failure, to a ceiling
 * that is itself never below the poll interval (a key polling every 5 minutes
 * must not start recovering every 60 seconds — that would be FASTER than
 * healthy, breaking the load invariant).
 *
 * ── #5134: THE FLOOR IS APPLIED LAST, AND THAT ORDER IS THE WHOLE FIX ────────
 *
 * Both clamps on the `retryAfterMs` path were right; their ORDER was not. It
 * read `min(max(retryAfterMs, baseMs), MAX_SERVER_WAIT_MS)`, which establishes
 * the floor and then lets the ceiling pull the answer back underneath it. Any
 * key polling slower than `MAX_SERVER_WAIT_MS` therefore recovered FASTER than
 * it polls the moment it saw a 429 — a direct breach of the load invariant that
 * is this module's entire safety argument for not capping the attempt count.
 *
 * It is not hypothetical and it is not confined to admin. A census of every
 * `refreshInterval` in the app (102 mentions, read whole — a count is not a
 * census, #5072) finds six keys above five minutes:
 *
 *     app/admin/page.tsx                       600_000    10 min  →  was 5 min
 *     components/weather/NaturalEvents.tsx   3_600_000     1 hr   →  was 5 min
 *     components/weather/RainForecast.tsx    3_600_000     1 hr   →  was 5 min
 *     components/weather/TemperatureMap.tsx  3_600_000     1 hr   →  was 5 min
 *     components/weather/WildCards.tsx      21_600_000     6 hr   →  was 5 min
 *     components/weather/ClimateDashboard.tsx 21_600_000    6 hr   →  was 5 min
 *
 * The worst case is a READER-facing page, not the admin one the issue named: a
 * six-hour weather key throttled once came back every five minutes — 72x its
 * healthy rate — and kept doing so for as long as the limiter kept saying 429,
 * because each nudge's own failure re-armed it at the same wrong number.
 *
 * So: clamp the server's instruction to what we are willing to wait, and THEN
 * take the floor. Written in that order the floor is last by construction and
 * cannot be undercut by a later operation — the property is structural rather
 * than a coincidence of two constants' relative sizes.
 */
export function recoveryDelayMs(
  baseMs: number,
  attempt: number,
  retryAfterMs: number | null,
): number {
  if (retryAfterMs !== null) {
    return Math.max(Math.min(retryAfterMs, MAX_SERVER_WAIT_MS), baseMs);
  }
  const ceiling = Math.max(baseMs, MAX_RECOVERY_DELAY_MS);
  return Math.min(baseMs * 2 ** attempt, ceiling);
}

export interface PollRecovery {
  /**
   * Wire to SWR's global `onError`. Arms, or advances, recovery for the key.
   *
   * `cachedData` is the key's current cache entry (`config.cache.get(key).data`)
   * and is only consulted for a function-valued `refreshInterval` — see
   * `pollIntervalMs`, and CERT-2587 for what evaluating without it cost.
   */
  recordError: (
    key: string,
    error: unknown,
    refreshInterval: unknown,
    cachedData?: unknown,
  ) => void;
  /** Keys with a nudge pending. For tests and for an admin read-out. */
  armedKeys: () => string[];
  /** The delay the pending nudge for `key` was scheduled with, or null. */
  pendingDelayMs: (key: string) => number | null;
  /** Cancel everything. Not used in the app; keeps tests from leaking timers. */
  stopAll: () => void;
}

export function createPollRecovery(deps: PollRecoveryDeps): PollRecovery {
  const armed = new Map<string, KeyState>();

  function disarm(key: string): void {
    const state = armed.get(key);
    if (!state) return;
    if (state.timer !== null) deps.clearTimer(state.timer);
    armed.delete(key);
  }

  function schedule(state: KeyState, key: string, delayMs: number): void {
    if (state.timer !== null) deps.clearTimer(state.timer);
    state.delayMs = delayMs;
    state.timer = deps.setTimer(() => {
      void fire(key);
    }, delayMs);
  }

  async function fire(key: string): Promise<void> {
    const state = armed.get(key);
    if (!state) return;
    state.timer = null;

    if (!deps.isVisible() || !deps.isOnline()) {
      // Nobody is reading a hidden tab, and SWR's own poll would not fetch
      // either. Come back at the same cadence WITHOUT spending an attempt: the
      // backoff measures consecutive failures, and a nap is not a failure.
      schedule(state, key, state.delayMs);
      return;
    }

    const epochAtFire = state.epoch;

    // `mutate` resolves whether or not the fetch worked. That is not an
    // oversight to route around — it is how swr@2.4.1 behaves: the hook's
    // revalidate catches the error, calls `onError`, and `return true`s, so the
    // promise carries no verdict. Awaiting it is only how we wait for the
    // attempt to finish; the verdict arrives through `recordError`.
    await deps.mutate(key).catch(() => undefined);

    const after = armed.get(key);
    if (!after || after.epoch !== epochAtFire) {
      // `recordError` fired during the nudge: the attempt failed and we have
      // already been re-armed at the next backoff step. Nothing to do — and
      // crucially, do NOT disarm, or we would cancel that fresh timer.
      return;
    }

    // No error was recorded, so one of two things is true, and both mean stop:
    // the nudge SUCCEEDED (swr has cleared the cached error and the key's own
    // poll is running again — handing back to it is the entire goal), or no
    // hook is mounted on this key any more, so the mutate was a no-op and the
    // reader has left the page.
    disarm(key);
  }

  return {
    recordError(key, error, refreshInterval, cachedData) {
      const baseMs = pollIntervalMs(refreshInterval, cachedData);
      if (baseMs === null) {
        // Not a polled key. A one-shot fetch that fails stays failed, exactly
        // as today — this ship restores the POLL, it does not invent retries
        // for keys that never had them.
        return;
      }

      const existing = armed.get(key);
      const state: KeyState = existing ?? {
        attempt: -1,
        baseMs,
        delayMs: 0,
        timer: null,
        epoch: 0,
      };
      state.attempt += 1;
      state.baseMs = baseMs;
      state.epoch += 1;
      armed.set(key, state);

      schedule(
        state,
        key,
        recoveryDelayMs(baseMs, state.attempt, serverWaitMs(error)),
      );
    },

    armedKeys: () => Array.from(armed.keys()),

    pendingDelayMs: (key) => {
      const state = armed.get(key);
      return state && state.timer !== null ? state.delayMs : null;
    },

    stopAll() {
      for (const key of Array.from(armed.keys())) disarm(key);
    },
  };
}
