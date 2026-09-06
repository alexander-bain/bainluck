/**
 * The contender trend chart — legend, lines and timeframe (UX-P132 re-skin).
 *
 * Structure adopted from Alex's Kalshi reference (`_KALSHI-REFERENCE-baseball-champion.png`):
 * legend of the top three above the chart, exactly three lines drawn in the
 * legend's colours with endpoint dots, timeframe selector bottom-right, then a
 * collapsed list of three rows and a "show all N" expander.
 *
 * **Adaptation, not imitation** — the ruling is explicit. Kalshi's rows carry
 * two-sided green/red price pills; that is a trading format and we do not copy
 * it. Our rows show one blended probability per contender. What is taken is the
 * STRUCTURE: legend → three-line chart → collapsed list.
 *
 * Standing doctrine still governs everything numeric:
 *
 * - **Fixed 0-100 axis, always.** `chartGeometry` never auto-scales to the data
 *   range. An auto-scaled axis turns a 2pp wiggle into a cliff, which on a page
 *   whose subject is movement is worse than showing nothing.
 * - **No smoothing, ever.** Straight segments between real observations. The
 *   reference's line is visibly jagged and that is the point — movement IS the
 *   product, and a smoother is a machine for hiding it.
 * - **Gaps stay gaps.** A day with no reading is absent, never interpolated
 *   and never carried forward.
 */

import type { TournamentRow, TournamentTrendPoint } from "./tournament";

/** How many contenders the legend names and the chart draws. Kalshi's own
 *  reference shows exactly three, which settled the 3-vs-5 question. */
export const CHART_SERIES_COUNT = 3;

/** How many rows the collapsed board shows before "show all N". Same three, so
 *  the list and the chart describe the same set — a list showing five while the
 *  chart drew three would invite the reader to look for two missing lines. */
export const COLLAPSED_ROW_COUNT = 3;

export const SERIES_COLORS = [
  "var(--series-1)",
  "var(--series-2)",
  "var(--series-3)",
  "var(--series-4)",
  "var(--series-5)",
  "var(--series-6)",
] as const;

/**
 * The most lines the picker will draw at once (UX-P137, Alex's ruling 6).
 *
 * Six is where a 320px-wide chart stops being readable, measured by eye rather
 * than asserted: at seven the endpoint dots of a tight field overlap and the
 * legend needs a second column. The default is still three — "default stays
 * top-3; the user chooses beyond that."
 */
export const MAX_SERIES_COUNT = SERIES_COLORS.length;

export type Timeframe = "1D" | "1W" | "1M" | "ALL";

export const TIMEFRAMES: Timeframe[] = ["1D", "1W", "1M", "ALL"];

const TIMEFRAME_DAYS: Record<Timeframe, number | null> = {
  "1D": 1,
  "1W": 7,
  "1M": 30,
  ALL: null,
};

/**
 * ═══ ux/1034 A1: THE CHART OPENS ON THE TOURNAMENT, NOT ON THE MONTH ═══
 *
 * Alex, on the live hub during the US Open's fourth day: *"I'm a LOT more
 * interested in how the Contender chart has looked … since the tournament
 * started than since August 5th."*
 *
 * He was reading `ALL`, which is what this chart has always opened on, and on
 * the men's board `ALL` is 30 days: three and a half weeks of pre-tournament
 * drift, then the four days anybody is actually watching, compressed into the
 * right-hand sixth of the plot. The four buttons could not fix it either —
 * `1W` is seven days back from the latest reading, which is a rolling window
 * that happens to land near the draw today and will not next Tuesday, and the
 * one thing a reader wants is a window with a MEANING rather than a length.
 *
 * So the range selector gains two options that are DATES rather than durations:
 *
 *   - **`DRAW`** — since the main draw began. The default, when the payload
 *     names a start and there are two readings inside it.
 *   - **`QUAL`** — since qualifying began, five days earlier. Alex's toggle:
 *     the qualifying week is real tournament history and some readers want it,
 *     but it is not what "the tournament started" means to most people.
 *
 * `1D`/`1W`/`1M`/`ALL` are untouched and stay on the row — the instruction was
 * to change the default and add a toggle, not to take anything away.
 *
 * ⚠️ **THE DATES ARE NEVER CONSTANTS HERE.** `30 August` is a fact about one
 * tournament in one year; a literal in this module would be wrong for the
 * Australian Open and silently wrong for next year's US Open. Both starts are
 * read off the payload — see `tournamentWindowStarts` — and an option whose
 * start the payload does not carry is not offered at all.
 */
export type ChartWindow = "DRAW" | "QUAL";

/** A window (a date) or a timeframe (a duration). What a range chip selects. */
export type ChartRange = ChartWindow | Timeframe;

/** The two date-anchored windows, in the order they are offered. */
export const CHART_WINDOWS: ChartWindow[] = ["DRAW", "QUAL"];

/**
 * Where each window starts, as `YYYY-MM-DD`, or `null` for "we cannot say".
 *
 * The trend series is a series of DAYS, so a day is the resolution this needs
 * and a timestamp would only invite a timezone argument the data cannot settle.
 */
export interface WindowStarts {
  /** First day of the main draw. */
  DRAW: string | null;
  /** First day of qualifying. */
  QUAL: string | null;
}

export const NO_WINDOW_STARTS: WindowStarts = { DRAW: null, QUAL: null };

/** Chip text. Short, because six of these share one row with the span note. */
export const RANGE_LABELS: Record<ChartRange, string> = {
  DRAW: "Draw",
  QUAL: "Quals",
  "1D": "1D",
  "1W": "1W",
  "1M": "1M",
  ALL: "ALL",
};

export function isChartWindow(range: ChartRange): range is ChartWindow {
  return range === "DRAW" || range === "QUAL";
}

/** The timeframe a range draws with. A window has already filtered its points. */
export function rangeTimeframe(range: ChartRange): Timeframe {
  return isChartWindow(range) ? "ALL" : range;
}

/**
 * What a chip means, spelled out — `Since the main draw began, 30 August`.
 *
 * Ruling 2's rule on this page, applied to a control instead of to a number: a
 * chip labelled `Draw` names a window whose bounds only the data knows, so the
 * sentence travels with it for a screen reader and as a `title` for everyone
 * else. `DRAW`/`QUAL` are the two chips a reader cannot decode from the label.
 */
