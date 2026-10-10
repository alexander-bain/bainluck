/**
 * #10239 / #10539 web follow-through of native PR #10849 (f1e15b3ef5): projected
 * final points by league NAME — NFL and college football with Q1 and seven-point
 * ticks; NBA, WNBA and women's college basketball with Q1 and twenty-point ticks;
 * men's college basketball with 1H and twenty-point ticks.
 *
 * Basketball during/after stays refused until the server serves an OBSERVED
 * first-period start for it (`period_markers.TRANSITION_SPORT_PREFIXES` is
 * football only), so the live and finished basketball cases here pin both the
 * refusal on today's served shape and the mount on the future observed shape.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ProjectedFinalPointsChart, { spokenPeriodLabel } from "@/components/event/ProjectedFinalPointsChart";
import {
  buildProjectedFinalPointsSeries,
  firstRecordedGameStateAt,
  PROJECTED_FINAL_POINTS_LEAGUES,
  projectedFinalPointsMount,
  type ProjectedFinalPointsInput,
  type ProjectedFinalPointsSeries,
} from "@/lib/projectedFinalPointsSeries";
import { normalizePeriodLabel } from "@/lib/periodMarkers";
import type { EventHistoryResponse } from "@/lib/types";

const TIP = "2026-11-12T00:10:00Z";
const LIVE_NOW = "2026-11-12T01:00:00Z";
const PREGAME = "2026-11-12T00:00:00Z";
const COMPLETED_AT = "2026-11-12T02:15:00Z";

/** A recorded capture as the #10461 route serves it, 17 s into its displayed minute. */
const row = (minute: string, home: number, away: number, homeProbability: number) => ({
  timestamp: `${minute}:00Z`,
  observed_at: `${minute}:17Z`,
  kind: "recorded",
  home_probability: homeProbability,
  away_probability: 1 - homeProbability,
  projected_home_score: home,
  projected_away_score: away,
});

const PREGAME_ROWS = [row("2026-11-11T22:00", 115.5, 108.0, 0.68), row("2026-11-11T23:30", 116.5, 108.0, 0.7)];
const LIVE_ROWS = [...PREGAME_ROWS, row("2026-11-12T00:30", 118.0, 104.5, 0.8), row("2026-11-12T00:50", 120.5, 101.0, 0.88)];
const SCORES = [
  { timestamp: "2026-11-11T23:50:00Z", home_score: 0, away_score: 0 },
  { timestamp: "2026-11-12T00:20:00Z", home_score: 12, away_score: 8 },
  { timestamp: "2026-11-12T00:45:00Z", home_score: 30, away_score: 22 },
];

/** An observed first-period start, the shape `observed_transition_markers` serves for football. */
const observed = (period: string) => ({
  timestamp: "2026-11-12T00:11:30Z",
  period,
  source: "espn_state",
  precision: "first_seen",
  not_before: "2026-11-12T00:10:40Z",
});
/** What a basketball page carries today: a marker an instrument saw, with no precision bracket. */
const unbracketed = (period: string) => ({ timestamp: "2026-11-12T00:11:30Z", period, source: "espn_state" });

function payload(over: Partial<EventHistoryResponse> & { status: string }): EventHistoryResponse {
  return { bookmaker_history: { draftkings: LIVE_ROWS }, score_history: SCORES, period_markers: [], ...over } as unknown as EventHistoryResponse;
}

const decide = (sportKey: string, eventStatus: string, history: EventHistoryResponse, now = LIVE_NOW) =>
  projectedFinalPointsMount({ sportKey, eventStatus, history, now });

function series(input: ProjectedFinalPointsInput): ProjectedFinalPointsSeries {
  const s = buildProjectedFinalPointsSeries(input);
  if (!s.supported) throw new Error(`expected supported, got ${s.reason}`);
  return s;
}

function mountedInput(sportKey: string, eventStatus: string, history: EventHistoryResponse, now = LIVE_NOW) {
  const d = decide(sportKey, eventStatus, history, now);
  if (!d.mount) throw new Error(`expected a mount for ${sportKey} ${eventStatus}, got ${d.reason}`);
  return d.input;
}

const scheduled = payload({ status: "scheduled", bookmaker_history: { draftkings: PREGAME_ROWS } });

