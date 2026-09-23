/**
 * #8215 — "SINCE START" CUT AT AN HOUR THAT WAS NEVER A START.
 *
 * For a Kalshi-clocked dated fixture we store the venue's `occurrence_datetime`, which is
 * byte-identical to `expected_expiration_time` — when the CONTRACT is expected to resolve, about
 * two hours after a tennis match is over. Kalshi publishes no kick-off field at all.
 *
 * Measured on production 2026-09-23, /events/15317314 (Basilashvili v Cina, ATP), 390px:
 * `commence_time` 09:10Z, and the 525 served Kalshi+Polymarket points run 2026-09-22 17:45Z →
 * 2026-09-23 09:19Z. Exactly **4 of those 525** fall at or after 09:10Z. So the Win Probability
 * chart's entire x-axis was nine minutes wide — a dead-flat line at 99% — over a page that names
 * the winner correctly. The two hours we actually captured, 0.39 → 0.995, were off-screen.
 *
 * The backend half (#7878, released) serves `commence_time_is_kickoff`. This is the render half.
 *
 * ═══ 🔴 WHY THE EXISTING ESCAPE HATCHES CANNOT CATCH IT ═══
 *
 * Both cut sites already guard against a bad `commence_time` — and both guards are the same guard:
 * *nothing survives the cut*. `computeSharedChartDomain` declines to cap when no point is left, and
 * `OddsChart.rangeStartTime` walks every series looking for one point at or after the candidate.
 * This population sits just PAST that hatch, on a handful of post-settlement quotes. **Four
 * surviving points is not an empty window, it is a wrong one**, and no test on the series can tell
 * those apart — which is exactly why the flag is served rather than inferred (⚠️ in the issue).
 *
 * 🔴 ARM 3/4 ARE THE ANTI-STRAWMAN. "Never cut at commence_time" passes arm 1 and throws away
 * "Since Start" for the 99%+ of events whose hour IS a kick-off (measured: `espn`-clocked events
 * were decided-before-start 0.0% of the time, against 66.8% for `kalshi`). Only an explicit served
 * `false` may change the window; `true` and a missing field — an older payload — keep the cut.
 *
 * 🔴 ARM 6 IS THE ONE THE PARENT CANNOT COVER. The fullscreen chart on the event page passes no
 * `chartStartTime`, so fixing `computeSharedChartDomain` alone leaves it cutting to nine minutes
 * while the chart behind it is correct. Arm 7 pins both call sites for the same reason.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import fs from "fs";
import path from "path";

import OddsChart from "@/components/OddsChart";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/** The specimen's real instants. Fixed — never `Date.now()` (gotcha #44). */
const COMMENCE = "2026-09-23T09:10:00.000Z"; // the venue's expected RESOLUTION hour
const SERIES_OPEN = Date.UTC(2026, 8, 22, 17, 45, 0);
const PLAY_FROM = Date.UTC(2026, 8, 23, 7, 0, 0);
const PLAY_TO = Date.UTC(2026, 8, 23, 8, 27, 0);
const TAIL = [
  Date.UTC(2026, 8, 23, 9, 10, 0),
  Date.UTC(2026, 8, 23, 9, 13, 0),
  Date.UTC(2026, 8, 23, 9, 16, 0),
  Date.UTC(2026, 8, 23, 9, 19, 0),
];

const pt = (ms: number, probability: number) => ({
  timestamp: new Date(ms).toISOString(),
  home_probability: probability,
  away_probability: 1 - probability,
});

const ramp = (fromMs: number, toMs: number, from: number, to: number, stepMin: number) => {
  const out = [];
  const span = toMs - fromMs;
  for (let t = fromMs; t <= toMs; t += stepMin * 60_000) {
    out.push(pt(t, from + ((to - from) * (t - fromMs)) / span));
  }
  return out;
};

/** Overnight pre-match drift, then the match itself, then four post-settlement quotes. */
const PRE_MATCH = ramp(SERIES_OPEN, PLAY_FROM - 60_000, 0.42, 0.39, 15);
const IN_PLAY = ramp(PLAY_FROM, PLAY_TO, 0.39, 0.995, 3);
const POST_SETTLEMENT = TAIL.map((ms) => pt(ms, 0.99));
const SERVED = [...PRE_MATCH, ...IN_PLAY, ...POST_SETTLEMENT];

/** The filed ratio, asserted rather than trusted: the defect needs a NON-empty wrong window. */
const survivingTheCut = SERVED.filter(
  (p) => new Date(p.timestamp).getTime() >= new Date(COMMENCE).getTime(),
).length;

const payload = (commence_time_is_kickoff?: boolean) =>
  ({
    history: [],
    win_prob_history: { kalshi: SERVED, polymarket: IN_PLAY },
    ...(commence_time_is_kickoff === undefined ? {} : { commence_time_is_kickoff }),
  }) as never;

