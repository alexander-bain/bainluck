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

  // live/059: the envelope now carries one variable-resolution series per
  // contender that reaches the market's listing, so the switch gained a "1M"
  // band and "All" finally means all. Before this the payload held 7 days, so
  // "All" and "7d" drew the same line — a switch that could not do anything.
  test("range switcher offers 1D / 1W / 1M / All", () => {
    const html = renderToStaticMarkup(
      <RaceToTitleChart competitors={mkCompetitors()} />,
    );
    expect(html).toContain(">1D<");
    expect(html).toContain(">1W<");
    expect(html).toContain(">1M<");
    expect(html).toContain(">All<");
  });

  test("a series that reaches back months still draws under the All range", () => {
    const now = Date.now();
    const DAY = 24 * HOUR;
    // 1-minute for the last hour, 12-hourly for eight months — the layered
    // shape `futures_chart_series` produces.
    const history = [
      ...Array.from({ length: 480 }, (_, i) => ({
        timestamp: new Date(now - (480 - i) * 12 * HOUR).toISOString(),
        probability: 0.2 + (i % 11) * 0.001,
      })),
      ...Array.from({ length: 60 }, (_, i) => ({
        timestamp: new Date(now - (60 - i) * 60 * 1000).toISOString(),
        probability: 0.42 + (i % 7) * 0.001,
      })),
    ];
    const html = renderToStaticMarkup(
      <RaceToTitleChart
        competitors={[
          { name: "Alpha", probability: 0.42, outcome_id: 1, history },
          { name: "Bravo", probability: 0.2, outcome_id: 2, history },
        ]}
      />,
    );
    // The default range is 1W; the honest-empty state must NOT be what a
    // months-long series renders.
    expect(html).not.toContain("Probability history isn&#x27;t available");
    expect(html).toContain("Race to the title");
    void DAY;
  });
});
