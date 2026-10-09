// #10090 — the live chart's endpoint moves with the accepted headline, and a
// later automatic history poll does not take it back.
//
// THE DEFECT (production, 15319175 Lens v Lyon, 390px held page 19:19:51Z–
// 19:21:12Z). Polymarket rev 218 (0.37, 19:20:28.820Z) reached the headline in
// 23 ms. The final screenshot, 43 s later, read 37% over a chart endpoint of
// 36% — rev 217's value. Two ways in this path drop 218, and either one is
// enough to freeze the line one revision behind the headline:
//   1. The automatic history poll (served 19:20:57Z). This is a single-source
//      page, so the line is `win_prob_history.polymarket`. The backend stored
//      0.36 at 19:20:19.59 and never stored 218, and the response ends in the
//      synthetic `live_edge` at 19:20:57 carrying that stored 0.36. The push
//      extension only appended readings strictly newer than the served edge,
//      so 218 (behind the edge but ahead of the stored reading the edge
//      carries) was dropped.
//   2. `quoteChartFrames` (found by ux at 1940Z). A newer revision with 218's
//      price and clock makes frame 218 "older", AT the held clock, and the
//      strict `at < heldAt` refused the very reading the headline shows.
//
// Rig: the page's own path, with frames going through `rememberLiveChartFrame`
// → `quoteChartFrames` → `mergeLiveChartHistory` onto a RECONSTRUCTED 19:20:57Z
// poll body (the captured response was not retained; the fixture's
// `_provenance` says how it was built). The real `OddsChart` renders it at
// 390px. The frames are the eleven the harness
// recorded, verbatim.

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

import OddsChart from "@/components/OddsChart";
import {
  mergeLiveChartHistory, quoteChartFrames, rememberLiveChartFrame, type LiveChartFrame,
} from "@/lib/liveChartHistory";
import type { EventHistoryResponse } from "@/lib/types";
import type { LiveStreamFrame } from "@/lib/liveStreamController";

const EVENT_ID = 15319175;
const served: EventHistoryResponse = JSON.parse(readFileSync(
  join(__dirname, "../fixtures/event-15319175-history-10090-tail.json"), "utf8",
));

const RECORDED: Array<[number, number, string]> = [
  [208, 0.38, "2026-10-09T19:19:52.857503+00:00"],
  [209, 0.385, "2026-10-09T19:19:55.434679+00:00"],
  [210, 0.425, "2026-10-09T19:19:56.257275+00:00"],
  [211, 0.415, "2026-10-09T19:19:56.464553+00:00"],
  [212, 0.39, "2026-10-09T19:19:58.813779+00:00"],
  [213, 0.385, "2026-10-09T19:19:59.147869+00:00"],
  [214, 0.37, "2026-10-09T19:20:07.311993+00:00"],
  [215, 0.365, "2026-10-09T19:20:10.170169+00:00"],
  [216, 0.37, "2026-10-09T19:20:13.116331+00:00"],
  [217, 0.36, "2026-10-09T19:20:19.705652+00:00"],
  [218, 0.37, "2026-10-09T19:20:28.820452+00:00"],
];
const frames: LiveStreamFrame[] = RECORDED.map(([rev, p, updated_at]) => ({
  event_id: EVENT_ID, p, source: "polymarket", source_value: p, updated_at,
  status: "live", rev: { [EVENT_ID]: rev },
}));
/** The held headline after `applyLiveFrame` took the last recorded frame. */
const heroAfter = (rev: number) => {
  const [, p, at] = RECORDED.find(([r]) => r === rev)!;
  return {
    status: "live", hero_probability: p, hero_probability_source: "blend",
    hero_probability_observed_at: at, blend_fold_revision: { [EVENT_ID]: rev },
  };
};
const pageHistory = (through: number, body: EventHistoryResponse = served) => {
  const points = frames.slice(0, through - 208 + 1)
    .reduce<LiveChartFrame[]>((acc, f) => rememberLiveChartFrame(acc, f, EVENT_ID), []);
  return mergeLiveChartHistory(body, quoteChartFrames(points, heroAfter(through)))!;
};
const render = (body: EventHistoryResponse) => renderToStaticMarkup(<OddsChart
  history={body.history} bookmakerHistory={body.bookmaker_history}
  aggregateLine={body.aggregate_line ?? undefined}
  winProbHistory={body.win_prob_history} winProbSources={body.win_prob_sources}
  backendBlendServed={false} homeTeam="Racing Club de Lens" awayTeam="Olympique Lyonnais"
  isLive eventStatus="live" commenceTime="2026-10-09T18:45:00+00:00"
  chartStartTime="2026-10-09T18:45:00Z" chartEndTime="2026-10-09T19:21:12Z"
/>);
const callout = (html: string) => /data-callout-label="([^"]+)"/.exec(html)?.[1];
const series = (body: EventHistoryResponse) => body.win_prob_history!.polymarket;

