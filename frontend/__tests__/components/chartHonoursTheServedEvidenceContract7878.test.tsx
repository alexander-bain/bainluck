// #7878 (web consumer of the producer contract) — through the REAL component,
// on a REAL production payload that carries `evidence_contract`.
//
// The pre-contract chart judged holes by a cadence heuristic with a 10-minute
// floor, so a source that went quiet for six minutes in-game was still drawn
// as one solid line. Codex's card-B decision set G = 300s as the display
// evidence resolution and the producer now serves it; a wider interval is
// UNKNOWN and the solid line must lift there. The same payload with the
// contract removed is the control: it must render exactly as before.
//
// Reads the SVG recharts emitted (pen-downs in the path's `d`), not
// `chartData`. Rig shared with chartStopsDrawingAcrossAHoleNobodyObserved7878.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  __esModule: true,
  useAnalyticsContext: () => ({ track: () => {} }),
  AnalyticsProvider: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

import OddsChart from "@/components/OddsChart";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import type { EventHistoryResponse } from "@/lib/types";

interface Curve {
  d: string;
  stroke: string;
  dasharray: string | null;
}
function curves(html: string): Curve[] {
  return (html.match(/<path[^>]*recharts-line-curve[^>]*>/g) ?? []).map((tag) => ({
    d: /\sd="([^"]*)"/.exec(tag)?.[1] ?? "",
    stroke: /stroke="([^"]+)"/.exec(tag)?.[1] ?? "",
    dasharray: /stroke-dasharray="([^"]+)"/.exec(tag)?.[1] ?? null,
  }));
}
const penDowns = (d: string) => d.split("M").map((s) => s.trim()).filter(Boolean).length;
const isConnector = (c: Curve) => c.dasharray === "2 5";
const solid = (html: string, color: string) => curves(html).find((c) => c.stroke === color && !isConnector(c));
const connector = (html: string, color: string) => curves(html).find((c) => c.stroke === color && isConnector(c));

const SPECIMEN: EventHistoryResponse & { status: string; commence_time: string } = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "event-15318166-history-7878-contract.json"), "utf8"),
);
const KALSHI = SPECIMEN.win_prob_sources!.kalshi.color;
const MLB = SPECIMEN.win_prob_sources!.mlb.color;

function render(evidenceContract: EventHistoryResponse["evidence_contract"]) {
  const domain = computeSharedChartDomain(SPECIMEN, "live", SPECIMEN.status, SPECIMEN.commence_time, "baseball_mlb");
  expect(domain).not.toBeNull();
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam={SPECIMEN.home_team}
      awayTeam={SPECIMEN.away_team}
      isLive={false}
      eventStatus={SPECIMEN.status}
      commenceTime={SPECIMEN.commence_time}
      commenceTimeIsKickoff={SPECIMEN.commence_time_is_kickoff}
      evidenceContract={evidenceContract}
      winProbHistory={SPECIMEN.win_prob_history}
      winProbSources={SPECIMEN.win_prob_sources}
      externalTimeRange="live"
      chartStartTime={domain!.start}
      chartEndTime={domain!.end}
      sharedTicks={domain!.ticks}
      chartLabelFormat={domain!.labelFormat}
    />,
  );
}

/** In-game intervals wider than `s` seconds, read straight off the fixture. */
function inGameWider(source: string, s: number): number {
  const start = Date.parse(SPECIMEN.commence_time);
  const pts = SPECIMEN.win_prob_history![source].map((p) => Date.parse(p.timestamp));
  let n = 0;
  for (let i = 1; i < pts.length; i++) if (pts[i - 1] >= start && pts[i] - pts[i - 1] > s * 1000) n++;
  return n;
}

describe("#7878 — 15318166 (Mets @ Rangers, completed) with the served contract", () => {
  test("the fixture is the shape these assertions are about", () => {
    expect(SPECIMEN.evidence_contract).toEqual({ v: "7878.v1", resolution_s: 300 });
    expect(SPECIMEN.status).toBe("completed");
    expect(SPECIMEN.commence_time_is_kickoff).toBe(true);
    expect(inGameWider("kalshi", 300)).toBe(0);
    // Five MLB intervals are 359–480s: over G, under the heuristic's 600s floor.
    expect(inGameWider("mlb", 300)).toBe(5);
    expect(inGameWider("mlb", 600)).toBe(0);
    for (const pts of Object.values(SPECIMEN.win_prob_history!)) {
      expect(pts[pts.length - 2].evidence).toEqual({ kind: "terminal_row" });
      expect(pts[pts.length - 1].evidence).toEqual({ kind: "final" });
    }
  });

  test("contract: the MLB line lifts at each of its five unproven stretches, bridged by a faint connector", () => {
    const html = render(SPECIMEN.evidence_contract);
    const mlb = solid(html, MLB);
    expect(mlb).toBeDefined();
    expect(penDowns(mlb!.d)).toBe(6);
    expect(connector(html, MLB)).toBeDefined();
  });

  test("contract: Kalshi, whose in-game readings are never more than G apart, stays ONE solid line", () => {
    const html = render(SPECIMEN.evidence_contract);
    const kalshi = solid(html, KALSHI);
    expect(kalshi).toBeDefined();
    expect(penDowns(kalshi!.d)).toBe(1);
    expect(connector(html, KALSHI)).toBeUndefined();
  });

  test("control — the same payload WITHOUT the contract renders as before: MLB is one unbroken line", () => {
    const html = render(undefined);
    expect(penDowns(solid(html, MLB)!.d)).toBe(1);
    expect(connector(html, MLB)).toBeUndefined();
    expect(penDowns(solid(html, KALSHI)!.d)).toBe(1);
  });

  test("a contract version this client does not know is the control, not a guess", () => {
    const html = render({ v: "7878.v2", resolution_s: 300 });
    expect(penDowns(solid(html, MLB)!.d)).toBe(1);
  });

  test("a finished game carries no stale-edge caption either way", () => {
    expect(render(SPECIMEN.evidence_contract)).not.toContain('data-testid="chart-stale-edges"');
    expect(render(undefined)).not.toContain('data-testid="chart-stale-edges"');
  });
});