export function rangeDescription(
  range: ChartRange,
  starts: WindowStarts
): string | null {
  if (!isChartWindow(range)) return null;
  const start = starts[range];
  if (!start) return null;
  const when = longDateLabel(start);
  return range === "DRAW"
    ? `Since the main draw began, ${when}`
    : `Since qualifying began, ${when}`;
}

/** `2026-08-30` -> `30 August`. Day-first, like the axis labels. */
export function longDateLabel(iso: string): string {
  const [year, month, day] = (iso || "").split("-").map(Number);
  if (!year || !month || !day) return iso;
  const months = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  return `${day} ${months[month - 1] ?? ""}`.trim();
}

/**
 * Points on or after a day, or every point when there is no day.
 *
 * String comparison rather than `Date.parse`, deliberately: both sides are
 * `YYYY-MM-DD`, which sorts lexicographically exactly as it sorts
 * chronologically, and parsing would reintroduce the midnight-UTC question that
 * `dayNumber` exists to keep out of the rest of this module.
 */
export function pointsFromDate(
  points: TournamentTrendPoint[],
  start: string | null
): TournamentTrendPoint[] {
  if (!Array.isArray(points)) return [];
  if (!start) return points;
  return points.filter((point) => typeof point.date === "string" && point.date >= start);
}

/**
 * A whole series list narrowed to a window.
 *
 * The narrowing happens HERE, before geometry, rather than inside
 * `pointsInTimeframe` — which would have meant threading a pair of dates
 * through `chartCeiling`, `chartGeometry`, `seriesPoints`, `seriesEndpoint` and
 * `timeframeIsDrawable`, five signatures whose every caller would then have to
 * be told about a tournament. A window is a smaller SERIES, and the chart
 * already knows how to draw a smaller series: `ALL` over it is the whole
 * window. Nothing downstream learns a new concept.
 */
export function seriesFromDate(
  series: ChartSeries[],
  start: string | null
): ChartSeries[] {
  if (!start) return series;
  return series.map((entry) => ({ ...entry, points: pointsFromDate(entry.points, start) }));
}

/** The series a range draws — windowed for `DRAW`/`QUAL`, untouched otherwise. */
export function seriesForRange(
  series: ChartSeries[],
  range: ChartRange,
  starts: WindowStarts
): ChartSeries[] {
  return isChartWindow(range) ? seriesFromDate(series, starts[range]) : series;
}

/** Whether a range has two readings to join. Windows and durations, one test. */
export function rangeIsDrawable(
  series: ChartSeries[],
  range: ChartRange,
  starts: WindowStarts
): boolean {
  return timeframeIsDrawable(
    seriesForRange(series, range, starts),
    rangeTimeframe(range)
  );
}

/**
 * The chips, in order: the windows the payload can date, then the durations.
 *
 * A window with no start is not offered. An option that cannot be honoured is
 * worse than an absent one — it would render disabled beside four disabled
 * duration buttons on a thin field and read as a broken control.
 */
export function chartRanges(starts: WindowStarts): ChartRange[] {
  return [
    ...CHART_WINDOWS.filter((window) => Boolean(starts[window])),
    ...TIMEFRAMES,
  ];
}

/**
 * What the chart opens on: the main draw where it can be drawn, else `ALL`.
 *
 * `ALL` remains the floor for the same reason it was the default before — with
 * a field's prices dark the narrow windows are the empty ones, and a chart that
 * opens blank on a market with a month of history is the worse failure. So the
 * tournament window has to EARN the default by having two readings in it, which
 * on the morning of day one it will not.
 */
export function defaultChartRange(
  series: ChartSeries[],
  starts: WindowStarts
): ChartRange {
  if (starts.DRAW && rangeIsDrawable(series, "DRAW", starts)) return "DRAW";
  return "ALL";
}

export interface ChartSeries {
  entityKey: string;
  displayName: string;
  color: string;
  probability: number | null;
  isLive: boolean;
  points: TournamentTrendPoint[];
}

/**
 * The top N rows as chart series, in board order.
 *
 * Rows without a probability (settled) are skipped: a result is not a
 * standing, and a settled player has no live line to draw.
 */
export function chartSeries(rows: TournamentRow[], limit = CHART_SERIES_COUNT): ChartSeries[] {
  return rows
    .filter((row) => row.probability !== null)
    .slice(0, limit)
    .map((row, index) => ({
      entityKey: row.entity_key,
      displayName: row.display_name,
      color: SERIES_COLORS[index % SERIES_COLORS.length],
      probability: row.probability,
      isLive: row.probability_is_live === true,
      points: Array.isArray(row.trend) ? row.trend : [],
    }));
}

/** Rows the chart is allowed to draw at all: a settled row has no live line. */
export function chartableRows(rows: TournamentRow[]): TournamentRow[] {
  return rows.filter((row) => row.probability !== null);
}

/** The default selection — the board's top three, by entity key. */
export function defaultSelection(rows: TournamentRow[]): string[] {
  return chartableRows(rows)
    .slice(0, CHART_SERIES_COUNT)
    .map((row) => row.entity_key);
}

/**
 * The chosen contenders as chart series (UX-P137, Alex's ruling 6).
 *
 * COLOUR FOLLOWS SELECTION ORDER, not board rank — so an ADDED line always
 * gets a colour no line on the chart is already using, which is the property
 * that makes the picker feel like adding rather than redrawing.
 *
 * It is NOT pinned per entity, and the honest consequence is that removing a
 * line recolours the ones after it. Pinning would need the selection to carry
 * its own colour slots, and the failure it would prevent is cosmetic: the
 * legend dot and the line both read `entry.color` from this one function, so
 * they can never disagree with each other — only with the reader's memory of
 * a second ago. Worth knowing, not worth a second data structure.
 *
 * Unknown or unpriced keys are dropped rather than rendered empty, and the
 * result is capped at `MAX_SERIES_COUNT`.
 */
export function chartSeriesFor(
  rows: TournamentRow[],
  selection: string[]
): ChartSeries[] {
  const byKey = new Map(chartableRows(rows).map((row) => [row.entity_key, row]));
  const out: ChartSeries[] = [];
  for (const key of selection) {
    const row = byKey.get(key);
    if (!row || out.some((entry) => entry.entityKey === key)) continue;
    out.push({
      entityKey: row.entity_key,
      displayName: row.display_name,
      color: SERIES_COLORS[out.length % SERIES_COLORS.length],
      probability: row.probability,
      isLive: row.probability_is_live === true,
      points: Array.isArray(row.trend) ? row.trend : [],
    });
    if (out.length >= MAX_SERIES_COUNT) break;
  }
  return out;
}

