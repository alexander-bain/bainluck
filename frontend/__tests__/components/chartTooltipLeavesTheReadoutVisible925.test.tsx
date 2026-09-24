/**
 * #925 — AT PHONE WIDTH THE WIN-PROBABILITY TOOLTIP COVERED THE READOUT UNDER THE CHART.
 *
 * Codex's production acceptance of #925's carried-age clause (2026-09-24 17:11Z,
 * `artifacts/chart-sprint-coordinator/20260924T1702-finish-audit/925-carried-390.png`)
 * held the chart on /events/14781697 (Cowboys 37–20 Commanders) at 390px and
 * recorded: "Current tooltip overlays much of the prominent card at 390px". The
 * picture shows why. Every source line — `Dallas Cowboys: 65.0% | Washington
 * Commanders: 35.0%` — wrapped to two rows under its own name row, so five
 * sources plus the blend made a card ~450px tall against a ~300px plot. Recharts
 * pins a card taller than the plot to the plot's top, so the tail hung below the
 * chart, over the readout the page prints there, which read "~0:12 - 2n…" with its
 * score, numbers and "as of 2:48 PM" line behind the card.
 *
 * The fix makes the rows shorter rather than moving the card (it was taller than
 * the space, so no position helps): under `CHART_TOOLTIP_COMPACT_MEDIA_QUERY` the
 * probabilities print as a table, one row per source and one column per team.
 *
 * Guards run both directions (gotcha #43): the phone card is the table, and the
 * wide card is the old line form, unchanged.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

interface TooltipProps {
  content?: React.ReactElement;
}
interface ChartDatum {
  time: string;
  timestamp: string;
  [key: string]: unknown;
}

const mockRecorded: { tooltip: TooltipProps | null; data: ChartDatum[] } = { tooltip: null, data: [] };

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  const react = jest.requireActual("react") as typeof React;
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      react.cloneElement(children, { width: 390, height: 300 }),
    ComposedChart: (props: { data?: ChartDatum[] }) => {
      if (props.data) mockRecorded.data = props.data;
      return react.createElement(actual.ComposedChart, props);
    },
    Tooltip: (props: TooltipProps) => {
      mockRecorded.tooltip = props;
      return react.createElement(actual.Tooltip, props);
    },
  };
});

import OddsChart from "@/components/OddsChart";
import { CHART_TOOLTIP_COMPACT_MEDIA_QUERY } from "@/lib/chartTooltipViewportFit";
import { chartTooltipCells, chartTooltipPair } from "@/lib/drawPricedWinner";
import type { EventHistoryResponse } from "@/lib/types";

const SPECIMEN: EventHistoryResponse & { status: string; commence_time: string } = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "event-15315912-history-7878.json"), "utf8"),
);
const KALSHI = SPECIMEN.win_prob_history!.kalshi!;
// A second source, so the card has more than one row to lay out.
const POLYMARKET = KALSHI.map((p) => ({
  ...p,
  home_probability: (p.home_probability as number) + 0.02,
  away_probability: (p.away_probability as number) - 0.02,
}));
const SOURCES = {
  kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market" as const, dash_pattern: "8 4", snapshot_count: 0 },
  polymarket: { display_name: "Polymarket", color: "#3b82f6", type: "market" as const, dash_pattern: "4 2", snapshot_count: 0 },
};

/**
 * This suite runs in jest's `node` environment (no jsdom is installed), so there
 * is no `window` unless one is put there. A bare object carrying only
 * `matchMedia` is enough: the chart reads nothing else off `window` while
 * rendering, and recharts decides it is server-side from `window.document`,
 * which stays absent.
 */
const g = globalThis as { window?: unknown };
function setViewport(compact: boolean | null) {
  if (compact === null) {
    // No `window` at all — the server render, and the chart's own default.
    delete g.window;
    return;
  }
  g.window = {
    matchMedia: (query: string) => ({
      matches: compact && query === CHART_TOOLTIP_COMPACT_MEDIA_QUERY,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  };
}

function renderCard(opts: { compact: boolean | null; awayWithheld?: boolean }): string {
  setViewport(opts.compact);
  mockRecorded.tooltip = null;
  mockRecorded.data = [];
  renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Dallas Cowboys"
      awayTeam="Washington Commanders"
      isLive={false}
      winProbSources={SOURCES}
      winProbHistory={{ kalshi: KALSHI, polymarket: POLYMARKET }}
      commenceTime={SPECIMEN.commence_time}
      eventStatus={SPECIMEN.status}
      awayWithheld={opts.awayWithheld ?? false}
    />,
  );
  const point = mockRecorded.data.find((d) => d.wp_kalshi_delta != null && d.wp_polymarket_delta != null);
  expect(point).toBeDefined();
  const payload = [
    { value: point!.wp_kalshi_delta as number, name: "Kalshi", color: "#22c55e", dataKey: "wp_kalshi_delta" },
    { value: point!.wp_polymarket_delta as number, name: "Polymarket", color: "#3b82f6", dataKey: "wp_polymarket_delta" },
  ];
  // Cast: TS narrows the field to `null` from the reset above; the render set it.
  const content = (mockRecorded.tooltip as TooltipProps | null)?.content;
  expect(React.isValidElement(content)).toBe(true);
  return renderToStaticMarkup(
    React.cloneElement(content as React.ReactElement, { active: true, payload, label: point!.time }),
  );
}

/** The two numbers the card must print for a source at this point, by the shared rule. */
function expectedCells(dataKey: string, awayWithheld = false) {
  const point = mockRecorded.data.find((d) => d.wp_kalshi_delta != null && d.wp_polymarket_delta != null)!;
  return chartTooltipCells(point[dataKey] as number, awayWithheld);
}

const realConsoleError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].includes("useLayoutEffect does nothing on the server")) return;
    realConsoleError(...args);
  };
});
afterAll(() => {
  console.error = realConsoleError;
  delete g.window;
});

