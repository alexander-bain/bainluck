/**
 * THE PLAYOFF GRID — players × rounds, read from the server, computed nowhere.
 *
 * ═══ WHAT UX-P139 CHANGED, AND WHY IT IS A REWRITE ═══
 *
 * UX-P138's grid assembled itself HERE, in the browser, from three unrelated
 * payload sections: the match list for the next round, the curated props for
 * the middle, the board for the title. It refused to compute — that part was
 * right — but its coverage was whatever those three happened to contain, so
 * the middle was holes. Alex read a row with a quarter-final number, a title
 * number, and nothing between them, and named it correctly:
 *
 *     "GRID GAPS ARE A DEALBREAKER ... a blank cell, an improperly blended
 *     cell, or a cell populated from the WRONG future is a linkage defect — no
 *     excuse, no interpolation. The derived-value fallback is retired: a cell
 *     whose direct markets are not linked renders as an ALARM STATE naming the
 *     missing linkage ... The register carries per-player per-round market IDs
 *     from BOTH sources; the grid reads only the register."
 *
 * "The grid reads only the register" is not something a client can promise
 * while stitching three sections together, so the build moved to the server —
 * `backend/app/utils/tournament_grid.py`, which walks `register.reaches` and
 * nothing else. This module is now a TYPED READER plus the display rules, and
 * it holds no cell-resolution logic at all. That absence is the feature: there
 * is no code path here that could put a number in a cell.
 *
 * ═══ WHAT THIS FILE STILL DECIDES ═══
 *
 * How wide the grid is (it scrolls rather than dropping a column — ruling 5),
 * what each state looks like in words, and how the two evals are worded for a
 * reader. Nothing numeric.
 */

/** The five cell states. Mirrors `tournament_grid.py`; there is no sixth. */
export type GridCellState =
  | "live"
  | "stale"
  | "dark"
  | "settled"
  | "no_market"
  /** ALARM: the register pins a market for this cell and it did not price. */
  | "unlinked"
  /** ALARM: no cell registered for this player × round. Nobody censused it. */
  | "unregistered";

import { isMarked, liquidityReveal, readLiquidity } from "./liquidity";
import type { PlayerImage } from "./slate";

export interface GridCellSource {
  source: string;
  probability?: number | null;
  age_hours?: number | null;
  price_state?: string;
  market_external_id?: string | null;
  state?: string;
}

export interface GridCell {
  state: GridCellState;
  probability: number | null;
  probability_is_live: boolean;
  sources: GridCellSource[];
  source_count: number;
  observed_at: string | null;
  age_hours: number | null;
  blend_rule: string | null;
  divergent: boolean;
  /** What is wrong / what is absent, in words. Always set on a failure state. */
  note: string | null;
  /** When both sources were last asked about this cell. */
  censused_at: string | null;
  is_alarm: boolean;
  freshest_observed_at?: string | null;
  partially_unlinked?: boolean;
  /** UX-P157. How thin the market behind this cell is — see `lib/liquidity`. */
  liquidity?: string | null;
  liquidity_reasons?: string[] | null;
}

export interface GridColumn {
  key: string;
  /** "SF" — the header a phone can fit. */
  short_label: string;
  /** "To reach the semi-finals" — the sentence, for `title=` and sr-only. */
  long_label: string;
  kind: "reach" | "title";
  /** How many players the round admits — the sum check's denominator. */
  slots: number | null;
}

export interface GridRow {
  entityKey: string;
  displayName: string;
  seed: number | null;
  /** Register-pinned face + flag (Alex's ruling 8). Read, never resolved. */
  image: PlayerImage | null;
  rank: number | null;
  /** On the championship board, so the title column is answerable for them. */
  onBoard: boolean;
  cells: Record<string, GridCell>;
}

export interface GridColumnSum {
  key: string;
  short_label: string;
  sum: number;
  expected: number | null;
  ratio: number | null;
  priced_rows: number;
  total_rows: number;
  verdict: "pass" | "over" | "under" | "unchecked";
}

export interface GridMonotonicityViolation {
  entity_key: string;
  display_name: string;
  earlier: string;
  later: string;
  earlier_probability: number;
  later_probability: number;
}

