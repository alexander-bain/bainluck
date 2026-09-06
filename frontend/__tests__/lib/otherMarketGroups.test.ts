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
  completedSetsForTennis,
  matchScoreStillReachable,
  mergeOutcomes,
  parseMatchScoreOutcome,
  parsePropLabel,
  periodWinnerParts,
  setNumberFromLabel,
  stripCardPrefix,
  tennisSetsWonFor,
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

// ─────────────────────────────────────────────────────────────────────────────
// live/065 (#2746) — THE US OPEN MATCH PAGE.
//
// Specimens below are the VERBATIM `other[]` wire of the live women's match
// Pegula vs Fernandez, `GET /api/events/15301138/game-markets`, captured
// 2026-09-04 09:58 PT while the second set was being played (`home_score` 0,
// `away_score` 1). Before this change the page printed, on a phone:
//
//   "US Open WTA: Jessica Pegula vs Leylah Fernandez Set 2 Winner"   87%
//   "US Open WTA: Jessica Pegula vs Leylah Fernandez Set 1 Winner"    0%   ← set over
//   card "Jessica Pegula vs Leylah Fernandez Total Sets:" / row "US Open WTA O/U 2.5"
//
// — each row repeating, over four wrapped lines, the card heading directly
// above it, and a TOUR NAME printed in the player slot of "Player Props".
// ─────────────────────────────────────────────────────────────────────────────

const USO_MARKET = "US Open WTA: Jessica Pegula vs Leylah Fernandez";
const USO_WIRE: OtherMarketRow[] = [
  { market_name: USO_MARKET, outcome_name: "Jessica Pegula", probability: 0.675, source: PM },
  { market_name: USO_MARKET, outcome_name: `${USO_MARKET} Set 1 Winner`, probability: 0.0005, source: PM },
  { market_name: USO_MARKET, outcome_name: `${USO_MARKET} Set Handicap +/-1.5`, probability: 0.0005, source: PM },
  { market_name: USO_MARKET, outcome_name: `${USO_MARKET} Set 2 Winner`, probability: 0.865, source: PM },
  { market_name: USO_MARKET, outcome_name: `${USO_MARKET} Total Sets: O/U 2.5`, probability: 0.58, source: PM },
  { market_name: USO_MARKET, outcome_name: `${USO_MARKET} Game Spread +/-4.5`, probability: 0.25, source: PM },
  { market_name: USO_MARKET, outcome_name: `${USO_MARKET} Match O/U 21.5`, probability: 0.5, source: PM },
  { market_name: USO_MARKET, outcome_name: `${USO_MARKET} Match O/U 22.5`, probability: 0.5, source: PM },
];

