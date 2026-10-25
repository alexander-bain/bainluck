/**
 * #10955 (340) — LIMITED CHART SPACE KEEPS THE EVIDENCED WINNER AND THE REAL
 * LEADING CONTENDERS.
 *
 * A graded leg's history ends with a settlement point (`bookmaker: "settlement"`,
 * 1 for the winner, 0 for an evidenced loss). That point is the RESULT, not a
 * reading (`lib/chartSettlementPoints.ts`). Two field-selection sorts read it as a
 * reading anyway:
 *
 *   `outcomesByLatestProb` (WinnerEvolutionChart draws its first 5) and
 *   `SettledPathChart.lastProbOf` ("Path to resolution" draws champion + 5).
 *
 * Every evidenced loser then reads 0, they tie, and the order falls back to the
 * endpoint's volume-ish order — the exact defect L2-132 fixed. An ungraded leg at
 * 12% outranks a 30% contender that lost.
 *
 * The field below is synthetic (lane1's 350 probe shape), not production
 * acceptance. Served order leads with longshots and trails with England/Brazil.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

let HISTORY: unknown = null;

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => {
    if (key == null) return { data: undefined, error: null, isLoading: false, mutate: () => {} };
    return { data: HISTORY, error: null, isLoading: false, mutate: () => {} };
  },
}));
jest.mock("../../components/event/FighterAvatar", () => ({ __esModule: true, default: () => null }));

import SettledPathChart from "@/components/event/SettledPathChart";
import { latestOutcomeProb, outcomesByLatestProb } from "@/lib/eventConceptDisplay";
import type { FuturesHistoryPoint, FuturesOutcomeHistory } from "@/lib/types";

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;
const START = Date.UTC(2026, 6, 1, 0, 0, 0);
const LAST_REAL = START + 20 * HOUR;
const RESULT_AT = LAST_REAL + 3 * DAY;
const NOW = RESULT_AT + DAY;

beforeAll(() => {
  jest.useFakeTimers({ doNotFake: ["performance"] });
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());

const pt = (at: number, p: number, bookmaker = "consensus"): FuturesHistoryPoint => ({
  timestamp: new Date(at).toISOString(),
  probability: p,
  american_odds: null,
  bookmaker,
});
/** Two real readings ending at `last`, then (optionally) the served grade. */
const leg = (id: number, name: string, last: number, grade?: 0 | 1): FuturesOutcomeHistory => ({
  outcome_id: id,
  name,
  history: [
    pt(START, last),
    pt(LAST_REAL, last),
    ...(grade == null ? [] : [pt(RESULT_AT, grade, "settlement")]),
  ],
});

/** Spain won at 55%; England 30% and Brazil 20% lost; France 12% is ungraded;
 *  four longshots lost. Served order: longshots first, contenders last. */
const FIELD = (winner = "Spain"): FuturesOutcomeHistory[] => {
  const g = (name: string): 0 | 1 => (name === winner ? 1 : 0);
  return [
    leg(1, "Egypt", 0.02, g("Egypt")),
    leg(2, "Japan", 0.015, g("Japan")),
    leg(3, "Spain", 0.55, g("Spain")),
    leg(4, "Ghana", 0.01, g("Ghana")),
    leg(5, "Peru", 0.005, g("Peru")),
    leg(6, "France", 0.12),
    leg(7, "England", 0.3, g("England")),
    leg(8, "Brazil", 0.2, g("Brazil")),
  ];
};
const names = (os: FuturesOutcomeHistory[]) => os.map((o) => o.name);

describe("outcomesByLatestProb: the drawn five are the winner and the real contenders", () => {
  it("Spain leads as the result; England and Brazil are kept over ungraded and longshot legs", () => {
    expect(names(outcomesByLatestProb(FIELD()).slice(0, 5))).toEqual([
      "Spain",
      "England",
      "Brazil",
      "France",
      "Egypt",
    ]);
  });

  it("an upset winner whose last real price was 1% still leads", () => {
    const ordered = names(outcomesByLatestProb(FIELD("Ghana")));
    expect(ordered.slice(0, 4)).toEqual(["Ghana", "Spain", "England", "Brazil"]);
  });

  it("a settlement point is never the latest reading; a real 0 or 1 still is", () => {
    expect(latestOutcomeProb(leg(7, "England", 0.3, 0))).toBeCloseTo(0.3);
    expect(latestOutcomeProb(leg(3, "Spain", 0.55, 1))).toBeCloseTo(0.55);
    expect(
      latestOutcomeProb({ outcome_id: 9, name: "Only", history: [pt(RESULT_AT, 1, "settlement")] }),
    ).toBe(-1);
    // Healthy real readings at the bounds are readings, not results.
    expect(latestOutcomeProb(leg(10, "Gone", 0))).toBe(0);
    expect(latestOutcomeProb(leg(11, "Sure", 1))).toBe(1);
  });

  it("a field with no settlement points orders by real readings, real 1 first and real 0 last", () => {
    const healthy = [leg(1, "Zero", 0), leg(2, "Mid", 0.4), leg(3, "One", 1), leg(4, "Low", 0.1)];
    expect(names(outcomesByLatestProb(healthy))).toEqual(["One", "Mid", "Low", "Zero"]);
  });
});

describe("SettledPathChart: the path to resolution keeps the contenders behind the champion", () => {
  const legend = (html: string) =>
    ["Egypt", "Japan", "Spain", "Ghana", "Peru", "France", "England", "Brazil"].filter((n) =>
      html.includes(`>${n}<`),
    );

  it("England and Brazil are drawn; the weakest longshots are not", () => {
    HISTORY = {
      market_id: 4242,
      market_name: "Who wins?",
      hours: 8760,
      actual_hours: 8760,
      outcomes: FIELD(),
      round_boundaries: null,
      leaderboard: null,
      total_data_points: 0,
      sparse: false,
      history_range: null,
    };
    const shown = legend(renderToStaticMarkup(<SettledPathChart marketId={4242} championName="Spain" />));
    expect(shown).toEqual(expect.arrayContaining(["Spain", "England", "Brazil", "France"]));
    expect(shown).not.toContain("Ghana");
    expect(shown).not.toContain("Peru");
  });
});
