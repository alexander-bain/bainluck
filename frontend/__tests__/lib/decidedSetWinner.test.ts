/**
 * ux/1103 (#3629) — the two pure functions behind "a set that is over says who
 * won it", and the arithmetic that lets them.
 *
 * A tennis event carries SETS WON, never a per-set line. `0` / `1` says Noskova
 * is a set up and says nothing about ORDER — but while one side is still on
 * zero, order does not matter: every set already played went the same way. That
 * single observation is the whole ship, and `min === 0` is the whole test.
 *
 * The rest of this file is the refusals. A frozen `last quote 0%` is weak; a
 * settled row naming the WRONG player is a lie on a marquee page, so each door
 * `decidedSetResult` can close gets a case here.
 */

import {
  completedSetsForTennis,
  decidedSetResult,
  decidedSetsWinnerFor,
} from "@/lib/otherMarketGroups";

const KOSTYUK_NOSKOVA = { home_team: "Marta Kostyuk", away_team: "Linda Noskova" };

describe("decidedSetsWinnerFor", () => {
  test("one side on zero names that side's opponent as the winner of every played set", () => {
    expect(decidedSetsWinnerFor("tennis_wta_us_open", { ...KOSTYUK_NOSKOVA, home_score: 0, away_score: 1 }))
      .toEqual({ side: "away", homeTeam: "Marta Kostyuk", awayTeam: "Linda Noskova" });
    expect(decidedSetsWinnerFor("tennis_atp_us_open", { ...KOSTYUK_NOSKOVA, home_score: 2, away_score: 0 }))
      .toEqual({ side: "home", homeTeam: "Marta Kostyuk", awayTeam: "Linda Noskova" });
  });

  test("a set apiece refuses — the score cannot say which set went which way", () => {
    expect(decidedSetsWinnerFor("tennis_atp", { ...KOSTYUK_NOSKOVA, home_score: 1, away_score: 1 })).toBeNull();
    expect(decidedSetsWinnerFor("tennis_atp", { ...KOSTYUK_NOSKOVA, home_score: 2, away_score: 1 })).toBeNull();
  });

  test("no set finished yet refuses", () => {
    expect(decidedSetsWinnerFor("tennis_wta", { ...KOSTYUK_NOSKOVA, home_score: 0, away_score: 0 })).toBeNull();
  });

  test("a score that cannot be a set count refuses, so games or points cannot leak in", () => {
    // Inherited from `completedSetsForTennis`: six sets have never been played.
    expect(decidedSetsWinnerFor("tennis_atp", { ...KOSTYUK_NOSKOVA, home_score: 0, away_score: 6 })).toBeNull();
    expect(completedSetsForTennis("tennis_atp", { home_score: 0, away_score: 6 })).toBe(0);
  });

  test("every non-tennis sport refuses at the first door", () => {
    for (const sport of ["baseball_mlb", "basketball_nba", "table_tennis", "americanfootball_nfl", "", null]) {
      expect(decidedSetsWinnerFor(sport, { ...KOSTYUK_NOSKOVA, home_score: 0, away_score: 1 })).toBeNull();
    }
  });

  test("a missing or absent score refuses — doubles arrive with both null", () => {
    expect(decidedSetsWinnerFor("tennis_other", { ...KOSTYUK_NOSKOVA, home_score: null, away_score: null })).toBeNull();
    expect(decidedSetsWinnerFor("tennis_other", KOSTYUK_NOSKOVA)).toBeNull();
    expect(decidedSetsWinnerFor("tennis_other", null)).toBeNull();
  });

  test("a nameless side refuses — there would be nothing to say", () => {
    expect(decidedSetsWinnerFor("tennis_wta", { home_team: "", away_team: "Linda Noskova", home_score: 0, away_score: 1 })).toBeNull();
    expect(decidedSetsWinnerFor("tennis_wta", { home_team: "Marta Kostyuk", away_team: "   ", home_score: 0, away_score: 1 })).toBeNull();
  });
});

describe("decidedSetResult", () => {
  const AWAY_UP = { side: "away" as const, homeTeam: "Marta Kostyuk", awayTeam: "Linda Noskova" };
  const HOME_UP = { side: "home" as const, homeTeam: "Marta Kostyuk", awayTeam: "Linda Noskova" };

  test("a surname pairs with the person it belongs to", () => {
    const parts = { scope: "Set 1", first: "Kostyuk", second: "Noskova" };
    expect(decidedSetResult(parts, AWAY_UP)).toBe("Noskova won Set 1");
    expect(decidedSetResult(parts, HOME_UP)).toBe("Kostyuk won Set 1");
  });

  test("the market may list its sides in either order", () => {
    const reversed = { scope: "Set 2", first: "Noskova", second: "Kostyuk" };
    expect(decidedSetResult(reversed, AWAY_UP)).toBe("Noskova won Set 2");
    expect(decidedSetResult(reversed, HOME_UP)).toBe("Kostyuk won Set 2");
  });

  test("it says the market's own scope, never a reconstructed one", () => {
    // Keeps `Set 3` reading as the market wrote it, and keeps this function out
    // of the business of numbering periods.
    expect(decidedSetResult({ scope: "Set 3", first: "Kostyuk", second: "Noskova" }, AWAY_UP))
      .toBe("Noskova won Set 3");
  });

  test("accents fold, because the wire and the scoreboard disagree about them", () => {
    const winner = { side: "home" as const, homeTeam: "Iva Jović", awayTeam: "Coco Gauff" };
    expect(decidedSetResult({ scope: "Set 1", first: "Jovic", second: "Gauff" }, winner))
      .toBe("Jovic won Set 1");
  });

  test("a doubles pair matches only when BOTH surnames are present", () => {
    const winner = {
      side: "away" as const,
      homeTeam: "Bolelli/Vavassori",
      awayTeam: "Gille/Verbeek",
    };
    expect(decidedSetResult({ scope: "Set 1", first: "Bolelli/Vavassori", second: "Gille/Verbeek" }, winner))
      .toBe("Gille/Verbeek won Set 1");
    // One name in common is not the same pair.
    expect(decidedSetResult({ scope: "Set 1", first: "Bolelli/Nys", second: "Gille/Verbeek" }, winner)).toBeNull();
  });

  test("two competitors sharing a surname refuse — a side matching both teams is no pairing", () => {
    const brothers = { side: "home" as const, homeTeam: "Bob Bryan", awayTeam: "Mike Bryan" };
    expect(decidedSetResult({ scope: "Set 1", first: "Bryan", second: "Bryan" }, brothers)).toBeNull();
  });

  test("sides belonging to a different match refuse", () => {
    expect(decidedSetResult({ scope: "Set 1", first: "Gauff", second: "Osaka" }, AWAY_UP)).toBeNull();
  });

  test("half a pairing refuses — one recognised side is not enough", () => {
    expect(decidedSetResult({ scope: "Set 1", first: "Kostyuk", second: "Rybakina" }, AWAY_UP)).toBeNull();
  });

  test("no parts and no winner both refuse", () => {
    expect(decidedSetResult(null, AWAY_UP)).toBeNull();
    expect(decidedSetResult({ scope: "Set 1", first: "Kostyuk", second: "Noskova" }, null)).toBeNull();
    expect(decidedSetResult(undefined, undefined)).toBeNull();
  });
});
