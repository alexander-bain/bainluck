// #11929 — the game page's win-probability chart draws a solid line through
// unobserved time.
//
// ALEX'S RULING (2026-11-04 12:09 PT): "A solid line through unobserved time.
// A hole between two observations is drawn like any other segment of that
// line (the chart's normal interpolation): no bridge, no dotted treatment, no
// label, and the caption's 'No numbers for N hours' sentence goes with it —
// nothing on the chart calls the reader's attention to a gap." (11:38 AM:
// "never call the reader's attention to a gap — the gaps themselves are the
// bug.") This supersedes #7878's interior-hole contract in `OddsChart`, which
// lifted the pen at the hole's first reading, resumed at the next, laid a
// faint dashed `__gap` connector between them and put "no readings A – B" in
// the tooltip.
//
// THE CHART'S NORMAL INTERPOLATION, read off the component: every minute of
// the domain is a row, each observation series is forward-filled through the
// rows between two readings, and the `type="linear"` line joins consecutive
// rows. So between two readings the line holds the earlier value and steps to
// the later one on its own minute — and a hole now gets exactly that.
//
// THE RIGHT EDGE IS NOT AN INTERIOR GAP and keeps #7878's behaviour: a live
// line whose source stopped reporting ends on its last reading and says how
// old it is ("last reading … · none in the 45m since"; tooltip "last reading
// …, none since"). A finished game has no stale edge.
//
// Specimens are CONSTRUCTED (labelled) on a fixed anchor, shaped like the
// issue's: a live match with a 73-minute in-game hole (15315912's length), and
// a finished match with a 50-minute hole before its result. Rendered through
// the real component; the assertions read the SVG recharts emitted and drive
// the real configured tooltip.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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
// `mock`-prefixed so the jest.mock factory may close over it.
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
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import type { EventHistoryResponse, WinProbHistoryPoint } from "@/lib/types";

const realConsoleError = console.error;
beforeAll(() => {
  console.error = (...a: unknown[]) => {
    if (typeof a[0] === "string" && a[0].includes("useLayoutEffect does nothing on the server")) return;
    realConsoleError(...a);
  };
});
afterAll(() => {
  console.error = realConsoleError;
});

// ── SVG readers ─────────────────────────────────────────────────────────────

interface Curve {
  tag: string;
  d: string;
  stroke: string;
  dasharray: string | null;
  opacity: number;
}
function curves(html: string): Curve[] {
  return (html.match(/<path[^>]*recharts-line-curve[^>]*>/g) ?? []).map((tag) => ({
    tag,
    d: /\sd="([^"]*)"/.exec(tag)?.[1] ?? "",
    stroke: /stroke="([^"]+)"/.exec(tag)?.[1] ?? "",
    dasharray: /stroke-dasharray="([^"]+)"/.exec(tag)?.[1] ?? null,
    opacity: Number(/stroke-opacity="([^"]+)"/.exec(tag)?.[1] ?? "1"),
  }));
}
function subpaths(d: string): Array<Array<[number, number]>> {
  return d
    .split("M")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) =>
      (s.match(/-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?/g) ?? []).map((pair) => pair.split(",").map(Number) as [number, number]),
    );
}
/** Every sentence #11929 removes, in any of the shapes it has had. */
const HOLE_PROSE = /no readings|No numbers for|in this stretch/i;

// ── The specimens ───────────────────────────────────────────────────────────

const KALSHI = "#22c55e";
const POLY = "#3b82f6";
const SOURCES = {
  kalshi: { display_name: "Kalshi", color: KALSHI, type: "market" as const, dash_pattern: null, snapshot_count: 0 },
  polymarket: { display_name: "Polymarket", color: POLY, type: "market" as const, dash_pattern: null, snapshot_count: 0 },
};
const COMMENCE = Date.UTC(2026, 9, 18, 0, 0, 0); // fixed anchor — never Date.now()
const commenceIso = new Date(COMMENCE).toISOString();
const atMin = (m: number) => new Date(COMMENCE + m * 60_000 + 7_000).toISOString(); // :07 into the minute
const minuteOf = (iso: string) => Math.floor(Date.parse(iso) / 60_000);

function readings(fromMin: number, toMin: number, p: (m: number) => number): WinProbHistoryPoint[] {
  const out: WinProbHistoryPoint[] = [];
  for (let m = fromMin; m <= toMin; m++) {
    out.push({ timestamp: atMin(m), home_probability: p(m), away_probability: 1 - p(m) });
  }
  return out;
}

// Kalshi: a reading every minute 1–40, then NOTHING for 73 minutes (40 → 113),
// then every minute to 140. The price moved while nobody looked: 55% → 63%.
// Polymarket: every minute 1–140 except its own 30-minute hole (70 → 100).
const KALSHI_HOLE = { from: 40, to: 113 };
const POLY_HOLE = { from: 70, to: 100 };
const kalshiLive = [
  ...readings(1, KALSHI_HOLE.from, (m) => 0.5 + m * 0.00125),
  ...readings(KALSHI_HOLE.to, 140, (m) => 0.63 - (m - KALSHI_HOLE.to) * 0.001),
];
const polyLive = [
  ...readings(1, POLY_HOLE.from, () => 0.52),
  ...readings(POLY_HOLE.to, 140, () => 0.6),
];

