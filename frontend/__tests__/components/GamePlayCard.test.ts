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

/**
 * live/055 (#2815) — the settled footer said the state twice.
 *
 * Production event 15293206 (Red Sox 3 – 8 Mariners, 2026-09-02) ships
 * `period: "Final"` alongside `game_clock: "Final"`, and this card joined the
 * two raw: **"Final Final  3 - 8"**. The values below are that payload, read
 * from `GET /api/events/15293206/history` — not an invented shape.
 *
 * BOTH ARMS, per gotcha #43. A fix that simply dropped the clock whenever the
 * period was present would pass the first test here and silently delete the
 * real clock every in-progress game depends on, so the second and third tests
 * are the ones with something to lose.
 */
describe("GamePlayCard settled state is not printed twice (#2815)", () => {
  it("prints the state once when period and clock carry the same word", () => {
    const html = render(
      makePoint({ period: "Final", clock: "Final", homeScore: 3, awayScore: 8 })
    );
    expect(badge(html)).toBe("Final");
    expect(html).not.toContain("Final Final");
  });

  it("is case-insensitive about the repeat", () => {
    const html = render(makePoint({ period: "Final", clock: "final" }));
    expect(badge(html)).toBe("Final");
  });

  // CONTROL — a clock that says something the period does not must survive.
  it("keeps a distinct non-clock-shaped clock beside the period", () => {
    const html = render(makePoint({ period: "Top 8th", clock: "2 out" }));
    expect(badge(html)).toBe("Top 8th 2 out");
  });

  // CONTROL — the ordinary in-game case, unchanged by adopting the authority.
  it("keeps a distinct clock-shaped clock beside the period", () => {
    const html = render(makePoint({ period: "4", clock: "1:09" }));
    expect(badge(html)).toBe("Q4 1:09");
  });

  // The authority's rule 2, which this card had never had: ESPN's basketball
  // detail spells the clock inside the period, so joining them duplicated it.
  it("drops a clock already spelled inside the period", () => {
    const html = render(makePoint({ period: "10:00 - 1st Quarter", clock: "10:00" }));
    expect(badge(html)).toBe("10:00 - 1st Quarter");
  });
});
