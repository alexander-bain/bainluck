// #10795 — a single-source live chart keeps the real dip it already drew when
// the next automatic history refresh lands.
//
// THE SPECIMEN (Root's retained capture, chart-tail-10791-review/reader-check-04fe,
// event 15325669, Polymarket the only source). The frames below are the
// capture's own, byte for byte: 0.565 → 0.525 → 0.51 → 0.565 inside 20:18:32–33.
// hist2 (first history response after them) drew the dip; hist3 (the next)
// dropped it while the endpoint correctly stayed on the current reading.
//
// THE SERVED BODIES ARE RECONSTRUCTED. The capture kept response status and
// cache headers, not history bodies. What is known: the backend stores sparse
// rows, so the dip itself was never stored, and by hist3 it had stored a row
// later than 20:18:32 (rev 245's 0.575 at 20:19:14.655 arrived 1.4 s before
// that request). The shapes below are the smallest bodies with those facts.
//
// THE CAUSE. `extendServedSourceSeries` kept only readings strictly after the
// last served real reading. That is right for the ENDPOINT, but applied to
// every reading it meant one later sparse row erased the excursion. A blended
// page never lost it: `aggregate_line` keeps every session frame. The
// within-minute range (#10093) can only ink what is still in the series.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

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

import OddsChart from "@/components/OddsChart";
import {
  mergeLiveChartHistory, quoteChartFrames, rememberLiveChartFrame, type LiveChartFrame,
} from "@/lib/liveChartHistory";
import type { LiveStreamFrame } from "@/lib/liveStreamController";
import type { EventHistoryResponse, WinProbHistoryPoint } from "@/lib/types";

const EVENT_ID = 15325669;
const frame = (rev: number, p: number, updated_at: string): LiveStreamFrame => ({
  event_id: EVENT_ID, p, source: "polymarket", source_value: p, updated_at,
  status: "live", rev: { [EVENT_ID]: rev },
});
// Verbatim from 15325669-hold.json, rev 235–245.
const CAPTURED = [
  frame(235, 0.58, "2026-10-09T20:18:13.400445+00:00"),
  frame(236, 0.575, "2026-10-09T20:18:21.762458+00:00"),
  frame(237, 0.58, "2026-10-09T20:18:28.983621+00:00"),
  frame(238, 0.575, "2026-10-09T20:18:31.365713+00:00"),
  frame(239, 0.565, "2026-10-09T20:18:31.550921+00:00"),
  frame(240, 0.525, "2026-10-09T20:18:32.432652+00:00"),
  frame(241, 0.51, "2026-10-09T20:18:32.87208+00:00"),
  frame(242, 0.565, "2026-10-09T20:18:33.048728+00:00"),
  frame(243, 0.56, "2026-10-09T20:18:36.158038+00:00"),
  frame(244, 0.58, "2026-10-09T20:18:41.562106+00:00"),
];
const REV_245 = frame(245, 0.575, "2026-10-09T20:19:14.655063+00:00");
const DIP = ["2026-10-09T20:18:32.432652+00:00", "2026-10-09T20:18:32.87208+00:00", "2026-10-09T20:18:33.048728+00:00"];

const hero = (last: LiveStreamFrame) => ({
  status: "live", hero_probability: last.p, hero_probability_source: "blend",
  hero_probability_observed_at: last.updated_at, blend_fold_revision: last.rev,
});
const remember = (frames: LiveStreamFrame[]) =>
  frames.reduce<LiveChartFrame[]>((points, f) => rememberLiveChartFrame(points, f, EVENT_ID), []);
const wp = (timestamp: string, v: number | null, extra: Partial<WinProbHistoryPoint> = {}): WinProbHistoryPoint => ({
  timestamp, home_probability: v, away_probability: v === null ? null : 1 - v, ...extra,
});
const edge = (timestamp: string, v: number) => wp(timestamp, v, { live_edge: true, evidence: { kind: "live_edge" } });

