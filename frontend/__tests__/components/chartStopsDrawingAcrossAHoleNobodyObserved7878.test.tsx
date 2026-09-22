// #7878 (web half) — the win-probability chart stops drawing a line across an
// interval nobody observed, and stops extending a stalled line to "now".
//
// THE DEFECT, in the renderer's own terms: `OddsChart` seeds every minute of
// the domain and forward-fills every plotted key through the seeded minutes
// with no bound on the carried value's age, then hands recharts `connectNulls`.
// A minute the source reported and a minute nobody looked at come out as the
// same solid line. On the saved specimen below the two ends of the hole differ
// (37% → 43%), so the base chart draws a diagonal recovery across 73 minutes
// the market never traded.
//
// THE SHIP: a reader can tell "the quote sat still" (solid line, real
// readings) from "we have no readings" (a faint dashed connector across an
// interior hole, explained on hover; a line that simply ENDS and says how old
// it is at a stale trailing edge). Healthy continuous history, a freshly
// re-observed unchanged quote, pre-match sleep and completed endpoints are all
// UNCHANGED — the controls here are the half that stops the fix from being
// "break every line".
//
// These go through the REAL component and read the SVG recharts emitted, not
// `chartData` — a null another step fills back in is not a break, and only
// the path's `d` can say whether the pen was lifted.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

// recharts draws NOTHING inside a ResponsiveContainer without a viewport, so
// the chart is handed phone dimensions (390px, the width every LOOK in this
// issue was shot at). Same rig as chartDrawsALineYouCanSee.test.tsx.
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
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import type { EventHistoryResponse, WinProbHistoryPoint } from "@/lib/types";

// ── SVG readers ─────────────────────────────────────────────────────────────

interface Curve {
  tag: string;
  d: string;
  stroke: string;
  dasharray: string | null;
  width: number;
}

/** Every line-curve path recharts stroked. */
function curves(html: string): Curve[] {
  const tags = html.match(/<path[^>]*recharts-line-curve[^>]*>/g) ?? [];
  return tags.map((tag) => ({
    tag,
    d: /\sd="([^"]*)"/.exec(tag)?.[1] ?? "",
    stroke: /stroke="([^"]+)"/.exec(tag)?.[1] ?? "",
    dasharray: /stroke-dasharray="([^"]+)"/.exec(tag)?.[1] ?? null,
    width: Number(/stroke-width="([^"]+)"/.exec(tag)?.[1] ?? "0"),
  }));
}

/** Split a path into its sub-paths (one per pen-down); each a list of [x, y]. */
function subpaths(d: string): Array<Array<[number, number]>> {
  return d
    .split("M")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) =>
      (s.match(/-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?/g) ?? []).map((pair) => {
        const [x, y] = pair.split(",").map(Number);
        return [x, y] as [number, number];
      }),
    );
}

const KALSHI_GREEN = "#22c55e";
const isConnector = (c: Curve) => c.dasharray === "2 5";
/** The solid Kalshi line: the primary source, drawn at full weight, not a connector. */
const kalshiSolid = (html: string) =>
  curves(html).find((c) => c.stroke === KALSHI_GREEN && !isConnector(c) && c.width >= 2);
const kalshiConnector = (html: string) =>
  curves(html).find((c) => c.stroke === KALSHI_GREEN && isConnector(c));

const KALSHI_META = {
  kalshi: { display_name: "Kalshi", color: KALSHI_GREEN, type: "market" as const, dash_pattern: "8 4", snapshot_count: 0 },
};

function renderChart(props: Record<string, unknown>) {
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Home"
      awayTeam="Away"
      isLive={false}
      eventStatus="suspended"
      externalTimeRange="live"
      winProbSources={KALSHI_META}
      {...props}
    />,
  );
}

// ── The real specimen ───────────────────────────────────────────────────────

// The wire payload carries `status` and `commence_time` beside the typed fields.
const SPECIMEN: EventHistoryResponse & { _fixture_note: string; status: string; commence_time: string } = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "event-15315912-history-7878.json"), "utf8"),
);
const SPECIMEN_HOLE = { fromIso: "2026-09-21T08:14:33.775017+00:00", toIso: "2026-09-21T09:28:12.162071+00:00" };

