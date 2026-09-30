/**
 * #6158 — "SINCE START" OPENS WHEN PLAY WAS OBSERVED TO BEGIN, NOT AT THE SCHEDULED HOUR.
 *
 * Specimen: `/events/15321836`, White Sox @ Astros (MLB wild card, 2026-09-30),
 * read at 390px at 21:25Z. `commence_time` 21:00Z; the first served period
 * marker is `Top 1st` at 21:13:06Z (source `win_prob`), and the `stat_model` and
 * `mlb` game-state series both begin at 21:13Z. Both charts' "Since Start" axes
 * opened at 2:00 PM PT, so a flat pre-game stretch read as the first thirteen
 * minutes of the game. #6158's earlier specimens: 28 min (15318355) and 47 min
 * (15316297) late.
 *
 * Every arm that moves the start pairs with a control that must not move it:
 * a rule that cuts every game at its first observation would crop real play
 * wherever we started watching late.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";

import OddsChart from "@/components/OddsChart";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
import {
  OBSERVED_START_LEAD_MS,
  OBSERVED_START_MAX_DELAY_MS,
  observedPlayStartMs,
} from "@/lib/observedPlayStart";
import type { PeriodBoundary } from "@/lib/periodMarkers";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

// Fixed instants — offset first, never `Date.now()` (gotcha #44).
const COMMENCE = "2026-09-30T21:00:00.000Z";
const COMMENCE_MS = Date.parse(COMMENCE);
const T1_MS = Date.parse("2026-09-30T21:13:06.610Z");
const MIN = 60_000;
const iso = (ms: number) => new Date(ms).toISOString();

const T1: PeriodBoundary = { timestamp: iso(T1_MS), label: "T1", source: "win_prob" };
const B1: PeriodBoundary = { timestamp: iso(T1_MS + 17 * MIN), label: "B1", source: "win_prob" };

const pt = (ms: number, p: number) => ({
  timestamp: iso(ms),
  home_probability: p,
  away_probability: 1 - p,
});

/** Kalshi quotes every minute from the evening before through the Top 1st. */
const KALSHI = [
  pt(COMMENCE_MS - 23 * 60 * MIN, 0.58),
  ...Array.from({ length: 91 }, (_, i) => {
    const ms = COMMENCE_MS - 60 * MIN + i * MIN;
    return pt(ms, ms < T1_MS ? 0.58 : 0.46 - (ms - T1_MS) / (60 * MIN));
  }),
];
/** The game-state model, which has nothing before first pitch. */
const STAT_MODEL = Array.from({ length: 17 }, (_, i) => pt(T1_MS + i * MIN, 0.46 - i * 0.01));

const payload = (extra: Record<string, unknown> = {}) =>
  ({
    history: [],
    win_prob_history: { kalshi: KALSHI, stat_model: STAT_MODEL },
    ...extra,
  }) as never;

const liveStart = (boundaries?: PeriodBoundary[] | null, extra: Record<string, unknown> = {}) =>
  Date.parse(
    computeSharedChartDomain(payload(extra), "live", "live", COMMENCE, "baseball_mlb", boundaries)!
      .start,
  );

describe("#6158 observedPlayStartMs — the cut is evidence, never earlier than the schedule", () => {
  it("a late start cuts a lead-in before the first observed opening period", () => {
    expect(observedPlayStartMs(COMMENCE, [T1, B1])).toBe(T1_MS - OBSERVED_START_LEAD_MS);
  });

  it("a `notBefore` bound is never crossed: only known pre-game time is cut", () => {
    const notBefore = iso(T1_MS - 5 * MIN);
    expect(observedPlayStartMs(COMMENCE, [{ ...T1, notBefore }, B1])).toBe(T1_MS - 5 * MIN);
    // A bound before the schedule leaves nothing to cut.
    expect(observedPlayStartMs(COMMENCE, [{ ...T1, notBefore: iso(COMMENCE_MS - MIN) }])).toBeNull();
  });

  it("CONTROL — an on-time start is unchanged (the lead-in reaches back past the schedule)", () => {
    const onTime = { ...T1, timestamp: iso(COMMENCE_MS + 90_000) };
    expect(observedPlayStartMs(COMMENCE, [onTime])).toBeNull();
  });

  it("CONTROL — first seen mid-game (B1, T3) is not a start: we may have started watching late", () => {
    expect(observedPlayStartMs(COMMENCE, [B1])).toBeNull();
    expect(
      observedPlayStartMs(COMMENCE, [{ ...T1, label: "T3" }, { ...B1, timestamp: iso(T1_MS + 60 * MIN) }]),
    ).toBeNull();
  });

  it("CONTROL — an ESTIMATED opening boundary is arithmetic on the schedule, not evidence", () => {
    expect(observedPlayStartMs(COMMENCE, [{ ...T1, source: "estimated" }])).toBeNull();
  });

  it("CONTROL — an opening boundary hours out is not read as a late start", () => {
    const far = { ...T1, timestamp: iso(COMMENCE_MS + OBSERVED_START_MAX_DELAY_MS + MIN) };
    expect(observedPlayStartMs(COMMENCE, [far])).toBeNull();
  });

  it("the earliest boundary decides, whatever order they arrive in", () => {
    expect(observedPlayStartMs(COMMENCE, [B1, T1])).toBe(T1_MS - OBSERVED_START_LEAD_MS);
  });

  it("opening labels across sports; a bare `1` (unit unknown) is not one", () => {
    for (const label of ["Q1", "P1", "1H", "R1", "T1"]) {
      expect(observedPlayStartMs(COMMENCE, [{ ...T1, label }])).toBe(T1_MS - OBSERVED_START_LEAD_MS);
    }
    expect(observedPlayStartMs(COMMENCE, [{ ...T1, label: "1" }])).toBeNull();
  });

  it("no boundaries, no schedule — nothing to say", () => {
    expect(observedPlayStartMs(COMMENCE, [])).toBeNull();
    expect(observedPlayStartMs(COMMENCE, null)).toBeNull();
    expect(observedPlayStartMs(undefined, [T1])).toBeNull();
  });
});

