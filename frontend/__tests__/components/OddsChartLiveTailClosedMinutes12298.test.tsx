// #12298 — a live window kept open grows no strokes behind the live edge.
//
// THE DEFECT. #10093 inks a minute's within-minute low-to-high as a vertical
// stroke. It was computed for EVERY live minute, so each minute the window
// watched kept one: on Yale–Brown (Nov 7, 10:21 AM) the open chart carried a
// thin spike every minute or two after the point where history ended, while a
// reload — one value a minute — drew none. On a thin book a minute's high or
// low is often a midpoint that quoted for seconds.
//
// THE SHIP. Only the CURRENT minute (the one holding the newest observation)
// keeps its stroke — #10093's own scope. A closed minute is drawn as its last
// published blend, which is the point the line already passes through.
//
// Rig: RECORDED production traffic, through the page's own path — frames via
// `rememberLiveChartFrame` → `quoteChartFrames` → `mergeLiveChartHistory` onto
// the history read the page held — rendered at 390px.

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

import OddsChart, { currentMinuteRange, intraMinuteRanges } from "@/components/OddsChart";
import {
  mergeLiveChartHistory, quoteChartFrames, rememberLiveChartFrame, type LiveChartFrame,
} from "@/lib/liveChartHistory";
import type { EventHistoryResponse } from "@/lib/types";
import type { LiveStreamFrame } from "@/lib/liveStreamController";

type Recording = { served: EventHistoryResponse; frames: LiveStreamFrame[]; hero: Parameters<typeof quoteChartFrames>[1] };
const load = (name: string): Recording =>
  JSON.parse(readFileSync(join(__dirname, "../fixtures", name), "utf8"));

const pageHistory = ({ served, frames, hero }: Recording, eventId: number) =>
  mergeLiveChartHistory(served, quoteChartFrames(
    frames.reduce<LiveChartFrame[]>((points, f) => rememberLiveChartFrame(points, f, eventId), []), hero,
  ))!;

const render = (body: EventHistoryResponse, start: string, end: string) =>
  renderToStaticMarkup(<OddsChart
    history={body.history} bookmakerHistory={body.bookmaker_history}
    aggregateLine={body.aggregate_line ?? undefined}
    winProbHistory={body.win_prob_history} winProbSources={body.win_prob_sources}
    backendBlendServed homeTeam="Home" awayTeam="Away"
    isLive eventStatus="live" commenceTime={start} chartStartTime={start} chartEndTime={end}
  />);

const strokes = (html: string) =>
  [...html.matchAll(/<line[^>]*data-minute-range-lo="([^"]+)"[^>]*data-minute-range-hi="([^"]+)"[^>]*>/g)]
    .map(m => ({ lo: Number(m[1]), hi: Number(m[2]) }));

/** The last value the stream published in each minute, from the recording itself. */
const lastPublishedByMinute = (frames: LiveStreamFrame[]) => {
  const out = new Map<string, { at: number; p: number }>();
  for (const f of frames) {
    const at = Date.parse(f.updated_at);
    const key = new Date(Math.floor(at / 60000) * 60000).toISOString();
    if (!out.has(key) || out.get(key)!.at < at) out.set(key, { at, p: f.p as number });
  }
  return out;
};
const lastDrawnByMinute = (line: Array<{ timestamp: string; home_probability: number }>) => {
  const out = new Map<string, { at: number; p: number }>();
  for (const point of line) {
    const at = Date.parse(point.timestamp);
    const key = new Date(Math.floor(at / 60000) * 60000).toISOString();
    if (!out.has(key) || out.get(key)!.at < at) out.set(key, { at, p: point.home_probability });
  }
  return out;
};

