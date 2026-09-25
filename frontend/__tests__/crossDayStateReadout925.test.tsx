import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import GamePlayCard from "@/components/GamePlayCard";
import type { ActiveChartPoint } from "@/lib/types";

function readout(timestamp: string, observedAt: string, field: "clock" | "period" | "score" = "clock") {
  const point: ActiveChartPoint = {
    timestamp, homeProb: 0.6, awayProb: 0.4, homeScore: 17, awayScore: 10,
    ...(field === "clock" ? { period: "2", clock: "0:12", clockApprox: true, clockObservedAt: observedAt } : {}),
    ...(field === "period" ? { period: "2", periodApprox: true, periodObservedAt: observedAt } : {}),
    ...(field === "score" ? { scoreApprox: true, scoreObservedAt: observedAt } : {}),
  };
  return renderToStaticMarkup(<GamePlayCard activePoint={point} homeTeam="Dallas Cowboys" awayTeam="Washington Commanders" sportKey="americanfootball_nfl" />);
}

test.each(["clock", "period", "score"] as const)("a %s carried across midnight names the observation date", field => {
  const html = readout("2026-09-23T00:01:00Z", "2026-09-22T23:59:00Z", field);
  expect(html).toContain("12:01 AM");
  expect(html).toContain("as of Sep 22, 11:59 PM");
});

test("the same wall-clock minute on a previous day is not a fresh observation", () => {
  expect(readout("2026-09-23T20:03:00Z", "2026-09-22T20:03:00Z"))
    .toContain("as of Sep 22, 8:03 PM");
});

test("the date boundary follows the reader's local calendar, not the raw ISO date", () => {
  // Jest's configured reader timezone is UTC: both instants fall on September22.
  const html = readout("2026-09-23T00:01:00+02:00", "2026-09-22T21:59:00Z");
  expect(html).toContain("as of 9:59 PM");
  expect(html).not.toContain("as of Sep");
});

test("a carry within the same displayed minute still avoids a redundant age line", () => {
  expect(readout("2026-09-22T20:03:50Z", "2026-09-22T20:03:10Z"))
    .not.toContain("game-play-card-state-as-of");
});
