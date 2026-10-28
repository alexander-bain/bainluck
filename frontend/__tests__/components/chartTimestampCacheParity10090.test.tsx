/** @jest-environment jsdom */
// #10090 — the chart transform's timestamp→ms reuse changes no output. Real
// chart bodies (the live MLB fixture and the completed Michigan–Iowa history,
// whose All range holds more distinct timestamps than the 1,024 cap) render
// once through the cache and once through the plain parse, in the same root:
// the complete DOM and every row of the point map must be identical, every
// cached read must equal the plain parse of its input, and every call site of
// the cache in OddsChart must be exercised.
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { readFileSync } from "fs";
import { join } from "path";
import { parseISO } from "date-fns";
import * as gameState from "@/lib/chartGameState";
import * as timestampMs from "@/lib/chartTimestampMs";
import OddsChart from "@/components/OddsChart";

jest.mock("@/components/Analytics/AnalyticsProvider", () => ({
  useAnalyticsContext: () => ({ track() {} }),
}));
jest.mock("recharts", () => ({
  ...jest.requireActual("recharts"),
  ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
    React.cloneElement(children, { width: 390, height: 300 }),
}));
jest.mock("@/lib/chartTimestampMs", () => {
  const actual = jest.requireActual("@/lib/chartTimestampMs");
  return { ...actual, createChartTimestampMs: jest.fn(actual.createChartTimestampMs) };
});

const actual = jest.requireActual<typeof import("@/lib/chartTimestampMs")>("@/lib/chartTimestampMs");
const factory = timestampMs.createChartTimestampMs as jest.Mock;
const fixture = (name: string) => JSON.parse(readFileSync(join(__dirname, "../fixtures", name), "utf8"));
const mlb = fixture("periodLabelRightRule.15314713.mlb-live-t10.json");
const final = fixture("event-15313791-history-8967-final.json");

type Props = React.ComponentProps<typeof OddsChart>;
const bodyProps = (body: typeof mlb, sportKey: string): Props => ({
  history: body.history, bookmakerHistory: body.bookmaker_history,
  winProbHistory: body.win_prob_history, winProbSources: body.win_prob_sources,
  espnHistory: body.espn_history, scoreHistory: body.score_history,
  scoringPlays: body.scoring_plays, evidenceContract: body.evidence_contract,
  aggregateLine: body.aggregate_line, backendBlendServed: true,
  homeTeam: body.home_team, awayTeam: body.away_team, sportKey,
  commenceTime: body.commence_time, eventId: body.event_id,
});
const mlbLive: Props = {
  ...bodyProps(mlb, "baseball_mlb"), isLive: true, eventStatus: "live",
  chartStartTime: mlb.commence_time, chartEndTime: "2026-09-20T04:47:00Z",
};
const preview = [...mlb.aggregate_line, { timestamp: "2026-09-20T04:46:30.123456+00:00", home_probability: 0.55 }];
const publications = {
  event_id: mlb.event_id, schema_version: 1, time_basis: "recorded_at_insert_before_commit", truncated: false,
  vertices: [{ rev: 1, t: "2026-09-20T03:00:00Z", p: 0.3 }, { rev: 2, t: "2026-09-20T03:30:00Z", p: 0.6 }],
};
const finalProps: Props = {
  ...bodyProps(final, "americanfootball_ncaaf"), isLive: false, eventStatus: "completed",
  completedAt: final.completed_at,
};

const scenarios: [string, string, Props][] = [
  ["MLB live, live range", "2026-09-20T04:47:00Z", { ...mlbLive, externalTimeRange: "live" }],
  ["MLB live, all range, preview edge", "2026-09-20T04:47:00Z", { ...mlbLive, externalTimeRange: "all", chartStartTime: undefined, aggregateLine: preview }],
  ["MLB valid-until collision", "2026-09-20T04:47:00Z", { ...mlbLive, aggregateLine: preview, history: [
    { timestamp: "2026-09-20T04:40:15Z", home_probability: 0.4, away_probability: 0.6, valid_until: "2026-09-20T04:42:15Z" },
    { timestamp: "2026-09-20T04:42:20Z", home_probability: 0.7, away_probability: 0.3 },
  ] as Props["history"] }],
  ["MLB finished, recorded checkpoint window", "2026-09-20T04:47:00Z", { ...mlbLive, isLive: false, eventStatus: "completed", aggregateLine: preview, publications: publications as Props["publications"] }],
  ["Michigan–Iowa final, all range (over the cap)", "2026-09-26T23:30:00Z", { ...finalProps, externalTimeRange: "all" }],
  ["Michigan–Iowa final, default range", "2026-09-26T23:30:00Z", finalProps],
];