interface Rendered {
  html: string;
  domain: NonNullable<ReturnType<typeof computeSharedChartDomain>>;
}
function renderGame(
  wph: Record<string, WinProbHistoryPoint[]>,
  opts: { status: string; isLive: boolean; completedAt?: string },
): Rendered {
  mockRecorded.tooltip = null;
  mockRecorded.data = [];
  const history = {
    event_id: 1,
    home_team: "Home",
    away_team: "Away",
    commence_time: commenceIso,
    status: opts.status,
    history: [],
    win_prob_history: wph,
    win_prob_sources: SOURCES,
  } as unknown as EventHistoryResponse;
  const domain = computeSharedChartDomain(history, "live", opts.status, commenceIso, "tennis_wta");
  expect(domain).not.toBeNull();
  const html = renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Home"
      awayTeam="Away"
      isLive={opts.isLive}
      eventStatus={opts.status}
      completedAt={opts.completedAt}
      commenceTime={commenceIso}
      winProbHistory={wph}
      winProbSources={SOURCES}
      externalTimeRange="live"
      chartStartTime={domain!.start}
      chartEndTime={domain!.end}
      sharedTicks={domain!.ticks}
      chartLabelFormat={domain!.labelFormat}
      defaultSourcesExpanded
    />,
  );
  return { html, domain: domain! };
}

/** Drive the real CustomTooltip at the chart's own row for `iso`'s minute. */
function cardAt(iso: string, key: string, name: string, color: string): string {
  const row = mockRecorded.data.find((d) => minuteOf(d.timestamp) === minuteOf(iso));
  expect(row).toBeDefined();
  const v = row![key];
  const content = mockRecorded.tooltip?.content as React.ReactElement;
  expect(React.isValidElement(content)).toBe(true);
  return renderToStaticMarkup(
    React.cloneElement(content, {
      active: true,
      label: row!.time,
      payload: [{ value: typeof v === "number" ? v : null, name, color, dataKey: key }],
    }),
  );
}

/**
 * The line for `color` (dataKey `key`) is ONE pen-down with a vertex at every
 * row that holds a value — consecutive vertices one category apart, so no
 * minute between its first and last is skipped — carried flat through the
 * hole and stepping to the far reading on that reading's own minute. Vertex
 * i is the i-th valued row of the chart's own data.
 */
function expectOneLineThroughTheHole(html: string, color: string, key: string, hole: { from: number; to: number }) {
  const line = curves(html).filter((c) => c.stroke === color);
  expect(line).toHaveLength(1);
  const runs = subpaths(line[0].d);
  expect(runs).toHaveLength(1);
  const run = runs[0];
  const step = run[1][0] - run[0][0];
  for (let i = 1; i < run.length; i++) expect(Math.abs(run[i][0] - run[i - 1][0] - step)).toBeLessThan(0.01);
  const valued = mockRecorded.data.filter((d) => typeof d[key] === "number");
  expect(valued).toHaveLength(run.length);
  const idx = (m: number) => valued.findIndex((d) => minuteOf(d.timestamp) === minuteOf(atMin(m)));
  const i0 = idx(hole.from);
  const i1 = idx(hole.to);
  expect(i0).toBeGreaterThan(0);
  expect(i1 - i0).toBe(hole.to - hole.from);
  for (let i = i0; i < i1; i++) {
    expect(run[i][1]).toBe(run[i0][1]);
    expect(valued[i][key]).toBe(valued[i0][key]);
  }
  // The far reading is a different (higher) price, reached on its minute.
  expect(run[i1][1]).toBeLessThan(run[i0][1]);
}

function expectNoGapTreatment(html: string) {
  for (const c of curves(html)) {
    // The sources keep their own registry dash ("8 4"); #7878's connector was "2 5".
    expect(c.dasharray).not.toBe("2 5");
    expect(c.tag).not.toContain("recharts-gap-connector");
  }
  expect(html).not.toContain("__gap");
  expect(html).not.toMatch(HOLE_PROSE);
}

// ── The live game ───────────────────────────────────────────────────────────

