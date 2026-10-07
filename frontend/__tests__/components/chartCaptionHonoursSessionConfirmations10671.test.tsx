// #10671 — the "last reading · none since" caption must not be contradicted by
// readings the page has already received.
//
// Specimen (production, live/0423Z): 15324650 MIL @ SD, live, 390px, main
// v5526. The served history (fixture, 04:17:22Z) stores `stat_model` only when
// its value changes: last row 04:11:24 0.9262, then the synthetic live edge at
// 04:17:21. The page's EventSource had meanwhile delivered the model's 0.9262
// again at 04:15:24 and 04:16:24 (then 0.8009 at 04:17:24). The chart printed
// "Bain Luck Model last reading 9:11 PM · none in the 5m since" and withdrew
// the model line after 9:11. The frames below are the SSE tap's, verbatim.
//
// Through the REAL component and the REAL merge the page uses
// (`mergeLiveChartHistory`), on the served payload. The served payload alone
// is the strawman: it must still caption, or this test proves nothing.

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
import { mergeLiveChartHistory, rememberLiveChartFrame, type LiveChartFrame } from "@/lib/liveChartHistory";
import { classifySeriesSupport, contractObservation } from "@/lib/chartObservationSupport";
import type { LiveStreamFrame } from "@/lib/liveStreamController";
import type { EventHistoryResponse, WinProbHistoryPoint } from "@/lib/types";

type Specimen = EventHistoryResponse & { status: string; commence_time: string; time_domain: { end: string }; aggregate_line: { timestamp: string; home_probability: number }[] };
const SERVED: Specimen = JSON.parse(
  readFileSync(join(__dirname, "..", "fixtures", "event-15324650-history-10671-live.json"), "utf8"),
);

const sse = (source: string, sourceValue: number, p: number, updatedAt: string, rev: number): LiveStreamFrame => ({
  event_id: 15324650, p, source, source_value: sourceValue, updated_at: updatedAt, status: "live",
  rev: { "15324650": rev },
} as LiveStreamFrame);
const FRAMES: LiveStreamFrame[] = [
  sse("stat_model", 0.9262, 0.8521, "2026-10-07T04:15:24.421108+00:00", 7000),
  sse("stat_model", 0.9262, 0.8233, "2026-10-07T04:16:24.731466+00:00", 7014),
  sse("stat_model", 0.8009, 0.7268, "2026-10-07T04:17:24.671078+00:00", 7022),
];
const buffer = (frames: LiveStreamFrame[]): LiveChartFrame[] =>
  frames.reduce<LiveChartFrame[]>((points, f) => rememberLiveChartFrame(points, f, 15324650), []);

function render(history: Specimen) {
  const domain = computeSharedChartDomain(history, "live", history.status, history.commence_time, "baseball_mlb");
  expect(domain).not.toBeNull();
  return renderToStaticMarkup(
    <OddsChart
      history={[]}
      homeTeam={history.home_team}
      awayTeam={history.away_team}
      isLive
      eventStatus={history.status}
      commenceTime={history.commence_time}
      commenceTimeIsKickoff={history.commence_time_is_kickoff}
      evidenceContract={history.evidence_contract}
      winProbHistory={history.win_prob_history}
      winProbSources={history.win_prob_sources}
      aggregateLine={history.aggregate_line}
      externalTimeRange="live"
      chartStartTime={domain!.start}
      chartEndTime={domain!.end}
      sharedTicks={domain!.ticks}
      chartLabelFormat={domain!.labelFormat}
    />,
  );
}
const modelCaption = (html: string) => /Bain Luck Model<\/span>\s*last reading/.test(html);
const trailing = (series: WinProbHistoryPoint[]) =>
  classifySeriesSupport(
    series.map((p) => contractObservation(p)!).filter(Boolean),
    { gameStartMs: Date.parse(SERVED.commence_time), domainEndMs: Date.parse(SERVED.time_domain.end), evidenceResolutionS: 300 },
  ).unsupported.filter((iv) => iv.kind === "trailing");