/** Colour per selected entity — so the board's name underline follows the chart. */
export function seriesColorByEntity(series: ChartSeries[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const entry of series) out[entry.entityKey] = entry.color;
  return out;
}

/**
 * Candidate rows for the picker, narrowed by what the reader typed.
 *
 * UX-P138, Alex's ruling 5: "is it as good as DataGolf's picker? If not, close
 * the gap." The honest answer was no, and this was the biggest of the three
 * gaps — DataGolf's picker filters as you type, ours made you expand a list of
 * 41 names and scan. On a men's field of 44 that is not a picker, it is a
 * directory. The report has the full comparison.
 *
 * Case- and accent-insensitive substring on the display name, matching
 * ANYWHERE rather than at the start: a reader who knows a surname should not
 * have to remember the first name it is filed under. Accent folding matters on
 * this field specifically — "Sørensen" and "Dvořák" are exactly the names a
 * reader types unaccented, and a picker that returns nothing for `sorensen`
 * looks broken rather than strict.
 */
export function filterCandidates(
  rows: TournamentRow[],
  query: string
): TournamentRow[] {
  const needle = foldForSearch(query);
  if (needle === "") return rows;
  return rows.filter((row) => foldForSearch(row.display_name).includes(needle));
}

/**
 * Lowercase, accent-stripped, trimmed — the one normalisation both sides use.
 *
 * NFD plus a combining-mark strip does NOT cover the Nordic and Slavic letters
 * that are their own codepoints rather than a base plus an accent: `ø`, `æ`,
 * `å`, `ł`, `đ`, `ß`. Those decompose to themselves, so `sorensen` would miss
 * `Sørensen` and the picker would look broken on exactly the names this field
 * is full of. The map is short and explicit because a PARTIAL fold is worse
 * than none: it works on Dvořák, fails on Sørensen, and teaches the reader
 * that search is unreliable rather than strict.
 */
const FOLD_SPECIALS: [RegExp, string][] = [
  [/ø/g, "o"],
  [/æ/g, "ae"],
  [/å/g, "a"],
  [/ł/g, "l"],
  [/đ/g, "d"],
  [/ð/g, "d"],
  [/þ/g, "th"],
  [/ß/g, "ss"],
];

function foldForSearch(value: string): string {
  let out = value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  for (const [pattern, replacement] of FOLD_SPECIALS) {
    out = out.replace(pattern, replacement);
  }
  return out.trim();
}

/**
 * Is this selection still the default? Drives whether a reset is offered.
 *
 * Order-insensitive on purpose: a reader who removed the second line and added
 * it back has the same three players in a different order, and offering to
 * "reset" a chart that already shows the default three is an affordance that
 * does nothing.
 */
export function selectionIsDefault(
  rows: TournamentRow[],
  selection: string[]
): boolean {
  const base = defaultSelection(rows);
  if (base.length !== selection.length) return false;
  const set = new Set(selection);
  return base.every((key) => set.has(key));
}

/**
 * Toggle one contender in or out of the selection.
 *
 * Refuses to empty the chart: removing the last line leaves a titled, bordered
 * box containing nothing, which reads as a failure rather than as a choice.
 * Refuses to exceed `MAX_SERIES_COUNT` for the reason written there.
 */
export function toggleSelection(selection: string[], entityKey: string): string[] {
  if (selection.includes(entityKey)) {
    if (selection.length <= 1) return selection;
    return selection.filter((key) => key !== entityKey);
  }
  if (selection.length >= MAX_SERIES_COUNT) return selection;
  return [...selection, entityKey];
}

/**
 * Points inside a timeframe, measured back from the LATEST OBSERVATION rather
 * than from now.
 *
 * Anchoring on `now` looks more correct and is worse here: #2199 has these
 * fields dark for 8-32 days, so a "1M" window measured from today would be
 * empty for markets that have a full month of history ending three weeks ago.
 * The chart would go blank and read as "no data" when the truth is "no RECENT
 * data" — which the staleness banner is already saying, properly, in words.
 */
export function pointsInTimeframe(
  points: TournamentTrendPoint[],
  timeframe: Timeframe
): TournamentTrendPoint[] {
  if (!Array.isArray(points) || points.length === 0) return [];
  const days = TIMEFRAME_DAYS[timeframe];
  if (days === null) return points;

  const last = points[points.length - 1];
  const end = new Date(`${last.date}T00:00:00Z`).getTime();
  if (Number.isNaN(end)) return points;
  const start = end - (days - 1) * 24 * 60 * 60 * 1000;

  return points.filter((point) => {
    const at = new Date(`${point.date}T00:00:00Z`).getTime();
    return !Number.isNaN(at) && at >= start;
  });
}

/**
 * Whether a timeframe has enough data to draw. A single point is not a line,
 * and joining it to an assumed origin would draw a movement that never
 * happened — so the selector offers it disabled rather than lying.
 */
export function timeframeIsDrawable(
  series: ChartSeries[],
  timeframe: Timeframe
): boolean {
  return series.some((entry) => pointsInTimeframe(entry.points, timeframe).length >= 2);
}

export interface ChartGeometry {
  /** Shared x-domain across all series so the lines are comparable. */
  dates: string[];
  width: number;
  height: number;
  /**
   * The top of the y-axis, as a probability (#2451). Always anchored at 0.
   * See `chartCeiling` for the whole argument.
   */
  ceiling: number;
}

