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
 * Only a finite positive NUMBER counts. `refreshInterval` may also be a
 * function of the cached data, and `0` is SWR's "not polled". Both route to
 * null: a key we cannot price is a key we do not add traffic for, and a key
 * that is not polling was never latched by the bug this fixes. (Measured at
 * time of writing: all 78 `refreshInterval` sites in the app are numeric
 * literals, including `autoRefresh ? 60000 : 0`, which correctly yields null
 * when auto-refresh is off.)
 */
function pollIntervalMs(refreshInterval: unknown): number | null {
  return typeof refreshInterval === "number" &&
    Number.isFinite(refreshInterval) &&
    refreshInterval > 0
    ? refreshInterval
    : null;
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
 */
export function recoveryDelayMs(
  baseMs: number,
  attempt: number,
  retryAfterMs: number | null,
): number {
  if (retryAfterMs !== null) {
    return Math.min(Math.max(retryAfterMs, baseMs), MAX_SERVER_WAIT_MS);
  }
  const ceiling = Math.max(baseMs, MAX_RECOVERY_DELAY_MS);
  return Math.min(baseMs * 2 ** attempt, ceiling);
}

export interface PollRecovery {
  /** Wire to SWR's global `onError`. Arms, or advances, recovery for the key. */
  recordError: (key: string, error: unknown, refreshInterval: unknown) => void;
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
    recordError(key, error, refreshInterval) {
      const baseMs = pollIntervalMs(refreshInterval);
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