describe("#6158 computeSharedChartDomain — both charts' 'Since Start' window", () => {
  it("the specimen opens at the observed Top 1st (minute-snapped), not at 21:00Z", () => {
    const start = liveStart([T1, B1]);
    expect(start).toBe(Date.parse("2026-09-30T21:11:00.000Z"));
    expect(start).toBeGreaterThan(COMMENCE_MS);
    expect(start).toBeLessThanOrEqual(T1_MS);
  });

  it("CONTROL — without boundaries it still cuts at the scheduled hour (today's behaviour)", () => {
    expect(liveStart()).toBe(COMMENCE_MS);
    expect(liveStart(null)).toBe(COMMENCE_MS);
  });

  it("CONTROL — 'All' does not move", () => {
    const withIt = computeSharedChartDomain(payload(), "all", "live", COMMENCE, "baseball_mlb", [T1]);
    const without = computeSharedChartDomain(payload(), "all", "live", COMMENCE, "baseball_mlb");
    expect(withIt!.start).toBe(without!.start);
  });

  it("CONTROL — a served `commence_time_is_kickoff: false` still declines every start cut (#8215)", () => {
    const allStart = Date.parse(KALSHI[0].timestamp);
    expect(liveStart([T1], { commence_time_is_kickoff: false })).toBe(
      new Date(allStart).setSeconds(0, 0),
    );
  });
});

type ChartProps = Partial<React.ComponentProps<typeof OddsChart>>;

/** The FULLSCREEN shape: no `chartStartTime`, so the chart's own fallback cuts. */
function drawFullscreen(overrides: ChartProps = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={[]}
        homeTeam="Houston Astros"
        awayTeam="Chicago White Sox"
        commenceTime={COMMENCE}
        eventStatus="live"
        isLive
        winProbHistory={{ kalshi: KALSHI, stat_model: STAT_MODEL } as never}
        externalTimeRange="live"
        {...overrides}
      />,
    ),
  );
}

const drawnStartMs = (html: string): number => {
  const match = html.match(/data-drawn-extent="([^"]*)"/);
  if (!match || match[1] === "") throw new Error("no drawn extent on the chart wrapper");
  return Number(match[1].split(",")[0]);
};

describe("#6158 the fullscreen chart opens at the same instant as the inline one", () => {
  it("with the page's boundaries, its first drawn point is after the lead-in cut", () => {
    const start = drawnStartMs(drawFullscreen({ periodBoundaries: [T1, B1] }));
    expect(start).toBeGreaterThanOrEqual(T1_MS - OBSERVED_START_LEAD_MS);
    expect(start).toBeLessThanOrEqual(T1_MS);
  });

  it("CONTROL — without boundaries it still draws from the scheduled hour", () => {
    expect(drawnStartMs(drawFullscreen())).toBe(COMMENCE_MS);
  });

  it("the event page hands the boundaries to the shared domain", () => {
    const source = fs.readFileSync(path.join(process.cwd(), "app/events/[id]/page.tsx"), "utf8");
    const call = source.slice(source.indexOf("computeSharedChartDomain("));
    const args = call.slice(0, call.indexOf(")"));
    expect(args).toMatch(/periodBoundaries/);
  });
});
