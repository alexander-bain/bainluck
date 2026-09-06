/**
 * WHAT DOES A LINE CHART HOLD, AND HOW DO WE KNOW WITHOUT BEING TOLD PER SURFACE?
 *
 * #2961 (charts epic #2911). A trend chart is honest about every point it draws
 * and silent about everything between them. A flat run is the strongest claim a
 * trend chart can make — *nothing changed* — and both of the surfaces in that
 * issue were making it by absence.
 *
 * ═══ WHY THE THRESHOLD CANNOT BE A NUMBER OF HOURS ═══
 *
 * The obvious rule is "flag a series whose newest point is older than N hours",
 * and it is wrong in both directions at once. Measured on production
 * 2026-09-06 19:1xZ, the two series #2961 names:
 *
 *   | series | n | median gap | newest point | largest hole |
 *   |---|---|---|---|---|
 *   | `/api/futures/16630403/history` "Yes" | 359 | **1.00h** | 5.6h old | **345.6h** |
 *   | `/api/politics` presidential (×11) | 51 | **8–10h** | 0.6h old | **≈220h** |
 *
 * Pick N=6h and the politics rows are called old at every ordinary overnight
 * pause, because 8h between readings is simply what that channel does. Pick
 * N=24h and the futures series — five and a half hours behind on an hourly
 * beat, which is a real outage — reads as perfectly current. There is no N.
 * The only honest reference is **the series' own observed cadence**.
 *
 * ═══ WHY MEDIAN, AND NOT MEAN ═══
 *
 * The same table, one column further: the futures series has a mean gap of
 * 1.99h against a median of 1.00h, and the politics rows have a mean of 14.4h
 * against a median of 8h. In both cases the mean is roughly double the median,
 * and it is inflated by *exactly the hole this module exists to find*. A mean
 * cadence is a cadence that has already forgiven the outage, so a rule built on
 * it grades every series against its own worst behaviour. Median.
 *
 * ═══ WHY "NEWEST POINT AGE" IS NOT THE WHOLE TEST ═══
 *
 * The case that shaped the state list: the futures series carries a **345.6h
 * hole** — fourteen days — *inside* an otherwise hourly run, and its newest
 * point is recent. Every newest-point threshold, at every N, passes it. All
 * eleven politics rows carry a ≈220h hole with a 0.6h age and pass it too. So
 * `gapped` is a first-class state and not a footnote on `stale`: a chart can be
 * completely up to date and still be mostly interpolation.
 *
 * ═══ WHAT THIS MODULE WILL NOT DO ═══
 *
 * It never reads absence as health. A series whose timestamps will not parse is
 * `undated`, never `current` — that is gotcha #53 (an empty 200 is a response
 * shape, not an absence) applied to a render path. And it describes only: no
 * string here predicts that a number will arrive, because this module cannot
 * know that and ruling 142 says a section states what it IS.
 *
 * Pure and total, like `decideCalibrationStaleness` next door: every input —
 * `null`, an empty array, timestamps in the future, strings that are not dates
 * — produces an answer, because the caller is a render path and a throw there
 * is a blank page.
 */

import { freshnessAge } from "@/lib/tournamentProps";

const HOUR_MS = 60 * 60 * 1000;

/**
 * Fewest points that can establish a cadence.
 *
 * Four points give three gaps, which is the smallest set whose median is not
 * just its mean. At n=3 (two gaps) the "median" is the average of the two and
 * carries none of the outlier resistance the whole rule rests on — so three
 * points are reported as `thin` rather than graded against a cadence they
 * cannot support. Measured instance: `/api/politics` serves J.D. Vance and Ted
 * Cruz at n=3, beside n=51 neighbours, at identical visual weight.
 */
export const MIN_POINTS_FOR_CADENCE = 4;

/**
 * How many of its own median gaps a series may fall behind before the newest
 * point stops reading as current.
 *
 * Four separates the two measured cases cleanly and is not tuned tighter than
 * the evidence supports: the futures series is 5.6 medians behind (flagged) and
 * the politics rows are 0.07 (silent). Anything from 3 to 5 would do the same
 * job on this data; 4 is the middle of that band.
 */
export const STALE_CADENCE_MULTIPLE = 4;