describe("#12298 Holy Cross at Georgetown (FCS), recorded: the thin-book excursion stays off closed minutes", () => {
  const rec = load("event-15342596-live-12298.json");
  const body = pageHistory(rec, 15342596);
  const html = render(body, "2026-11-07T20:30:00Z", "2026-11-07T20:48:00Z");

  it("CONTROL: the recorded minutes really did swing — 20:46 published 24.7 to 32.9 inside one minute", () => {
    const all = intraMinuteRanges(body.aggregate_line!);
    const m46 = all.get("2026-11-07T20:46:00.000Z")!;
    expect(m46.lo).toBeCloseTo(24.7, 1);
    expect(m46.hi).toBeCloseTo(32.9, 1);
    expect(all.has("2026-11-07T20:45:00.000Z")).toBe(true);
  });

  it("draws one stroke, on the current minute (20:47) only, spanning what it published", () => {
    const drawn = strokes(html);
    expect(drawn).toHaveLength(1);
    expect(drawn[0].lo).toBeCloseTo(25.7, 1);
    expect(drawn[0].hi).toBeCloseTo(26.3, 1);
    expect(drawn.some(s => s.hi > 30)).toBe(false);
  });

  it("every minute the stream published in ends on its last published blend", () => {
    const published = lastPublishedByMinute(rec.frames);
    const drawn = lastDrawnByMinute(body.aggregate_line!);
    for (const [minute, { p }] of published) {
      if (minute === "2026-11-07T20:47:00.000Z") continue; // the served edge at 20:47:32 carries the same 26.3
      expect(drawn.get(minute)!.p).toBeCloseTo(p, 9);
    }
  });
});

describe("#12298 Arkansas at Auburn, a recorded live session: a window kept open grows no strokes", () => {
  const rec = load("event-15339961-live-session-12298.json");
  const body = pageHistory(rec, 15339961);
  const first = rec.frames[0].updated_at;
  const last = rec.frames[rec.frames.length - 1].updated_at;

  it("CONTROL: before #12298 this session inked a stroke on most of the minutes it watched", () => {
    const watched = [...intraMinuteRanges(body.aggregate_line!).keys()].filter(k => k >= first.slice(0, 16));
    expect(watched.length).toBeGreaterThanOrEqual(10);
  });

  it("at most one stroke, and only on the minute holding the newest observation", () => {
    const html = render(body, "2026-11-07T20:35:00Z", new Date(Date.parse(last) + 120000).toISOString());
    expect(strokes(html).length).toBeLessThanOrEqual(1);
    const kept = currentMinuteRange(body.aggregate_line!);
    expect(kept.size).toBeLessThanOrEqual(1);
    const newest = body.aggregate_line!.reduce((a, b) => (Date.parse(b.timestamp) > Date.parse(a.timestamp) ? b : a));
    for (const key of kept.keys()) {
      expect(key).toBe(new Date(Math.floor(Date.parse(newest.timestamp) / 60000) * 60000).toISOString());
    }
  });

  it("every closed minute the stream published in ends on its last published blend — the movement that happened", () => {
    const published = lastPublishedByMinute(rec.frames);
    const drawn = lastDrawnByMinute(body.aggregate_line!);
    const lastMinute = new Date(Math.floor(Date.parse(last) / 60000) * 60000).toISOString();
    let checked = 0;
    for (const [minute, { p }] of published) {
      if (minute >= lastMinute) continue;
      expect(drawn.get(minute)!.p).toBeCloseTo(p, 9);
      checked += 1;
    }
    expect(checked).toBeGreaterThanOrEqual(10);
  });
});

describe("currentMinuteRange", () => {
  it("keeps only the newest minute's range; a quiet newest minute keeps nothing", () => {
    const pts = [
      { timestamp: "2026-11-07T20:46:04Z", home_probability: 0.33 },
      { timestamp: "2026-11-07T20:46:37Z", home_probability: 0.25 },
      { timestamp: "2026-11-07T20:47:05Z", home_probability: 0.26 },
      { timestamp: "2026-11-07T20:47:18Z", home_probability: 0.27 },
    ];
    expect([...currentMinuteRange(pts).keys()]).toEqual(["2026-11-07T20:47:00.000Z"]);
    expect(currentMinuteRange(pts.slice(0, 3)).size).toBe(0);
    expect(currentMinuteRange([{ timestamp: "x", home_probability: 0.5 }, { timestamp: "2026-11-07T20:47:18Z", home_probability: null }]).size).toBe(0);
  });
});
