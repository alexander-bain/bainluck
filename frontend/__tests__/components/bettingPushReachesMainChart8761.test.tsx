import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";
import { mergeLiveChartHistory, rememberLiveChartFrame } from "@/lib/liveChartHistory";
import type { EventHistoryResponse } from "@/lib/types";
import type { LiveStreamFrame } from "@/lib/liveStreamController";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  useAnalyticsContext: () => ({ track: () => {} }),
}));
jest.mock("recharts", () => ({
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }),
}));
import OddsChart from "@/components/OddsChart";

// Live624's actual /history response before the 15:23:22 betting quote.
const served: EventHistoryResponse = JSON.parse(readFileSync(
  join(__dirname, "../fixtures/event-15315386-history-8761.json"), "utf8",
));
const frame = (extra = {}): LiveStreamFrame => ({
  event_id: 15315386, source: "betting", source_value: .2944, p: .2944,
  updated_at: "2026-09-26T15:23:22.513Z", status: "live", ...extra,
});
const merge = (f = frame(), body = served) => mergeLiveChartHistory(
  body, rememberLiveChartFrame([], f, 15315386),
)!;

describe("#8761 betting frames reach the existing main sportsbook line", () => {
  it("renders the page's 390px chart at the pushed quote before another history response", () => {
    expect(served.aggregate_line).toBeNull();
    expect(served.win_prob_history).toEqual({});
    expect(served.history).toHaveLength(66);
    const html = (body: EventHistoryResponse) => renderToStaticMarkup(<OddsChart
      history={body.history} bookmakerHistory={body.bookmaker_history}
      aggregateLine={body.aggregate_line ?? undefined}
      winProbHistory={body.win_prob_history} winProbSources={body.win_prob_sources}
      backendBlendServed={false} homeTeam="Swindon Town" awayTeam="Accrington Stanley"
      isLive eventStatus="live" commenceTime="2026-09-26T14:00:00Z"
      chartStartTime="2026-09-26T14:00:00Z" chartEndTime="2026-09-26T15:24:00Z"
    />);
    expect(html(served)).toContain('data-callout-label="30%"');
    expect(html(merge())).toContain('data-callout-label="29%"');
    expect(html(merge())).not.toContain("Bain Luck");
  });

  it("preserves the actual betting value/clock, without inventing a bookmaker or away probability", () => {
    const result = merge(frame({ p: .8 })); // Deliberately distinguish source from blend.
    expect(result.history.at(-1)).toEqual({
      timestamp: frame().updated_at, home_probability: .2944, away_probability: null,
      over_under: null, projected_home_score: null, projected_away_score: null,
      bookmaker: "aggregate",
    });
    expect(result.history.slice(0, -1)).toEqual(served.history);
    expect(result.bookmaker_history).toBe(served.bookmaker_history);
    expect(result.win_prob_history).toBe(served.win_prob_history);
    expect(served.history).toHaveLength(66);
  });

  it.each([
    { source: "kalshi" }, { source_value: null }, { source_value: -1 },
    { source_value: 1.1 }, { updated_at: "invalid" },
    { updated_at: "2026-09-26T15:20:30Z" },
    { updated_at: served.history.at(-1)!.timestamp },
  ])("does not overwrite sportsbook history with unusable or older readings: %j", extra => {
    expect(merge(frame(extra)).history).toBe(served.history);
  });

  it("does not manufacture betting history or alter its historical line when a served blend is primary", () => {
    const empty = { ...served, history: [] };
    expect(merge(frame(), empty).history).toBe(empty.history);
    const blended = { ...served, aggregate_line: [{ timestamp: "2026-09-26T15:21:00Z", home_probability: .7 }] };
    expect(merge(frame(), blended).history).toBe(served.history);
  });

  it("retains changed observations through stale polls, but equally/newer served readings win", () => {
    let points = rememberLiveChartFrame([], frame(), 15315386);
    points = rememberLiveChartFrame(points, frame({ updated_at: "2026-09-26T15:24:01Z", source_value: .27, p: .27 }), 15315386);
    expect(mergeLiveChartHistory(served, points)!.history.slice(-2).map(p => p.home_probability)).toEqual([.2944, .27]);
    const caughtUp = { ...served, history: [...served.history, { ...served.history.at(-1)!, timestamp: frame().updated_at, home_probability: .293 }] };
    expect(mergeLiveChartHistory(caughtUp, points)!.history.slice(-2).map(p => p.home_probability)).toEqual([.293, .27]);
    const validUntil = { ...served, history: [{ ...served.history.at(-1)!, valid_until: "2026-09-26T15:24:00Z" }] };
    expect(merge(frame(), validUntil).history).toBe(validUntil.history);
  });
});
