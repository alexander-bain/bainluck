// #10923 — AN OVERTIME PLAY READS "OT", NOT "Q5".
//
// `/events/14780557` (BAL 30–23 ATL, Final in overtime), 390px, shopper pass
// 0361: the play row under the win-prob chart read "Q5 2:57 · Tyler Huntley 1 Yd
// Rush". The served `scoring_plays[-1].period` is the bare digit `"5"`, and
// `formatPeriod` turned any digit into `Q${n}` — football has no fifth quarter.
// `periodMarkers.ts` already bounded the chart's bare digits by regulation
// (#4955); the play row and the live header (both through `formatPeriod`) did
// not.
//
// `SPECIMEN_POINT` is `computeLastChartPoint` over the production
// `/api/events/14780557/history` payload (2026-10-12 04:03Z), verbatim. Rendered
// through the real card it read `Q5 2:57` before this fix and `OT 2:57` after.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "@/components/GamePlayCard";
import { formatPeriod, restingGameClock } from "@/lib/restingGameClock";
import type { ActiveChartPoint } from "@/lib/types";

const SPECIMEN_POINT = {
  timestamp: "2026-10-12T03:48:00+00:00",
  homeProb: 0,
  awayProb: 1,
  probKnown: true,
  homeScore: 23,
  awayScore: 30,
  period: "Final",
  clock: "Final",
  scoringPlay: {
    timestamp: "2026-10-12T03:43:07.536361+00:00",
    description: "Tyler Huntley 1 Yd Rush (Tyler Loop Kick)",
    short_text: "",
    team: "Baltimore Ravens",
    type: "Rushing Touchdown",
    home_score: 23,
    away_score: 30,
    period: "5",
    clock: "2:57",
    timestamp_resolved: true,
  },
  scoreStamp: "2026-10-12T03:48:00+00:00",
  scoreFrom: "history",
} as unknown as ActiveChartPoint;

function playRowText(): string {
  return renderToStaticMarkup(
    <GamePlayCard
      homeTeam="Atlanta Falcons"
      awayTeam="Baltimore Ravens"
      sportKey="americanfootball_nfl"
      activePoint={null}
      lastPoint={SPECIMEN_POINT}
    />,
  )
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ");
}

describe("#10923 the play row names overtime", () => {
  test("specimen: the winning play reads OT 2:57, never Q5", () => {
    const text = playRowText();
    expect(text).toContain("OT 2:57");
    expect(text).toContain("Tyler Huntley 1 Yd Rush");
    expect(text).not.toMatch(/\bQ5\b/);
  });

  test("the live header's selector reads the same OT", () => {
    const clock = restingGameClock(
      { timestamp: "2026-10-12T03:43:00Z", period: "5", clock: "2:57" },
      "americanfootball_nfl",
    );
    expect(clock.period).toBe("OT");
    expect(clock.gameClock).toBe("2:57");
  });

  test.each([
    ["5", "americanfootball_nfl", "OT"],
    ["7", "americanfootball_ncaaf", "3OT"],
    ["5", "basketball_nba", "OT"],
    ["6", "basketball_wnba", "2OT"],
    ["3", "basketball_ncaab", "OT"],
    ["4", "icehockey_nhl", "OT"],
  ])("overtime: %s in %s → %s", (period, sport, label) => {
    expect(formatPeriod(period, sport)).toBe(label);
  });

  test.each([
    // Hockey's 5th is a regular-season shootout OR a playoff 2nd overtime.
    ["5", "icehockey_nhl"],
    // Soccer's 3rd is an extra-time half, not overtime.
    ["3", "soccer_epl"],
    ["0", "americanfootball_nfl"],
  ])("a number the sport cannot name honestly prints nothing: %s in %s", (period, sport) => {
    expect(formatPeriod(period, sport)).toBe("");
  });

  // ---- controls: green on both sides of the fix ----

  test.each([
    ["4", "americanfootball_nfl", "Q4"],
    ["1", "basketball_nba", "Q1"],
  ])("CONTROL: regulation keeps its quarter: %s in %s → %s", (period, sport, label) => {
    expect(formatPeriod(period, sport)).toBe(label);
  });

  test("CONTROL: a spelled-out period and an absent sport render as before", () => {
    expect(formatPeriod("Overtime", "americanfootball_nfl")).toBe("Overtime");
    expect(formatPeriod("3")).toBe("Q3");
  });

  // The sport now picks the unit: these read Q2 / Q1 before the fix.
  test("hockey and soccer get their own unit inside regulation", () => {
    expect(formatPeriod("2", "icehockey_nhl")).toBe("P2");
    expect(formatPeriod("1", "soccer_epl")).toBe("1H");
  });
});
