// #7878 (web half), the tooltip arm — SUPERSEDED for interior holes by #11929.
//
// #11929 — ALEX'S RULING (2026-11-04 12:09 PT): "A solid line through
// unobserved time … no bridge, no dotted treatment, no label … nothing on the
// chart calls the reader's attention to a gap." The tooltip's interior-hole
// note ("no readings 1:14 AM – 2:28 AM") was such a label, and it is gone: a
// minute inside the specimen's 73.6-minute hole is now an ordinary minute of
// the line — chartData carries the 08:14 reading through it and the card
// quotes that number, with no note. `filterNull={false}` is still needed and
// still guarded, for the one note that remains: a live line past its STALE
// RIGHT EDGE ("last reading …, none since") is null there, and recharts'
// default would render no card at all. The CONTROL arm now proves that on a
// stalled live line instead of on the interior hole.
//
// THE ORIGINAL #7878 TEXT (the hole half is history):
//
// WHY THIS FILE EXISTS, AND WHY IT IS SEPARATE. The sibling suite
// (`chartStopsDrawingAcrossAHoleNobodyObserved7878`) reads the SVG recharts
// emitted under `renderToStaticMarkup`. A tooltip has no static markup — it
// exists only on hover — so that rig cannot reach it, and a mutation run
// proved the consequence: deleting `filterNull={false}` from `<Tooltip>`
// killed no test, while the production hover frame
// (`artifacts/ux-1440/AFTER-15315912-local-390-hover-in-hole.png`) shows the
// note it silently removes.
//
// THE MECHANISM THAT PROP GUARDS. Recharts' `filterNull` defaults to TRUE: it
// drops every null-valued entry from the payload and then renders no card at
// all when none remain. A minute inside an unsupported interval is precisely
// the minute where the series' value is null — so on the default the reader
// hovers the hole and gets nothing, which is the same silence the fix exists
// to end. `CustomTooltip` has something true to say there, so it must be
// asked.
//
// HOW IT IS REACHED WITHOUT A DOM. The rig is `testEnvironment: 'node'` — no
// jsdom, no hover. So the recharts mock RECORDS what the chart hands it (the
// `<Tooltip>` props, including the live `content` element, and `<LineChart>`'s
// real `data`) and then renders the real component as usual. The assertions
// below drive the REAL `CustomTooltip` the chart configured, at a bucket taken
// from the REAL chartData, with the payload shape recharts delivers on each
// setting of the prop. Nothing here matches source text.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { format, parseISO } from "date-fns";
import { readFileSync } from "fs";
import { join } from "path";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

interface TooltipProps {
  filterNull?: boolean;
  content?: React.ReactElement;
}
interface ChartDatum {
  time: string;
  timestamp: string;
  [key: string]: unknown;
}

// `mock`-prefixed so the jest.mock factory may close over them.
const mockRecorded: { tooltip: TooltipProps | null; data: ChartDatum[] } = { tooltip: null, data: [] };

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  const react = jest.requireActual("react") as typeof React;
  return {
    __esModule: true,
    ...actual,
    // Same viewport the sibling suite gives it: recharts draws nothing inside a
    // ResponsiveContainer without one.
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
import type { EventHistoryResponse } from "@/lib/types";

const KALSHI_GREEN = "#22c55e";
const KALSHI_KEY = "wp_kalshi_delta";
const KALSHI_META = {
  kalshi: { display_name: "Kalshi", color: KALSHI_GREEN, type: "market" as const, dash_pattern: "8 4", snapshot_count: 0 },
};

const SPECIMEN: EventHistoryResponse & { status: string; commence_time: string } = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "event-15315912-history-7878.json"), "utf8"),
);
// The one hole the rule finds on this specimen: 1 of its 184 in-game intervals.
const HOLE = { fromIso: "2026-09-21T08:14:33.775017+00:00", toIso: "2026-09-21T09:28:12.162071+00:00" };

/**
 * Render exactly as the event page mounts it, recording what recharts was
 * handed. Returns the axis label format so the expected clock strings are
 * DERIVED, never typed: this suite runs at UTC and the LOOK frames were shot
 * at PDT, so a literal "1:14 AM" would be an assertion about the runner's
 * timezone (gotcha #44's shape) rather than about the hole.
 */
