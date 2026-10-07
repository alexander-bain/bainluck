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
  request(): void;
  cancel(): void;
}

export function createFoldedRefetchScheduler(
  refetch: () => void | Promise<unknown>,
  windowMs: number,
  now: () => number = Date.now,
  // Opt-in for authoritative quote pairs: one retry after a failed or
  // insufficient read, even when no later invalidation arrives.
  retryUnresolved?: () => boolean,
): FoldedRefetchScheduler {
  let lastAt = Number.NEGATIVE_INFINITY;
  let trailing: ReturnType<typeof setTimeout> | null = null;
  let inFlight = false;
  let pending = false;
  let generation = 0;
  let automaticRetries = 0;
  let automaticRetryPending = false;

  const finish = (startedGeneration: number) => {
    if (generation !== startedGeneration) return;
    inFlight = false;
    if (!pending && automaticRetries === 0 && retryUnresolved?.()) {
      automaticRetries += 1;
      automaticRetryPending = true;
      pending = true;
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
    lastAt = now();
    const startedGeneration = generation;
    inFlight = true;
    const request = refetch();
    // The consumer owns error presentation. Rejection still releases this
    // slot so one retained invalidation can recover on the next read.
    if (request) {
      void Promise.resolve(request).then(
        () => finish(startedGeneration), () => finish(startedGeneration),
      );
    } else {
      finish(startedGeneration);
    }
  };
  const schedule = () => {
    if (inFlight || trailing) return;
    const wait = lastAt + windowMs - now();
    if (wait <= 0) fire();
    else trailing = setTimeout(fire, wait);
  };

  return {
    request() {
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
