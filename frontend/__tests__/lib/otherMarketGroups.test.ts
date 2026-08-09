// UX-P037 (#1627), gaps K10 + K11 — the "Additional Markets" section.
//
// The specimens below are REAL production rows from six live games measured
// 2026-08-09 13:06–13:12 PT via GET /api/events/{id}/game-markets. The Acuña
// case is the one that mattered: the wire carried 0.095, 0.125 and 0.905 for
// one label, and the old "furthest from 0.5" merge rendered 91% — the product
// telling a reader during the game that a 9.5% home-run prop was near-certain.

import {
  AGREEMENT_TOLERANCE,
  MAX_OUTCOMES_PER_CARD,
  PLAYER_PROPS_CATEGORY,
  buildMarketSection,
  categorizeMarketName,
  mergeOutcomes,
  parsePropLabel,
  type OtherMarketRow,
} from "../../lib/otherMarketGroups";

const PM = "polymarket";

/** Real rows, Atlanta Braves @ New York Yankees (event 15191123). */
const YANKEES_MARKET = "Atlanta Braves vs. New York Yankees - Player Props";
const ACUNA: OtherMarketRow[] = [
  { market_name: YANKEES_MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.095, source: PM },
  { market_name: YANKEES_MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.125, source: PM },
  { market_name: YANKEES_MARKET, outcome_name: "Ronald Acuña Jr.: Home Runs O/U 0.5", probability: 0.905, source: PM },
];

describe("parsePropLabel", () => {
  test("recovers the statistic the old surface threw away", () => {
    expect(parsePropLabel("Ronald Acuña Jr.: Home Runs O/U 0.5")).toEqual({
      player: "Ronald Acuña Jr.",
      statistic: "Home Runs",
      threshold: "0.5",
    });
  });

  test("keeps the threshold as its source string", () => {
    // A statistic carries several thresholds live (0.5 AND 1.5 both occur), so
    // the threshold has to survive onto the row, and "0.5" must not become
    // "0.5000000001" via a float round-trip.
    expect(parsePropLabel("Jarren Duran: Home Runs O/U 1.5")?.threshold).toBe("1.5");
    expect(parsePropLabel("Shane Bieber: Strikeouts O/U 5")?.threshold).toBe("5");
  });

  test("returns null for every non-prop shape on the wire", () => {
    // These are the real unparseable labels measured across the six games.
    for (const label of ["Yes", "No", "NRFI", "Bases Loaded", "Extra Inning", "Error", "Event does not qualify", "Chicago WS wins first 5 innings", "Atlanta Braves vs. New York Yankees"]) {
      expect(parsePropLabel(label)).toBeNull();
    }
  });

  test("returns null for non-strings and empty halves", () => {
    expect(parsePropLabel(null)).toBeNull();
    expect(parsePropLabel(undefined)).toBeNull();
    expect(parsePropLabel(": Home Runs O/U 0.5")).toBeNull();
    expect(parsePropLabel("Someone:  O/U 0.5")).toBeNull();
  });
});

describe("mergeOutcomes — the wrong-number defect", () => {
  test("NEVER renders the extreme of a conflicting duplicate (the Acuña specimen)", () => {
    const { outcomes, withheld } = mergeOutcomes(
      ACUNA.map((r) => ({ label: r.outcome_name!, probability: r.probability!, source: r.source! })),
    );
    expect(withheld).toBe(1);
    expect(outcomes).toHaveLength(0);
    // The whole point: 0.905 must not reach a screen under this label.
    expect(outcomes.some((o) => o.prob === 0.905)).toBe(false);
  });

  test("duplicates that AGREE still collapse, keeping the source badge", () => {
    const { outcomes, withheld } = mergeOutcomes([
      { label: "Caleb Durbin: Home Runs O/U 0.5", probability: 0.505, source: PM },
      { label: "Caleb Durbin: Home Runs O/U 0.5", probability: 0.505, source: PM },
    ]);
    expect(withheld).toBe(0);
    expect(outcomes).toHaveLength(1);
    expect(outcomes[0].sourceCount).toBe(2);
    expect(outcomes[0].prob).toBe(0.505);
  });

  test("a single row trivially agrees with itself", () => {
    const { outcomes, withheld } = mergeOutcomes([{ label: "NRFI", probability: 0.475, source: PM }]);
    expect(withheld).toBe(0);
    expect(outcomes).toEqual([{ label: "NRFI", prob: 0.475, source: PM, sourceCount: 1 }]);
  });

  test("tolerance is a boundary, not a vibe", () => {
    const at = mergeOutcomes([
      { label: "x", probability: 0.5, source: PM },
      { label: "x", probability: 0.5 + AGREEMENT_TOLERANCE, source: PM },
    ]);
    expect(at.withheld).toBe(0);

    const past = mergeOutcomes([
      { label: "x", probability: 0.5, source: PM },
      { label: "x", probability: 0.5 + AGREEMENT_TOLERANCE + 0.001, source: PM },
    ]);
    expect(past.withheld).toBe(1);
  });

  test("preserves first-appearance order", () => {
    const { outcomes } = mergeOutcomes([
      { label: "b", probability: 0.1, source: PM },
      { label: "a", probability: 0.9, source: PM },
    ]);
    expect(outcomes.map((o) => o.label)).toEqual(["b", "a"]);
  });
});