function renderSpecimen(): string {
  mockRecorded.tooltip = null;
  mockRecorded.data = [];
  const domain = computeSharedChartDomain(SPECIMEN, "live", SPECIMEN.status, SPECIMEN.commence_time, "tennis_wta");
  expect(domain).not.toBeNull();
  renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Home"
      awayTeam="Away"
      isLive={false}
      winProbSources={KALSHI_META}
      winProbHistory={SPECIMEN.win_prob_history}
      commenceTime={SPECIMEN.commence_time}
      eventStatus={SPECIMEN.status}
      externalTimeRange="live"
      chartStartTime={domain!.start}
      chartEndTime={domain!.end}
      sharedTicks={domain!.ticks}
      chartLabelFormat={domain!.labelFormat}
    />,
  );
  return domain!.labelFormat;
}

/** The hole's ends spelled the way the axis spells its ticks. */
const atAxisClock = (iso: string, labelFormat: string) => format(parseISO(iso), labelFormat);

/** A bucket strictly inside the hole, taken from the chart's own data. */
function bucketInsideHole(): ChartDatum {
  const from = Date.parse(HOLE.fromIso);
  const to = Date.parse(HOLE.toIso);
  const inside = mockRecorded.data.filter((d) => {
    const ms = Date.parse(d.timestamp);
    return ms > from && ms < to;
  });
  // ~73 minute buckets; if this is empty the specimen has gone inert.
  expect(inside.length).toBeGreaterThan(60);
  return inside[Math.floor(inside.length / 2)];
}

/** Drive the real CustomTooltip the chart configured. */
function renderCard(label: string, payload: Array<{ value: number | null; name: string; color: string; dataKey: string }>) {
  const content = mockRecorded.tooltip?.content;
  expect(React.isValidElement(content)).toBe(true);
  return renderToStaticMarkup(React.cloneElement(content as React.ReactElement, { active: true, payload, label }));
}

// The tooltip card is the one part of this chart that uses `useLayoutEffect`
// (`ViewportFittedTooltipCard`, the #1833 width cap), and React warns about
// that on every server render. It is expected here and only here, so it is
// filtered BY MESSAGE — anything else console.error says still gets through,
// because a suppression wide enough to hide a real warning is worse than the
// noise it removes.
const realConsoleError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].includes("useLayoutEffect does nothing on the server")) return;
    realConsoleError(...args);
  };
});
afterAll(() => {
  console.error = realConsoleError;
});