describe("#10090 the chart endpoint follows the accepted reading through a later history poll", () => {
  it("rev 218 drives the line's end and its label after the 19:20:57 poll: 37%, as the headline", () => {
    const body = pageHistory(218);
    const html = render(body);
    expect(callout(html)).toBe("37%");
    // The reading lands at its own time, before the edge, and the edge — still
    // the backend's synthetic delivery point at its own time — carries it.
    const tail = series(body).slice(-2);
    expect(tail[0]).toEqual({
      timestamp: "2026-10-09T19:20:28.820452+00:00", home_probability: 0.37, away_probability: null,
    });
    expect(tail[1]).toMatchObject({
      timestamp: "2026-10-09T19:20:57+00:00", home_probability: 0.37,
      live_edge: true, evidence: { kind: "live_edge" },
    });
  });

  it("CONTROL: with the stream at rev 217 the same body ends at 36% — the served value is right for 217", () => {
    // 217 (19:20:19.705Z) is a hair after the stored 0.36 (19:20:19.591Z) and
    // carries the same price, so the edge has nothing to change.
    const body = pageHistory(217);
    expect(callout(render(body))).toBe("36%");
    expect(series(body).at(-1)!.home_probability).toBe(0.36);
  });

  it("CONTROL: the served body alone ends at 36% — the fixture really is the frozen shape", () => {
    expect(callout(render(served))).toBe("36%");
    expect(series(served).at(-1)).toMatchObject({ live_edge: true, home_probability: 0.36 });
  });

  it("keeps history honest: the stored readings are untouched and nothing is drawn backwards", () => {
    const body = pageHistory(218);
    // Value and time of every stored reading as served. (The last one may gain
    // #10671's `observed` coverage from rev 217's equal price — evidence only.)
    const before = series(served).slice(0, -1);
    const plain = (pts: typeof before) => pts.map(p => [p.timestamp, p.home_probability]);
    expect(plain(series(body).slice(0, before.length))).toEqual(plain(before));
    const times = series(body).map(p => Date.parse(p.timestamp));
    expect([...times].sort((a, b) => a - b)).toEqual(times);
    // Interior frames (209–216 sit between stored readings) are not inserted.
    // 217 (19:20:19.705, a hair after the stored 19:20:19.591) repeats 0.36, so
    // it is coverage on the stored reading (#10671), not a point; only 218 and
    // the edge follow.
    expect(series(body)[before.length - 1].evidence).toEqual({
      kind: "observed", covered_through: "2026-10-09T19:20:19.705652+00:00",
    });
    expect(series(body).slice(before.length).map(p => p.timestamp)).toEqual([
      "2026-10-09T19:20:28.820452+00:00", "2026-10-09T19:20:57+00:00",
    ]);
    expect(served.win_prob_history!.polymarket.at(-1)!.home_probability).toBe(0.36);
  });

  describe("a newer revision that kept 218's price and clock (ux 1940Z, quoteChartFrames boundary)", () => {
    // The revision bumps on ANY bag change (wps_revision.py trigger), so the
    // headline can hold rev 219 stamped with rev 218's own clock and price.
    // Frame 218 is then "older", AT the held clock: the reading the headline
    // shows. The strict `at < heldAt` refused it and the line ended on 36%.
    const points = () => frames
      .reduce<LiveChartFrame[]>((acc, f) => rememberLiveChartFrame(acc, f, EVENT_ID), []);
    const held219 = (over: object = {}) => ({ ...heroAfter(218), blend_fold_revision: { [EVENT_ID]: 219 }, ...over });

    it("held rev 219 at 218's clock: 218 is admitted and the endpoint reads 37%, as the headline", () => {
      const admitted = quoteChartFrames(points(), held219());
      expect(admitted.at(-1)!.timestamp).toBe("2026-10-09T19:20:28.820452+00:00");
      const body = mergeLiveChartHistory(served, admitted)!;
      expect(callout(render(body))).toBe("37%");
      expect(series(body).at(-1)).toMatchObject({ live_edge: true, home_probability: 0.37 });
    });

    it("REFUSES: a frame at the held clock with a DIFFERENT value is not the headline's reading", () => {
      const admitted = quoteChartFrames(points(), held219({ hero_probability: 0.4 }));
      expect(admitted.map(p => p.timestamp)).not.toContain("2026-10-09T19:20:28.820452+00:00");
    });

    it("FAILS CLOSED: an unknown held clock admits no older frame (the served 36% stands)", () => {
      const admitted = quoteChartFrames(points(), held219({ hero_probability_observed_at: null }));
      expect(admitted).toEqual([]);
      expect(callout(render(mergeLiveChartHistory(served, admitted)!))).toBe("36%");
    });
  });

  it("a reading the headline refused (an older fold revision) never moves the endpoint", () => {
    // The held headline is at rev 218; a delayed rev-216-stamped 0.42 with a
    // clock after the held observation must not reach the line.
    const late: LiveStreamFrame = {
      event_id: EVENT_ID, p: 0.42, source: "polymarket", source_value: 0.42,
      updated_at: "2026-10-09T19:20:40+00:00", status: "live", rev: { [EVENT_ID]: 216 },
    };
    const points = [...frames, late]
      .reduce<LiveChartFrame[]>((acc, f) => rememberLiveChartFrame(acc, f, EVENT_ID), []);
    const hero = { ...heroAfter(218), hero_probability_observed_at: "2026-10-09T19:20:30+00:00" };
    const body = mergeLiveChartHistory(served, quoteChartFrames(points, hero))!;
    expect(callout(render(body))).toBe("37%");
    expect(series(body).map(p => p.home_probability)).not.toContain(0.42);
  });
});
