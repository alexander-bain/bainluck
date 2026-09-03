/**
 * ux/1034 B5 — A TENNIS PAGE STOPS PRINTING SETS AS GAMES.
 *
 * Alex, on `/events/15293830` (Marozsan–Zheng, US Open R128, final `0 — 3`):
 *
 *   > Score Differential is in GAMES (the green projection is the books' game
 *   > spread); the bug is "Actual Score Diff" is fed the SET score so it sits
 *   > flat.
 *
 * He had it exactly right, and it is one defect in three widgets. Every number
 * below is that event's, read from production on 2026-09-02:
 *
 *   `home_score` 0, `away_score` 3            <- SETS
 *   `over_under` 34.8                          <- GAMES
 *   `projected_home_score` 15.1 / away 19.7    <- GAMES
 *   `score_history` 0-0, 0-1, 0-2, 0-3         <- SETS, four points, 3.5 hours
 *
 * so the page drew a ±3 step function under a ±5 game axis, graded
 * `FINAL ZHE by 3+` (three SETS) against `PRE-GAME ZHE by 1.5+` (a game and a
 * half), and printed `FINAL 3 games` (three SETS, summed) beside `PRE-GAME 35`.
 *
 * ## What this suite does NOT claim
 *
 * It does not claim the widget now shows the right actual line. Alex's fix —
 * "actual = cumulative games differential from ESPN's linescore" — needs the
 * linescore, and no payload this page fetches carries it (`espn_history` is
 * EMPTY for this event: 0 of 798 snapshots). That is on the bus. What ships is
 * the removal of the wrong-unit line, on the standing rule that a number in the
 * wrong unit is worse than an absent one because it looks sourced.
 *
 * ## The control is the whole test
 *
 * Every assertion below runs twice — once on tennis, once on the same shaped
 * data under `basketball_nba`. A suppression that fired everywhere would pass
 * every tennis assertion in this file and silently delete the actual line from
 * every sport on the site. The point-sport arm is what makes the tennis arm
 * mean something.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import MarketMapSection from "@/components/MarketMapSection";
import ScoreDifferentialChart from "@/components/ScoreDifferentialChart";
import { sportVocab, UNSCORED_IN_POINTS } from "@/lib/marketMapUtils";

function visibleText(html: string): string {
  return html
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Event 15293830's own history, trimmed to the two fields these widgets read. */
const HISTORY = [
  { timestamp: "2026-09-02T18:30:00Z", home_probability: 0.44, away_probability: 0.56, projected_home_score: 17.2, projected_away_score: 17.9, bookmaker_count: 9 },
  { timestamp: "2026-09-02T20:00:00Z", home_probability: 0.28, away_probability: 0.72, projected_home_score: 16.1, projected_away_score: 18.8, bookmaker_count: 11 },
  { timestamp: "2026-09-02T22:05:00Z", home_probability: 0.03, away_probability: 0.97, projected_home_score: 15.1, projected_away_score: 19.7, bookmaker_count: 11 },
];

/** …and its `score_history`, which is FOUR POINTS AND THEY ARE SETS. */
const SET_SCORE_HISTORY = [
  { timestamp: "2026-09-02T18:39:13Z", home_score: 0, away_score: 0 },
  { timestamp: "2026-09-02T21:03:07Z", home_score: 0, away_score: 1 },
  { timestamp: "2026-09-02T21:40:06Z", home_score: 0, away_score: 2 },
  { timestamp: "2026-09-02T22:11:48Z", home_score: 0, away_score: 3 },
];

function renderChart(sportKey: string | undefined) {
  return renderToStaticMarkup(
    <ScoreDifferentialChart
      history={HISTORY as never}
      homeTeam="Fabian Marozsan"
      awayTeam="Michael Zheng"
      commenceTime="2026-09-02T18:27:00Z"
      isLive={false}
      eventStatus="completed"
      scoreHistory={SET_SCORE_HISTORY as never}
      currentHomeScore={0}
      currentAwayScore={3}
      sportKey={sportKey}
    />
  );
}

/** The real shape of a US Open `game-markets` body, with the final set score on it. */
function markets() {
  return {
    event_id: 15293830,
    home_team: "Fabian Marozsan",
    away_team: "Michael Zheng",
    // 0 and 3 SETS. On the basketball arm they are read as points, which is
    // wrong for basketball too but is not what this suite is about — what
    // matters is that the point arm still DRAWS them.
    home_score: 0,
    away_score: 3,
    status: "closed",
    player_props: [],
    team_totals: [],
    period_markets: [],
    matchups: [],
    other: [],
    pace: null,
    props_script: [],
    spreads: [
      { market_name: "Fabian Marozsan vs Michael Zheng: Game Spread", outcome_name: "Michael Zheng -1.5 games", threshold: 1.5, probability: 0.71, source: "kalshi", is_winner: null, resolution_source: null },
      { market_name: "Fabian Marozsan vs Michael Zheng: Game Spread", outcome_name: "Michael Zheng -3.5 games", threshold: 3.5, probability: 0.53, source: "kalshi", is_winner: null, resolution_source: null },
      { market_name: "Fabian Marozsan vs Michael Zheng: Game Spread", outcome_name: "Fabian Marozsan -1.5 games", threshold: 1.5, probability: 0.22, source: "kalshi", is_winner: null, resolution_source: null },
    ],
    totals: [
      { threshold: 32.5, over_probability: 0.66, source: "kalshi", market_type: "game_total", market_name: "Fabian Marozsan vs Michael Zheng: Total Games", outcome_name: "Over 32.5 games", is_winner: null, resolution_source: null, movement: 0, period: null },
      { threshold: 37.5, over_probability: 0.41, source: "kalshi", market_type: "game_total", market_name: "Fabian Marozsan vs Michael Zheng: Total Games", outcome_name: "Over 37.5 games", is_winner: null, resolution_source: null, movement: 0, period: null },
    ],
  };
}