// ─────────────────────────────────────────────────────────────────────────────
// #3575 — the SAME shape one match later, captured whole.
//
// `GET /api/events/15305580/game-markets` `other`, verbatim, 2026-09-06 14:20Z
// (Iga Swiatek vs Qinwen Zheng, US Open women's semi-final). All 17 rows, in
// wire order. What USO_WIRE above could not show is here: the parent's 10
// un-sided child titles arrive ALONGSIDE the properly sided rows carrying the
// very same numbers — `Set 1 Winner: Swiatek vs Zheng | Yes = 0.735` beside the
// parent's `… Set 1 Winner = 0.735`. The page was rendering the un-sided copy
// and filtering the sided one out.
//
// Two `futures_markets` rows also answer to the identical name here (an
// undecomposed parent, and the match market with a clean Yes/No), which is what
// defeated `findWinProbMarkets`'s row count and reprinted the hero as `Yes 80%`.
// ─────────────────────────────────────────────────────────────────────────────
const SWIATEK_MARKET = "US Open WTA: Iga Swiatek vs Qinwen Zheng";
const SWIATEK_WIRE: OtherMarketRow[] = [
  { market_name: SWIATEK_MARKET, outcome_name: "Iga Swiatek", probability: 0.795, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: "Yes", probability: 0.795, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: "No", probability: 0.205, source: PM },
  { market_name: "Set 1 Winner: Swiatek vs Zheng", outcome_name: "Yes", probability: 0.735, source: PM },
  { market_name: "Set 1 Winner: Swiatek vs Zheng", outcome_name: "No", probability: 0.265, source: PM },
  { market_name: "Set 2 Winner: Swiatek vs Zheng", outcome_name: "Yes", probability: 0.72, source: PM },
  { market_name: "Set 2 Winner: Swiatek vs Zheng", outcome_name: "No", probability: 0.28, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Set 1 Winner`, probability: 0.735, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Set Handicap +/-1.5`, probability: 0.585, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Set 2 Winner`, probability: 0.73, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Total Sets: O/U 2.5`, probability: 0.315, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Game Spread +/-5.5`, probability: 0.42, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Set 1 O/U 8.5`, probability: 0.63, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Set 1 O/U 9.5`, probability: 0.415, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Set 1 O/U 10.5`, probability: 0.23, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Match O/U 21.5`, probability: 0.445, source: PM },
  { market_name: SWIATEK_MARKET, outcome_name: `${SWIATEK_MARKET} Match O/U 22.5`, probability: 0.445, source: PM },
];

function labelsOf(section: ReturnType<typeof buildMarketSection>): string[] {
  return section.categories.flatMap((c) => c.cards.flatMap((k) => k.outcomes.map((o) => o.label)));
}

describe("stripCardPrefix — a row does not repeat its own card's name", () => {
  test("the five real US Open child titles read as what distinguishes them", () => {
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET} Set 2 Winner`)).toBe("Set 2 Winner");
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET} Set 1 Winner`)).toBe("Set 1 Winner");
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET} Game Spread +/-4.5`)).toBe("Game Spread +/-4.5");
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET} Set Handicap +/-1.5`)).toBe("Set Handicap +/-1.5");
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET} Match O/U 21.5`)).toBe("Match O/U 21.5");
  });

  test("the colon a child title leaves behind before O/U is closed up", () => {
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET} Total Sets: O/U 2.5`)).toBe("Total Sets O/U 2.5");
  });

  test("a row that is NOT prefixed comes through byte-identical", () => {
    // The MLB/NFL population — no label there begins with its market's name.
    expect(stripCardPrefix(YANKEES_MARKET, "Ronald Acuña Jr.: Home Runs O/U 0.5")).toBe(
      "Ronald Acuña Jr.: Home Runs O/U 0.5",
    );
    expect(stripCardPrefix(USO_MARKET, "Jessica Pegula")).toBe("Jessica Pegula");
    for (const label of ["Yes", "No", "NRFI", "Bases Loaded"]) {
      expect(stripCardPrefix(YANKEES_MARKET, label)).toBe(label);
    }
  });

  test("a row never loses its name", () => {
    // The child title IS the parent title: keep it rather than render a blank.
    expect(stripCardPrefix(USO_MARKET, USO_MARKET)).toBe(USO_MARKET);
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET}   `)).toBe(USO_MARKET);
    expect(stripCardPrefix(USO_MARKET, `${USO_MARKET}: `)).toBe(`${USO_MARKET}:`);
  });

  test("only a real prefix is consumed, and casing/spacing survive", () => {
    expect(stripCardPrefix(USO_MARKET, "Leylah Fernandez to win Set 2")).toBe("Leylah Fernandez to win Set 2");
    expect(stripCardPrefix("US Open WTA:  Jessica Pegula vs Leylah Fernandez", `${USO_MARKET} Set 2 Winner`)).toBe("Set 2 Winner");
    expect(stripCardPrefix(USO_MARKET.toUpperCase(), `${USO_MARKET} Set 2 Winner`)).toBe("Set 2 Winner");
  });

  test("empty and absent halves are safe", () => {
    expect(stripCardPrefix(null, "Set 2 Winner")).toBe("Set 2 Winner");
    expect(stripCardPrefix(USO_MARKET, null)).toBe("");
    expect(stripCardPrefix(undefined, undefined)).toBe("");
  });

  test("a market name with regex metacharacters is matched literally", () => {
    // `+`, `(` and `.` all occur in wire market names; an unescaped splice
    // would either throw or match the wrong thing.
    const odd = "Set Handicap +/-1.5 (Men's)";
    expect(stripCardPrefix(odd, `${odd} Winner`)).toBe("Winner");
    expect(stripCardPrefix("A.B", "AxB Winner")).toBe("AxB Winner");
  });
});

