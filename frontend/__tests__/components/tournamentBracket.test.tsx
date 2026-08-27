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
 * and onto the Tournament tab; those assertions live in
 * `tournamentMatches.test.tsx`.
 *
 * UX-P139 moved the GRID out too. The grid is built server-side now — the
 * amendment makes cell provenance a correctness property ("the grid reads only
 * the register"), so its logic and its two evals are asserted in
 * `backend/tests/test_tournament_grid.py`, and its rendering in
 * `playoffGrid.test.tsx`. What is left here is the FOLD: the draw-to-rounds
 * arithmetic and the rule that nothing advances without a declared result.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { bracketProgress, buildBracket, roundIsUnreached, ROUND_NAMES } from "@/lib/bracket";
import type { TournamentBoardData, TournamentRow } from "@/lib/tournament";
import {
  SYNTHETIC_MENS_DRAW,
  SYNTHETIC_WOMENS_DRAW,
  syntheticDrawWithHoles,
  syntheticFirstRoundResults,
  syntheticPartialResults,
} from "../fixtures/syntheticDraw";

export { };

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
