// #9391: the Alfred Dunhill Links page's "Race to the title · Top 5" listed
// Fleetwood, Fitzpatrick, Schott, Gavins and Ko while the Winner table below it
// read Aberg, Fleetwood, Fitzpatrick, Gerard, Hovland. The chart ranked by each
// golfer's last HISTORY point. Aberg, Gerard and Hovland served no history (-1,
// dropped out), and Ko, whose current price is 0, had one stale 4.9% point.
// The specimen below is that served shape (9/28 14:33Z), trimmed.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import type { EventConceptCompetitor } from "@/lib/types";
import RaceToTitleChart, { raceTopSelection } from "../../components/event/RaceToTitleChart";
import { competitorsToOutcomeHistory } from "@/lib/eventConceptDisplay";

const HOUR = 3600 * 1000;

function hist(...ps: number[]) {
  const now = Date.now();
  return ps.map((p, i) => ({
    timestamp: new Date(now - (ps.length - i) * HOUR).toISOString(),
    probability: p,
  }));
}

function dunhill(): EventConceptCompetitor[] {
  return [
    { name: "Ludvig Aberg", probability: 0.118 },
    { name: "Tommy Fleetwood", probability: 0.101, outcome_id: 2, history: hist(0.09, 0.1, 0.101) },
    { name: "Matt Fitzpatrick", probability: 0.086, outcome_id: 3, history: hist(0.08, 0.085, 0.086) },
    { name: "Ryan Gerard", probability: 0.072 },
    { name: "Viktor Hovland", probability: 0.071 },
    { name: "Jeong Weon Ko", probability: 0, outcome_id: 6, history: hist(0.05, 0.049) },
    { name: "Daniel Gavins", probability: 0.004, outcome_id: 7, history: hist(0.02, 0.012) },
    { name: "Freddy Schott", probability: 0.007, outcome_id: 8, history: hist(0.007, 0.007) },
    ...Array.from({ length: 8 }, (_, i) => ({
      name: `Field ${i}`,
      probability: 0.002,
      outcome_id: 100 + i,
      history: hist(0.002, 0.002),
    })),
  ];
}

describe("#9391 race chart Top N is the current top N", () => {
  test("Top 5 draws only the priced top five that have a line", () => {
    const cs = dunhill();
    const sel = raceTopSelection(cs, competitorsToOutcomeHistory(cs, 168), 5);
    expect([...sel].sort((a, b) => a - b)).toEqual([2, 3]);
  });

  test("an unpriced golfer with a stale history point is never auto-picked", () => {
    const cs = dunhill();
    const sel = raceTopSelection(cs, competitorsToOutcomeHistory(cs, 168), 10);
    expect(sel.has(6)).toBe(false);
    expect(sel.has(8)).toBe(true); // priced 0.7%: inside a Top 10 on price
  });

  test("Full field still draws every series, unpriced ones included", () => {
    const cs = dunhill();
    const outcomes = competitorsToOutcomeHistory(cs, 168);
    expect(raceTopSelection(cs, outcomes, 0).size).toBe(outcomes.length);
  });

  test("no current prices at all falls back to the history ranking", () => {
    const cs = dunhill().map((c) => ({ ...c, probability: null }));
    const sel = raceTopSelection(cs, competitorsToOutcomeHistory(cs, 168), 2);
    expect([...sel].sort((a, b) => a - b)).toEqual([2, 3]);
  });

  test("the rendered legend names the contenders, not the field", () => {
    const html = renderToStaticMarkup(<RaceToTitleChart competitors={dunhill()} domain="golf" />);
    expect(html).toContain("Tommy Fleetwood");
    expect(html).toContain("Matt Fitzpatrick");
    expect(html).not.toContain("Jeong Weon Ko");
    expect(html).not.toContain("Freddy Schott");
    expect(html).not.toContain("Daniel Gavins");
  });
});
