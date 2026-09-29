// #9576 + #9574 — a futures ladder page reads the same as its own rows.
//
// #9576: `/futures/59699693` (Hurricane Polo), 2026-09-29 0817Z — the hero read
// `100%` over a still-trading 0.995 while its All Outcomes row and the /weather
// card both read `>99%`. The hero printed the bare row integer and skipped the
// boundary rule every row runs.
//
// #9574: the same page listed Cat 1, Cat 2, Cat 5, Cat 3, Cat 4 under
// Probability ↓ (all five at 0.995), and `/futures/63153672` (Brent) printed
// `Above $103` above `Above $102.50` at a shared 6%. Ties fell through to serve
// order. The specimens below are the served payloads, in served order.
import { readFileSync } from "fs";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { FuturesHero } from "../../components/FuturesHero";
import { sortFuturesOutcomes } from "../../lib/futuresDetailDisplay";
import { buildOutcomeLadderRungs, ladderInclusionRanks } from "../../lib/futuresLadder";

const CURVE = [0.97, 0.98, 0.99, 0.995];

function heroText(html: string): string {
  const marker = html.match(/data-testid="hero-percent-marker"[^>]*>([^<]*)</)?.[1] ?? "";
  const digits = html.match(/data-testid="hero-percent"[^>]*>([^<]*)</)?.[1] ?? "";
  return `${marker}${digits}`.replace(/&gt;/g, ">").replace(/&lt;/g, "<");
}

describe("#9576 — the futures hero clamps like its rows", () => {
  test.each([
    ["plain numeral", undefined],
    ["ambient numeral", CURVE],
  ])("%s: a still-trading 0.995 reads >99, never 100", (_label, points) => {
    const html = renderToStaticMarkup(
      <FuturesHero
        name="Hurricane Polo max category"
        probability={0.995}
        rendered={100}
        outcomeName="Category 5 or above"
        sparklinePoints={points}
      />,
    );
    expect(heroText(html)).toBe(">99");
  });

  test("a possible 0.004 reads <1, never 0", () => {
    const html = renderToStaticMarkup(
      <FuturesHero name="M" probability={0.004} outcomeName="Yes" />,
    );
    expect(heroText(html)).toBe("<1");
  });

  test("an ordinary number carries no marker (the rule is not a blanket prefix)", () => {
    const html = renderToStaticMarkup(
      <FuturesHero name="M" probability={0.575} outcomeName="Yes" />,
    );
    expect(html).not.toContain("hero-percent-marker");
    expect(heroText(html)).toBe("58");
  });

  test("the upset note on a won market never prints 0% over a real price", () => {
    const html = renderToStaticMarkup(
      <FuturesHero name="M" probability={0.003} outcomeName="Longshot" resolved resolvedWon />,
    );
    expect(html).toContain("Markets gave this just &lt;1%.");
  });
});

const HURRICANE = [
  { id: 226005312, name: "Category 1 or above", probability: 0.995 },
  { id: 226005313, name: "Category 2 or above", probability: 0.995 },
  { id: 226005316, name: "Category 5 or above", probability: 0.995 },
  { id: 226005314, name: "Category 3 or above", probability: 0.995 },
  { id: 226005315, name: "Category 4 or above", probability: 0.995 },
];

// Brent tail, served order, with the tie the issue photographed (6%).
const BRENT = [
  { id: 238114129, name: "Above $101", probability: 0.115 },
  { id: 238114133, name: "Above $103", probability: 0.06 },
  { id: 238114132, name: "Above $102.50", probability: 0.06 },
  { id: 238114136, name: "Above $104.50", probability: 0.03 },
  { id: 238114135, name: "Above $104", probability: 0.03 },
];

const names = (rows: { name: string }[]) => rows.map((r) => r.name);

describe("#9574 — tied rungs keep the ladder's order", () => {
  test("hurricane: all tied, Probability ↓ reads Cat 1 → Cat 5", () => {
    const sorted = sortFuturesOutcomes(HURRICANE, "probability", "desc", false, ladderInclusionRanks(HURRICANE));
    expect(names(sorted)).toEqual([
      "Category 1 or above",
      "Category 2 or above",
      "Category 3 or above",
      "Category 4 or above",
      "Category 5 or above",
    ]);
  });

  test("brent: an 'above' ladder's ties run low threshold first under Probability ↓", () => {
    const sorted = sortFuturesOutcomes(BRENT, "probability", "desc", false, ladderInclusionRanks(BRENT));
    expect(names(sorted)).toEqual([
      "Above $101",
      "Above $102.50",
      "Above $103",
      "Above $104",
      "Above $104.50",
    ]);
    // …and Probability ↑ is the exact reverse, so the arrow never lies.
    const up = sortFuturesOutcomes(BRENT, "probability", "asc", false, ladderInclusionRanks(BRENT));
    expect(names(up)).toEqual(names(sorted).reverse());
  });

  test("a 'below' ladder nests the other way, read from the prices, not the words", () => {
    const below = [
      { id: 1, name: "Under 95", probability: 0.2 },
      { id: 2, name: "Under 100", probability: 0.7 },
      { id: 3, name: "Under 98", probability: 0.7 },
      { id: 4, name: "Under 105", probability: 0.9 },
    ];
    const sorted = sortFuturesOutcomes(below, "probability", "desc", false, ladderInclusionRanks(below));
    expect(names(sorted)).toEqual(["Under 105", "Under 100", "Under 98", "Under 95"]);
  });

  test("the ladder bars and the table agree on the brent tie", () => {
    const rungs = buildOutcomeLadderRungs(BRENT, "cumulative");
    // Ascending probability, least inclusive first.
    expect(rungs.map((r) => r.label)).toEqual([
      "Above $104.50",
      "Above $104",
      "Above $103",
      "Above $102.50",
      "Above $101",
    ]);
  });

  test("refusals keep serve order: a two-number label, or no ranks passed", () => {
    const bins = [
      { id: 1, name: "Between 95 and 96", probability: 0.1 },
      { id: 2, name: "Above 96", probability: 0.1 },
    ];
    expect(ladderInclusionRanks(bins)).toBeNull();
    expect(names(sortFuturesOutcomes(HURRICANE, "probability", "desc"))).toEqual(names(HURRICANE));
  });

  test("the futures page breaks table ties only on a cumulative market", () => {
    const page = readFileSync(path.join(__dirname, "../../app/futures/[id]/page.tsx"), "utf8");
    expect(page).toMatch(
      /ladderOrderFor\(market\.mutually_exclusive\) === "cumulative"\s*\? ladderInclusionRanks\(market\.outcomes\)\s*: null/,
    );
  });
});
