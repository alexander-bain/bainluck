// UX-P040 (#1638) — a finished game stops printing MISS on props nobody graded.
//
// Rendered guard, both directions per gotcha #43:
//   * the never-graded game shows the honest fallback and ZERO verdicts, and
//   * a genuinely graded prop still renders HIT/MISS exactly as before.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import PlayerPropsDashboard from "../../components/PlayerPropsDashboard";
import type { GameMarketsResponse } from "../../lib/api";

const MARKET = "Tampa Bay Rays vs. Seattle Mariners - Player Props";

/**
 * Real production rows, event 15191121 (final, 4-1), 2026-08-09. Every row
 * carried `actual: null, hit: null, is_winner: false, resolution_source: null`
 * — never graded. All 25 rendered a red MISS before this fix.
 */
const NEVER_GRADED_ROWS = [
  { outcome_name: "Victor Mesa Jr.: Home Runs O/U 0.5", threshold: 0.5, over_probability: 0.705 },
  { outcome_name: "Victor Mesa Jr.: Home Runs O/U 1.5", threshold: 1.5, over_probability: 0.505 },
  { outcome_name: "Cole Young: Home Runs O/U 0.5", threshold: 0.5, over_probability: 0.505 },
  { outcome_name: "Cedric Mullins: Home Runs O/U 0.5", threshold: 0.5, over_probability: 0.505 },
].map((r) => ({
  market_name: MARKET,
  source: "polymarket",
  movement: null,
  actual: null,
  hit: null,
  is_winner: false,
  resolution_source: null,
  ...r,
}));

function payload(player_props: Array<Record<string, unknown>>): GameMarketsResponse {
  return { player_props, other: [] } as unknown as GameMarketsResponse;
}

function renderSettled(rows: Array<Record<string, unknown>>, boxScore: unknown = null) {
  return renderToStaticMarkup(
    <PlayerPropsDashboard
      data={payload(rows)}
      eventStatus="completed"
      homeTeam="Tampa Bay Rays"
      awayTeam="Seattle Mariners"
      boxScore={boxScore as never}
    />,
  );
}

describe("settled props with no published grade", () => {
  const html = renderSettled(NEVER_GRADED_ROWS);

  it("never states a verdict the backend did not publish", () => {
    expect(html).not.toContain("MISS");
    expect(html).not.toContain("HIT");
  });

  it("says so, using the honest branch that already existed", () => {
    expect(html).toContain("grading unavailable");
  });

  it("does not advertise the section as graded", () => {
    expect(html).toContain("per-player grading unavailable for this game");
    expect(html).not.toContain("Final &middot; graded results");
    expect(html).not.toContain("Final · graded results");
  });

  it("still shows the props — this suppresses the verdict, not the section", () => {
    expect(html).toContain("Player Props");
    // The line is still stated; only the invented verdict is gone.
    expect(html).toContain("0.5+");
  });

  /**
   * `box_score_data.players` is a DICT keyed by player name, not an array
   * (gotcha #37). `.length` on it is undefined, so `hasBoxScore` is false and
   * the client-side box-score grading path never runs. That path is
   * adjudication (ruling 003) and must stay off; this asserts the dict shape
   * does not accidentally switch it on.
   */
  it("does not grade itself off a box score", () => {
    const dictBoxScore = { players: { "Cole Young": { "home runs": 0.0 } } };
    const withBox = renderSettled(NEVER_GRADED_ROWS, dictBoxScore);
    expect(withBox).not.toContain("MISS");
    expect(withBox).toContain("grading unavailable");
  });
});

// The other direction (gotcha #43): the fix must not swallow a real grade.
describe("settled props the backend DID grade", () => {
  const graded = NEVER_GRADED_ROWS.map((r, i) =>
    i === 0
      ? { ...r, actual: 1, hit: true, is_winner: true, resolution_source: "polymarket_api" }
      : r,
  );
  const html = renderSettled(graded);

  it("still renders the verdict", () => {
    expect(html).toContain("HIT");
  });

  it("flips the section subtitle back to graded", () => {
    expect(html).toContain("graded results");
  });

  it("shows the published actual alongside the verdict", () => {
    expect(html).toContain("of 0.5");
  });

  /**
   * UPDATED by #1639, in the same cycle that wrote it.
   *
   * When this was written these four rows collapsed into ONE stat group, because
   * `parsePlayerName` read the player from `market_name` — so evidence on any
   * rung graded everything. #1639 fixed that collapse, and each player is now
   * its own card. So the graded player shows its verdict and the ungraded
   * players stay honest, side by side — which is what this test wanted in the
   * first place and could not have while the collapse existed.
   */
  it("grades the graded player and leaves the ungraded ones honest", () => {
    expect(html).toContain("HIT");
    expect(html).toContain("grading unavailable");
  });
});

describe("a graded MISS is still a MISS", () => {
  it("renders MISS when the backend published one", () => {
    const rows = NEVER_GRADED_ROWS.map((r, i) =>
      i === 0
        ? { ...r, actual: 0, hit: false, is_winner: false, resolution_source: "polymarket_api" }
        : r,
    );
    expect(renderSettled(rows)).toContain("MISS");
  });
});

