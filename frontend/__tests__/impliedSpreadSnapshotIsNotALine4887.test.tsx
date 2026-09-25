/**
 * #4887 (D123, Alex): a venue's implied margin is one current reading. It is
 * not drawn as a flat line across the game, and it is hidden until the reader
 * asks for it through the "+ N sources" press.
 *
 * Seen on production 2026-09-25 22:40Z, `/events/15318545` (Cubs @ Red Sox,
 * live, 0–0 in the 4th), 390px: the Score Differential card's only forecast
 * series was a purple dashed "Kalshi Implied" flat at Red Sox +1.2 from 2:40 PM
 * to now. `pm_spread_data.implied_spreads` carries no history — the served
 * Kalshi arm read `home_margin -0.2` a few minutes later — so every point but
 * the last asserted a reading we never took.
 *
 * recharts draws nothing inside `ResponsiveContainer` in a server render, so
 * the drawn set is read off the wrapper attributes (#6142's reason), and the
 * one-point placement is asserted on the helper the chart build calls.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { stampImpliedSpreadSnapshot } from "@/lib/impliedSpreadAxis";

const LIVE = JSON.parse(
  readFileSync(join(__dirname, "fixtures/impliedSpread.14780544.live.json"), "utf8")
);

/** The Kalshi arm served for 15318545 at 2026-09-25 ~22:45Z, verbatim. */
const RED_SOX_KALSHI = {
  spread: 0.2,
  home_margin: -0.2,
  confidence: 0.85,
  contracts: [
    { threshold: -3.5, probability: 0.89 },
    { threshold: -2.5, probability: 0.79 },
    { threshold: -1.5, probability: 0.69 },
    { threshold: 1.5, probability: 0.24 },
    { threshold: 2.5, probability: 0.15 },
    { threshold: 3.5, probability: 0.07 },
  ],
};

function attr(markup: string, name: string): string | null {
  const m = markup.match(new RegExp(`${name}="([^"]*)"`));
  return m ? m[1] : null;
}

function renderChart(wire: Record<string, unknown>, status?: string): string {
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: wire.history as never,
      homeTeam: wire.home_team as string,
      awayTeam: wire.away_team as string,
      commenceTime: wire.commence_time as string,
      scoreHistory: wire.score_history as never,
      eventStatus: status ?? (wire.status as string),
      sportKey: "americanfootball_nfl",
      pmSpreadData: wire.pm_spread_data as never,
    } as never)
  );
}

function points(n: number): Array<Record<string, unknown>> {
  return Array.from({ length: n }, (_, i) => ({
    timestamp: new Date(Date.UTC(2026, 8, 25, 21, 30 + i)).toISOString(),
    actualDiff: 0,
  }));
}

describe("#4887 — the chart hides the venues' snapshot until asked", () => {
  it("strawman: the live fixture still carries an arm the chart would draw", () => {
    // Without an eligible arm every assertion below is vacuous.
    expect(LIVE.status).toBe("live");
    expect(attr(renderChart(LIVE), "data-implied-spread-series")).toBe("polymarket");
  });

  it("THE SHIP: by default no venue snapshot is on the plot", () => {
    expect(attr(renderChart(LIVE), "data-implied-spread-drawn")).toBe("none");
  });

  it("and the press that reveals it is there, collapsed, counting what it holds", () => {
    const markup = renderChart(LIVE);
    expect(markup).toMatch(/<button[^>]*aria-expanded="false"[^>]*>\+ 1 source<svg/);
    // The rest of the card is intact — not an error stub passing for the wrong reason.
    expect(attr(markup, "data-actual-series")).toBe("true");
    expect(markup).not.toContain("Score data is not available");
  });

  it("a finished game offers no press — #6142 withholds every arm there", () => {
    const markup = renderChart(LIVE, "completed");
    expect(attr(markup, "data-implied-spread-series")).toBe("none");
    expect(markup).not.toMatch(/\+ \d+ sources?<svg/);
  });
});

describe("#4887 — a snapshot is one point, not a line", () => {
  it("stamps the reading on the LAST point only", () => {
    const pts = points(60);
    stampImpliedSpreadSnapshot(pts, { kalshi: RED_SOX_KALSHI }, ["kalshi"]);
    const carrying = pts
      .map((p, i) => (typeof p.pm_kalshi_spread === "number" ? i : -1))
      .filter((i) => i >= 0);
    expect(carrying).toEqual([59]);
  });

  it("on the home-margin axis, never the betting-line sign (#3948)", () => {
    const pts = points(3);
    stampImpliedSpreadSnapshot(pts, { kalshi: RED_SOX_KALSHI }, ["kalshi"]);
    expect(pts[2].pm_kalshi_spread).toBe(-0.2);
  });

  it("only the sources it is handed — the eligibility rule stays upstream", () => {
    const pts = points(3);
    stampImpliedSpreadSnapshot(
      pts,
      { kalshi: RED_SOX_KALSHI, polymarket: { spread: -6.7, home_margin: 6.7, confidence: 0.97 } },
      ["polymarket"]
    );
    expect(pts[2].pm_kalshi_spread).toBeUndefined();
    expect(pts[2].pm_polymarket_spread).toBe(6.7);
  });

  it("an empty domain stamps nothing and does not throw", () => {
    const pts: Array<Record<string, unknown>> = [];
    stampImpliedSpreadSnapshot(pts, { kalshi: RED_SOX_KALSHI }, ["kalshi"]);
    expect(pts).toEqual([]);
  });

  it("the chart build calls the stamp and no longer paints every point", () => {
    // The chart's data build is not exported; this pins the call site so the
    // helper above cannot be tested green while the chart goes around it.
    const src = readFileSync(
      join(__dirname, "../components/ScoreDifferentialChart.tsx"),
      "utf8"
    );
    expect(src).toContain(
      "stampImpliedSpreadSnapshot(points, pmSpreadData?.implied_spreads, impliedSpreadSources);"
    );
    expect(src).not.toMatch(/pt\[key\]\s*=\s*impliedSpreadHomeMargin/);
    expect(src).not.toMatch(/dataKey="pm_(kalshi|polymarket)_spread"[\s\S]{0,200}connectNulls/);
  });
});