describe("#11929 — a live game with a 73-minute interior hole", () => {
  // The backend's synthetic live edge, 30 s after the last reading (#920): the
  // series reaches the right edge, so there is no stale edge.
  const live = {
    kalshi: [...kalshiLive, { ...readings(140, 140, () => 0.603)[0], timestamp: new Date(COMMENCE + 140 * 60_000 + 37_000).toISOString(), live_edge: true }],
    polymarket: polyLive,
  };

  test("each line is ONE path through every observation, carried across its hole, with no connector, dash or label", () => {
    const { html } = renderGame(live, { status: "live", isLive: true });
    expect(curves(html)).toHaveLength(2); // one per source — no third, connector path
    expectOneLineThroughTheHole(html, KALSHI, "wp_kalshi_delta", KALSHI_HOLE);
    expectOneLineThroughTheHole(html, POLY, "wp_polymarket_delta", POLY_HOLE);
    expectNoGapTreatment(html);
    expect(html).not.toContain('data-testid="chart-stale-edges"');
  });

  test("the tooltip inside the hole quotes the carried price and says nothing about the stretch", () => {
    renderGame(live, { status: "live", isLive: true });
    const inHole = atMin(KALSHI_HOLE.from + 36);
    const html = cardAt(inHole, "wp_kalshi_delta", "Kalshi", KALSHI);
    expect(html).toMatch(/\d+(\.\d+)?%/);
    expect(html).not.toContain("chart-gap-note");
    expect(html).not.toMatch(HOLE_PROSE);
    expect(html).not.toMatch(/none since/);
  });
});

describe("#11929 — the right edge is not a gap: a live line that went quiet keeps its stale-edge statement", () => {
  // Same game, but Kalshi's readings stop at minute 95 while the live edge is
  // at 140 — a TRAILING interval, not an interior one. Polymarket keeps its
  // interior hole, so both rules are proven on one chart.
  const kalshiQuiet = readings(1, 95, (m) => 0.5 + m * 0.001);
  const quiet = {
    kalshi: [...kalshiQuiet, { ...kalshiQuiet[kalshiQuiet.length - 1], timestamp: new Date(COMMENCE + 140 * 60_000 + 37_000).toISOString(), live_edge: true }],
    polymarket: polyLive,
  };

  test("the quiet line ends ON its last reading and the caption says how old it is; the other line still runs through its hole", () => {
    const { html } = renderGame(quiet, { status: "live", isLive: true });
    const k = curves(html).filter((c) => c.stroke === KALSHI);
    expect(k).toHaveLength(1);
    const kRuns = subpaths(k[0].d);
    expect(kRuns).toHaveLength(1);
    const p = curves(html).find((c) => c.stroke === POLY)!;
    const pMaxX = Math.max(...subpaths(p.d)[0].map((v) => v[0]));
    const kMaxX = Math.max(...kRuns[0].map((v) => v[0]));
    // 45 of ~140 minutes short of the right edge.
    expect(pMaxX - kMaxX).toBeGreaterThan(390 * 0.2);
    expectOneLineThroughTheHole(html, POLY, "wp_polymarket_delta", POLY_HOLE);
    expect(html).toContain('data-testid="chart-stale-edges"');
    expect(html).toMatch(/Kalshi<\/span> last reading .+ · none in the 45m since/);
    expectNoGapTreatment(html);
  });

  test("past the edge the tooltip says 'last reading …, none since' and quotes no price", () => {
    renderGame(quiet, { status: "live", isLive: true });
    const html = cardAt(atMin(120), "wp_kalshi_delta", "Kalshi", KALSHI);
    expect(html).toMatch(/last reading .+, none since/);
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
    expect(html).not.toMatch(HOLE_PROSE);
  });
});

// ── The finished game ───────────────────────────────────────────────────────

describe("#11929 — a finished game with an interior hole before its result", () => {
  // Readings every minute 1–60, nothing for 50 minutes, readings 110–150, then
  // the backend's terminal row and the result (`final`, home wins).
  const settledKalshi: WinProbHistoryPoint[] = [
    ...readings(1, 60, (m) => 0.5 + m * 0.002),
    ...readings(110, 150, (m) => 0.8 + (m - 110) * 0.004),
    { timestamp: atMin(151), home_probability: 1, away_probability: 0, game_state: { final: true } },
  ];
  const completedAt = new Date(COMMENCE + 151 * 60_000 + 30_000).toISOString();

  test("one path through every observation to the result, no connector, no caption, no tooltip note", () => {
    const { html } = renderGame({ kalshi: settledKalshi }, { status: "completed", isLive: false, completedAt });
    const k = curves(html).filter((c) => c.stroke === KALSHI);
    expect(k).toHaveLength(1);
    expect(curves(html)).toHaveLength(1);
    expectOneLineThroughTheHole(html, KALSHI, "wp_kalshi_delta", { from: 60, to: 110 });
    // The line ends on the result: the top of the plot, at its right-most vertex.
    const run = subpaths(k[0].d)[0];
    const last = run[run.length - 1];
    expect(last[1]).toBe(Math.min(...run.map((v) => v[1])));
    expectNoGapTreatment(html);
    expect(html).not.toContain('data-testid="chart-stale-edges"');
    const card = cardAt(atMin(85), "wp_kalshi_delta", "Kalshi", KALSHI);
    expect(card).toMatch(/\d+(\.\d+)?%/);
    expect(card).not.toMatch(HOLE_PROSE);
    expect(card).not.toMatch(/none since/);
  });
});
