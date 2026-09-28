/**
 * #9441 — a finished soccer page's chart readout says `Final`, not `—`.
 *
 * Production 2026-09-28, 390px, settled `/events/15194390` (England 2 – 3
 * Spain). Soccer history carries no period, so the readout at rest printed a
 * lone `—` above `2 - 3`, where a finished MLB page prints `Final`. The point
 * below is that page's last chart point in shape: score 2–3, no period, no clock.
 *
 * Every arm that must NOT say Final is paired with the one that must.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "../../components/GamePlayCard";
import type { ActiveChartPoint } from "../../lib/types";

const last: ActiveChartPoint = {
  timestamp: "2026-09-26T20:42:00Z",
  homeProb: 0,
  awayProb: 1,
  homeScore: 2,
  awayScore: 3,
  period: null,
  clock: null,
  scoringPlay: null,
};

const FINAL = { home: 2, away: 3 };

function badge(props: Partial<React.ComponentProps<typeof GamePlayCard>>): string {
  const html = renderToStaticMarkup(
    <GamePlayCard
      activePoint={null}
      lastPoint={last}
      homeTeam="England"
      awayTeam="Spain"
      sportKey="soccer_uefa_nations_league"
      {...props}
    />,
  );
  return html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
}

describe("#9441 the finished soccer readout at rest", () => {
  it("says Final on the production specimen", () => {
    const t = badge({ restingFinalScore: FINAL });
    expect(t.startsWith("Final")).toBe(true);
  });

  it("keeps the dash on a live or upcoming game (no final score passed)", () => {
    expect(badge({}).startsWith("—")).toBe(true);
  });

  it("keeps the dash while the reader scrubs a mid-game point", () => {
    // Already 2–3, but ten minutes before full time: the game is not over yet.
    const mid: ActiveChartPoint = { ...last, timestamp: "2026-09-26T20:30:00Z" };
    expect(badge({ restingFinalScore: FINAL, activePoint: mid }).startsWith("—")).toBe(true);
  });

  it("does not call a resting point Final when its score is not the final score", () => {
    const stale: ActiveChartPoint = { ...last, homeScore: 2, awayScore: 2 };
    expect(badge({ restingFinalScore: FINAL, lastPoint: stale }).startsWith("—")).toBe(true);
  });

  it("a point that names its own period keeps it", () => {
    const withPeriod: ActiveChartPoint = { ...last, period: "Full Time" };
    const t = badge({ restingFinalScore: FINAL, lastPoint: withPeriod });
    expect(t.startsWith("Full Time")).toBe(true);
  });
});