describe("admission is by exact league name", () => {
  it("names exactly the six leagues native admits, with their first period and tick step", () => {
    expect(Object.fromEntries(PROJECTED_FINAL_POINTS_LEAGUES)).toEqual({
      americanfootball_nfl: { firstPeriod: "Q1", tickStep: 7 },
      americanfootball_ncaaf: { firstPeriod: "Q1", tickStep: 7 },
      basketball_nba: { firstPeriod: "Q1", tickStep: 20 },
      basketball_wnba: { firstPeriod: "Q1", tickStep: 20 },
      basketball_ncaab: { firstPeriod: "1H", tickStep: 20 },
      basketball_wncaab: { firstPeriod: "Q1", tickStep: 20 },
    });
  });

  it.each([
    // A puck line or run line is a fixed ±1.5 handicap, not an expected margin.
    ["icehockey_nhl"],
    ["baseball_mlb"],
    ["mma_mixed_martial_arts"],
    ["soccer_epl"],
    // Prefix lookalikes are not admitted leagues.
    ["basketball_euroleague"],
    ["americanfootball_cfl"],
    ["basketball_nba_championship_winner"],
    ["americanfootball_nfl_super_bowl_winner"],
    // An object-prototype key is not a league either.
    ["constructor"],
  ])("refuses %s before and keeps its Score Differential card", (sportKey) => {
    expect(decide(sportKey, "scheduled", scheduled, PREGAME)).toEqual({ mount: false, reason: "sport_not_supported" });
  });
});

describe("pregame basketball mounts with twenty-point ticks", () => {
  it.each([["basketball_nba"], ["basketball_wnba"], ["basketball_ncaab"], ["basketball_wncaab"]])(
    "%s: forecasts only, the page's own sport key, no actual score",
    (sportKey) => {
      const input = mountedInput(sportKey, "scheduled", scheduled, PREGAME);
      expect(input.sportKey).toBe(sportKey);
      const s = series(input);
      expect(s.phase).toBe("before");
      expect(s.actualSteps).toEqual([]);
      expect(s.latest).toMatchObject({ home: 116.5, away: 108 });
      // max(20, ceil((116.5 + 20/4) / 20) * 20) = 140
      expect(s.yMax).toBe(140);
      expect(s.yTicks).toEqual([0, 20, 40, 60, 80, 100, 120, 140]);
    },
  );

  it("the axis formula is max(step, ceil((high + step/4) / step) * step) for each step", () => {
    const at = (sportKey: string, home: number, away: number) =>
      series({
        sportKey,
        sourceKey: "draftkings",
        basis: "same_book_same_capture_full_game_spread_and_total",
        pairs: [{ timestamp: "2026-11-11T23:30:00Z", home, away, homeProbability: 0.6, kind: "recorded" }],
        actuals: [],
        kickoffAt: null,
        finalAt: null,
        asOf: PREGAME,
      });
    // 115.5 + 5 = 120.5 → 140; exactly 115 + 5 = 120 → 120.
    expect(at("basketball_nba", 115.5, 100).yMax).toBe(140);
    expect(at("basketball_nba", 115, 100).yMax).toBe(120);
    // A football 27.8 + 1.75 = 29.55 → 35, ticks of seven.
    const fb = at("americanfootball_ncaaf", 27.8, 23.8);
    expect(fb.yMax).toBe(35);
    expect(fb.yTicks).toEqual([0, 7, 14, 21, 28, 35]);
    // A tiny pair never collapses below one step.
    expect(at("basketball_wnba", 0, 0).yMax).toBe(20);
  });
});

describe("each league's own first period floors the actual score", () => {
  it("web normalizes men's college basketball's '1st Half' to 1H, and the others' '1st Quarter' to Q1", () => {
    expect(normalizePeriodLabel("1st Half", "basketball_ncaab")).toBe("1H");
    expect(normalizePeriodLabel("1st Quarter", "basketball_wncaab")).toBe("Q1");
    // A bare period number completes from the sport: halves for the men, quarters for the women.
    expect(normalizePeriodLabel("1", "basketball_ncaab")).toBe("1H");
    expect(normalizePeriodLabel("1", "basketball_wncaab")).toBe("Q1");
  });

  it.each([
    ["basketball_ncaab", "1st Half", "1st Quarter"],
    ["basketball_nba", "1st Quarter", "1st Half"],
    ["basketball_wnba", "1st Quarter", "1st Half"],
    ["basketball_wncaab", "1st Quarter", "1st Half"],
    ["americanfootball_ncaaf", "1st Quarter", "1st Half"],
  ])("%s reads %s and refuses %s", (sportKey, own, other) => {
    expect(firstRecordedGameStateAt([observed(own)], sportKey)).toBe("2026-11-12T00:10:40Z");
    expect(firstRecordedGameStateAt([observed(other)], sportKey)).toBeNull();
  });

  it("an unadmitted sport has no first period here", () => {
    expect(firstRecordedGameStateAt([observed("1st Quarter")], "basketball_euroleague")).toBeNull();
    expect(firstRecordedGameStateAt([observed("1st Period")], "icehockey_nhl")).toBeNull();
    expect(firstRecordedGameStateAt([observed("1st Quarter")], null)).toBeNull();
  });
});

