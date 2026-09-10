/**
 * THE PLAYOFF GRID's rendering, and the three items it answers (UX-P139).
 *
 * The grid's LOGIC and its two evals live on the server now — Alex's amendment
 * makes cell provenance a correctness property ("the grid reads only the
 * register"), so those are asserted in `backend/tests/test_tournament_grid.py`.
 * What this file guards is everything a backend test cannot see:
 *
 *   * **No cell is ever blank** (the amendment's dealbreaker), as a property
 *     over the rendered HTML rather than over the model.
 *   * The semifinal column reaches the DOM (ruling 4).
 *   * The sum check is on the page, with its failures visible (ruling 4).
 *   * Wide grids scroll instead of dropping a column (ruling 5).
 *   * An alarm cell says what is broken, in words a reader can act on.
 *
 * The plant rule (`reference_plant_must_hit_the_render`): every assertion here
 * reads the rendered markup, because a pure-library guard stays green the day
 * the component stops printing the feature.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import PlayoffGrid, {
  GRID_COL_TRACK_FIXED,
  GRID_COL_TRACK_FLEX,
  GRID_NAME_TRACK,
  GRID_SCROLL_SNAP,
  GRID_STICKY_NAME,
  gridTemplate,
} from "@/components/tournament/PlayoffGrid";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import { COLLAPSED_LIST_COUNT } from "@/components/tournament/ShowMore";
import {
  columnSumSentence,
  formatAge,
  gridCellExplanation,
  gridCellGlyph,
  gridEvalVerdict,
  GRID_CARD_CONTENT_PX,
  GRID_COLUMN_WIDTH_PX,
  GRID_GAP_PX,
  GRID_NAME_WIDTH_PX,
  GRID_ROW_PADDING_PX,
  gridScrollFloorPx,
  gridScrolls,
  gridWidthPx,
  readPlayoffGrid,
  type GridCell,
  type PlayoffGrid as GridModel,
  type PlayoffGridPayload,
} from "@/lib/playoffGrid";

function cell(overrides: Partial<GridCell> = {}): GridCell {
  return {
    state: "live",
    probability: 0.575,
    probability_is_live: true,
    sources: [{ source: "polymarket", probability: 0.575 }],
    source_count: 1,
    observed_at: "2026-08-27T00:00:00+00:00",
    age_hours: 0.5,
    blend_rule: "single",
    divergent: false,
    note: null,
    censused_at: "2026-08-27T00:00:00+00:00",
    is_alarm: false,
    ...overrides,
  };
}

const COLUMNS = [
  { key: "R16", short_label: "R16", long_label: "To reach the round of 16", kind: "reach" as const, slots: 16 },
  { key: "QF", short_label: "QF", long_label: "To reach the quarter-finals", kind: "reach" as const, slots: 8 },
  { key: "SF", short_label: "SF", long_label: "To reach the semi-finals", kind: "reach" as const, slots: 4 },
  { key: "F", short_label: "Final", long_label: "To reach the final", kind: "reach" as const, slots: 2 },
  { key: "title", short_label: "Title", long_label: "To win the title", kind: "title" as const, slots: 1 },
];

function payload(overrides: Partial<PlayoffGridPayload> = {}): PlayoffGridPayload {
  return {
    draw: "mens-singles",
    label: "Men's Singles",
    columns: COLUMNS,
    rows: [
      {
        entity_key: "carlos-alcaraz",
        display_name: "Carlos Alcaraz",
        seed: 2,
        rank: 1,
        on_board: true,
        cells: {
          R16: cell({ probability: 0.9 }),
          QF: cell({ probability: 0.78 }),
          SF: cell({ probability: 0.575 }),
          F: cell({ probability: 0.375 }),
          title: cell({ probability: 0.263 }),
        },
      },
    ],
    counts: { live: 5 },
    total_cells: 5,
    priced_cells: 5,
    no_market_cells: 0,
    alarm_cells: 0,
    column_sums: COLUMNS.map((c) => ({
      key: c.key,
      short_label: c.short_label,
      sum: c.slots ?? 0,
      expected: c.slots,
      ratio: 1,
      priced_rows: 1,
      total_rows: 1,
      verdict: "pass" as const,
    })),
    monotonicity_violations: [],
    ...overrides,
  };
}

function grid(overrides: Partial<PlayoffGridPayload> = {}): GridModel {
  const model = readPlayoffGrid(payload(overrides));
  if (model === null) throw new Error("payload did not read");
  return model;
}

// ---------------------------------------------------------------------------
// THE DEALBREAKER: no cell is ever blank
// ---------------------------------------------------------------------------

describe("no cell is ever blank", () => {
  const STATES: GridCell["state"][] = [
    "live", "stale", "dark", "settled", "no_market", "unlinked", "unregistered",
  ];

  it("every state prints something, in the DOM", () => {
    for (const state of STATES) {
      const html = renderToStaticMarkup(
        <PlayoffGrid
          grid={grid({
            rows: [{
              entity_key: "p", display_name: "P", seed: null, rank: 1, on_board: true,
              cells: Object.fromEntries(
                COLUMNS.map((c) => [
                  c.key,
                  cell({
                    state,
                    probability: state === "live" || state === "stale" || state === "dark" ? 0.5 : null,
                    probability_is_live: state === "live",
                    note: state === "no_market" ? "No SF market at kalshi, polymarket" : "broken link",
                    is_alarm: state === "unlinked" || state === "unregistered",
                  }),
                ])
              ),
            }],
          })}
        />
      );
      const cells = [...html.matchAll(/data-testid="grid-cell"[^>]*data-state="([^"]*)"/g)];
      expect(cells.length).toBe(COLUMNS.length);
      for (const match of cells) expect(match[1]).toBe(state);
      // And the cell's own box is never empty text.
      const rendered = html.split('data-testid="grid-row"')[1] ?? "";
      const emptySpans = rendered.match(/data-testid="grid-cell"[^>]*><\/span>/g) ?? [];
      expect(emptySpans).toHaveLength(0);
    }
  });

  it("a no-market cell prints NOTHING, and still says what it is (#4171 item 2)", () => {
    // It printed NO MKT. Alex, notice 34, about this page: "if a number cannot
    // be shown honestly, leave the space empty". UX-P137's ruling 2 wanted the
    // reader to be able to tell a hole from a layout artifact, and since
    // UX-P157 the CELL carries that sentence itself — so this asserts BOTH
    // halves: the jargon is off the screen AND the answer is still on the cell.
    const html = renderToStaticMarkup(
      <PlayoffGrid
        grid={grid({
          rows: [{
            entity_key: "jannik-sinner", display_name: "Jannik Sinner", seed: 1, rank: 1,
            on_board: true,
            cells: {
              ...Object.fromEntries(
                ["R16", "QF", "SF", "F"].map((k) => [
                  k,
                  cell({
                    state: "no_market", probability: null, probability_is_live: false,
                    note: "No " + k + " market at kalshi, polymarket", is_alarm: false,
                  }),
                ])
              ),
              title: cell({ probability: 0.525 }),
            },
          }],
          counts: { no_market: 4, live: 1 },
          no_market_cells: 4,
          priced_cells: 1,
        })}
      />
    );
    // 1. THE WORDS ARE GONE — in any casing, anywhere in the markup.
    expect(html.toLowerCase()).not.toContain("no mkt");

    // 2. THE FOUR CELLS ARE STILL THERE, and each one still answers for itself.
    //    Without this the test above is passed perfectly by a grid that stopped
    //    rendering the row — the removal mutant that matters.
    const noMarketCells = [
      ...html.matchAll(/data-testid="grid-cell"[^>]*data-state="no_market"[^>]*/g),
    ];
    expect(noMarketCells).toHaveLength(4);
    expect(html).toContain("No R16 market at kalshi, polymarket");
    for (const key of ["R16", "QF", "SF", "F"]) {
      expect(html).toContain(`No ${key} market at kalshi, polymarket`);
    }

    // 3. AND THE EMPTY CELL STILL OCCUPIES ITS BOX, so the `title` that now
    //    carries the whole answer has something to hover. A zero-width span is
    //    how "we moved it to the tooltip" quietly becomes "we deleted it".
    const emptyBoxes = html.match(/<span aria-hidden="true">\u00a0<\/span>/g) ?? [];
    expect(emptyBoxes).toHaveLength(4);

    // 4. It is NOT the settled dash — that glyph means "this player is out",
    //    which is a different claim from "nobody quoted this".
    expect(gridCellGlyph(cell({ state: "settled", note: "eliminated" }))).toBe("—");
    expect(gridCellGlyph(cell({ state: "no_market" }))).toBe("");

    // The censused absence is NOT an alarm, and the banner must not fire.
    expect(html).not.toContain('data-testid="grid-alarm-banner"');
    /* #4122 (notice 34): the legend that aggregated "K say NO MKT" is gone —
       it was a coverage count plus an explanation of our own emptiness. The
       count is on the section for probes. */
    expect(html).not.toContain('data-testid="grid-legend"');
    expect(html).toContain('data-no-market="4"');
  });

  it("an alarm cell names the market that did not link", () => {
    const html = renderToStaticMarkup(
      <PlayoffGrid
        grid={grid({
          rows: [{
            entity_key: "p", display_name: "P", seed: null, rank: 1, on_board: true,
            cells: {
              ...Object.fromEntries(
                ["R16", "QF", "F", "title"].map((k) => [k, cell()])
              ),
              SF: cell({
                state: "unlinked", probability: null, probability_is_live: false,
                note: "Registered but unpriced: polymarket 0xdeadbeef", is_alarm: true,
              }),
            },
          }],
          alarm_cells: 1,
        })}
      />
    );
    expect(html).toContain('data-testid="grid-alarm-banner"');
    expect(html).toContain('data-count="1"');
    expect(html).toContain("0xdeadbeef");
    // "the fix is linking the real markets" — so it is stated as ours.
    expect(html).toContain("fault on our side");
    expect(html).toContain('data-alarm="true"');
  });

  it("the alarm banner stays away when the grid is clean", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid()} />);
    expect(html).not.toContain('data-testid="grid-alarm-banner"');
    expect(html).toContain('data-alarms="0"');
  });
});

