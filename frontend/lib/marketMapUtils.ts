import { AGREEMENT_TOLERANCE } from "./otherMarketGroups";

export function posOnRail(value: number, min: number, max: number): number {
  return Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
}

/**
 * Float slack on the tolerance comparison, matching `otherMarketGroups`:
 * `0.52 - 0.5` is `0.020000000000000018` in IEEE 754, so a bare `>` would
 * withhold a pair sitting EXACTLY at tolerance.
 */
const TOLERANCE_EPSILON = 1e-9;

export interface RungCollapseResult<T> {
  rows: T[];
  /** Redundant rows removed because their duplicates agreed. */
  collapsed: number;
  /** Rungs withheld because their duplicates disagreed beyond tolerance. */
  withheld: number;
}

/**
 * Collapse market-map rows that describe the SAME rung into one row each.
 *
 * Why this exists — measured on production 2026-08-09, event 15191147
 * (Athletics @ Boston Red Sox, final). Its `period_markets` bucket carried 28
 * `half_total` rows spanning only 7 real thresholds, because FOUR different
 * games' Kalshi tickers were linked to one event:
 *
 *   KXMLBF5TOTAL-26JUL27…, -26JUL28…, -26JUL29…, -26JUL30…  on an Aug 9 game.
 *
 * The 1st-half total ladder therefore painted every rung four times, and two
 * of those repeats disagreed outright — `Over 1.5` rendered as 99% immediately
 * above `Over 1.5` at 1%. The corruption is not only cosmetic: the duplicated
 * points are fed to `buildDensityFromThresholds`, which quadruples their
 * weight, and to the closest-to-50% `reduce` that places the pre-game O/U
 * marker, so a wrong line can be picked from a repeated point.
 *
 * The monotonicity filter downstream cannot catch this. It tests
 * `prob <= lastProb`, and equal duplicates pass trivially, so a run of four
 * identical rungs slides straight through the guard meant to keep the ladder
 * sane.
 *
 * Policy is deliberately IDENTICAL to the "Additional Markets" section
 * (UX-P037): duplicates that agree collapse to one row; duplicates that
 * materially disagree are WITHHELD, never averaged and never resolved by
 * picking the more extreme value. The event page gets one agreement rule, not
 * two — hence the shared `AGREEMENT_TOLERANCE` import rather than a second
 * constant. Showing both sides would be showing source divergence, which the
 * standing *"the blend is the product"* ruling forbids.
 *
 * The full-game `totals` path already deduped by threshold (keeping the
 * highest `bookmaker_count`); the period paths and both spread paths never
 * did. This closes that inconsistency rather than inventing a new rule.
 *
 * PURE: no I/O, no React. Input order is preserved.
 */
export function collapseDuplicateRungs<T>(
  rows: T[],
  keyOf: (row: T) => string,
  probOf: (row: T) => number,
): RungCollapseResult<T> {
  const order: string[] = [];
  const byKey = new Map<string, T[]>();

  for (const row of rows) {
    const key = keyOf(row);
    let bucket = byKey.get(key);
    if (!bucket) {
      bucket = [];
      byKey.set(key, bucket);
      order.push(key);
    }
    bucket.push(row);
  }

  const kept: T[] = [];
  let collapsed = 0;
  let withheld = 0;

  for (const key of order) {
    const group = byKey.get(key) as T[];
    if (group.length === 1) {
      kept.push(group[0]);
      continue;
    }

    const probs = group.map(probOf);
    const spread = Math.max(...probs) - Math.min(...probs);

    if (spread > AGREEMENT_TOLERANCE + TOLERANCE_EPSILON) {
      withheld += 1;
      continue;
    }

    kept.push(group[0]);
    collapsed += group.length - 1;
  }

  return { rows: kept, collapsed, withheld };
}

export function rgbaFromIntensity(intensity: number, rgb: string): string {
  const alpha = 0.10 + (intensity / 100) * 0.78;
  return `rgba(${rgb},${alpha.toFixed(2)})`;
}

export interface ParsedSpread {
  team: string;
  threshold: number;
  probability: number;
  source: string;
  isHome: boolean;
  margin: number;
}

export function parseSpreadOutcome(
  outcomeName: string,
  probability: number,
  source: string,
  homeTeam: string,
  awayTeam: string
): ParsedSpread | null {
  const lower = outcomeName.toLowerCase();
  const homeWords = homeTeam.toLowerCase().split(" ");
  const awayWords = awayTeam.toLowerCase().split(" ");
  const isHome = homeWords.some((w) => w.length >= 3 && lower.includes(w));
  const isAway = awayWords.some((w) => w.length >= 3 && lower.includes(w));
  if (!isHome && !isAway) return null;

  const matches = outcomeName.match(/(\d+\.?\d*)/g);
  if (!matches || matches.length === 0) return null;
  const threshold = parseFloat(matches[matches.length - 1]);

  const team = isHome ? homeTeam : awayTeam;
  const margin = isHome ? threshold : -threshold;

  return { team, threshold, probability, source, isHome, margin };
}

