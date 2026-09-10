/**
 * #4538 — THE CONTENDER ROW MUST NOT HIDE THE NAME IT EXISTS TO PRINT
 *
 * ## What was measured, and what the filing got wrong
 *
 * Production, `https://www.bainluck.com/tournaments/us-open`, 2026-09-09 ~18:10 PT,
 * read out of the layout engine by `tools/board-row-fit-4538.mjs` (rendered
 * `gridTemplateColumns` + per-track client rects + `scrollWidth > clientWidth` on
 * the truncating node — never from looking for an ellipsis in a screenshot):
 *
 * | width | rank 1 name track | wants | clipped |
 * |-------|-------------------|-------|---------|
 * | 360px | 72.6px            | 125px | all three rows, `Ben Shelton` included |
 * | 390px | 102.6px           | 125px | rank 1 only (`Alexander Z…`) |
 * | 430px+| 142.6px+          | 125px | none |
 *
 * #4538 filed this as a row "whose number column is half empty". It is not: at
 * 390px the number track is 59.4px and `44.3%` inks 59.4px of it — `numberAir: 0`,
 * and `trailingSlack: 0` at the row's right edge. There was no slack anywhere. So
 * the two changes below do not reclaim air; they remove a track and stop hiding
 * the overflow. The three ideas the measurement KILLED are recorded at the foot of
 * this file, because each looks right until you measure it.
 *
 * ## The two changes
 *
 * 1. **Below `sm` there is no sparkline track.** 52px + a 10px gap back to the
 *    name. This follows #3358's finding on `components/futures/OutcomeRow.tsx`
 *    ("an empty or fixed-width column buys no width", `sm` and up byte-identical)
 *    and picks the sparkline because the row states the same fact twice, 10px
 *    apart: `+19.9` in points, and a 52x26px fixed-axis line that is passed the
 *    very same `delta` and coloured by `trendDirection(delta)`.
 * 2. **The name wraps rather than truncating.** Returning 62px covers every name
 *    in both US Open draws at 390px, and all but the longest at 360px — the 80
 *    rows' longest are `Felix Auger-Aliassime` and `Ekaterina Alexandrova` at 21
 *    characters. Those wrap to a second line instead of printing an ellipsis.
 *
 * ## Red-first, measured rather than asserted
 *
 * Run against the parent commit's row (`grid-cols-[22px_28px_1fr_auto_52px]` with
 * no `sm:` variant, a `truncate` name cell and a bare `<TrendSparkline>`):
 * **6 of 10 fail, 4 pass.**
 *
 * The six that fail are the diff: `four tracks below sm`, `five tracks at sm`,
 * `name cell is not truncate`, `name cell wraps`, `sparkline sits in a hidden
 * sm:block slot`, and `no name is ellipsised at 390px` (the class-contract form).
 *
 * The four that pass are CONTROLS over rules the parent already followed, and they
 * are here to catch the over-correction — deleting the sparkline outright, or
 * dropping the delta, would be an easy way to make the six go green:
 * `the sparkline is still rendered`, `the delta still prints`, `the probability
 * still prints`, and `the rank and avatar tracks are unchanged`. None of the four
 * is load-bearing for this diff and none is claimed as such.
 *
 * No assertion here claims a pixel. There is no layout engine in this suite; the
 * pixel readings above are the production probe's and are reproducible with it.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBoard from "@/components/tournament/TournamentBoard";
import type { TournamentBoardData, TournamentRow } from "@/lib/tournament";

/** The longest name across the 80 rows of both US Open draws, 2026-09-09. */
const LONGEST_REAL_NAME = "Felix Auger-Aliassime";

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "player-a",
    display_name: "Alexander Zverev",
    seed: null,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.443,
    probability_is_live: true,
    observed_at: "2026-09-09T18:00:00+00:00",
    age_hours: 1,
    price_state: "live",
    freshest_observed_at: "2026-09-09T18:00:00+00:00",
    freshest_age_hours: 1,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: [
      { date: "2026-09-07", probability: 0.24 },
      { date: "2026-09-08", probability: 0.31 },
      { date: "2026-09-09", probability: 0.443 },
    ],
    trend_delta: 0.199,
    ...overrides,
  };
}

function board(overrides: Partial<TournamentBoardData> = {}): TournamentBoardData {
  return {
    draw: "mens-singles",
    label: "Men's Singles",
    rows: [row()],
    contenders: 36,
    unpriced: 0,
    rows_not_live: 0,
    mixed_freshness_rows: 0,
    price_state: "live",
    newest_observed_at: "2026-09-09T18:00:00+00:00",
    age_hours: 1,
    ...overrides,
  };
}

function render(data: TournamentBoardData = board()): string {
  return renderToStaticMarkup(<TournamentBoard board={data} />);
}