/** The server's shape, verbatim. */
export interface PlayoffGridPayload {
  draw: string;
  label: string;
  columns: GridColumn[];
  rows: {
    entity_key: string;
    display_name: string;
    seed: number | null;
    image?: PlayerImage | null;
    rank: number | null;
    on_board: boolean;
    cells: Record<string, GridCell>;
  }[];
  counts: Record<string, number>;
  total_cells: number;
  priced_cells: number;
  no_market_cells: number;
  alarm_cells: number;
  column_sums: GridColumnSum[];
  monotonicity_violations: GridMonotonicityViolation[];
}

export interface PlayoffGrid {
  draw: string;
  label: string;
  columns: GridColumn[];
  rows: GridRow[];
  counts: Record<string, number>;
  totalCells: number;
  pricedCells: number;
  noMarketCells: number;
  alarmCells: number;
  columnSums: GridColumnSum[];
  monotonicityViolations: GridMonotonicityViolation[];
}

/**
 * ALEX'S RULING 3, applied. "Priced to get there" is gambling vocabulary —
 * *priced* is a trading verb and *get there* is a bet's payoff condition. This
 * is the probability sentence for the same fact.
 */
export const GRID_SECTION_LABEL = "Chance of reaching";

/**
 * How wide a numeric column is, and what a name needs beside it.
 *
 * Measured against the layout rather than chosen: `100%` in tabular figures
 * with breathing room needs 46px, and a real surname with a seed badge
 * ("Auger-Aliassime [11]") needs ~118px before it truncates.
 */
export const GRID_NAME_WIDTH_PX = 118;
export const GRID_COLUMN_WIDTH_PX = 46;

/**
 * The same two measurements taken again for a desktop window (UX-P145).
 *
 * Alex: the bracket looked "like we only made a mobile version", and it did,
 * because 118/46 are the widths a 390px phone can spare and nothing above ever
 * asked for different ones. In a 1024px+ window they are not thrifty, they are
 * wrong: a five-column table using 348 of 1100 available pixels reads as broken
 * rather than as compact, and it truncates "Auger-Aliassime" to buy space that
 * is already there.
 *
 * 236 is the widest real name plus a seed badge at the desktop type size with
 * nothing clipped; 84 fits "100%" in the larger tabular figures with the same
 * breathing room 46 gives the small ones. They are applied as CSS variables and
 * a `lg:` override rather than by measuring the viewport in JS — a hook would
 * make the first client render disagree with the server's and the capture rig
 * renders through `renderToStaticMarkup`, where no viewport exists at all.
 */
export const GRID_NAME_WIDTH_DESKTOP_PX = 236;
export const GRID_COLUMN_WIDTH_DESKTOP_PX = 84;

/**
 * THE TWO THINGS THE ROW IS ALSO MADE OF (#3072).
 *
 * A grid row is not only its tracks. `PlayoffGrid`'s header and every `<li>`
 * carry `gap-1.5` between tracks and `px-3.5` down each side, and both were
 * missing from `gridWidthPx` below — which is how a five-column men's draw came
 * to be declared a fit inside a box it overflows by 74px.
 *
 * These are the Tailwind classes' own values (`gap-1.5` = 0.375rem = 6px,
 * `px-3.5` = 0.875rem = 14px), so they are a transcription rather than a
 * judgement, and `playoffGrid.test.tsx` pins them against the component's class
 * string in the same way `GRID_SIZING` is pinned.
 */
export const GRID_GAP_PX = 6;
export const GRID_ROW_PADDING_PX = 14;