/**
 * ═══ THE Y-AXIS HAS A TOP NOW, AND IT SAYS WHAT IT IS (#2451) ═══
 *
 * Alex, on the TO WIN THE TITLE chart: *"renders three contender lines inside
 * roughly the bottom 15% of the plot area, with **no y-axis labels at all**.
 * Alcaraz 34.5%, Zverev 23.5%, Shelton 9.3% — all visually flat and
 * indistinguishable."* And the instruction: **"Fix the scale, do not smooth the
 * line."**
 *
 * The scale was a hard 0–100. That is the right default for a two-horse
 * question and the wrong one for a 128-player draw, where a runaway favourite
 * is 35% and the third contender is 9%: two thirds of the plot is permanently
 * empty and the whole title race is drawn in the bottom third, where a
 * ten-point gap between Alcaraz and Zverev is 13px on a phone.
 *
 * ### Zero stays. The top moves.
 *
 * The classic chart lie is a truncated baseline — cropping the bottom to
 * magnify a wiggle. That is not on the table and is not what this does: the
 * axis is ALWAYS anchored at 0, so a line's height remains proportional to the
 * probability and a player at 9% is drawn at 9% of the ceiling, not floated up
 * from a fake floor.
 *
 * What adapts is the CEILING, and only in coarse steps: 10%, 25%, 50%, 75%,
 * 100%. Coarse deliberately — a continuous fit-to-max would rescale the plot
 * every time the leader moved a point, and a chart whose axis changes daily
 * makes movement unreadable, which is the opposite of the standing ruling that
 * movement is the product. Five steps means the axis holds still for weeks at a
 * time and changes when the shape of the race genuinely changes.
 *
 * Worked on the men's board Alex was reading: max 0.345 → ceiling 0.5. Alcaraz
 * lands at 69% of the plot height instead of 34%, Zverev at 47%, Shelton at
 * 19%. The gap he could not see is now half the plot.
 *
 * ### The 75 step, and why the ladder had a cliff in it (#3032)
 *
 * The ladder shipped as 10/25/50/100, and the gap between the last two is where
 * it stopped paying. Measured on the live men's board this morning: Alcaraz at
 * **0.445** wants `0.445 × 1.15 = 0.512`, so the first step that fits is
 * **1.0** — and the entire title race draws in the bottom half with an empty
 * top half. That is #2451's own complaint arrived at from the other direction,
 * and it bites precisely when a tournament has a clear favourite, which is the
 * moment the chart is most worth reading.
 *
 * `0.75` covers leaders from 44% to 65%; Alcaraz then occupies 59% of the plot
 * instead of 44%. The ladder stays coarse — five steps is still an axis that
 * holds still for weeks — and the labels keep it honest.
 *
 * ### And it is only honest because it is LABELLED
 *
 * A moving ceiling with no y-axis labels would be strictly worse than a fixed
 * one: the reader would have no way to know the top had changed. The labels are
 * the other half of this fix, not a decoration on it — see `chartYLabels`.
 */
const CEILING_STEPS = [0.1, 0.25, 0.5, 0.75, 1] as const;

/** Room above the leader, so the top line is not welded to the frame. */
const CEILING_HEADROOM = 1.15;

export function chartCeiling(series: ChartSeries[], timeframe: Timeframe): number {
  let max = 0;
  for (const entry of series) {
    for (const point of pointsInTimeframe(entry.points, timeframe)) {
      if (Number.isFinite(point.probability) && point.probability > max) {
        max = point.probability;
      }
    }
    // The board's current number too: a contender whose history is one reading
    // draws no line, but its legend value is on screen and the axis must be
    // able to contain it. `entry.probability` is nullable where `point`'s is
    // not — a contender with no price at all — and `Number.isFinite` is not a
    // type predicate, so the null is ruled out here rather than by it.
    const current = entry.probability;
    if (current !== null && Number.isFinite(current) && current > max) {
      max = current;
    }
  }
  const wanted = max * CEILING_HEADROOM;
  return CEILING_STEPS.find((step) => step >= wanted) ?? 1;
}

/**
 * The y-axis labels, top to bottom, as `{probability, label}` (#2451).
 *
 * Three of them — top, middle, zero — and never more. This plot is 96px tall on
 * a phone; a fourth rule would be 24px from its neighbours and the labels would
 * collide. The zero line is always drawn because it is the claim the whole
 * scale rests on: a reader who can see the baseline can see that nothing has
 * been cropped.
 */
export function chartYLabels(ceiling: number): { probability: number; label: string }[] {
  return [ceiling, ceiling / 2, 0].map((probability) => ({
    probability,
    // Whole percents: the steps are 10/25/50/75/100, so halves land on
    // 5/12.5/25/37.5/50 and only the 25 and 75 cases need a decimal. `12.5%` is
    // correct and reads as precision nobody asked for on an axis label, so it
    // rounds — and the rounding is visible only on a rule the reader is using to
    // place a line, never on a number the page states as a fact.
    label: `${Math.round(probability * 100)}%`,
  }));
}

/**
 * The shared x-domain: every date any drawn series observed, sorted.
 *
 * Built as a union rather than per-series so two players' lines line up in
 * time. Giving each line its own x-scale would put Monday under Thursday and
 * make crossing lines mean nothing.
 */
export function chartGeometry(
  series: ChartSeries[],
  timeframe: Timeframe,
  width: number,
  height: number
): ChartGeometry {
  const dates = new Set<string>();
  for (const entry of series) {
    for (const point of pointsInTimeframe(entry.points, timeframe)) {
      dates.add(point.date);
    }
  }
  return {
    dates: Array.from(dates).sort(),
    width,
    height,
    ceiling: chartCeiling(series, timeframe),
  };
}

/**
 * `2026-08-12` -> whole days since the epoch, UTC. `null` for anything that is
 * not a `YYYY-MM-DD`.
 *
 * Whole days rather than milliseconds because the domain IS days — the server
 * means each outcome-day — and integer day numbers make the axis arithmetic
 * exact instead of almost-exact.
 */
function dayNumber(iso: string): number | null {
  const parsed = Date.parse(`${iso}T00:00:00Z`);
  if (!Number.isFinite(parsed)) return null;
  return Math.round(parsed / 86_400_000);
}

/**
 * THE X-SCALE: a date's position on the drawn axis, 0 at the first reading and
 * `geometry.width` at the last.
 *
 * ═══ UX-P146: THIS USED TO BE AN ORDINAL SCALE, AND THAT WAS THE BUG ═══
 *
 * Alex, on the UX-P145 desktop artifact: the headline chart's x-axis has weird
 * spacing. It did, and here is the arithmetic on the real men's board
 * (`docs/mocks/us-open/payload-2026-08-27.json`), which carries 23 observed
 * dates: 2026-07-28 through 2026-08-17 daily, then an EIGHT-DAY HOLE, then
 * 08-26 and 08-27.
 *
 * The old scale placed a point at `index / (dates.length - 1)` — its position
 * in the LIST of observed dates, not its position in time. So:
 *
 *   - 08-08 sat at exactly 50%, and was labelled as the middle of the window.
 *     The true midpoint of 28 Jul → 27 Aug is 12 Aug. The axis was four days
 *     out and said so with a date.
 *   - The last nine calendar days (18 Aug → 27 Aug) got 2 of 22 steps — 9% of
 *     the width — while the eleven days 28 Jul → 08 Aug got 50% of it. Two
 *     stretches of comparable length, drawn at a 5:1 difference in scale.
 *   - The eight-day hole was drawn as one ordinary step, indistinguishable
 *     from a single overnight move.
 *
 * The old note defended this: "gaps stay gaps, and the axis agrees with the
 * line about where they are." The axis did agree with the line — they were
 * wrong together. And it is the exact inverse of what this module means by
 * gaps staying gaps (no interpolated point, ever): an ordinal scale does not
 * preserve a gap, it DELETES it, by drawing eight missing days at the width of
 * one observed one.
 *
 * So x is calendar time. A month-long window and a day-long window are now
 * different shapes rather than the same shape with different labels.
 */
