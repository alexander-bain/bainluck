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

// ─── #3703 — the struck score, rendered ──────────────────────────────────────
//
// Production, `/events/15304939` at 22:05Z 2026-09-06. The screen showed
// `Daniil Medvedev 3-0  39%` as the card's bold, violet-barred leading row,
// on a match Medvedev was two sets down in.
const EXACT_SCORE_MARKET = "Daniil Medvedev vs. Frances Tiafoe - Exact Score";
const EXACT_SCORE_ROWS = [
  { market_name: EXACT_SCORE_MARKET, outcome_name: "Daniil Medvedev 3-0", probability: 0.39, source: PM },
  { market_name: EXACT_SCORE_MARKET, outcome_name: "Frances Tiafoe 3-0", probability: 0.384, source: PM },
  { market_name: EXACT_SCORE_MARKET, outcome_name: "Daniil Medvedev 3-2", probability: 0.215, source: PM },
  { market_name: EXACT_SCORE_MARKET, outcome_name: "Frances Tiafoe 3-1", probability: 0.205, source: PM },
  { market_name: EXACT_SCORE_MARKET, outcome_name: "Frances Tiafoe 3-2", probability: 0.115, source: PM },
  { market_name: EXACT_SCORE_MARKET, outcome_name: "Daniil Medvedev 3-1", probability: 0.0475, source: PM },
];
const TIAFOE_TWO_SETS_UP = {
  home: 0,
  away: 2,
  homeTeam: "Daniil Medvedev",
  awayTeam: "Frances Tiafoe",
};

describe("SpecialEventMarkets — a score the board has ruled out (#3703)", () => {
  const before = renderToStaticMarkup(<SpecialEventMarkets data={payload(EXACT_SCORE_ROWS)} />);
  const after = renderToStaticMarkup(
    <SpecialEventMarkets data={payload(EXACT_SCORE_ROWS)} setsWon={TIAFOE_TWO_SETS_UP} />,
  );

  test("today's screen, reproduced: 39% on an impossible score", () => {
    expect(before).toContain("39%");
    expect(before).toContain("Daniil Medvedev 3-0");
    expect(before).not.toContain("no longer possible");
  });

  test("the price is gone from both dead rows — and so is the bar", () => {
    expect(after).toContain("Daniil Medvedev 3-0 — no longer possible");
    expect(after).toContain("Daniil Medvedev 3-1 — no longer possible");
    expect(after).not.toContain("39%");
    // Not just "39% is absent" — neither struck row carries a percentage at
    // all. (A bare `not.toContain("5%")` would fail for an unrelated reason:
    // 4.75% renders as 5%, and a LIVE row's bar is `width:11.5%`.)
    const struckRows = after.split('data-testid="special-markets-result"').slice(1);
    expect(struckRows).toHaveLength(2);
    for (const struck of struckRows) {
      expect(struck.slice(0, struck.indexOf("</div>"))).not.toContain("%");
    }
    // `bg-violet-400` is the leading row's bar, and there is exactly one.
    expect(after.split("bg-violet-400").length - 1).toBe(1);
    // Four bars for four reachable rows, where six rows drew six before.
    expect(after.split("rounded-full transition-all").length - 1).toBe(4);
    expect(before.split("rounded-full transition-all").length - 1).toBe(6);
  });

  test("the emphasis moves to the score that is actually leading", () => {
    // Rank 0 is the only violet bar on the card, and it now sits on the row
    // both venues agree on rather than on the corpse.
    const violet = after.indexOf("bg-violet-400");
    const tiafoe30 = after.indexOf("Frances Tiafoe 3-0");
    const struck = after.indexOf("no longer possible");
    expect(violet).toBeGreaterThan(-1);
    expect(tiafoe30).toBeLessThan(struck);
    expect(after).toContain("38%");
  });

  test("a struck row is muted, not bold — it is being crossed off", () => {
    expect(after).toContain(
      '<div class="flex-1 text-text-muted" data-testid="special-markets-unreachable">',
    );
  });

  test("a set-winner result on the same page keeps the bold it has today", () => {
    // Both states side by side, as the live page carried them: `Tiafoe won Set
    // 2` is news and stays bold, the struck score is muted. If this change had
    // restyled `result` wholesale instead of branching on `unreachable`, this
    // is the assertion that would have caught it.
    const both = renderToStaticMarkup(
      <SpecialEventMarkets
        data={payload([
          ...EXACT_SCORE_ROWS,
          { market_name: "Set 2 Winner: Medvedev vs Tiafoe", outcome_name: "Yes", probability: 0.04, source: PM },
          { market_name: "Set 2 Winner: Medvedev vs Tiafoe", outcome_name: "No", probability: 0.96, source: PM },
        ])}
        completedSets={2}
        decidedSetsWinner={{ side: "away", homeTeam: "Daniil Medvedev", awayTeam: "Frances Tiafoe" }}
        setsWon={TIAFOE_TWO_SETS_UP}
      />,
    );
    expect(both).toContain('<div class="flex-1 font-semibold">Tiafoe won Set 2</div>');
    expect(both).toContain(
      '<div class="flex-1 text-text-muted" data-testid="special-markets-unreachable">',
    );
  });

  test("without the tally nothing changes, which is every other sport", () => {
    expect(renderToStaticMarkup(<SpecialEventMarkets data={payload(EXACT_SCORE_ROWS)} setsWon={null} />)).toBe(before);
  });
});