/**
 * How many median gaps an interior hole must span to be called a hole.
 *
 * Six rather than four because an interior gap is a weaker signal than a
 * trailing one — a single skipped beat is normal operation, and at 4× a series
 * that misses two consecutive reads would be marked every time. Both measured
 * holes clear this by orders of magnitude (346× and 27×).
 */
export const GAP_CADENCE_MULTIPLE = 6;

/**
 * Absolute floors, so a fast series is not marked for a trivially small lapse.
 *
 * A 2-minute cadence times four is eight minutes, and eight minutes is not news
 * on a chart a reader is scrolling past; `FreshnessChip` already owns the live
 * leaderboard's 5-minute question and this module should not second-guess it at
 * that scale. These bound the multiples from below, never from above.
 */
export const STALE_FLOOR_MS = 15 * 60 * 1000;
export const GAP_FLOOR_MS = 2 * HOUR_MS;

export type SeriesFreshnessState =
  /** No usable points at all. */
  | "empty"
  /** Too few points to establish a cadence — see `MIN_POINTS_FOR_CADENCE`. */
  | "thin"
  /** Points exist, but none of them could be dated. Never read as current. */
  | "undated"
  /** The newest point is far behind the series' own cadence. */
  | "stale"
  /** Up to date, but a hole inside the run is far wider than the cadence. */
  | "gapped"
  /** Nothing to declare. */
  | "current";

export interface SeriesFreshness {
  state: SeriesFreshnessState;
  /** Points that carried a usable timestamp. */
  n: number;
  /** The series' own observed cadence. `null` when it has too few gaps. */
  medianGapMs: number | null;
  /** Newest point to `now`. `null` when nothing could be dated. */
  ageMs: number | null;
  /** Widest interior hole. `null` when there are no gaps to compare. */
  largestGapMs: number | null;
  /**
   * The sentence to render, or `null` for "say nothing".
   *
   * Always self-labelling, so a caller may drop it anywhere without a heading —
   * the same contract `PropFreshness.label` holds on the tournament board.
   */
  note: string | null;
}

/** A finite epoch-ms instant, or `null`. Rejects `NaN` from an unparseable date. */
function asInstant(value: unknown): number | null {
  if (value instanceof Date) {
    const t = value.getTime();
    return Number.isFinite(t) ? t : null;
  }
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string") {
    const t = new Date(value).getTime();
    return Number.isFinite(t) ? t : null;
  }
  return null;
}

