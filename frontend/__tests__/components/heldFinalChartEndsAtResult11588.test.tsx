// #11588 — a page held open through the final draws the chart a fresh load
// draws: the line's end label and the resting readout both read the result.
//
// Rig: the page's finished arm — `finishedChartFrames` and
// `appendAdmittedSourceObservations` over the session's admitted bank, then
// `mergeLiveChartHistory` — onto a REAL production finished /history body
// (15313791, Iowa 20–19 at Michigan, read 2026-09-26; #8967's fixture), drawn
// by the real `OddsChart` at 390px. The body carries the result the way the
// backend serves it: the blend line's LAST element (23:04:00, the minute play
// ended, floored — out of time order after a post-final 23:06 market minute)
// and an `evidence.kind: "final"` point on every source series. The game row
// was written at 23:04:41, so live readings at 23:04:xx sit inside the
// completion bound and inside the result's minute.
//
// THE DEFECT, at 534d8748: the held page's end label and readout read live
// numbers under a Final hero (production 15334266: 82% and 71%), while a
// fresh load of the same body read the result.

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
  admitChartFrames, appendAdmittedSourceObservations, finishedChartFrames, mergeLiveChartHistory,
  rememberLiveChartFrame, type LiveChartFrame,
} from "@/lib/liveChartHistory";
import { computeLastChartPoint, computeSharedChartDomain } from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";
import type { LiveStreamFrame } from "@/lib/liveStreamController";

const EVENT_ID = 15313791;
const COMMENCE = "2026-09-26T19:30:00+00:00"; // the body's own commence_time
const served: EventHistoryResponse = JSON.parse(readFileSync(
  join(__dirname, "../fixtures/event-15313791-history-8967-final.json"), "utf8",
));
const frame = (updated_at: string, p: number, rev: number): LiveStreamFrame => ({
  event_id: EVENT_ID, p, source: "kalshi", source_value: p, updated_at, status: "live", rev: { [EVENT_ID]: rev },
});
const completed = {
  id: EVENT_ID, status: "completed", completed_at: served.completed_at, blend_fold_revision: { [EVENT_ID]: 226 },
};

/** What the open page composes after the finish: a pre-result reading at
 * 23:03:40, then the last live reading at 23:04:20, on the blend and on the
 * game-end sources the detail was carrying. */
function heldPage(lastLive: number): EventHistoryResponse {
  const frames = [frame("2026-09-26T23:03:40Z", 0.62, 224), frame("2026-09-26T23:04:20Z", lastLive, 225)];
  const remembered = frames.reduce<LiveChartFrame[]>((points, f) => rememberLiveChartFrame(points, f, EVENT_ID), []);
  const held = {
    status: "live", hero_probability: lastLive, hero_probability_source: "blend",
    hero_probability_observed_at: "2026-09-26T23:04:20Z", blend_fold_revision: { [EVENT_ID]: 225 },
  };
  const admitted = {
    ...admitChartFrames(EVENT_ID, remembered, held),
    sourcePoints: ["espn", "stat_model", "kalshi"].flatMap(source => [
      { timestamp: "2026-09-26T23:03:40Z", source, source_probability: 0.62, rev: { [EVENT_ID]: 224 } },
      { timestamp: "2026-09-26T23:04:20Z", source, source_probability: lastLive, rev: { [EVENT_ID]: 225 } },
    ]),
  };
  const observed = appendAdmittedSourceObservations(served, admitted, completed)!;
  return mergeLiveChartHistory(observed, finishedChartFrames(admitted, EVENT_ID, completed, served))!;
}

const draw = (body: EventHistoryResponse) => {
  const domain = computeSharedChartDomain(body, "live", "completed", COMMENCE, "americanfootball_ncaaf", null);
  return renderToStaticMarkup(<OddsChart
    history={body.history} bookmakerHistory={body.bookmaker_history}
    aggregateLine={body.aggregate_line ?? undefined}
    winProbHistory={body.win_prob_history} winProbSources={body.win_prob_sources}
    espnHistory={body.espn_history} evidenceContract={body.evidence_contract}
    backendBlendServed homeTeam="Michigan" awayTeam="Iowa"
    isLive={false} eventStatus="completed" commenceTime={COMMENCE}
    completedAt={body.completed_at ?? undefined}
    chartStartTime={domain?.start} chartEndTime={domain?.end}
  />);
};
const callout = (html: string) => /data-callout-label="([^"]+)"/.exec(html)?.[1];
const readout = (body: EventHistoryResponse) => computeLastChartPoint(body, 19, 20, null, null, "completed")?.homeProb;

describe("#11588 a held finished chart ends on the result, the same as a fresh load", () => {
  it("the fresh load: the served body ends on Iowa's win — label and readout read the result", () => {
    expect(callout(draw(served))).toBe("0%");
    expect(readout(served)).toBe(0);
  });

  it.each([
    ["the loser (Michigan 71%)", 0.71],
    ["the winner short of the result (Iowa 71%)", 0.29],
  ])("held through the final, last live reading favouring %s: the same label and readout", (_side, lastLive) => {
    const held = heldPage(lastLive);
    expect(callout(draw(held))).toBe(callout(draw(served)));
    expect(readout(held)).toBe(readout(served));
  });
});
