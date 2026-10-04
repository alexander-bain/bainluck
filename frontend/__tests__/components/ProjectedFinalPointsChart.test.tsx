/**
 * #10239 — the projected final points module draws two forecast lines and a
 * quieter actual score, or nothing at all.
 *
 * Rendered with real inputs through `renderToStaticMarkup`. The cursor is a
 * prop on the view, so the inspected state is rendered the same way the
 * latest one is.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ProjectedFinalPointsChart, {
  formatProjectionTime,
  ProjectedFinalPointsChartView,
} from "../../components/event/ProjectedFinalPointsChart";
import {
  buildProjectedFinalPointsSeries,
  inspectionInstants,
  type ProjectedFinalPointsInput,
} from "@/lib/projectedFinalPointsSeries";

const KICKOFF = "2026-09-29T00:16:00Z";
const FINAL = "2026-09-29T03:10:00Z";

function nflInput(over: Partial<ProjectedFinalPointsInput> = {}): ProjectedFinalPointsInput {
  return {
    sportKey: "americanfootball_nfl",
    sourceKey: "draftkings",
    basis: "same_book_same_capture_full_game_spread_and_total",
    pairs: [
      { timestamp: "2026-09-28T23:30:00Z", home: 24.5, away: 20.0, homeProbability: 0.62 },
      { timestamp: "2026-09-29T00:30:00Z", home: 27.5, away: 17.0, homeProbability: 0.75 },
      { timestamp: "2026-09-29T01:00:00Z", home: null, away: null },
      { timestamp: "2026-09-29T01:20:00Z", home: 28.0, away: 13.5, homeProbability: 0.9 },
      { timestamp: "2026-09-29T01:40:00Z", home: Number.NaN, away: 12.0 },
      { timestamp: "2026-09-29T02:30:00Z", home: 27.0, away: 9.5, homeProbability: 0.97 },
      { timestamp: "2026-09-29T03:08:00Z", home: 26.5, away: 8.3, homeProbability: 0.99 },
      { timestamp: "2026-09-29T03:09:00Z", home: 27.0, away: 7.5, homeProbability: 0.99 },
      { timestamp: "2026-09-29T03:11:00Z", home: 27.0, away: 7.0, homeProbability: 0.99 },
    ],
    actuals: [
      { timestamp: "2026-09-28T23:50:00Z", home_score: 0, away_score: 0 },
      { timestamp: "2026-09-29T00:24:00Z", home_score: 7, away_score: 0 },
      { timestamp: "2026-09-29T01:15:00Z", home_score: 14, away_score: 7 },
      { timestamp: "2026-09-29T03:06:00Z", home_score: 27, away_score: 7 },
    ],
    kickoffAt: KICKOFF,
    finalAt: FINAL,
    asOf: "2026-09-29T04:00:00Z",
    ...over,
  };
}

const teams = { homeTeam: "Chicago Bears", awayTeam: "Philadelphia Eagles" };

function render(input: ProjectedFinalPointsInput, cursorIndex: number | null = null): string {
  return renderToStaticMarkup(<ProjectedFinalPointsChartView input={input} {...teams} cursorIndex={cursorIndex} />);
}

const count = (html: string, needle: string) => html.split(needle).length - 1;

function instantIndex(input: ProjectedFinalPointsInput, iso: string): number {
  const s = buildProjectedFinalPointsSeries(input);
  if (!s.supported) throw new Error("expected supported");
  const i = inspectionInstants(s).indexOf(Date.parse(iso));
  if (i < 0) throw new Error(`${iso} is not an instant`);
  return i;
}

describe("unsupported games render nothing", () => {
  it.each(["baseball_mlb", "soccer_epl", "tennis_atp_us_open", "golf_pga_championship_winner"])(
    "%s leaves no empty module behind",
    (sportKey) => {
      expect(renderToStaticMarkup(<ProjectedFinalPointsChart input={nflInput({ sportKey })} {...teams} />)).toBe("");
    },
  );

  it("an NFL game with no usable pair leaves no empty module behind", () => {
    expect(render(nflInput({ pairs: [{ timestamp: "2026-09-29T00:30:00Z", home: null, away: 10 }] }))).toBe("");
  });
});

describe("a finished game", () => {
  const html = render(nflInput());

  it("draws two forecast series and two quieter actual steps", () => {
    expect(html).toContain("Projected final points");
    expect(html).toContain('data-series="forecast-home"');
    expect(html).toContain('data-series="forecast-away"');
    expect(count(html, 'data-series="actual-home"')).toBe(1);
    expect(count(html, 'data-series="actual-away"')).toBe(1);
    expect(html).toContain('stroke-dasharray="6 5"');
  });

  it("shows the last valid projection with its time, not the final as a forecast", () => {
    expect(html).toContain("Last projection before the final · recorded " + formatProjectionTime(Date.parse("2026-09-29T03:09:00Z")));
    expect(html).toContain(">27.0<");
    expect(html).toContain(">7.5<");
    expect(html).toMatch(/27 final/);
    expect(html).toMatch(/7 final/);
    expect(html).not.toMatch(/current|settled/i);
  });

  it("draws each lone reading as a dot, never stretched toward a gap", () => {
    // 01:20 and 02:30 each sit between two withheld readings, and 03:09 is the
    // last reading with no later confirmation: three dots for each team.
    expect(count(html, 'data-single-point="true"')).toBe(6);
    expect(count(html, 'data-series="forecast-home"')).toBe(4);
  });

  it("marks each withheld reading on the time axis", () => {
    expect(html).toContain('data-withheld="pair_incomplete"');
    expect(html).toContain('data-withheld="not_a_number"');
    expect(html).toContain('data-withheld="below_recorded_score"');
  });

  it("names the source and keeps sportsbook jargon off the page", () => {
    expect(html).toContain("DraftKings");
    expect(html).not.toMatch(/\bbooks?\b|bookmaker/i);
  });

  it("gives screen readers both quantities in the inspector", () => {
    expect(html).toContain(
      `aria-valuetext="recorded ${formatProjectionTime(Date.parse("2026-09-29T03:09:00Z"))}, Chicago Bears 27.0, Philadelphia Eagles 7.5 projected final points"`,
    );
  });
});

describe("before kickoff", () => {
  const html = render(nflInput({ kickoffAt: null, finalAt: null, asOf: "2026-09-29T00:00:00Z" }));

  it("has no actual score anywhere", () => {
    expect(html).not.toContain("data-actual=");
    expect(html).not.toContain('data-series="actual-');
    expect(html).toContain("Latest projection · recorded " + formatProjectionTime(Date.parse("2026-09-28T23:30:00Z")));
  });
});

describe("inspecting a moment", () => {
  const input = nflInput();

  it("reads the projection and score at the cursor, and nothing later", () => {
    const html = render(input, instantIndex(input, "2026-09-29T00:30:00Z"));
    expect(html).toContain("Projection at this point · recorded " + formatProjectionTime(Date.parse("2026-09-29T00:30:00Z")));
    expect(html).toContain(">27.5<");
    expect(html).toContain(">17.0<");
    expect(html).toMatch(/7 scored/);
    expect(html).toContain('data-testid="projected-cursor"');
    // Later readings, later scores and later gap ticks are not drawn.
    expect(html).not.toContain(">7.5<");
    expect(html).not.toMatch(/27 (final|scored)/);
    expect(html).not.toContain('data-withheld="below_recorded_score"');
    expect(html).toContain("Back to latest");
  });

  it("says so when the inspected reading was unusable", () => {
    const html = render(input, instantIndex(input, "2026-09-29T01:00:00Z"));
    expect(html).toContain("No usable projection at this point");
    expect(html).not.toContain(">27.5<");
  });
});

describe("a live game whose newest reading was unusable", () => {
  it("says so once, without repeating the time", () => {
    const html = render(nflInput({ finalAt: null, asOf: "2026-09-29T01:50:00Z" }));
    expect(html).toContain("Latest projection · recorded " + formatProjectionTime(Date.parse("2026-09-29T01:20:00Z")));
    expect(html).toContain("No usable projection since then");
  });
});