function renderMaps(sportKey: string) {
  return renderToStaticMarkup(
    <MarketMapSection
      gameMarkets={markets() as never}
      eventStatus="completed"
      homeTeam="Fabian Marozsan"
      awayTeam="Michael Zheng"
      homeAbbr="MAR"
      awayAbbr="ZHE"
      homeWinProb={0.0313}
      awayWinProb={0.9687}
      homeSpread={-4.6}
      overUnder={34.8}
      sportKey={sportKey}
    />
  );
}

describe("ux/1034 B5 — the scoreboard's unit is declared, not assumed", () => {
  it("says tennis counts sets while its market quotes games", () => {
    const tennis = sportVocab("tennis_atp_us_open");
    expect(tennis.scoreboardCountsTheUnit).toBe(false);
    expect(tennis.scoreboardUnit).toBe("sets");
    expect(tennis.unit).toBe("games");
    expect(sportVocab("tennis_wta_us_open")).toEqual(tennis);
  });

  /**
   * THE DEFAULT RUNS THE OTHER WAY FROM `hasDerivedSpread`'s, deliberately —
   * see the field's note. Defaulting false would delete a true line from
   * cricket, rugby and every sport nobody has declared yet.
   */
  it("assumes every other sport's scoreboard does count its unit", () => {
    for (const key of [
      "basketball_nba", "americanfootball_nfl", "baseball_mlb",
      "icehockey_nhl", "soccer_epl",
      "cricket_ipl", "rugbyleague_nrl", "aussierules_afl", "",
    ]) {
      expect(sportVocab(key).scoreboardCountsTheUnit).toBe(true);
    }
    expect(UNSCORED_IN_POINTS.scoreboardCountsTheUnit).toBe(true);
    expect(sportVocab(undefined).scoreboardCountsTheUnit).toBe(true);
  });
});

describe("ux/1034 B5 — Score Differential", () => {
  it("draws no actual line for tennis, and says why", () => {
    const html = renderChart("tennis_atp_us_open");

    // The widget is still here and still has its projection — Alex withdrew
    // the hide (D41) and asked for the widget kept.
    expect(html).not.toBe("");
    expect(visibleText(html)).not.toContain("Score data is not available");
    expect(html).toContain('data-projected-series="true"');
    expect(html).toContain("recharts-responsive-container");

    // But the set-count series is not drawn. Asserted through the wrapper
    // attribute and NOT through the legend text, because recharts renders
    // nothing inside `ResponsiveContainer` without a viewport — a guard that
    // looked for the missing `Actual Score Diff` string would pass on both
    // arms and be worth nothing. See the attribute's note.
    expect(html).toContain('data-actual-series="false"');

    // And the absence is stated, in both units, rather than left as a gap.
    expect(html).toContain('data-testid="score-diff-unit-note"');
    const text = visibleText(html);
    expect(text).toContain("Played games are not captured yet");
    expect(text).toContain("the scoreboard reports sets");
  });

  it("still draws it for a point sport — the control", () => {
    const html = renderChart("basketball_nba");
    expect(html).toContain('data-actual-series="true"');
    expect(html).toContain('data-projected-series="true"');
    expect(html).not.toContain('data-testid="score-diff-unit-note"');
  });

  /** A caller that passes no key is unchanged. There is one production caller
   *  and it passes one, but the prop is optional and the default has to be the
   *  old behaviour or this change reaches surfaces nobody reviewed. */
  it("is unchanged for a caller that names no sport", () => {
    expect(renderChart(undefined)).toBe(renderChart("basketball_nba"));
  });
});

describe("ux/1034 B5 — the two market maps", () => {
  it("grades neither margin nor total against a set count", () => {
    const text = visibleText(renderMaps("tennis_atp_us_open"));

    // The rungs, the rail and the pre-game marks all survive — this suppresses
    // the half we cannot state, not the card.
    expect(text).toContain("ZHE by 1.5+");
    expect(text).toContain("Over 32.5");
    expect(text).toContain("Pre-game");

    // What is gone: `FINAL ZHE by 3+` (three sets) and `FINAL 3 games`.
    expect(text).not.toContain("Final");
    expect(text).not.toContain("3 games");

    // A title that promises a comparison the card cannot draw is the same
    // defect one level up, so it reverts to the declared title…
    expect(text).not.toContain("expected vs final");
    expect(text).toContain("Game margin map");
    expect(text).toContain("Games map");
    // …and the card says which two units it is refusing to mix.
    expect(text).toContain("The scoreboard reports sets, this market quotes games");
  });

  it("still grades a point sport against its own scoreboard — the control", () => {
    const text = visibleText(renderMaps("basketball_nba"));
    expect(text).toContain("Final");
    expect(text).toContain("expected vs final");
    expect(text).not.toContain("The scoreboard reports");
  });
});