describe("#925 — at phone width the tooltip is a table, so it fits inside the plot", () => {
  test("phone width: one table row per source, both teams as column heads, no wrapped sentences", () => {
    const html = renderCard({ compact: true });
    expect(html).toContain('data-testid="chart-tooltip-table"');
    expect(html).toContain("grid-cols-[1fr_auto_auto]");
    // Column heads are the short names, printed once for the whole card.
    expect(html).toContain(">Cowboys</span>");
    expect(html).toContain(">Commanders</span>");
    // Each source is a name cell followed directly by its two number cells.
    for (const [name, key] of [["Kalshi", "wp_kalshi_delta"], ["Polymarket", "wp_polymarket_delta"]] as const) {
      const cells = expectedCells(key);
      const row = new RegExp(
        `>${name}</span><span[^>]*>${cells.home.replace(".", "\\.")}</span><span[^>]*>${cells.away!.replace(".", "\\.")}</span>`,
      );
      expect(html).toMatch(row);
    }
    // The sentence form is what wrapped; it must not also be printed.
    expect(html).not.toContain("Dallas Cowboys:");
    expect(html).not.toContain("Sources:");
  });

  test("wide viewport: the card is the old line form, unchanged", () => {
    const html = renderCard({ compact: false });
    expect(html).not.toContain("chart-tooltip-table");
    const kalshi = expectedCells("wp_kalshi_delta");
    expect(html).toContain(`Dallas Cowboys: ${kalshi.home} | Washington Commanders: ${kalshi.away}`);
    expect(html).toContain("Sources:");
  });

  test("no window (the server render): the line form, never the table", () => {
    const html = renderCard({ compact: null });
    expect(html).not.toContain("chart-tooltip-table");
    expect(html).toContain("Dallas Cowboys: ");
  });

  test("a withheld away side drops its whole column at phone width — header and cells", () => {
    const html = renderCard({ compact: true, awayWithheld: true });
    expect(html).toContain("grid-cols-[1fr_auto]");
    expect(html).not.toContain("grid-cols-[1fr_auto_auto]");
    expect(html).not.toContain(">Commanders</span>");
    const kalshi = expectedCells("wp_kalshi_delta", true);
    expect(kalshi.away).toBeNull();
    const complement = chartTooltipCells(
      mockRecorded.data.find((d) => d.wp_kalshi_delta != null && d.wp_polymarket_delta != null)!.wp_kalshi_delta as number,
      false,
    ).away!;
    expect(html).not.toContain(`>${complement}</span>`);
    expect(html).toContain(`>${kalshi.home}</span>`);
  });
});

describe("#925 — one rule for the numbers, one breakpoint for the layout", () => {
  test("the table cells and the line form round and withhold identically", () => {
    for (const p of [0, 0.04, 12.35, 49.95, 50, 57.49999999999999, 99.96, 100]) {
      const c = chartTooltipCells(p, false);
      expect(chartTooltipPair("H", p, "A", false)).toBe(`H: ${c.home} | A: ${c.away}`);
      expect(chartTooltipPair("H", p, "A", true)).toBe(`H: ${chartTooltipCells(p, true).home}`);
      expect(chartTooltipCells(p, true).away).toBeNull();
    }
  });

  test("the breakpoint is where the #1833 width cap starts to bind — min(24rem, 100vw - 7rem)", () => {
    // 24rem = 384px and 7rem = 112px at the 16px root: the cap binds below 496px.
    const src = readFileSync(join(__dirname, "..", "..", "components", "OddsChart.tsx"), "utf8");
    expect(src).toContain("max-w-[min(24rem,calc(100vw_-_7rem))]");
    const m = CHART_TOOLTIP_COMPACT_MEDIA_QUERY.match(/^\(max-width: (\d+)px\)$/);
    expect(m).not.toBeNull();
    expect(Number(m![1]) + 1).toBe(24 * 16 + 7 * 16);
  });
});
