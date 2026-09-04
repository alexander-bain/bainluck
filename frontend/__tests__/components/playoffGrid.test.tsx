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

import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import TournamentBracket from "@/components/tournament/TournamentBracket";
import {
  columnSumSentence,
  formatAge,
  gridCellExplanation,
  gridCellGlyph,
  gridEvalVerdict,
  GRID_CARD_CONTENT_PX,
  GRID_GAP_PX,
  GRID_ROW_PADDING_PX,
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

  it("a no-market cell says NO MKT, not a dot or a dash", () => {
    // "·" is a fact about the layout; "no mkt" is a fact about the world, and
    // UX-P137's ruling 2 exists because the reader could not tell them apart.
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
    expect(html).toContain("no mkt");
    expect(html).toContain("No R16 market at kalshi, polymarket");
    // The censused absence is NOT an alarm, and the banner must not fire.
    expect(html).not.toContain('data-testid="grid-alarm-banner"');
    expect(html).toContain('data-testid="grid-no-market"');
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

  it("shows the sum check on the page", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid()} />);
    expect(html).toContain('data-testid="grid-sum-check"');
    expect((html.match(/data-testid="grid-sum-row"/g) ?? []).length).toBe(5);
    expect(html).toContain("4 places");
  });

  it("names an over-summing column and does NOT rescale it", () => {
    const model = grid({
      column_sums: [
        { key: "F", short_label: "Final", sum: 2.781, expected: 2, ratio: 1.39,
          priced_rows: 44, total_rows: 56, verdict: "over" },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).toContain('data-verdict="over"');
    expect(html).toContain("2.8");
    expect(html).toContain("rather than scaling it down");
    // The CELLS are untouched — the check is a diagnostic, never a corrector.
    // 0.375 in the F column still prints 38%, not a rescaled 27%.
    expect(html).toContain('data-column="F"');
    expect(html).toContain("38%");
  });

  it("explains an under-summing column with its coverage count", () => {
    const model = grid({
      column_sums: [
        { key: "R16", short_label: "R16", sum: 13.667, expected: 16, ratio: 0.854,
          priced_rows: 44, total_rows: 56, verdict: "under" },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).toContain('data-verdict="under"');
    expect(html).toContain("12 of 56 players have no market");
  });

  it("reports monotonicity violations without hiding the numbers", () => {
    const model = grid({
      monotonicity_violations: [
        { entity_key: "cameron-norrie", display_name: "Cameron Norrie",
          earlier: "SF", later: "F", earlier_probability: 0.04, later_probability: 0.05 },
      ],
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={model} />);
    expect(html).toContain('data-testid="grid-monotonicity"');
    expect(html).toContain("Cameron Norrie (SF → F)");
    // UX-P145 reworded the sentence around this ("are priced higher" → "have a
    // higher chance"). What the assertion is FOR is unchanged: the page says it
    // noticed and still shows the market's own numbers rather than correcting
    // them. `tournamentPlainLanguage.test.tsx` guards the vocabulary.
    expect(html).toContain("shown exactly as quoted");
    expect(html).toContain("higher chance for a later round");
  });
});

// ---------------------------------------------------------------------------
// Ruling 5 — scrolling, sparingly
// ---------------------------------------------------------------------------

describe("ruling 5 — wide rounds scroll rather than lose a column", () => {
  it("counts a row's PADDING and GAPS, not only its tracks (#3072)", () => {
    // The old formula was `name + n × col` — tracks only. A row is
    // `px-3.5` + name + `gap-1.5` + col + `gap-1.5` + col …, so five columns
    // need 28 + 118 + 230 + 30 = 406px, not 348.
    expect(GRID_ROW_PADDING_PX).toBe(14);
    expect(GRID_GAP_PX).toBe(6);
    expect(gridWidthPx(5)).toBe(406);
    expect(gridWidthPx(6)).toBe(458);
    expect(gridWidthPx(3)).toBe(302);
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
    // data. A three-column grid fits (302 <= 332) and stays still.
    expect(gridScrolls(3)).toBe(false);
    expect(gridScrolls(2)).toBe(false);
  });

  it("the rendered five-column grid is a scroller, and its floor is the whole row", () => {
    const five = grid({ columns: COLUMNS.slice(0, 5) });
    const html = renderToStaticMarkup(<PlayoffGrid grid={five} />);
    expect(html).toContain('data-scrolls="true"');
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain(`min-width:${gridWidthPx(5)}px`);
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
    expect(gridCellGlyph(cell({ state: "no_market" }))).toBe("no mkt");
    expect(gridCellGlyph(cell({ state: "unlinked" }))).toBe("!");
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
    ).toContain("4 places — as it should");
  });

  it("does not write \"1 places\" on the title column", () => {
    expect(
      columnSumSentence({ key: "title", short_label: "Title", sum: 1.21, expected: 1,
        ratio: 1.21, priced_rows: 36, total_rows: 56, verdict: "over" })
    ).toContain("against 1 place.");
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