/** Render exactly as the event page mounts it: the page's shared domain, its range, its status. */
function renderSpecimen(range: "all" | "live") {
  const domain = computeSharedChartDomain(SPECIMEN, range, SPECIMEN.status, SPECIMEN.commence_time, "tennis_wta");
  expect(domain).not.toBeNull();
  return renderChart({
    winProbHistory: SPECIMEN.win_prob_history,
    commenceTime: SPECIMEN.commence_time,
    eventStatus: SPECIMEN.status,
    externalTimeRange: range,
    chartStartTime: domain!.start,
    chartEndTime: domain!.end,
    sharedTicks: domain!.ticks,
    chartLabelFormat: domain!.labelFormat,
  });
}

describe("#7878 — the saved specimen 15315912 (a 73.6-minute interior hole)", () => {
  test("the fixture is the shape the issue measured, so the assertions below are about that hole", () => {
    const pts = SPECIMEN.win_prob_history!.kalshi;
    expect(pts).toHaveLength(199);
    const gapMin = (Date.parse(SPECIMEN_HOLE.toIso) - Date.parse(SPECIMEN_HOLE.fromIso)) / 60_000;
    expect(gapMin).toBeGreaterThan(73);
    expect(gapMin).toBeLessThan(74);
    expect(pts[79].timestamp).toBe(SPECIMEN_HOLE.fromIso);
    expect(pts[80].timestamp).toBe(SPECIMEN_HOLE.toIso);
    expect(pts.length - 81).toBe(118);
  });

  test("Since Start: the solid Kalshi line is lifted at the hole and a dashed connector spans exactly it", () => {
    const html = renderSpecimen("live");
    const solid = kalshiSolid(html);
    expect(solid).toBeDefined();
    const runs = subpaths(solid!.d);
    // BASE: one sub-path — the pen never lifts, the hole is drawn as a line.
    expect(runs.length).toBe(2);
    const [before, after] = runs;
    expect(before.length).toBeGreaterThan(10);
    expect(after.length).toBeGreaterThan(100);
    const lastBefore = before[before.length - 1];
    const firstAfter = after[0];
    // The hole is 73.6 of the ~391 drawn minutes: a visible break, not a hairline.
    expect(firstAfter[0] - lastBefore[0]).toBeGreaterThan(40);

    // The connector starts where the solid line stopped and ends where it
    // resumed — in x AND in y — so it carries the eye and nothing else.
    const connector = kalshiConnector(html);
    expect(connector).toBeDefined();
    const bridge = subpaths(connector!.d);
    expect(bridge.length).toBe(1);
    const c0 = bridge[0][0];
    const c1 = bridge[0][bridge[0].length - 1];
    expect(Math.abs(c0[0] - lastBefore[0])).toBeLessThan(0.75);
    expect(Math.abs(c0[1] - lastBefore[1])).toBeLessThan(0.75);
    expect(Math.abs(c1[0] - firstAfter[0])).toBeLessThan(0.75);
    expect(Math.abs(c1[1] - firstAfter[1])).toBeLessThan(0.75);
    // Faint, dashed, thinner than the line it bridges.
    expect(connector!.width).toBeLessThan(solid!.width);
    expect(/stroke-opacity="0\.[0-6]/.test(connector!.tag)).toBe(true);
  });

  test("All: the same hole is still a break in the 28-hour window", () => {
    const html = renderSpecimen("all");
    const solid = kalshiSolid(html);
    expect(solid).toBeDefined();
    expect(subpaths(solid!.d).length).toBe(2);
    expect(kalshiConnector(html)).toBeDefined();
  });

  test("no stale-edge caption: the specimen's series runs to the chart's right edge", () => {
    // The hole is interior. The only trailing interval here is from the last
    // observation to the drawn domain's end, which IS that observation.
    const html = renderSpecimen("live");
    expect(html).not.toContain('data-testid="chart-stale-edges"');
  });
});

// ── Constructed fixtures (labelled: shapes built to isolate one rule each) ──

const COMMENCE = Date.UTC(2026, 8, 21, 18, 0, 0); // fixed anchor — never Date.now()
const commenceIso = new Date(COMMENCE).toISOString();

function series(offsetsS: number[], value: number | ((i: number) => number)): WinProbHistoryPoint[] {
  return offsetsS.map((s, i) => {
    const p = typeof value === "function" ? value(i) : value;
    return {
      timestamp: new Date(COMMENCE + s * 1000).toISOString(),
      home_probability: p,
      away_probability: 1 - p,
    };
  });
}

/** Render with the page's real shared-domain computation for these props. */
function renderConstructed(
  kalshi: WinProbHistoryPoint[],
  opts: { status: string; isLive: boolean; range: "all" | "live"; extra?: Record<string, unknown> },
) {
  const history: EventHistoryResponse = {
    event_id: 1,
    home_team: "Home",
    away_team: "Away",
    commence_time: commenceIso,
    status: opts.status,
    history: [],
    win_prob_history: { kalshi },
    win_prob_sources: KALSHI_META,
  } as unknown as EventHistoryResponse;
  const domain = computeSharedChartDomain(history, opts.range, opts.status, commenceIso, "tennis_wta");
  expect(domain).not.toBeNull();
  return renderChart({
    winProbHistory: { kalshi },
    commenceTime: commenceIso,
    eventStatus: opts.status,
    isLive: opts.isLive,
    externalTimeRange: opts.range,
    chartStartTime: domain!.start,
    chartEndTime: domain!.end,
    sharedTicks: domain!.ticks,
    chartLabelFormat: domain!.labelFormat,
    ...opts.extra,
  });
}

describe("#7878 — CONSTRUCTED: the stalled live line (15316479's shape, per the issue)", () => {
  // Five real readings two minutes apart from kickoff, then nothing for 3h17m,
  // then the backend's synthetic `live_edge` point at "now" (#920). The issue's
  // frame: one flat line across the whole domain, badged LIVE.
  const stalled = [
    ...series([141, 260, 380, 500, 619], 0.01),
    { ...series([12_437], 0.01)[0], live_edge: true },
  ];

  test("the solid line ends at the last real reading — it is not extended to the live edge", () => {
    const html = renderConstructed(stalled, { status: "live", isLive: true, range: "live" });
    const solid = kalshiSolid(html);
    expect(solid).toBeDefined();
    const runs = subpaths(solid!.d);
    expect(runs.length).toBe(1);
    const xs = runs[0].map((p) => p[0]);
    const lastX = Math.max(...xs);
    // Plot is 390px wide; the readings cover ~10 of ~208 drawn minutes, so the
    // ink must end well inside the left fifth. BASE draws to the right edge.
    expect(lastX).toBeLessThan(390 * 0.25);
    // No connector: there is no far-side reading to connect to.
    expect(kalshiConnector(html)).toBeUndefined();
    // And the chart says how old the last reading is.
    expect(html).toContain('data-testid="chart-stale-edges"');
    expect(html).toMatch(/Kalshi.*last reading .* none in the 3h 1[6-7]m since/);
  });

  test("the footer readout is anchored at the last reading, not at the live edge", () => {
    const html = renderConstructed(stalled, { status: "live", isLive: true, range: "live" });
    const at = /data-callout-at="([^"]*)"/.exec(html)?.[1];
    expect(at).toBe(new Date(COMMENCE + 619 * 1000).toISOString().replace(/:\d\d\.\d{3}Z$/, ":00.000Z"));
  });
});

