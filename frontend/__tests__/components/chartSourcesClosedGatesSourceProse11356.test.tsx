/**
 * #11356 — with Sources closed over the blend no source line is drawn, so no
 * prose may describe one: not the tooltip's hole notes (#7878) and not the
 * stale-edge caption under the chart. The gate is "sources hidden behind the
 * blend", NOT "source lines drawn" — with no blend (sportsbooks-only, MODE B)
 * the one Sportsbooks line IS drawn and its holes keep their note.
 *
 * lane1's source review of PR #11387 (`0d0412ae63`) found the gate keyed on
 * `sourceLinesShown`, which is also false in sportsbooks-only mode: a minute
 * inside the hole of the only line on the plot drew no tooltip card at all —
 * the silence #7878 removed. Its control (parent: card; subject: empty) is the
 * first arm below, kept as lane1 wrote it.
 *
 * Static markup cannot hover, so the recharts mock RECORDS the `<Tooltip>`
 * props and `<ComposedChart>` data and the test drives the REAL configured
 * `CustomTooltip` at a bucket of the REAL chartData (the #7878 rig).
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { format, parseISO } from "date-fns";
import { readFileSync } from "fs";
import { join } from "path";

import { AnalyticsProvider } from "@/components/Analytics";
import cases from "../fixtures/chartSingleTrajectory11356.json";

interface TooltipProps {
  filterNull?: boolean;
  content?: React.ReactElement;
}
interface ChartDatum {
  time: string;
  timestamp: string;
  [key: string]: unknown;
}

// `mock`-prefixed so the jest.mock factory may close over it.
const mockRecorded: { tooltip: TooltipProps | null; data: ChartDatum[] } = {
  tooltip: null,
  data: [],
};

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
import type { EventHistoryResponse } from "@/lib/types";

const realConsoleError = console.error;
beforeAll(() => {
  console.error = (...a: unknown[]) => {
    if (typeof a[0] === "string" && a[0].includes("useLayoutEffect")) return;
    realConsoleError(...a);
  };
});
afterAll(() => {
  console.error = realConsoleError;
});

// The text nodes of a static-markup fragment, in order (nothing is stripped, so
// nothing here claims to sanitise markup).
const textOf = (html: string) =>
  [...html.matchAll(/>([^<]*)</g)].map((m) => m[1]).join(" ");
const cardText = (html: string) => textOf(html).replace(/\s+/g, " ").trim();

describe("sportsbooks-only: a hole in the one drawn line keeps its note", () => {
  // The #7878 specimen with its one series fed as SPORTSBOOK history: no
  // blend, so the drawn line is MODE B's `homeDelta`. The one hole the rule
  // finds on it is 08:14–09:28.
  const SPECIMEN: EventHistoryResponse & {
    status: string;
    commence_time: string;
  } = JSON.parse(
    readFileSync(
      join(__dirname, "..", "fixtures", "event-15315912-history-7878.json"),
      "utf8",
    ),
  );
  const HOLE = {
    fromIso: "2026-09-21T08:14:33.775017+00:00",
    toIso: "2026-09-21T09:28:12.162071+00:00",
  };
  const asBook = SPECIMEN.win_prob_history!.kalshi.map((p) => ({
    timestamp: p.timestamp,
    home_probability: p.home_probability,
    away_probability: p.away_probability,
    over_under: null,
    projected_home_score: null,
    projected_away_score: null,
    bookmaker: "consensus",
  }));

  it("a minute inside the hole draws a card naming the two bounding readings", () => {
    mockRecorded.tooltip = null;
    mockRecorded.data = [];
    const domain = computeSharedChartDomain(
      SPECIMEN,
      "live",
      SPECIMEN.status,
      SPECIMEN.commence_time,
      "tennis_wta",
    )!;
    renderToStaticMarkup(
      <AnalyticsProvider>
        <OddsChart
          history={asBook as never}
          homeTeam="Home"
          awayTeam="Away"
          isLive={false}
          commenceTime={SPECIMEN.commence_time}
          eventStatus={SPECIMEN.status}
          externalTimeRange="live"
          chartStartTime={domain.start}
          chartEndTime={domain.end}
          sharedTicks={domain.ticks}
          chartLabelFormat={domain.labelFormat}
        />
      </AnalyticsProvider>,
    );
    const from = Date.parse(HOLE.fromIso);
    const to = Date.parse(HOLE.toIso);
    const inside = mockRecorded.data.filter((d) => {
      const ms = Date.parse(d.timestamp);
      return ms > from && ms < to;
    });
    expect(inside.length).toBeGreaterThan(60);
    const bucket = inside[Math.floor(inside.length / 2)];
    expect(bucket.homeDelta ?? null).toBeNull();
    // The render above reassigned it; TS still narrows it to the `null` set first.
    const content = (mockRecorded.tooltip as TooltipProps | null)
      ?.content as React.ReactElement;
    const html = renderToStaticMarkup(
      React.cloneElement(content, {
        active: true,
        label: bucket.time,
        payload: [
          {
            value: null,
            name: "Sportsbooks",
            color: "#0f172a",
            dataKey: "homeDelta",
          },
        ],
      }),
    );
    expect(cardText(html)).toContain(
      `Sportsbooks no readings ${format(parseISO(HOLE.fromIso), domain.labelFormat)} – ${format(parseISO(HOLE.toIso), domain.labelFormat)}`,
    );
  });
});

describe("the stale-edge caption names only a drawn line", () => {
  // Jaguars–Eagles 14639175, 14:35–15:05Z (retained real rows), live, with
  // Kalshi's readings cut 15 minutes before the window ends — so Kalshi is the
  // one series with a trailing edge.
  const C = cases.cases.find((x) => x.case === "close-crossing")!;
  const cut = Date.parse(C.window.end) - 15 * 60_000;
  const wph = Object.fromEntries(
    Object.entries(C.win_prob_history).map(([k, v]) => [
      k,
      k === "kalshi"
        ? (v as Array<{ timestamp: string }>).filter(
            (p) => Date.parse(p.timestamp) < cut,
          )
        : v,
    ]),
  );
  const render = (over: Record<string, unknown> = {}) =>
    renderToStaticMarkup(
      <AnalyticsProvider>
        <OddsChart
          history={[]}
          homeTeam={C.home_team}
          awayTeam={C.away_team}
          sportKey="americanfootball_nfl"
          commenceTime={C.window.start}
          eventStatus="live"
          isLive
          winProbHistory={wph as never}
          aggregateLine={C.aggregate_line as never}
          backendBlendServed
          chartStartTime={C.window.start}
          chartEndTime={C.window.end}
          externalTimeRange="all"
          {...over}
        />
      </AnalyticsProvider>,
    );
  const caption = (html: string) =>
    textOf(
      `>${/data-testid="chart-stale-edges">([\s\S]*?)<\/div>/.exec(html)?.[1] ?? ""}<`,
    )
      .replace(/\s+/g, " ")
      .trim();
  const curves = (html: string) =>
    (html.match(/recharts-line-curve/g) ?? []).length;

  it("Sources closed over the blend: one line drawn, no source caption", () => {
    const closed = render();
    expect(curves(closed)).toBe(1);
    expect(closed).not.toContain('data-testid="chart-stale-edges"');
  });

  it("Sources open: the revealed Kalshi line carries its caption", () => {
    const opened = render({ defaultSourcesExpanded: true });
    expect(curves(opened)).toBeGreaterThan(1);
    expect(caption(opened)).toMatch(
      /^Kalshi last reading .+ · none in the 15m since$/,
    );
  });

  it("no blend: the vendor lines are the drawn lines and keep the caption", () => {
    const noBlend = render({ backendBlendServed: false, aggregateLine: [] });
    expect(curves(noBlend)).toBeGreaterThan(1);
    expect(caption(noBlend)).toMatch(
      /^Kalshi last reading .+ · none in the 15m since$/,
    );
  });
});
