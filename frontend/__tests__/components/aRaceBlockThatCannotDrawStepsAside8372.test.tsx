// #8372: the Presidents Cup page opened with "Race to the title" — Top 5 / Top 10
// / Full field tabs over an empty chart that said "history isn't available". Team
// match play has two teams and no ranks, and its Winner field carried no history.
// Two rules, each guarded in both directions:
//   1. the rank tabs are offered only where they change which lines are drawn;
//   2. the page mounts the race chart (and its "Race" nav pill) only when some
//      competitor has a drawable series — a stroke-play field with history keeps it.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";
import RaceToTitleChart, { raceRankTabs } from "../../components/event/RaceToTitleChart";
import { raceChartHasHistory } from "@/lib/eventConceptDisplay";

const HOUR = 3600 * 1000;

function withHistory(name: string, id: number, p: number): EventConceptCompetitor {
  const now = Date.now();
  return {
    name,
    probability: p,
    outcome_id: id,
    history: [
      { timestamp: new Date(now - 2 * HOUR).toISOString(), probability: p - 0.01 },
      { timestamp: new Date(now - 1 * HOUR).toISOString(), probability: p },
    ],
  };
}

// The production payload, 2026-09-24 08:20Z: /api/event/presidents-cup.
const PRESIDENTS_CUP: EventConceptCompetitor[] = [
  { name: "Team USA", probability: 0.835, history: [] } as EventConceptCompetitor,
  { name: "Team World", probability: 0.125, history: [] } as EventConceptCompetitor,
];

describe("raceRankTabs (#8372)", () => {
  test("a field of five or fewer offers no rank tab at all", () => {
    expect(raceRankTabs(0)).toEqual([]);
    expect(raceRankTabs(2)).toEqual([]);
    expect(raceRankTabs(5)).toEqual([]);
  });

  test("a field of six to ten offers Top 5 and Full field, never Top 10", () => {
    expect(raceRankTabs(6).map((t) => t.label)).toEqual(["Top 5", "Full field"]);
    expect(raceRankTabs(10).map((t) => t.label)).toEqual(["Top 5", "Full field"]);
  });

  test("a stroke-play field keeps all three tabs", () => {
    expect(raceRankTabs(11).map((t) => t.label)).toEqual(["Top 5", "Top 10", "Full field"]);
    expect(raceRankTabs(156).map((t) => t.label)).toEqual(["Top 5", "Top 10", "Full field"]);
  });

  test("a two-team race with history renders its lines and no rank tabs", () => {
    const html = renderToStaticMarkup(
      <RaceToTitleChart
        competitors={[withHistory("Team USA", 1, 0.8), withHistory("Team World", 2, 0.15)]}
        domain="golf"
      />,
    );
    expect(html).toContain("Race to the title");
    expect(html).not.toContain("Top 5");
    expect(html).not.toContain("Top 10");
    expect(html).not.toContain("Full field");
    expect(html).not.toContain("history isn&#x27;t available");
    // The range switch still works on two lines.
    expect(html).toContain(">1W<");
  });
});

describe("raceChartHasHistory (#8372)", () => {
  test("the Presidents Cup payload has nothing to draw", () => {
    expect(raceChartHasHistory(PRESIDENTS_CUP)).toBe(false);
  });

  test("one priced point is not a line", () => {
    const one = withHistory("Solo", 1, 0.5);
    one.history = one.history!.slice(0, 1);
    expect(raceChartHasHistory([one])).toBe(false);
  });

  test("a field with a drawable series keeps its chart, even if older than a week", () => {
    const old = withHistory("Alpha", 1, 0.4);
    old.history = old.history!.map((p, i) => ({
      ...p,
      timestamp: new Date(Date.now() - (60 - i) * 24 * HOUR).toISOString(),
    }));
    expect(raceChartHasHistory([old, ...PRESIDENTS_CUP])).toBe(true);
  });
});