describe("buildMarketSection — grouping (gap K11)", () => {
  const rows: OtherMarketRow[] = [
    ...ACUNA,
    { market_name: YANKEES_MARKET, outcome_name: "Matt Olson: Home Runs O/U 0.5", probability: 0.095, source: PM },
    { market_name: YANKEES_MARKET, outcome_name: "Aaron Judge: Home Runs O/U 0.5", probability: 0.21, source: PM },
    { market_name: YANKEES_MARKET, outcome_name: "Max Fried: Strikeouts O/U 5.5", probability: 0.44, source: PM },
    { market_name: YANKEES_MARKET, outcome_name: "Spencer Strider: Strikeouts O/U 6.5", probability: 0.38, source: PM },
  ];

  test("splits one heap into named statistic families", () => {
    const section = buildMarketSection(rows);
    expect(section.categories).toHaveLength(1);
    expect(section.categories[0].title).toBe(PLAYER_PROPS_CATEGORY);
    expect(section.categories[0].cards.map((c) => c.name)).toEqual(["Home Runs", "Strikeouts"]);
  });

  test("drops the redundant statistic from the row but KEEPS the threshold", () => {
    const section = buildMarketSection(rows);
    const homeRuns = section.categories[0].cards.find((c) => c.name === "Home Runs")!;
    expect(homeRuns.outcomes.map((o) => o.label)).toContain("Aaron Judge O/U 0.5");
    // Acuña was withheld, so his label must be absent entirely.
    expect(homeRuns.outcomes.some((o) => o.label.startsWith("Ronald Acuña"))).toBe(false);
  });

  test("the header count equals the bars actually rendered", () => {
    const section = buildMarketSection(rows);
    const bars = section.categories.reduce(
      (n, c) => n + c.cards.reduce((m, card) => m + card.outcomes.length, 0),
      0,
    );
    expect(section.renderedOutcomes).toBe(bars);
    // 7 rows in, 3 of them one conflicting label -> 4 labels render, 1 withheld.
    expect(section.renderedOutcomes).toBe(4);
    expect(section.withheld).toBe(1);
  });

  test("outcomes sort by probability within a card", () => {
    const section = buildMarketSection(rows);
    const homeRuns = section.categories[0].cards.find((c) => c.name === "Home Runs")!;
    const probs = homeRuns.outcomes.map((o) => o.prob);
    expect([...probs].sort((a, b) => b - a)).toEqual(probs);
  });
});

