// UX-P037 (#1627), gaps K10 + K11 — rendered guards for "Additional Markets".
//
// Both directions, per gotcha #43: the wall collapses AND the surface stays
// populated; the withheld rows are named, never silently dropped.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import SpecialEventMarkets from "../../components/SpecialEventMarkets";
import { MAX_OUTCOMES_PER_CARD } from "../../lib/otherMarketGroups";
import type { GameMarketsResponse } from "../../lib/api";

const PM = "polymarket";
const MARKET = "Atlanta Braves vs. New York Yankees - Player Props";

function payload(other: Array<Record<string, unknown>>): GameMarketsResponse {
  return { other } as unknown as GameMarketsResponse;
}

/** Real production rows, Braves @ Yankees (15191123), 2026-08-09. */
const LIVE_ROWS = [
  { market_name: MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.095, source: PM },
  { market_name: MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.125, source: PM },
  { market_name: MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.905, source: PM },
  { market_name: MARKET, outcome_name: "Aaron Judge: Home Runs O/U 0.5", probability: 0.21, source: PM },
  { market_name: MARKET, outcome_name: "Matt Olson: Home Runs O/U 0.5", probability: 0.095, source: PM },
  { market_name: MARKET, outcome_name: "Max Fried: Strikeouts O/U 5.5", probability: 0.44, source: PM },
];

describe("SpecialEventMarkets — the wrong number never reaches the screen", () => {
  const html = renderToStaticMarkup(<SpecialEventMarkets data={payload(LIVE_ROWS)} />);

  test("Acuña's 91% is absent, and so is his row", () => {
    expect(html).not.toContain("91%");
    expect(html).not.toContain("Ronald Acuña");
  });

  test("the withheld row is COUNTED on screen, not silently dropped", () => {
    expect(html).toContain("1 hidden");
    expect(html).toContain("conflicting duplicate price");
  });

  test("the rows we can attribute still render", () => {
    expect(html).toContain("Aaron Judge O/U 0.5");
    expect(html).toContain("Matt Olson O/U 0.5");
    expect(html).toContain("Max Fried O/U 5.5");
    expect(html).toContain("21%");
  });
});

describe("SpecialEventMarkets — grouping and honest counts", () => {
  const html = renderToStaticMarkup(<SpecialEventMarkets data={payload(LIVE_ROWS)} />);

  test("statistic families are named", () => {
    expect(html).toContain("Home Runs");
    expect(html).toContain("Strikeouts");
    expect(html).toContain("Player Props");
  });

  test("the header counts the bars, and pluralizes", () => {
    // 6 rows, 3 of them one conflicting label -> 3 bars render.
    expect(html).toContain("3 markets grouped by category");
    expect(html).not.toContain("3 market grouped");
  });

  test("a single rendered bar says 'market', not 'markets'", () => {
    const single = renderToStaticMarkup(
      <SpecialEventMarkets
        data={payload([
          { market_name: MARKET, outcome_name: "A: Home Runs O/U 0.5", probability: 0.1, source: PM },
          { market_name: MARKET, outcome_name: "B: Home Runs O/U 0.5", probability: 0.2, source: PM },
          { market_name: MARKET, outcome_name: "B: Home Runs O/U 0.5", probability: 0.9, source: PM },
          { market_name: MARKET, outcome_name: "C: Home Runs O/U 0.5", probability: 0.3, source: PM },
          { market_name: MARKET, outcome_name: "C: Home Runs O/U 0.5", probability: 0.95, source: PM },
        ])}
      />,
    );
    expect(single).toContain("1 market grouped by category");
  });
});

describe("SpecialEventMarkets — the wall collapses, both directions", () => {
  const many = Array.from({ length: MAX_OUTCOMES_PER_CARD + 10 }, (_, i) => ({
    market_name: MARKET,
    outcome_name: `Player${i}: Home Runs O/U 0.5`,
    probability: 0.5 - i / 100,
    source: PM,
  }));
  const html = renderToStaticMarkup(<SpecialEventMarkets data={payload(many)} />);

  test("only the cap is shown up front", () => {
    expect(html).toContain("10 more");
  });

  test("but every mark is still reachable in the disclosure", () => {
    for (let i = 0; i < MAX_OUTCOMES_PER_CARD + 10; i += 1) {
      expect(html).toContain(`Player${i} O/U 0.5`);
    }
  });

  test("the header still counts all of them", () => {
    expect(html).toContain(`${MAX_OUTCOMES_PER_CARD + 10} markets grouped by category`);
  });
});

describe("SpecialEventMarkets — graceful degradation", () => {
  test("a non-prop payload renders its original categories with no hidden note", () => {
    const html = renderToStaticMarkup(
      <SpecialEventMarkets
        data={payload([
          { market_name: "Coin Toss", outcome_name: "Heads", probability: 0.5, source: "kalshi" },
          { market_name: "Gatorade Color", outcome_name: "Orange", probability: 0.3, source: "kalshi" },
          { market_name: "Game MVP", outcome_name: "Mahomes", probability: 0.35, source: "kalshi" },
        ])}
      />,
    );
    expect(html).toContain("Novelty Props");
    expect(html).toContain("MVP");
    expect(html).not.toContain("Player Props");
    // NB: assert the NOTE, not the word "hidden" — `overflow-hidden` is a class
    // on every bar, and the looser assertion passed for the wrong reason.
    expect(html).not.toContain("conflicting duplicate price");
    expect(html).toContain("3 markets grouped by category");
  });

  test("too few rows renders nothing at all", () => {
    expect(renderToStaticMarkup(<SpecialEventMarkets data={payload([])} />)).toBe("");
  });
});
