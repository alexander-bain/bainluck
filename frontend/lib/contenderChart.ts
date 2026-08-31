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
  return { dates: Array.from(dates).sort(), width, height };
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
 * One series as SVG polyline points on a FIXED 0-100 y-axis.
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
      const clamped = Math.max(0, Math.min(1, point.probability));
      const y = geometry.height - clamped * geometry.height;
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

/** Plot width, in px, that each tier's breakpoint first gives this chart. */
const TIER_PLOT_PX: Record<AxisTickTier, number> = {
  // Measured on the same element `lg:h-40` / `2xl:h-56` were measured against
  // (see `ContenderChart`'s viewBox note for the end-to-end arithmetic): ~358px
  // on a phone, ~486px at `lg`, ~817px at `2xl`.
  major: 358,
  wide: 486,
  fine: 817,
};

/**
 * Centre-to-centre px two neighbouring labels need.
 *
 * A `26 Aug` label is ~30px at `text-[9.5px]` in tabular figures (6 glyphs, and
 * tabular means the widest date is the same width as the narrowest). 44 leaves
 * 14px of air, which is more than the 8px the previous pass budgeted, because
 * this axis puts labels at even intervals — if the pitch is wrong here it is
 * wrong for EVERY pair on the axis rather than for one unlucky snap.
 */
const LABEL_PITCH_PX = 44;

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
  }

  return out.reverse();
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

/** Short legend name: `Aryna Sabalenka` -> `A. Sabalenka`. */
export function legendName(displayName: string): string {
  const parts = displayName.trim().split(/\s+/);
  if (parts.length < 2) return displayName;
  const surname = parts.slice(1).join(" ");
  return `${parts[0][0]}. ${surname}`;
}
