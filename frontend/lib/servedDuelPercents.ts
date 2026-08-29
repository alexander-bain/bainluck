/**
 * #2279 — the web arm of "both served or neither".
 *
 * UX-P114 moved the two whole percents a game strip prints to the server, so the
 * two sides of one question are decided ONCE. Every surface that adopted the
 * fields then coalesced PER SIDE:
 *
 *     const awayPct = data.current_odds?.away_rendered_percent ?? fallbackAwayPct;
 *     const homePct = data.current_odds?.home_rendered_percent ?? fallbackHomePct;
 *
 * A payload carrying one field and not the other therefore prints a served value
 * beside a locally derived one, and that is the same 101 UX-P114 shipped to close
 * arriving from the other direction: on `0.505 / 0.495` a served home 51 sits
 * beside a naively derived away 50. The fields are optional precisely because a
 * Discover response is CACHED and the native and widget arms ship on their own
 * schedule — "the backend deployed" is not "every payload carries it", as
 * `discover/EventCard.tsx`'s own comment says. A response written across a
 * partial rollout is the case the fallback exists for, and it is exactly the case
 * the per-side form gets wrong.
 *
 * So the two served values are ONE decision. Either both are present and both are
 * used, or the pair falls back WHOLE to `renderedDuelPercents`.
 *
 * 🔴 THE SERVED PAIR DESCRIBES `current_odds` AND NOTHING ELSE. A caller whose
 * probabilities came from somewhere else — `opening_odds`, a history row, a chart
 * point — must pass `null` for both served values. Handing in `current_odds`'
 * rounding beside another source's probability prints a mismatched pair that
 * still sums to 100, so no sum guard can see it. They are separate parameters
 * rather than a `CurrentOdds` so the caller has to make that choice at the branch
 * that knows the answer.
 *
 * The native arm of this rule is `duelPercents` in
 * `ios/Bain Luck/Bain Luck/Utilities/RenderedPercent.swift`; the two are pinned
 * to each other by `frontend/__tests__/ios/duelPercentServedPair.test.ts`.
 */

import { renderedDuelPercents } from "@/lib/renderedPercent";

export function servedDuelPercents(
  awayProbability: number | null | undefined,
  homeProbability: number | null | undefined,
  servedAway: number | null | undefined,
  servedHome: number | null | undefined,
): Array<number | null> {
  if (servedAway != null && servedHome != null) return [servedAway, servedHome];
  return renderedDuelPercents(awayProbability, homeProbability);
}