// ---------------------------------------------------------------------------
// CERT C-UX-P139-GRID-REGISTER-1 [P1] — the specimen, at the RENDER
// ---------------------------------------------------------------------------
//
// The cert executed a registered Polymarket+Kalshi SF cell with Polymarket
// loaded and Kalshi absent and got `state='live'`, `probability_is_live=true`,
// `source_count=1`, `is_alarm=false`, `alarm_cells=0`. The backend fix turns
// that cell into an alarm and withholds the number; these assertions are what
// a reader would actually have seen, because the backend guard alone stays
// green the day this component starts printing `cell.sources[0].probability`
// (the plant rule — `reference_plant_must_hit_the_render`).

describe("cert P1 — one missing leg is an alarm at the render, not a number", () => {
  /** The server's shape for the specimen, post-fix. */
  const PARTIAL_CELL = {
    state: "unlinked" as const,
    probability: null,
    probability_is_live: false,
    sources: [
      { source: "polymarket", probability: 0.6, price_state: "live", market_external_id: "0x000a" },
      { source: "kalshi", state: "unlinked", market_external_id: "KXSFALCARAZ" },
    ],
    source_count: 2,
    observed_at: null,
    age_hours: null,
    blend_rule: null,
    divergent: false,
    note: "1 of 2 registered sources priced; unpriced: kalshi KXSFALCARAZ",
    censused_at: "2026-08-27T00:00:00+00:00",
    is_alarm: true,
    partially_unlinked: true,
  };

  function partialGrid() {
    return grid({
      rows: [{
        entity_key: "carlos-alcaraz", display_name: "Carlos Alcaraz", seed: 2, rank: 1,
        on_board: true,
        cells: {
          ...Object.fromEntries(["R16", "QF", "F", "title"].map((k) => [k, cell()])),
          SF: PARTIAL_CELL,
        },
      }],
      counts: { live: 4, unlinked: 1 },
      priced_cells: 4,
      alarm_cells: 1,
    });
  }

  it("the surviving leg's price never reaches the DOM", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={partialGrid()} />);
    const sf = html.split('data-column="SF"').slice(1).join("");
    // 0.6 would print as "60%". The other four cells are untouched, so this is
    // scoped to the SF cell's own markup rather than to the whole grid.
    expect(sf).not.toContain("60%");
  });

  it("the cell renders as an alarm, not as a live number", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={partialGrid()} />);
    expect(html).toContain('data-state="unlinked" data-column="SF"');
    const sfCell = html.match(
      /data-testid="grid-cell" data-state="unlinked" data-column="SF"[^>]*/
    )?.[0] ?? "";
    expect(sfCell).toContain('data-live="false"');
    expect(sfCell).toContain('data-alarm="true"');
  });

  it("the banner fires and the eval reads RED", () => {
    const model = partialGrid();
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).toContain('data-testid="grid-alarm-banner"');
    expect(html).toContain('data-count="1"');
    // The laundering the cert named: the grid used to report zero alarms while
    // publishing this cell.
    expect(gridEvalVerdict(model)).toBe("red");
  });

  it("it says WHICH leg failed, and that it is ours", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={partialGrid()} />);
    expect(html).toContain("KXSFALCARAZ");
    expect(html).toContain("1 of 2 registered sources priced");
    expect(html).toContain("fault on our side");
  });

  it("a fully-loaded two-source cell still prints its blended number", () => {
    // The fix withholds a BROKEN cell, not a working one.
    const html = renderToStaticMarkup(
      <PlayoffGrid
        grid={grid({
          rows: [{
            entity_key: "carlos-alcaraz", display_name: "Carlos Alcaraz", seed: 2, rank: 1,
            on_board: true,
            cells: {
              ...Object.fromEntries(["R16", "QF", "F", "title"].map((k) => [k, cell()])),
              SF: cell({
                probability: 0.58,
                source_count: 2,
                sources: [
                  { source: "polymarket", probability: 0.6 },
                  { source: "kalshi", probability: 0.56 },
                ],
                blend_rule: "equal_weight_midpoint",
              }),
            },
          }],
        })}
      />
    );
    expect(html).toContain("58%");
    expect(html).not.toContain('data-testid="grid-alarm-banner"');
  });
});

// ---------------------------------------------------------------------------
// Ruling 4 — the semifinal column, and the sum check
// ---------------------------------------------------------------------------

