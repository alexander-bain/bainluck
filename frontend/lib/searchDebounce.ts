/**
 * A search box that waits for typing to settle before it asks the server
 * anything (LAT-P142).
 *
 * WHY THIS EXISTS, IN BUFFER BLOCKS.
 *
 * `CategoryBrowser`'s in-category box put its query straight into the SWR key,
 * so every keystroke was a request. Those requests are not equally priced.
 * `q` reaches `/api/futures/browse` as an unanchored `name ILIKE '%q%'`, and the
 * index that serves it — `ix_futures_name_trgm`, a GIN trigram index — needs
 * THREE characters before it can produce a trigram to look up. Below that
 * Postgres has no choice but to scan. Measured on production 2026-08-30,
 * `category=politics`, `EXPLAIN (ANALYZE, BUFFERS)`:
 *
 *     q='s'     132.8 ms   4,821 shared blocks   Bitmap Heap Scan, no trigram
 *     q='sup'    16.1 ms      40 shared blocks   BitmapAnd on ix_futures_name_trgm
 *
 * So the first two letters of every search cost ~120x the buffer traffic of the
 * query that immediately supersedes them, and nobody ever reads their results.
 * Debouncing is what stops them being issued at all.
 *
 * Framework-agnostic and timer-injectable, the same shape as
 * `createPrincipalDebouncer` next door and for the same reason: it makes the
 * coalescing a deterministic fake-timer test instead of a browser exercise.
 *
 * 🔴 WHAT THIS IS NOT. It is not a minimum-length gate. Refusing to search for
 * "US" would change what a person SEES, which is a product decision and not the
 * latency lane's to make. A slow typist still issues every prefix they pause on;
 * this removes the ones nobody asked for, not the ones somebody did.
 */

export interface SearchDebouncer {
  /**
   * Schedule `commit` for `value`, replacing anything already pending.
   *
   * Replacement rather than queueing is the whole point: five keystrokes inside
   * the window produce one commit, of the LAST value, not five commits.
   */
  schedule(value: string, commit: (value: string) => void): void;
  /** Drop any pending commit unconditionally (use on unmount). */
  cancel(): void;
  /** The value of the currently pending commit, or `undefined` if none. */
  readonly pendingValue: string | undefined;
}

export function createSearchDebouncer(
  delayMs: number,
  timers: {
    setTimeout: (fn: () => void, ms: number) => unknown;
    clearTimeout: (handle: never) => void;
  } = globalThis as never
): SearchDebouncer {
  let handle: unknown = null;
  let pending: string | undefined;

  const clear = () => {
    if (handle !== null) timers.clearTimeout(handle as never);
    handle = null;
    pending = undefined;
  };

  return {
    schedule(value, commit) {
      clear();
      pending = value;
      handle = timers.setTimeout(() => {
        // Cleared BEFORE dispatch so a `commit` that synchronously schedules
        // again (a re-render inside the state setter) cannot be cancelled by
        // this firing's own bookkeeping.
        handle = null;
        pending = undefined;
        commit(value);
      }, delayMs);
    },

    cancel: clear,

    get pendingValue() {
      return pending;
    },
  };
}
