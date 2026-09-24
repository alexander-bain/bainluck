/**
 * #8344 (second half) — a question the hero does not answer is not the hero's.
 *
 * WHAT THE READER SAW: `/events/15318167` (White Sox @ Royals), production,
 * 390px, 2026-09-24 07:1xZ, after #8356 went live. The wrong "Chicago White Sox
 * Win" headline was gone — and so was the question it had been hiding. The
 * page's only market that was not the moneyline, "Will there be a run scored in
 * the first inning?", rendered nowhere (lane1b/552 spotted it first).
 *
 * MECHANISM: `findWinProbMarkets`' Yes/No pair clause. `Yes 0.505 / No 0.495`
 * sums to 1, so the market was taken for the hero's own question and removed
 * from Additional Markets. Its two siblings on the same wire really are the
 * moneyline and must keep being removed.
 *
 * `SPECIMEN` is the `other[]` array of `GET /api/events/15318167/game-markets`,
 * 2026-09-24 07:1xZ, verbatim in every field this module reads.
 */

import {
  askedQuestionTitle,
  buildMarketSection,
  findWinProbMarkets,
  type OtherMarketRow,
} from "@/lib/otherMarketGroups";

const QUESTION =
  "Will there be a run scored in the first inning?: Chicago White Sox vs. Kansas City Royals";

const SPECIMEN: OtherMarketRow[] = [
  { market_name: "Chicago White Sox vs Kansas City", outcome_name: "Chicago White Sox", probability: 0.545, source: "kalshi" },
  { market_name: "Chicago White Sox vs Kansas City", outcome_name: "Kansas City", probability: 0.455, source: "kalshi" },
  { market_name: QUESTION, outcome_name: "Yes", probability: 0.505, source: "polymarket" },
  { market_name: QUESTION, outcome_name: "No", probability: 0.495, source: "polymarket" },
  { market_name: "Chicago White Sox vs. Kansas City Royals", outcome_name: "Chicago White Sox", probability: 0.545, source: "polymarket" },
  { market_name: "Chicago White Sox vs. Kansas City Royals", outcome_name: "Kansas City Royals", probability: 0.455, source: "polymarket" },
];

const yesNo = (name: string, yes: number): OtherMarketRow[] => [
  { market_name: name, outcome_name: "Yes", probability: yes, source: "polymarket" },
  { market_name: name, outcome_name: "No", probability: 1 - yes, source: "polymarket" },
];

describe("#8344 — the first-inning question survives the hero filter", () => {
  it("the two moneylines are still the hero's; the question is not", () => {
    expect([...findWinProbMarkets(SPECIMEN)].sort()).toEqual([
      "Chicago White Sox vs Kansas City",
      "Chicago White Sox vs. Kansas City Royals",
    ]);
  });

  it("the page's Additional Markets section renders the question, headed by the question", () => {
    const section = buildMarketSection(SPECIMEN, {
      homeTeam: "Kansas City Royals",
      awayTeam: "Chicago White Sox",
    });
    const cards = section.categories.flatMap((c) => c.cards);
    expect(cards.map((c) => c.name)).toEqual([
      "Will there be a run scored in the first inning?",
    ]);
    expect(cards[0].outcomes.map((o) => [o.label, o.prob])).toEqual([
      ["Yes", 0.505],
      ["No", 0.495],
    ]);
    expect(section.renderedOutcomes).toBe(2);
  });

  it("the other measured '?' shapes are not eaten either", () => {
    const rows = [
      ...yesNo("Bengals vs. Texans: Safety?", 0.08),
      ...yesNo("Will the game go to extra innings?: Boston Red Sox vs. Cleveland Guardians", 0.09),
      { market_name: "Brentford FC vs. Chelsea FC: Total Corners Odd or Even?", outcome_name: "Odd", probability: 0.5, source: "polymarket" },
      { market_name: "Brentford FC vs. Chelsea FC: Total Corners Odd or Even?", outcome_name: "Even", probability: 0.5, source: "polymarket" },
    ];
    expect([...findWinProbMarkets(rows)]).toEqual([]);
  });

  it("CONTROL: a matchup-named Yes/No pair is still the hero's question (#3575)", () => {
    const rows = yesNo("US Open WTA: Iga Swiatek vs Qinwen Zheng", 0.795);
    expect([...findWinProbMarkets(rows)]).toEqual(["US Open WTA: Iga Swiatek vs Qinwen Zheng"]);
  });
});

describe("#8344 — askedQuestionTitle", () => {
  it("keeps the question and drops the restated matchup", () => {
    expect(askedQuestionTitle(QUESTION)).toBe("Will there be a run scored in the first inning?");
  });

  it("declines every other shape, so the venue's string is kept", () => {
    expect(askedQuestionTitle("Bengals vs. Texans: Safety?")).toBeNull();
    expect(askedQuestionTitle("Jynxzi vs Speed: who wins in Chess?")).toBeNull();
    expect(askedQuestionTitle("Will it rain?: A vs B vs C")).toBeNull();
    expect(askedQuestionTitle("Chicago White Sox vs. Kansas City Royals")).toBeNull();
    expect(askedQuestionTitle("?: A vs B")).toBeNull();
    expect(askedQuestionTitle(null)).toBeNull();
  });
});