const body = (series: WinProbHistoryPoint[]): EventHistoryResponse => ({
  event_id: EVENT_ID, home_team: "Montevideo City Torque", away_team: "Danubio",
  history: [], bookmaker_history: {}, aggregate_line: undefined,
  win_prob_history: { polymarket: series },
  win_prob_sources: { polymarket: { display_name: "Polymarket", type: "market", color: "#2563eb", snapshot_count: series.length } },
} as unknown as EventHistoryResponse);
// hist2: last stored row is rev 235's reading; the edge is the serve minute.
const HIST2 = body([wp("2026-10-09T20:10:00+00:00", 0.57), wp("2026-10-09T20:18:13.400445+00:00", 0.58), edge("2026-10-09T20:18:45+00:00", 0.58)]);
// hist3: a later sparse row (rev 245's 0.575) is stored; the dip never was.
const HIST3 = body([
  wp("2026-10-09T20:10:00+00:00", 0.57), wp("2026-10-09T20:18:13.400445+00:00", 0.58),
  wp("2026-10-09T20:19:14.655063+00:00", 0.575), edge("2026-10-09T20:19:17+00:00", 0.575),
]);

const page = (served: EventHistoryResponse, frames: LiveStreamFrame[]) =>
  mergeLiveChartHistory(served, quoteChartFrames(remember(frames), hero(frames[frames.length - 1])))!;
const render = (b: EventHistoryResponse) => renderToStaticMarkup(<OddsChart
  history={b.history} bookmakerHistory={b.bookmaker_history}
  aggregateLine={b.aggregate_line ?? undefined}
  winProbHistory={b.win_prob_history} winProbSources={b.win_prob_sources}
  backendBlendServed={false} homeTeam="Montevideo City Torque" awayTeam="Danubio"
  isLive eventStatus="live" commenceTime="2026-10-09T20:00:00+00:00"
  chartStartTime="2026-10-09T20:00:00Z" chartEndTime="2026-10-09T20:20:00Z"
/>);
const pct = (tag: string, attr: string) => Math.round(Number(new RegExp(`${attr}="([^"]+)"`).exec(tag)?.[1]));
const ranges = (html: string) =>
  [...html.matchAll(/<line[^>]*data-minute-range-lo[^>]*>/g)]
    .map(m => `${pct(m[0], "data-minute-range-lo")}%-${pct(m[0], "data-minute-range-hi")}%`);
const callout = (html: string) => /data-callout-label="([^"]+)"/.exec(html)?.[1];
const at = (series: WinProbHistoryPoint[], ts: string) => series.find(p => p.timestamp === ts)?.home_probability;

describe("#10795 the dip drawn on a single-source live chart survives the next history refresh", () => {
  it("hist2: the dip is the trailing tail, drawn as the 20:18 minute's 51%–58% range", () => {
    const html = render(page(HIST2, CAPTURED));
    expect(ranges(html)).toEqual(["51%-58%"]);
  });

  it("hist3 (sparse REST refresh): the same dip stays, and the line still ends on the current reading", () => {
    const merged = page(HIST3, [...CAPTURED, REV_245]);
    const series = merged.win_prob_history!.polymarket;
    expect(DIP.map(ts => at(series, ts))).toEqual([0.525, 0.51, 0.565]);
    // The endpoint is untouched: the served row and edge, in place, last.
    expect(series.slice(-2)).toEqual(HIST3.win_prob_history!.polymarket.slice(-2));
    const html = render(merged);
    expect(ranges(html)).toEqual(["51%-58%"]);
    expect(callout(html)).toBe("58%");
  });

  it("CONTROL: the served hist3 alone draws no range (the dip was never stored)", () => {
    expect(ranges(render(HIST3))).toEqual([]);
  });

  it("served wins an exact-time tie: rev 235 and rev 245 add no second point at their instants", () => {
    const series = page(HIST3, [...CAPTURED, REV_245]).win_prob_history!.polymarket;
    const instants = series.map(p => p.timestamp);
    expect(new Set(instants).size).toBe(instants.length);
    expect(series.filter(p => p.timestamp === "2026-10-09T20:18:13.400445+00:00")).toHaveLength(1);
    // Strictly time-ordered.
    expect(instants.map(Date.parse)).toEqual([...instants.map(Date.parse)].sort((a, b) => a - b));
  });
});

