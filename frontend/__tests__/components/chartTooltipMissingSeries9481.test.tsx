import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));
type Entry = { dataKey: string; value?: number | null; name: string; color: string };
const mockRecorded: { content: React.ReactElement | null; data: Array<Record<string, unknown>> } = { content: null, data: [] };
jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  const react = jest.requireActual("react") as typeof React;
  return { ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) => react.cloneElement(children, { width: 1000, height: 300 }),
    ComposedChart: (props: { data: Array<Record<string, unknown>> }) => {
      mockRecorded.data = props.data;
      return react.createElement(actual.ComposedChart, props);
    },
    Tooltip: (props: { content: React.ReactElement }) => {
      mockRecorded.content = props.content;
      return react.createElement(actual.Tooltip, props);
    },
  };
});
import OddsChart from "@/components/OddsChart";

const early = "2026-09-22T08:29:00Z";
const later = "2026-09-28T22:44:00Z";
const row = (timestamp: string, p: number) => ({ timestamp, home_probability: p, away_probability: 1 - p, over_under: null, projected_home_score: null, projected_away_score: null, bookmaker: "consensus" });
const entry = (dataKey: string, value?: number | null): Entry => ({ dataKey, value, name: dataKey, color: "#123456" });
function card(payload: Entry[], compact = false, booksOnly = false): string {
  const g = globalThis as { window?: unknown };
  g.window = { matchMedia: () => ({ matches: compact, addEventListener() {}, removeEventListener() {} }) };
  try {
    renderToStaticMarkup(<OddsChart history={[row(early, 0.3962), row(later, 0.4)]}
      homeTeam="Chicago Bears" awayTeam="Philadelphia Eagles" eventStatus="scheduled"
      commenceTime="2026-09-29T00:15:00Z" isLive={false}
      winProbHistory={booksOnly ? undefined : { kalshi: [row(later, 0.4)], polymarket: [row(later, 0.4)] }}
      aggregateLine={booksOnly ? undefined : [row(early, 0.3962), row(later, 0.4)]} backendBlendServed={!booksOnly}
    />);
    const point = mockRecorded.data.find(p => p.timestamp === "2026-09-22T08:29:00.000Z");
    expect(point).toBeDefined();
    // A source exists later but has no reading at this early bucket.
    // Recharts filterNull=false can deliver either null or undefined entries.
    if (!booksOnly) expect(point!.wp_kalshi_delta == null).toBe(true);
    return renderToStaticMarkup(React.cloneElement(mockRecorded.content!, { active: true, payload, label: point!.time }));
  } finally { delete g.window; }
}

describe("#9481 a missing source point must not destroy the chart", () => {
  test.each([false, true])("early missing venue reads are absent, while real books/blend remain (compact=%s)", compact => {
    const html = card([entry("bainLuckDelta", 39.62), entry("homeDelta", 39.62), entry("wp_kalshi_delta"), entry("wp_polymarket_delta")], compact);
    expect(html).toContain("39.6%");
    expect(html).toContain("60.4%");
    expect(html).not.toContain("Kalshi");
    expect(html).not.toContain("Polymarket");
    expect(html).not.toContain("NaN");
  });
  test.each([undefined, null, NaN, Infinity, -Infinity])("invalid entries never reach number formatting: %s", value => {
    const html = card([entry("bainLuckDelta", value), entry("homeDelta", 40), entry("wp_kalshi_delta", value)]);
    expect(html).toContain("40.0%");
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("Infinity");
  });
  test("a sparse individual bookmaker entry is absent too", () => {
    const html = card([entry("homeDelta", 40), entry("fanduel_delta"), entry("draftkings_delta", 40)], false, true);
    expect(html).toContain("40.0%");
    expect(html).not.toContain("NaN");
  });
  test.each([0, 100])("legitimate endpoint %s survives filtering", value => {
    const html = card([entry("bainLuckDelta", value), entry("homeDelta", value), entry("wp_kalshi_delta", value)]);
    expect(html).toContain(`${value.toFixed(1)}%`);
    expect(html).toContain(`${(100 - value).toFixed(1)}%`);
    expect(html).toContain("Kalshi");
  });
});
