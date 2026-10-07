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
  return {
    recover(generation: number) {
      if (retired || !Number.isSafeInteger(generation) || generation <= latest) return;
      latest = generation;
      if (timer !== null) return;
      const chosen = delayMs();
      const wait = Number.isFinite(chosen) ? Math.max(100, Math.min(4999, chosen)) : 4999;
      timer = setTimeout(() => {
        timer = null;
        if (!retired) requestPair(latest);
      }, wait);
    },
    cancel() {
      retired = true;
      if (timer !== null) clearTimeout(timer);
      timer = null;
    },
  };
}