describe("#7878 — REAL healthy control: a completed MLB game with five dense sources (15316298)", () => {
  const HEALTHY: EventHistoryResponse & { status: string; commence_time: string } = JSON.parse(
    readFileSync(join(__dirname, "..", "fixtures", "event-15316298-history-7878-healthy.json"), "utf8"),
  );

  test("every observation line is one unbroken sub-path, no connector, no stale caption — the page as it is today", () => {
    const domain = computeSharedChartDomain(HEALTHY, "live", HEALTHY.status, HEALTHY.commence_time, "baseball_mlb");
    expect(domain).not.toBeNull();
    const html = renderToStaticMarkup(
      <OddsChart
        history={HEALTHY.history}
        bookmakerHistory={HEALTHY.bookmaker_history}
        winProbHistory={HEALTHY.win_prob_history}
        winProbSources={HEALTHY.win_prob_sources}
        aggregateLine={HEALTHY.aggregate_line}
        homeTeam={HEALTHY.home_team}
        awayTeam={HEALTHY.away_team}
        commenceTime={HEALTHY.commence_time}
        completedAt={HEALTHY.completed_at}
        isLive={false}
        eventStatus={HEALTHY.status}
        externalTimeRange="live"
        chartStartTime={domain!.start}
        chartEndTime={domain!.end}
        sharedTicks={domain!.ticks}
        chartLabelFormat={domain!.labelFormat}
      />,
    );
    const all = curves(html);
    // Blend + 5 sources + sportsbooks = 7 lines, as production draws today.
    expect(all.length).toBe(7);
    for (const c of all) {
      expect(isConnector(c)).toBe(false);
      expect(subpaths(c.d).length).toBe(1);
    }
    expect(html).not.toContain('data-testid="chart-stale-edges"');
    // And the market lines still run to the chart's right edge: a market
    // that stopped quoting when the venue settled is finished, not stale.
    const kalshi = all.find((c) => c.stroke === KALSHI_GREEN)!;
    const maxX = Math.max(...subpaths(kalshi.d)[0].map((p) => p[0]));
    const rightmost = Math.max(...all.flatMap((c) => subpaths(c.d)[0].map((p) => p[0])));
    expect(maxX).toBe(rightmost);
  });
});

