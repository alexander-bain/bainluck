/**
 * #7161 — THE "All" TAB LABELLED A WINDOW IT DID NOT DRAW.
 *
 * On a FINISHED game the x-axis ran backwards: measured on production
 * 2026-09-19, /events/14638896 (Chiefs 31-10 Broncos, 390px), the Win
 * Probability axis rendered `7:00 PM` at x=21 and `3:15 PM` at x=257.
 *
 * `computeSharedChartDomain` caps a completed game's "All" start to two hours
 * before kick-off and builds `sharedTicks` and the `h:mm a` label format on that
 * five-hour window — deliberately, because a sub-12h window needs no
 * date-qualified label (L2-163 Item 2c). `OddsChart` then drew every point the
 * payload served: that event's series open 2026-05-12, and 4,017 of its 4,607
 * `aggregate_line` points — 87% — fall before the day of the game. A categorical
 * XAxis places a tick by matching its STRING against the category list, so with
 * four months of `h:mm a` categories under it, `3:15 PM` matched a May category
 * near the left edge and the two ticks landed reversed.
 *
 * ═══ WHY THE CATEGORIES AND NOT THE TICKS ═══
 *
 * recharts renders nothing inside `ResponsiveContainer` without a viewport, so
 * no server-rendered guard can read a tick's x — the production probe
 * (`tools/ux1354-all-tab-axis-runs-forward-7161.mjs`) does that, and banked both
 * arms. What a guard CAN hold is the cause: the category list the axis maps its
 * ticks onto. `data-category-span` is that list's extent and length, and it is
 * deliberately a different fact from `data-drawn-extent` — a category outside
 * the window mis-places a tick whether or not it carries ink.
 *
 * 🔴 ARM 3 IS THE ANTI-STRAWMAN. "Clip everything before kick-off" passes arms
 * 1 and 2 and deletes the two pre-kickoff hours that "All" exists to show — the
 * difference between the tab being fixed and the tab being pointless. The window
 * the ink is cut to has to be the PARENT'S, not `commenceTime`.
 *
 * 🔴 ARM 4 IS THE FLOOR, and it is why this is a memo and not a `&&`. "All" is
 * the window the chart RESETS TO when the live one draws nothing (#6349);
 * nothing rescues an empty "All". A start cutoff with no point at or after it
 * would not trim a pre-window slab, it would delete the journey.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import OddsChart from "@/components/OddsChart";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";
// eslint-disable-next-line @typescript-eslint/no-var-requires
const { AnalyticsProvider } = require("@/components/Analytics");

/** Fixed anchor — never `Date.now()`, and offset before truncating (gotcha #44). */
const KICKOFF = Date.UTC(2026, 8, 15, 0, 15, 0);
const MIN = 60 * 1000;
const iso = (offsetMin: number) => new Date(KICKOFF + offsetMin * MIN).toISOString();

const FINAL_MIN = 181;
/** The specimen's real shape: the served series open four months before kick-off. */
const PRE_SEASON_FROM_MIN = -125 * 24 * 60;

const series = (fromMin: number, toMin: number, probability: number, stepMin = 1) => {
  const points = [];
  for (let m = fromMin; m <= toMin; m += stepMin) {
    points.push({ timestamp: iso(m), home_probability: probability });
  }
  return points;
};

/** Four months of pre-season drift, one point every six hours. */
const PRE_SEASON = series(PRE_SEASON_FROM_MIN, -121, 0.54, 360);
/** The two hours "All" exists to show. */
const PRE_GAME = series(-120, -1, 0.56, 10);
const IN_PLAY = series(0, FINAL_MIN, 0.84, 10);

const SERVED = [...PRE_SEASON, ...PRE_GAME, ...IN_PLAY];

const withAway = (points: { timestamp: string; home_probability: number }[]) =>
  points.map((p) => ({ ...p, away_probability: 1 - p.home_probability }));

/**
 * The window the page itself computes for this payload — not a number typed
 * here. A hand-written domain would let the guard pass while the real helper
 * moved underneath it.
 */
const DOMAIN = computeSharedChartDomain(
  {
    history: withAway(SERVED),
    espn_history: IN_PLAY,
    win_prob_history: { espn: IN_PLAY, stat_model: IN_PLAY },
    aggregate_line: SERVED,
  } as never,
  "all",
  "completed",
  new Date(KICKOFF).toISOString(),
  "americanfootball_nfl",
);

type ChartProps = Partial<React.ComponentProps<typeof OddsChart>>;

function draw(overrides: ChartProps = {}): string {
  return renderToStaticMarkup(
    React.createElement(
      AnalyticsProvider,
      null,
      <OddsChart
        history={withAway(SERVED) as never}
        homeTeam="Chiefs"
        awayTeam="Broncos"
        commenceTime={new Date(KICKOFF).toISOString()}
        eventStatus="completed"
        completedAt={iso(FINAL_MIN)}
        espnHistory={IN_PLAY as never}
        winProbHistory={{ espn: IN_PLAY, stat_model: IN_PLAY } as never}
        aggregateLine={SERVED}
        externalTimeRange="all"
        chartStartTime={DOMAIN?.start}
        chartEndTime={DOMAIN?.end}
        {...overrides}
      />,
    ),
  );
}

