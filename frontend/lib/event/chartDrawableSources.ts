import type { EventHistoryResponse } from "@/lib/types";

/**
 * WHICH SOURCES THE CHART ACTUALLY STROKES (#8182).
 *
 * `/events/[id]/models` printed "Shown as this line on the chart" under every
 * source card, unconditionally. On `/events/15011303/models` (Real Sociedad
 * 4-1 Real Betis, FINAL) that sentence sat under a green dashed swatch for
 * Kalshi while the chart drew no Kalshi mark at all: the page named a line,
 * gave its dash pattern, and a reader who went to look found nothing there.
 *
 * TWO THINGS HAVE TO BE TRUE AT ONCE, and the page was checking neither.
 *
 *   1. THE SERIES NEEDS TWO POINTS. Every series is stroked `dot={false}`
 *      (`OddsChart.tsx`), so a ONE-POINT series renders literally nothing. The
 *      chart's own admission test is `points.length === 0` — one point short
 *      of the case that matters. #2000 closed that in the serializer by
 *      EMPTYING such a series, but the rule is asserted here too so the page
 *      is honest whether or not that has reached production.
 *
 *   2. IT NEEDS THEM IN THE RANGE THE CHART IS SHOWING, which is the half the
 *      page could not see. The chart's first paint asks for
 *      `range=since_start` (`EVENT_BOOT_HISTORY_RANGE`) and that drops every
 *      reading from before kick-off; the models page asked for the whole
 *      journey. Measured on production 2026-09-23 10:36Z, event 15011303:
 *      `win_prob_history.kalshi` is 2 points with no range and 1 point at
 *      `since_start`. So the untrimmed payload answers "drawable" about a plot
 *      on which nothing is drawn — the page was not wrong about its own data,
 *      it was answering about a different range from the one being looked at.
 *
 * 🔴 THE THREE CARD KINDS READ THREE DIFFERENT SERIES, so one lookup will not
 * do. Betting is stroked from `history` (`dataKey: "homeDelta"`), model
 * sources from `win_prob_history[key]`, and the legacy ESPN fallback from
 * `espn_history`. Checking `win_prob_history` alone would have hidden the
 * footer on the BETTING card, which draws on essentially every one of these
 * pages — a fix for an over-claim that silently introduces an under-claim.
 *
 * 🔴 THE ESPN FALLBACK IS AN `else`, NOT AN ALTERNATIVE. `OddsChart` reaches
 * `espn_history` only when `win_prob_history` is empty, and the models page's
 * own card list has the same shape (`hasApiSources ? … : legacy espn`). The
 * branch is mirrored rather than flattened, so the two cannot drift into
 * crediting ESPN with a line on a page whose chart is drawing the modern
 * series instead.
 *
 * UNKNOWN IS NOT DRAWABLE. Given no payload — still loading, or the request
 * failed — this returns an EMPTY set, so the page says nothing rather than
 * repeating a claim it cannot support. Fail-closed is the honest direction
 * here: an absent sentence costs a reader a pointer, a wrong one sends them
 * looking for a line that was never on the plot.
 */

/** A series shorter than this strokes nothing, because every line is `dot={false}`. */
export const MIN_POINTS_TO_STROKE = 2;

/** True iff `points` is long enough for the chart to stroke a visible segment. */
function strokes(points: unknown): boolean {
  return Array.isArray(points) && points.length >= MIN_POINTS_TO_STROKE;
}

/**
 * The set of source keys the chart draws a visible line for, read off the
 * payload for the range the chart is showing — NOT the page's own payload.
 */
export function drawableChartSources(
  chartRangeHistory: EventHistoryResponse | undefined | null,
): Set<string> {
  const drawable = new Set<string>();
  if (!chartRangeHistory) return drawable;

  if (strokes(chartRangeHistory.history)) drawable.add("betting");

  const winProb = chartRangeHistory.win_prob_history ?? {};
  if (Object.keys(winProb).length > 0) {
    for (const [key, points] of Object.entries(winProb)) {
      if (strokes(points)) drawable.add(key);
    }
  } else if (strokes(chartRangeHistory.espn_history)) {
    drawable.add("espn");
  }

  return drawable;
}
