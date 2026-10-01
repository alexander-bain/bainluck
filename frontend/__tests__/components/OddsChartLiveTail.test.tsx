// #10093 — a live spike and reversal inside one minute stays on the chart.
//
// THE DEFECT. `OddsChart` buckets by minute on a categorical axis, so every
// accepted push frame inside a minute writes the same point and the last one
// wins. `liveChartHistory` already keeps each publication at its own time; the
// renderer folded them. A live .42 → .55 → .43 inside one minute drew a flat
// .43 while the headline had just printed 55%.
//
// THE SHIP. The minute keeps its last reading on the line (that is the number
// the hero and the callout print) and inks its real low-to-high as a vertical
// stroke at that minute, in the primary line's colour, while the game is live.
//
// Rig: the page's own path — frames through `rememberLiveChartFrame` →
// `quoteChartFrames` → `mergeLiveChartHistory` — onto a REAL production
// /history body (15322164, Harris/Hsieh doubles, live, Kalshi + Polymarket +
// the served blend, read 2026-10-01 17:41Z), rendered at 390px.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

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

import OddsChart, { intraMinuteRanges } from "@/components/OddsChart";
import {
  mergeLiveChartHistory, quoteChartFrames, rememberLiveChartFrame, type LiveChartFrame,
} from "@/lib/liveChartHistory";
import type { EventHistoryResponse } from "@/lib/types";
import type { LiveStreamFrame } from "@/lib/liveStreamController";

const EVENT_ID = 15322164;
const COMMENCE = "2026-10-01T15:00:00+00:00"; // the body's own commence_time
const served: EventHistoryResponse = JSON.parse(readFileSync(
  join(__dirname, "../fixtures/event-15322164-history-10093.json"), "utf8",
));
// The detail payload's headline half, as production served it at 17:42Z.
const hero = {
  status: "live", hero_probability: 0.25, hero_probability_source: "blend",
  hero_probability_observed_at: "2026-10-01T17:42:06.171658+00:00",
  blend_fold_revision: { [EVENT_ID]: 221 },
};
const frame = (updated_at: string, p: number, rev = 222): LiveStreamFrame => ({
  event_id: EVENT_ID, p, source: "kalshi", source_value: p, updated_at,
  status: "live", rev: { [EVENT_ID]: rev },
});
/** The acceptance sequence: one rally and its reversal inside 17:43. */
const SPIKE = [
  frame("2026-10-01T17:42:30Z", 0.40),
  frame("2026-10-01T17:43:05Z", 0.42),
  frame("2026-10-01T17:43:25Z", 0.55),
  frame("2026-10-01T17:43:50Z", 0.43),
];

const remember = (frames: LiveStreamFrame[]) =>
  frames.reduce<LiveChartFrame[]>((points, f) => rememberLiveChartFrame(points, f, EVENT_ID), []);
const pageHistory = (frames: LiveStreamFrame[]) =>
  mergeLiveChartHistory(served, quoteChartFrames(remember(frames), hero))!;

const render = (body: EventHistoryResponse, live: { isLive: boolean; eventStatus: string } = { isLive: true, eventStatus: "live" }) =>
  renderToStaticMarkup(<OddsChart
    history={body.history} bookmakerHistory={body.bookmaker_history}
    aggregateLine={body.aggregate_line ?? undefined}
    winProbHistory={body.win_prob_history} winProbSources={body.win_prob_sources}
    backendBlendServed homeTeam="Harris/Hsieh" awayTeam="Lammons/Withrow"
    isLive={live.isLive} eventStatus={live.eventStatus} commenceTime={COMMENCE}
    chartStartTime="2026-10-01T15:00:00Z" chartEndTime="2026-10-01T17:44:00Z"
  />);

// Whole percents for readability in the assertions; the attributes carry the
// raw 0–100 axis values the stroke was drawn from.
const pct = (tag: string, attr: string) => Math.round(Number(new RegExp(`${attr}="([^"]+)"`).exec(tag)?.[1]));
const ranges = (html: string) =>
  [...html.matchAll(/<line[^>]*data-minute-range-lo[^>]*>/g)].map(m => ({
    label: `${pct(m[0], "data-minute-range-lo")}%-${pct(m[0], "data-minute-range-hi")}%`,
    y1: Number(/\sy1="([^"]+)"/.exec(m[0])?.[1]),
    y2: Number(/\sy2="([^"]+)"/.exec(m[0])?.[1]),
    stroke: /\sstroke="([^"]+)"/.exec(m[0])?.[1],
  }));
const callout = (html: string) => /data-callout-label="([^"]+)"/.exec(html)?.[1];
const BLEND_EMERALD = "#059669";

