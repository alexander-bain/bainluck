/**
 * #10090 — WITHOUT THE OPT-IN, THE HERO AND THE CHART ARE MASTER'S, BYTE FOR BYTE.
 *
 * Alex chose to live with one-decimal headlines before deciding (Speed,
 * 2026-10-28), so the change ships switched off for everyone who has not opened
 * `?tenths=fit` (`lib/tenthsOptIn.ts`). "Off" has to mean today's page, not a
 * page that looks like it: same markup, same classes, same inline styles.
 *
 * The digests below were taken by running THIS FILE, unchanged, on origin/master
 * `2cd03b0354` (before the opt-in existed) with `TENTHS_PRINT_DIGESTS=1`. On
 * master the `tenths` prop does not exist and is ignored, so the same cases
 * render there. Here every case renders twice, with the prop absent (every
 * reader who never opted in) and with `tenths={false}` (the page's hook before
 * and without an opt-in), and both must hash to master's markup.
 *
 * Snapshotted once, while master was the BEFORE (notice 50): do not refresh the
 * digests from a tree that has the opt-in. If a later, unrelated change to the
 * hero or the chart moves them, retire this file with the opt-in, or re-take them
 * from that change's own parent.
 *
 * Cases: a live two-sided pair, a `>99` / `<1` band pair, a venue-settled
 * contest, an away-withheld (draw-priced) slot, a pair arriving by push
 * (`animate`), a pair with no away reading; the chart live mid-game, live in
 * the `>99` band, and completed.
 */

import React from "react";
import { createHash } from "crypto";
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

import EventHeroProbabilityPair from "@/components/EventHeroProbabilityPair";
import OddsChart from "@/components/OddsChart";

/** Fixed anchor — never `Date.now()` (gotcha #44). */
const START = Date.UTC(2026, 9, 25, 18, 0, 0);
const N = 60;
const NOW = START + N * 60_000;

type HeroProps = React.ComponentProps<typeof EventHeroProbabilityPair>;
type ChartProps = React.ComponentProps<typeof OddsChart>;

const HERO_CASES: Record<string, HeroProps> = {
  live: { homeProb: 0.6234, awayProb: 0.3766, homePct: 62, awayPct: 38, started: true },
  band: { homeProb: 0.996, awayProb: 0.004, homePct: 100, awayPct: 0, started: true },
  settled: {
    homeProb: 1, awayProb: 0, homePct: 100, awayPct: 0, started: true, venueSettled: true,
  },
  withheld: { homeProb: 0.4175, awayProb: 0.5825, homePct: 42, awayPct: 58, awayWithheld: true },
  animated: { homeProb: 0.5125, awayProb: 0.4875, homePct: 51, awayPct: 49, started: true, animate: true },
  noAway: { homeProb: 0.42, awayProb: null, homePct: 42, awayPct: null },
};

/** A minute series that drifts and ends at `endPct` (0–100). */
function series(endPct: number) {
  return Array.from({ length: N }, (_, i) => {
    const p = i === N - 1 ? endPct : 55 + 8 * Math.sin(i * 0.4);
    return {
      timestamp: new Date(START + i * 60_000).toISOString(),
      home_probability: p / 100,
      away_probability: 1 - p / 100,
    };
  });
}

function chartProps(endPct: number, status: "live" | "completed"): ChartProps {
  return {
    history: [],
    homeTeam: "Lens",
    awayTeam: "Lyon",
    commenceTime: new Date(START).toISOString(),
    isLive: status === "live",
    eventStatus: status,
    chartStartTime: new Date(START).toISOString(),
    chartEndTime: new Date(START + (N - 1) * 60_000).toISOString(),
    winProbHistory: { kalshi: series(endPct) },
    winProbSources: {
      kalshi: { display_name: "Kalshi", color: "#22c55e", type: "market", snapshot_count: N },
    },
  };
}

const CHART_CASES: Record<string, ChartProps> = {
  live: chartProps(36.75, "live"),
  band: chartProps(99.7, "live"),
  completed: chartProps(100, "completed"),
};

const HERO_STYLE = { homeColor: "#111827", awayColor: "#94A3B8" };

/**
 * recharts numbers its ids from module counters (`recharts12-clip`,
 * `clipPath-recharts-line-3`), so they depend on how many charts rendered
 * before this one; the count is not the render.
 */
const normalise = (html: string) => html.replace(/recharts(-[a-z]+)*-?\d+/g, (m) => m.replace(/\d+$/, "N"));
const digest = (html: string) => {
  const n = normalise(html);
  return `${createHash("sha256").update(n).digest("hex").slice(0, 16)}:${n.length}`;
};

// The `tenths` prop is passed through an untyped spread so this file still runs
// on master, where the prop does not exist (see the header).
const hero = (props: HeroProps, extra: Record<string, unknown> = {}) =>
  renderToStaticMarkup(<EventHeroProbabilityPair {...HERO_STYLE} {...props} {...extra} />);
const chart = (props: ChartProps, extra: Record<string, unknown> = {}) =>
  renderToStaticMarkup(<OddsChart {...props} {...extra} />);

/** Taken on origin/master 2cd03b0354 — see the header. Never refreshed. */
const MASTER: Record<string, string> = {
  "hero:live": "3ece61ac54a0e831:1037",
  "hero:band": "44d9bb64b42e0d50:1219",
  "hero:settled": "213ddb01e000bd2a:1032",
  "hero:withheld": "a7c30d81b342ad99:617",
  "hero:animated": "778f6e9f27030228:1037",
  "hero:noAway": "37e1cbb892fe36c3:1034",
  "chart:live": "ab0f104d2054733f:40176",
  "chart:band": "28bb930f913f3b85:39848",
  "chart:completed": "d9b06d38d03f0921:40064",
};

beforeAll(() => {
  jest.useFakeTimers();
  jest.setSystemTime(NOW);
});
afterAll(() => jest.useRealTimers());

describe("#10090 the opt-in's OFF render is master's markup", () => {
  if (process.env.TENTHS_PRINT_DIGESTS === "1") {
    it("prints the digests (run on master only)", () => {
      const out: Record<string, string> = {};
      for (const [k, p] of Object.entries(HERO_CASES)) out[`hero:${k}`] = digest(hero(p));
      for (const [k, p] of Object.entries(CHART_CASES)) out[`chart:${k}`] = digest(chart(p));
      // eslint-disable-next-line no-console
      console.log(`TENTHS_DIGESTS ${JSON.stringify(out)}`);
    });
    return;
  }

  it("is not vacuous: the chart laid out and drew its end label, the hero drew digits", () => {
    expect(chart(CHART_CASES.live)).toMatch(/data-callout-label="[^"]+"/);
    expect(hero(HERO_CASES.live)).toContain("data-hero-digits");
  });

  for (const [k, p] of Object.entries(HERO_CASES)) {
    it(`hero ${k}: no prop and tenths={false} both equal master`, () => {
      expect(digest(hero(p))).toBe(MASTER[`hero:${k}`]);
      expect(digest(hero(p, { tenths: false }))).toBe(MASTER[`hero:${k}`]);
    });
  }

  for (const [k, p] of Object.entries(CHART_CASES)) {
    it(`chart ${k}: no prop and tenths={false} both equal master`, () => {
      expect(digest(chart(p))).toBe(MASTER[`chart:${k}`]);
      expect(digest(chart(p, { tenths: false }))).toBe(MASTER[`chart:${k}`]);
    });
  }
});
