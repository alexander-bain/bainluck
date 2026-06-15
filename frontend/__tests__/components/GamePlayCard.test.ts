import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import GamePlayCard from "../../components/GamePlayCard";
import type { ActiveChartPoint } from "../../lib/types";

function makePoint(overrides: Partial<ActiveChartPoint> = {}): ActiveChartPoint {
  return {
    timestamp: "2026-06-15T20:09:00+00:00",
    homeProb: 0.62,
    awayProb: 0.38,
    homeScore: 101,
    awayScore: 98,
    period: "4",
    clock: "1:09",
    ...overrides,
  };
}

function render(point: ActiveChartPoint) {
  return renderToStaticMarkup(
    React.createElement(GamePlayCard, {
      activePoint: point,
      homeTeam: "Boston Celtics",
      awayTeam: "Oklahoma City Thunder",
    })
  );
}

/** Text inside the game-state badge (the bg-surface-secondary span). */
function badge(html: string): string | null {
  const m = html.match(/bg-surface-secondary[^>]*>([^<]*)</);
  return m ? m[1] : null;
}

describe("GamePlayCard scrub readout (#925)", () => {
  it("shows score, period+clock, and time-of-day together", () => {
    const html = render(makePoint());
    expect(html).toContain("101");
    expect(html).toContain("98");
    expect(badge(html)).toBe("Q4 1:09"); // period + exact clock
    expect(html).toMatch(/\d{1,2}:\d{2}\s?(AM|PM)/i); // time-of-day present
  });

  it("marks a forward-filled clock as approximate", () => {
    const html = render(makePoint({ clockApprox: true }));
    expect(badge(html)).toBe("Q4 ~1:09");
  });

  it('shows "—" for game state when clock and period are absent but a score exists', () => {
    const html = render(makePoint({ period: null, clock: null }));
    expect(badge(html)).toBe("—");
  });

  it("falls back to period when clock is absent (e.g. baseball innings)", () => {
    const html = render(
      makePoint({ period: "Top 8th", clock: null, homeScore: 11, awayScore: 2 })
    );
    expect(badge(html)).toBe("Top 8th"); // period only, no invented clock
  });
});