describe("#7878 — CONTROLS: the lines that must NOT break", () => {
  test("a fresh unchanged quote stays one solid line to the live edge (the heartbeat rows are real readings)", () => {
    // Thirty readings at the live cadence, all 0.99, then a live edge 90s after
    // the last. Nothing traded; everything was observed. This is the case the
    // directive names as the healthy control, and BASE passes it too — it is
    // here so the fix cannot be "any flat line is suspicious".
    const flat = [
      ...series(Array.from({ length: 30 }, (_, i) => i * 120), 0.99),
      { ...series([29 * 120 + 90], 0.99)[0], live_edge: true },
    ];
    const html = renderConstructed(flat, { status: "live", isLive: true, range: "live" });
    const solid = kalshiSolid(html);
    expect(solid).toBeDefined();
    const runs = subpaths(solid!.d);
    expect(runs.length).toBe(1);
    const lastX = Math.max(...runs[0].map((p) => p[0]));
    expect(lastX).toBeGreaterThan(390 * 0.8);
    expect(kalshiConnector(html)).toBeUndefined();
    expect(html).not.toContain('data-testid="chart-stale-edges"');
  });

  test("a healthy dense in-game series with real movement is one line", () => {
    const dense = series(Array.from({ length: 120 }, (_, i) => i * 33), (i) => 0.3 + 0.4 * ((i % 20) / 20));
    const html = renderConstructed(dense, { status: "live", isLive: true, range: "live" });
    expect(subpaths(kalshiSolid(html)!.d).length).toBe(1);
    expect(kalshiConnector(html)).toBeUndefined();
  });

  test("overnight pre-match holes are never broken (pre-match dedup makes silence the normal shape)", () => {
    const sleepy = series([-172_800, -86_400, -43_200, -3_600, -600], (i) => 0.4 + i * 0.02);
    const html = renderConstructed(sleepy, { status: "scheduled", isLive: false, range: "all" });
    expect(subpaths(kalshiSolid(html)!.d).length).toBe(1);
    expect(kalshiConnector(html)).toBeUndefined();
    expect(html).not.toContain('data-testid="chart-stale-edges"');
  });

  test("a hole that straddles the scheduled start is left joined (a scheduled kickoff is not an evidenced start)", () => {
    const straddle = series([-7_200, -3_600, 14_400, 14_520, 14_640], 0.5);
    const html = renderConstructed(straddle, { status: "live", isLive: true, range: "all" });
    expect(subpaths(kalshiSolid(html)!.d).length).toBe(1);
  });

  test("a slow-but-steady series is judged on its own rhythm: 20-minute cadence is not a hole", () => {
    const slow = series(Array.from({ length: 10 }, (_, i) => i * 1_200), (i) => 0.4 + i * 0.01);
    const html = renderConstructed(slow, { status: "live", isLive: true, range: "live" });
    expect(subpaths(kalshiSolid(html)!.d).length).toBe(1);
  });

  test("a completed match keeps its settled endpoint: the terminal point is drawn, not withdrawn", () => {
    // 20 readings a minute apart, then the backend's terminal `final` point
    // 50 minutes later at the result (a real endpoint — the outcome). The
    // interval into it is unobserved, so it is bridged dashed; the endpoint
    // itself stays on the solid path.
    const settled = [
      ...series(Array.from({ length: 20 }, (_, i) => i * 60), (i) => 0.6 + i * 0.01),
      { ...series([20 * 60 + 3_000], 1.0)[0], game_state: { final: true } },
    ];
    const html = renderConstructed(settled, {
      status: "completed",
      isLive: false,
      range: "live",
      extra: { completedAt: new Date(COMMENCE + 20 * 60_000 + 3_000_000).toISOString() },
    });
    const solid = kalshiSolid(html);
    const runs = subpaths(solid!.d);
    expect(runs.length).toBe(2);
    // The far run is the one settled point; recharts still emits its sub-path.
    expect(runs[1].length).toBeGreaterThanOrEqual(1);
    expect(kalshiConnector(html)).toBeDefined();
  });
});
