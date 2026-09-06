// #3151 / #3111 — a chart never renders ONLY de-emphasised lines.
//
// LOOKED at production /events/15300276 (Jodar v Bu, US Open, FINAL) at 390px
// on 2026-09-06: the Win Probability card drew its axis, its y-labels, its
// gridlines, "Lead changes (6)" and the footer "5:03 PM · Jodar 1% — Bu 99%",
// and no curve. The route serves 559 Kalshi points spanning 0.01–0.93.
//
// The line was never missing. Read out of the production DOM, it was there and
// correct — an 852px path, green, inside the viewBox — at `stroke-width: 1` and
// `stroke-opacity: 0.28`, dashed. A 1px 28% hairline on a white card is not a
// line a reader can see.
//
// Cause: `isMultiSource` is `nonBettingSources.length > 0` — TRUE at one source
// — so a Kalshi-only match takes the blend-dominant branch, where sources are
// drawn faint on purpose because a 3px blend line is supposed to sit on top of
// them. `showBlendLine` also requires a backend `aggregate_line`, and a
// single-source match has none. Faint sources, no blend: nothing legible.
//
// The guard is the reader's property, not the constants: whatever the chart
// draws, SOMETHING on it has to be visible. Pinning 2.5/1.0 would go green on a
// restyle that reintroduced the blank plot at different numbers.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// recharts draws NOTHING inside a ResponsiveContainer without a viewport, so a
// test that rendered the component as-is would assert over an empty string and
// pass on both arms. Hand the chart real dimensions instead (the same reason
// `tennisScoreUnits.test.tsx` has to assert through wrapper attributes).
jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

import OddsChart from "@/components/OddsChart";

// Verbatim shape of the production payload for 15300276: one non-betting
// source, no sportsbook history, no backend blend. Twelve points is enough to
// stroke a path — the defect is the paint, not the count, so this fixture backs
// SHAPE and makes no claim about 559.
const START = Date.UTC(2026, 8, 2, 15, 56, 0); // fixed anchor — never Date.now()
const KALSHI = Array.from({ length: 12 }, (_, i) => ({
  timestamp: new Date(START + i * 60_000).toISOString(),
  home_probability: 0.3 + (i % 5) * 0.1,
  away_probability: 0.7 - (i % 5) * 0.1,
}));

interface DrawnLine {
  strokeWidth: number;
  strokeOpacity: number;
}

/** Every line recharts actually stroked, with the weight it stroked it at. */
function drawnLines(html: string): DrawnLine[] {
  const curves = html.match(/<path[^>]*recharts-line-curve[^>]*>/g) ?? [];
  return curves.map((tag) => ({
    strokeWidth: Number(/stroke-width="([^"]+)"/.exec(tag)?.[1] ?? "0"),
    // recharts omits the attribute entirely at full opacity.
    strokeOpacity: Number(/stroke-opacity="([^"]+)"/.exec(tag)?.[1] ?? "1"),
  }));
}

/** A line a reader can actually see on a white card. */
const isLegible = (l: DrawnLine) => l.strokeWidth >= 2 && l.strokeOpacity >= 0.8;

function renderChart(props: Record<string, unknown>) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Rafael Jodar"
      awayTeam="Yu Bu"
      commenceTime="2026-09-02T15:00:00+00:00"
      isLive={false}
      eventStatus="closed"
      externalTimeRange="all"
      {...props}
    />,
  );
}

describe("#3151/#3111 — the settled single-source chart draws a line you can see", () => {
  test("a lone Kalshi source with no backend blend is drawn at full weight", () => {
    const html = renderChart({
      winProbHistory: { kalshi: KALSHI },
      winProbSources: { kalshi: { display_name: "Kalshi", color: "#22c55e", type: "prediction_market" } },
    });

    const lines = drawnLines(html);
    // The rig has to actually draw something, or every assertion below is
    // vacuous — this is the half that would have hidden the bug.
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.some(isLegible)).toBe(true);
  });

  test("the control: with a backend blend, the sources stay faint under it", () => {
    // "The blend is the product" — a source line is de-emphasised precisely
    // because the blend dominates it. This arm fails if the fix above is
    // written as "always draw sources boldly".
    const html = renderChart({
      winProbHistory: {
        kalshi: KALSHI,
        espn: KALSHI.map((p) => ({ ...p, home_probability: p.home_probability - 0.05 })),
      },
      winProbSources: {
        kalshi: { display_name: "Kalshi", color: "#22c55e", type: "prediction_market" },
        espn: { display_name: "ESPN", color: "#f97316", type: "model" },
      },
      aggregateLine: KALSHI.map((p) => ({
        timestamp: p.timestamp,
        home_probability: p.home_probability,
      })),
    });

    const lines = drawnLines(html);
    expect(lines.some(isLegible)).toBe(true); // the blend itself
    // and at least one source is still drawn subordinate to it
    expect(lines.some((l) => !isLegible(l))).toBe(true);
  });
});
