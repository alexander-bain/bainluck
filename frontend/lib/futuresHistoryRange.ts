// Reader-chosen history ranges for the generic `/futures/<id>` page (#7545).
//
// THE DEFECT THIS REPLACES. The page never asked the reader how far back to
// look. It DERIVED a single window on mount — 168h normally, up to 720h if the
// market had gone quiet, up to 4320h if it had settled — fetched once, and gave
// no control. Two things followed, both measured on production 2026-09-20:
//
//  1. THE HISTORY WAS THERE AND UNREACHABLE. `/futures/112921` (China/Taiwan)
//     served 161 points over the default 168h window; the same endpoint at
//     `hours=8760` served 4,527 back to 2026-02-19. `/futures/112894` (Xi):
//     73 vs 3,547. A promoted card about a months-long move landed on a page
//     that could only show the reader its last week.
//
//  2. THE SPAN MOVED ON ITS OWN. The backend widens a sparse window
//     (`_EXTEND_TIERS = [(20, 720), (10, 2160)]`), so the span depended on how
//     many points happened to fall inside it. `/futures/171` (Stanley Cup) was
//     read at 168h → `actual_hours=720`, 145 points, and later the same day at
//     168h → `actual_hours=168`, 22 points, because recent coverage had crossed
//     the threshold. Nothing on the page said which of those the reader had.
//
// WHY THE RUNGS REFETCH INSTEAD OF CLIPPING ONE WIDE FETCH. The sibling
// charts (SettledPathChart, WinnerEvolutionChart) fetch a fixed wide window once
// and clip it client-side with `windowOutcomeHistory`. That convention does not
// transfer here, and the reason is cost: measured at `hours=4320`,
// `/futures/109596` is **1.80 MB** and `/futures/1` is **1.18 MB**, against
// 95 KB and 48 KB at the 168h default. Fetching wide on mount would make every
// futures page load 20-40x heavier to serve a range most readers never open. So
// each rung is its own request, keyed by hours in SWR — which also makes the
// return trip free: going 1W → All → 1W re-reads the cached week rather than
// refetching it.
//
// 4320 WAS NOT "ALL". The old settled-market branch capped its reach at 4320h
// (180d) and called that the market's full life. It is not: at `hours=8760`,
// 112921 and 112894 both reach 2026-02-19 and `/futures/1` reaches 2026-02-02 —
// five to seven weeks earlier than the cap allowed. On all three the saturated
// `coverage_start` equals the market's own `created_at` to within a second, so
// `created_at` — not a constant — is what sizes an honest "All".

import { CHART_RANGES, type ChartRange, type ChartRangeKey } from "@/lib/chartWindow";

/**
 * The rungs this page offers. A strict subset of `ChartRangeKey`, so the chips
 * reuse `ChartRangeChips` verbatim with no change to the shared vocabulary that
 * the two event-concept charts also read.
 *
 * `1D` and `since_start` are deliberately not offered: futures prices are polled
 * hourly at best, so a day is usually a handful of points, and a futures market
 * has no event start to anchor to.
 */
export type FuturesRangeKey = Extract<ChartRangeKey, "1W" | "1M" | "all">;

/** Narrowest → widest, the order the chips are read in. */
export const FUTURES_RANGE_KEYS: readonly FuturesRangeKey[] = ["1W", "1M", "all"] as const;

/** Fixed-width rungs, in hours. `all` is derived per market — see `futuresRangeHours`. */
export const FUTURES_FIXED_RANGE_HOURS: Record<
  Exclude<FuturesRangeKey, "all">,
  number
> = {
  "1W": 168,
  "1M": 720,
};

/** `all` never asks for less than a month... */
export const FUTURES_ALL_MIN_HOURS = 720;
/** ...nor more than three years, so one ancient market cannot ask for everything. */
export const FUTURES_ALL_MAX_HOURS = 26280;
/**
 * `all` when the market will not say when it opened. A year saturates every
 * specimen measured for #7545; the note tells the reader when it did not.
 */
export const FUTURES_ALL_FALLBACK_HOURS = 8760;

const HOURS_MS = 60 * 60 * 1000;

/**
 * The chips, in `FUTURES_RANGE_KEYS` order, taken from the shared `CHART_RANGES`
 * so the labels cannot drift from the other two charts' labels for the same key.
 */
export const FUTURES_RANGE_CHIPS: ChartRange[] = FUTURES_RANGE_KEYS.map((key) => {
  const shared = CHART_RANGES.find((r) => r.key === key);
  if (!shared) {
    // Unreachable while FuturesRangeKey is an Extract<> of ChartRangeKey; guarded
    // by test so a future edit to CHART_RANGES cannot silently drop a chip.
    throw new Error(`futuresHistoryRange: no CHART_RANGES entry for "${key}"`);
  }
  return shared;
});

