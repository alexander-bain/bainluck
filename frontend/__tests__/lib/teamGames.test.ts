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

describe("assignGameNumbers — doubleheaders", () => {
  test("two games vs the same opponent on the same day get G1/G2 in time order", () => {
    // Local (no Z) datetimes so the calendar-day grouping is timezone-stable.
    const g2 = brief({ id: 2, opponent: "New York Yankees", commence_time: "2026-07-22T19:00:00" });
    const g1 = brief({ id: 1, opponent: "New York Yankees", commence_time: "2026-07-22T13:00:00" });
    const nums = assignGameNumbers([g2, g1]);
    expect(nums[1]).toBe(1);
    expect(nums[2]).toBe(2);
  });

  test("a solo game gets no number", () => {
    const solo = brief({ id: 9, opponent: "New York Yankees", commence_time: "2026-07-22T13:00:00" });
    expect(assignGameNumbers([solo])[9]).toBeUndefined();
  });

  test("same opponent on different days are not a doubleheader", () => {
    const a = brief({ id: 1, opponent: "Yankees", commence_time: "2026-07-22T13:00:00" });
    const b = brief({ id: 2, opponent: "Yankees", commence_time: "2026-07-23T13:00:00" });
    const nums = assignGameNumbers([a, b]);
    expect(nums[1]).toBeUndefined();
    expect(nums[2]).toBeUndefined();
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
