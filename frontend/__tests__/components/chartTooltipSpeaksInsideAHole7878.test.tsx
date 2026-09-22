// #7878 (web half), the tooltip arm — a minute inside a hole says "no
// readings", and the one prop that lets it say so is guarded.
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

describe("#7878 — the tooltip speaks inside a hole", () => {
  test("the chart asks recharts for null entries, because the default would render no card at all there", () => {
    renderSpecimen();
    // Not `!== true`: the point is that the chart states it, so a refactor that
    // drops the prop and falls back to recharts' default fails here.
    expect(mockRecorded.tooltip?.filterNull).toBe(false);
  });

  test("a minute inside the hole reports the interval that bounds it, and quotes no price", () => {
    const labelFormat = renderSpecimen();
    const bucket = bucketInsideHole();
    // The series IS null at this minute — that is what the fix withdrew — so
    // this is the payload recharts delivers with `filterNull={false}`.
    const html = renderCard(bucket.time, [
      { value: null, name: "Kalshi", color: KALSHI_GREEN, dataKey: KALSHI_KEY },
    ]);

    // Both ends of the hole, in the axis's own label format — the times the
    // reader is looking at on the ticks. Named in full so a rule that reported
    // SOME interval here could not pass by accident.
    expect(html).toContain(
      `no readings ${atAxisClock(HOLE.fromIso, labelFormat)} – ${atAxisClock(HOLE.toIso, labelFormat)}`,
    );
    expect(html).toContain("Kalshi");
    // A hole never carries a number: no percentage anywhere on the card.
    expect(html).not.toMatch(/\d+(\.\d+)?%/);
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

  test("CONTROL — on recharts' default the hole's card does not exist, which is the silence the prop removes", () => {
    renderSpecimen();
    const bucket = bucketInsideHole();
    // `filterNull: true` drops the null entry; recharts then hands `content` an
    // EMPTY payload, and `CustomTooltip`'s first guard returns no card. This is
    // the state the reader was in before the fix, reproduced through the real
    // component — so the arm above is asserting a difference that exists.
    const html = renderCard(bucket.time, []);
    expect(html).toBe("");
  });
});