/**
 * ALEX'S RULING 5: "Wide rounds may scroll horizontally — sparingly, better
 * than excluding data."
 *
 * UX-P138 capped the grid at three reach columns and reported the drop. That
 * cap is what produced the defect in ruling 4 — the second-week grid "jumped
 * QF→title" because SF was the fourth column and did not fit. The ruling
 * overturns the trade: a column is never dropped, and a grid wider than the
 * viewport scrolls.
 *
 * `sparingly` is honoured by the arithmetic rather than by restraint — and the
 * arithmetic has to be RIGHT, which until #3072 it was not. See the correction
 * below `gridScrolls`.
 *
 * ═══ UX-P145: THIS IS A RULE ABOUT PHONES, AND IT SAYS SO NOW ═══
 *
 * Alex: "P138's horizontal-scroll ruling applies to mobile, not a 1400px
 * window." The `358` default is the 390px phone's content box and always was —
 * the ruling was verdicted on that capture. What was missing is that nothing
 * stopped it applying at 1400px too, where a five-column table has a thousand
 * spare pixels and scrolling it is absurd.
 *
 * The fix is not to weaken this function; it stays exactly as measured and its
 * verdict is still what the phone gets. Desktop simply never reaches the
 * question: `PlayoffGrid` sizes its columns with `minmax(var(--grid-col-w),
 * 1fr)`, so above `lg` the grid fills whatever width it is given and there is
 * nothing to scroll. Scroll survives where it was written for and expires where
 * it was not, with no second source of truth about widths.
 */
/**
 * The measured inner width of the grid card at a 390px phone viewport.
 *
 * Not derived from 390 by subtracting guesses — read off production with a
 * pinned viewport (see `gridScrolls`), because every previous attempt to derive
 * it lost a padding somewhere.
 */
export const GRID_CARD_CONTENT_PX = 332;

/**
 * ═══ #3072: BOTH SIDES OF THIS INEQUALITY WERE OPTIMISTIC, AND THE READER PAID
 * ═══ FOR IT WITH THE ONE COLUMN THE PAGE EXISTS TO SHOW.
 *
 * Measured on production, `/tournaments/us-open` → Bracket, pinned 390px
 * viewport (`isMobile: false` — with `isMobile: true` Chromium widens the layout
 * viewport to the content and the page reads clean, so that mode cannot see
 * this class of bug at all):
 *
 *     innerWidth                   390
 *     documentElement.scrollWidth  421     ← the PAGE scrolled sideways by 31px
 *     grid card   clientWidth      332     scrollWidth 392   overflow-x: hidden
 *     "Title" header, right edge   421     — outside its own card, and CLIPPED
 *
 * `overflow-x: hidden` clips without scrolling, so 60px of the men's grid was
 * not merely off-screen, it was UNREACHABLE: no swipe, no scrollbar. The column
 * lost was **Title** — the chance of winning the tournament.
 *
 * The verdict came out wrong because the model of a row was wrong on both sides:
 *
 * - `gridWidthPx` counted TRACKS ONLY. A row is `px-3.5` + track + `gap-1.5` +
 *   track + … so five columns need `118 + 5×46 + 5×6 + 2×14 = 406px`, not 348.
 * - the `358` content box was the phone's page width minus its own padding, but
 *   the grid sits inside a CARD inside that page: the measured client box is
 *   **332**.
 *
 * 406 > 332, so the men's five-column draw scrolls — and so does a four-column
 * one (`354 > 332`), which is the honest answer too: the old formula said a
 * four-column grid had 10px to spare when it was 22px over.
 *
 * ⚠️ RULING 5 IS NOT WEAKENED BY THIS, IT IS APPLIED. Alex ruled *"wide rounds
 * may scroll horizontally — sparingly, better than excluding data."* Clipping a
 * column is excluding data; it is the outcome the ruling forbids, arrived at by
 * arithmetic instead of by choice. "Sparingly" still binds: a three-column grid
 * (`302 ≤ 332`) — the tournament's first week — does not scroll.
 *
 * ⚠️ AND DESKTOP STILL NEVER ASKS. Above `lg` the value tracks are `1fr`, the
 * component sets `lg:overflow-x-visible` and retires the inline floor with
 * `lg:!min-w-0`, so nothing here reaches a wide window.
 */
export function gridScrolls(columnCount: number, contentWidthPx = GRID_CARD_CONTENT_PX): boolean {
  return gridWidthPx(columnCount) > contentWidthPx;
}

/** Everything a row occupies: side padding, the name track, the value tracks, and the gaps between them. */
export function gridWidthPx(columnCount: number): number {
  return (
    2 * GRID_ROW_PADDING_PX +
    GRID_NAME_WIDTH_PX +
    columnCount * GRID_COLUMN_WIDTH_PX +
    columnCount * GRID_GAP_PX
  );
}