describe("basketball during and after waits for an observed first-period start", () => {
  it.each([
    ["basketball_nba", "1st Quarter"],
    ["basketball_ncaab", "1st Half"],
  ])("%s live on today's served shape (no precision bracket) keeps its Score Differential card", (sportKey, period) => {
    const h = payload({ status: "live", period_markers: [unbracketed(period)] as never });
    expect(decide(sportKey, "live", h)).toEqual({ mount: false, reason: "no_recorded_game_state" });
    const done = payload({ status: "completed", completed_at: COMPLETED_AT, period_markers: [unbracketed(period)] as never });
    expect(decide(sportKey, "completed", done)).toEqual({ mount: false, reason: "no_recorded_game_state" });
  });

  it("men's college basketball does not open on a quarter, even an observed one", () => {
    const h = payload({ status: "live", period_markers: [observed("1st Quarter")] as never });
    expect(decide("basketball_ncaab", "live", h)).toEqual({ mount: false, reason: "no_recorded_game_state" });
  });

  it("once an observed 1H arrives, a men's college basketball page mounts with actuals floored there", () => {
    const h = payload({ status: "live", period_markers: [observed("1st Half")] as never });
    const input = mountedInput("basketball_ncaab", "live", h);
    expect(input.kickoffAt).toBeNull();
    expect(input.scoreObservationStartAt).toBe("2026-11-12T00:10:40Z");
    const s = series(input);
    expect(s.phase).toBe("during");
    // The pregame 0–0 is not an actual score.
    expect(s.actualSteps.map((a) => [a.home, a.away])).toEqual([[12, 8], [30, 22]]);
    expect(s.yTicks.every((v) => v % 20 === 0)).toBe(true);
  });
});

describe("college football mounts during the game on an observed Q1", () => {
  const fbRows = [row("2026-11-11T23:30", 31.5, 24.0, 0.7), row("2026-11-12T00:30", 34.0, 20.5, 0.8)];
  const fbScores = [{ timestamp: "2026-11-12T00:25:00Z", home_score: 7, away_score: 0 }];

  it("draws seven-point ticks and the observed floor; an unbracketed Q1 still refuses", () => {
    const h = payload({ status: "live", bookmaker_history: { draftkings: fbRows }, score_history: fbScores, period_markers: [observed("1st Quarter")] as never });
    const s = series(mountedInput("americanfootball_ncaaf", "live", h));
    expect(s.phase).toBe("during");
    expect(s.yMax).toBe(42);
    expect(s.yTicks).toEqual([0, 7, 14, 21, 28, 35, 42]);
    expect(s.actualSteps.map((a) => [a.home, a.away])).toEqual([[7, 0]]);
    const bare = { ...h, period_markers: [unbracketed("1st Quarter")] } as unknown as EventHistoryResponse;
    expect(decide("americanfootball_ncaaf", "live", bare)).toEqual({ mount: false, reason: "no_recorded_game_state" });
  });
});

describe("the chart explains and speaks the league's own periods", () => {
  const teams = { homeTeam: "Duke Blue Devils", awayTeam: "Kansas Jayhawks" };
  const boundaries = [
    { timestamp: "2026-11-12T00:11:30Z", label: "1H", precision: "first_seen", source: "espn_state" },
    { timestamp: "2026-11-12T00:42:00Z", label: "HT", precision: "first_seen", source: "espn_state" },
  ];

  it("men's college basketball says halves, never quarters, in the copy and to a screen reader", () => {
    const h = payload({ status: "live", period_markers: [observed("1st Half")] as never });
    const input = mountedInput("basketball_ncaab", "live", h);
    const html = renderToStaticMarkup(<ProjectedFinalPointsChart input={input} {...teams} periodBoundaries={boundaries as never} />);
    expect(html).toContain('data-period-marker="1H"');
    expect(html).toContain("mark each half, halftime or overtime");
    expect(html).not.toMatch(/quarter/i);
    expect(html).toMatch(/Game state marked on the chart:.*1st half first seen in progress/);
    expect(html).toMatch(/Halftime first seen in progress/);
  });

  it("a quarter league keeps the quarter wording", () => {
    const h = payload({ status: "live", period_markers: [observed("1st Quarter")] as never });
    const input = mountedInput("basketball_nba", "live", h);
    const qBoundaries = [{ ...boundaries[0], label: "Q1" }, boundaries[1]];
    const html = renderToStaticMarkup(<ProjectedFinalPointsChart input={input} {...teams} periodBoundaries={qBoundaries as never} />);
    expect(html).toContain("mark each quarter, halftime or overtime");
    expect(html).toMatch(/1st quarter first seen in progress/);
  });

  it.each([
    ["Q1", "1st quarter"],
    ["Q2", "2nd quarter"],
    ["Q3", "3rd quarter"],
    ["Q4", "4th quarter"],
    ["1H", "1st half"],
    ["2H", "2nd half"],
    ["HT", "Halftime"],
    ["OT", "Overtime"],
    ["OT2", "2nd overtime"],
    ["/Q2", "End of 2nd quarter"],
    ["/OT", "End of overtime"],
    ["T3", "T3"],
    ["Q0", "Q0"],
  ])("speaks %s as %s", (chip, spoken) => {
    expect(spokenPeriodLabel(chip)).toBe(spoken);
  });
});
