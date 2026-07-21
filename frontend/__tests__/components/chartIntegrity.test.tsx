// CHART-INTEGRITY guard (#L2-137 chart-excellence Phase 0). The "Path to
// resolution" regression shipped a chart with no readable axis labels, no
// legend, and no time-range control. This test is the self-filing tripwire for
// that class: if the probability-path chart loses its axis labels, its legend,
// or its range chips, CI fails. Runs in the node/SSR env (renderToStaticMarkup)
// — no jsdom, no SWR.

import { renderToStaticMarkup } from "react-dom/server";
import React from "react";
import { FuturesChart } from "../../components/FuturesChart";
import ChartRangeChips from "../../components/event/ChartRangeChips";
import {
  CHART_RANGES,
  availableRanges,
  windowOutcomeHistory,
  latestSnapshotTime,
} from "../../lib/chartWindow";
import type { FuturesOutcomeHistory } from "../../lib/types";

const DAY = 24 * 60 * 60 * 1000;
const END = Date.UTC(2026, 6, 20, 18, 0, 0); // fixed anchor — never Date.now()

// Two contenders whose paths span ~40 days then spike at resolution.
const OUTCOMES: FuturesOutcomeHistory[] = [
  {
    outcome_id: 1,
    name: "Scottie Scheffler",
    history: [
      { timestamp: new Date(END - 40 * DAY).toISOString(), probability: 0.2, american_odds: null, bookmaker: "blend" },
      { timestamp: new Date(END - 7 * DAY).toISOString(), probability: 0.35, american_odds: null, bookmaker: "blend" },
      { timestamp: new Date(END - 2 * DAY).toISOString(), probability: 0.6, american_odds: null, bookmaker: "blend" },
      { timestamp: new Date(END).toISOString(), probability: 1.0, american_odds: null, bookmaker: "blend" },
    ],
  },
  {
    outcome_id: 2,
    name: "Rory McIlroy",
    history: [
      { timestamp: new Date(END - 40 * DAY).toISOString(), probability: 0.18, american_odds: null, bookmaker: "blend" },
      { timestamp: new Date(END - 7 * DAY).toISOString(), probability: 0.22, american_odds: null, bookmaker: "blend" },
      { timestamp: new Date(END - 2 * DAY).toISOString(), probability: 0.1, american_odds: null, bookmaker: "blend" },
      { timestamp: new Date(END).toISOString(), probability: 0.0, american_odds: null, bookmaker: "blend" },
    ],
  },
];

describe("FuturesChart integrity — axes + legend", () => {
  test("renders y-axis percent labels when showAxes", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={OUTCOMES} fixedYAxis stepInterpolation showAxes showLegend />,
    );
    expect(html).toContain("0%");
    expect(html).toContain("50%");
    expect(html).toContain("100%");
  });

  test("renders a static legend naming each line when no toggle handler", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={OUTCOMES} fixedYAxis stepInterpolation showAxes showLegend />,
    );
    expect(html).toContain('aria-label="Chart legend"');
    expect(html).toContain("Scottie Scheffler");
    expect(html).toContain("Rory McIlroy");
  });

  test("draws a line path for each contender", () => {
    const html = renderToStaticMarkup(
      <FuturesChart historyData={OUTCOMES} fixedYAxis stepInterpolation showAxes showLegend />,
    );
    // Two <path d="..."> line elements (one per outcome).
    expect((html.match(/<path/g) || []).length).toBeGreaterThanOrEqual(2);
  });
});

describe("ChartRangeChips integrity — controls present", () => {
  test("renders the range buttons", () => {
    const ranges = availableRanges(OUTCOMES, false);
    const html = renderToStaticMarkup(
      <ChartRangeChips ranges={ranges} selected="all" onSelect={() => {}} />,
    );
    expect(html).toContain('aria-label="Chart time range"');
    expect(html).toContain(">All<");
    // ~40-day span → 1W and 1D chips are meaningful; 1M is dropped (span < 1M).
    expect(html).toContain(">1W<");
    expect(html).toContain(">1D<");
  });

  test("marks the selected range pressed", () => {
    const ranges = availableRanges(OUTCOMES, false);
    const html = renderToStaticMarkup(
      <ChartRangeChips ranges={ranges} selected="1W" onSelect={() => {}} />,
    );
    expect(html).toContain('aria-pressed="true"');
  });

  test("hides itself when only one range is available", () => {
    const html = renderToStaticMarkup(
      <ChartRangeChips ranges={[CHART_RANGES[0]]} selected="all" onSelect={() => {}} />,
    );
    expect(html).toBe("");
  });
});

describe("windowOutcomeHistory — zoom to the resolution spike", () => {
  test("'all' is a passthrough", () => {
    expect(windowOutcomeHistory(OUTCOMES, "all")).toBe(OUTCOMES);
  });

  test("'1D' clips to the last day and carries the pre-window value forward", () => {
    const windowed = windowOutcomeHistory(OUTCOMES, "1D");
    const scheffler = windowed[0];
    const times = scheffler.history.map((p) => new Date(p.timestamp).getTime());
    // Anchored to the last snapshot, not now — the window is [END-1D, END].
    for (const t of times) expect(t).toBeGreaterThanOrEqual(END - DAY - 1);
    // A carried anchor point sits exactly at the window start.
    expect(times[0]).toBe(END - DAY);
    // Still at least 2 points so the line renders.
    expect(scheffler.history.length).toBeGreaterThanOrEqual(2);
  });

  test("'since_start' with no start is a passthrough", () => {
    expect(windowOutcomeHistory(OUTCOMES, "since_start")).toBe(OUTCOMES);
  });

  test("'since_start' clips to the event start when provided", () => {
    const startMs = END - 10 * DAY;
    const windowed = windowOutcomeHistory(OUTCOMES, "since_start", startMs);
    for (const p of windowed[0].history) {
      expect(new Date(p.timestamp).getTime()).toBeGreaterThanOrEqual(startMs);
    }
  });

  test("availableRanges offers since_start only when an event exists", () => {
    expect(availableRanges(OUTCOMES, false).some((r) => r.key === "since_start")).toBe(false);
    expect(availableRanges(OUTCOMES, true).some((r) => r.key === "since_start")).toBe(true);
  });

  test("latestSnapshotTime finds the resolution timestamp", () => {
    expect(latestSnapshotTime(OUTCOMES)).toBe(END);
  });
});