type Read = { input: string; output: number; line: number | null };

/** The cache, recording each read and the OddsChart line that made it. */
function recordingFactory(reads: Read[]) {
  return () => {
    const ms = actual.createChartTimestampMs();
    return (input: string) => {
      const output = ms(input);
      const frame = new Error().stack?.split("\n").find((l) => l.includes("OddsChart.tsx"));
      const line = frame?.match(/OddsChart\.tsx:(\d+):\d+/)?.[1];
      reads.push({ input, output, line: line ? Number(line) : null });
      return output;
    };
  };
}
const plainFactory = () => (input: string) => parseISO(input).getTime();

function rowShapes(map: Map<string, object>) {
  return [...map].map(([key, row]) => [key, Reflect.ownKeys(row).map((k) => {
    const v = (row as Record<string | symbol, unknown>)[k];
    return [k.toString(), Object.getOwnPropertyDescriptor(row, k)?.enumerable, v === undefined ? { absent: true } : JSON.parse(JSON.stringify(v))];
  })]);
}

/** OddsChart lines that call the per-transform cache (not the factory line). */
const sourceSiteLines = readFileSync(join(__dirname, "../../components/OddsChart.tsx"), "utf8")
  .split("\n")
  .map((text, i) => ({ text, line: i + 1 }))
  .filter(({ text }) => /\bchartTimestampMs\(/.test(text) && !text.includes("createChartTimestampMs"))
  .map(({ line }) => line);

const linesHit = new Set<number>();
let maxDistinct = 0;
let previousAct: unknown;
let stackLimit: number;
let stamp: jest.SpyInstance;
beforeAll(() => {
  previousAct = (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT;
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true;
  stackLimit = Error.stackTraceLimit;
  Error.stackTraceLimit = 4;
  stamp = jest.spyOn(gameState, "stampObservedGameState");
});
afterAll(() => {
  stamp.mockRestore();
  factory.mockImplementation(actual.createChartTimestampMs);
  Error.stackTraceLimit = stackLimit;
  (globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = previousAct;
});

describe("#10090 the timestamp cache changes no DOM, no row, and no parsed value on real chart bodies", () => {
  test.each(scenarios)("%s", async (name, now, props) => {
    jest.useFakeTimers().setSystemTime(Date.parse(now));
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    const reads: Read[] = [];
    // A fresh aggregate array each arm forces the transform to run again.
    const renderArm = async (impl: () => (input: string) => number) => {
      factory.mockImplementation(impl);
      const runs = factory.mock.calls.length;
      await act(async () => root.render(<OddsChart {...props} aggregateLine={[...(props.aggregateLine ?? [])]} />));
      expect(factory.mock.calls.length).toBeGreaterThan(runs);
      return { html: host.innerHTML, rows: rowShapes(stamp.mock.calls[stamp.mock.calls.length - 1][0] as Map<string, object>) };
    };
    try {
      const cached = await renderArm(recordingFactory(reads));
      const plain = await renderArm(plainFactory);
      const cachedAgain = await renderArm(recordingFactory([]));
      expect(cached.rows.length).toBeGreaterThan(0);
      expect({ name, rows: cached.rows }).toEqual({ name, rows: plain.rows });
      expect({ name, html: cached.html }).toEqual({ name, html: plain.html });
      expect({ name, html: cachedAgain.html }).toEqual({ name, html: plain.html });

      expect(reads.length).toBeGreaterThan(0);
      const wrong = reads.filter((r) => !Object.is(r.output, parseISO(r.input).getTime()));
      expect({ name, wrong }).toEqual({ name, wrong: [] });
      const distinct = new Set(reads.map((r) => r.input)).size;
      expect(distinct).toBeLessThan(reads.length); // the cache was actually reused
      maxDistinct = Math.max(maxDistinct, distinct);
      for (const r of reads) if (r.line !== null) linesHit.add(r.line);
    } finally {
      await act(async () => root.unmount());
      host.remove();
      jest.useRealTimers();
    }
  }, 60_000);

  test("one scenario holds more distinct timestamps than the cap, and every cache call site ran", () => {
    expect(sourceSiteLines.length).toBe(5); // 7 calls: the two sort comparators hold two each
    expect(maxDistinct).toBeGreaterThan(timestampMs.CHART_TIMESTAMP_MS_MAX_ENTRIES);
    expect([...linesHit].sort((a, b) => a - b)).toEqual(sourceSiteLines);
  });
});
