/**
 * #6987 — THE END CUTOFF IS NOT A PROPERTY OF THE RANGE.
 *
 * A FINAL NFL game read `100%` under "Since Start" and `>99%` under "All", on
 * the same page, for what looked like the same point. It was not the same
 * point. Measured on production 2026-09-19 on /events/14638896 (Chiefs 31-10
 * Broncos):
 *
 *   ESPN / stat model / sportsbooks   last point 03:16Z   home_probability 1.0
 *   Kalshi                            13 points after     0.99
 *   Polymarket                        11 points after     0.9995
 *   aggregate_line                    10 points after     0.999
 *
 * `GAME_END_SOURCES` excludes the prediction markets precisely because they
 * keep quoting past the final whistle, so `smartEndTime` lands on 03:16Z — but
 * it was applied inside the `timeRange !== "all"` arm of all five series
 * filters. "All" therefore drew ten post-final minutes of flat blend and
 * anchored its callout on the last of them. Two points ten minutes apart, and
 * whichever tab a reader landed on decided whether the chart would say the
 * Chiefs had won.
 *
 * ═══ WHY THESE ARMS AND NOT A UNIT TEST OF THE LABEL ═══
 *
 * `chartAxisPercents` was never wrong here — it is strict on the probability,
 * and `chartCalloutHonoursTheBoundaryRule6858` already pins that a genuine `1`
 * prints `100%`. A unit test of the formatter would have passed all along. The
 * question is WHICH POINT reaches it, so every arm below reads
 * `data-callout-at` (the instant) beside `data-callout-label` (the string), and
 * `data-drawn-extent` for where the ink actually stops — the callout is one
 * reader of the window, the flat tail was the whole of the defect.
 *
 * The strings and instants are read off the wrapper because the callout is
 * drawn inside a recharts `shape`, and recharts renders nothing inside
 * `ResponsiveContainer` without a viewport: a guard grepping the markup for
 * "100%" would find nothing on either arm and be worth nothing. Same channel
 * CERT-1984 opened for the period-chip count.
 *
 * 🔴 ARM 3 IS THE ANTI-STRAWMAN and is the reason this file is not two
 * assertions. "Trim until the number is 100%" would pass arms 1 and 2 and be a
 * different, worse bug. Arm 3 is the same fixture with the game-end sources
 * running all the way to the tail, where `>99%` is the honest answer and the
 * chart must still print it.
 *
 * 🔴 ARM 4 IS THE FLOOR. "All" is the window the chart RESETS TO when the live
 * one draws nothing (#6349); nothing rescues an empty "All". A cutoff derived
 * from `completed_at` — a backend processing timestamp — can precede the data
 * entirely, and applying it would delete the journey rather than trim its tail.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/** Fixed anchor — never `Date.now()`, and offset before truncating (gotcha #44). */
const KICKOFF = Date.UTC(2026, 8, 15, 0, 15, 0);
const MIN = 60 * 1000;
const iso = (offsetMin: number) => new Date(KICKOFF + offsetMin * MIN).toISOString();

/** The whistle: where ESPN, the stat model and the sportsbooks all stop. */
const FINAL_MIN = 181;
/** The last minute the prediction markets kept quoting into. */
const TAIL_MIN = 191;

const series = (
  fromMin: number,
  toMin: number,
  probability: number,
  stepMin = 1,
) => {
  const points = [];
  for (let m = fromMin; m <= toMin; m += stepMin) {
    points.push({ timestamp: iso(m), home_probability: probability });
  }
  return points;
};

/**
 * The specimen's shape: two hours of pre-kickoff drift, an in-play climb, an
 * exact `1.0` at the whistle from every game-end source, and a prediction-market
 * tail at `0.999` for ten minutes after it.
 */
const PRE_GAME = series(-120, -1, 0.62, 10);
const IN_PLAY = series(0, FINAL_MIN - 1, 0.84, 10);
const AT_FINAL = [{ timestamp: iso(FINAL_MIN), home_probability: 1.0 }];
const POST_FINAL_TAIL = series(FINAL_MIN + 1, TAIL_MIN, 0.999);

const GAME_END_SERIES = [...PRE_GAME, ...IN_PLAY, ...AT_FINAL];
/** The blend the backend serves: it includes the post-final tail. */
const AGGREGATE_LINE = [...GAME_END_SERIES, ...POST_FINAL_TAIL];

const withAway = (points: { timestamp: string; home_probability: number }[]) =>
  points.map((p) => ({ ...p, away_probability: 1 - p.home_probability }));

type ChartProps = Partial<React.ComponentProps<typeof OddsChart>>;

