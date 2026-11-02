/**
 * TEST-ONLY, independent of the stream controller and watchdog.
 *
 * The owner must call retrying() only for its primary connection while visible
 * and otherwise eligible. Call cancel() immediately on hidden, terminal,
 * navigation, or genuinely newer authoritative adoption, not on heartbeats or
 * duplicate previews. opened() both establishes OPEN and cancels an old probe.
 * Pass the same credit object across effect recreation and same-page navigation.
 */
export interface CurrentPreviewProbeCredit { spent: boolean }

export interface CurrentPreviewProbeLog {
  event: 'armed' | 'request' | 'result' | 'cancelled' | 'expired' | 'error' | 'ignored';
  at: number;
  reason?: string;
  error?: unknown;
}

export interface CurrentPreviewProbeOptions<Result, Timer> {
  now: () => number;
  schedule: (callback: () => void, delayMs: number) => Timer;
  cancelTimer: (timer: Timer) => void;
  request: (signal: AbortSignal) => Promise<Result>;
  onResult: (result: Result) => void;
  resultLog: (entry: CurrentPreviewProbeLog) => void;
  /** Inject an already-selected jitter value; deterministic default is 750 ms. */
  delayMs?: number;
  /** Lifetime starts at arming, not at request dispatch. */
  expiryMs?: number;
  credit?: CurrentPreviewProbeCredit;
}

export interface CurrentPreviewProbe {
  opened(): void;
  /** Returns true only when this transition spends the one lifetime credit. */
  retrying(): boolean;
  cancel(reason: string): void;
  dispose(): void;
}

export function createCurrentPreviewProbe<Result, Timer>(
  options: CurrentPreviewProbeOptions<Result, Timer>,
): CurrentPreviewProbe {
  const delay = options.delayMs ?? 750;
  const lifetime = options.expiryMs ?? 1500;
  if (!Number.isFinite(delay) || delay < 0 || !Number.isFinite(lifetime) || lifetime <= 0) {
    throw new RangeError('Probe delay must be nonnegative and lifetime positive and finite');
  }
  const credit = options.credit ?? { spent: false };
  type Attempt = {
    deadline: number;
    controller: AbortController;
    timers: Set<Timer>;
  };
  let active: Attempt | null = null;
  let phase: 'unestablished' | 'open' | 'retrying' = 'unestablished';
  let disposed = false;

  function log(event: CurrentPreviewProbeLog['event'], reason?: string, error?: unknown) {
    // Observability must never break the policy or create an unhandled rejection.
    try { options.resultLog({ event, at: options.now(), reason, error }); } catch { /* isolated */ }
  }

  function clearTimers(attempt: Attempt) {
    for (const timer of attempt.timers) options.cancelTimer(timer);
    attempt.timers.clear();
  }

  function finish(attempt: Attempt, abort: boolean) {
    if (active !== attempt) return;
    active = null; // Invalidate before abort handlers can synchronously reenter.
    clearTimers(attempt);
    if (abort) attempt.controller.abort();
  }

  function expire(attempt: Attempt) {
    if (active !== attempt) return;
    finish(attempt, true);
    log('expired', 'original-arm-deadline');
  }

  function isCurrent(attempt: Attempt): boolean {
    if (disposed || active !== attempt || attempt.controller.signal.aborted) return false;
    if (options.now() >= attempt.deadline) {
      expire(attempt);
      return false;
    }
    return true;
  }

  async function dispatch(attempt: Attempt) {
    if (!isCurrent(attempt)) return;
    log('request');
    try {
      const result = await options.request(attempt.controller.signal);
      if (!isCurrent(attempt)) {
        log('ignored', 'late-or-cancelled-result');
        return;
      }
      finish(attempt, false);
      options.onResult(result);
      log('result');
    } catch (error) {
      // Includes sync request throws, rejected requests and consumer errors.
      // Rejection can beat a throttled expiry timer too: do not skip its abort.
      if (active === attempt && options.now() >= attempt.deadline) expire(attempt);
      const wasCurrent = active === attempt;
      if (wasCurrent) finish(attempt, false);
      log('error', wasCurrent ? 'request-or-result-callback' : 'inactive-request-or-result-callback', error);
    }
  }

  function cancel(reason: string) {
    if (!active) return;
    finish(active, true);
    log('cancelled', reason);
  }

  return {
    opened() {
      if (disposed) return;
      phase = 'open';
      cancel('native-open');
    },
    retrying() {
      if (disposed || phase !== 'open') return false;
      phase = 'retrying';
      if (credit.spent) return false;
      credit.spent = true; // Atomic, before any callback can reenter.
      const attempt: Attempt = {
        deadline: options.now() + lifetime,
        controller: new AbortController(),
        timers: new Set<Timer>(),
      };
      active = attempt;
      log('armed');
      // Expiry has priority at an equal due time and never grants a fresh lease.
      attempt.timers.add(options.schedule(() => expire(attempt), lifetime));
      attempt.timers.add(options.schedule(() => { void dispatch(attempt); }, delay));
      return true;
    },
    cancel,
    dispose() {
      if (disposed) return;
      disposed = true;
      cancel('unmount');
    },
  };
}
