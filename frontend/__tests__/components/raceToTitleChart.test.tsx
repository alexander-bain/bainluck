// L2-138: the "Race to the title" chart keeps a top-5 contender default but must
// expose a full-field toggle via the existing picker (no spaghetti by default,
// nothing removed). This guards that the picker offers Top 5 / Top 10 / Full
// field — the capability Alex's corrected ruling requires.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";
import RaceToTitleChart from "../../components/event/RaceToTitleChart";

const HOUR = 3600 * 1000;

// A few contenders with recent history so the chart branch renders.
function mkCompetitors(): EventConceptCompetitor[] {
  const now = Date.now();
  const hist = (a: number, b: number, c: number) => [
    { timestamp: new Date(now - 3 * HOUR).toISOString(), probability: a },
    { timestamp: new Date(now - 2 * HOUR).toISOString(), probability: b },
    { timestamp: new Date(now - 1 * HOUR).toISOString(), probability: c },
  ];
  return [
    { name: "Alpha", probability: 0.4, outcome_id: 1, history: hist(0.2, 0.3, 0.4) },
    { name: "Bravo", probability: 0.3, outcome_id: 2, history: hist(0.3, 0.3, 0.3) },
    { name: "Charlie", probability: 0.2, outcome_id: 3, history: hist(0.25, 0.22, 0.2) },
  ];
}

describe("RaceToTitleChart picker (L2-138)", () => {
  test("offers Top 5 / Top 10 / Full field", () => {
    const html = renderToStaticMarkup(
      <RaceToTitleChart competitors={mkCompetitors()} />,
    );
    expect(html).toContain("Race to the title");
    expect(html).toContain("Top 5");
    expect(html).toContain("Top 10");
    expect(html).toContain("Full field");
  });

  test("range switcher present (24h / 7d / All)", () => {
    const html = renderToStaticMarkup(
      <RaceToTitleChart competitors={mkCompetitors()} />,
    );
    expect(html).toContain("24h");
    expect(html).toContain("7d");
    expect(html).toContain(">All<");
  });
});