/** The `class="..."` of the single `board-row` `<li>` in the markup. */
function rowClasses(html: string): string {
  const li = html.match(/<li[^>]*data-testid="board-row"[^>]*>/);
  if (!li) throw new Error("no board-row in the rendered markup");
  return li[0].match(/class="([^"]*)"/)?.[1] ?? "";
}

describe("#4538 the name column is not starved at phone widths", () => {
  it("drops the sparkline track below sm — four tracks, not five", () => {
    const cls = rowClasses(render());
    // The unprefixed template is what every width below `sm` gets.
    expect(cls).toContain("grid-cols-[22px_28px_1fr_auto]");
    expect(cls).not.toMatch(/(^|\s)grid-cols-\[22px_28px_1fr_auto_52px\](\s|$)/);
  });

  it("keeps all five tracks at sm and up", () => {
    expect(rowClasses(render())).toContain("sm:grid-cols-[22px_28px_1fr_auto_52px]");
  });

  it("does not truncate the name cell", () => {
    const html = render();
    const nameCell = html.match(/<div class="([^"]*text-\[15px\][^"]*)"/)?.[1] ?? "";
    expect(nameCell).not.toMatch(/(^|\s)truncate(\s|$)/);
  });

  it("wraps a name that does not fit instead of hiding its tail", () => {
    const nameCell =
      render().match(/<div class="([^"]*text-\[15px\][^"]*)"/)?.[1] ?? "";
    expect(nameCell).toMatch(/(^|\s)break-words(\s|$)/);
  });

  it("puts the sparkline in a slot that is display:none below sm", () => {
    const html = render();
    const slot = html.match(/<div class="([^"]*)"[^>]*data-testid="board-row-trend-slot"/);
    expect(slot).not.toBeNull();
    // `hidden` is display:none, so the slot is not a grid item below `sm` and
    // cannot open an implicit sixth row against the four-track template.
    expect(slot![1]).toMatch(/(^|\s)hidden(\s|$)/);
    expect(slot![1]).toMatch(/(^|\s)sm:block(\s|$)/);
  });

  it("prints the longest real name in full, with no ellipsis class on its cell", () => {
    const html = render(board({ rows: [row({ display_name: LONGEST_REAL_NAME })] }));
    expect(html).toContain(LONGEST_REAL_NAME);
    const nameCell = html.match(/<div class="([^"]*text-\[15px\][^"]*)"/)?.[1] ?? "";
    expect(nameCell).not.toMatch(/(^|\s)(truncate|text-ellipsis|overflow-hidden)(\s|$)/);
  });

  // ── CONTROLS ──────────────────────────────────────────────────────────────
  // Green on the parent too. They fence the over-correction, not the diff.

  it("CONTROL: the sparkline is still rendered, not deleted", () => {
    expect(render()).toContain('data-testid="trend-sparkline"');
  });

  it("CONTROL: the delta still prints beside the number", () => {
    expect(render()).toContain('data-testid="row-delta"');
    expect(render()).toContain("+19.9");
  });

  it("CONTROL: the probability still prints", () => {
    expect(render()).toContain('data-testid="row-probability"');
    expect(render()).toContain("44.3%");
  });

  it("CONTROL: the rank and avatar tracks are untouched", () => {
    const cls = rowClasses(render());
    expect(cls).toContain("22px_28px");
    expect(cls).toContain("gap-2.5");
  });
});

/**
 * ── THREE FIXES THE MEASUREMENT KILLED ────────────────────────────────────────
 *
 * Recorded so the next session does not spend the afternoon re-deriving them.
 *
 * 1. **"Show the number column's spare width to the name."** #4538's own stated
 *    cause. There is no spare width: `numberAir: 0` on every row, `trailingSlack:
 *    0` at the row's right edge. The filing's headline was false about its own
 *    specimen.
 *
 * 2. **"Pin the number track so rows stop jittering."** The `auto` track really
 *    does vary by row — 59.4px on `44.3%`, 47.6px on `9.2%` — so rank 1, with the
 *    biggest number, gets the NARROWEST name. It reads like the bug. It is not:
 *    the number is right-aligned and the track that follows it is fixed, so every
 *    row's number lands on the same right edge (285px at 390px, measured, all
 *    three rows). Nothing a reader can see jitters, and pinning the track would
 *    have taken 11.8px off rank 3's name to fix an invisible problem. `auto` is
 *    correct: it hands the name whatever the number does not need.
 *
 * 3. **"An empty column buys no width — skip the sparkline track when no row
 *    draws one."** #3358's first change, and genuinely reachable here (
 *    `sparklinePoints` returns "" below two points, and `TrendSparkline` then
 *    renders an empty 52px slot to hold the rows in line). Dropped anyway: it is
 *    inert for a reader. Both US Open draws have 0/36 and 0/44 empty sparklines,
 *    so it could not be demonstrated on the specimen; and below `sm` change 1
 *    already removes the track, while at `sm`+ the name track is 353px at 640px
 *    and reclaiming 52px more buys nobody anything.
 */
