// L2-158 Item 2: state-honesty logic for team-page game cards.
import {
  isGameLive,
  isGameSettled,
  isGameSuspended,
  assignGameNumbers,
  teamLastScore,
  teamResult,
} from "../../lib/teamGames";
import type { TeamGameBrief } from "../../lib/api";

function brief(overrides: Partial<TeamGameBrief>): TeamGameBrief {
  return {
    id: 1,
    home_team: "Boston Celtics",
    away_team: "Los Angeles Lakers",
    home_score: null,
    away_score: null,
    status: "scheduled",
    commence_time: null,
    sport_key: "basketball_nba",
    is_home: true,
    opponent: "Los Angeles Lakers",
    win_probability: null,
    ...overrides,
  };
}

describe("isGameLive — chip honesty both directions", () => {
  const NOW = new Date("2026-07-22T20:00:00Z").getTime();

  test("LIVE only once the game has actually started", () => {
    const started = brief({
      status: "live",
      commence_time: "2026-07-22T19:00:00Z", // 1h ago
    });
    expect(isGameLive(started, NOW)).toBe(true);
  });

  test("premature 'live' status before commence_time is NOT live", () => {
    // Backend flipped status='live' ~4h before first pitch (gotcha #14). The
    // chip must derive from commence+status BOTH, not status alone.
    const early = brief({
      status: "live",
      commence_time: "2026-07-23T00:00:00Z", // 4h in the future
    });
    expect(isGameLive(early, NOW)).toBe(false);
  });

  test("scheduled games are never live", () => {
    expect(
      isGameLive(brief({ status: "scheduled", commence_time: "2026-07-22T19:00:00Z" }), NOW),
    ).toBe(false);
  });

  test("live status with no commence_time is not live (can't prove it started)", () => {
    expect(isGameLive(brief({ status: "live", commence_time: null }), NOW)).toBe(false);
  });
});

describe("isGameSettled — completed AND closed", () => {
  test("completed is settled", () => {
    expect(isGameSettled(brief({ status: "completed" }))).toBe(true);
  });
  test("closed is settled (r242: closed games must not vanish)", () => {
    expect(isGameSettled(brief({ status: "closed" }))).toBe(true);
  });
  test("scheduled/live are not settled", () => {
    expect(isGameSettled(brief({ status: "scheduled" }))).toBe(false);
    expect(isGameSettled(brief({ status: "live" }))).toBe(false);
  });
});

describe("assignGameNumbers — a G-chip comes from the provider, or not at all (#2866)", () => {
  // The exact production shape lane1/082 photographed on the Bears page: same
  // opponent, same calendar day, same result — two rows for ONE game, because
  // 47 of 50 NFL preseason rows have a regular-season twin. Every arm below
  // reuses it, because the point of this suite is that no property of these two
  // rows can produce a chip.
  const twin = (o: Partial<TeamGameBrief> = {}) => [
    brief({ id: 1, opponent: "Tennessee Titans", commence_time: "2026-08-29T17:00:00", ...o }),
    brief({ id: 2, opponent: "Tennessee Titans", commence_time: "2026-08-29T17:00:00", ...o }),
  ];

  test("a same-day opponent pair with no authority gets NO chips — in ANY league", () => {
    // lane1/087 gated the old inference to MLB. That stopped the NFL case and
    // not the class: inside MLB a twin and a real doubleheader are IDENTICAL
    // under same-day pairing, so the chip could still launder a duplicate. The
    // MLB arm is the one that used to be a passing "CONTROL" asserting G1/G2 —
    // it is now the regression this suite exists for, so it is listed FIRST.
    for (const league of ["mlb", "MLB", "nfl", "nba", "nhl", "epl", "ncaaf", "", "MLB-ish"]) {
      const nums = assignGameNumbers(twin());
      expect(nums[1]).toBeUndefined();
      expect(nums[2]).toBeUndefined();
      // The league is not an argument any more, and that is deliberate. Reading
      // it here keeps the loop honest about what it is sweeping over: the
      // answer must be the same for every one of these, INCLUDING baseball.
      expect(league).toBeDefined();
    }
  });

  test("CONTROL: the provider's own doubleheader metadata DOES get G1/G2", () => {
    // Without this arm a function hard-wired to `return {}` would pass every
    // guard above perfectly — the one-armed-test failure mode. `doubleHeader`
    // and `gameNumber` are MLB Stats API's own field names, already parsed by
    // schedule_sentinel.py's TruthGame.
    const [g1, g2] = twin();
    const nums = assignGameNumbers([
      { ...g2, doubleheader: true, game_number: 2 },
      { ...g1, doubleheader: true, game_number: 1 },
    ]);
    expect(nums[1]).toBe(1);
    expect(nums[2]).toBe(2);
  });

  test("the number is the PROVIDER's, not the array's — order cannot renumber a game", () => {
    // The old function derived N from position after sorting by commence_time.
    // Two games of a doubleheader routinely share a placeholder start time, so
    // that ordering was unstable exactly where it mattered. Here game 2 is
    // listed first and is still game 2.
    const nums = assignGameNumbers([
      brief({ id: 7, doubleheader: true, game_number: 2 }),
      brief({ id: 8, doubleheader: true, game_number: 1 }),
    ]);
    expect(nums[7]).toBe(2);
    expect(nums[8]).toBe(1);
  });

  test("a vouched game numbers alone — half a pair is still the provider's word", () => {
    // Only one of the two can fall inside the recents window. Suppressing the
    // survivor would be inventing a "pair must be present" rule the provider
    // never stated.
    expect(assignGameNumbers([brief({ id: 3, doubleheader: true, game_number: 2 })])[3]).toBe(2);
  });

  test("doubleheader:true with an unusable game_number gets NO chip", () => {
    // Missing, null, zero, negative, fractional, NaN. Each is "the authority
    // did not actually say"; a `G0` chip would be the same confident lie in a
    // new font. `false as never`-free: these are the shapes JSON can deliver.
    const bad = [undefined, null, 0, -1, 1.5, NaN] as (number | null | undefined)[];
    for (const game_number of bad) {
      const nums = assignGameNumbers([brief({ id: 4, doubleheader: true, game_number })]);
      expect(nums[4]).toBeUndefined();
    }
  });

  test("a game_number WITHOUT doubleheader:true gets NO chip", () => {
    // MLB stamps `gameNumber: 1` on ordinary single games too, so the number
    // alone is not a claim of anything. Both fields, or no chip.
    for (const doubleheader of [undefined, null, false]) {
      const nums = assignGameNumbers([brief({ id: 5, doubleheader, game_number: 1 })]);
      expect(nums[5]).toBeUndefined();
    }
  });

  test("today's real payload — no authority fields at all — yields an empty map", () => {
    // The state on production the day this shipped: `_format_event_brief` emits
    // neither field. Empty is the CORRECT answer here, not a placeholder.
    expect(assignGameNumbers(twin())).toEqual({});
  });
});