/** Median of a non-empty list. Even lengths average the middle pair. */
function median(sorted: number[]): number {
  const mid = sorted.length >> 1;
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/**
 * "9 days" / "6 hours" / "20 min" — a SPAN, not an age.
 *
 * Deliberately not `freshnessAge`, which formats an age and suffixes "ago".
 * A hole in the middle of a series did not happen "ago" relative to anything a
 * reader can see, so borrowing that formatter would produce "no numbers for 9
 * days ago". Same rounding rule as its neighbour — always DOWN, so a hole is
 * never flattered into a smaller one.
 */
export function formatSpan(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return "0 min";
  const hours = ms / HOUR_MS;
  if (hours < 1) {
    const minutes = Math.max(1, Math.floor(hours * 60));
    return `${minutes} min`;
  }
  if (hours < 48) {
    const h = Math.floor(hours);
    return `${h} hour${h === 1 ? "" : "s"}`;
  }
  const days = Math.floor(hours / 24);
  return `${days} days`;
}

/**
 * What must a reader be told about this series?
 *
 * `timestamps` may be anything a payload carries — ISO strings, epoch numbers,
 * `Date`s, nulls, junk. Order does not matter; they are sorted here, because
 * two of the three callers hand over a payload array they did not sort
 * themselves and a single out-of-order point would otherwise invent a negative
 * gap and, through it, a hole.
 */
export function seriesFreshness(
  timestamps: readonly unknown[] | null | undefined,
  now: number = Date.now(),
): SeriesFreshness {
  const raw = timestamps ?? [];
  const points = raw
    .map(asInstant)
    .filter((t): t is number => t !== null)
    .sort((a, b) => a - b);

  const empty: SeriesFreshness = {
    state: "empty",
    n: 0,
    medianGapMs: null,
    ageMs: null,
    largestGapMs: null,
    note: "No numbers yet",
  };

  if (raw.length === 0) return empty;
  if (points.length === 0) {
    // Points arrived and none of them could be dated. This is NOT `empty` (the
    // series has content) and it is emphatically not `current`: we are looking
    // at data we cannot place in time and saying so is the only honest move.
    return {
      state: "undated",
      n: 0,
      medianGapMs: null,
      ageMs: null,
      largestGapMs: null,
      note: "These numbers aren't dated",
    };
  }

  const newest = points[points.length - 1];
  // Clamp at zero. A point stamped slightly in the future is a clock skew
  // between us and a venue, not a negative age, and "−3 min ago" is nonsense
  // on a page.
  const ageMs = Math.max(0, now - newest);

  if (points.length < MIN_POINTS_FOR_CADENCE) {
    const count = points.length;
    return {
      state: "thin",
      n: count,
      medianGapMs: null,
      ageMs,
      largestGapMs: null,
      note: `Only ${count} number${count === 1 ? "" : "s"} so far`,
    };
  }

  const gaps: number[] = [];
  for (let i = 1; i < points.length; i += 1) gaps.push(points[i] - points[i - 1]);
  const largestGapMs = Math.max(...gaps);
  const medianGapMs = median([...gaps].sort((a, b) => a - b));

  const staleAfter = Math.max(STALE_CADENCE_MULTIPLE * medianGapMs, STALE_FLOOR_MS);
  const gapAfter = Math.max(GAP_CADENCE_MULTIPLE * medianGapMs, GAP_FLOOR_MS);

  const base = { n: points.length, medianGapMs, ageMs, largestGapMs };

  // Precedence, and it is this way round deliberately. Being behind NOW is the
  // stronger fact: it is the one that changes whether the reader should trust
  // the right-hand end of the line, which is where they look first and where
  // the endpoint dot is. A series that is both behind and holed gets the
  // trailing sentence; the hole is still readable in `largestGapMs` for any
  // caller that wants to draw it.
  if (ageMs > staleAfter) {
    return {
      ...base,
      state: "stale",
      // Same words as the tournament board's `propFreshness`, on purpose —
      // #2961 asked for the vocabulary that already exists rather than a new one.
      note: `Last number ${freshnessAge(ageMs / HOUR_MS)}`,
    };
  }

  if (largestGapMs > gapAfter) {
    return {
      ...base,
      state: "gapped",
      note: `No numbers for ${formatSpan(largestGapMs)} in this stretch`,
    };
  }

  return { ...base, state: "current", note: null };
}

/**
 * True when the line a caller is about to draw crosses at least one hole.
 *
 * Split out because it answers a rendering question — *may this be drawn as one
 * continuous stroke?* — which is not the same question as *what do we tell the
 * reader?*, and a surface may want one without the other. `stale` says nothing
 * about the interior, so it is not sufficient on its own; a series can be both.
 */
export function seriesHasHole(freshness: SeriesFreshness): boolean {
  const { medianGapMs, largestGapMs } = freshness;
  if (medianGapMs === null || largestGapMs === null) return false;
  return largestGapMs > Math.max(GAP_CADENCE_MULTIPLE * medianGapMs, GAP_FLOOR_MS);
}

/**
 * The width at which a gap in THIS series stops being a skipped beat and starts
 * being a hole — or `null` for "this series cannot be graded, never split it".
 *
 * `seriesHasHole` answers *does this line cross a hole?*; a renderer needs the
 * stronger *which of my gaps are holes?*, and the only safe way to give it that
 * is to hand over the threshold rather than let it re-derive one. #3659 exists
 * because two places disagreeing about that number would be worse than either
 * being wrong: the caption under a plot (`seriesFreshness.note`) and the break
 * in the line above it have to be talking about the same interval.
 *
 * Clock-free on purpose, unlike its neighbours — geometry must not move when
 * the page is left open, and a path that re-broke on a timer would be a
 * different chart at 3am than at noon.
 */
export function seriesGapThresholdMs(
  timestamps: readonly unknown[] | null | undefined,
): number | null {
  const points = (timestamps ?? [])
    .map(asInstant)
    .filter((t): t is number => t !== null)
    .sort((a, b) => a - b);
  if (points.length < MIN_POINTS_FOR_CADENCE) return null;

  const gaps: number[] = [];
  for (let i = 1; i < points.length; i += 1) gaps.push(points[i] - points[i - 1]);
  const medianGapMs = median([...gaps].sort((a, b) => a - b));
  return Math.max(GAP_CADENCE_MULTIPLE * medianGapMs, GAP_FLOOR_MS);
}
