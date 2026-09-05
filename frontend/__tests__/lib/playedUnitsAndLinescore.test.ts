/**
 * live/073 — COUNT THE UNIT THE MARKET QUOTES, WHEREVER IT COMES FROM.
 *
 * ux/1034 B5 nulled the scoreboard on a tennis page because `home_score` is
 * SETS and every rail on that page is drawn in GAMES. That was right and it is
 * kept. What it left behind was a finished match whose Games map read
 * `PRE-GAME 29` and "we did not record the games played" — measured over all
 * 207 anchored settled tennis rows on 2026-09-05, every one of them.
 *
 * `Event.linescore` records them now, so the rule these tests pin is the one
 * that replaced "trust the scoreboard": count the unit, from the scoreboard
 * where it counts it and from the line where it does not — and from nothing at
 * all otherwise, still, because an invented number is the defect B5 removed.
 */

import {
  formatLinescore,
  playedUnits,
  sportVocab,
  UNSCORED_IN_POINTS,
} from "@/lib/marketMapUtils";

const TENNIS = sportVocab("tennis_atp_us_open");
const NBA = sportVocab("basketball_nba");

/** Event 15301243 as the API serves it: Wu home, Alcaraz d. Wu 6-3, 6-4, 6-1. */
const WU_ALCARAZ = {
  sets: [[3, 6], [4, 6], [1, 6]] as [number, number][],
  home_games: 8,
  away_games: 18,
  source: "espn",
};

describe("playedUnits — the scoreboard where it counts the unit", () => {
  it("reads a point sport's scoreboard, linescore or no linescore", () => {
    expect(playedUnits(NBA, { home: 112, away: 108 })).toEqual({ home: 112, away: 108 });
    // The scoreboard WINS. A stray line on a sport that counts its own unit
    // must never rewrite a score that is already right.
    expect(playedUnits(NBA, { home: 112, away: 108 }, WU_ALCARAZ)).toEqual({
      home: 112,
      away: 108,
    });
  });

  it("an undeclared sport keeps the scoreboard — B5's default, unchanged", () => {
    expect(UNSCORED_IN_POINTS.scoreboardCountsTheUnit).toBe(true);
    expect(playedUnits(UNSCORED_IN_POINTS, { home: 3, away: 1 })).toEqual({
      home: 3,
      away: 1,
    });
  });

  it("a half-written scoreboard is an absence, not a zero", () => {
    expect(playedUnits(NBA, { home: 112, away: null })).toBeNull();
    expect(playedUnits(NBA, { home: null, away: undefined })).toBeNull();
  });
});

describe("playedUnits — the line where it does not", () => {
  it("counts the games, never the sets", () => {
    expect(playedUnits(TENNIS, { home: 0, away: 3 }, WU_ALCARAZ)).toEqual({
      home: 8,
      away: 18,
    });
  });

  it("the sets on the scoreboard are refused with a line and without one", () => {
    // THE WHOLE OF B5 IN ONE ASSERTION: 0 and 3 are sets, and they never reach
    // a rail measured in games — the absence stays an absence until a real
    // count arrives.
    expect(playedUnits(TENNIS, { home: 0, away: 3 })).toBeNull();
    expect(playedUnits(TENNIS, { home: 0, away: 3 }, null)).toBeNull();
    expect(playedUnits(TENNIS, { home: 0, away: 3 }, undefined)).toBeNull();
  });

  it("an empty line is an absence wearing a shape", () => {
    expect(
      playedUnits(TENNIS, { home: 0, away: 3 }, {
        sets: [],
        home_games: 0,
        away_games: 0,
      })
    ).toBeNull();
  });

  it("a line missing its totals is refused rather than summed here", () => {
    expect(
      playedUnits(TENNIS, { home: 0, away: 3 }, {
        sets: [[3, 6]],
        home_games: undefined as unknown as number,
        away_games: 6,
      })
    ).toBeNull();
  });

  it("a genuine 0-0 first game IS a count, and is not confused with absence", () => {
    /* The one case a truthiness test would get wrong: a set in play at 0-0 has
       a line, and `home_games: 0` is a real number. `sets.length` is what
       separates it from a row we hold nothing for. */
    expect(
      playedUnits(TENNIS, { home: 0, away: 0 }, {
        sets: [[0, 0]],
        home_games: 0,
        away_games: 0,
      })
    ).toEqual({ home: 0, away: 0 });
  });
});

describe("formatLinescore", () => {
  it("prints our order by default", () => {
    expect(formatLinescore(WU_ALCARAZ.sets)).toBe("3-6, 4-6, 1-6");
  });

  it("prints the winner first when the caller says the away side won", () => {
    expect(formatLinescore(WU_ALCARAZ.sets, { reversed: true })).toBe("6-3, 6-4, 6-1");
  });

  it("says nothing about an absent line", () => {
    expect(formatLinescore(null)).toBe("");
    expect(formatLinescore(undefined)).toBe("");
    expect(formatLinescore([])).toBe("");
  });

  it("never infers the winner from the games — the loser can play more", () => {
    /* 7-6, 0-6, 7-6 to the HOME player — two sets to one, and FOURTEEN games
       to eighteen. A "winner first" rule that counted games would print this
       line upside down, naming the loser's score as the result. The caller
       passes the set score's answer in. */
    const sets: [number, number][] = [[7, 6], [0, 6], [7, 6]];
    expect(formatLinescore(sets, { reversed: false })).toBe("7-6, 0-6, 7-6");
    expect(sets.reduce((n, [h]) => n + h, 0)).toBeLessThan(
      sets.reduce((n, [, a]) => n + a, 0)
    );
  });
});