describe("setNumberFromLabel", () => {
  test("names the set a row is about", () => {
    expect(setNumberFromLabel("Set 1 Winner")).toBe(1);
    expect(setNumberFromLabel("set 3 winner")).toBe(3);
  });

  test("is null for rows that are not about ONE named set", () => {
    for (const label of ["Set Handicap +/-1.5", "Total Sets O/U 2.5", "Match O/U 21.5", "Jessica Pegula", "Settlement", ""]) {
      expect(setNumberFromLabel(label)).toBeNull();
    }
    expect(setNumberFromLabel(null)).toBeNull();
  });
});

describe("completedSetsForTennis", () => {
  test("the live specimen: one set banked while the second is played", () => {
    expect(completedSetsForTennis("tennis_wta_us_open", { home_score: 0, away_score: 1 })).toBe(1);
    expect(completedSetsForTennis("tennis_atp", { home_score: 2, away_score: 1 })).toBe(3);
  });

  test("every other sport returns zero, so no row of theirs can be marked", () => {
    expect(completedSetsForTennis("baseball_mlb", { home_score: 4, away_score: 2 })).toBe(0);
    expect(completedSetsForTennis("americanfootball_nfl", { home_score: 21, away_score: 17 })).toBe(0);
    expect(completedSetsForTennis(null, { home_score: 1, away_score: 1 })).toBe(0);
  });

  test("it refuses a score that cannot be a set count", () => {
    // Six is not a set count in any tennis match ever played: these are games
    // or points, and guessing would freeze a set that is still being played.
    expect(completedSetsForTennis("tennis_atp", { home_score: 6, away_score: 4 })).toBe(0);
    expect(completedSetsForTennis("tennis_atp", { home_score: null, away_score: 1 })).toBe(0);
    expect(completedSetsForTennis("tennis_atp", null)).toBe(0);
    expect(completedSetsForTennis("tennis_atp", { home_score: -1, away_score: 1 })).toBe(0);
  });
});

