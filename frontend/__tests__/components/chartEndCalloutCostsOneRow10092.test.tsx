/**
 * #10092: the end callout costs one row, not every row on the chart.
 *
 * Live replayed an accepted push on the production-built event page
 * (`/events/15320645`, 390px, 2026-10-02). From frame to hero digits plus chart
 * callout it measured p95 233.7 ms against a 100 ms target. The hero commits
 * together with the chart, and the chart's end dot was a `<Scatter>` laid over
 * all of `chartData`. That's one row per minute: 2,865 symbol groups for one
 * dot, rebuilt on every push. Drawn on its one row, the same replay measured
 * p95 84.4 ms (n = 33).
 *
 * Two halves:
 *  1. COST: on the real 48 h payload from that replay, the chart draws its
 *     callout with no per-row scatter symbols, and draws it once.
 *  2. SAME PIXELS: `ChartRowMarks` hands a shape the cx/cy/yAxis a recharts
 *     `<Scatter>` hands it for the same row, and clips the same way. This half
 *     is what stops the cheaper path from moving the dot. Its first draft
 *     clipped both axes to the plot and cut off the right half of the end dot,
 *     because recharts clips only the axis that allows overflow.
 */
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import { ComposedChart, Customized, Line, Scatter, XAxis, YAxis } from "recharts";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock("recharts", () => ({
  __esModule: true,
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }),
}));

import OddsChart, { ChartRowMarks, type ChartRowMark } from "@/components/OddsChart";
import type { EventHistoryResponse } from "@/lib/types";

// The replay's own frozen read of /api/events/15320645/history (05:52Z 10/2).
const served: EventHistoryResponse = JSON.parse(readFileSync(
  join(__dirname, "../fixtures/event-15320645-history-10092.json"), "utf8",
));

const renderSpecimen = () => renderToStaticMarkup(<OddsChart
  history={served.history} bookmakerHistory={served.bookmaker_history}
  aggregateLine={served.aggregate_line ?? undefined}
  winProbHistory={served.win_prob_history} winProbSources={served.win_prob_sources}
  homeTeam="Pallacanestro Trieste" awayTeam="Reyer Venezia"
  isLive={false} eventStatus="scheduled" commenceTime="2026-10-04T15:30:00+00:00"
  chartStartTime="2026-09-30T06:00:00Z" chartEndTime="2026-10-02T05:52:00Z"
/>);

const count = (html: string, re: RegExp) => [...html.matchAll(re)].length;
/** The callout's glow ring: the only r=8 circle the chart draws. */
const glows = (html: string) => [...html.matchAll(/<circle[^>]*\sr="8"[^>]*>/g)].map((m) => ({
  cx: Number(/\scx="([^"]+)"/.exec(m[0])?.[1]),
  cy: Number(/\scy="([^"]+)"/.exec(m[0])?.[1]),
}));
/** The last vertex of every drawn line. */
const lineEnds = (html: string) => [...html.matchAll(/<path[^>]*class="recharts-curve recharts-line-curve"[^>]*\sd="([^"]+)"/g)]
  .map((m) => {
    const nums = m[1].match(/-?\d+(?:\.\d+)?/g)!.map(Number);
    return { x: nums[nums.length - 2], y: nums[nums.length - 1] };
  });

describe("#10092 the chart's end callout is drawn on its one row", () => {
  const html = renderSpecimen();

  it("draws no per-row scatter symbols on the replay's 48 h chart", () => {
    // A <Scatter> over the chart's data leaves one of these per row whatever
    // its shape returns (2,865 on this page in the browser).
    expect(count(html, /recharts-scatter-symbol/g)).toBe(0);
  });

  it("still draws the callout exactly once, labelled with the number the wrapper exports", () => {
    expect(glows(html)).toHaveLength(1);
    const label = /data-callout-label="([^"]+)"/.exec(html)?.[1];
    expect(label).toMatch(/^\d+%$/);
    // The painted text the #10092 harness reads (`.recharts-scatter text`).
    expect(html).toMatch(new RegExp(`class="recharts-layer recharts-scatter"[^]*?<text[^>]*>${label}</text>`));
  });

  it("puts the dot on the end of the line it labels", () => {
    const [dot] = glows(html);
    const ends = lineEnds(html);
    expect(ends.length).toBeGreaterThan(0);
    expect(ends.some((e) => Math.abs(e.x - dot.cx) < 0.01 && Math.abs(e.y - dot.cy) < 0.01)).toBe(true);
  });
});

describe("#10092 ChartRowMarks hands a shape what a recharts <Scatter> hands it", () => {
  type Seen = { cx: number; cy: number; plotY?: number; plotH?: number; v: unknown };
  const rows = ["1:00", "1:01", "1:02", "1:03", "1:04", "1:05"].map((time, i) => ({ time, v: 40 + i * 3 } as Record<string, unknown>));
  const MARKED = 3;

  const renderBoth = (overflow: boolean) => {
    const data: Array<Record<string, unknown>> = rows.map((r, i) => (i === MARKED ? { ...r, mark: r.v } : { ...r }));
    const seen: Record<"scatter" | "marks", Seen[]> = { scatter: [], marks: [] };
    const probe = (who: "scatter" | "marks") => (p: {
      cx?: number; cy?: number; payload?: Record<string, unknown>; yAxis?: { y?: number; height?: number };
    }) => {
      if (who === "scatter" && p.payload?.mark == null) return <g />;
      seen[who].push({ cx: p.cx!, cy: p.cy!, plotY: p.yAxis?.y, plotH: p.yAxis?.height, v: p.payload?.v });
      return <circle data-who={who} cx={p.cx} cy={p.cy} r={5} />;
    };
    const marks: ChartRowMark[] = [{ index: MARKED, y: data[MARKED].v as number, payload: data[MARKED] }];
    const html = renderToStaticMarkup(
      <ComposedChart width={390} height={300} data={data} margin={{ top: 15, right: 10, left: 0, bottom: 5 }}>
        <XAxis dataKey="time" />
        <YAxis domain={[0, 100]} allowDataOverflow={overflow} />
        <Line dataKey="v" isAnimationActive={false} dot={false} />
        <Scatter dataKey="mark" isAnimationActive={false} shape={probe("scatter")} />
        <Customized component={<ChartRowMarks rows={marks} shape={probe("marks")} />} />
      </ComposedChart>,
    );
    return { html, seen };
  };
  const clipRects = (html: string) => [...html.matchAll(/<clipPath id="(clipPath-recharts-scatter[^"]*|odds-chart-marks[^"]*)"><rect([^>]*)>/g)]
    .map((m) => ({ id: m[1].startsWith("odds") ? "marks" : "scatter", rect: m[2].trim() }));

  it.each([true, false])("same cx, cy and plot rect for the same row (allowDataOverflow=%s)", (overflow) => {
    const { seen } = renderBoth(overflow);
    expect(seen.scatter).toHaveLength(1);
    expect(seen.marks).toEqual(seen.scatter);
    expect(seen.marks[0].v).toBe(rows[MARKED].v);
  });

  it("clips exactly as the scatter does: the y axis to the plot, the x axis left open", () => {
    const rects = clipRects(renderBoth(true).html);
    expect(rects.map((r) => r.id).sort()).toEqual(["marks", "scatter"]);
    expect(rects[0].rect).toBe(rects[1].rect);
  });

  it("CONTROL: no clip at all when no axis allows overflow — the scatter draws none either", () => {
    expect(clipRects(renderBoth(false).html)).toEqual([]);
  });
});