/**
 * URL guard. `?range=` is reader-editable and arrives as an arbitrary string, so
 * anything that is not one of this page's three rungs is not a range — including
 * the two real `ChartRangeKey`s this page does not offer.
 */
export function isFuturesRangeKey(value: unknown): value is FuturesRangeKey {
  return (
    typeof value === "string" &&
    (FUTURES_RANGE_KEYS as readonly string[]).includes(value)
  );
}

function hoursSince(iso: string | null | undefined, now: number): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return null;
  const h = (now - t) / HOURS_MS;
  // A timestamp in the future is a clock we do not trust, not a negative window.
  return h > 0 ? h : null;
}

/**
 * The `hours=` this rung asks the API for.
 *
 * `all` reaches back to the market's own open plus a day of slack, clamped — it
 * is NOT a constant, because the constant is what truncated 112921's history at
 * 180 days when 213 were there.
 */
export function futuresRangeHours(
  range: FuturesRangeKey,
  createdAt?: string | null,
  now: number = Date.now(),
): number {
  if (range !== "all") return FUTURES_FIXED_RANGE_HOURS[range];

  const open = hoursSince(createdAt, now);
  if (open == null) return FUTURES_ALL_FALLBACK_HOURS;
  return Math.min(
    Math.max(Math.ceil(open + 24), FUTURES_ALL_MIN_HOURS),
    FUTURES_ALL_MAX_HOURS,
  );
}

export interface FuturesRangeMarketState {
  status?: string | null;
  resolution_date?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

/**
 * Which rung the page opens on when the reader has not chosen one.
 *
 * This preserves exactly what the old derived `historyHours` was reaching for —
 * a settled market shows its whole life, a market that has gone quiet shows a
 * month, everything else shows a week — but as a NAMED rung the reader can see
 * they are on and move off, rather than a number computed behind the chart.
 */
export function defaultFuturesRange(
  market: FuturesRangeMarketState | null | undefined,
  now: number = Date.now(),
): FuturesRangeKey {
  if (!market) return "1W";

  const resolvedAt = market.resolution_date
    ? new Date(market.resolution_date).getTime()
    : null;
  const isSettled =
    market.status === "resolved" ||
    (resolvedAt != null && Number.isFinite(resolvedAt) && resolvedAt < now);
  if (isSettled) return "all";

  const quiet = hoursSince(market.updated_at, now);
  if (quiet != null && quiet > 72) return "1M";
  return "1W";
}

/**
 * How the empty state names the window the reader is looking at.
 *
 * "Not enough price history yet" is true of a market with no prices and FALSE of
 * a market whose prices all predate the rung the reader happens to be on — and
 * the second is now reachable in one tap, so the empty state has to know which
 * one it is saying.
 */
export function futuresRangeSpanWords(
  range: FuturesRangeKey,
  createdAt?: string | null,
  now: number = Date.now(),
): string {
  if (range === "all") return "this market's history";
  return `the last ${spanWords(futuresRangeHours(range, createdAt, now))}`;
}

function spanWords(hours: number): string {
  if (hours < 48) {
    const h = Math.max(1, Math.round(hours));
    return `${h} hour${h === 1 ? "" : "s"}`;
  }
  const d = Math.round(hours / 24);
  return `${d} day${d === 1 ? "" : "s"}`;
}

/**
 * The one sentence that keeps a chip from lying.
 *
 * The backend may widen a sparse window past what was asked for. #7545's bar is
 * that the reader's chosen range stays explicit — so rather than discard the
 * extra data (which would empty the chart on exactly the quiet markets the
 * widening exists to rescue), the chart draws what came back and this states the
 * difference. The chip says what was asked; this says what arrived.
 *
 * Returns null when the two agree, which is the ordinary case — silence is the
 * correct output when there is nothing to reconcile.
 */
export function rangeCoverageNote(
  requestedHours: number,
  actualHours?: number | null,
): string | null {
  if (!Number.isFinite(requestedHours) || requestedHours <= 0) return null;
  if (actualHours == null || !Number.isFinite(actualHours)) return null;
  // Round both before comparing: a sub-hour difference is not a widening, and
  // reporting "showing 7 days" against a requested 7 days is noise, not truth.
  if (Math.round(actualHours) <= Math.round(requestedHours)) return null;
  return `Too few prices in ${spanWords(requestedHours)} — showing ${spanWords(actualHours)}.`;
}
