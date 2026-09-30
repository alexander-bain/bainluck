// #8997 — A FINISHED GAME'S SCORE DIFFERENTIAL STOPS ADVERTISING A LINE IT
// DOES NOT DRAW.
//
// `/events/15292394` — Dubai Basketball 78–77 Real Madrid, EuroLeague, FINAL.
// Production 9/30 11:10Z at 390px: the legend reads "Projected margin · Actual
// Score Diff", and the only orange on the plot is a 1–2px sliver at the right
// edge. `/history` serves `score_history` = ONE row (the final, stamped at
// completed_at) and `espn_history` = 0, so the actual series is one point at
// the last category — the #7211 carry has nothing to extend — and a
// `stepAfter` line through one point is a zero-length segment.
//
// Ship: a lone captured score is drawn as a DOT at the time it was observed
// (Dubai +1 at the buzzer). Two or more points keep the step line exactly as
// before. Nothing is invented between them. Native twin: #9005.
//
// Controls that are load-bearing:
//   * THE SAME BYTES WITH ONE MORE SCORE keep the line and paint no dot — a fix
//     that dots every actual series passes the ship arm and fails this one.
//   * The render is a real chart (recharts draws nothing inside a
//     ResponsiveContainer without a viewport, so it is mocked to a fixed size
//     — #6964's rig) and the actual series is present in both arms, so neither
//     assertion can pass on an empty SVG.

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "fs";
import { join } from "path";

import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { computeSharedChartDomain } from "@/lib/eventKeyStats";

jest.mock("recharts", () => {
  const actual = jest.requireActual("recharts");
  return {
    __esModule: true,
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactElement }) =>
      React.cloneElement(children, { width: 390, height: 300 }),
  };
});

const WIRE = JSON.parse(
  readFileSync(
    join(__dirname, "fixtures/scoreDiffLoneFinal.15292394.euroleague-final.json"),
    "utf8"
  )
);

const ORANGE = "#f97316";

/**
 * The chart as `/events/[id]` mounts it: the page's shared domain (default
 * range "Since Start"), bookmaker lines and ticks included. The first cut of
 * this fix was proved WITHOUT the domain and shipped inert: the page's domain
 * ends a minute or two after the final, the #7211 carry stretches the lone
 * reading across those minutes, and a count taken after the carry read "line"
 * on production. Rendering it the page's way is what reproduces that.
 */
function render(scoreHistory: unknown[]): string {
  const wire = { ...WIRE, score_history: scoreHistory };
  const domain = computeSharedChartDomain(wire, "live", WIRE.status, WIRE.commence_time, WIRE.sport);
  return renderToStaticMarkup(
    React.createElement(ScoreDifferentialChart, {
      history: WIRE.history,
      homeTeam: WIRE.home_team,
      awayTeam: WIRE.away_team,
      commenceTime: WIRE.commence_time,
      bookmakerHistory: WIRE.bookmaker_history,
      scoreHistory,
      espnHistory: WIRE.espn_history,
      currentHomeScore: WIRE.home_score,
      currentAwayScore: WIRE.away_score,
      eventStatus: WIRE.status,
      sportKey: WIRE.sport,
      chartStartTime: domain?.start,
      chartEndTime: domain?.end,
      sharedTicks: domain?.ticks,
      chartLabelFormat: domain?.labelFormat,
      externalTimeRange: "live",
    } as never)
  );
}

/** The line-dot circles recharts painted for the actual series. */
function orangeDots(markup: string): string[] {
  return (markup.match(/<circle[^>]*>/g) ?? []).filter(
    (c) => c.includes("recharts-line-dot") && c.includes(`fill="${ORANGE}"`)
  );
}

const SPECIMEN = render(WIRE.score_history);

// A halftime reading two hours before the final: the actual series now has a
// real journey (carried forward to the final), so it must stay a line.
const WITH_HALFTIME = render([
  { timestamp: "2026-09-24T19:00:00+00:00", home_score: 40, away_score: 38 },
  ...WIRE.score_history,
]);

describe("#8997 — the fixture is the specimen and the render is a chart", () => {
  it("the page's domain runs past the final, so the lone reading IS carried", () => {
    // The production shape: without this the ship arm below is the inert
    // first cut's proof over again.
    expect(SPECIMEN).toMatch(/data-actual-tail-carried="[1-9]\d*"/);
  });

  it("the captured payload holds exactly one score, the 78–77 final", () => {
    expect(WIRE.score_history).toHaveLength(1);
    expect(WIRE.score_history[0]).toMatchObject({ home_score: 78, away_score: 77 });
    expect(WIRE.espn_history).toHaveLength(0);
  });

  it.each([
    ["specimen", SPECIMEN],
    ["with halftime", WITH_HALFTIME],
  ])("%s: draws the actual series in a real SVG", (_name, markup) => {
    expect(markup).toContain("<svg");
    expect(markup).toContain('data-actual-series="true"');
    expect(markup).toMatch(new RegExp(`class="recharts-curve recharts-line-curve"[^>]*stroke="${ORANGE}"|stroke="${ORANGE}"[^>]*class="recharts-curve recharts-line-curve"`));
  });
});

describe("#8997 — a lone captured score is a dot", () => {
  it("SHIP: the one-score final draws one orange dot and says so", () => {
    expect(SPECIMEN).toContain('data-actual-drawn-as="dot"');
    expect(orangeDots(SPECIMEN)).toHaveLength(1);
  });

  it("the dot sits on the observed reading, not on a carried minute", () => {
    const path = SPECIMEN.match(new RegExp(`stroke="${ORANGE}"[^>]*d="M([\\d.]+),([\\d.]+)`));
    expect(path).not.toBeNull();
    const dot = orangeDots(SPECIMEN)[0];
    expect(dot).toContain(`cx="${path![1]}"`);
    expect(dot).toContain(`cy="${path![2]}"`);
  });

  it("CONTROL: two scores keep the step line and paint no dot", () => {
    expect(WITH_HALFTIME).toContain('data-actual-drawn-as="line"');
    expect(orangeDots(WITH_HALFTIME)).toHaveLength(0);
  });
});