const attr = (html: string, name: string): string => {
  const match = html.match(new RegExp(`${name}="([^"]*)"`));
  if (!match) throw new Error(`the wrapper lost its ${name} attribute`);
  return match[1];
};

const categorySpan = (html: string) => {
  const raw = attr(html, "data-category-span");
  if (raw === "") return null;
  const [startMs, endMs, count] = raw.split(",").map(Number);
  return { startMs, endMs, count };
};

const drawnExtent = (html: string) => {
  const raw = attr(html, "data-drawn-extent");
  if (raw === "") return null;
  const [startMs, endMs] = raw.split(",").map(Number);
  return { startMs, endMs };
};

describe("#7161 — 'All' draws the window it labels", () => {
  /**
   * The fixture has to hold the defect, or every assertion below is true by
   * construction. This is the production shape, stated as a precondition: the
   * payload really does open four months before the window does.
   */
  test("PRECONDITION: the served payload reaches far outside the computed window", () => {
    expect(DOMAIN).not.toBeNull();
    const domainStart = new Date(DOMAIN!.start).getTime();
    const servedStart = new Date(SERVED[0].timestamp).getTime();

    expect(servedStart).toBeLessThan(domainStart);
    // Not "a bit outside" — months, which is what breaks a 12h-unique label.
    expect(domainStart - servedStart).toBeGreaterThan(30 * 24 * 60 * MIN);
    // And the window the page computed really is the short one.
    expect(new Date(DOMAIN!.end).getTime() - domainStart).toBeLessThan(12 * 60 * MIN);
  });

  test("ARM 1: no category falls outside the window the axis is labelled for", () => {
    const span = categorySpan(draw());
    const domainStart = new Date(DOMAIN!.start).getTime();
    const domainEnd = new Date(DOMAIN!.end).getTime();

    expect(span).not.toBeNull();
    expect(span!.startMs).toBeGreaterThanOrEqual(domainStart);
    expect(span!.endMs).toBeLessThanOrEqual(domainEnd);
  });

  test("ARM 2: and the ink stays inside it too", () => {
    const extent = drawnExtent(draw());
    const domainStart = new Date(DOMAIN!.start).getTime();

    expect(extent).not.toBeNull();
    expect(extent!.startMs).toBeGreaterThanOrEqual(domainStart);
  });

  test("ARM 3 (anti-strawman): the two pre-kickoff hours 'All' exists for survive", () => {
    // A clip at `commenceTime` — the obvious wrong fix — passes arms 1 and 2 and
    // makes "All" identical to "Since Start". The window belongs to the parent.
    const extent = drawnExtent(draw());

    expect(extent!.startMs).toBeLessThan(KICKOFF);
    expect(extent!.startMs).toBeGreaterThanOrEqual(new Date(DOMAIN!.start).getTime());
  });

  test("ARM 4 (the floor): a window that starts after every point does not empty the chart", () => {
    // The /events/15300276 class of wrong field, at the other end: a domain
    // start derived from a `commence_time` that was never really the start can
    // land past the whole series. Trimming to it would delete the journey, and
    // nothing rescues an empty "All".
    const html = draw({ chartStartTime: iso(FINAL_MIN + 600), chartEndTime: DOMAIN!.end });

    const extent = drawnExtent(html);
    expect(extent).not.toBeNull();
    // The cutoff is DISCARDED, not honoured: the journey is still there, opening
    // on the first point the payload served. A `&&` here would draw nothing.
    expect(extent!.startMs).toBe(new Date(SERVED[0].timestamp).getTime());
    expect(extent!.endMs).toBe(new Date(IN_PLAY[IN_PLAY.length - 1].timestamp).getTime());
  });

  test("ARM 5: 'Since Start' is unchanged — it still opens at kick-off", () => {
    const liveDomain = computeSharedChartDomain(
      {
        history: withAway(SERVED),
        espn_history: IN_PLAY,
        win_prob_history: { espn: IN_PLAY, stat_model: IN_PLAY },
        aggregate_line: SERVED,
      } as never,
      "live",
      "completed",
      new Date(KICKOFF).toISOString(),
      "americanfootball_nfl",
    );
    const extent = drawnExtent(
      draw({
        externalTimeRange: "live",
        chartStartTime: liveDomain?.start,
        chartEndTime: liveDomain?.end,
      }),
    );

    expect(extent).not.toBeNull();
    expect(extent!.startMs).toBeGreaterThanOrEqual(KICKOFF);
  });

  test("ARM 6: with no parent window, 'All' is still uncapped", () => {
    // The fullscreen chart is rendered without a shared domain. This pins that
    // the clip is keyed on the parent's window and nothing else, so a chart that
    // is given none keeps every point rather than silently drawing nothing.
    const span = categorySpan(draw({ chartStartTime: undefined, chartEndTime: undefined }));

    expect(span).not.toBeNull();
    expect(span!.startMs).toBe(new Date(SERVED[0].timestamp).getTime());
  });
});