describe("#10671 — 15324650 (MIL @ SD, live): the caption reads the session's own confirmations", () => {
  test("the fixture is the shape the defect needs", () => {
    expect(SERVED.evidence_contract).toEqual({ v: "7878.v1", resolution_s: 300 });
    expect(SERVED.status).toBe("live");
    expect(SERVED.aggregate_line.length).toBeGreaterThan(0); // blended: source series are not extended
    const model = SERVED.win_prob_history!.stat_model;
    expect(model.slice(-2).map((p) => [p.timestamp, p.home_probability, p.live_edge ?? false])).toEqual([
      ["2026-10-07T04:11:24.662539+00:00", 0.9262, false],
      ["2026-10-07T04:17:21+00:00", 0.9262, true],
    ]);
  });

  test("strawman: the served payload alone captions the model — the production frame", () => {
    expect(trailing(SERVED.win_prob_history!.stat_model)).toHaveLength(1);
    const html = render(SERVED);
    expect(modelCaption(html)).toBe(true);
    expect(html).toMatch(/none in the\s*(<!-- -->)?\s*5m\s*(<!-- -->)?\s*since/);
  });

  test("with the frames the page held, the model is observed through 04:16:24 and nothing is captioned", () => {
    const merged = mergeLiveChartHistory(SERVED, buffer(FRAMES))!;
    const model = merged.win_prob_history!.stat_model;
    expect(model[model.length - 2].evidence).toEqual({ kind: "observed", covered_through: "2026-10-07T04:16:24.731466+00:00" });
    expect(trailing(model)).toHaveLength(0);
    expect(modelCaption(render(merged))).toBe(false);
  });

  test("evidence only: the same points, the same values; other sources keep their served arrays", () => {
    const merged = mergeLiveChartHistory(SERVED, buffer(FRAMES))!;
    const served = SERVED.win_prob_history!;
    const model = merged.win_prob_history!.stat_model;
    expect(model.map((p) => [p.timestamp, p.home_probability])).toEqual(served.stat_model.map((p) => [p.timestamp, p.home_probability]));
    expect(served.stat_model[served.stat_model.length - 2].evidence).toBeUndefined(); // response not mutated
    for (const key of ["kalshi", "polymarket", "mlb", "espn"]) expect(merged.win_prob_history![key]).toBe(served[key]);
  });

  test("a change first is not a confirmation: 0.8009 before 0.9262 leaves the caption", () => {
    const frames = [
      sse("stat_model", 0.8009, 0.80, "2026-10-07T04:15:24.421108+00:00", 7000),
      sse("stat_model", 0.9262, 0.82, "2026-10-07T04:16:24.731466+00:00", 7014),
    ];
    const merged = mergeLiveChartHistory(SERVED, buffer(frames))!;
    expect(merged.win_prob_history).toBe(SERVED.win_prob_history);
    expect(modelCaption(render(merged))).toBe(true);
  });

  test("another source's frames confirm nothing about the model", () => {
    const frames = [sse("kalshi", 0.9262, 0.85, "2026-10-07T04:16:24.731466+00:00", 7014)];
    expect(trailing(mergeLiveChartHistory(SERVED, buffer(frames))!.win_prob_history!.stat_model)).toHaveLength(1);
  });

  test("a confirmation older than the stored reading proves nothing new", () => {
    const frames = [sse("stat_model", 0.9262, 0.85, "2026-10-07T04:11:24.000000+00:00", 6900)];
    expect(mergeLiveChartHistory(SERVED, buffer(frames))!.win_prob_history).toBe(SERVED.win_prob_history);
  });
});

describe("#10671 — confirmServedSourceCoverage rules, on small series", () => {
  const t = (m: number, s = 0) => new Date(Date.UTC(2026, 9, 7, 4, m, s)).toISOString();
  const pt = (m: number, v: number, extra: Partial<WinProbHistoryPoint> = {}): WinProbHistoryPoint =>
    ({ timestamp: t(m), home_probability: v, away_probability: 1 - v, ...extra });
  const f = (m: number, v: number) => sse("stat_model", v, 0.7, t(m), m);

  test("a non-reading last point (candle) is left alone — fails closed", () => {
    const history = { aggregate_line: [{ timestamp: t(0), home_probability: 0.7 }], win_prob_history: {
      stat_model: [pt(1, 0.6), pt(2, 0.6, { evidence: { kind: "candle" } }), pt(9, 0.6, { live_edge: true })],
    } };
    expect(mergeLiveChartHistory(history, buffer([f(5, 0.6)]))!.win_prob_history).toBe(history.win_prob_history);
  });

  test("an existing `observed` span is only ever widened, never narrowed", () => {
    const wider = { stat_model: [pt(1, 0.6, { evidence: { kind: "observed", covered_through: t(8) } })] };
    const history = { aggregate_line: [{ timestamp: t(0), home_probability: 0.7 }], win_prob_history: wider };
    expect(mergeLiveChartHistory(history, buffer([f(5, 0.6)]))!.win_prob_history).toBe(wider);
    const narrower = { stat_model: [pt(1, 0.6, { evidence: { kind: "observed", covered_through: t(3) } })] };
    const out = mergeLiveChartHistory({ ...history, win_prob_history: narrower }, buffer([f(5, 0.6)]))!;
    expect(out.win_prob_history!.stat_model[0].evidence).toEqual({ kind: "observed", covered_through: t(5) });
  });

  test("single-source page: the confirmation and the push extension both land", () => {
    const history = { aggregate_line: [], win_prob_history: {
      stat_model: [pt(1, 0.6), pt(6, 0.6, { live_edge: true })],
    } };
    const out = mergeLiveChartHistory(history, buffer([f(4, 0.6), f(7, 0.55)]))!;
    const model = out.win_prob_history!.stat_model;
    expect(model[0].evidence).toEqual({ kind: "observed", covered_through: t(4) });
    expect(model.map((p) => [p.timestamp, p.home_probability])).toEqual([[t(1), 0.6], [t(6), 0.6], [t(7), 0.55]]);
  });
});
