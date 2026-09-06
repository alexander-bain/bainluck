/**
 * What an OPEN event page still refetches while the push stream is healthy, and
 * what a pushed frame is allowed to overwrite when it lands.
 *
 * Both were inline in `app/events/[id]/page.tsx`. They are here because they are
 * the two halves of one question — *does a value that is not in the frame ever
 * reach a page somebody left open?* — and because that question is answerable
 * without a DOM, which is the only way it gets a test in this repo (no jsdom, no
 * React Testing Library).
 *
 * ═══ THE BUG THAT MOVED THEM (CERT-1994) ═══
 *
 * live/034 S2 shipped SSE push for live events: while the stream delivers,
 * `refreshInterval` is **0** and polling stops entirely. That is right for the
 * probability, which the frame carries.
 *
 * It is wrong for everything the frame does NOT carry. The frame holds one
 * probability, one source and one stamp; the cache update spreads `...prev` for
 * the rest. So on a page left open, every other field is frozen at the moment it
 * was first fetched: the score, the status — and the tennis games line and its
 * `observed_at`, which is what made this visible.
 *
 * The freshness chip (#3242) turned that freeze into a false statement. The
 * server re-confirms the games line against ESPN every ~10 minutes; the page
 * never heard, so the chip counted up from a stamp nobody had refreshed and said
 * `Stale · 40m ago` about a number the server had re-confirmed a minute earlier.
 * A worse failure than the one the chip exists to prevent, because it is the
 * honesty mechanism itself lying.
 */

/**
 * How often an open event page revalidates, given what the stream is doing.
 *
 * `connected` no longer means "never" — it means SLOWLY. The push ship stands:
 * the probability still arrives in ~2s instead of waiting up to 32s, and that
 * was always the point. What changes is that the rest of the payload is
 * reconciled on a bounded background poll instead of never.
 *
 * ═══ WHY 120s AND NOT A TASTE ═══
 *
 * It is derived from the chip it has to keep honest, not chosen. `FreshnessChip`
 * calls a stamp stale past `STALE_MS` (5 min). If the page can go longer than
 * that without refetching, then a page-induced staleness is indistinguishable on
 * screen from a real one, and the chip stops meaning "the data is old" and starts
 * meaning "one of two different things is old". So the interval must sit
 * comfortably under the stale threshold; `SCHEDULED_REFRESH_INTERVAL` (120s)
 * already does, at 2.5x headroom, and reusing it beats inventing a fourth
 * cadence constant. `pushedRefreshIntervalIsHonest` pins that relationship so it
 * cannot be broken by editing either number alone.
 */
export function eventRefreshInterval(
  status: string | null | undefined,
  streamConnected: boolean,
  intervals: { live: number; scheduled: number },
): number {
  if (streamConnected) return intervals.scheduled;
  return status === "live" ? intervals.live : intervals.scheduled;
}

/** True while the pushed-page poll cannot itself cause a false `Stale`. */
export function pushedRefreshIntervalIsHonest(
  pushedInterval: number,
  staleMs: number,
): boolean {
  return pushedInterval > 0 && pushedInterval < staleMs;
}

export interface LiveFrame {
  p: number;
  source: string;
  source_value?: number | null;
  updated_at: string;
}

/**
 * A pushed frame applied to whatever the cache currently holds.
 *
 * The spread is the important part and it runs in this order on purpose: `prev`
 * first, then only the fields the frame actually speaks for. A frame knows one
 * probability. It must never be able to reinstate an older copy of anything
 * else — so when the background poll above lands a newer games line, the next
 * frame carries it forward rather than reverting it.
 */
export function applyLiveFrame<T>(prev: T | undefined, frame: LiveFrame): T | undefined {
  if (!prev) return prev;
  // A source entry carries display metadata (`display_name`, `type`, `color`)
  // that a frame cannot know, so the merge is structural and the type is
  // asserted at this one boundary — the same escape the inline version made
  // with `as never`, named instead of scattered. What actually guarantees the
  // spread preserves everything else is the behavioural test, not this cast.
  const sources = ((prev as { win_probability_sources?: Record<string, Record<string, unknown>> })
    .win_probability_sources ?? {}) as Record<string, Record<string, unknown>>;
  const existing = sources[frame.source] ?? {};
  return {
    ...prev,
    // `resolveProbability` reads `hero_probability` first on the live branch, so
    // this is the number the hero actually renders.
    hero_probability: frame.p,
    hero_probability_away: 1 - frame.p,
    win_probability_sources: {
      ...sources,
      [frame.source]: {
        ...existing,
        value: frame.source_value ?? frame.p,
        updated_at: frame.updated_at,
      },
    },
  } as unknown as T;
}
