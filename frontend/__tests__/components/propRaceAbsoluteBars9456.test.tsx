/**
 * #9456 — A TEAM PAGE'S PROP-RACE BAR IS THE ROW'S OWN PROBABILITY.
 *
 * ═══ WHAT WAS ON PRODUCTION ═══
 *
 * Photographed at 390px on 2026-09-28 (search "bears" → Chicago Bears):
 *
 *   Offensive Player Of The Year   Caleb Williams  0.015  "2%"  full bar
 *                                  D'Andre Swift   0.01   "1%"  half bar
 *
 * and the same component on the Eagles page, from its served payload:
 *
 *   MVP                            leader 0.035           full bar
 *   Defensive Player Of The Year   leader 0.032           full bar
 *   Next Team                      leader 0.095           full bar
 *   Season Receiving Yards         leader 0.58            full bar
 *
 * `TeamPropFamilies` filled each bar against the card's leader. A team page
 * shows only that team's slice of an award field, so the leader is rarely the
 * favourite, and the threshold ladders are separate yes/no questions at
 * different lines. A 2% award chance drawn as a full bar reads as a sure thing.
 *
 * ═══ BOTH DIRECTIONS (gotcha #43) ═══
 *
 * "The leader is not full width" is passed by a component that draws no bar.
 * So the controls: a settled `✓ Won` row (served 1.0) is still full, a
 * genuine 58% leader draws 58, a null draws nothing, and the rows stay in
 * bar-length order (the ranking the relative bar existed to show).
 *
 *   npx jest --testPathPatterns=propRaceAbsoluteBars9456
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { TeamPropFamilies } from "../../components/TeamPropFamilies";
import type { PropFamily } from "../../lib/api";

jest.mock("next/link", () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

// The avatar is not under test, and must not contribute a `width:` of its own.
jest.mock("../../components/EntityImage", () => ({
  __esModule: true,
  default: () => null,
}));

type Row = PropFamily["rows"][number];

function familyWith(label: string, rows: Array<Partial<Row>>): PropFamily {
  return {
    family_key: label.toLowerCase(),
    label,
    entity_count: rows.length,
    sources: ["kalshi", "polymarket"],
    rows: rows.map((r, i) => ({
      entity: `Entity ${i}`,
      market_id: 9456000 + i,
      outcome_id: 94560000 + i,
      probability: 0.5,
      source: "kalshi",
      sources: ["kalshi"],
      cross_source: {},
      group_id: null,
      status: "open",
      settled: false,
      result: null,
      top_outcome: null,
      ...r,
    })),
  };
}

/** Every bar's width, in render order, read from the served markup. */
function barWidths(rows: Array<Partial<Row>>, label = "Offensive Player Of The Year"): number[] {
  const html = renderToStaticMarkup(
    <TeamPropFamilies families={[familyWith(label, rows)]} teamColor="#0B162A" />,
  );
  return [...html.matchAll(/width:(\d+)%/g)].map((m) => Number(m[1]));
}

describe("#9456 the bar is drawn against 100%, not against the card's leader", () => {
  test("Bears OPOY: Caleb Williams' 2% no longer draws a full bar", () => {
    const [williams, swift] = barWidths([
      { entity: "Caleb Williams", probability: 0.015 },
      { entity: "D'Andre Swift", probability: 0.01 },
    ]);
    expect(williams).toBe(2);
    expect(swift).toBe(2); // the 2% visibility floor, not 1% of a track
  });

  test("Eagles MVP: a 3.5% leader draws 4, not 100", () => {
    expect(
      barWidths(
        [
          { entity: "Jalen Hurts", probability: 0.035 },
          { entity: "Saquon Barkley", probability: 0.01 },
          { entity: "A. J. Brown", probability: 0.01 },
        ],
        "MVP",
      ),
    ).toEqual([4, 2, 2]);
  });

  test("threshold ladder: each row draws its own chance", () => {
    expect(
      barWidths(
        [
          { entity: "Rome Odunze", probability: 0.47, top_outcome: "800+ receiving yards" },
          { entity: "Luther Burden III", probability: 0.44, top_outcome: "825+ receiving yards" },
          { entity: "Colston Loveland", probability: 0.29, top_outcome: "800+ receiving yards" },
        ],
        "Season Receiving Yards",
      ),
    ).toEqual([47, 44, 29]);
  });
});

describe("#9456 controls", () => {
  test("a settled ✓ Won row (served 1.0) is still a full bar; its losers keep the floor", () => {
    expect(
      barWidths([
        { entity: "Winner", probability: 1.0, settled: true, result: "won" },
        { entity: "Loser", probability: 0.0, settled: true, result: "lost" },
      ]),
    ).toEqual([100, 2]);
  });

  test("a null price draws no bar", () => {
    expect(
      barWidths([
        { entity: "Priced", probability: 0.3 },
        { entity: "Unpriced", probability: null },
      ]),
    ).toEqual([30, 0]);
  });

  test("sorted rows still read in bar-length order", () => {
    const widths = barWidths([
      { probability: 0.58 },
      { probability: 0.535 },
      { probability: 0.495 },
      { probability: 0.2 },
    ]);
    expect(widths).toEqual([58, 54, 50, 20]);
    expect([...widths].sort((a, b) => b - a)).toEqual(widths);
  });
});
