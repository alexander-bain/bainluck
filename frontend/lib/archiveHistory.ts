/**
 * A POINT RECOVERED FROM KALSHI'S ARCHIVE SAYS SO ON THE CHART (#683).
 *
 * Calibration's archive store (PR #11083) serves Kalshi's own recorded price
 * intervals on `/history` and `/multi-history` for questions whose live
 * history we never captured. Each such point is additive on the wire:
 *
 *   { timestamp: <interval close>, probability, american_odds: null,
 *     bookmaker: "kalshi_archive", provenance: "kalshi_archive",
 *     interval_start, period_minutes: 1 | 60,
 *     price_basis: "traded_interval" | "quote_only" }
 *
 * Live points are unchanged and carry no `provenance`. Without a reader that
 * looks, an archive close draws as an ordinary polling instant, so the chart
 * cannot be told apart from our own captures. This module is that reader.
 *
 * ═══ WHAT IT READS ═══
 *
 * The POINTS the chart is about to draw, never the response's `archive_history`
 * block. The block is the server's statement of what it served; the caption has
 * to describe what is on screen after the range cut and the legend selection,
 * and only the drawn points know that. A chart drawing no archive point says
 * nothing.
 *
 * ═══ WHAT IT SAYS ═══
 *
 * The span the archive covers, the cadence (hourly / minute-by-minute), and
 * whether the prices are trades or quotes from intervals with no trades — in
 * words, never the field strings. "From … to …, this line is" only when no live
 * point sits inside that span; otherwise "Some points from … to … are", because
 * the store withholds intervals that overlap a live capture and the two can
 * interleave.
 *
 * Pure and total: a render path calls it, so unparseable stamps are skipped,
 * not thrown on.
 */

import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

export const KALSHI_ARCHIVE_PROVENANCE = "kalshi_archive";

type PointLike = Pick<FuturesHistoryPoint, "timestamp" | "probability" | "bookmaker"> &
  Partial<Pick<FuturesHistoryPoint, "provenance" | "interval_start" | "period_minutes" | "price_basis">>;

/** Either marker names the archive; the contract sets both. */
export function isArchivePoint(point: PointLike | null | undefined): boolean {
  if (!point) return false;
  return (
    point.provenance === KALSHI_ARCHIVE_PROVENANCE ||
    point.bookmaker === KALSHI_ARCHIVE_PROVENANCE
  );
}

function stampMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

/** "hourly" / "minute-by-minute" only when every point agrees; else nothing. */
function cadenceWord(points: PointLike[]): string {
  const periods = new Set(points.map((p) => p.period_minutes));
  if (periods.size !== 1) return "";
  const [only] = Array.from(periods);
  if (only === 60) return "hourly";
  if (only === 1) return "minute-by-minute";
  return "";
}

function basisPhrase(points: PointLike[]): string {
  const bases = new Set(points.map((p) => p.price_basis));
  const traded = bases.has("traded_interval");
  const quoted = bases.has("quote_only");
  const known = (traded ? 1 : 0) + (quoted ? 1 : 0);
  if (known !== bases.size) return "prices";
  if (traded && quoted) return "trade and quoted prices";
  if (quoted) return "quoted prices (no trades)";
  return "trade prices";
}

export interface ArchiveChartNote {
  text: string;
  /** Earliest interval open drawn, ISO. */
  from: string;
  /** Latest interval close drawn, ISO. */
  through: string;
  points: number;
  /** True when no live point is drawn inside [from, through]. */
  whole: boolean;
}

/**
 * The one caption for the archive points among `outcomes` (the series the chart
 * draws), or null when it draws none.
 */
export function archiveChartNote(
  outcomes: readonly Pick<FuturesOutcomeHistory, "history">[],
  options: { timeZone?: string; now?: number } = {},
): ArchiveChartNote | null {
  const archive: PointLike[] = [];
  const live: number[] = [];
  let fromMs = Infinity;
  let throughMs = -Infinity;
  for (const outcome of outcomes) {
    for (const point of outcome.history ?? []) {
      if (point.probability === null || point.probability === undefined) continue;
      const closeMs = stampMs(point.timestamp);
      if (closeMs === null) continue;
      if (!isArchivePoint(point)) {
        live.push(closeMs);
        continue;
      }
      archive.push(point);
      const openMs = stampMs(point.interval_start) ?? closeMs;
      fromMs = Math.min(fromMs, openMs, closeMs);
      throughMs = Math.max(throughMs, closeMs);
    }
  }
  if (archive.length === 0) return null;

  const whole = !live.some((ms) => ms >= fromMs && ms <= throughMs);
  const zone = options.timeZone;
  const yearOf = (ms: number) =>
    Number(new Intl.DateTimeFormat("en-US", { year: "numeric", timeZone: zone }).format(ms));
  const thisYear = yearOf(options.now ?? Date.now());
  const showYear = yearOf(fromMs) !== thisYear || yearOf(throughMs) !== thisYear;
  const day = new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    ...(showYear ? { year: "numeric" as const } : {}),
    timeZone: zone,
  });
  const a = day.format(fromMs);
  const b = day.format(throughMs);
  const what = [cadenceWord(archive), basisPhrase(archive)].filter(Boolean).join(" ");
  const tail = `${what} recovered from Kalshi's records, not our own live price checks.`;
  const text =
    a === b
      ? whole
        ? `On ${a}, this line is ${tail}`
        : `Some points on ${a} are ${tail}`
      : whole
        ? `From ${a} to ${b}, this line is ${tail}`
        : `Some points from ${a} to ${b} are ${tail}`;

  return {
    text,
    from: new Date(fromMs).toISOString(),
    through: new Date(throughMs).toISOString(),
    points: archive.length,
    whole,
  };
}

/**
 * The tooltip's one line about the points it is showing (one per line under the
 * cursor), or null when none of them is an archive point.
 */
export function archiveTooltipNote(points: readonly (PointLike | null | undefined)[]): string | null {
  const shown = points.filter((p): p is PointLike => p != null);
  const archive = shown.filter(isArchivePoint);
  if (archive.length === 0) return null;
  const cadence = cadenceWord(archive);
  const record = cadence ? `Kalshi's ${cadence} record` : "Kalshi's record";
  const lead = archive.length === shown.length ? "From" : "Partly from";
  const noTrades = archive.every((p) => p.price_basis === "quote_only") ? " · no trades" : "";
  return `${lead} ${record}${noTrades}`;
}