describe("buildMarketSection — the live US Open wire", () => {
  test("no rendered label repeats the match's own name", () => {
    const labels = labelsOf(buildMarketSection(USO_WIRE, { completedSets: 1 }));
    expect(labels.length).toBeGreaterThan(0);
    for (const label of labels) expect(label).not.toContain("Jessica Pegula vs Leylah Fernandez");
  });

  // SUPERSEDED, #3575. This test used to assert that the rows read "Set 2
  // Winner", "Set 1 Winner", "Total Sets O/U 2.5", "Game Spread +/-4.5" and
  // "Match O/U 21.5", under the name "the rows say what they are". They do not
  // say what they are. Every one of those strings is a QUESTION: `Set 1 Winner
  // 74%` never says for whom and `Match O/U 21.5 45%` never says over or under.
  // De-prefixing made them short enough to read and no more answerable, because
  // the side is not in the wire text to recover. So the assertion is inverted:
  // a question is not a row.
  test("a question is never rendered as if it were an answer", () => {
    const labels = labelsOf(buildMarketSection(USO_WIRE, { completedSets: 1 }));
    for (const question of [
      "Set 2 Winner",
      "Set 1 Winner",
      "Total Sets O/U 2.5",
      "Game Spread +/-4.5",
      "Match O/U 21.5",
      "Match O/U 22.5",
      "Set Handicap +/-1.5",
    ]) {
      expect(labels).not.toContain(question);
    }
  });

  test("the row that DOES name a side survives", () => {
    // The parent's one real outcome. The rule drops child titles, not rows.
    expect(labelsOf(buildMarketSection(USO_WIRE, { completedSets: 1 }))).toContain("Jessica Pegula");
  });

  test("a tour name is no longer parsed as a player", () => {
    // `US Open WTA: … Total Sets: O/U 2.5` used to parse to player "US Open
    // WTA", putting the tour in the player slot of a "Player Props" card named
    // after the matchup.
    const section = buildMarketSection(USO_WIRE, { completedSets: 1 });
    expect(section.categories.map((c) => c.title)).not.toContain(PLAYER_PROPS_CATEGORY);
    expect(labelsOf(section)).not.toContain("US Open WTA O/U 2.5");
  });

  test("a set already played is marked decided; the set being played is not", () => {
    // Moved onto SWIATEK_WIRE (#3575): the freeze now rides the SIDED row, which
    // is the only one left. The label no longer begins "Set 1", so this also
    // proves the set number is carried from the market title rather than
    // re-read from the rendered string.
    const outcomes = buildMarketSection(SWIATEK_WIRE, { completedSets: 1 }).categories
      .flatMap((c) => c.cards.flatMap((k) => k.outcomes));
    const byLabel = new Map(outcomes.map((o) => [o.label, o]));
    expect(byLabel.get("Swiatek wins Set 1")?.decided).toBe(true);
    expect(byLabel.get("Swiatek wins Set 2")?.decided).toBeUndefined();
    // Neither is dropped: the reader still sees both rows.
    expect(byLabel.get("Swiatek wins Set 1")?.prob).toBe(0.735);
  });

  test("before a set is finished nothing is decided", () => {
    const outcomes = buildMarketSection(SWIATEK_WIRE, { completedSets: 0 }).categories
      .flatMap((c) => c.cards.flatMap((k) => k.outcomes));
    expect(outcomes.every((o) => o.decided === undefined)).toBe(true);
    // …and the default is the same as zero, so no caller can decide by accident.
    const defaulted = buildMarketSection(SWIATEK_WIRE).categories
      .flatMap((c) => c.cards.flatMap((k) => k.outcomes));
    expect(defaulted.every((o) => o.decided === undefined)).toBe(true);
  });

  test("a set-adjacent row is never frozen by a set finishing", () => {
    // Repointed off USO_WIRE (#3575). Read against that fixture this test now
    // passes for the WRONG reason: the rows it names are gone, and
    // `undefined?.decided` is `undefined`, which is what it asserts. So it is
    // given rows that really exist — and asserted to have found them first.
    const rows: OtherMarketRow[] = [
      // Market names deliberately free of the `handicap` / `total` / `winner`
      // keywords, so this measures the SET-FREEZE rule and not the redundancy
      // filter that would otherwise remove the rows before it runs.
      { market_name: "Swiatek vs. Zheng: Sets Margin", outcome_name: "Set Handicap +/-1.5", probability: 0.585, source: PM },
      { market_name: "Swiatek vs. Zheng: Sets Count", outcome_name: "Total Sets O/U 2.5", probability: 0.315, source: PM },
      { market_name: "Swiatek vs. Zheng: Match Games", outcome_name: "Match O/U 21.5", probability: 0.445, source: PM },
    ];
    const outcomes = buildMarketSection(rows, { completedSets: 3 }).categories
      .flatMap((c) => c.cards.flatMap((k) => k.outcomes));
    const byLabel = new Map(outcomes.map((o) => [o.label, o]));
    for (const label of ["Set Handicap +/-1.5", "Total Sets O/U 2.5", "Match O/U 21.5"]) {
      expect(byLabel.has(label)).toBe(true);
      expect(byLabel.get(label)?.decided).toBeUndefined();
    }
  });

  test("the MLB population is untouched by both rules", () => {
    // The same specimen the module was built on, re-run with a set count that
    // would freeze rows if the tennis rule leaked: nothing changes.
    const before = buildMarketSection(ACUNA);
    const after = buildMarketSection(ACUNA, { completedSets: 3 });
    expect(after).toEqual(before);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// #3575 — the whole card, not one label at a time.
//
// The defect was never a single bad string; it was that EVERY row on the card
// was unreadable, in three different ways at once. So the guard asserts the
// finished card, which is the only thing that can catch "fixed one, left two".
// ─────────────────────────────────────────────────────────────────────────────
describe("buildMarketSection — every row on the card names a side (#3575)", () => {
  test("the un-sided questions are gone and the sided rows they duplicated are what renders", () => {
    const section = buildMarketSection(SWIATEK_WIRE);
    expect(labelsOf(section).sort()).toEqual(["Swiatek wins Set 1", "Swiatek wins Set 2"]);
  });

  test("the numbers survive the swap — the sided twin carries the same price", () => {
    // The parent said `… Set 1 Winner = 0.735`; the sided row says
    // `Set 1 Winner: Swiatek vs Zheng | Yes = 0.735`. Nothing is lost by
    // dropping the question: its number is still on the page, now attached to
    // someone's name.
    const byLabel = new Map(
      buildMarketSection(SWIATEK_WIRE).categories
        .flatMap((c) => c.cards.flatMap((k) => k.outcomes))
        .map((o) => [o.label, o.prob]),
    );
    expect(byLabel.get("Swiatek wins Set 1")).toBe(0.735);
    expect(byLabel.get("Swiatek wins Set 2")).toBe(0.72);
  });

  test("the hero is not reprinted in the rail, despite two markets sharing one name", () => {
    const labels = labelsOf(buildMarketSection(SWIATEK_WIRE));
    // `Yes 80%` / `No 21%` / `Iga Swiatek 80%` are all the 78%-22% hero.
    expect(labels).not.toContain("Yes");
    expect(labels).not.toContain("No");
    expect(labels).not.toContain("Iga Swiatek");
  });

  test("the period-winner rows sit on ONE card headed with the matchup", () => {
    const cards = buildMarketSection(SWIATEK_WIRE).categories.flatMap((c) => c.cards);
    expect(cards).toHaveLength(1);
    expect(cards[0].name).toBe("Swiatek vs Zheng");
  });

  test("the complementary No is dropped, never renamed to the other player", () => {
    // Naming `No` as `Zheng wins Set 1` is only true where the period cannot be
    // drawn. The module has no way to know that, so it must not say it.
    const labels = labelsOf(buildMarketSection(SWIATEK_WIRE));
    expect(labels.some((l) => l.startsWith("Zheng"))).toBe(false);
    expect(labels.some((l) => l.includes("does not"))).toBe(false);
  });

  test("the count in the header is the rows a reader can actually read", () => {
    // It said "13 markets grouped by category" above thirteen unreadable rows.
    expect(buildMarketSection(SWIATEK_WIRE).renderedOutcomes).toBe(2);
  });

  test("A MATCH winner is still filtered — only PERIOD-scoped winners are spared", () => {
    const rows: OtherMarketRow[] = [
      { market_name: "Match Winner: Swiatek vs Zheng", outcome_name: "Yes", probability: 0.78, source: PM },
      { market_name: "Match Winner: Swiatek vs Zheng", outcome_name: "No", probability: 0.22, source: PM },
      { market_name: "Coin Toss", outcome_name: "Heads", probability: 0.5, source: PM },
      { market_name: "Gatorade Color", outcome_name: "Orange", probability: 0.3, source: PM },
      { market_name: "Game MVP", outcome_name: "Judge", probability: 0.25, source: PM },
    ];
    const labels = labelsOf(buildMarketSection(rows));
    expect(labels.some((l) => l.includes("wins Match"))).toBe(false);
    // …and the rest of the card is undisturbed.
    expect(labels).toEqual(expect.arrayContaining(["Heads", "Orange", "Judge"]));
  });

  test("a period winner we CANNOT name stays filtered — no bare Yes/No is un-hidden", () => {
    // Verbatim from production, 2026-09-06 14:47Z:
    //     Counter-Strike: G2 vs TYLOO - Map 1 Winner   Yes 0.500 / No 0.500
    // The words `map 1 winner` are there, but the `vs` comes BEFORE the scope,
    // so there is no `Winner: A vs B` to read sides out of. An exemption keyed
    // on the period WORDS un-hid this and left `Yes 50%` / `No 50%` on screen —
    // the very defect being removed, newly introduced on esports pages. The
    // exemption is granted by the same function that produces the label, so a
    // market we cannot name keeps falling through to the `winner` keyword.
    const rows: OtherMarketRow[] = [
      { market_name: "Counter-Strike: G2 vs TYLOO - Map 1 Winner", outcome_name: "Yes", probability: 0.5, source: PM },
      { market_name: "Counter-Strike: G2 vs TYLOO - Map 1 Winner", outcome_name: "No", probability: 0.5, source: PM },
      { market_name: "Coin Toss", outcome_name: "Heads", probability: 0.5, source: PM },
      { market_name: "Gatorade Color", outcome_name: "Orange", probability: 0.3, source: PM },
      { market_name: "Game MVP", outcome_name: "Judge", probability: 0.25, source: PM },
    ];
    const labels = labelsOf(buildMarketSection(rows));
    expect(labels).not.toContain("Yes");
    expect(labels).not.toContain("No");
    // …and the rest of the section is undisturbed, so this is a filter and not a wipe.
    expect(labels).toEqual(expect.arrayContaining(["Heads", "Orange", "Judge"]));
  });

  test("`Match Winner: A vs B` parses but is refused — that one IS the hero", () => {
    expect(periodWinnerParts("Match Winner: Swiatek vs Zheng")).toBeNull();
    expect(periodWinnerParts("Set 1 Winner: Swiatek vs Zheng")).toEqual({
      scope: "Set 1",
      first: "Swiatek",
      second: "Zheng",
    });
    expect(periodWinnerParts("Counter-Strike: G2 vs TYLOO - Map 1 Winner")).toBeNull();
    expect(periodWinnerParts("1st Half Winner: Arsenal vs Chelsea")).toEqual({
      scope: "1st Half",
      first: "Arsenal",
      second: "Chelsea",
    });
  });

  test("a row whose name merely EQUALS its card's keeps rendering", () => {
    // The drop is for a child TITLE — a real prefix with a remainder. An
    // outcome that simply repeats its market name has no remainder, is not a
    // question, and must not be swept up.
    const rows: OtherMarketRow[] = [
      { market_name: "Rain Delay", outcome_name: "Rain Delay", probability: 0.4, source: PM },
      { market_name: "Coin Toss", outcome_name: "Heads", probability: 0.5, source: PM },
      { market_name: "Game MVP", outcome_name: "Judge", probability: 0.25, source: PM },
    ];
    expect(labelsOf(buildMarketSection(rows))).toContain("Rain Delay");
  });
});

// ─── #3703 — a match page stops pricing a score the board has ruled out ──────
//
// Production, `GET /api/events/15304939/game-markets` at 22:05Z 2026-09-06,
// Medvedev–Tiafoe in the US Open round of 16. `home_score: 0, away_score: 2`,
// the hero read `6-7, 4-6, 4-4`, and the card two rows above the ladder read
// `Tiafoe won Set 2 / Tiafoe won Set 1`. The Polymarket ladder nevertheless made
// `Daniil Medvedev 3-0` its LEADING outcome at 0.390 — bold, violet bar — a
// score that stopped being reachable an hour earlier. Kalshi's ladder had the
// same result at 0.010, so the two cards disagreed by 38 points on one question.
//
// Both wire dialects below are verbatim from that single response.
const MEDVEDEV_TIAFOE_SETS = {
  home: 0,
  away: 2,
  homeTeam: "Daniil Medvedev",
  awayTeam: "Frances Tiafoe",
};

const EXACT_SCORE_WIRE: OtherMarketRow[] = [
  { market_name: "Daniil Medvedev vs. Frances Tiafoe - Exact Score", outcome_name: "Daniil Medvedev 3-0", probability: 0.39, source: PM },
  { market_name: "Daniil Medvedev vs. Frances Tiafoe - Exact Score", outcome_name: "Frances Tiafoe 3-0", probability: 0.384, source: PM },
  { market_name: "Daniil Medvedev vs. Frances Tiafoe - Exact Score", outcome_name: "Daniil Medvedev 3-2", probability: 0.215, source: PM },
  { market_name: "Daniil Medvedev vs. Frances Tiafoe - Exact Score", outcome_name: "Frances Tiafoe 3-1", probability: 0.205, source: PM },
  { market_name: "Daniil Medvedev vs. Frances Tiafoe - Exact Score", outcome_name: "Frances Tiafoe 3-2", probability: 0.115, source: PM },
  { market_name: "Daniil Medvedev vs. Frances Tiafoe - Exact Score", outcome_name: "Daniil Medvedev 3-1", probability: 0.0475, source: PM },
];

describe("tennisSetsWonFor", () => {
  test("it reports the per-side tally the live specimen carried", () => {
    expect(
      tennisSetsWonFor("tennis_atp_us_open", {
        home_score: 0,
        away_score: 2,
        home_team: "Daniil Medvedev",
        away_team: "Frances Tiafoe",
      }),
    ).toEqual(MEDVEDEV_TIAFOE_SETS);
  });

  test("it answers at one set all, where `decidedSetsWinnerFor` must stay silent", () => {
    // The state this exists for: nobody can be named the winner of the sets so
    // far, yet BOTH 3-0 finishes are already dead.
    expect(
      tennisSetsWonFor("tennis_wta", {
        home_score: 1,
        away_score: 1,
        home_team: "Marta Kostyuk",
        away_team: "Linda Noskova",
      }),
    ).toEqual({ home: 1, away: 1, homeTeam: "Marta Kostyuk", awayTeam: "Linda Noskova" });
  });

  test("it is null at 0-0, for every other sport, and with a name missing", () => {
    const named = { home_team: "A", away_team: "B" };
    expect(tennisSetsWonFor("tennis_atp", { home_score: 0, away_score: 0, ...named })).toBeNull();
    expect(tennisSetsWonFor("baseball_mlb", { home_score: 4, away_score: 2, ...named })).toBeNull();
    expect(tennisSetsWonFor("tennis_atp", { home_score: 6, away_score: 4, ...named })).toBeNull();
    expect(tennisSetsWonFor("tennis_atp", { home_score: 0, away_score: 2, home_team: "", away_team: "B" })).toBeNull();
    expect(tennisSetsWonFor("tennis_atp", null)).toBeNull();
  });
});

describe("parseMatchScoreOutcome", () => {
  test("both live dialects parse to the same shape", () => {
    expect(parseMatchScoreOutcome("Frances Tiafoe wins 3-0")).toEqual({ side: "Frances Tiafoe", won: 3, lost: 0 });
    expect(parseMatchScoreOutcome("Daniil Medvedev 3-1")).toEqual({ side: "Daniil Medvedev", won: 3, lost: 1 });
    expect(parseMatchScoreOutcome("Aryna Sabalenka 2-0")).toEqual({ side: "Aryna Sabalenka", won: 2, lost: 0 });
  });

  test("it refuses every label that is not a match score", () => {
    // A set's game score, a totals line, a bare side, and a losing tally.
    expect(parseMatchScoreOutcome("Medvedev 6-4")).toBeNull();
    expect(parseMatchScoreOutcome("Match O/U 21.5")).toBeNull();
    expect(parseMatchScoreOutcome("Over")).toBeNull();
    expect(parseMatchScoreOutcome("Tiafoe 1-3")).toBeNull();
    expect(parseMatchScoreOutcome("Tiafoe 3-3")).toBeNull();
    expect(parseMatchScoreOutcome("3-0")).toBeNull();
    expect(parseMatchScoreOutcome(null)).toBeNull();
  });
});

describe("matchScoreStillReachable", () => {
  test("the two dead scores are dead, in both dialects", () => {
    for (const label of ["Daniil Medvedev 3-0", "Daniil Medvedev wins 3-0", "Daniil Medvedev 3-1", "Daniil Medvedev wins 3-1"]) {
      expect(matchScoreStillReachable(label, MEDVEDEV_TIAFOE_SETS)).toBe(false);
    }
  });

  test("every score still on the table survives", () => {
    for (const label of ["Daniil Medvedev 3-2", "Frances Tiafoe 3-0", "Frances Tiafoe 3-1", "Frances Tiafoe 3-2"]) {
      expect(matchScoreStillReachable(label, MEDVEDEV_TIAFOE_SETS)).toBe(true);
    }
  });

  test("at one set all it strikes BOTH 3-0s and nothing else", () => {
    const sets = { home: 1, away: 1, homeTeam: "Marta Kostyuk", awayTeam: "Linda Noskova" };
    expect(matchScoreStillReachable("Marta Kostyuk 3-0", sets)).toBe(false);
    expect(matchScoreStillReachable("Linda Noskova 3-0", sets)).toBe(false);
    expect(matchScoreStillReachable("Marta Kostyuk 3-1", sets)).toBe(true);
    expect(matchScoreStillReachable("Linda Noskova 3-2", sets)).toBe(true);
  });

  test("it fails OPEN — no tally, no parse, or a side it cannot place", () => {
    // Striking a LIVE row off is the worse error, so every door returns true.
    expect(matchScoreStillReachable("Daniil Medvedev 3-0", null)).toBe(true);
    expect(matchScoreStillReachable("Something Else", MEDVEDEV_TIAFOE_SETS)).toBe(true);
    // A side naming neither competitor, and — the collision door — one naming
    // both, which is what a doubles pair sharing a surname produces.
    expect(matchScoreStillReachable("Carlos Alcaraz 3-0", MEDVEDEV_TIAFOE_SETS)).toBe(true);
    expect(
      matchScoreStillReachable("Bryan 2-0", {
        home: 1,
        away: 0,
        homeTeam: "Bob Bryan",
        awayTeam: "Mike Bryan",
      }),
    ).toBe(true);
  });

  test("the surname the market uses places against the full name the event uses", () => {
    // The wire is not consistent about this: the ladder writes full names while
    // `Set N Winner` markets write surnames, and both must place.
    expect(matchScoreStillReachable("Medvedev 3-0", MEDVEDEV_TIAFOE_SETS)).toBe(false);
    expect(matchScoreStillReachable("Tiafoe 3-1", MEDVEDEV_TIAFOE_SETS)).toBe(true);
  });
});

describe("buildMarketSection — the struck exact-score row (#3703)", () => {
  const cardOf = (opts: Parameters<typeof buildMarketSection>[1]) => {
    const section = buildMarketSection(EXACT_SCORE_WIRE, opts);
    const cards = section.categories.flatMap((c) => c.cards);
    expect(cards).toHaveLength(1);
    return cards[0];
  };

  test("today's render, reproduced: the impossible score leads the card", () => {
    const card = cardOf({});
    expect(card.outcomes[0].label).toBe("Daniil Medvedev 3-0");
    expect(card.outcomes[0].result).toBeUndefined();
    expect(card.outcomes[0].unreachable).toBeUndefined();
  });

  test("with the tally, it is struck, said plainly, and sunk to the bottom", () => {
    const card = cardOf({ setsWon: MEDVEDEV_TIAFOE_SETS });
    // The leader is now the score both venues actually agree on.
    expect(card.outcomes[0].label).toBe("Frances Tiafoe 3-0");
    expect(card.outcomes[0].unreachable).toBeUndefined();

    const struck = card.outcomes.filter((o) => o.unreachable === true);
    expect(struck.map((o) => o.result)).toEqual([
      "Daniil Medvedev 3-0 — no longer possible",
      "Daniil Medvedev 3-1 — no longer possible",
    ]);
    // Sunk: both live at the END of the list, after every reachable row.
    expect(card.outcomes.slice(-2)).toEqual(struck);
    // And they are still THERE. A reader who came looking for 3-0 gets an
    // answer; a silently dropped row is not one.
    expect(card.outcomes).toHaveLength(EXACT_SCORE_WIRE.length);
  });

  test("reachable rows keep their bar, their price and their order", () => {
    const card = cardOf({ setsWon: MEDVEDEV_TIAFOE_SETS });
    const live = card.outcomes.filter((o) => o.unreachable !== true);
    expect(live.map((o) => o.label)).toEqual([
      "Frances Tiafoe 3-0",
      "Daniil Medvedev 3-2",
      "Frances Tiafoe 3-1",
      "Frances Tiafoe 3-2",
    ]);
    for (const o of live) {
      expect(o.decided).toBeUndefined();
      expect(o.result).toBeUndefined();
    }
    expect(live[0].prob).toBeCloseTo(0.384);
  });

  test("a non-tennis ladder is byte-for-byte what it is today", () => {
    // `setsWon` is null for every other sport, so this is the whole regression
    // surface for the MLB and NFL payloads this module was built on.
    const before = buildMarketSection(USO_WIRE, { completedSets: 1 });
    const after = buildMarketSection(USO_WIRE, { completedSets: 1, setsWon: null });
    expect(after).toEqual(before);
  });
});