describe("#10093 a live within-minute spike and reversal stays on the web chart", () => {
  it("draws the minute's real 42%–55% range, and the line still ends on the 43% the hero holds", () => {
    const html = render(pageHistory(SPIKE));
    const drawn = ranges(html);
    expect(drawn).toHaveLength(1);
    expect(drawn[0].label).toBe("42%-55%");
    expect(drawn[0].stroke).toBe(BLEND_EMERALD);
    // A visible stroke, top above bottom, both inside the 300px frame: the
    // y-axis was widened for the 55%, not clipped at it.
    expect(drawn[0].y2 - drawn[0].y1).toBeGreaterThan(20);
    expect(drawn[0].y1).toBeGreaterThan(0);
    expect(drawn[0].y2).toBeLessThan(300);
    expect(callout(html)).toBe("43%");
  });

  it("the exact-time tail reaches the chart intact; a minute category alone keeps only its last reading", () => {
    const body = pageHistory(SPIKE);
    const minute = body.aggregate_line!.filter(p => p.timestamp.startsWith("2026-10-01T17:43"));
    expect(minute.map(p => p.home_probability)).toEqual([0.42, 0.55, 0.43]);
    // The exact-time tail survives delivery; the category keeps only the last.
    const range = intraMinuteRanges(minute).get("2026-10-01T17:43:00.000Z")!;
    expect(range.lo).toBeCloseTo(42, 9);
    expect(range.hi).toBeCloseTo(55, 9);
    expect(intraMinuteRanges(minute.slice(-1)).size).toBe(0);
  });

  it("CONTROL: the served payload alone draws nothing — its 17:41 minute holds two readings of the SAME 25%", () => {
    const sameValueMinute = served.aggregate_line!.filter(p => p.timestamp.startsWith("2026-10-01T17:41"));
    expect(sameValueMinute.map(p => p.home_probability)).toEqual([0.25, 0.25]);
    const html = render(served);
    expect(ranges(html)).toEqual([]);
    expect(callout(html)).toBe("25%");
  });

  it("CONTROL: a quiet tail — frames that never change value — draws no range and nothing moves", () => {
    const quiet = [
      frame("2026-10-01T17:43:05Z", 0.25), frame("2026-10-01T17:43:25Z", 0.25),
      frame("2026-10-01T17:43:50Z", 0.25),
    ];
    expect(ranges(render(pageHistory(quiet)))).toEqual([]);
  });

  it("CONTROL: the same body on a finished event draws no range — the settled ending is not this change's", () => {
    const body = pageHistory(SPIKE);
    expect(ranges(render(body, { isLive: false, eventStatus: "completed" }))).toEqual([]);
    expect(ranges(render(body, { isLive: false, eventStatus: "live" }))).toEqual([]);
  });

  it("out-of-order arrival orders by observation time: the line ends on the newest reading, not the last delivered", () => {
    const shuffled = [SPIKE[0], SPIKE[3], SPIKE[1], SPIKE[2]];
    const html = render(pageHistory(shuffled));
    expect(ranges(html).map(r => r.label)).toEqual(["42%-55%"]);
    expect(callout(html)).toBe("43%");
  });

  it("a frame the headline refused (older fold revision, newer clock) inks nothing", () => {
    const refused = [SPIKE[0], SPIKE[1], frame("2026-10-01T17:43:25Z", 0.55, 220), SPIKE[3]];
    const html = render(pageHistory(refused));
    expect(ranges(html).map(r => r.label)).toEqual(["42%-43%"]);
    expect(html).not.toContain("55%");
  });

  it("a single-source live line (no served blend) gets the range on its own source series", () => {
    const kalshiOnly: EventHistoryResponse = {
      ...served, aggregate_line: undefined,
      win_prob_history: { kalshi: served.win_prob_history!.kalshi },
      win_prob_sources: { kalshi: served.win_prob_sources!.kalshi },
    };
    const body = mergeLiveChartHistory(kalshiOnly, remember(SPIKE))!;
    const html = renderToStaticMarkup(<OddsChart
      history={body.history} bookmakerHistory={body.bookmaker_history}
      aggregateLine={body.aggregate_line ?? undefined}
      winProbHistory={body.win_prob_history} winProbSources={body.win_prob_sources}
      backendBlendServed={false} homeTeam="Harris/Hsieh" awayTeam="Lammons/Withrow"
      isLive eventStatus="live" commenceTime={COMMENCE}
      chartStartTime="2026-10-01T15:00:00Z" chartEndTime="2026-10-01T17:44:00Z"
    />);
    const drawn = ranges(html);
    expect(drawn.map(r => r.label)).toEqual(["42%-55%"]);
    expect(drawn[0].stroke).toBe("#22c55e");
    expect(callout(html)).toBe("43%");
  });

  it("intraMinuteRanges reads only real observations: nulls, bad clocks and one-reading minutes add nothing", () => {
    expect(intraMinuteRanges([
      { timestamp: "2026-10-01T17:43:05Z", home_probability: 0.42 },
      { timestamp: "2026-10-01T17:43:25Z", home_probability: null },
      { timestamp: "not a time", home_probability: 0.9 },
      { timestamp: "2026-10-01T17:44:10Z", home_probability: 0.1 },
    ]).size).toBe(0);
  });
});
