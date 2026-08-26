/**
 * THE BRACKET TAB and its fold logic (UX-P131, restructured by UX-P138).
 *
 * Charter amendment 2026-08-25: the bracket does not wait for Thursday's draw
 * ceremony. This suite is what makes that real — the fold logic is gated now,
 * against a synthetic fixture, so 08-28 swaps the data source and nothing else.
 *
 * The assertion that matters most is still the one about projection: nothing
 * advances without a declared result, and no cell is ever computed. A bracket
 * that greys in a projected winner, or a grid that chains match odds into
 * P(reach the semis), looks identical to one showing a measured fact — and the
 * charter's reliability doctrine is that every element does what it looks like
 * it does.
 *
 * UX-P138 (Alex's ruling 4) moved the MATCH RENDERING out of this component
 * and onto the Tournament tab. Those assertions now live in
 * `tournamentMatches.test.tsx`; what is left here is the fold, the pre-draw
 * state, and the playoff grid that replaced the round strip.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import TournamentBracket from "@/components/tournament/TournamentBracket";
import PlayoffGrid from "@/components/tournament/PlayoffGrid";
import { bracketProgress, buildBracket, roundIsUnreached, ROUND_NAMES } from "@/lib/bracket";
import { buildMatchList } from "@/lib/matchList";
import {
  GRID_MAX_REACH_COLUMNS,
  GRID_SECTION_LABEL,
  buildPlayoffGrid,
  formatGridCell,
  nextRoundOdds,
  roundAfter,
} from "@/lib/playoffGrid";
import type { PropMarket } from "@/lib/tournamentProps";
import type { SlateMatch, SlateSide } from "@/lib/slate";
import type { TournamentBoardData, TournamentRow } from "@/lib/tournament";
import {
  SYNTHETIC_MENS_DRAW,
  SYNTHETIC_WOMENS_DRAW,
  syntheticDrawWithHoles,
  syntheticFirstRoundResults,
  syntheticPartialResults,
} from "../fixtures/syntheticDraw";

const count = (html: string, needle: string) =>
  (html.match(new RegExp(needle, "g")) ?? []).length;

describe("the synthetic fixture is a usable stand-in for a real draw", () => {
  it("carries a full 128-slot draw for both sides", () => {
    expect(SYNTHETIC_MENS_DRAW).toHaveLength(128);
    expect(SYNTHETIC_WOMENS_DRAW).toHaveLength(128);
  });

  it("has unique entity keys — a duplicate would fake a bracket collision", () => {
    const keys = new Set(SYNTHETIC_MENS_DRAW.map((s) => s.entity_key));
    expect(keys.size).toBe(128);
  });

  it("is deterministic across builds", () => {
    expect(SYNTHETIC_MENS_DRAW[0].entity_key).toBe("syn-m-1");
    expect(SYNTHETIC_MENS_DRAW[127].entity_key).toBe("syn-m-128");
    expect(SYNTHETIC_MENS_DRAW[0].display_name).toBe(SYNTHETIC_MENS_DRAW[0].display_name);
  });

  it("leaves most of the field without a title probability, as a real draw does", () => {
    const priced = SYNTHETIC_MENS_DRAW.filter((s) => s.probability !== null);
    expect(priced).toHaveLength(16);
    expect(SYNTHETIC_MENS_DRAW[100].probability).toBeNull();
  });

  it("mixes seeded and unseeded entrants", () => {
    const seeded = SYNTHETIC_MENS_DRAW.filter((s) => s.seed !== null);
    expect(seeded.length).toBeGreaterThan(0);
    expect(seeded.length).toBeLessThan(128);
  });
});

describe("buildBracket folds a draw into rounds", () => {
  const rounds = buildBracket(SYNTHETIC_MENS_DRAW);

  it("produces seven rounds from a 128 draw, ending at the final", () => {
    expect(rounds.map((r) => r.round)).toEqual([...ROUND_NAMES]);
    expect(rounds[rounds.length - 1].round).toBe("F");
  });

  it("halves the match count each round", () => {
    expect(rounds.map((r) => r.matches.length)).toEqual([64, 32, 16, 8, 4, 2, 1]);
  });

  it("pairs adjacent slots in the first round", () => {
    const first = rounds[0].matches[0];
    expect(first.top?.entity_key).toBe("syn-m-1");
    expect(first.bottom?.entity_key).toBe("syn-m-2");
  });

  it("starts a 32-slot draw at R32, not at R128", () => {
    const small = buildBracket(SYNTHETIC_MENS_DRAW.slice(0, 32));
    expect(small[0].round).toBe("R32");
    expect(small[small.length - 1].round).toBe("F");
  });

  it("refuses a draw that is not a power of two rather than truncating it", () => {
    expect(buildBracket(SYNTHETIC_MENS_DRAW.slice(0, 100))).toEqual([]);
    expect(buildBracket([])).toEqual([]);
  });
});

describe("an unplayed bracket projects nothing", () => {
  const rounds = buildBracket(SYNTHETIC_MENS_DRAW);

  it("declares no winners", () => {
    expect(rounds.every((r) => r.matches.every((m) => m.winnerKey === null))).toBe(true);
  });

  it("leaves every later round empty rather than guessing at it", () => {
    const secondRound = rounds[1];
    expect(secondRound.matches.every((m) => m.top === null && m.bottom === null)).toBe(true);
  });

  it("reports honest progress", () => {
    expect(bracketProgress(rounds)).toEqual({ played: 0, total: 127 });
  });
});

describe("results advance winners and only winners", () => {
  const results = syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW);
  const rounds = buildBracket(SYNTHETIC_MENS_DRAW, results);

  it("carries first-round winners into the second round", () => {
    expect(rounds[0].matches[0].winnerKey).toBe("syn-m-1");
    expect(rounds[1].matches[0].top?.entity_key).toBe("syn-m-1");
    expect(rounds[1].matches[0].bottom?.entity_key).toBe("syn-m-3");
  });

  it("does not advance past the results it was given", () => {
    expect(rounds[1].matches.every((m) => m.winnerKey === null)).toBe(true);
    expect(rounds[2].matches.every((m) => m.top === null && m.bottom === null)).toBe(true);
  });

  it("counts only decided matches", () => {
    expect(bracketProgress(rounds)).toEqual({ played: 64, total: 127 });
  });
});

describe("NOTHING advances without a declared result (UX-P136 regression)", () => {
  // The bug: a `null` opponent slot was read as a bye and advanced the other
  // side. It fired in two places, and BOTH printed a player into a round it
  // had not reached — the one thing the charter forbids, because a projection
  // rendered this way is indistinguishable from a result.

  it("does not advance a winner past an UNDECIDED sibling match", () => {
    // Two first-round matches feed R64-1. Decide only the first. The winner of
    // R128-1 belongs in R64 and NOWHERE further, because R128-2 is still on
    // court and R64-1 therefore has not been played.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 1));

    expect(rounds[1].matches[0].top?.entity_key).toBe("syn-m-1");
    expect(rounds[1].matches[0].bottom).toBeNull();
    // The bug walked syn-m-1 straight into R32 for beating an empty slot.
    expect(rounds[1].matches[0].winnerKey).toBeNull();
    expect(rounds[2].matches[0].top).toBeNull();
    expect(rounds[2].matches[0].bottom).toBeNull();
  });

  it("keeps a half-played first round out of every later round", () => {
    // THIRTY-THREE, not thirty-two, and the odd number is the whole point. An
    // even count fills R64 in complete pairs, so no match is ever left with
    // one side — the bug cannot fire and a green here would mean nothing. At
    // 33, R64's seventeenth match holds one name against an empty slot, which
    // is exactly the shape that used to promote him.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 33));
    const named = rounds[1].matches.flatMap((m) => [m.top, m.bottom]).filter(Boolean);
    expect(named).toHaveLength(33);
    expect(rounds[1].matches[16].top?.entity_key).toBe("syn-m-65");
    expect(rounds[1].matches[16].bottom).toBeNull();
    for (const later of rounds.slice(2)) {
      expect(later.matches.every((m) => m.top === null && m.bottom === null)).toBe(true);
    }
  });

  it("treats a register HOLE as undetermined, not as a bye", () => {
    // The backend's own contract: `None` is "a slot we hold no registered
    // player for … not a bye, and never a name we invented". The fold used to
    // disagree with the function feeding it, and promoted the opponent.
    const holed = syntheticDrawWithHoles(SYNTHETIC_MENS_DRAW, [1]);
    const rounds = buildBracket(holed);

    expect(rounds[0].matches[0].top?.entity_key).toBe("syn-m-1");
    expect(rounds[0].matches[0].bottom).toBeNull();
    expect(rounds[0].matches[0].winnerKey).toBeNull();
    // syn-m-1 did not win the Round of 128 by being the only one in it.
    expect(rounds[1].matches[0].top).toBeNull();
  });

  it("refuses a result naming somebody who is not in the match", () => {
    // A data fault, and the honest response is an empty slot rather than a
    // name teleported across the draw.
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, { "R128-1": "syn-m-99" });
    expect(rounds[0].matches[0].winnerKey).toBeNull();
    expect(rounds[1].matches[0].top).toBeNull();
  });
});

describe("roundIsUnreached", () => {
  it("is true for a round nobody has got to, false for one with names", () => {
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW));
    expect(roundIsUnreached(rounds[0])).toBe(false);
    expect(roundIsUnreached(rounds[1])).toBe(false);
    expect(roundIsUnreached(rounds[2])).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Shared fixtures for the grid — a board, a slate, curated advance markets
// ---------------------------------------------------------------------------

function row(overrides: Partial<TournamentRow> = {}): TournamentRow {
  return {
    entity_key: "carlos-alcaraz",
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: null,
    rank: 1,
    state: "live",
    probability: 0.31,
    probability_is_live: true,
    observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 0.2,
    price_state: "live",
    freshest_observed_at: "2026-08-26T20:00:00+00:00",
    freshest_age_hours: 0.2,
    stale_sources: [],
    mixed_freshness: false,
    source_count: 2,
    sources: [],
    blend_rule: "equal_weight_midpoint",
    divergent: false,
    trend: [],
    trend_delta: null,
    ...overrides,
  };
}

function boardOf(rows: TournamentRow[], draw = "mens-singles"): TournamentBoardData {
  return {
    draw,
    label: draw === "mens-singles" ? "Men's Singles" : "Women's Singles",
    rows,
    contenders: rows.length,
    unpriced: 0,
    rows_not_live: 0,
    mixed_freshness_rows: 0,
    price_state: "live",
    newest_observed_at: "2026-08-26T20:00:00+00:00",
    age_hours: 0.2,
  };
}

function slateSide(overrides: Partial<SlateSide> = {}): SlateSide {
  return {
    entity_key: "carlos-alcaraz",
    display_name: "Carlos Alcaraz",
    seed: 1,
    country: null,
    role: "participant",
    probability: 0.78,
    opening_probability: 0.74,
    move: 0.04,
    raw_probability: 0.78,
    raw_opening_probability: 0.74,
    age_hours: 0.2,
    price_state: "live",
    ...overrides,
  };
}

function slateMatch(overrides: Partial<SlateMatch> = {}): SlateMatch {
  return {
    matchup_key: "mens-singles:alcaraz-vs-rublev:2026-08-31",
    draw: "mens-singles",
    draw_label: "Men's Singles",
    round: "R64",
    scheduled_date: "2026-08-31T15:00:00+00:00",
    sides: [
      slateSide(),
      slateSide({
        entity_key: "andrey-rublev",
        display_name: "Andrey Rublev",
        seed: 9,
        probability: 0.22,
        opening_probability: 0.26,
        move: -0.04,
      }),
    ],
    coherent: true,
    raw_sum: 1,
    opening_raw_sum: 1,
    probability_is_live: true,
    price_state: "live",
    observed_at: "2026-08-31T14:50:00+00:00",
    age_hours: 0.2,
    freshest_observed_at: "2026-08-31T14:50:00+00:00",
    freshest_age_hours: 0.2,
    stale_sides: [],
    mixed_freshness: false,
    favourite: "carlos-alcaraz",
    has_moved: true,
    source_count: 1,
    ...overrides,
  };
}

function advanceProp(
  key: string,
  title: string,
  probability: number,
  draw = "mens-singles",
  live = false
): PropMarket {
  return {
    key,
    title,
    hook: null,
    draw,
    source: "polymarket",
    answer_entity_key: `${key}:yes`,
    price_state: live ? "live" : "stale",
    observed_at: "2026-08-25T20:00:00+00:00",
    age_hours: live ? 0.5 : 24.6,
    freshest_observed_at: "2026-08-25T20:00:00+00:00",
    freshest_age_hours: live ? 0.5 : 24.6,
    stale_outcomes: live ? [] : [`${key}:yes`],
    mixed_freshness: false,
    outcomes: [
      {
        entity_key: `${key}:yes`,
        display_name: "Yes",
        probability,
        probability_is_live: live,
        observed_at: "2026-08-25T20:00:00+00:00",
        age_hours: live ? 0.5 : 24.6,
        price_state: live ? "live" : "stale",
        is_answer: true,
      },
    ],
  };
}

// ---------------------------------------------------------------------------
// Ruling 1 (UX-P137) — the pre-draw view is not empty. UNCHANGED BY UX-P138.
// ---------------------------------------------------------------------------

describe("ruling 1 — the pre-draw view is not empty", () => {
  const boards = [
    boardOf([row({ display_name: "Ivan Petrenko" })], "mens-singles"),
    boardOf(
      [row({ entity_key: "marta-k", display_name: "Marta Kowalczyk" })],
      "womens-singles"
    ),
  ];

  it("shows BOTH winner boards before the draw exists", () => {
    // "Never an empty page when tradeable truth exists." Both, not the one
    // behind the gender pill — on the day before a ceremony there is exactly
    // one question and it has two answers.
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} drawReleased={false} preDrawBoards={boards} />
    );
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect(count(html, 'data-testid="tournament-board"')).toBe(2);
    expect(html).toContain("Ivan Petrenko");
    expect(html).toContain("Marta Kowalczyk");
  });

  it("still says the draw is not out — the boards are an addition, not a cover", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} drawReleased={false} preDrawBoards={boards} />
    );
    expect(html).toContain("Draw not released");
  });

  it("degrades to the honest sentence when there are no boards either", () => {
    const html = renderToStaticMarkup(
      <TournamentBracket grid={null} drawReleased={false} />
    );
    expect(html).toContain("Draw not released");
    expect(html).not.toContain('data-testid="tournament-board"');
  });

  it("falls back to the pre-draw state when the draw IS out but the grid is empty", () => {
    // The other direction, and the one a release-day bug lands on: the flag
    // latches, the prices have not arrived, and a released-but-empty tab would
    // render a titled box containing a header row and nothing else.
    const html = renderToStaticMarkup(
      <TournamentBracket
        grid={buildPlayoffGrid({ board: null, draw: "mens-singles" })}
        drawReleased
        preDrawBoards={boards}
      />
    );
    expect(html).toContain('data-testid="bracket-unreleased"');
    expect(html).not.toContain('data-testid="playoff-grid"');
  });
});

// ---------------------------------------------------------------------------
// Ruling 4 — the Bracket tab is the playoff grid
// ---------------------------------------------------------------------------

describe("roundAfter — the one piece of round arithmetic in the grid", () => {
  it("walks the draw forward, and stops at the final", () => {
    expect(roundAfter("qualifying")).toBe("R128");
    expect(roundAfter("R128")).toBe("R64");
    expect(roundAfter("QF")).toBe("SF");
    expect(roundAfter("SF")).toBe("F");
    expect(roundAfter("F")).toBeNull();
  });

  it("covers every round name, so a new round cannot fall off the end silently", () => {
    for (const name of ROUND_NAMES.slice(0, -1)) {
      expect(roundAfter(name)).not.toBeNull();
    }
  });
});

describe("nextRoundOdds — winning your match IS reaching the next round", () => {
  it("reads the price straight off an undecided match, with no arithmetic", () => {
    const entries = buildMatchList({ slate: [slateMatch()] });
    const odds = nextRoundOdds(entries);
    expect(odds["carlos-alcaraz"]).toEqual({
      round: "R32",
      probability: 0.78,
      isLive: true,
    });
    expect(odds["andrey-rublev"].probability).toBe(0.22);
  });

  it("ignores a DECIDED match — 1 or 0 is a result, not a forecast", () => {
    const entries = buildMatchList({
      slate: [slateMatch({ winner_entity_key: "carlos-alcaraz" })],
    });
    expect(nextRoundOdds(entries)).toEqual({});
  });

  it("ignores an incoherent pair rather than laundering it into a cell", () => {
    const entries = buildMatchList({
      slate: [
        slateMatch({
          coherent: false,
          sides: [
            slateSide({ probability: null }),
            slateSide({ entity_key: "andrey-rublev", display_name: "Andrey Rublev", probability: null }),
          ],
        }),
      ],
    });
    expect(nextRoundOdds(entries)).toEqual({});
  });

  it("keeps the EARLIER hurdle when a feed offers a player two matches", () => {
    const entries = buildMatchList({
      slate: [
        slateMatch({ matchup_key: "later", round: "QF" }),
        slateMatch({ matchup_key: "earlier", round: "R64" }),
      ],
    });
    // R64 -> reaches R32; QF -> reaches SF. The first hurdle wins.
    expect(nextRoundOdds(entries)["carlos-alcaraz"].round).toBe("R32");
  });
});

describe("buildPlayoffGrid — every cell is a price, and holes stay holes", () => {
  const rows = [
    row(),
    row({ entity_key: "andrey-rublev", display_name: "Andrey Rublev", seed: 9, rank: 2, probability: 0.09 }),
    row({ entity_key: "jannik-sinner", display_name: "Jannik Sinner", seed: 2, rank: 3, probability: 0.28 }),
  ];
  const board = boardOf(rows);
  const props = [
    advanceProp("alcaraz-semifinals", "Does Alcaraz reach the semifinals?", 0.575),
  ];
  const matches = buildMatchList({ slate: [slateMatch()] });

  it("fills the next-round column from the match price", () => {
    const grid = buildPlayoffGrid({ board, propMarkets: props, matches, draw: "mens-singles" });
    const alcaraz = grid.rows.find((r) => r.entityKey === "carlos-alcaraz");
    expect(alcaraz?.cells.R32).toMatchObject({
      probability: 0.78,
      state: "priced",
      origin: "match",
    });
  });

  it("fills a curated column from the register's own market", () => {
    const grid = buildPlayoffGrid({ board, propMarkets: props, matches, draw: "mens-singles" });
    const alcaraz = grid.rows.find((r) => r.entityKey === "carlos-alcaraz");
    expect(alcaraz?.cells.SF).toMatchObject({
      probability: 0.575,
      state: "priced",
      origin: "curated",
    });
  });

  it("fills the title column from the BOARD, not from the draw slot", () => {
    const grid = buildPlayoffGrid({ board, propMarkets: props, matches, draw: "mens-singles" });
    const alcaraz = grid.rows.find((r) => r.entityKey === "carlos-alcaraz");
    expect(alcaraz?.cells.title).toMatchObject({ probability: 0.31, origin: "board" });
  });

  it("NEVER computes a cell — an unpriced middle round stays unpriced", () => {
    // The whole design constraint. Sinner has a title price and no match and
    // no curated market, so his semi-final cell has to be a hole. A grid that
    // chained his title probability into one would look better and be a model
    // output in the type reserved for a price.
    const grid = buildPlayoffGrid({ board, propMarkets: props, matches, draw: "mens-singles" });
    const sinner = grid.rows.find((r) => r.entityKey === "jannik-sinner");
    expect(sinner?.cells.SF).toMatchObject({ state: "unpriced", probability: null });
    expect(sinner?.cells.R32).toMatchObject({ state: "unpriced", probability: null });
    expect(formatGridCell(sinner!.cells.SF)).toBeNull();
  });

  it("counts its own coverage, so a sparse grid can say it is sparse", () => {
    const grid = buildPlayoffGrid({ board, propMarkets: props, matches, draw: "mens-singles" });
    // 2 match cells + 1 curated + 3 title = 6, out of 3 rows x 3 columns.
    expect(grid.pricedCells).toBe(6);
    expect(grid.totalCells).toBe(grid.rows.length * grid.columns.length);
    expect(grid.pricedCells).toBeLessThan(grid.totalCells);
  });

  it("puts the title column LAST and labels it as a different question", () => {
    const grid = buildPlayoffGrid({ board, propMarkets: props, matches, draw: "mens-singles" });
    const last = grid.columns[grid.columns.length - 1];
    expect(last.key).toBe("title");
    expect(last.kind).toBe("title");
    expect(last.longLabel).toBe("To win the title");
    // "Reach the final" and "win the title" are two markets and one is
    // strictly harder. A shared header would re-commit UX-P137's ruling 2.
    expect(grid.columns.filter((c) => c.kind === "reach").map((c) => c.longLabel)).not.toContain(
      "To win the title"
    );
  });

  it("offers no column for a round nothing prices", () => {
    const grid = buildPlayoffGrid({ board, propMarkets: [], matches: [], draw: "mens-singles" });
    expect(grid.columns.map((c) => c.key)).toEqual(["title"]);
  });

  it("refuses a curated market whose subject matches two players", () => {
    // "Does Williams reach the semifinals?" against a board holding both
    // Williams sisters. A cell attached to the wrong player renders as a
    // confident answer, which is worse than no cell at all.
    const ambiguous = boardOf([
      row({ entity_key: "v-williams", display_name: "Venus Williams" }),
      row({ entity_key: "s-williams", display_name: "Serena Williams", rank: 2 }),
    ]);
    const grid = buildPlayoffGrid({
      board: ambiguous,
      propMarkets: [advanceProp("williams-semifinals", "Does Williams reach the semifinals?", 0.4)],
      draw: "mens-singles",
    });
    expect(grid.columns.map((c) => c.key)).toEqual(["title"]);
  });

  it("caps the reach columns at the width that fits, and NEVER silently", () => {
    const many = [
      advanceProp("alcaraz-round-of-16", "Does Alcaraz reach the round of 16?", 0.8),
      advanceProp("alcaraz-quarterfinals", "Does Alcaraz reach the quarterfinals?", 0.7),
      advanceProp("alcaraz-semifinals", "Does Alcaraz reach the semifinals?", 0.575),
      advanceProp("alcaraz-final", "Does Alcaraz reach the final?", 0.4),
    ];
    const grid = buildPlayoffGrid({ board, propMarkets: many, matches, draw: "mens-singles" });
    expect(grid.columns.filter((c) => c.kind === "reach").length).toBe(GRID_MAX_REACH_COLUMNS);
    expect(grid.droppedColumns.length).toBeGreaterThan(0);
    // And the component SAYS so.
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} />);
    expect(html).toContain('data-testid="grid-dropped-columns"');
  });

  it("prefers the EARLIER rounds when it has to drop some", () => {
    const many = [
      advanceProp("alcaraz-round-of-16", "Does Alcaraz reach the round of 16?", 0.8),
      advanceProp("alcaraz-quarterfinals", "Does Alcaraz reach the quarterfinals?", 0.7),
      advanceProp("alcaraz-semifinals", "Does Alcaraz reach the semifinals?", 0.575),
      advanceProp("alcaraz-final", "Does Alcaraz reach the final?", 0.4),
    ];
    const grid = buildPlayoffGrid({ board, propMarkets: many, matches: [], draw: "mens-singles" });
    expect(grid.columns.map((c) => c.key)).toEqual(["R16", "QF", "SF", "title"]);
    expect(grid.droppedColumns.map((c) => c.key)).toEqual(["F"]);
  });
});

describe("PlayoffGrid rendering", () => {
  const rows = Array.from({ length: 12 }, (_, i) =>
    row({
      entity_key: `p-${i}`,
      display_name: `Player ${i}`,
      rank: i + 1,
      probability: 0.3 - i * 0.02,
    })
  );
  const grid = buildPlayoffGrid({
    board: boardOf(rows),
    propMarkets: [],
    matches: [],
    draw: "mens-singles",
  });

  it("renders the section under probability language, not gambling language", () => {
    // Ruling 3: "priced to get there" is a bet's payoff condition.
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} />);
    expect(html).toContain(GRID_SECTION_LABEL);
    expect(GRID_SECTION_LABEL).toBe("Chance of reaching");
    expect(html).not.toContain("Priced to get there");
    expect(html.toLowerCase()).not.toContain("odds");
  });

  it("collapses to five players with an expander that says how many there are", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} />);
    expect(count(html, 'data-testid="grid-row"')).toBe(5);
    expect(html).toContain("Show all 12");
  });

  it("expands to the whole field", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} initialExpanded />);
    expect(count(html, 'data-testid="grid-row"')).toBe(12);
  });

  it("prints a hole as a hole, with words a screen reader can hear", () => {
    const sparse = buildPlayoffGrid({
      board: boardOf([row(), row({ entity_key: "b", display_name: "B", rank: 2, probability: null })]),
      propMarkets: [advanceProp("alcaraz-semifinals", "Does Alcaraz reach the semifinals?", 0.5)],
      draw: "mens-singles",
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={sparse} />);
    expect(html).toContain('data-state="unpriced"');
    expect(html).toContain("Not priced");
    // Never a zero: a zero is a forecast that something is impossible.
    expect(html).not.toContain(">0%<");
  });

  it("states its own coverage rather than letting the holes speak for it", () => {
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} />);
    expect(html).toContain('data-testid="grid-coverage"');
    expect(html).toContain("Nothing here is calculated from anything else.");
  });

  it("says nothing to chart rather than rendering an empty frame", () => {
    const html = renderToStaticMarkup(
      <PlayoffGrid grid={buildPlayoffGrid({ board: null, draw: "mens-singles" })} />
    );
    expect(html).toContain('data-testid="grid-empty"');
    expect(html).not.toContain('data-testid="grid-row"');
  });

  it("carries the column's full sentence, not just its abbreviation", () => {
    // Ruling 2's standing rule: a number names its own question. "SF" does not.
    const withReach = buildPlayoffGrid({
      board: boardOf(rows),
      propMarkets: [advanceProp("player-0-semifinals", "Does Player reach the semifinals?", 0.5)],
      matches: buildMatchList({ slate: [slateMatch()] }),
      draw: "mens-singles",
    });
    const html = renderToStaticMarkup(<PlayoffGrid grid={withReach} />);
    expect(html).toContain("To win the title");
    expect(html).toContain("To reach the");
  });
});

describe("the grid renders a real draw's shape without exploding it", () => {
  it("never puts more than four numeric columns on a phone", () => {
    const rows = SYNTHETIC_MENS_DRAW.slice(0, 40).map((slot, i) =>
      row({
        entity_key: slot.entity_key,
        display_name: slot.display_name,
        seed: slot.seed,
        rank: i + 1,
        probability: slot.probability,
      })
    );
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, syntheticPartialResults(SYNTHETIC_MENS_DRAW, 20));
    const grid = buildPlayoffGrid({
      board: boardOf(rows),
      matches: buildMatchList({ rounds }),
      draw: "mens-singles",
    });
    expect(grid.columns.length).toBeLessThanOrEqual(GRID_MAX_REACH_COLUMNS + 1);
  });

  it("marks a round a player has already reached, and one they are out of", () => {
    const results = syntheticFirstRoundResults(SYNTHETIC_MENS_DRAW);
    const rounds = buildBracket(SYNTHETIC_MENS_DRAW, results);
    const winner = SYNTHETIC_MENS_DRAW[0];
    const loser = SYNTHETIC_MENS_DRAW[1];
    const rows = [winner, loser].map((slot, i) =>
      row({
        entity_key: slot.entity_key,
        display_name: slot.display_name,
        seed: slot.seed,
        rank: i + 1,
        probability: slot.probability,
      })
    );
    const grid = buildPlayoffGrid({
      board: boardOf(rows),
      matches: buildMatchList({ rounds }),
      draw: "mens-singles",
    });
    const w = grid.rows.find((r) => r.entityKey === winner.entity_key);
    const l = grid.rows.find((r) => r.entityKey === loser.entity_key);
    expect(w?.cells.R64.state).toBe("reached");
    expect(formatGridCell(w!.cells.R64)).toBe("✓");
    expect(l?.cells.R64.state).toBe("out");
    expect(l?.cells.title.state).toBe("out");
  });

  it("holds up on the women's draw too, which is a different field", () => {
    const rows = SYNTHETIC_WOMENS_DRAW.slice(0, 8).map((slot, i) =>
      row({
        entity_key: slot.entity_key,
        display_name: slot.display_name,
        rank: i + 1,
        probability: slot.probability,
      })
    );
    const grid = buildPlayoffGrid({ board: boardOf(rows, "womens-singles"), draw: "womens-singles" });
    const html = renderToStaticMarkup(<PlayoffGrid grid={grid} drawLabel="Women's Singles" />);
    expect(html).toContain("Women&#x27;s Singles");
    expect(html).toContain('data-entity="syn-w-1"');
  });

  it("a draw with register holes does not put a hole in the grid's rows", () => {
    // The grid's rows come from the BOARD, so a draw-slot hole cannot produce
    // a nameless row. Asserted because the old bracket rendered draw slots
    // directly and a hole WAS a row there.
    const holed = buildBracket(syntheticDrawWithHoles(SYNTHETIC_MENS_DRAW, [0, 3, 8]));
    const rows = SYNTHETIC_MENS_DRAW.slice(0, 6).map((slot, i) =>
      row({ entity_key: slot.entity_key, display_name: slot.display_name, rank: i + 1 })
    );
    const grid = buildPlayoffGrid({
      board: boardOf(rows),
      matches: buildMatchList({ rounds: holed }),
      draw: "mens-singles",
    });
    expect(grid.rows.every((r) => r.displayName.trim() !== "")).toBe(true);
    expect(grid.rows).toHaveLength(6);
  });
});
