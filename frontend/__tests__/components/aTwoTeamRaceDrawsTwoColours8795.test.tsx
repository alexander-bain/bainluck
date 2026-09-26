// #8795: the Presidents Cup "Race to the title" drew Team International and Team
// USA in golf's two leader greens (#006747 / #2d8659); the lines cross at R3, so a
// reader could not tell which team was which. A two-sided golf race takes the
// default palette's blue and red; a stroke-play field keeps its green theme.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";
import RaceToTitleChart from "../../components/event/RaceToTitleChart";
import { SERIES_COLORS, SERIES_COLORS_GREEN } from "@/lib/seriesColors";

const HOUR = 3600 * 1000;

function withHistory(name: string, id: number, from: number, to: number): EventConceptCompetitor {
  const now = Date.now();
  return {
    name,
    probability: to,
    outcome_id: id,
    history: [
      { timestamp: new Date(now - 2 * HOUR).toISOString(), probability: from },
      { timestamp: new Date(now - 1 * HOUR).toISOString(), probability: to },
    ],
  };
}

/** The legend dot colours, in order, as rendered. */
function legendColours(html: string): string[] {
  const legend = html.split('aria-label="Chart legend"')[1] ?? "";
  return [...legend.matchAll(/background-color:\s*(#[0-9a-fA-F]{6})/g)].map((m) =>
    m[1].toLowerCase(),
  );
}

const lower = (xs: readonly string[]) => xs.map((x) => x.toLowerCase());

describe("a two-team golf race draws two distinguishable colours (#8795)", () => {
  // The production shape: International falls ~80% → 43%, USA rises ~10% → 50%.
  const presidentsCup = [
    withHistory("Team International", 1, 0.8, 0.43),
    withHistory("Team USA", 2, 0.1, 0.5),
  ];

  test("the two teams take the default palette's blue and red, never the greens", () => {
    const colours = legendColours(
      renderToStaticMarkup(<RaceToTitleChart competitors={presidentsCup} domain="golf" />),
    );
    expect(colours).toHaveLength(2);
    expect(new Set(colours)).toEqual(new Set(lower(SERIES_COLORS.slice(0, 2))));
    for (const green of lower(SERIES_COLORS_GREEN.slice(0, 2))) {
      expect(colours).not.toContain(green);
    }
  });

  test("a stroke-play field keeps golf's green leader theme", () => {
    const field = [0.3, 0.2, 0.15, 0.1, 0.08, 0.05].map((p, i) =>
      withHistory(`Golfer ${i + 1}`, i + 1, p, p),
    );
    const colours = legendColours(
      renderToStaticMarkup(<RaceToTitleChart competitors={field} domain="golf" />),
    );
    expect(colours.length).toBeGreaterThan(0);
    expect(colours[0]).toBe(SERIES_COLORS_GREEN[0].toLowerCase());
  });
});
