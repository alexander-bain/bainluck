// #925 — THE RESTING READOUT CARRIES THE INNING THROUGH A SCORE-ONLY ROW.
//
// `/events/15318166` (Mets @ Rangers, MLB, live), 390px, 2026-09-24 19:47Z: the
// header read "Bottom 4th" and the readout under the chart, with no finger on
// it, read "—" over "12:45 PM". The served `espn_history` tail was
//
//   19:38:04Z  period "Bottom 4th"  clock null
//   19:39:08Z  period "Bottom 4th"  clock "0:00"
//   19:41:04Z  period null          clock null     ← score-only
//   19:43:04Z  period null          clock null
//   19:45:04Z  period null          clock null
//   19:47:04Z  period "End 4th"
//
// `computeLastChartPoint` took `lastEspn.period` raw, so for eight minutes of
// every such gap the resting readout had no inning at all. The hover path
// carries (`carryGameStateForward`), so the same minute read two ways.
//
// The real path is exercised: the rows go through `computeLastChartPoint`, and
// its output is handed to the real `GamePlayCard` as `lastPoint` — the prop the
// event page passes when nobody is holding the chart. jest pins TZ=UTC.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import GamePlayCard from "@/components/GamePlayCard";
import { computeLastChartPoint } from "@/lib/eventKeyStats";
import type { ESPNHistoryPoint, EventHistoryResponse } from "@/lib/types";

type Row = { at: string; period: string | null; clock: string | null };

function history(rows: Row[]): EventHistoryResponse {
  const partial: Partial<EventHistoryResponse> = {
    event_id: 15318166,
    home_team: "Texas Rangers",
    away_team: "New York Mets",
    history: [],
    espn_history: rows.map((r): ESPNHistoryPoint => ({
      timestamp: r.at,
      home_probability: 0.72,
      away_probability: 0.28,
      home_score: 2,
      away_score: 1,
      game_clock: r.clock,
      period: r.period,
    })),
  };
  return partial as EventHistoryResponse;
}

function resting(rows: Row[], sportKey: string): string {
  const lastPoint = computeLastChartPoint(history(rows), 2, 1);
  return renderToStaticMarkup(
    <GamePlayCard
      homeTeam="Texas Rangers"
      awayTeam="New York Mets"
      sportKey={sportKey}
      activePoint={null}
      lastPoint={lastPoint}
    />,
  );
}

const SPECIMEN: Row[] = [
  { at: "2026-09-24T19:38:04Z", period: "Bottom 4th", clock: null },
  { at: "2026-09-24T19:39:08Z", period: "Bottom 4th", clock: "0:00" },
  { at: "2026-09-24T19:41:04Z", period: null, clock: null },
  { at: "2026-09-24T19:43:04Z", period: null, clock: null },
  { at: "2026-09-24T19:45:04Z", period: null, clock: null },
];

describe("#925 the resting readout takes the newest reading of each field", () => {
  test("specimen: a score-only tail keeps the inning, marked carried and dated", () => {
    const p = computeLastChartPoint(history(SPECIMEN), 2, 1)!;
    expect(p.period).toBe("Bottom 4th");
    expect(p.periodApprox).toBe(true);
    expect(p.periodObservedAt).toBe("2026-09-24T19:39:08Z");

    const html = resting(SPECIMEN, "baseball_mlb");
    expect(html).toContain("~Bottom 4th");
    expect(html).toContain("as of 7:39 PM");
    // Baseball has no clock: the carried "0:00" must not surface (#6684).
    expect(html).not.toContain("0:00");
  });

  test("control: a last row that brings its own inning is exact and undated", () => {
    const rows = [...SPECIMEN, { at: "2026-09-24T19:47:04Z", period: "End 4th", clock: null }];
    const p = computeLastChartPoint(history(rows), 2, 1)!;
    expect(p.period).toBe("End 4th");
    expect(p.periodApprox).toBeUndefined();
    expect(p.periodObservedAt).toBeUndefined();

    const html = resting(rows, "baseball_mlb");
    expect(html).toContain("End 4th");
    expect(html).not.toContain("~End 4th");
    expect(html).not.toContain("as of");
  });

  test("period and clock are found independently: a clock-only row dates only the period", () => {
    const rows: Row[] = [
      { at: "2026-09-24T20:00:00Z", period: "4th Quarter", clock: "2:14" },
      { at: "2026-09-24T20:03:00Z", period: null, clock: "1:09" },
    ];
    const p = computeLastChartPoint(history(rows), 2, 1)!;
    expect(p.period).toBe("4th Quarter");
    expect(p.periodApprox).toBe(true);
    expect(p.periodObservedAt).toBe("2026-09-24T20:00:00Z");
    expect(p.clock).toBe("1:09");
    expect(p.clockApprox).toBeUndefined();
  });

  test("no inning ever observed: nothing is invented, the card keeps its '—'", () => {
    const rows: Row[] = [
      { at: "2026-09-24T19:41:04Z", period: null, clock: null },
      { at: "2026-09-24T19:43:04Z", period: null, clock: null },
    ];
    const p = computeLastChartPoint(history(rows), 2, 1)!;
    expect(p.period).toBeNull();
    expect(p.periodApprox).toBeUndefined();
    // Not `toContain("—")`: the card also prints "—" between the two teams'
    // percentages, so that assertion could never fail. What must hold is that
    // no inning and no age were invented.
    const html = resting(rows, "baseball_mlb");
    expect(html).not.toContain("~");
    expect(html).not.toContain("as of");
    expect(html).not.toMatch(/Top|Bottom|Middle|End \d/);
  });
});
