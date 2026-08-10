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
   * These four rows collapse into ONE stat group, because `parsePlayerName`
   * reads the player from `market_name` — and MLB's market_name is the matchup,
   * with the player sitting in `outcome_name`. Evidence on any rung therefore
   * grades the group, which is correct for a ladder's rungs. The collapse
   * itself is a separate defect, filed apart from this one; asserted here so
   * the grouping is documented rather than assumed.
   */
  it("grades the group from evidence on one rung", () => {
    expect(html).not.toContain("grading unavailable");
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