export function dateX(iso: string, geometry: ChartGeometry): number | null {
  const dates = geometry.dates;
  if (dates.length < 2) return null;
  const at = dayNumber(iso);
  const first = dayNumber(dates[0]);
  const last = dayNumber(dates[dates.length - 1]);
  if (at === null || first === null || last === null) return null;
  // `dates` is a sorted set, so two or more entries means last > first and the
  // divide-by-zero this would otherwise need a guard for cannot happen.
  if (last === first) return null;
  return ((at - first) * geometry.width) / (last - first);
}

/**
 * One series as SVG polyline points, on a ZERO-ANCHORED y-axis whose top is
 * `geometry.ceiling` (#2451 — see `chartCeiling`).
 *
 * Returns "" for fewer than two points. x is the point's position in CALENDAR
 * TIME across the shared domain (see `dateX`), so a series that started late
 * begins part-way across instead of being stretched to fill the width, and two
 * readings a fortnight apart are drawn a fortnight apart.
 */
export function seriesPoints(
  entry: ChartSeries,
  geometry: ChartGeometry,
  timeframe: Timeframe
): string {
  const points = pointsInTimeframe(entry.points, timeframe);
  if (points.length < 2 || geometry.dates.length < 2) return "";

  return points
    .map((point) => {
      // Still gated on membership of the shared domain: a reading the domain
      // does not carry is a reading outside the drawn window, and placing it by
      // date alone would draw it off the end of the plot.
      if (!geometry.dates.includes(point.date)) return null;
      const x = dateX(point.date, geometry);
      if (x === null) return null;
      // Clamped to the CEILING, not to 1. A reading above the top of the axis
      // would otherwise be drawn off the plot; `chartCeiling` picks a step that
      // contains every point, so this only fires on a non-finite value.
      const top = geometry.ceiling > 0 ? geometry.ceiling : 1;
      const clamped = Math.max(0, Math.min(top, point.probability));
      const y = geometry.height - (clamped / top) * geometry.height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter((value): value is string => value !== null)
    .join(" ");
}

/**
 * How wide a window a tick's label needs before it is worth drawing (UX-P147).
 *
 * The axis is one set of ticks rendered into a plot whose real width runs from
 * ~358px on a phone to ~817px at `2xl`, and this module cannot measure a
 * viewport — the chart is server-rendered and the capture rig renders it
 * through `renderToStaticMarkup`, where no viewport exists at all. So density
 * is expressed as a TIER on each tick and spent by a CSS breakpoint at the call
 * site, which is the same trick `GRID_SIZING` uses for the grid's two widths.
 *
 * UX-P207 dropped a fourth member, `end`. It existed because the first and last
 * OBSERVED dates were placed unconditionally; they are not placed at all now,
 * and a tier that names a rule nobody applies is a trap for the next reader.
 */
export type AxisTickTier = "major" | "wide" | "fine";

export interface AxisTick {
  /** ISO date, `YYYY-MM-DD` — the calendar value the tick names. */
  date: string;
  /** Where it sits on the drawn x-axis, in viewBox units. */
  x: number;
  /** `26 Aug` — short enough for a 320-unit axis at three ticks. */
  label: string;
  /** Narrowest window this tick earns its label in — see `axisTicks`. */
  tier: AxisTickTier;
}

/**
 * ═══ UX-P207: THE AXIS IS A CALENDAR GRID, NOT A SAMPLE OF THE DATA ═══
 *
 * Alex, on the live `/tournaments/us-open` on opening day: *"The x-axis in the
 * chart is weird."* It was, and this is the exact sequence he read, reproduced
 * from the production payload (men's board, 16 observed dates, 1 Aug → 31 Aug)
 * against the axis this replaces, at `lg`:
 *
 *   1 Aug ── 6 Aug ─ 10 Aug ─────────────────────────── 26 Aug ── 31 Aug
 *   0%       16.7%    30.0%                              83.3%     100%
 *   gaps:      16.7    13.3            53.3                16.7
 *
 * Four labels in the first third, then a 53%-wide stretch of axis with nothing
 * on it. A reader cannot use that: the eye reads regular ticks as a ruler, so
 * an irregular one does not say "these are the days we have readings for", it
 * says "this chart is broken".
 *
 * ═══ THE CAUSE WAS THE ONE RULE EVERY EARLIER PASS PROTECTED ═══
 *
 * UX-P139 through UX-P147 all held that *an axis tick must label a day
 * something was actually read*, so each candidate position was SNAPPED to the
 * nearest observed date. That rule is what bends the axis. This board has a
 * **fifteen-day hole** (11 Aug → 25 Aug, no readings), and every candidate
 * inside it snaps back to 10 Aug or forward to 26 Aug, collides with the tick
 * already there, and is dropped. The hole gets no labels at all, and the
 * labels that survive cluster wherever the data happens to be dense — so the
 * axis's spacing is a picture of the SAMPLING, drawn on top of a plot whose
 * x is calendar time. Two different scales in one strip.
 *
 * So the rule is reversed, deliberately: **ticks are calendar positions, and
 * a tick may name a day nothing was read.** That is what a time axis is. It
 * costs nothing true — the LINE still has no point in the hole, gaps still stay
 * gaps — and it buys the thing the hole was hiding: with `17 Aug` and `24 Aug`
 * on the axis, the fifteen-day hole is legible AS fifteen days. Under the old
 * rule the same hole was an unlabelled void that could have been any length.
 *
 * ═══ THE STEP, AND WHY IT IS A CALENDAR NUMBER ═══
 *
 * One step for the whole axis, taken from `STEP_LADDER_DAYS` — the smallest
 * rung that divides the window into at most `MAX_INTERVALS` — and every tick
 * is a whole number of steps back from the LATEST reading. Anchoring on the
 * latest rather than on a calendar boundary (a Monday, a 1st) is deliberate:
 * the newest reading is where the endpoint dot is and where the reader's eye
 * starts, so it is the one position that must carry a label. The cost is that
 * the leftmost tick can sit up to one step inside the left edge — 2 of 30 days
 * on the men's board, 6.7% of the plot — which is what a real time axis looks
 * like and is not what Alex was pointing at.
 *
 * The ladder is `1, 2, 7, 14, 28, 91, 182, 364`: days, then weeks, then
 * quarters, then a year. Nothing between 2 and 7, because a 3-, 4- or 5-day
 * step produces labels a reader cannot count in their head. On today's data
 * this lands where the directive asked it to — **weekly for the month-long
 * men's window, daily for the six-day women's one** — without the timeframe
 * button having to say so, which matters because the button cannot: `ALL` on
 * the women's board is five days, and a table keyed on `1M`/`ALL` would give
 * that five-day window a monthly step.
 *
 * `1D` is in the ladder's reach and unreachable in practice: the server's trend
 * series carries one point per DAY (`TournamentTrendPoint.date`), so a one-day
 * window holds one point, `timeframeIsDrawable` is false, and the button
 * renders disabled. An hourly axis needs an hourly series first — named here
 * so the next reader does not go looking for the bug.
 *
 * ═══ THE THREE DENSITIES, FROM ONE SERVER RENDER ═══
 *
 * Unchanged in spirit from UX-P147 and unchanged in mechanism: this module
 * cannot measure a viewport (the chart is server-rendered, and the capture rig
 * has no viewport at all), so each tick carries the tier naming the narrowest
 * plot its label fits in and `ContenderChart` spends the tiers with `lg:` and
 * `2xl:`. What changed is how a tier is decided. It used to be a property of
 * the SLOT (`k % 4`), which is why the count could not respond to the data;
 * it is now a STRIDE computed from the label pitch — take every tick at `2xl`,
 * every `n`th at `lg`, every `m`th on a phone, with `m` a multiple of `n` so
 * the phone's axis is always a SUBSET of the desktop's at identical positions.
 * A stride keeps the spacing even at every width, which a per-slot tier could
 * not promise and, on this data, did not deliver (the women's board showed
 * 40/20/40 on a phone).
 */

/**
 * Plot width, in px, that each tier's breakpoint first gives this chart.
 *
 * ⚠️ **THESE ARE MEASURED, NOT DERIVED, AND THAT IS THE POINT (#3520).** They
 * used to be read off `ContenderChart`'s viewBox note, which computes the plot
 * from the window width by subtracting the shell's gutters. That arithmetic was
 * right at `lg` and `2xl` and wrong on a phone — it put the phone plot at 358px
 * when it is ~305px, a 17% overstatement, because the tournament page carries
 * ~28px of its own horizontal padding at that width which the chain never
 * subtracted. The axis therefore believed it had room for eight daily labels
 * across the US Open's 7-day window, emitted all eight, and `30 Aug` and
 * `31 Aug` overprinted into one 11-character non-word on both draws.
 *
 * Re-measured off production screenshots at each breakpoint (DPR 2, so CSS px
 * is half the image px), by finding the chart card's own left and right border
 * columns and taking off the 1px borders and the `px-3.5` padding:
 *
 *   390px  → card border cols 56/723   → 334 − 2 − 28 = ~305px   (was 358)
 *   1024px → card border cols 96/1125  → 515 − 2 − 28 = ~485px   (said 486)
 *   1600px → card border cols 96/1787  → 846 − 2 − 28 = ~816px   (said 817)
 *
 * Artifacts: `artifacts-live-074/usopen-lg.png`, `usopen-2xl.png`, and
 * `artifacts-live-073/usopen-womens.png` for the phone. Cross-checked against
 * the rendered tick pitch in each shot (43.4 / 69.3 / 116.5 CSS px over the same
 * 7 intervals), which agrees to within a pixel. The two desktop numbers are left
 * exactly as they were: they were already right, and moving them by the 1px of
 * measurement noise would be pretending to a precision this has not got.
 *
 * If the page's gutters change, RE-MEASURE — do not re-derive. The derivation is
 * what was wrong.
 */
export const TIER_PLOT_PX: Record<AxisTickTier, number> = {
  major: 305,
  wide: 486,
  fine: 817,
};

/**
 * The widest label this axis can print, in px.
 *
 * `30 Aug` at `text-[9.5px]`: two tabular digits, a space, and a three-letter
 * month. Measured at 31.1px off the production crop (`crop-axis-labels.png`,
 * a 3x crop of a DPR-2 shot, so 6x — the ink runs divide out), rounded up. A
 * one-digit day (`6 Sep`) is ~25px; the widest is the one the budget must clear.
 */
export const AXIS_LABEL_MAX_PX = 32;

/**
 * How far a label may hang past the plot into the card's own padding, in px.
 *
 * The card is `px-3.5` (14px), so 12px of bleed still leaves the label 2px clear
 * of the border — it stays inside the card, which is the bound that matters, and
 * `#3525` is the same family of bug on the other chart caught the other way.
 *
 * This exists to buy back the pitch that the edge alignment spends; see
 * `LABEL_PITCH_PX`.
 */
export const AXIS_LABEL_BLEED_PX = 12;

/**
 * How far the first and last labels must move INWARD to stay inside the bleed.
 *
 * A centred label at the very edge of the plot hangs half its width past it. The
 * bleed absorbs `AXIS_LABEL_BLEED_PX` of that; whatever is left over is a nudge
 * the renderer applies, and a cost the pitch below has to carry.
 */
export const AXIS_LABEL_NUDGE_PX = Math.max(
  0,
  AXIS_LABEL_MAX_PX / 2 - AXIS_LABEL_BLEED_PX
);

/** Minimum air between two neighbouring labels, in px. */
const LABEL_AIR_PX = 8;

/**
 * Centre-to-centre px two neighbouring labels need.
 *
 * ═══ WHY THIS IS DERIVED NOW AND NOT A BARE `44` (#3520) ═══
 *
 * It was a bare 44 with a note about `26 Aug` being ~30px and 44 leaving "14px
 * of air". That reasoning is sound **for two centred labels** and it is the only
 * case it ever considered — but `ContenderChart` does not centre all of them.
 * The first and last are clamped so they cannot hang off the card, which shoves
 * each one HALF A LABEL inward, toward the neighbour it is already closest to.
 * So the two edge pairs are ~16px tighter than every interior pair, and the
 * budget never knew. On the US Open's 7-day window that is exactly where the
 * overprint landed — not in the middle of the axis, at both ends of it.
 *
 * The honest requirement, for the worst pair (both labels full width):
 *
 *   interior:  pitch ≥ w/2 + w/2 + air              = 32 + 8      = 40
 *   at an edge: pitch ≥ (w/2 + nudge) + w/2 + air   = 32 + 4 + 8  = 44
 *
 * So 44 was never wrong about the number — it was wrong about which pair it
 * described, and it only survives as 44 BECAUSE of the bleed. Take the bleed
 * away and the edge requirement is 32 + 16 + 8 = 56, which is what the axis was
 * actually being asked to do with 44px of budget.
 *
 * Both halves are guarded, and the guard measures a rendered tick set at 305px
 * rather than re-deriving this expression — a guard that recomputes the thing it
 * is checking agrees with it by construction and catches nothing.
 */
const LABEL_PITCH_PX =
  AXIS_LABEL_MAX_PX + AXIS_LABEL_NUDGE_PX + LABEL_AIR_PX;

/** Calendar steps a person can count in their head. Ascending. */
const STEP_LADDER_DAYS = [1, 2, 7, 14, 28, 91, 182, 364];

/** The most intervals the finest tier will draw across the window. */
const MAX_INTERVALS = 12;

/**
 * The tick step for a window, in days — the smallest ladder rung that keeps the
 * axis under `MAX_INTERVALS` intervals.
 *
 * Exported because it is the sentence the axis is built on, and a guard that
 * has to re-derive it from rendered tick positions is testing arithmetic it
 * just re-implemented.
 */
export function axisStepDays(spanDays: number): number {
  for (const step of STEP_LADDER_DAYS) {
    if (spanDays / step <= MAX_INTERVALS) return step;
  }
  return STEP_LADDER_DAYS[STEP_LADDER_DAYS.length - 1];
}

/**
 * How many steps apart two labels must be, per tier, so neither pair overlaps.
 *
 * The coarser strides are rounded UP onto a multiple of the finer one. That
 * rounding is what keeps each tier's own set of labels EVENLY SPACED: the set a
 * screen shows is `{k : k % major === 0}` ∪ `{k : k % wide === 0}`, and unless
 * `major` is a multiple of `wide` that union has two different gaps in it. With
 * `major = 3, wide = 2` the `lg` axis reads 0, 2, 3, 4, 6, 8, 9 — which is the
 * ragged axis this queue exists to remove, arrived at from the other direction.
 *
 * ⚠️ **AT `MAX_INTERVALS = 12` THE ROUNDING IS UNREACHABLE, AND IT STAYS.** The
 * ladder guarantees `fractionPerStep ≥ 1/12`, so `needed` is at most
 * `ceil(44 / (358/12)) = 2` for every tier and at least 1 — and every pair
 * drawn from `{1, 2}` with `major ≥ wide` already nests. The line is therefore
 * dead code TODAY and load-bearing the moment anyone raises `MAX_INTERVALS` or
 * widens `LABEL_PITCH_PX`, which is exactly when nobody will be thinking about
 * it. `axisTickStrides` is exported so the property can be asserted directly
 * rather than through an `axisTicks` call that cannot reach it — a guard that
 * routes through the unreachable path is a guard that passes for the wrong
 * reason.
 */
export function axisTickStrides(
  fractionPerStep: number
): Record<AxisTickTier, number> {
  return tickStrides(fractionPerStep);
}

function tickStrides(fractionPerStep: number): Record<AxisTickTier, number> {
  const needed = (tier: AxisTickTier) =>
    Math.max(1, Math.ceil(LABEL_PITCH_PX / (fractionPerStep * TIER_PLOT_PX[tier])));
  const fine = needed("fine");
  const wide = fine * Math.ceil(needed("wide") / fine);
  const major = wide * Math.ceil(needed("major") / wide);
  return { major, wide, fine };
}

/** `2026-08-12` from a whole-day count since the epoch. Inverse of `dayNumber`. */
function isoFromDay(day: number): string {
  return new Date(day * 86_400_000).toISOString().slice(0, 10);
}

export function axisTicks(geometry: ChartGeometry, timeframe?: Timeframe): AxisTick[] {
  // The step comes from the DRAWN WINDOW, not from which button is pressed —
  // see the note above on `ALL` over a five-day field.
  void timeframe;
  const dates = geometry.dates;
  if (dates.length < 2) return [];

  const firstDay = dayNumber(dates[0]);
  const lastDay = dayNumber(dates[dates.length - 1]);
  if (firstDay === null || lastDay === null || lastDay <= firstDay) return [];

  const span = lastDay - firstDay;
  const step = axisStepDays(span);
  const strides = tickStrides(step / span);

  const out: AxisTick[] = [];
  /** The `k` each emitted tick was generated at, parallel to `out`. */
  const steps: number[] = [];
  // `k` counts steps back from the LATEST reading, so `k = 0` is the right-hand
  // edge and is visible at every width (0 is a multiple of every stride).
  for (let k = 0; lastDay - k * step >= firstDay; k += 1) {
    const tier =
      k % strides.major === 0 ? "major" : k % strides.wide === 0 ? "wide"
      : k % strides.fine === 0 ? "fine" : null;
    if (tier === null) continue;
    const date = isoFromDay(lastDay - k * step);
    out.push({
      date,
      x: ((lastDay - k * step - firstDay) * geometry.width) / span,
      label: shortDateLabel(date),
      tier,
    });
    steps.push(k);
  }

  pinOldestLabel(out, steps, strides.major);

  return out.reverse();
}

/**
 * ═══ THE OLDEST TICK CARRIES A LABEL AT EVERY WIDTH (#3520) ═══
 *
 * A stride anchored on the newest reading labels `k = 0, S, 2S, …`, and it only
 * lands on the oldest tick when the tick count happens to be a multiple of `S`.
 * When it does not, the axis's leftmost DRAWN tick has no label on a phone, and
 * the chart contradicts itself: the footer says `7d shown`, the axis reads
 * `31 Aug … 6 Sep`, and a reader counting the axis gets six.
 *
 * So the oldest emitted tick is promoted to `major`. The module already holds
 * that the NEWEST must always be labelled ("where the endpoint dot is and where
 * the reader's eye starts"); this is the same claim about the other end, which a
 * window chart needs at least as much — the left edge is the only thing on the
 * page that says how far back the window reaches.
 *
 * ⚠️ **THE PROMOTION COSTS THE EVEN SPACING, AND THAT IS THE TRADE.** Promoting
 * `k = K` without demoting anything would put a label one step from the label at
 * `k = K − (K mod S)`, which is the overprint this queue exists to remove,
 * re-created at the far end. So the neighbour is demoted to `wide` — it keeps
 * its label from `lg` up, where there is room for both. The phone axis is
 * therefore even everywhere except its leftmost gap, which is `(K mod S) + S`
 * steps instead of `S`: strictly less than double, and the price of the axis
 * agreeing with the footer. UX-P207's even-spacing rule still governs every
 * other pair, and the guard asserts the exception is exactly this one pair and
 * not a general licence to be ragged.
 *
 * `k = 0` is never demoted — if the only major near the oldest tick IS the
 * newest, the pin is abandoned rather than trade one endpoint for the other.
 */
function pinOldestLabel(
  ticks: AxisTick[],
  steps: number[],
  majorStride: number
): void {
  const oldest = ticks.length - 1;
  if (oldest <= 0 || ticks[oldest].tier === "major") return;

  // Scan toward the newest for the nearest tick that already has a label.
  let neighbour = -1;
  for (let i = oldest - 1; i >= 0; i -= 1) {
    if (ticks[i].tier === "major") {
      neighbour = i;
      break;
    }
  }
  if (neighbour < 0) return;
  if (steps[oldest] - steps[neighbour] >= majorStride) {
    // Already a full stride clear — promote and leave the neighbour alone.
    ticks[oldest].tier = "major";
    return;
  }
  // Too close to coexist on a phone, and `k = 0` is not ours to give up.
  if (steps[neighbour] === 0) return;
  ticks[oldest].tier = "major";
  ticks[neighbour].tier = "wide";
}

/** `2026-08-26` -> `26 Aug`. Day-first, because the month repeats and the day does not. */
export function shortDateLabel(iso: string): string {
  const [year, month, day] = (iso || "").split("-").map(Number);
  if (!year || !month || !day) return iso;
  const months = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return `${day} ${months[month - 1] ?? ""}`.trim();
}

/**
 * How long the drawn window actually is, in days — the sentence beside the
 * ticks.
 *
 * Three dates on an axis tell a reader WHERE they are; "30 days" tells them how
 * much of the story they are looking at, which is the question the timeframe
 * buttons are answering and which the buttons alone cannot confirm (`ALL` on a
 * field with four readings is four days, not all of history).
 */
/**
 * The drawn window's two ends, labelled — `{ from: "1 Aug", to: "31 Aug" }`.
 *
 * UX-P207. The accessible label used to name the FIRST AND LAST TICK as the
 * window's bounds, which was true only because the axis pinned ticks to the
 * domain's ends. It does not any more, so a screen reader would have been told
 * the chart covers "3 Aug to 31 Aug" while the sighted footer beside it said
 * "30d shown" — the same disagreement, in two modalities, that this queue
 * exists to remove. Both now read the DOMAIN, from one function, and the ticks
 * are what they always should have been: positions inside the window, not the
 * definition of it.
 */
export function axisWindow(
  geometry: ChartGeometry
): { from: string; to: string } | null {
  const dates = geometry.dates;
  if (dates.length < 2) return null;
  return {
    from: shortDateLabel(dates[0]),
    to: shortDateLabel(dates[dates.length - 1]),
  };
}

export function axisSpanDays(geometry: ChartGeometry): number | null {
  const dates = geometry.dates;
  if (dates.length < 2) return null;
  const first = Date.parse(`${dates[0]}T00:00:00Z`);
  const last = Date.parse(`${dates[dates.length - 1]}T00:00:00Z`);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
  return Math.max(0, Math.round((last - first) / 86_400_000));
}

/** The last plotted coordinate — the reference's endpoint dot. */
export function seriesEndpoint(
  entry: ChartSeries,
  geometry: ChartGeometry,
  timeframe: Timeframe
): { x: number; y: number } | null {
  const drawn = seriesPoints(entry, geometry, timeframe);
  if (drawn === "") return null;
  const last = drawn.split(" ").pop();
  if (!last) return null;
  const [x, y] = last.split(",").map(Number);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return { x, y };
}

/**
 * ═══ THE `+33` SAYS WHICH WINDOW IT MEASURES (#3033) ═══
 *
 * On the men's board, in one frame: the chart opens on `Draw`, its footer says
 * "6d shown · 30 Aug – 5 Sep", and Alcaraz's line climbs about 19 points across
 * it. The row directly under it reads **+33.4**.
 *
 * Both numbers are correct. `trend_delta` is measured over the row's WHOLE
 * tracked history — verified against the wire, it is exactly
 * `trend[last] − trend[0]` (Alcaraz 0.334374 = 0.456374 − 0.122) — and the chart
 * is showing the tournament. They sit six points apart on one card and the only
 * thing that reconciles them is a footer the reader has to notice and then
 * reason about.
 *
 * This is the cheap honest fix: the board says, once, what its movement column
 * measures. Making the badge FOLLOW the chart's range is truer and is not this
 * — it needs the selected range lifted out of `ContenderChart`'s own state, and
 * it is a bigger change than the disagreement warrants.
 *
 * **It is computed over the rows on screen, and it is not one date per board.**
 * The obvious version of this — one window stated once for the whole board —
 * is wrong, and measurably so: on the live men's board 23 rows start 6 Aug, 12
 * start 26 Aug and one starts 7 Aug, because a contender's history begins when
 * a market first priced them. So when the visible rows agree the note names
 * their shared date, and when they do not it says so rather than picking one
 * row's date and printing it over the others. Expanding the board can therefore
 * change the sentence, which is the truth changing, not the copy wobbling.
 */
export function deltaWindowNote(rows: TournamentRow[]): string | null {
  const starts = new Set<string>();
  for (const row of rows) {
    // A row with no delta shown contributes no claim to reconcile.
    if (row.trend_delta === null) continue;
    const first = row.trend?.[0]?.date;
    if (first) starts.add(first);
  }
  if (starts.size === 0) return null;
  if (starts.size > 1) return "Movement since each contender's first number.";
  const [only] = Array.from(starts);
  return `Movement since ${shortDateLabel(only)}.`;
}

/** Short legend name: `Aryna Sabalenka` -> `A. Sabalenka`. */
export function legendName(displayName: string): string {
  const parts = displayName.trim().split(/\s+/);
  if (parts.length < 2) return displayName;
  const surname = parts.slice(1).join(" ");
  return `${parts[0][0]}. ${surname}`;
}
