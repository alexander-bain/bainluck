/**
 * What a counting-up hero number is entitled to SAY at a given moment (#3119).
 *
 * `AnimatedProbability` (`components/discover/shared.tsx`) starts its counter at
 * 0 and only counts up once the span is 50% visible. Until then it rendered a
 * fully-styled `0%` — and on 2026-09-05 that put a live Omega European Masters
 * hero on page one of Discover reading
 *
 *     0%   Thriston Lawrence   ▲17%
 *
 * while the feed payload beside it said `probability: 0.252` and the card's own
 * reason line said "leads at 25.2% (up 17.0% today)". The two largest numbers on
 * the card contradicted each other and the big one was wrong.
 *
 * The component already had the right grammar for this and applied it to the
 * wrong 0: a `value` of 0 on an unresolved market renders an em-dash, because a
 * zero there means "we have no probability". A `displayed` of 0 before the
 * animation starts means exactly the same thing — we have not begun to say
 * anything — and it was being printed as a reading.
 *
 * So the rule is one sentence: **a hero prints a percent only once it has
 * started counting toward a real one.** Everything else is `unknown`.
 *
 * This lives in `lib/` rather than inside the component because the frontend
 * jest environment is `node` — there is no DOM, no IntersectionObserver and no
 * effect to drive — so a guard can only reach this decision if the decision is
 * a pure function. See `__tests__/lib/animatedProbabilityReading.test.ts`.
 */

export type ProbabilityReading =
  | { kind: "unknown" }
  | { kind: "percent"; percent: number };

export function animatedProbabilityReading({
  value,
  resolved,
  started,
  displayed,
}: {
  /** The whole percent the counter is heading for. */
  value: number;
  /** A settled market may legitimately read 0% — that is a result, not a gap. */
  resolved?: boolean;
  /** Has the count-up actually begun (i.e. has the card been seen)? */
  started: boolean;
  /** The counter's current frame. */
  displayed: number;
}): ProbabilityReading {
  // A zero we were GIVEN is a missing probability, settled markets excepted.
  if (value === 0 && !resolved) return { kind: "unknown" };
  // A zero we have not yet moved off is not a reading at all. Off-screen cards
  // sit here for as long as they are off-screen — which, in any render that
  // never scrolls (every `tools/look.sh` screenshot, and a throttled background
  // tab), is forever.
  if (!started) return { kind: "unknown" };
  return { kind: "percent", percent: displayed };
}