describe("ruling 4 — the semifinal column and the sum check", () => {
  it("renders the SF column header, with its full sentence", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid()} />);
    expect(html).toContain('data-testid="grid-column" data-column="SF"');
    expect(html).toContain("To reach the semi-finals");
    // The order is the order the rounds are played, title last.
    const order = [...html.matchAll(/data-testid="grid-column" data-column="([^"]*)"/g)].map(
      (m) => m[1]
    );
    expect(order).toEqual(["R16", "QF", "SF", "F", "title"]);
  });

  it("puts the title column last and calls it a DIFFERENT question", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid()} />);
    expect(html).toContain('data-kind="title"');
    expect(html).toContain("To win the title");
    // Not "reach the final" — two markets, one strictly harder.
    expect(html.indexOf("To win the title")).toBeGreaterThan(
      html.indexOf("To reach the final")
    );
  });

  /* ═══ #4278 / notice 34: THE SELF-AUDIT IS OFF THE PAGE AND STILL MEASURED ═══
     These four cases used to assert the OPPOSITE — that the `grid-sum-check`
     disclosure, its five rows and the monotonicity paragraph rendered. They are
     inverted rather than deleted, because the risk of a copy sweep over a
     self-check is that it takes the CHECK with the CAPTION, and an inverted
     test is the only thing that fails if someone later "restores" the prose or
     drops the model that fed it. Every assertion below is paired: the sentence
     is gone AND the fact it carried is still readable. */

  it("does not print the column self-audit to the reader (#4278)", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid()} />);
    // The banned shapes, anchored on the clause that made each one banned
    // rather than on words a legitimate string could share.
    expect(html).not.toContain("Does each column add up");
    expect(html).not.toContain("columns within tolerance");
    expect(html).not.toContain('data-testid="grid-sum-check"');
    expect(html).not.toContain('data-testid="grid-sum-row"');
    // ...and the audit itself still ran and is still readable by a probe.
    expect(html).toContain('data-sum-columns="5"');
    expect(html).toMatch(/data-sum-failing="\d+"/);
  });

  it("still refuses to rescale an over-summing column (ruling 4's substance)", () => {
    const model = grid({
      column_sums: [
        { key: "F", short_label: "Final", sum: 2.781, expected: 2, ratio: 1.39,
          priced_rows: 44, total_rows: 56, verdict: "over" },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    // THIS IS THE PART NOTICE 34 DID NOT TOUCH. Ruling 4 forbids quietly
    // scaling the numbers until they add up; it does not require a paragraph
    // saying so. 0.375 in the F column still prints 38%, not a rescaled 27%.
    expect(html).toContain('data-column="F"');
    expect(html).toContain("38%");
    // The sentence that used to explain it is gone from the body.
    expect(html).not.toContain("rather than scaling it down");
    // The failing column is counted where machines look.
    expect(html).toContain('data-sum-failing="1"');
  });

  it("counts an under-summing column without explaining it in prose", () => {
    // #4174: `uncovered_rows` is the coverage count now — players STILL IN THE
    // DRAW that nobody quotes. It used to be `total_rows - priced_rows`, which
    // counted a player who lost in the third round as a missing market. The
    // number is machine-readable only; #4278 took the sentence off the page.
    const model = grid({
      column_sums: [
        { key: "R16", short_label: "R16", sum: 13.667, expected: 16, slots: 16,
          ratio: 0.854, priced_rows: 44, decided_rows: 0, uncovered_rows: 12,
          total_rows: 56, verdict: "under" },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).not.toContain("12 of 56 players have no market");
    expect(html).not.toContain("12 players have no market");
    expect(html).toContain('data-sum-failing="1"');
    expect(html).toContain('data-sum-columns="1"');
  });

  it("a decided column is a finished check, not a failed one (#4174)", () => {
    // The QF column read `0.63 of 8` on a morning when all eight
    // quarter-finalists were already known, and every probe reading
    // `data-sum-failing` was told the grid had failed its own check.
    const model = grid({
      column_sums: [
        { key: "QF", short_label: "QF", sum: 0, expected: 0, slots: 8, ratio: null,
          priced_rows: 0, decided_rows: 56, uncovered_rows: 0, total_rows: 56,
          verdict: "settled" },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).toContain('data-sum-failing="0"');
    expect(html).toContain('data-sum-columns="1"');
  });

  it("counts monotonicity violations without hiding the numbers", () => {
    const model = grid({
      monotonicity_violations: [
        { entity_key: "cameron-norrie", display_name: "Cameron Norrie",
          earlier: "SF", later: "F", earlier_probability: 0.04, later_probability: 0.05 },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).not.toContain('data-testid="grid-monotonicity"');
    expect(html).not.toContain("Cameron Norrie (SF → F)");
    expect(html).not.toContain("shown exactly as quoted");
    expect(html).not.toContain("higher chance for a later round");
    // Still detected, still counted, and — the part that matters — the market's
    // own numbers are still what the grid prints.
    expect(html).toContain('data-monotonicity="1"');
  });

  it("counts zero when every column is coherent (positive control)", () => {
    // The `data-sum-failing` assertions above are worthless if the attribute
    // reads the same on a clean grid as on a broken one. It does not.
    const model = grid({
      column_sums: [
        { key: "F", short_label: "Final", sum: 2.0, expected: 2, ratio: 1.0,
          priced_rows: 56, total_rows: 56, verdict: "pass" },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).toContain('data-sum-failing="0"');
    expect(html).toContain('data-monotonicity="0"');
  });
});

// ---------------------------------------------------------------------------
// Ruling 5 — scrolling, sparingly
// ---------------------------------------------------------------------------

describe("ruling 5 — wide rounds scroll rather than lose a column", () => {
  it("counts a row's PADDING and GAPS, not only its tracks (#3072)", () => {
    // The old formula was `name + n × col` — tracks only. A row is
    // `px-3.5` + name + `gap-1.5` + col + `gap-1.5` + col …, so five columns
    // need 28 + 118 + 270 + 30 = 446px, not 348.
    //
    // (#4171 widened the phone value track 46 → 54 because the cell stopped
    // being only a number: `100%` + `gap-1` + `LiquidityMark` measures 51px.
    // Every figure in this describe moved by 8px per column with it; the shape
    // of the arithmetic — padding and gaps counted, not only tracks — did not.)
    expect(GRID_ROW_PADDING_PX).toBe(14);
    expect(GRID_GAP_PX).toBe(6);
    expect(gridWidthPx(5)).toBe(446);
    expect(gridWidthPx(6)).toBe(506);
    expect(gridWidthPx(3)).toBe(326);
  });

  it("THE #3072 DEFECT: the men's five-column draw scrolls, because it does not fit", () => {
    // Measured on production, pinned 390px viewport: the grid card's client box
    // is 332px and the grid inside it is 392px, clipped by `overflow-x: hidden`
    // — so the Title column, the chance of WINNING the tournament, was drawn
    // outside the card and could not be reached by any gesture.
    expect(GRID_CARD_CONTENT_PX).toBe(332);
    expect(gridScrolls(5)).toBe(true);
    expect(gridScrolls(4)).toBe(true);
    expect(gridScrolls(6)).toBe(true);
  });

  it("…and 'sparingly' still binds — the first week's grid does not scroll", () => {
    // Ruling 5 is applied here, not weakened: clipping a column IS excluding
    // data. A three-column grid fits (326 <= 332, still true at #4171's 54px
    // track — the widening was sized to keep this verdict) and stays still.
    expect(gridScrolls(3)).toBe(false);
    expect(gridScrolls(2)).toBe(false);
  });

  it("the rendered five-column grid is a scroller, and its floor is the whole row", () => {
    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    expect(html).toContain('data-scrolls="true"');
    expect(html).toContain("overflow-x-auto");
    // The floor is the row's whole width ROUNDED UP so the scroll end lands on
    // a snap point (#3087, second half) — `gridWidthPx(5)` = 446 would leave the
    // end at 114, which is where the QF column hid half a number behind the
    // sticky name. `gridScrollFloorPx` is what the component pins.
    expect(html).toContain(`min-width:${gridScrollFloorPx(5)}px`);
    expect(gridScrollFloorPx(5)).toBe(452);
    expect(gridScrollFloorPx(5)).toBeGreaterThan(gridWidthPx(5));
    // The column that was being clipped is present and named.
    expect(html).toContain('data-kind="title"');
  });

  it("puts the header INSIDE the scroller so it cannot drift off its column", () => {
    const wide = grid({
      columns: [...COLUMNS.slice(0, 4), ...COLUMNS],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={wide} />);
    expect(html).toContain('data-scrolls="true"');
    const scrollerStart = html.indexOf('data-testid="grid-scroller"');
    expect(html.indexOf('data-testid="grid-header"')).toBeGreaterThan(scrollerStart);
    expect(html.indexOf('data-testid="grid-row"')).toBeGreaterThan(scrollerStart);
  });

  it("never drops a column, however many there are", () => {
    const wide = grid({ columns: [...COLUMNS.slice(0, 4), ...COLUMNS] });
    const html = renderToStaticMarkup(<PlayoffGrid grid={wide} />);
    expect((html.match(/data-testid="grid-column"/g) ?? []).length).toBe(9);
    expect(html).not.toContain("do not fit this width");
  });
});

// ---------------------------------------------------------------------------
// #3087 — the name stays when the reader swipes for the number
// ---------------------------------------------------------------------------

describe("#3087 — a scrolled grid keeps the name beside the number", () => {
  it("THE DEFECT: at full scroll the rows read 's Alcaraz' unless the name sticks", () => {
    // Measured on production 2026-09-04 11:02 PT, 390px viewport, the men's
    // five-column grid: the card's scroller is 332 wide over 446 of content
    // (406 when this was measured, before #4171's wider track), so `scrollLeft`
    // reaches 114 — and any of that is most of the 118px name track. The
    // header at that offset reads `R16 QF SF FINAL TITLE` and the rows read
    // `s Alcaraz` / `nder Z…` / `Medve…`. Sticky is what puts the two halves of
    // the sentence on screen at once.
    expect(gridWidthPx(5) - GRID_CARD_CONTENT_PX).toBe(114);

    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    // EVERY rendered row, not just the first, and read off each name cell's OWN
    // class attribute. An earlier draft asserted `html.toContain("sticky …")`
    // and stayed green with the rows unstuck, because the sticky HEADER satisfied
    // it — a sticky header over rows that still scroll away is the same defect
    // wearing a fix.
    const nameClasses = [...html.matchAll(/class="([^"]*)"\s+data-testid="grid-name"/g)].map(
      (m) => m[1]
    );
    const rows = (html.match(/data-testid="grid-row"/g) ?? []).length;
    expect(rows).toBeGreaterThan(0);
    expect(nameClasses.length).toBe(rows);
    for (const cls of nameClasses) {
      expect(cls).toContain("sticky left-0 z-10 bg-surface-card");
    }
    // The HEADER's name cell sticks too, or "Player" slides off its own column.
    const header = html.slice(
      html.indexOf('data-testid="grid-header"'),
      html.indexOf('data-testid="grid-row"')
    );
    expect(header).toContain("sticky left-0");
    expect(header).toContain("Player");
  });

  it("sticks WITHOUT moving anything: every negative margin is cancelled by its padding", () => {
    // The whole risk of this change is that it re-lays-out the row and truncates
    // a name one character earlier. `-ml-3.5/pl-3.5` and `-mr-1.5/pr-1.5` pair
    // exactly, so the box paints over the row's `px-3.5` and the `gap-1.5`
    // beside it while its CONTENT box does not move and the track's max-content
    // contribution is unchanged.
    expect(GRID_STICKY_NAME).toContain("-ml-3.5");
    expect(GRID_STICKY_NAME).toContain("pl-3.5");
    expect(GRID_STICKY_NAME).toContain("-mr-1.5");
    expect(GRID_STICKY_NAME).toContain("pr-1.5");
    // Opaque, or the percentages slide visibly under the name.
    expect(GRID_STICKY_NAME).toContain("bg-surface-card");
    // 14px of left margin is the row's own padding; 6px of right is its gap.
    expect(GRID_ROW_PADDING_PX).toBe(14);
    expect(GRID_GAP_PX).toBe(6);
  });

  it("expires exactly where ruling 5 expires — not on a grid that fits, not at lg", () => {
    // A first-week three-column grid does not scroll, so there is nothing to
    // stick to and no sticky cell is emitted at all.
    const three = grid({ columns: COLUMNS.slice(0, 3) });
    const threeHtml = renderToStaticMarkup(<PlayoffGrid grid={three} />);
    expect(gridScrolls(3)).toBe(false);
    expect(threeHtml).toContain('data-scrolls="false"');
    expect(threeHtml).not.toContain("sticky left-0");
    // …and the name cell is still there, just not stuck.
    expect(threeHtml).toContain('data-testid="grid-name"');

    // Above lg the tracks are 1fr and the grid fills its card: sticky retires.
    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const fiveHtml = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    expect(fiveHtml).toContain("lg:static");
    expect(fiveHtml).toContain("lg:ml-0");
    expect(fiveHtml).toContain("lg:pl-0");
  });

  it("comes to rest on WHOLE columns — the snap line is the sticky cell's right edge", () => {
    // The defect the sticky column created, photographed on production at
    // scrollLeft = 74: the QF column sat half under the name box and Alcaraz's
    // row read `Carlos Alcaraz  5%  67%  62%  43%` — his QF number is 75%.
    // Snapping removes the resting position that eats a digit.
    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    expect(html).toContain("snap-x snap-mandatory");
    // Every value cell is a target — header and rows, or the header drifts off
    // the column it names at the snap position.
    // Read whole tags: the header cell carries a `title=` between its class and
    // its testid, so a class-then-testid regex silently sees the rows only —
    // which is half a guard for a defect that lives in both.
    const valueCells = [...html.matchAll(/<span\s([^>]*)>/g)]
      .map((m) => m[1])
      .filter((attrs) => /data-testid="grid-(column|value-cell)"/.test(attrs))
      .map((attrs) => /class="([^"]*)"/.exec(attrs)?.[1] ?? "");
    expect(valueCells.length).toBe(5 * 2); // one header cell + one row cell, ×5 columns
    for (const cls of valueCells) expect(cls).toContain("snap-start");

    // THE ARITHMETIC, parsed back out of the literal Tailwind class. 138 is the
    // row's own padding + the name track + the gap, i.e. the exact width of the
    // sticky box; if any of the three moves, this fails instead of the layout.
    const padding = /scroll-pl-\[(\d+)px\]/.exec(GRID_SCROLL_SNAP);
    expect(padding).not.toBeNull();
    expect(Number(padding![1])).toBe(
      GRID_ROW_PADDING_PX + GRID_NAME_WIDTH_PX + GRID_GAP_PX
    );
    expect(Number(padding![1])).toBe(138);
    // Which puts the rest positions at 0 and one column-plus-gap along, where
    // the reader can read QF→TITLE whole.
    expect(GRID_COLUMN_WIDTH_PX + GRID_GAP_PX).toBe(60);
    expect(GRID_SCROLL_SNAP).toContain("lg:snap-none");
  });

  it("THE END OF THE SCROLL IS A SNAP POINT, because a browser always rests there", () => {
    // Measured on production with a real wheel gesture, snapping live but the
    // floor still 406: +20 rested at 0, +40 at 52 (both snap points, both
    // whole), and +70 and +120 both rested at 74 — the content END, which is
    // not a snap point and is exactly where a swipe lands. At 74 the QF column
    // sat half under the name box. Rounding the overflow up to a whole column
    // step makes the end a snap point too.
    const step = GRID_COLUMN_WIDTH_PX + GRID_GAP_PX;
    for (const columns of [4, 5, 6, 9]) {
      const overflow = gridScrollFloorPx(columns) - GRID_CARD_CONTENT_PX;
      expect(gridScrolls(columns)).toBe(true);
      expect(overflow % step).toBe(0); // the end IS a rest position
      expect(gridScrollFloorPx(columns)).toBeGreaterThanOrEqual(gridWidthPx(columns));
      // …and it never over-pads: at most one step of gutter.
      expect(gridScrollFloorPx(columns) - gridWidthPx(columns)).toBeLessThan(step);
    }
    // Five columns: 446 overflows 332 by 114, which rounds to 120 → floor 452.
    expect(gridScrollFloorPx(5)).toBe(452);
    // Four columns: 386 overflows by 54, rounds to one whole step → floor 392.
    expect(gridScrollFloorPx(4)).toBe(392);
  });

  it("A SCROLLING PHONE GRID HAS FIXED VALUE TRACKS, or the floor is eaten", () => {
    // The floor adds width ABOVE the grid's natural width. Free space goes to
    // flexible tracks, so with `1fr` value columns the rounding fed the columns
    // instead of the gutter: measured on production, 46 -> 52 wide, step
    // 52 -> 58, and 104 stopped being a whole step. Fixed tracks while scrolling
    // is the property that makes `gridScrollFloorPx` mean what it says.
    const base = (v: string) => v.split(" ").filter((c) => !c.startsWith("lg:"));
    const lg = (v: string) => v.split(" ").filter((c) => c.startsWith("lg:"));

    // The scrolling variant's PHONE track is a fixed length — no `1fr` anywhere.
    expect(base(GRID_COL_TRACK_FIXED).join(" ")).not.toContain("1fr");
    expect(base(GRID_COL_TRACK_FIXED)).toEqual([
      `[--grid-col-track:${GRID_COLUMN_WIDTH_PX}px]`,
    ]);
    // The non-scrolling variant keeps the flexible track that fills the card.
    expect(base(GRID_COL_TRACK_FLEX).join(" ")).toContain("1fr");
    // Above `lg` nothing scrolls, so the two must not disagree.
    expect(lg(GRID_COL_TRACK_FIXED)).toEqual(lg(GRID_COL_TRACK_FLEX));

    // …and the template consumes the variable rather than hard-coding a track.
    expect(gridTemplate(5)).toContain("var(--grid-col-track)");
    expect(gridTemplate(5)).not.toContain("1fr");

    // The plant rule: the RENDER picks the right variant for each state.
    const five = grid({ columns: COLUMNS });
    const wide = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    expect(gridScrolls(5)).toBe(true);
    for (const c of GRID_COL_TRACK_FIXED.split(" ")) expect(wide).toContain(c);

    const three = grid({ columns: COLUMNS.slice(0, 3) });
    const narrow = renderToStaticMarkup(<PlayoffGrid grid={three} />);
    expect(gridScrolls(3)).toBe(false);
    for (const c of GRID_COL_TRACK_FLEX.split(" ")) expect(narrow).toContain(c);
    expect(narrow).not.toContain(`[--grid-col-track:${GRID_COLUMN_WIDTH_PX}px] `);
  });

  it("a grid that fits keeps its own width — nothing to round", () => {
    expect(gridScrolls(3)).toBe(false);
    expect(gridScrollFloorPx(3)).toBe(gridWidthPx(3));
    expect(gridScrollFloorPx(2)).toBe(gridWidthPx(2));
    // And the component pins no floor at all on one.
    const three = grid({ columns: COLUMNS.slice(0, 3) });
    expect(renderToStaticMarkup(<PlayoffGrid grid={three} />)).not.toContain("min-width:");
  });

  it("does not snap a grid that does not scroll", () => {
    const three = grid({ columns: COLUMNS.slice(0, 3) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={three} />);
    expect(html).not.toContain("snap-x");
    expect(html).not.toContain("snap-start");
  });

  it("leaves the name's own content alone — face, name, seed", () => {
    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    // Ruling 8's avatar and the seed badge are inside the sticky box, so they
    // travel with the name rather than being left behind with the numbers.
    expect(html).toContain("flex min-w-0 items-baseline");
    expect(html).toContain("Carlos Alcaraz");
  });
});

// ---------------------------------------------------------------------------
// #4558 — the phone's name track stops drinking the scroll floor, and a name
// that does not fit takes a second line instead of an ellipsis
// ---------------------------------------------------------------------------

describe("#4558 — three names were clipped and three rows' columns were 6px out", () => {
  it("THE DEFECT: a growable name track on a phone eats the floor and still clips", () => {
    /* Measured on production, `/tournaments/us-open`, 390px, 2026-09-09 19:20
     * PT, with `tools/grid-name-fit-4558.mjs` — which reads the resolved
     * `gridTemplateColumns` and each name cell's own rects, never a screenshot
     * and never the `.truncate` class (a probe keyed on the defect can only
     * ever express the FAIL — ux/1165's `a2c32f61`):
     *
     *   header template        118px 54px 54px 54px 54px 54px
     *   Alexander Zverev       name cell 144px  text 102/114  → `Alexander Zv…`
     *   Ben Shelton            name cell 138px  text  79/79
     *   Karen Khachanov        name cell 144px  text 102/114  → `Karen Khach…`
     *   Lorenzo Musetti        name cell 144px  text 102/105  → `Lorenzo Mus…`
     *
     * Two facts in one measurement. The 6px spread is `gridScrollFloorPx(5)`
     * pinning 452px over a 446px row: free space, handed by "maximize tracks"
     * to the only growable track in the row — and each `<li>` is its OWN grid
     * container, so it is handed out per row, which is why three rows' value
     * columns start 6px right of the other two. And it bought nothing: 102px
     * of name where 114px was wanted still prints an ellipsis.
     */
    expect(gridScrollFloorPx(5) - gridWidthPx(5)).toBe(6);
  });

  it("the phone track is a fixed length, so every row's columns start together", () => {
    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    // The template consumes the variable…
    expect(gridTemplate(5)).toBe("var(--grid-name-track) repeat(5, var(--grid-col-track))");
    expect(html).toContain("grid-template-columns:var(--grid-name-track) repeat(5,");
    // …and the variable is a bare length below `sm`. No `max-content`, no `1fr`,
    // nothing the floor can be poured into.
    const base = GRID_NAME_TRACK.split(" ").filter((c) => !/^(sm|md|lg):/.test(c));
    expect(base).toEqual(["[--grid-name-track:var(--grid-name-w)]"]);
    expect(base.join(" ")).not.toContain("max-content");
    expect(base.join(" ")).not.toContain("1fr");
    // The plant: the class is on the rendered scroller, not merely exported.
    for (const c of GRID_NAME_TRACK.split(" ")) expect(html).toContain(c);
  });

  it("keeps UX-P147 where Alex measured it — the growth limit returns at sm", () => {
    // "Player names truncate too early when the window is not super wide."
    // 560–1024px is a real window with real free space and the names still get
    // first claim on it; the phone's 6px was a rounded-up scroll floor wearing
    // the same shape. Deleting the `sm:` half restores his complaint.
    expect(GRID_NAME_TRACK).toContain(
      "sm:[--grid-name-track:minmax(var(--grid-name-w),max-content)]"
    );
  });

  it("A NAME THAT DOES NOT FIT WRAPS — it does not answer WHO with an ellipsis", () => {
    // The same decision #4538 took on this page's other list the day before,
    // and for Alex's own reason: the row exists to say who. `break-words` is
    // the safety net for a name with no space in it.
    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    const nameSpan = /class="([^"]*)"[^>]*>Carlos Alcaraz</.exec(html);
    expect(nameSpan).not.toBeNull();
    expect(nameSpan![1]).toContain("break-words");
    expect(nameSpan![1]).not.toContain("truncate");
    // …and the box it wraps inside can still shrink, or a flex item's automatic
    // minimum size silently restores the overflow this fixes.
    expect(html).toContain("flex min-w-0");
  });

  it("the sticky box is 138px on EVERY row again, which is what the snap line says", () => {
    // `scroll-pl-[138px]` is transcribed from padding + name track + gap. With
    // a per-row track it was true of the short-name rows and 6px wrong on the
    // long-name ones, so a snapped column rested under the name on those rows
    // and nowhere else. A fixed track makes the transcription true everywhere.
    const padding = /scroll-pl-\[(\d+)px\]/.exec(GRID_SCROLL_SNAP);
    expect(Number(padding![1])).toBe(GRID_ROW_PADDING_PX + GRID_NAME_WIDTH_PX + GRID_GAP_PX);
    // The floor's own invariant, restored: the rounded-up pixels are gutter.
    expect(gridScrollFloorPx(5)).toBeGreaterThan(gridWidthPx(5));
    expect(gridWidthPx(5)).toBe(2 * GRID_ROW_PADDING_PX + GRID_NAME_WIDTH_PX + 5 * (GRID_COLUMN_WIDTH_PX + GRID_GAP_PX));
  });
});

// ---------------------------------------------------------------------------
// #4593 — the OTHER half of the same mechanism: at `sm` and above the free
// space is real, so a per-row track staggers the columns by up to 18px. One
// grid container, adopted by subgrid, is the fix.
// ---------------------------------------------------------------------------

describe("#4593 — the columns are a column because there is only ONE grid", () => {
  // The specimen is the one that was measured: the five men still on the board
  // at 768px on 2026-09-10, names and all. Name LENGTH is the whole mechanism —
  // "Alexander Zverev" is what bought its row a wider track than "Ben Shelton"
  // — so a fixture of equal-length placeholders would render the defect
  // invisible while every assertion below stayed green.
  const MEASURED = [
    "Alexander Zverev", "Ben Shelton", "Frances Tiafoe",
    "Karen Khachanov", "Lorenzo Musetti",
  ];
  const FIVE = grid({
    columns: COLUMNS.slice(0, 5),
    rows: MEASURED.map((name, i) => ({
      entity_key: name.toLowerCase().replace(/ /g, "-"),
      display_name: name,
      seed: null,
      rank: i + 1,
      on_board: true,
      cells: Object.fromEntries(COLUMNS.map((c) => [c.key, cell()])),
    })),
  });
  const render = () => renderToStaticMarkup(<PlayoffGrid grid={FIVE} />);

  it("THE DEFECT: five grids given the same template are not five rows sharing tracks", () => {
    /* Measured on production, `/tournaments/us-open`, 768px, anonymous,
     * 2026-09-10 03:44 PT, with `tools/grid-name-fit-4558.mjs` — which reads
     * the RESOLVED `gridTemplateColumns` and each row's own rects, never a
     * screenshot:
     *
     *   header name track   118px
     *   Alexander Zverev    first value cell at 156.1
     *   Ben Shelton                             138.0
     *   Frances Tiafoe                          138.2
     *   Karen Khachanov                         155.8
     *   Lorenzo Musetti                         147.2
     *
     * 18.1px of stagger across five rows, and the header 38px left of the
     * widest of them — so `QF` did not sit over the QF numbers either. The
     * cause is one word in the old markup: the header and every `<li>` each
     * declared `grid-template-columns`, so `max-content` resolved per row and
     * each row bought its own name width.
     *
     * The guard for that is a COUNT, not a presence: the template string is in
     * the markup before AND after the fix, so every `toContain` assertion on it
     * is green on the bug (the same trap #3417's guard documents). Before the
     * fix a five-row grid printed it 7 times — header + 5 rows + 0 wrapper;
     * now exactly once.
     */
    const declarations = render().match(/grid-template-columns:/g) ?? [];
    expect(declarations).toHaveLength(1);
  });

  it("and the one declaration is on the wrapper that also carries the scroll floor", () => {
    // Both directions in one assertion: the template must be on the element
    // that owns the tracks, not merely present somewhere. `gridScrollFloorPx`
    // pins a min-width on this same element, and free space can only stay out
    // of the tracks if the thing it is pinned to IS the track-holder.
    const wrapper = /<div[^>]*data-testid="grid-tracks"[^>]*>/.exec(render());
    expect(wrapper).not.toBeNull();
    expect(wrapper![0]).toContain(`grid-template-columns:${gridTemplate(5)}`);
    expect(wrapper![0]).toContain(`min-width:${gridScrollFloorPx(5)}px`);
    // …and it is a GRID. `grid-template-columns` on a non-grid element is
    // inert: the subgrids below would then have no parent grid to adopt, fall
    // back to one implicit column, and every number would stack under the
    // name. Dropping this one class breaks the whole table and every other
    // assertion in this file stays green — measured, which is why it is here.
    // Matched as a standalone class token, because `grid-template-columns` and
    // `grid-tracks` both contain the substring.
    const classes = /class="([^"]*)"/.exec(wrapper![0]);
    expect(classes).not.toBeNull();
    expect(classes![1].split(/\s+/)).toContain("grid");
  });

  it("the header, the list AND every row adopt those tracks — the chain is unbroken", () => {
    // A `<li>` can only subgrid its OWN parent, so the `<ol>` has to subgrid
    // too or the rows fall back to their own single-column grid and every
    // number stacks under the name. Three links, asserted by count so that
    // dropping any one of them fails here: 1 header + 1 ol + 5 rows.
    const html = render();
    expect((html.match(/grid-cols-subgrid/g) ?? [])).toHaveLength(7);
    for (const testid of ["grid-header", "grid-row"]) {
      const el = new RegExp(`<(?:div|li)[^>]*data-testid="${testid}"[^>]*>`).exec(html);
      expect(el).not.toBeNull();
      expect(el![0]).toContain("grid-cols-subgrid");
      // Spanning every track is what makes it a row rather than a cell.
      expect(el![0]).toContain("col-span-full");
    }
    expect(/<ol[^>]*class="[^"]*grid-cols-subgrid/.test(html)).toBe(true);
  });

  it("no subgrid re-declares the column gap, which is how they stay aligned", () => {
    // A subgrid with its own `column-gap` overrides the parent's gutter INSIDE
    // itself. Today both would be 6px and nothing would move, which is exactly
    // why this needs a guard rather than a comment: the misalignment appears
    // the day one of the two is changed and the other is not. The gap is
    // declared once, on the wrapper, and inherited by all three subgrids.
    const html = render();
    const rowLike = html.match(/<(?:div|li|ol)[^>]*grid-cols-subgrid[^>]*>/g) ?? [];
    expect(rowLike.length).toBeGreaterThan(0);
    for (const el of rowLike) {
      expect(el).not.toMatch(/\bgap-1\.5\b/);
      expect(el).not.toMatch(/\bgap-x-/);
    }
    const wrapper = /<div[^>]*data-testid="grid-tracks"[^>]*>/.exec(html);
    expect(wrapper![0]).toContain("gap-x-1.5");
  });

  it("the padding is on the track holder, and every subgrid cancels its own", () => {
    /* THE ARITHMETIC INVARIANT, and the one this fix got wrong on the first
     * attempt. A subgrid contributes its own padding to the first and last
     * tracks it spans. Leaving `px-3.5` on the rows reads as harmless — above
     * `sm` the name track is `minmax(…,max-content)` and just grows by it — but
     * below `sm` that track is a FIXED length, so the padding comes out of the
     * NAME. Measured at 390px: text room per row 96px → 82px and the first
     * value column 138px → 124px, which also desyncs the `138` that
     * `GRID_SCROLL_SNAP` transcribes. #4558's defect, reintroduced by #4593's
     * fix, with every other guard in this file still green.
     *
     * So: the padding lives on the track holder, OUTSIDE the tracks, which is
     * where `gridWidthPx`'s `2 * GRID_ROW_PADDING_PX + …` has always assumed it
     * was; and each subgridded row cancels it with `-mx` + matching `px` so its
     * border box stays full-bleed (the dividers reach the card's edge, as they
     * do on production today) while its content box lands back on the shared
     * tracks. Asserted as a PAIR, because either half alone is a defect: `-mx`
     * without `px` parts the columns, `px` without `-mx` shortens the name.
     */
    const html = render();
    const classesOf = (el: string) => (/class="([^"]*)"/.exec(el)?.[1] ?? "").split(/\s+/);
    const wrapper = /<div[^>]*data-testid="grid-tracks"[^>]*>/.exec(html)![0];

    // The track holder carries it, at both breakpoints.
    expect(classesOf(wrapper)).toEqual(expect.arrayContaining(["px-3.5", "lg:px-5"]));
    // …and it is the same number the rest of this file is transcribed from, so
    // the two cannot drift apart silently.
    expect(classesOf(wrapper)).toContain(`px-${GRID_ROW_PADDING_PX / 4}`);

    // Every subgridded item cancels it, in both directions and at both breakpoints.
    const subgrids = html.match(/<(?:div|li|ol)[^>]*grid-cols-subgrid[^>]*>/g) ?? [];
    expect(subgrids).toHaveLength(7); // 1 header + 1 ol + 5 rows
    for (const el of subgrids) {
      const c = classesOf(el);
      const padded = c.includes("px-3.5");
      // The `<ol>` is a pure pass-through link in the chain and carries neither.
      expect(padded ? c.includes("-mx-3.5") : !c.includes("-mx-3.5")).toBe(true);
      if (padded) expect(c).toEqual(expect.arrayContaining(["lg:px-5", "lg:-mx-5"]));
    }
    // The header and the rows are the ones that must be padded — asserted by
    // count so that dropping the pair from one of them fails here rather than
    // reading as "no subgrid is padded, therefore consistent".
    expect(subgrids.filter((el) => classesOf(el).includes("px-3.5"))).toHaveLength(6);
  });

  it("the show-more control spans the table, not the name column", () => {
    // The wrapper is a grid now, so a bare child lands in track 1 and
    // `ShowMore`'s own `w-full` measures 118px instead of the table.
    const many = grid({
      rows: Array.from({ length: COLLAPSED_LIST_COUNT + 2 }, (_, i) => ({
        entity_key: `p-${i}`, display_name: `Player ${i}`, seed: null,
        rank: i + 1, on_board: true,
        cells: Object.fromEntries(COLUMNS.map((c) => [c.key, cell()])),
      })),
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={many} />);
    const button = /<button[^>]*>/.exec(html);
    expect(button).not.toBeNull();
    // The control exists, the element wrapping it spans every track, and it
    // cancels the holder's padding the same way the rows do — its top border is
    // one of the dividers a reader sees, and on production that reaches the
    // card's edge like all the others.
    const wrap = /<div class="([^"]*)">\s*<button/.exec(html);
    expect(wrap).not.toBeNull();
    const wrapClasses = wrap![1].split(/\s+/);
    expect(wrapClasses).toContain("col-span-full");
    expect(wrapClasses).toEqual(expect.arrayContaining(["-mx-3.5", "lg:-mx-5"]));
  });

  it("a trailing filler track is what makes a row reach the card's edge", () => {
    // `col-span-full` spans the TRACKS, and the tracks total `gridWidthPx` —
    // 446px for five columns — inside a card that is far wider. Without a
    // filler every `border-t` stops under the Title column instead of running
    // edge to edge, which is what production draws today. It must be LAST, or
    // it moves the value columns; and `minmax(0,1fr)` rather than `1fr` so it
    // collapses instead of imposing an auto minimum when the grid scrolls.
    const wrapper = /<div[^>]*data-testid="grid-tracks"[^>]*>/.exec(render())![0];
    const template = /grid-template-columns:([^;"]*)/.exec(wrapper);
    expect(template).not.toBeNull();
    expect(template![1].trim()).toBe(`${gridTemplate(5)} minmax(0,1fr)`);
  });

  it("UX-P147 survives: the name track is still the only growable one", () => {
    // Sharing the tracks must not change WHICH track wins the free space.
    // Alex: "names get priority over bar width; bars compress first." The name
    // track's `max-content` is a growth limit and `1fr` is not, so the name
    // still fills before the bars — it now just reaches one width for
    // everybody rather than five.
    expect(GRID_NAME_TRACK).toContain("max-content");
    expect(gridTemplate(5)).toBe("var(--grid-name-track) repeat(5, var(--grid-col-track))");
    // And the phone half of #4558 is untouched by the structural change: a
    // fixed track below `sm` is still what keeps the rounded-up scroll floor
    // out of the name, shared container or not.
    const base = GRID_NAME_TRACK.split(" ").filter((c) => !/^(sm|md|lg):/.test(c));
    expect(base).toEqual(["[--grid-name-track:var(--grid-name-w)]"]);
  });
});

// ---------------------------------------------------------------------------
// Item 1 — the draw notice says WHEN
// ---------------------------------------------------------------------------

describe("item 1 — the draw panel states the date and time", () => {
  it("names the ceremony and the first round", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket
        grid={null}
        drawReleased={false}
        drawReleaseLabel="Thursday 27 August, 12:00 ET"
        mainDrawLabel="Sunday 30 August"
      />
    );
    expect(html).toContain('data-has-release-time="true"');
    expect(html).toContain('data-testid="draw-release-label"');
    expect(html).toContain("Thursday 27 August, 12:00 ET");
    expect(html).toContain("Sunday 30 August");
  });

  it("degrades to the old sentence when no date is supplied", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} drawReleased={false} />
    );
    expect(html).toContain("Draw not released");
    expect(html).toContain('data-has-release-time="false"');
  });

  it("shows the GRID before the draw, with the date above it", () => {
    // The markets that fill this grid are live today; withholding it until a
    // ceremony would be an empty page over tradeable truth.
    const html = renderToStaticMarkup(
      <TournamentBracket
        grid={grid()}
        drawReleased={false}
        drawReleaseLabel="Thursday 27 August, 12:00 ET"
      />
    );
    expect(html).toContain('data-testid="playoff-grid"');
    expect(html).toContain("Thursday 27 August, 12:00 ET");
    expect(html.indexOf("Thursday 27 August")).toBeLessThan(
      html.indexOf('data-testid="playoff-grid"')
    );
  });
});

