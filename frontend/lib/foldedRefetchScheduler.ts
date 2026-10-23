/**
 * #9051 — the event page's "this held blend cannot be ordered, read detail
 * again" requests, rate-limited without losing the last one.
 *
 * A folded hero refuses every raw-row frame, and an incomparable history edge
 * is refused too; each says the blend moved, so the page refetches detail. The
 * stream can deliver a frame every few seconds, so requests are limited to one
 * per `windowMs` — but a leading-edge limit alone drops the LAST request of a
 * burst, and if the stream then goes quiet the headline waits out the
 * stream-connected poll. So a request inside the window schedules exactly one
 * trailing refetch at the window's end.
 *
 * The page never writes the SWR cache in the same tick as a request: swr
 * discards a fetch whose start precedes a later mutation, even a no-op one, so
 * "refetch, then mutate(prev => prev)" would cancel its own refetch.
 */
export interface FoldedRefetchScheduler {
  /**
   * `keepBackoff` (#10090): an ordinary invalidation. It still reads, but it
   * leaves an armed persistent ladder and its step count alone, so a busy page
   * cannot turn the ladder into its own rate.
   */
  request(options?: { keepBackoff?: boolean }): void;
  cancel(): void;
}

/** Why a read fired: `backoff` when the persistent ladder (below) asked for it. */
export type FoldedRefetchRead = { backoff: boolean };

export function createFoldedRefetchScheduler(
  refetch: (read: FoldedRefetchRead) => void | Promise<unknown>,
  windowMs: number,
  now: () => number = Date.now,
  // Opt-in for authoritative quote pairs: one retry after a failed or
  // insufficient read, even when no later invalidation arrives.
  retryUnresolved?: () => boolean,
  // #10090: an obligation no retry count may discharge (a reconcile floor).
  // After the one retry above, keep retrying while `owed()` holds, each wait
  // `delayMs(attempt)` from the previous read's end — still one read in
  // flight, and a fresh `request()` restarts the ladder. A read rejected with
  // the server's `retryAfterMs` (a 429) holds every next read, ladder or not,
  // until that wait has passed.
  persistent?: { owed: () => boolean; delayMs: (attempt: number) => number },
): FoldedRefetchScheduler {
  let lastAt = Number.NEGATIVE_INFINITY;
  let trailing: ReturnType<typeof setTimeout> | null = null;
  let inFlight = false;
  let pending = false;
  let generation = 0;
  let automaticRetries = 0;
  let automaticRetryPending = false;
  let backoff: ReturnType<typeof setTimeout> | null = null;
  let backoffAttempts = 0;
  let backoffDue = false;
  let holdUntil = Number.NEGATIVE_INFINITY;
  const disarmBackoff = () => {
    if (backoff) clearTimeout(backoff);
    backoff = null;
  };

  const finish = (startedGeneration: number, error?: unknown) => {
    if (generation !== startedGeneration) return;
    inFlight = false;
    const retryAfterMs = (error as { retryAfterMs?: unknown } | null | undefined)?.retryAfterMs;
    if (typeof retryAfterMs === "number" && Number.isFinite(retryAfterMs) && retryAfterMs > 0) {
      holdUntil = Math.max(holdUntil, now() + retryAfterMs);
    }
    if (!pending && automaticRetries === 0 && retryUnresolved?.()) {
      automaticRetries += 1;
      automaticRetryPending = true;
      pending = true;
    }
    // An invalidation's read that ends while a step is armed leaves it: the
    // wait is measured from the read that armed it.
    if (!pending && !backoff && persistent?.owed()) {
      backoffAttempts += 1;
      const chosen = persistent.delayMs(backoffAttempts);
      const wait = Math.max(windowMs, Number.isFinite(chosen) ? chosen : windowMs, holdUntil - now());
      backoff = setTimeout(() => {
        backoff = null;
        if (!persistent.owed()) return;
        pending = true;
        backoffDue = true;
        schedule();
      }, wait);
    }
    if (pending) schedule();
  };
  const fire = () => {
    trailing = null;
    // Navigation, terminal state or a covering response may retire the quote
    // while this retry waits. Do not turn it into an unrelated detail read.
    if (automaticRetryPending && !retryUnresolved?.()) {
      automaticRetryPending = false;
      pending = false;
      return;
    }
    automaticRetryPending = false;
    pending = false;
    const read = { backoff: backoffDue };
    backoffDue = false;
    lastAt = now();
    const startedGeneration = generation;
    inFlight = true;
    const request = refetch(read);
    // The consumer owns error presentation. Rejection still releases this
    // slot so one retained invalidation can recover on the next read.
    if (request) {
      void Promise.resolve(request).then(
        () => finish(startedGeneration), (error: unknown) => finish(startedGeneration, error),
      );
    } else {
      finish(startedGeneration);
    }
  };
  const schedule = () => {
    if (inFlight || trailing) return;
    const wait = Math.max(lastAt + windowMs, holdUntil) - now();
    if (wait <= 0) fire();
    else trailing = setTimeout(fire, wait);
  };

  return {
    request(options) {
      if (!options?.keepBackoff) {
        disarmBackoff();
        backoffAttempts = 0;
      }
      automaticRetryPending = false;
      automaticRetries = 0;
      pending = true;
      schedule();
    },
    cancel() {
      if (trailing) clearTimeout(trailing);
      trailing = null;
      pending = false;
      inFlight = false;
      generation += 1;
      disarmBackoff();
      backoffAttempts = 0;
      backoffDue = false;
      automaticRetries = 0;
      automaticRetryPending = false;
    },
  };
}

/** Consume only when a fetch starts; a deduped refresh must retain its intent. */
export function takeFreshRead(intent: { current: boolean }): boolean {
  const fresh = intent.current;
  intent.current = false;
  return fresh;
}