const domain = (flag?: boolean) =>
  computeSharedChartDomain(payload(flag), "live", "suspended", COMMENCE, "tennis_atp");

type ChartProps = Partial<React.ComponentProps<typeof OddsChart>>;

/** The FULLSCREEN shape: no `chartStartTime`, so the chart's own fallback decides the cut. */
function drawFullscreen(overrides: ChartProps = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={[]}
        homeTeam="Basilashvili"
        awayTeam="Cina"
        commenceTime={COMMENCE}
        eventStatus="suspended"
        winProbHistory={{ kalshi: SERVED, polymarket: IN_PLAY } as never}
        externalTimeRange="live"
        {...overrides}
      />,
    ),
  );
}

const drawnExtent = (html: string) => {
  const match = html.match(/data-drawn-extent="([^"]*)"/);
  if (!match) throw new Error("the wrapper lost its data-drawn-extent attribute");
  if (match[1] === "") return null;
  const [startMs, endMs] = match[1].split(",").map(Number);
  return { startMs, endMs };
};

describe("#8215 — a 'Since Start' window is not cut at an expected END", () => {
  it("the specimen is the filed one: a handful of points DO survive the cut", () => {
    // If this ever reads 0 the defect has become "nothing survives", the existing hatches fire,
    // and every arm below would pass for a reason that has nothing to do with the flag.
    expect(survivingTheCut).toBe(4);
    // The ratio is the shape, not the raw count: on production it was 4 of 525 (0.8%). This
    // series is coarser, but the fact that matters is identical — a tiny non-empty minority.
    expect(survivingTheCut / SERVED.length).toBeLessThan(0.05);
    expect(SERVED.length).toBeGreaterThan(50);
  });

  it("a served `false` stops commence_time being the start (the fix)", () => {
    const d = domain(false);
    expect(d).not.toBeNull();
    // The window opens at the series, not at the venue's resolution hour.
    expect(new Date(d!.start).getTime()).toBe(SERIES_OPEN);
    // And it contains the match we actually captured.
    expect(new Date(d!.start).getTime()).toBeLessThan(PLAY_FROM);
    expect(new Date(d!.end).getTime()).toBeGreaterThanOrEqual(PLAY_TO);
  });

  it("CONTROL — a served `true` keeps cutting at commence_time", () => {
    // Without this, "never trust commence_time" passes the arm above and deletes "Since Start"
    // for every ESPN/StatPal-clocked game, which is almost all of them.
    expect(new Date(domain(true)!.start).getTime()).toBe(new Date(COMMENCE).getTime());
  });

  it("CONTROL — an older payload with no flag at all is unchanged", () => {
    expect(new Date(domain(undefined)!.start).getTime()).toBe(new Date(COMMENCE).getTime());
  });

  it("the nine-minute window is what `true` still produces, and `false` does not", () => {
    // States the defect as a measurement rather than a case.
    const cut = new Date(domain(true)!.end).getTime() - new Date(domain(true)!.start).getTime();
    const fixed = new Date(domain(false)!.end).getTime() - new Date(domain(false)!.start).getTime();
    expect(cut).toBeLessThanOrEqual(10 * 60_000);
    expect(fixed).toBeGreaterThan(12 * 60 * 60_000);
  });

  it("ARM 6 — the FULLSCREEN chart, which has no parent domain, draws the match too", () => {
    const withFlag = drawnExtent(drawFullscreen({ commenceTimeIsKickoff: false }));
    expect(withFlag).not.toBeNull();
    expect(withFlag!.startMs).toBeLessThanOrEqual(PLAY_FROM);
    expect(withFlag!.endMs).toBeGreaterThanOrEqual(PLAY_TO);

    // CONTROL on the same renderer: without the flag it is still the dead tail, so the assertion
    // above is about the flag and not about some other thing the chart happens to do.
    const without = drawnExtent(drawFullscreen());
    expect(without).not.toBeNull();
    expect(without!.startMs).toBeGreaterThanOrEqual(TAIL[0]);
  });

  it("ARM 7 — BOTH event-page charts are passed the flag", () => {
    // The fullscreen one is the easy one to miss: it takes no `chartStartTime`, so a wiring that
    // covers only the inline chart leaves the defect live one tap away.
    const source = fs.readFileSync(
      path.join(process.cwd(), "app/events/[id]/page.tsx"),
      "utf8",
    );
    const charts = source.split("<OddsChart").slice(1);
    expect(charts).toHaveLength(2);
    for (const chart of charts) {
      const props = chart.slice(0, chart.indexOf("/>"));
      expect(props).toContain("commenceTimeIsKickoff={historyData?.commence_time_is_kickoff}");
    }
  });
});