// ===========================================================================
// UX-P044 (#1642) — the SECOND shape of the same failure.
//
// #1638 stopped a bare `is_winner` from becoming a verdict, but left a route
// around it: a `resolution_source` was treated as licence to believe the
// defaulted `false`. Measured on 19 settled production events / 358 rendered
// cards, that route produced **70 red MISSes and 3 HITs** the backend never
// typed.
//
// It is a box-score miss, mechanically: `_grade_settled_prop` passes
// `is_winner` / `resolution_source` straight through from the outcome row while
// `actual` / `hit` come only from the box score.
// ===========================================================================
describe("a generic resolution source is not a verdict (#1642 P1)", () => {
  /** The exact wire shape behind the 70: 115 of 561 sampled rows looked like this. */
  const SOURCED_UNGRADED = NEVER_GRADED_ROWS.map((r) => ({
    ...r,
    resolution_source: "api_settlement",
    is_winner: false,
  }));

  it("does not render MISS for a source plus a defaulted false", () => {
    const html = renderSettled(SOURCED_UNGRADED);
    expect(html).not.toContain("MISS");
    expect(html).toContain("grading unavailable");
  });

  it("does not render HIT from a source plus is_winner: true either", () => {
    const html = renderSettled(
      SOURCED_UNGRADED.map((r) => ({ ...r, is_winner: true })),
    );
    expect(html).not.toContain("HIT");
    expect(html).toContain("grading unavailable");
  });

  it("a void settlement is withheld, not called a loss", () => {
    const html = renderSettled(
      SOURCED_UNGRADED.map((r) => ({ ...r, resolution_source: "void" })),
    );
    expect(html).not.toContain("MISS");
  });

  // Both directions (gotcha #43). This is the majority of the real cohort —
  // 367 of 561 sampled rows carried a box-score `hit` and must be unaffected.
  it("a source ALONGSIDE a real hit still grades", () => {
    const html = renderSettled(
      NEVER_GRADED_ROWS.map((r, i) =>
        i === 0
          ? { ...r, actual: 1, hit: true, is_winner: true, resolution_source: "api_settlement" }
          : r,
      ),
    );
    expect(html).toContain("HIT");
  });
});

describe("a ladder whose rungs disagree states no group verdict (#1642 P2)", () => {
  // A real player with exactly 1 hit: HIT at 0.5, MISS at 1.5. Seven of the 358
  // sampled cards were this, and each rendered whichever rung sorted first.
  const CONFLICT = [
    {
      market_name: MARKET, source: "polymarket", movement: null,
      outcome_name: "Victor Mesa Jr.: Hits O/U 0.5", threshold: 0.5, over_probability: 0.8,
      actual: 1, hit: true, is_winner: true, resolution_source: "box_score",
    },
    {
      market_name: MARKET, source: "polymarket", movement: null,
      outcome_name: "Victor Mesa Jr.: Hits O/U 1.5", threshold: 1.5, over_probability: 0.3,
      actual: 1, hit: false, is_winner: false, resolution_source: "box_score",
    },
  ];

  it("withholds rather than picking a rung", () => {
    const html = renderSettled(CONFLICT);
    expect(html).not.toContain("HIT");
    expect(html).not.toContain("MISS");
    expect(html).toContain("grading unavailable");
  });

  it("does not depend on input order", () => {
    expect(renderSettled([...CONFLICT].reverse())).toEqual(renderSettled(CONFLICT));
  });

  it("agreeing rungs are not a conflict", () => {
    const agree = CONFLICT.map((r) => ({ ...r, hit: true }));
    expect(renderSettled(agree)).toContain("HIT");
  });
});

describe("a matchup bucket never borrows another row's grade (#1642 P1b)", () => {
  // `market_name` has no colon and no statistic matches, and the outcome label
  // is not `Player: Statistic O/U N` — so `parsePlayerName` falls back to the
  // whole market name and every such row lands in ONE bucket. Measured 0 times
  // on today's cohort (#1639's outcome-label parse catches the MLB rows); this
  // is the guard, not a reported frequency.
  const UNIDENTIFIED = ["Yes", "No", "NRFI"].map((outcome_name, i) => ({
    market_name: MARKET,
    source: "polymarket",
    movement: null,
    outcome_name,
    threshold: 0.5 + i,
    over_probability: 0.5,
    actual: i === 0 ? 4 : null,
    hit: i === 0 ? true : null,
    is_winner: i === 0,
    resolution_source: i === 0 ? "box_score" : null,
  }));

  it("refuses the group verdict rather than attaching one row's grade to all", () => {
    const html = renderSettled(UNIDENTIFIED);
    expect(html).not.toContain("HIT");
    expect(html).toContain("grading unavailable");
  });

  it("does not leak the borrowed actual either", () => {
    expect(renderSettled(UNIDENTIFIED)).not.toContain("of 0.5</div>4");
  });

  // Both directions: a row that DOES name a player keeps grading normally.
  it("an identified player in the same payload is unaffected", () => {
    const mixed = [
      ...UNIDENTIFIED,
      {
        market_name: MARKET, source: "polymarket", movement: null,
        outcome_name: "Cole Young: Hits O/U 0.5", threshold: 0.5, over_probability: 0.7,
        actual: 2, hit: true, is_winner: true, resolution_source: "box_score",
      },
    ];
    const html = renderSettled(mixed);
    expect(html).toContain("HIT");           // the identified player grades
    expect(html).toContain("grading unavailable"); // the matchup bucket does not
  });
});
