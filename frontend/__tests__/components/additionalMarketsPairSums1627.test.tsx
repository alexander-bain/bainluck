/**
 * #1627 — a two-row card in Additional Markets is ONE question, so its two
 * numbers are rounded together and total 100.
 *
 * Each row used to round on its own. A venue quotes a complement pair on a
 * half-cent grid, so both halves land on `.5` and both round up. Seen at 390px
 * on production 2026-10-01 07:2xZ, both pregame:
 *
 *   /events/15322407 Phillies @ Braves (Wild Card decider)
 *     "Will there be a run scored in the first inning?"  No 53% · Yes 48%
 *   /events/14780550 Steelers @ Browns (TNF)
 *     "Steelers vs. Browns: Safety?"                      No 94% · Yes 7%
 *
 * The rows below are those events' `/game-markets` → `other`, verbatim from
 * production, less `contributor_outcome_ids` (not read by the section).
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import SpecialEventMarkets from "@/components/SpecialEventMarkets";
import type { GameMarketsResponse } from "@/lib/api";

type Rows = GameMarketsResponse["other"];

const FIRST_INNING_RUN: Rows = [
  { market_name: "Will there be a run scored in the first inning?: Philadelphia Phillies vs. Atlanta Braves", outcome_name: "No", observed_at: "2026-10-01T07:14:34.200576+00:00", probability: 0.525, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 63546726 },
  { market_name: "Will there be a run scored in the first inning?: Philadelphia Phillies vs. Atlanta Braves", outcome_name: "Yes", observed_at: "2026-10-01T07:14:34.200576+00:00", probability: 0.475, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 63546726 },
  // The hero's own market rides the same array; the section drops it.
  { market_name: "Philadelphia Phillies vs. Atlanta Braves", outcome_name: "Atlanta Braves", observed_at: "2026-10-01T07:14:34.200576+00:00", probability: 0.505, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 63069860 },
  { market_name: "Philadelphia Phillies vs. Atlanta Braves", outcome_name: "Philadelphia Phillies", observed_at: "2026-10-01T07:14:34.200576+00:00", probability: 0.495, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 63069860 },
];

const SAFETY: Rows = [
  { market_name: "Steelers vs. Browns: Safety?", outcome_name: "No", observed_at: "2026-10-01T00:21:10.838861+00:00", probability: 0.935, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 63339287 },
  { market_name: "Steelers vs. Browns: Safety?", outcome_name: "Yes", observed_at: "2026-10-01T00:21:10.838861+00:00", probability: 0.065, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 63339287 },
];

function render(other: Rows, home = "Atlanta Braves", away = "Philadelphia Phillies"): string {
  const data = { other, home_team: home, away_team: away } as GameMarketsResponse;
  return renderToStaticMarkup(<SpecialEventMarkets data={data} eventStatus="scheduled" />);
}

/** Every printed percent, in page order. */
function percents(html: string): number[] {
  return Array.from(html.matchAll(/>(\d{1,3})%</g), (m) => Number(m[1]));
}

describe("#1627 a two-row card totals 100", () => {
  it("Phillies @ Braves first-inning run prints 53 / 47, not 53 / 48", () => {
    const html = render(FIRST_INNING_RUN);
    expect(html).toMatch(/run scored in the first inning/);
    expect(percents(html)).toEqual([53, 47]);
  });

  it("Steelers @ Browns safety prints 94 / 6, not 94 / 7", () => {
    const html = render(SAFETY, "Cleveland Browns", "Pittsburgh Steelers");
    expect(html).toMatch(/Safety\?/);
    expect(percents(html)).toEqual([94, 6]);
  });
});

describe("#1627 controls — cards the pair rule must not touch", () => {
  it("a two-row pair outside the complement band keeps its own two roundings", () => {
    const rows: Rows = [
      { market_name: "Steelers vs. Browns: Overtime?", outcome_name: "No", probability: 0.57, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 7 },
      { market_name: "Steelers vs. Browns: Overtime?", outcome_name: "Yes", probability: 0.4, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 7 },
    ];
    expect(percents(render(rows, "Cleveland Browns", "Pittsburgh Steelers"))).toEqual([57, 40]);
  });

  it("a three-row card is rounded row by row, as before", () => {
    const rows: Rows = [
      { market_name: "Pittsburgh vs Cleveland: Race to 10 Points", outcome_name: "Pittsburgh", probability: 0.525, source: "kalshi", is_winner: null, resolution_source: null, _market_id: 9 },
      { market_name: "Pittsburgh vs Cleveland: Race to 10 Points", outcome_name: "Cleveland", probability: 0.435, source: "kalshi", is_winner: null, resolution_source: null, _market_id: 9 },
      { market_name: "Pittsburgh vs Cleveland: Race to 10 Points", outcome_name: "Neither team", probability: 0.045, source: "kalshi", is_winner: null, resolution_source: null, _market_id: 9 },
    ];
    expect(percents(render(rows, "Cleveland Browns", "Pittsburgh Steelers"))).toEqual([53, 44, 5]);
  });

  it("a pair with one unpriced row prints the priced row on its own rounding", () => {
    const rows: Rows = [
      { market_name: "Steelers vs. Browns: Safety?", outcome_name: "No", probability: 0.935, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 8 },
      { market_name: "Steelers vs. Browns: Safety?", outcome_name: "Yes", probability: null, source: "polymarket", is_winner: null, resolution_source: null, _market_id: 8 },
    ];
    expect(percents(render(rows, "Cleveland Browns", "Pittsburgh Steelers"))).toEqual([94]);
  });
});