describe("#10795 controls: what an interior session reading may NOT do", () => {
  const T = (s: number) => new Date(Date.UTC(2026, 9, 9, 20, 18, s)).toISOString();
  const f = (s: number, p: number, rev: number) => frame(rev, p, T(s));
  const merge = (series: WinProbHistoryPoint[], frames: LiveStreamFrame[]) =>
    page(body(series), frames).win_prob_history!.polymarket;

  it("a quiet interval (every reading equals the served value) adds nothing — that is #10671's coverage, not a line", () => {
    const series = [wp(T(0), 0.58), wp(T(50), 0.6), edge(T(55), 0.6)];
    expect(merge(series, [f(10, 0.58, 1), f(20, 0.58, 2), f(30, 0.58, 3)])).toBe(series);
  });

  it("one differing reading keeps its whole run, the return included", () => {
    const series = [wp(T(0), 0.58), wp(T(50), 0.6), edge(T(55), 0.6)];
    const out = merge(series, [f(10, 0.58, 1), f(20, 0.51, 2), f(30, 0.58, 3)]);
    expect(out.map(p => p.home_probability)).toEqual([0.58, 0.58, 0.51, 0.58, 0.6, 0.6]);
  });

  it("the backend's observed proof wins: nothing inside an observed point's covered_through", () => {
    const series = [
      wp(T(0), 0.58, { evidence: { kind: "observed", covered_through: T(40) } }),
      wp(T(50), 0.6), edge(T(55), 0.6),
    ];
    expect(merge(series, [f(20, 0.51, 1), f(30, 0.58, 2)])).toBe(series);
    // After the proof's end, the excursion is admitted.
    const out = merge(series, [f(42, 0.51, 1), f(45, 0.58, 2)]);
    expect(out.map(p => p.home_probability)).toEqual([0.58, 0.51, 0.58, 0.6, 0.6]);
  });

  it("nothing before the first served point, and nothing after a served point with no number (a gap stays open)", () => {
    const series = [wp(T(10), 0.58), wp(T(20), null), wp(T(50), 0.6), edge(T(55), 0.6)];
    expect(merge(series, [f(5, 0.4, 1), f(30, 0.4, 2), f(40, 0.45, 3)])).toBe(series);
  });

  it("the endpoint rules are unchanged: a newer reading still moves the synthetic edge, and the interior run rides along", () => {
    const series = [wp(T(0), 0.58), wp(T(30), 0.6), edge(T(55), 0.6)];
    const out = merge(series, [f(10, 0.51, 1), f(20, 0.58, 2), f(40, 0.62, 3)]);
    expect(out.map(p => [p.timestamp, p.home_probability])).toEqual([
      [T(0), 0.58], [T(10), 0.51], [T(20), 0.58], [T(30), 0.6], [T(40), 0.62], [T(55), 0.62],
    ]);
    expect(out[out.length - 1].live_edge).toBe(true);
  });

  it("a blended page is untouched: the backend's blend line carries the push, source series keep their served points", () => {
    const series = [wp(T(0), 0.58), wp(T(50), 0.6), edge(T(55), 0.6)];
    const blended = { ...body(series), aggregate_line: [{ timestamp: T(0), home_probability: 0.58 }] };
    const merged = page(blended, [f(10, 0.58, 1), f(20, 0.51, 2), f(30, 0.58, 3)]);
    expect(merged.win_prob_history!.polymarket).toBe(series);
  });
});