// ---------------------------------------------------------------------------
// The display vocabulary
// ---------------------------------------------------------------------------

describe("the cell vocabulary", () => {
  it("names every state in a sentence a reader can hear", () => {
    expect(gridCellExplanation(cell({ state: "live" }), "To reach the semi-finals"))
      .toContain("Live number");
    expect(gridCellExplanation(cell({ state: "stale", age_hours: 27 }), "SF"))
      .toContain("27h ago");
    expect(gridCellExplanation(cell({ state: "no_market", note: "No SF market at kalshi" }), "SF"))
      .toContain("No SF market at kalshi");
    expect(gridCellExplanation(cell({ state: "unlinked", note: "x" }), "SF"))
      .toContain("fault on our side");
  });

  it("glyphs a settled cell by its result, not by a shared dash", () => {
    expect(gridCellGlyph(cell({ state: "settled", note: "won" }))).toBe("✓");
    expect(gridCellGlyph(cell({ state: "settled", note: "eliminated" }))).toBe("—");
    // #4171 item 2 — a no-market cell prints nothing; see its own test above.
    expect(gridCellGlyph(cell({ state: "no_market" }))).toBe("");
    expect(gridCellGlyph(cell({ state: "unlinked" }))).toBe("!");
  });

  it("a player who is THROUGH gets a tick, not the out dash (#4174)", () => {
    // The draw decides these two, not the market: `reached` is "they are in
    // this round", `out` is "they are not in the tournament". Both used to
    // arrive as a stale probability with a bar under it.
    expect(gridCellGlyph(cell({ state: "settled", note: "reached" }))).toBe("✓");
    expect(gridCellGlyph(cell({ state: "settled", note: "out" }))).toBe("—");
  });

  it("a decided cell says what happened, in words (#4174)", () => {
    expect(
      gridCellExplanation(cell({ state: "settled", note: "reached" }), "To reach the semi-finals")
    ).toBe("To reach the semi-finals. Reached.");
    expect(
      gridCellExplanation(
        cell({ state: "settled", note: "out", settled_round: "R32" }),
        "To reach the final"
      )
    ).toBe("To reach the final. Out in the third round.");
    // No exit round on the cell, and no invented one either.
    expect(
      gridCellExplanation(cell({ state: "settled", note: "out" }), "To win the title")
    ).toBe("To win the title. Out of the tournament.");
    // A round key we have no words for stays off the screen.
    expect(
      gridCellExplanation(
        cell({ state: "settled", note: "out", settled_round: "R9999" }),
        "To win the title"
      )
    ).toBe("To win the title. Out of the tournament.");
    // The market's own terminal word still reads as it always did.
    expect(
      gridCellExplanation(cell({ state: "settled", note: "eliminated" }), "SF")
    ).toBe("SF. Settled: eliminated.");
  });

  it("formats an age without ever claiming to know one it does not", () => {
    expect(formatAge(0.4)).toBe("24m");
    expect(formatAge(27)).toBe("27h");
    expect(formatAge(200)).toBe("8d");
    expect(formatAge(null)).toBe("an unknown time");
  });

  it("calls only an alarm red — a failing sum is the market, not us", () => {
    expect(gridEvalVerdict(grid())).toBe("green");
    expect(
      gridEvalVerdict(
        grid({
          column_sums: [{ key: "F", short_label: "Final", sum: 2.8, expected: 2,
            ratio: 1.4, priced_rows: 4, total_rows: 4, verdict: "over" }],
        })
      )
    ).toBe("green");
    expect(gridEvalVerdict(grid({ alarm_cells: 1 }))).toBe("red");
  });

  it("wording for a passing column states the target", () => {
    expect(
      columnSumSentence({ key: "SF", short_label: "SF", sum: 4.0, expected: 4,
        ratio: 1, priced_rows: 44, total_rows: 56, verdict: "pass" })
    ).toContain("4 places still to be won — as it should");
  });

  it("does not write \"1 places\" on the title column", () => {
    const sentence = columnSumSentence({
      key: "title", short_label: "Title", sum: 1.21, expected: 1,
      ratio: 1.21, priced_rows: 36, total_rows: 56, verdict: "over",
    });
    expect(sentence).toContain("against 1 place ");
    expect(sentence).not.toContain("1 places");
  });

  it("names the target as what is still to be won, not the round's size", () => {
    // #4174: two of the four semi-final places were already taken, and the
    // column was being asked to add up to four.
    expect(
      columnSumSentence({ key: "SF", short_label: "SF", sum: 1.8, expected: 2, slots: 4,
        ratio: 0.9, priced_rows: 10, decided_rows: 40, uncovered_rows: 6,
        total_rows: 56, verdict: "pass" })
    ).toContain("2 places still to be won");
  });
});

describe("readPlayoffGrid", () => {
  it("returns null for an absent grid rather than an empty one", () => {
    // Different states: "this draw has no grid" must not render as "this draw
    // has an empty grid", which is a claim about the markets.
    expect(readPlayoffGrid(undefined)).toBeNull();
    expect(readPlayoffGrid(null)).toBeNull();
  });

  it("carries on_board through, so an unranked tail can explain itself", () => {
    const model = grid({
      rows: [{
        entity_key: "gael-monfils", display_name: "Gael Monfils", seed: null,
        rank: null, on_board: false,
        cells: Object.fromEntries(COLUMNS.map((c) => [c.key, cell()])),
      }],
    });
    expect(model.rows[0].onBoard).toBe(false);
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).toContain('data-on-board="false"');
  });
});
