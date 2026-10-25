/**
 * #10955 (350) — A LIMITED SETTLED CHART KEEPS AN EVIDENCED WINNER VISIBLE EVEN
 * WHEN ITS CHAMPION NAME CANNOT BE MATCHED.
 *
 * "Path to resolution" (SettledPathChart) puts a matched champion first and
 * draws champion + 5. With no matched name it handed FuturesChart the served
 * order, which draws the first 5 rows. `/api/futures/{id}/history` serves its
 * top 8 and appends the graded winner AFTER them (`_select_charted_outcome_ids`),
 * so an upset winner sat at row 9 and was never drawn.
 *
 * The grade is the served settlement point (`bookmaker: "settlement"`, 1 = won),
 * read by `splitSettlementPoints`. Nothing here guesses a name, infers a loss, or
 * reads a real 0/1 reading as a result.
 *
 * Synthetic field in the server's shape, not production acceptance.
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
const leg = (id: number, name: string, last: number, grade?: number): FuturesOutcomeHistory => ({
  outcome_id: id,
  name,
  history: [
    pt(START, last),
    pt(LAST_REAL, last),
    ...(grade == null ? [] : [pt(RESULT_AT, grade, "settlement")]),
  ],
});

/** Served order: longshots first, then France (ungraded), England, Brazil and
 *  Italy; the graded winner Spain (an upset at 4%) is APPENDED as row 9.
 *  `spainGrade` is what Spain's settlement point carries. */
const FIELD = (spainGrade: number = 1): FuturesOutcomeHistory[] => [
  leg(1, "Egypt", 0.02, 0),
  leg(2, "Japan", 0.015, 0),
  leg(3, "Ghana", 0.01, 0),
  leg(4, "Peru", 0.005, 0),
  leg(5, "France", 0.12),
  leg(6, "England", 0.3, 0),
  leg(7, "Brazil", 0.2, 0),
  leg(8, "Italy", 0.08, 0),
  leg(9, "Spain", 0.04, spainGrade),
];
const ALL = ["Egypt", "Japan", "Ghana", "Peru", "France", "England", "Brazil", "Italy", "Spain"];

const payload = (outcomes: FuturesOutcomeHistory[]) => ({
  market_id: 4242,
  market_name: "Who wins?",
  hours: 8760,
  actual_hours: 8760,
  outcomes,
  round_boundaries: null,
  leaderboard: null,
  total_data_points: 0,
  sparse: false,
  history_range: null,
});

/** The legend names exactly the drawn lines, in drawn order. */
function drawn(outcomes: FuturesOutcomeHistory[], championName?: string | null, names = ALL): string[] {
  HISTORY = payload(outcomes);
  const html = renderToStaticMarkup(<SettledPathChart marketId={4242} championName={championName} />);
  return names
    .filter((n) => html.includes(`>${n}<`))
    .sort((a, b) => html.indexOf(`>${a}<`) - html.indexOf(`>${b}<`));
}

const DEFAULT_FIVE = ["Egypt", "Japan", "Ghana", "Peru", "France"];
const WINNER_AND_CONTENDERS = ["Spain", "England", "Brazil", "France", "Italy", "Egypt"];

describe("unmatched champion name: the evidenced winner beyond the first five is drawn, first", () => {
  it.each([
    ["no champion name", null],
    ["a champion name that matches no leg", "España"],
  ])("%s", (_label, championName) => {
    expect(drawn(FIELD(), championName)).toEqual(WINNER_AND_CONTENDERS);
  });

  it("the drawn rest are the strongest real readings, not the served longshots", () => {
    const shown = drawn(FIELD(), null);
    expect(shown).toEqual(expect.arrayContaining(["England", "Brazil"]));
    expect(shown).not.toContain("Ghana");
    expect(shown).not.toContain("Peru");
  });
});

describe("controls", () => {
  it("a matched champion name keeps its existing order (unchanged branch)", () => {
    expect(drawn(FIELD(), "Spain")).toEqual(WINNER_AND_CONTENDERS);
  });

  it("an unknown grade is not a win: the served first five, Spain not lifted", () => {
    expect(drawn(FIELD(0.5), null)).toEqual(DEFAULT_FIVE);
  });

  it("a field whose grades are all losses keeps the served first five", () => {
    expect(drawn(FIELD(0), null)).toEqual(DEFAULT_FIVE);
  });

  it("healthy real 0 and 1 readings are readings, not results: the served first five", () => {
    const names = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Sure"];
    const healthy = [
      leg(1, "Alpha", 0.3),
      leg(2, "Bravo", 0.2),
      leg(3, "Charlie", 0.1),
      leg(4, "Delta", 0.05),
      leg(5, "Echo", 0),
      leg(6, "Sure", 1),
    ];
    expect(drawn(healthy, null, names)).toEqual(["Alpha", "Bravo", "Charlie", "Delta", "Echo"]);
  });
});