/**
 * ═══ #3087: THE SCROLL END HAS TO BE A SNAP POINT, OR SNAPPING DOES NOTHING
 * ═══ ABOUT THE POSITION THE READER ACTUALLY SWIPES TO.
 *
 * `PlayoffGrid` snaps its scroller (`scroll-padding-left: 138px`, every value
 * cell a `snap-start` target), which puts the rest positions at multiples of one
 * column plus its gap: 0, 52, 104… A browser will ALWAYS also let the scroll
 * rest at the end of its content, snap point or not, and measured on production
 * with a real wheel gesture that is exactly where a swipe lands:
 *
 *     wheel +20  → scrollLeft   0    (snapped back)
 *     wheel +40  → scrollLeft  52    ✓ a snap point, whole columns
 *     wheel +70  → scrollLeft  74    ✗ the END — QF half under the name box
 *     wheel +120 → scrollLeft  74    ✗ same
 *
 * At 74 the men's grid printed `Carlos Alcaraz  5%  67%  62%  43%` with his real
 * QF number (75%) behind the frozen name. Snapping fixed every position but the
 * one a reader reaches by swiping as far as it goes.
 *
 * So the scroll floor rounds the OVERFLOW up to a whole number of column steps.
 * Five columns overflow a 332px card by 74; 74 rounds to 104; the floor becomes
 * 436 and the scroll range becomes 104 — which IS a snap point, so every resting
 * position shows whole columns and the last one leaves a small gutter instead of
 * half a number. Four columns overflow by 22, which rounds to 52 the same way.
 *
 * A grid that fits is untouched and returns its own width: there is no scroll,
 * no snapping, and nothing to round.
 */
export function gridScrollFloorPx(
  columnCount: number,
  contentWidthPx = GRID_CARD_CONTENT_PX
): number {
  const width = gridWidthPx(columnCount);
  const overflow = width - contentWidthPx;
  if (overflow <= 0) return width;
  const step = GRID_COLUMN_WIDTH_PX + GRID_GAP_PX;
  return contentWidthPx + Math.ceil(overflow / step) * step;
}

/**
 * How many cells wear an illiquidity mark (UX-P157).
 *
 * Counted rather than assumed, and it is what gates the legend: a grid with no
 * marked cell must not print a key explaining a symbol that is not on screen —
 * the same rule the `no mkt` clause beside it already follows. It is also the
 * honest denominator for the report, because "the signal is live" and "the
 * signal fires on this draw" are two different claims.
 */
export function markedCellCount(grid: PlayoffGrid): number {
  let marked = 0;
  for (const row of grid.rows) {
    for (const cell of Object.values(row.cells ?? {})) {
      if (isMarked(readLiquidity(cell?.liquidity))) marked += 1;
    }
  }
  return marked;
}

/** The server payload, in this module's own casing. No logic, no defaults. */
export function readPlayoffGrid(payload: PlayoffGridPayload | null | undefined): PlayoffGrid | null {
  if (!payload) return null;
  return {
    draw: payload.draw,
    label: payload.label,
    columns: payload.columns ?? [],
    rows: (payload.rows ?? []).map((row) => ({
      entityKey: row.entity_key,
      displayName: row.display_name,
      seed: row.seed ?? null,
      image: row.image ?? null,
      rank: row.rank ?? null,
      onBoard: row.on_board !== false,
      cells: row.cells ?? {},
    })),
    counts: payload.counts ?? {},
    totalCells: payload.total_cells ?? 0,
    pricedCells: payload.priced_cells ?? 0,
    noMarketCells: payload.no_market_cells ?? 0,
    alarmCells: payload.alarm_cells ?? 0,
    columnSums: payload.column_sums ?? [],
    monotonicityViolations: payload.monotonicity_violations ?? [],
  };
}

/**
 * What a cell PRINTS, or `null` when it prints a word instead of a number.
 *
 * There is deliberately no "·" case any more. UX-P138 printed a middle dot for
 * a hole and explained it in a legend; a hole is now one of four named,
 * differently-styled states, each of which says what it is in the cell itself.
 */
export function formatGridCell(cell: GridCell): string | null {
  if (cell.probability === null || !Number.isFinite(cell.probability)) return null;
  return `${Math.round(cell.probability * 100)}%`;
}