export function isFullGameSpread(marketName: string): boolean {
  const lower = (marketName || "").toLowerCase();
  return (
    !lower.includes("1h") &&
    !lower.includes("1st half") &&
    !lower.includes("first half") &&
    !lower.includes("2h") &&
    !lower.includes("2nd half") &&
    !lower.includes("second half") &&
    !lower.includes("first 5")
  );
}

export function isGameTotal(outcomeName: string): boolean {
  return !outcomeName.includes(":");
}

export function buildDensityFromSpreads(
  spreads: ParsedSpread[],
  rangeMin: number,
  rangeMax: number,
  segments: number = 14
): number[] {
  if (spreads.length === 0) return new Array(segments).fill(5);

  const density = new Array(segments).fill(0);
  const step = (rangeMax - rangeMin) / segments;

  for (const s of spreads) {
    const segIdx = Math.floor((s.margin - rangeMin) / step);
    const clampedIdx = Math.max(0, Math.min(segments - 1, segIdx));
    density[clampedIdx] += s.probability;
  }

  const peak = Math.max(...density, 0.01);
  return density.map((d) => Math.round((d / peak) * 96));
}

export function buildDensityFromThresholds(
  thresholds: Array<{ threshold: number; overProbability: number }>,
  rangeMin: number,
  rangeMax: number,
  segments: number = 12
): number[] {
  if (thresholds.length < 2) return new Array(segments).fill(8);

  const sorted = [...thresholds].sort((a, b) => a.threshold - b.threshold);

  const rawPdf: Array<{ mid: number; density: number }> = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const dt = sorted[i + 1].threshold - sorted[i].threshold;
    if (dt <= 0) continue;
    const dp = sorted[i].overProbability - sorted[i + 1].overProbability;
    rawPdf.push({
      mid: (sorted[i].threshold + sorted[i + 1].threshold) / 2,
      density: Math.max(0, dp / dt),
    });
  }

  if (rawPdf.length === 0) return new Array(segments).fill(8);

  const step = (rangeMax - rangeMin) / segments;
  const density = new Array(segments).fill(0);

  for (let i = 0; i < segments; i++) {
    const x = rangeMin + (i + 0.5) * step;
    let d = 0;

    if (rawPdf.length === 1) {
      d = rawPdf[0].density;
    } else if (x <= rawPdf[0].mid) {
      d = rawPdf[0].density * Math.max(0, 1 - (rawPdf[0].mid - x) / (step * 3));
    } else if (x >= rawPdf[rawPdf.length - 1].mid) {
      d = rawPdf[rawPdf.length - 1].density * Math.max(0, 1 - (x - rawPdf[rawPdf.length - 1].mid) / (step * 3));
    } else {
      for (let j = 0; j < rawPdf.length - 1; j++) {
        if (x >= rawPdf[j].mid && x <= rawPdf[j + 1].mid) {
          const t = (x - rawPdf[j].mid) / (rawPdf[j + 1].mid - rawPdf[j].mid);
          d = rawPdf[j].density * (1 - t) + rawPdf[j + 1].density * t;
          break;
        }
      }
    }
    density[i] = d;
  }

  // Smooth: simple 3-point moving average to reduce choppiness
  const smoothed = density.map((_, i) => {
    const prev = i > 0 ? density[i - 1] : density[i];
    const next = i < density.length - 1 ? density[i + 1] : density[i];
    return (prev + density[i] * 2 + next) / 4;
  });

  const peak = Math.max(...smoothed, 0.001);
  return smoothed.map((d) => Math.round((d / peak) * 96));
}

export function sportVocab(sportKey: string | undefined): {
  marginTitle: string;
  totalTitle: string;
  unit: string;
  unitSingular: string;
} {
  const key = (sportKey || "").toLowerCase();
  if (key.includes("baseball") || key.includes("mlb")) {
    return { marginTitle: "Run margin map", totalTitle: "Runs map", unit: "runs", unitSingular: "run" };
  }
  if (key.includes("hockey") || key.includes("nhl")) {
    return { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal" };
  }
  if (key.includes("soccer") || key.includes("mls") || key.includes("epl")) {
    return { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal" };
  }
  return { marginTitle: "Margin map", totalTitle: "Total map", unit: "points", unitSingular: "point" };
}
