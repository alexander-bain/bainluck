/** #10666: one coalesced catch-up without ending a healthy SSE.
 * Caller retains the existing paired-read scheduler and its single bounded retry.
 * Jitter spreads requests; it is not a global concurrency or capacity guarantee.
 */
export function createReconnectCatchup(
  requestPair: (generation: number) => void,
  delayMs: () => number = () => 100 + Math.floor(Math.random() * 4900),
) {
  let latest = 0;
  let retired = false;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let dueAt = 0;
  return {
    recover(generation: number, maximumDelayMs?: number) {
      if (retired || !Number.isSafeInteger(generation) || generation <= latest) return;
      latest = generation;
      if (timer !== null && maximumDelayMs === undefined) return;
      const chosen = delayMs();
      const regular = Number.isFinite(chosen) ? Math.max(100, Math.min(4999, chosen)) : 4999;
      const cap = typeof maximumDelayMs === "number" && Number.isFinite(maximumDelayMs)
        ? Math.max(100, Math.min(4999, maximumDelayMs)) : 4999;
      // Rescale the full ordinary draw into the prompt interval: clamping
      // would put almost every viewer on exactly the maximum delay.
      const wait = cap < 4999
        ? 100 + Math.floor(((regular - 100) / 4900) * (cap - 99))
        : regular;
      const nextDue = Date.now() + wait;
      if (timer !== null) {
        if (dueAt <= nextDue) return;
        clearTimeout(timer);
      }
      dueAt = nextDue;
      timer = setTimeout(() => {
        timer = null;
        if (!retired) requestPair(latest);
      }, wait);
    },
    // #10666: the page already adopted a complete pair for this generation, so
    // the queued catch-up would only repeat it. A newer generation keeps its
    // timer. Caller proves same event/lifetime/range and captures the
    // generation before its read starts.
    complete(generation: number): boolean {
      if (retired || !Number.isSafeInteger(generation) || generation <= 0 ||
          generation !== latest || timer === null) return false;
      clearTimeout(timer);
      timer = null;
      dueAt = 0;
      return true;
    },
    cancel() {
      retired = true;
      if (timer !== null) clearTimeout(timer);
      timer = null;
    },
  };
}