/** The short word a non-numeric cell shows. */
export function gridCellGlyph(cell: GridCell): string {
  switch (cell.state) {
    case "settled":
      return cell.note === "won" ? "✓" : "—";
    case "no_market":
      // NOT a dot and NOT a dash. "No market" is a fact about the world; a
      // punctuation mark is a fact about the layout, and UX-P137's ruling 2
      // exists because the reader could not tell them apart.
      return "no mkt";
    case "unlinked":
    case "unregistered":
      return "!";
    default:
      return "—";
  }
}

/**
 * The sentence behind the glyph, for `title=` and for screen readers.
 *
 * Since UX-P157 the illiquidity reveal is APPENDED here rather than living only
 * on the mark itself. A grid value track is 46px on a phone: the mark inside it
 * is eight pixels wide and is not a hover target anybody can reliably find, so
 * the cell's own tooltip — which covers the whole cell — has to carry the
 * answer too. Appended and not substituted: "0.8% to reach the quarter-final"
 * and "barely traded" are two different things the reader needs, and the
 * second one is only interesting because the first one is on screen.
 */
export function gridCellExplanation(cell: GridCell, columnLabel: string): string {
  const base = gridCellStateExplanation(cell, columnLabel);
  const reveal = liquidityReveal(
    { liquidity: cell.liquidity, liquidity_reasons: cell.liquidity_reasons },
    cell.observed_at
  );
  return reveal === null ? base : `${base} ${reveal}`;
}

function gridCellStateExplanation(cell: GridCell, columnLabel: string): string {
  switch (cell.state) {
    case "live":
      // UX-P146: was "Live price." Alex's product-wide ruling on the noun.
      return `${columnLabel}. Live number.`;
    case "stale":
      return `${columnLabel}. Last seen ${formatAge(cell.age_hours)} ago.`;
    case "dark":
      return `${columnLabel}. No reading in over two days.`;
    case "settled":
      return `${columnLabel}. Settled: ${cell.note ?? "decided"}.`;
    case "no_market":
      // UX-P145: the fallback said "Neither source prices this question" —
      // *prices* as a verb, and *source* is our word for the venues.
      // UX-P150, ruling 141: naming the venues instead was the wrong fix. What
      // the reader needs is that the QUESTION has no answer anywhere, which is
      // the same admission without our sourcing in it.
      return `${columnLabel}. ${cell.note ?? "Nobody is answering this question."}`;
    case "unlinked":
    case "unregistered":
      return `${columnLabel}. ${cell.note ?? "Market not linked."} This is a fault on our side.`;
    default:
      return columnLabel;
  }
}

export function formatAge(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours)) return "an unknown time";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))}m`;
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

/**
 * The sum check, in a sentence a reader can act on (Alex's ruling 4).
 *
 * "8 for QF, 4 for SF, 2 for F, 1 for title" is the arithmetic; this is what it
 * MEANS when it misses, and the two directions mean different things. Under is
 * usually coverage — the field is bigger than the market prices. Over is the
 * market disagreeing with arithmetic, which is a real property of thin binaries
 * and not something the page is entitled to correct.
 */
export function columnSumSentence(check: GridColumnSum): string {
  const target = check.expected ?? 0;
  const total = check.sum.toFixed(1);
  // "1 places" is the kind of thing a reader files under "nobody looked at
  // this", which is the opposite of what a check is for.
  const places = `${target} place${target === 1 ? "" : "s"}`;
  switch (check.verdict) {
    case "pass":
      return `${check.short_label} adds to ${total} against ${places} — as it should.`;
    case "under":
      return `${check.short_label} adds to ${total}, under the ${places} available: ${
        check.total_rows - check.priced_rows
      } of ${check.total_rows} players have no market for it.`;
    case "over":
      return `${check.short_label} adds to ${total} against ${places}. The market is giving out more chances than can happen; we show what it quotes rather than scaling it down.`;
    default:
      return `${check.short_label} has no numbers to check yet.`;
  }
}

export function gridEvalVerdict(grid: PlayoffGrid): "green" | "red" {
  // ALARMS ARE RED, and nothing else is. A column that does not sum and a
  // monotonicity break are the MARKET's incoherence, reported; an alarm is
  // OURS, and Alex's amendment says so in as many words.
  return grid.alarmCells > 0 ? "red" : "green";
}
