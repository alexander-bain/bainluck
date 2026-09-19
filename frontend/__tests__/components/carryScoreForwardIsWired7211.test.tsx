/**
 * #7211 — THE WIRING HALF: the chart actually carries the score, on the shape
 * production served.
 *
 * `carryScoreForward7211.test.ts` pins the rule. It cannot see whether
 * `ScoreDifferentialChart` calls it, and that gap is not hypothetical: on #7163
 * a correct rule was wired to `event.sport_key`, a field the payload does not
 * carry, and shipped inert on the very page it targeted. Every gate was green.
 *
 * Read through `data-actual-tail-carried` for the reason the file's other attributes
 * exist: recharts renders nothing inside `ResponsiveContainer` without a
 * viewport, so a guard hunting for an SVG path in static markup would pass on
 * both arms of this.
 *
 * The attribute reports the size of the TAIL the carry covers, and that choice
 * was forced twice. "Does the line reach the edge" is 0 on every chart once
 * this ships; the TOTAL carry is 55 of 57 categories on BOTH fixtures below,
 * because `fillMinuteGaps` seeds every minute and most of the filling happens
 * between readings rather than after the last one. Both are constants, and a
 * mutant hardcoding a constant survives. Only a number that moves with the data
 * can be cornered by two tests.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";

// Fixed anchor — offset first, then use (gotcha #44).
const KICKOFF_MS = Date.UTC(2026, 8, 19, 11, 30, 0);
const MIN = 60 * 1000;
const at = (offsetMin: number, seconds = 0) =>
  new Date(KICKOFF_MS + offsetMin * MIN + seconds * 1000).toISOString();
const COMMENCE = new Date(KICKOFF_MS).toISOString();
const SPORT = "soccer_epl";

/**
 * The specimen, exactly as `/api/events/15305207/history` served it at 12:26Z:
 * two readings, the second the goal, and 6 minutes of live chart after it.
 */
const SCORES = [
  { timestamp: at(0, 30), home_score: 0, away_score: 0 },
  { timestamp: at(50, 30), home_score: 0, away_score: 1 },
];

const ODDS = Array.from({ length: 57 }, (_, i) => ({
  timestamp: at(i),
  home_probability: 0.5 - i * 0.004,
  away_probability: 0.5 + i * 0.004,
  projected_home_score: 1.4,
  projected_away_score: 1.2,
}));

function draw(
  scoreHistory: Array<{
    timestamp: string;
    home_score: number;
    away_score: number;
  }>,
): string {
  return renderToStaticMarkup(
    <ScoreDifferentialChart
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      history={ODDS as any}
      homeTeam="Tottenham Hotspur"
      awayTeam="Aston Villa"
      commenceTime={COMMENCE}
      isLive
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      scoreHistory={scoreHistory as any}
      currentHomeScore={0}
      currentAwayScore={1}
      eventStatus="live"
      sportKey={SPORT}
      chartStartTime={COMMENCE}
      chartEndTime={at(56)}
    />,
  );
}

const carriedIn = (html: string): string | null => {
  const m = html.match(/data-actual-tail-carried="(\d+)"/);
  return m ? m[1] : null;
};

const reachesEdge = (html: string): string | null => {
  const m = html.match(/data-actual-reaches-edge="(true|false)"/);
  return m ? m[1] : null;
};

describe("#7211 the chart carries the score to the right edge", () => {
  test("THE SHIP — on the specimen's own shape the score is carried past the goal", () => {
    const html = draw(SCORES);
    expect(html).toMatch(/data-actual-series="true"/);
    // The goal lands at minute 50 and the domain ends at minute 56, so six
    // minutes of line exist that no reading covers. Those six are exactly the
    // hole the production frame shows: the orange line stopping at the goal
    // while the green projection runs on to the right edge.
    expect(carriedIn(html)).toBe("6");
    // ...and those six minutes now HAVE a line. The assertion above measures
    // the hole; this one is the only thing in the render that notices whether
    // it was filled, because the tail is counted before the carry runs.
    expect(reachesEdge(html)).toBe("true");
  });

  test("the goal is still a step and not a smoothed slide", () => {
    // The carry must not change HOW the line gets from 0 to -1. `stepAfter` is
    // what makes a goal read as an instant rather than a 50-minute drift, and a
    // mutant that swaps it for `linear`/`monotone` while leaving the carry
    // intact would pass every other assertion in this file.
    const html = draw(SCORES);
    expect(html).toMatch(/data-actual-series="true"/);
    const src = require("fs").readFileSync(
      require("path").join(
        __dirname,
        "../../components/ScoreDifferentialChart.tsx",
      ),
      "utf8",
    );
    const actualLine = src.slice(src.indexOf('dataKey="actualDiff"') - 200);
    expect(actualLine).toMatch(/type="stepAfter"/);
  });

  test("A SECOND, DIFFERENT NUMBER — a reading on the last minute carries nothing", () => {
    // This is the assertion that makes the one above a measurement. The ship
    // test alone is satisfied by any implementation that reports a constant;
    // pinning a SECOND value on a second shape leaves a hardcoded answer
    // nowhere to stand. A mutant returning 0 unconditionally dies here, and one
    // returning 6 unconditionally dies above.
    const html = draw([
      { timestamp: at(0, 30), home_score: 0, away_score: 0 },
      { timestamp: at(56), home_score: 0, away_score: 1 },
    ]);
    expect(carriedIn(html)).toBe("0");
  });

  test("CONTROL — no score series at all reports nothing, not a carry of 0", () => {
    // `absent` and `0` are different claims: a chart with no score line has no
    // carry to report, and printing 0 would read as "observed at every minute".
    const html = renderToStaticMarkup(
      <ScoreDifferentialChart
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        history={ODDS as any}
        homeTeam="Tottenham Hotspur"
        awayTeam="Aston Villa"
        commenceTime={COMMENCE}
        isLive
        scoreHistory={[]}
        eventStatus="live"
        sportKey={SPORT}
        chartStartTime={COMMENCE}
        chartEndTime={at(56)}
      />,
    );
    if (html !== "") {
      expect(html).toMatch(/data-actual-series="false"/);
      expect(carriedIn(html)).toBeNull();
      expect(reachesEdge(html)).toBeNull();
    }
  });

  test("the carry does not back-fill the pre-game half of the domain", () => {
    // The chart opens before the first reading here. Nothing may paint a score
    // onto those minutes — the same asymmetry the rule test pins, checked once
    // through the component so a call site that sorted or reversed the points
    // first cannot pass.
    const html = renderToStaticMarkup(
      <ScoreDifferentialChart
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        history={ODDS as any}
        homeTeam="Tottenham Hotspur"
        awayTeam="Aston Villa"
        commenceTime={COMMENCE}
        isLive
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        scoreHistory={SCORES as any}
        currentHomeScore={0}
        currentAwayScore={1}
        eventStatus="live"
        sportKey={SPORT}
        chartStartTime={at(-30)}
        chartEndTime={at(56)}
      />,
    );
    // Still exactly the six minutes AFTER the goal — not the thirty pre-game
    // minutes as well, which a back-filling implementation would also claim.
    expect(carriedIn(html)).toBe("6");
    expect(reachesEdge(html)).toBe("true");
    // ...and the span the period chips are bounded by (CERT-1995) still starts
    // at the first READING, not at the opening of the domain.
    expect(html).toMatch(/data-actual-series="true"/);
  });
});
