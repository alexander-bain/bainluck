/**
 * #6349 — THE READER-FACING HALF: "Score Differential" stops being a heading
 * with nothing under it.
 *
 * `app/events/[id]/page.tsx` renders the card shell and the heading, then hands
 * `ScoreDifferentialChart` the shared window. The chart's last early return is a
 * bare `if (chartData.length === 0) return null` — a silent null INSIDE a card
 * the parent has already drawn — so any window the chart cannot fill leaves the
 * heading standing alone. That is what a reader found on `/events/15296797`.
 *
 * The domain guard in `__tests__/lib/chartWindowMayNotEndBeforeItStarts.test.ts`
 * proves the window is no longer inverted. This one proves the consequence the
 * reader actually sees: with that window, the chart draws the match's real score
 * line rather than returning null.
 *
 * Read through `data-actual-series` for the reason its own source comments give:
 * recharts renders nothing inside `ResponsiveContainer` without a viewport, so a
 * guard hunting for an SVG path in static markup would pass on both arms.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";

// Fixed anchor — offset first, then use (gotcha #44).
const KICKOFF_MS = Date.UTC(2026, 8, 14, 22, 0, 0);
const MIN = 60 * 1000;
const at = (offsetMin: number, seconds = 0) =>
  new Date(KICKOFF_MS + offsetMin * MIN + seconds * 1000).toISOString();
const COMMENCE = new Date(KICKOFF_MS).toISOString();
const SPORT = "soccer_argentina_primera_division";

/** 15296797's shape: the books closed ~20h before kickoff, projections and all. */
const PREGAME_ODDS = [
  {
    timestamp: at(-1200),
    home_probability: 0.63,
    away_probability: 0.37,
    projected_home_score: 1.4,
    projected_away_score: 1.1,
  },
  {
    timestamp: at(-1195),
    home_probability: 0.64,
    away_probability: 0.36,
    projected_home_score: 1.5,
    projected_away_score: 1.0,
  },
  {
    timestamp: at(-1192),
    home_probability: 0.62,
    away_probability: 0.38,
    projected_home_score: 1.3,
    projected_away_score: 1.2,
  },
];

/** The only series inside the match — 0-0, then 1-0, then the equaliser. */
const IN_GAME_SCORES = [
  { timestamp: at(3, 53), home_score: 0, away_score: 0 },
  { timestamp: at(49, 53), home_score: 1, away_score: 0 },
  { timestamp: at(86, 54), home_score: 1, away_score: 1 },
];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const HISTORY_PAYLOAD: any = {
  event_id: 15296797,
  commence_time: COMMENCE,
  history: PREGAME_ODDS,
  score_history: IN_GAME_SCORES,
  espn_history: [],
  win_prob_history: {},
  bookmaker_history: {},
};

function drawWith(window: { start: string; end: string } | null): string {
  return renderToStaticMarkup(
    <ScoreDifferentialChart
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      history={PREGAME_ODDS as any}
      homeTeam="Banfield"
      awayTeam="Barracas Central"
      commenceTime={COMMENCE}
      isLive={false}
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      scoreHistory={IN_GAME_SCORES as any}
      currentHomeScore={1}
      currentAwayScore={1}
      eventStatus="completed"
      sportKey={SPORT}
      chartStartTime={window?.start}
      chartEndTime={window?.end}
    />,
  );
}

describe("#6349 the Score Differential card draws inside the repaired window", () => {
  const repaired = computeSharedChartDomain(
    HISTORY_PAYLOAD,
    "live",
    "completed",
    COMMENCE,
    SPORT,
  );

  test("the window handed to the chart is one a match was played in", () => {
    expect(repaired).not.toBeNull();
    expect(new Date(repaired!.end).getTime()).toBeGreaterThan(
      new Date(repaired!.start).getTime(),
    );
  });

  test("THE SHIP — the chart returns markup, not the silent null under a heading", () => {
    const html = drawWith(repaired);
    expect(html).not.toBe("");
    expect(html).toMatch(/data-actual-series="true"/);
  });

  test("THE DEFECT, HELD STILL — the same chart given the inverted window draws nothing", () => {
    // This is the window production served before the fix: start at kickoff,
    // end at the last sportsbook tick 19h52m EARLIER. Nothing about the chart
    // changed to fix this page; the window did. Passing the old window back in
    // reproduces the empty card, which is what makes the test above meaningful
    // rather than a restatement of "the component works".
    const html = drawWith({ start: COMMENCE, end: at(-1192) });
    expect(html).toBe("");
  });

  test("CONTROL — with no score series at all the chart still declines, window or not", () => {
    const html = renderToStaticMarkup(
      <ScoreDifferentialChart
        history={[]}
        homeTeam="Banfield"
        awayTeam="Barracas Central"
        commenceTime={COMMENCE}
        isLive={false}
        scoreHistory={[]}
        eventStatus="completed"
        sportKey={SPORT}
        chartStartTime={repaired?.start}
        chartEndTime={repaired?.end}
      />,
    );
    expect(html).toBe("");
  });
});
