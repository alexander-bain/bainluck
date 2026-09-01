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

/**
 * HOW A SPORT IS SCORED — DECLARED, NEVER ASSUMED (#2441).
 *
 * ═══ THE DEFECT ═══
 *
 * Alex, on `/events/15293846` (a US Open match) on 2026-08-31: the page showed
 * **`PRE-GAME BER +4.5`**, **`Total: expected vs final — PRE-GAME 40`**,
 * **`Margin: expected vs final`** and a rail reading **`WAW by 18+ / BER by
 * 18+`**. *"Tennis has no point spread and no 40-point total. This is a generic
 * event template applied to a sport it does not fit, and it is the clearest
 * single tell that the page was not built for tennis."*
 *
 * Every one of those numbers came from here. The old `sportVocab` named three
 * sports and **fell through to points for everything else** — so tennis,
 * cricket, golf, darts, chess and every sport we have not yet met inherited
 * basketball's furniture by default, and the ±18 rail inherited basketball's
 * scale.
 *
 * ═══ WHY A REGISTRY AND NOT A FOURTH `if` ═══
 *
 * A fallthrough default is a claim about every sport that has not been written
 * down yet, made by whoever wrote the default. Adding `tennis` to the chain
 * fixes the page Alex read and leaves the next sport to be discovered the same
 * way — by him.
 *
 * So the polarity is inverted: **a sport gets scoring furniture only by being
 * NAMED, with its unit and its scale.** `UNSCORED_IN_POINTS` is what an
 * unrecognised sport gets, and it declares `hasDerivedSpread: false`, which
 * SUPPRESSES the derived-spread marker rather than inventing one. Silence now
 * means "we have not said", not "assume basketball". Same shape as the
 * win-prob blend's declared prefix registry (CERT-636), and for the same
 * reason: the previous version there was also a spelling test standing in for
 * a semantic one.
 *
 * ═══ WHAT `hasDerivedSpread` ACTUALLY GATES ═══
 *
 * Not the ladder — the MARKER. A tennis match really does have a game-spread
 * market (Kalshi quotes `Berrettini -1.5 games`) and a game total (`Over 34.5
 * games`), and those are true things worth showing in their own units. What is
 * NOT true is `current_odds.home_spread`, which is a POINTS figure derived from
 * the moneyline by a model that assumes interchangeable points. On the
 * Berrettini match that model produced **-4.3**, and the page printed it as
 * `BER +4.5` over a sport with no points at all.
 *
 * So a sport that declares `hasDerivedSpread: false` keeps every market a
 * bookmaker or exchange actually quoted, and loses only the number we made up.
 */
export interface SportScoringVocab {
  marginTitle: string;
  totalTitle: string;
  /** Plural, as the axis and the tiles say it: "points", "runs", "games". */
  unit: string;
  unitSingular: string;
  /**
   * How far the margin rail reaches, in THIS sport's units. Was `18` for
   * everything that was not baseball/hockey/soccer, which is how a tennis rail
   * came to be labelled `by 18+`.
   */
  marginRange: number;
  /**
   * May the page draw a spread it DERIVED from the win probability?
   *
   * True only where the sport is scored in interchangeable points and an
   * expected margin is a real quantity. `false` is the default an unnamed sport
   * inherits, because the failure it prevents (a fabricated margin in a unit
   * the sport does not have) is worse than the one it causes (a marker missing
   * from a sport that could have had one, which is one line to add here).
   */
  hasDerivedSpread: boolean;
}

/**
 * The declared sports. A prefix/substring match against the sport key, in
 * order, so `basketball_nba` and `basketball_ncaab` share one entry.
 *
 * Ranges are the sport's own realistic spread of outcomes, not a round number:
 * an NBA game is decided by up to ~18, a baseball game by ~5, a best-of-five
 * tennis match by ~6 games in the margin the market actually quotes.
 */
const SPORT_SCORING: { match: string[]; vocab: SportScoringVocab }[] = [
  {
    match: ["baseball", "mlb"],
    vocab: { marginTitle: "Run margin map", totalTitle: "Runs map", unit: "runs", unitSingular: "run", marginRange: 5, hasDerivedSpread: true },
  },
  {
    match: ["hockey", "nhl"],
    vocab: { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal", marginRange: 5, hasDerivedSpread: true },
  },
  {
    match: ["soccer", "mls", "epl", "uefa", "fifa"],
    vocab: { marginTitle: "Goal margin map", totalTitle: "Goals map", unit: "goals", unitSingular: "goal", marginRange: 5, hasDerivedSpread: true },
  },
  {
    // #2441's subject. A tennis match is scored in games inside sets; the
    // market quotes a game spread and a game total, and NEITHER is a point.
    // `hasDerivedSpread: false` is what stops `BER +4.5` being drawn from a
    // points model over a sport with no points.
    match: ["tennis"],
    vocab: { marginTitle: "Game margin map", totalTitle: "Games map", unit: "games", unitSingular: "game", marginRange: 6, hasDerivedSpread: false },
  },
  {
    match: ["basketball", "nba", "wnba", "ncaab"],
    vocab: { marginTitle: "Margin map", totalTitle: "Points map", unit: "points", unitSingular: "point", marginRange: 18, hasDerivedSpread: true },
  },
  {
    match: ["americanfootball", "nfl", "ncaaf"],
    vocab: { marginTitle: "Margin map", totalTitle: "Points map", unit: "points", unitSingular: "point", marginRange: 18, hasDerivedSpread: true },
  },
];

/**
 * What a sport we have not declared gets.
 *
 * Deliberately NOT basketball's entry under another name. The titles avoid
 * naming a unit at all, the rail is narrow, and no derived spread is drawn —
 * so an undeclared sport renders only what a market actually quoted, in the
 * market's own words, and nothing this file invented.
 */
export const UNSCORED_IN_POINTS: SportScoringVocab = {
  marginTitle: "Margin map",
  totalTitle: "Scoring map",
  unit: "",
  unitSingular: "",
  marginRange: 6,
  hasDerivedSpread: false,
};

export function sportVocab(sportKey: string | undefined): SportScoringVocab {
  const key = (sportKey || "").toLowerCase();
  if (!key) return UNSCORED_IN_POINTS;
  for (const entry of SPORT_SCORING) {
    if (entry.match.some((m) => key.includes(m))) return entry.vocab;
  }
  return UNSCORED_IN_POINTS;
}

/**
 * `"33 games"`, or just `"33"` for a sport whose unit we have not declared.
 *
 * `UNSCORED_IN_POINTS.unit` is deliberately the empty string — an undeclared
 * sport should print the number a market quoted and NOT a unit this file
 * guessed. Every template that interpolates the unit therefore has to survive
 * it being absent, and doing that inline produces `"33 "` and
 * `"Final  distribution"`. One helper, so a new call site cannot reintroduce
 * the double space.
 */
export function withUnit(value: string | number, vocab: SportScoringVocab): string {
  return vocab.unit ? `${value} ${vocab.unit}` : String(value);
}

/** `"Final games distribution"` / `"Final distribution"`. Same reason. */
export function unitPhrase(prefix: string, vocab: SportScoringVocab, suffix: string): string {
  return [prefix, vocab.unit, suffix].filter(Boolean).join(" ");
}
