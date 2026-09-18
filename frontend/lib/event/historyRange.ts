/**
 * #6948 — WHICH HISTORY BODY THE EVENT PAGE IS ENTITLED TO ASK FOR.
 *
 * `GET /api/events/{id}/history?range=since_start` omits points captured before kick-off. The event
 * page sends it on first paint because a finished game's chart opens on "Since Start" and draws none
 * of the pre-kickoff half — measured on production 2026-09-18, that half is 85-94% of the payload
 * (KC-DEN 2,299,202 B -> 588,254 B). The saving is serialize + `JSON.parse` on a phone's main
 * thread; the default view's render inputs are byte-identical either way.
 *
 * The deferral is lossless ONLY if the head can still be asked for, because the chart's "All" range
 * really does draw those points. So the page needs a rule for "do I still owe a wider request?", and
 * that rule is the whole of the risk in this ship. It lives here, pure, because the page it runs in
 * is a client component the frontend jest environment cannot render — a rule stated in a component
 * body is a rule asserted by a source scan, and a source scan cannot see an oscillation.
 */

import { EVENT_BOOT_HISTORY_RANGE } from "@/lib/event/detailBoot";

/** The chart's two ranges, spelled as `OddsChart` spells them. */
export type ChartTimeRange = "all" | "live";

/** The value of `range` for a given latch state. `undefined` means "send no parameter". */
export type HistoryRangeParam = "since_start" | undefined;

/**
 * The range the page is SETTLING ON for the data it currently holds.
 *
 * 🔴 NOT the `chartTimeRange` state variable, and the difference is a live defect rather than a
 * nicety. `defaultChartTimeRange` answers "all" whenever it cannot find `MIN_POINTS_TO_DRAW_A_LINE`
 * post-kickoff points — and before the history request resolves it is looking at `undefined`, so it
 * finds zero. Every event page therefore passes through a transient "all" that means "no data yet",
 * not "the reader wants the whole journey".
 *
 * That transient outlives the arrival of the payload by one commit: `servedHistory` and the stale
 * "all" are both readable in the same render, because the effect that corrects the range has not run
 * yet. A latch reading the state variable fires there — measured on KC-DEN 14638896, which then
 * fetched the trimmed body AND the full body on every load, i.e. strictly more work than before the
 * ship. Reading the evidence range instead is race-free because it is a `useMemo` over the very same
 * `historyData`: within one render they cannot disagree.
 *
 * Once the reader has chosen, their choice is the answer — including OddsChart's own
 * `nothingToDrawInLiveWindow` self-reset (#6349), which routes through the page's setter and so
 * marks the range user-set.
 */
export function effectiveChartRange(
  chartRangeUserSet: boolean,
  chartTimeRange: ChartTimeRange,
  evidenceChartTimeRange: ChartTimeRange
): ChartTimeRange {
  return chartRangeUserSet ? chartTimeRange : evidenceChartTimeRange;
}

/**
 * Should the page now hold a latch demanding the whole journey?
 *
 * ONE-WAY BY CONSTRUCTION — `prev === true` returns `true` whatever else is passed. That is not
 * defensiveness, it is the property that makes the feature terminate:
 *
 *   The obvious spelling keys the request on `chartTimeRange` alone. Then the full payload arrives
 *   carrying `pre_window_omitted: false` — which is ALSO the condition for not needing it — so the
 *   key flips back, SWR serves the cached trimmed body, `pre_window_omitted` reads true again, and
 *   the page fetches forever. A latch that can only rise cannot do that.
 *
 * IT ASKS THE SERVER'S FLAG, NOT THE RANGE ALONE. A scheduled game's chart also defaults to "all",
 * but the route already served it everything (there is no post-kickoff point to trim to) and sets
 * `pre_window_omitted: false`. Keying on the range alone would spend a duplicate request on that
 * cohort — which is most "all" charts, and is precisely the LAT-P171/P172 duplicate-fetch defect.
 *
 * `preWindowOmitted` is read as STRICTLY true: `undefined` is an older payload, or one served before
 * the field existed, and must not be guessed at. The client must never re-derive this by looking for
 * points older than `commence_time` — a series that legitimately has none is indistinguishable from
 * a trimmed one.
 */
export function nextFullHistoryLatch(
  prev: boolean,
  chartTimeRange: ChartTimeRange,
  preWindowOmitted: boolean | undefined
): boolean {
  if (prev) return true;
  return chartTimeRange === "all" && preWindowOmitted === true;
}

/**
 * The `range` parameter for a latch state.
 *
 * Omitted — not `"all"`, not `""` — once the whole journey is wanted: the route treats every
 * unrecognised value as "serve everything", but sending a made-up token would leave the client
 * depending on that leniency instead of on the documented contract.
 *
 * Returns the BOOT's constant rather than re-spelling the token, so the parked URL and every URL
 * this decides are one expression. Two builders that must stay equal is LAT-P171/P172's shape.
 */
export function historyRangeParam(fullHistoryRequested: boolean): HistoryRangeParam {
  return fullHistoryRequested ? undefined : EVENT_BOOT_HISTORY_RANGE;
}