describe("teamResult — team-relative W/L", () => {
  // live/056: `teamResult` now requires a SETTLED status, so these fixtures say
  // so. They previously read `scheduled` and still graded — which was the same
  // defect this change closes, told smaller: two numbers were treated as a
  // verdict without anything having said the match ended.
  const settled = (o: Partial<TeamGameBrief>) =>
    brief({ status: "completed", ...o });

  test("home win", () => {
    expect(
      settledResult({ is_home: true, home_score: 6, away_score: 1 }),
    ).toEqual({ char: "W", teamScore: 6, oppScore: 1 });
  });
  test("away win (is_home false flips perspective)", () => {
    expect(
      settledResult({ is_home: false, home_score: 1, away_score: 6 }),
    ).toEqual({ char: "W", teamScore: 6, oppScore: 1 });
  });
  test("loss and tie", () => {
    expect(settledResult({ is_home: true, home_score: 1, away_score: 3 })?.char).toBe("L");
    expect(settledResult({ is_home: true, home_score: 2, away_score: 2 })?.char).toBe("T");
  });
  test("null scores yield null", () => {
    expect(settledResult({ home_score: null, away_score: null })).toBeNull();
  });
  test("'closed' grades exactly like 'completed' (#1204)", () => {
    expect(
      teamResult(settled({ status: "closed", is_home: true, home_score: 6, away_score: 1 }))
        ?.char,
    ).toBe("W");
  });

  function settledResult(o: Partial<TeamGameBrief>) {
    return teamResult(settled(o));
  }
});

describe("teamResult refuses to grade a match nothing settled (live/056)", () => {
  // 🔴 THE SHIP GUARD. The team page's recent rail now carries `suspended`, and
  // a suspended row arrives with the PARTIAL score play reached. Grading 1-2 as
  // an "L" is the false Final live/048 removed, printed by a different
  // component — so the function that mints the verdict refuses.
  test("a suspended match with a partial score is NOT a loss", () => {
    expect(
      teamResult(
        brief({ status: "suspended", is_home: true, home_score: 1, away_score: 2 }),
      ),
    ).toBeNull();
  });

  test.each(["suspended", "live", "scheduled"] as const)(
    "%s never yields a W/L, however complete the score looks",
    (status) => {
      expect(
        teamResult(brief({ status, is_home: true, home_score: 6, away_score: 1 })),
      ).toBeNull();
    },
  );

  test("isGameSuspended reads the shared vocabulary, not a local literal", () => {
    expect(isGameSuspended(brief({ status: "suspended" }))).toBe(true);
    for (const status of ["completed", "closed", "live", "scheduled"] as const) {
      expect(isGameSuspended(brief({ status }))).toBe(false);
    }
  });

  test("isGameSettled still excludes suspended — settled means settled", () => {
    expect(isGameSettled(brief({ status: "suspended" }))).toBe(false);
    expect(isGameSettled(brief({ status: "completed" }))).toBe(true);
    expect(isGameSettled(brief({ status: "closed" }))).toBe(true);
  });
});

describe("teamLastScore — what IS known about a suspended match", () => {
  test("team-relative, both directions", () => {
    expect(
      teamLastScore(brief({ is_home: true, home_score: 1, away_score: 2 })),
    ).toEqual({ teamScore: 1, oppScore: 2 });
    expect(
      teamLastScore(brief({ is_home: false, home_score: 1, away_score: 2 })),
    ).toEqual({ teamScore: 2, oppScore: 1 });
  });

  test("a HALF score is no score — the CERT-752 partial-line trap", () => {
    expect(teamLastScore(brief({ home_score: 1, away_score: null }))).toBeNull();
    expect(teamLastScore(brief({ home_score: null, away_score: 2 }))).toBeNull();
  });
});
