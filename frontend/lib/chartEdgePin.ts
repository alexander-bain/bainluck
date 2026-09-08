/**
 * chartEdgePin — the page renders ONE number, even when two workers answered.
 *
 * #3911 / CERT-2243. Standing ruling #1 is card == hero == chart: one number
 * per question. The backend already pins the blend line's right edge to the
 * point-in-time blend (`_pin_blend_edge`, UX-P003/#3714) so the curve ends
 * where the hero sits. That works within one process and cannot work across
 * two:
 *
 *   `_event_detail_cache` is module-global, which on Heroku means PROCESS
 *   -local. The event page fires `/events/{id}` and `/events/{id}/history` as
 *   two HTTP requests, and they can land on different web workers. Worker A
 *   serves a hero it cached up to 300s ago; worker B, whose cache is empty,
 *   computes the edge from live rows. Reproduced by the cert bus at
 *   hero 0.40 against edge 0.10 after both venues moved.
 *
 * The only place that holds both payloads is the page. So the page performs
 * the final pin.
 *
 * ═══ WHAT DOES NOT MOVE TO THE CLIENT ═══
 *
 * The POLICY — live appends, pre-match overwrites, a settled row stands down,
 * an edge older than two minutes is a genuine past reading and must keep its
 * own value (#1561, stale-rendered-as-fresh). That is four rules with two
 * disagreeing owners for "settled", and re-deriving them here would be ruling
 * 003's "the client must not adjudicate twice" — plus a second copy to drift.
 *
 * So the backend sends its ANSWER, not its reasoning: `blend_edge_pinned` is
 * true exactly when `_pin_blend_edge` wrote to the last point, i.e. when that
 * point is a claim about NOW. This function only decides WHICH number that
 * claim carries, and the answer is always "the one the reader can see".
 *
 * Deliberately a no-op in every other case — a false flag, a missing hero, a
 * hero that is not the blend (a settled winner, an `opening` fallback), or an
 * empty line. When the same worker served both, the value it writes is the
 * value already there.
 */

/** The subset of the detail payload this needs. */
export interface HeroForEdge {
  hero_probability?: number | null;
  hero_probability_source?: string | null;
}

/** The subset of the history payload this needs. */
export interface HistoryForEdge {
  aggregate_line?: Array<{ timestamp: string; home_probability: number }> | null;
  blend_edge_pinned?: boolean | null;
}

/**
 * The one `hero_probability_source` whose number IS the point-in-time blend.
 * Mirrors `_PINNABLE_HERO_SOURCE` in `backend/app/routes/events.py`: a settled
 * hero, an `opening` fallback and `final-unresolved` are different claims about
 * a different number, and stamping one onto a live curve's edge would say
 * something no aggregator said.
 */
export const PINNABLE_HERO_SOURCE = "blend";

/**
 * `history` with its blend line's right edge carrying the hero the page was
 * actually served. Returns the SAME object when nothing needs correcting, so
 * callers can memoize on identity and React sees no new value.
 *
 * `undefined` in, `undefined` out, and NOT widened to accept `null`: SWR's
 * `data` is `T | undefined`, and letting a `null` through here would only push
 * the widened type onto every consumer of the derived value downstream.
 */
export function pinChartEdgeToHero<T extends HistoryForEdge>(
  history: T | undefined,
  hero: HeroForEdge | undefined | null
): T | undefined {
  if (!history || !hero) return history;
  if (!history.blend_edge_pinned) return history;

  const line = history.aggregate_line;
  if (!line || line.length === 0) return history;

  const value = hero.hero_probability;
  if (typeof value !== "number" || !Number.isFinite(value)) return history;
  if (hero.hero_probability_source !== PINNABLE_HERO_SOURCE) return history;

  const last = line[line.length - 1];
  if (last.home_probability === value) return history;

  // Copy rather than mutate: `history` is SWR's cached value, and writing
  // through it would edit the cache entry every other consumer reads — the
  // number would change under a component that never re-rendered.
  return {
    ...history,
    aggregate_line: [
      ...line.slice(0, -1),
      { ...last, home_probability: value },
    ],
  };
}
