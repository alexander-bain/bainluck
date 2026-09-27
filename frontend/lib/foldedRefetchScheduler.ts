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
  refetch: () => void,
  windowMs: number,
  now: () => number = Date.now,
): FoldedRefetchScheduler {
  let lastAt = Number.NEGATIVE_INFINITY;
  let trailing: ReturnType<typeof setTimeout> | null = null;

  const fire = () => {
    lastAt = now();
    refetch();
  };

  return {
    request() {
      const wait = lastAt + windowMs - now();
      if (wait <= 0) {
        // A late-running trailing timer would repeat this refetch.
        if (trailing) clearTimeout(trailing);
        trailing = null;
        fire();
        return;
      }
      if (trailing) return;
      trailing = setTimeout(() => {
        trailing = null;
        fire();
      }, wait);
    },
    cancel() {
      if (trailing) clearTimeout(trailing);
      trailing = null;
    },
  };
}