describe("#7878 / #11929 — the tooltip names no hole, and speaks past a stale edge", () => {
  test("the chart asks recharts for null entries, because the default would render no card at all there", () => {
    renderSpecimen();
    // Not `!== true`: the point is that the chart states it, so a refactor that
    // drops the prop and falls back to recharts' default fails here.
    expect(mockRecorded.tooltip?.filterNull).toBe(false);
  });

  test("#11929: a minute inside the hole is an ordinary minute — it carries the last reading, and the card quotes it with no note", () => {
    const labelFormat = renderSpecimen();
    const bucket = bucketInsideHole();
    // The carry was NOT withdrawn: the bucket holds the value at the hole's
    // first reading, exactly as any minute between two readings does.
    const atHoleStart = mockRecorded.data.find(
      (d) => Math.floor(Date.parse(d.timestamp) / 60_000) === Math.floor(Date.parse(HOLE.fromIso) / 60_000),
    );
    expect(typeof atHoleStart?.[KALSHI_KEY]).toBe("number");
    expect(bucket[KALSHI_KEY]).toBe(atHoleStart![KALSHI_KEY]);
    const html = renderCard(bucket.time, [
      { value: bucket[KALSHI_KEY] as number, name: "Kalshi", color: KALSHI_GREEN, dataKey: KALSHI_KEY },
    ]);
    expect(html).toMatch(/\d+(\.\d+)?%/);
    // Nothing names the stretch: no note, no bounding times, no "none since".
    expect(html).not.toContain("chart-gap-note");
    expect(html).not.toMatch(/no readings|No numbers for|none since/i);
    expect(html).not.toContain(`${atAxisClock(HOLE.fromIso, labelFormat)} – ${atAxisClock(HOLE.toIso, labelFormat)}`);
    // Even handed a null entry, a minute inside an INTERIOR hole gets no note
    // (the card has nothing to say, so there is no card).
    expect(renderCard(bucket.time, [{ value: null, name: "Kalshi", color: KALSHI_GREEN, dataKey: KALSHI_KEY }])).toBe("");
  });

  test("the same card at a minute the source DID report shows the number and no note", () => {
    renderSpecimen();
    const from = Date.parse(HOLE.fromIso);
    const supported = mockRecorded.data.find((d) => Date.parse(d.timestamp) < from && typeof d[KALSHI_KEY] === "number");
    expect(supported).toBeDefined();
    const html = renderCard(supported!.time, [
      { value: supported![KALSHI_KEY] as number, name: "Kalshi", color: KALSHI_GREEN, dataKey: KALSHI_KEY },
    ]);

    expect(html).toMatch(/\d+(\.\d+)?%/);
    expect(html).not.toContain("no readings");
  });

  test("a minute past a STALE RIGHT EDGE says how old the last reading is, and quotes no price", () => {
    const { labelFormat, lastReadingIso } = renderStalled();
    const bucket = bucketPastStaleEdge(lastReadingIso);
    expect(bucket[KALSHI_KEY] ?? null).toBeNull();
    const html = renderCard(bucket.time, [
      { value: null, name: "Kalshi", color: KALSHI_GREEN, dataKey: KALSHI_KEY },
    ]);
    expect(html).toContain(`last reading ${atAxisClock(lastReadingIso, labelFormat)}, none since`);
    expect(html).toContain("Kalshi");
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
  });

  test("CONTROL — on recharts' default the stale edge's card does not exist, which is the silence the prop removes", () => {
    const { lastReadingIso } = renderStalled();
    const bucket = bucketPastStaleEdge(lastReadingIso);
    // `filterNull: true` drops the null entry; recharts then hands `content` an
    // EMPTY payload, and `CustomTooltip`'s first guard returns no card. This is
    // the state the reader would be in without the prop, reproduced through
    // the real component — so the arm above asserts a difference that exists.
    const html = renderCard(bucket.time, []);
    expect(html).toBe("");
  });
});

// ── Constructed (labelled): a stalled live line — 15316479's shape ──────────
// Five real readings two minutes apart from the start, then nothing for 3h17m,
// then the backend's synthetic `live_edge` point at "now" (#920).
const STALL_COMMENCE = Date.UTC(2026, 8, 21, 18, 0, 0); // fixed anchor — never Date.now()

function renderStalled(): { labelFormat: string; lastReadingIso: string } {
  mockRecorded.tooltip = null;
  mockRecorded.data = [];
  const commenceIso = new Date(STALL_COMMENCE).toISOString();
  const at = (s: number) => new Date(STALL_COMMENCE + s * 1000).toISOString();
  const kalshi = [
    ...[141, 260, 380, 500, 619].map((s) => ({ timestamp: at(s), home_probability: 0.6, away_probability: 0.4 })),
    { timestamp: at(12_437), home_probability: 0.6, away_probability: 0.4, live_edge: true },
  ];
  const history = {
    event_id: 1, home_team: "Home", away_team: "Away", commence_time: commenceIso, status: "live",
    history: [], win_prob_history: { kalshi }, win_prob_sources: KALSHI_META,
  } as unknown as EventHistoryResponse;
  const domain = computeSharedChartDomain(history, "live", "live", commenceIso, "tennis_wta");
  expect(domain).not.toBeNull();
  renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam="Home"
      awayTeam="Away"
      isLive
      winProbSources={KALSHI_META}
      winProbHistory={{ kalshi }}
      commenceTime={commenceIso}
      eventStatus="live"
      externalTimeRange="live"
      chartStartTime={domain!.start}
      chartEndTime={domain!.end}
      sharedTicks={domain!.ticks}
      chartLabelFormat={domain!.labelFormat}
    />,
  );
  return { labelFormat: domain!.labelFormat, lastReadingIso: at(619) };
}

function bucketPastStaleEdge(lastReadingIso: string): ChartDatum {
  const last = Date.parse(lastReadingIso);
  const past = mockRecorded.data.filter((d) => Date.parse(d.timestamp) > last + 60_000);
  expect(past.length).toBeGreaterThan(60);
  return past[Math.floor(past.length / 2)];
}