describe("buildMarketSection — graceful degradation (both-direction guard)", () => {
  test("a payload with no parseable statistic keeps the old categories", () => {
    // NOTE: two rows under one market name summing to ~1.0 are treated as the
    // hero's win probability and filtered (findWinProbMarkets) — so this
    // fixture deliberately gives each market a single row.
    const nfl: OtherMarketRow[] = [
      { market_name: "Coin Toss", outcome_name: "Heads", probability: 0.5, source: "kalshi" },
      { market_name: "Gatorade Color", outcome_name: "Orange", probability: 0.3, source: "kalshi" },
      { market_name: "Game MVP", outcome_name: "Mahomes", probability: 0.35, source: "kalshi" },
      { market_name: "First Touchdown", outcome_name: "Kelce", probability: 0.2, source: "kalshi" },
    ];
    const section = buildMarketSection(nfl);
    const titles = section.categories.map((c) => c.title);
    expect(titles).toContain("Novelty Props");
    expect(titles).toContain("MVP");
    expect(titles).toContain("Game Props");
    expect(titles).not.toContain(PLAYER_PROPS_CATEGORY);
    // Nothing withheld, nothing lost.
    expect(section.withheld).toBe(0);
    expect(section.renderedOutcomes).toBe(4);
  });

  test("the fallback categorizer is unchanged", () => {
    expect(categorizeMarketName("Coin Toss").category).toBe("Novelty Props");
    expect(categorizeMarketName("First Touchdown").category).toBe("Game Props");
    expect(categorizeMarketName("Anything Else").category).toBe("Other Markets");
  });

  test("fewer than three rows renders nothing, as before", () => {
    expect(buildMarketSection([{ market_name: "a", outcome_name: "b", probability: 0.5, source: PM }]).categories).toEqual([]);
    expect(buildMarketSection(undefined).categories).toEqual([]);
    expect(buildMarketSection(null).categories).toEqual([]);
  });

  test("spread / moneyline rows stay filtered out", () => {
    const rows: OtherMarketRow[] = [
      { market_name: "Game Spread", outcome_name: "Yankees -1.5", probability: 0.5, source: PM },
      { market_name: "Moneyline", outcome_name: "Yankees", probability: 0.6, source: PM },
      { market_name: "Coin Toss", outcome_name: "Heads", probability: 0.5, source: PM },
      { market_name: "Gatorade Color", outcome_name: "Orange", probability: 0.3, source: PM },
      { market_name: "Game MVP", outcome_name: "Judge", probability: 0.25, source: PM },
    ];
    const section = buildMarketSection(rows);
    const labels = section.categories.flatMap((c) => c.cards.flatMap((k) => k.outcomes.map((o) => o.label)));
    expect(labels).not.toContain("Yankees -1.5");
    expect(labels).not.toContain("Yankees");
  });
});

describe("buildMarketSection — the section is corrected, not gutted", () => {
  // The sizing that justified withholding at all: on the six live games it
  // costs 5–18 labels and leaves 73–88% of rows rendering. A rule that emptied
  // the surface would be gotcha #43 all over again.
  test("most rows survive when only some duplicates conflict", () => {
    const rows: OtherMarketRow[] = [];
    for (let i = 0; i < 20; i += 1) {
      rows.push({ market_name: YANKEES_MARKET, outcome_name: `Player ${i}: Home Runs O/U 0.5`, probability: 0.1, source: PM });
    }
    // Five of them get a conflicting twin.
    for (let i = 0; i < 5; i += 1) {
      rows.push({ market_name: YANKEES_MARKET, outcome_name: `Player ${i}: Home Runs O/U 0.5`, probability: 0.905, source: PM });
    }
    const section = buildMarketSection(rows);
    expect(section.withheld).toBe(5);
    expect(section.renderedOutcomes).toBe(15);
    expect(section.categories[0].cards[0].outcomes.every((o) => o.prob === 0.1)).toBe(true);
  });

  test("a card emptied entirely by withholding does not render as an empty card", () => {
    const rows: OtherMarketRow[] = [
      { market_name: YANKEES_MARKET, outcome_name: "A: Home Runs O/U 0.5", probability: 0.1, source: PM },
      { market_name: YANKEES_MARKET, outcome_name: "A: Home Runs O/U 0.5", probability: 0.9, source: PM },
      { market_name: YANKEES_MARKET, outcome_name: "B: Strikeouts O/U 5.5", probability: 0.4, source: PM },
    ];
    const section = buildMarketSection(rows);
    expect(section.categories[0].cards.map((c) => c.name)).toEqual(["Strikeouts"]);
    expect(section.categories.every((c) => c.cards.every((k) => k.outcomes.length > 0))).toBe(true);
  });

  test("every mark is still reachable — the cap disclosed, not applied to the data", () => {
    const rows: OtherMarketRow[] = [];
    for (let i = 0; i < MAX_OUTCOMES_PER_CARD + 12; i += 1) {
      rows.push({ market_name: YANKEES_MARKET, outcome_name: `Player ${i}: Home Runs O/U 0.5`, probability: 0.1 + i / 1000, source: PM });
    }
    const section = buildMarketSection(rows);
    expect(section.categories[0].cards[0].outcomes).toHaveLength(MAX_OUTCOMES_PER_CARD + 12);
  });
});