function draw(overrides: ChartProps = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={withAway(GAME_END_SERIES) as never}
        homeTeam="Chiefs"
        awayTeam="Broncos"
        commenceTime={new Date(KICKOFF).toISOString()}
        eventStatus="completed"
        completedAt={iso(FINAL_MIN)}
        espnHistory={GAME_END_SERIES as never}
        winProbHistory={
          {
            espn: GAME_END_SERIES,
            stat_model: GAME_END_SERIES,
            kalshi: [...GAME_END_SERIES, ...series(FINAL_MIN + 1, TAIL_MIN, 0.99)],
            polymarket: [
              ...GAME_END_SERIES,
              ...series(FINAL_MIN + 1, TAIL_MIN, 0.9995),
            ],
          } as never
        }
        aggregateLine={AGGREGATE_LINE}
        externalTimeRange="all"
        {...overrides}
      />,
    ),
  );
}

const attr = (html: string, name: string): string => {
  const match = html.match(new RegExp(`${name}="([^"]*)"`));
  if (!match) throw new Error(`the wrapper lost its ${name} attribute`);
  // The boundary form's marker is a literal `>`, which React escapes inside an
  // attribute. Decoding here rather than asserting on `&gt;99%` keeps every
  // expectation below written the way the reader sees it — an assertion spelled
  // in entities is one nobody can check against a screenshot.
  return match[1]
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&amp;/g, "&");
};

const calloutLabel = (html: string) => attr(html, "data-callout-label");
const calloutAt = (html: string) => attr(html, "data-callout-at");
const drawnExtent = (html: string) => {
  const raw = attr(html, "data-drawn-extent");
  if (raw === "") return null;
  const [startMs, endMs] = raw.split(",").map(Number);
  return { startMs, endMs };
};

describe("#6987 — a completed game's chart ends when the game did, in BOTH ranges", () => {
  test("ARM 1: 'All' anchors its callout on the whistle, not on the market tail", () => {
    const html = draw({ externalTimeRange: "all" });

    expect(calloutAt(html)).toBe(iso(FINAL_MIN));
    expect(calloutLabel(html)).toBe("100%");
  });

  test("ARM 2: 'Since Start' agrees with it — one game, one ending", () => {
    const all = draw({ externalTimeRange: "all" });
    const live = draw({ externalTimeRange: "live" });

    expect(calloutAt(live)).toBe(calloutAt(all));
    expect(calloutLabel(live)).toBe(calloutLabel(all));
  });

  test("the ink stops at the whistle in 'All', and still opens before kick-off", () => {
    const extent = drawnExtent(draw({ externalTimeRange: "all" }));

    expect(extent).not.toBeNull();
    // The tail is gone …
    expect(extent!.endMs).toBe(KICKOFF + FINAL_MIN * MIN);
    // … and the half of the journey "All" exists to show is still there. A trim
    // that also ate the pre-game would pass every callout assertion above.
    expect(extent!.startMs).toBeLessThan(KICKOFF);
  });

  test("'Since Start' still opens at kick-off — the START is still a range choice", () => {
    const extent = drawnExtent(draw({ externalTimeRange: "live" }));

    expect(extent).not.toBeNull();
    expect(extent!.startMs).toBeGreaterThanOrEqual(KICKOFF);
  });

  test("ARM 3 (anti-strawman): when the game-end sources run to the tail, '>99%' stands", () => {
    // The ONLY change: ESPN and the stat model keep reporting to `TAIL_MIN`, so
    // the whistle IS the tail and there is nothing to trim. A fix that reached
    // `100%` by preferring certainty, or by dropping any point a prediction
    // market quoted, would print the wrong number here.
    const toTheTail = [...GAME_END_SERIES, ...POST_FINAL_TAIL];
    const html = draw({
      externalTimeRange: "all",
      history: withAway(toTheTail) as never,
      espnHistory: toTheTail as never,
      winProbHistory: {
        espn: toTheTail,
        stat_model: toTheTail,
      } as never,
    });

    expect(calloutAt(html)).toBe(iso(TAIL_MIN));
    expect(calloutLabel(html)).toBe(">99%");
  });

  test("ARM 4 (the floor): a `completed_at` before the data does not empty 'All'", () => {
    // No game-end sources and no sportsbook history, so `smartEndTime` falls all
    // the way through to `completed_at` — here a backend stamp an hour before
    // the match was played, the /events/15300276 class of wrong field. Applying
    // it would not trim a tail, it would delete the journey, and "All" is the
    // window the chart resets TO when the live one draws nothing (#6349).
    const html = draw({
      externalTimeRange: "all",
      completedAt: iso(-180),
      history: [] as never,
      espnHistory: [] as never,
      winProbHistory: { kalshi: AGGREGATE_LINE } as never,
    });

    const extent = drawnExtent(html);
    expect(extent).not.toBeNull();
    expect(extent!.endMs).toBe(KICKOFF + TAIL_MIN * MIN);
    expect(calloutLabel(html)).not.toBe("");
  });

  test("a live game is not trimmed at all — `smartEndTime` is a completed-game rule", () => {
    const html = draw({
      externalTimeRange: "all",
      eventStatus: "live",
      isLive: true,
      completedAt: undefined,
    });

    // Nothing has ended, so every served point is still the chart's business.
    expect(drawnExtent(html)!.endMs).toBe(KICKOFF + TAIL_MIN * MIN);
  });
});
